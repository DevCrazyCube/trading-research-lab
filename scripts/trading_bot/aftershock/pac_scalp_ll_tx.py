#!/usr/bin/env python3
"""Exact calibration-only transaction profile for matched submit-latency measurement.

The transaction cannot trade: it contains only ComputeBudget limit/price, a fixed SOL tip transfer,
and a campaign memo.  Both control and intervention submit the identical signed wire profile.  The
wire is reparsed and its ed25519 signature verified before it can leave the process.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
import struct

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from .execution import RefusedExecution
from . import pac_v2_calibration as solana


PROFILE = "CALIBRATION_TIP_PRIORITY_MEMO_NO_TRADE_LEGACY_V1"
COMPUTE_BUDGET_PROGRAM = "ComputeBudget111111111111111111111111111111"
SYSTEM_PROGRAM = "11111111111111111111111111111111"
MEMO_PROGRAM = solana.MEMO_PROGRAM_ID
TIP_ACCOUNTS = (
    "4ACfpUFoaSD9bfPdeu6DBt89gB6ENTeHBXCAi87NhDEE",
    "D2L6yPZ2FmmmTKPgzaMKdhu6EWZcTpLy1Vhx8uvZe7NZ",
    "9bnz4RShgq1hAnLnZbP8kbgBg1kEmcJBYQq3gQbmnSta",
    "5VY91ws6B2hMmBFRsXkoAAdsPHBJwRfBht4DXox3xkwn",
    "2nyhqdwKcJZR2vcqCyrYsaPVdAnFoJjiksCXJ7hfEYgD",
    "2q5pghRs6arqVjRvT5gfgWfWcHWmw1ZuCzphgd5KfWGJ",
    "wyvPkWjVZz1M8fHQnMMCDTQDbkManefNNhweYk5WkcF",
    "3KCKozbAaF75qEU33jtzozcJ29yJuaLJTy2jFdzUY8bT",
    "4vieeGHPYPG2MmyPRcYjdiDmmhN3ww7hsFNap8pVN3Ey",
    "4TQLFNWK8AovT1gFvda5jfw2oJeRMKEmw7aH6MGBJ3or",
)
MIN_SWQOS_TIP_LAMPORTS = 5_000


def _shortvec(value: int) -> bytes:
    if type(value) is not int or value < 0:
        raise RefusedExecution("shortvec value is invalid")
    output = bytearray()
    while True:
        byte = value & 0x7f
        value >>= 7
        output.append(byte | (0x80 if value else 0))
        if not value:
            return bytes(output)


def _read_shortvec(raw: bytes, offset: int) -> tuple[int, int]:
    value = shift = 0
    for _ in range(4):
        if offset >= len(raw):
            raise RefusedExecution("truncated shortvec")
        byte = raw[offset]; offset += 1
        value |= (byte & 0x7f) << shift
        if not byte & 0x80:
            return value, offset
        shift += 7
    raise RefusedExecution("overlong shortvec")


def campaign_memo(campaign_sha256: str, arm: str, attempt_index: int) -> bytes:
    if (not isinstance(campaign_sha256, str) or len(campaign_sha256) != 64
            or any(c not in "0123456789abcdef" for c in campaign_sha256)
            or arm not in {"PUBLIC_CONTROL", "LOW_LATENCY_INTERVENTION"}
            or type(attempt_index) is not int or attempt_index < 0):
        raise RefusedExecution("calibration memo identity is invalid")
    # One-byte arm code keeps both treatments exactly equal in wire length.
    arm_code = {"PUBLIC_CONTROL": "C", "LOW_LATENCY_INTERVENTION": "I"}[arm]
    memo = f"PAC_SCALP_LL:{campaign_sha256}:{arm_code}:{attempt_index:06d}".encode("ascii")
    if len(memo) > 128:
        raise RefusedExecution("calibration memo exceeds frozen profile")
    return memo


@dataclass(frozen=True)
class Profile:
    compute_unit_limit: int
    micro_lamports_per_cu: int
    tip_lamports: int
    tip_account: str

    def __post_init__(self) -> None:
        if (type(self.compute_unit_limit) is not int or not 1 <= self.compute_unit_limit <= 200_000
                or type(self.micro_lamports_per_cu) is not int
                or self.micro_lamports_per_cu <= 0
                or type(self.tip_lamports) is not int
                or self.tip_lamports < MIN_SWQOS_TIP_LAMPORTS
                or self.tip_account not in TIP_ACCOUNTS):
            raise RefusedExecution("calibration transaction profile is invalid")


def build(private: Ed25519PrivateKey, *, recent_blockhash: bytes, memo: bytes,
          profile: Profile) -> tuple[str, str, str]:
    if not isinstance(private, Ed25519PrivateKey) or len(recent_blockhash) != 32 \
            or not isinstance(memo, bytes) or not memo:
        raise RefusedExecution("calibration transaction build inputs are invalid")
    payer = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    accounts = (
        payer,
        solana._b58decode("tip account", profile.tip_account, exact_length=32),
        solana._b58decode("compute budget", COMPUTE_BUDGET_PROGRAM, exact_length=32),
        solana._b58decode("memo program", MEMO_PROGRAM, exact_length=32),
        solana._b58decode("system program", SYSTEM_PROGRAM, exact_length=32),
    )
    # payer signer+writable; tip unsigned+writable; three unsigned readonly programs.
    header = bytes((1, 0, 3))
    instructions = (
        bytes((2,)) + _shortvec(0) + _shortvec(5)
        + bytes((2,)) + struct.pack("<I", profile.compute_unit_limit),
        bytes((2,)) + _shortvec(0) + _shortvec(9)
        + bytes((3,)) + struct.pack("<Q", profile.micro_lamports_per_cu),
        bytes((4,)) + _shortvec(2) + bytes((0, 1)) + _shortvec(12)
        + struct.pack("<IQ", 2, profile.tip_lamports),
        bytes((3,)) + _shortvec(0) + _shortvec(len(memo)) + memo,
    )
    message = (header + _shortvec(len(accounts)) + b"".join(accounts) + recent_blockhash
               + _shortvec(len(instructions)) + b"".join(instructions))
    signature = private.sign(message)
    wire = _shortvec(1) + signature + message
    encoded = base64.b64encode(wire).decode("ascii")
    parsed = verify(encoded, expected_memo=memo, expected_profile=profile)
    return encoded, parsed["signature"], parsed["fee_payer"]


def verify(encoded: str, *, expected_memo: bytes, expected_profile: Profile) -> dict:
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError) as exc:
        raise RefusedExecution("calibration transaction is invalid base64") from exc
    sig_count, offset = _read_shortvec(raw, 0)
    if sig_count != 1 or offset + 64 > len(raw):
        raise RefusedExecution("calibration transaction is not single-signer")
    signature = raw[offset:offset + 64]; message = raw[offset + 64:]
    cursor = 0
    if message[:3] != bytes((1, 0, 3)):
        raise RefusedExecution("calibration transaction header/profile mismatch")
    cursor = 3
    count, cursor = _read_shortvec(message, cursor)
    if count != 5 or cursor + count * 32 + 32 > len(message):
        raise RefusedExecution("calibration transaction account schema mismatch")
    accounts = [message[cursor + i * 32:cursor + (i + 1) * 32] for i in range(count)]
    cursor += count * 32
    blockhash = message[cursor:cursor + 32]; cursor += 32
    expected_programs = (
        solana._b58decode("compute budget", COMPUTE_BUDGET_PROGRAM, exact_length=32),
        solana._b58decode("memo program", MEMO_PROGRAM, exact_length=32),
        solana._b58decode("system program", SYSTEM_PROGRAM, exact_length=32),
    )
    if (accounts[1] != solana._b58decode(
            "tip account", expected_profile.tip_account, exact_length=32)
            or tuple(accounts[2:]) != expected_programs):
        raise RefusedExecution("calibration transaction account/program substitution")
    instruction_count, cursor = _read_shortvec(message, cursor)
    instructions = []
    for _ in range(instruction_count):
        if cursor >= len(message):
            raise RefusedExecution("calibration transaction instruction is truncated")
        program = message[cursor]; cursor += 1
        account_count, cursor = _read_shortvec(message, cursor)
        account_indices = message[cursor:cursor + account_count]; cursor += account_count
        data_len, cursor = _read_shortvec(message, cursor)
        data = message[cursor:cursor + data_len]; cursor += data_len
        if len(account_indices) != account_count or len(data) != data_len:
            raise RefusedExecution("calibration transaction instruction payload is truncated")
        instructions.append((program, account_indices, data))
    expected = [
        (2, b"", bytes((2,)) + struct.pack("<I", expected_profile.compute_unit_limit)),
        (2, b"", bytes((3,)) + struct.pack("<Q", expected_profile.micro_lamports_per_cu)),
        (4, bytes((0, 1)), struct.pack("<IQ", 2, expected_profile.tip_lamports)),
        (3, b"", expected_memo),
    ]
    if cursor != len(message) or instruction_count != 4 or instructions != expected:
        raise RefusedExecution("calibration transaction instruction profile drift")
    try:
        Ed25519PublicKey.from_public_bytes(accounts[0]).verify(signature, message)
    except (InvalidSignature, ValueError) as exc:
        raise RefusedExecution("calibration transaction signature is invalid") from exc
    return {
        "signature": solana._b58encode(signature), "fee_payer": solana._b58encode(accounts[0]),
        "recent_blockhash": solana._b58encode(blockhash), "profile": PROFILE,
    }
