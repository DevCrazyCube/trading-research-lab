#!/usr/bin/env python3
"""Causal PAC V2 account snapshots for PAPER-SCENARIO pricing.

The snapshot is observed *after* a modeled landing target.  It is not a historical state and it is
not relabelled as an executable fill.  Unlike PAC V1's trade-boundary model, it remains observable
when a dead mint produces no later trade.  The raw RPC exchange is durably appended before any
economic interpretation is returned.
"""
from __future__ import annotations

import base64
from dataclasses import asdict, dataclass
import hashlib
import json
import os
import pathlib
import struct
import time
import urllib.error
import urllib.request
from typing import Protocol

from scripts.trading_bot.aftershock.execution import ReserveState, RefusedExecution


ROOT = pathlib.Path(__file__).resolve().parents[3]
EXCHANGES = ROOT / "research" / "data" / "aftershock" / "pac_v2" / "snapshot_exchanges.jsonl"
PUBLIC_RPC_URL = "https://api.mainnet-beta.solana.com"
SCHEMA = 1
SOURCE = "public_rpc_processed_account_snapshot"
MAX_SNAPSHOT_STALENESS_NANOS = 30_000_000_000
PUMP_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
_DISCRIMINATOR = bytes.fromhex("17b7f83760d8ac60")
_ACCOUNT_LENGTH = 115
_ACCOUNT_SOL_QUOTE_MINT = "So11111111111111111111111111111111111111112"
_B58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_ED_Q = 2 ** 255 - 19
_ED_D = (-121665 * pow(121666, _ED_Q - 2, _ED_Q)) % _ED_Q


def _b58decode(text: str) -> bytes:
    if not isinstance(text, str) or not text:
        raise ValueError("base58 text required")
    number = 0
    for char in text:
        if char not in _B58_ALPHABET:
            raise ValueError("invalid base58 character")
        number = number * 58 + _B58_ALPHABET.index(char)
    raw = number.to_bytes((number.bit_length() + 7) // 8, "big") if number else b""
    return b"\x00" * (len(text) - len(text.lstrip("1"))) + raw


def _b58encode(raw: bytes) -> str:
    number = int.from_bytes(raw, "big"); out = ""
    while number:
        number, remainder = divmod(number, 58)
        out = _B58_ALPHABET[remainder] + out
    return "1" * (len(raw) - len(raw.lstrip(b"\x00"))) + (out or "1")


def _is_on_curve(encoded: bytes) -> bool:
    if len(encoded) != 32:
        return False
    y = int.from_bytes(encoded, "little"); sign = (y >> 255) & 1; y &= (1 << 255) - 1
    if y >= _ED_Q:
        return False
    denominator = (_ED_D * y * y + 1) % _ED_Q
    if denominator == 0:
        return False
    x2 = ((y * y - 1) * pow(denominator, _ED_Q - 2, _ED_Q)) % _ED_Q
    x = pow(x2, (_ED_Q + 3) // 8, _ED_Q)
    if (x * x - x2) % _ED_Q:
        x = (x * pow(2, (_ED_Q - 1) // 4, _ED_Q)) % _ED_Q
    return (x * x - x2) % _ED_Q == 0 and not (x == 0 and sign)


def _bonding_curve_pda(mint: str) -> str | None:
    try:
        mint_bytes = _b58decode(mint); program = _b58decode(PUMP_PROGRAM)
    except ValueError:
        return None
    if len(mint_bytes) != 32 or len(program) != 32:
        return None
    for bump in range(255, -1, -1):
        candidate = hashlib.sha256(
            b"bonding-curve" + mint_bytes + bytes([bump]) + program
            + b"ProgramDerivedAddress").digest()
        if not _is_on_curve(candidate):
            return _b58encode(candidate)
    return None


class SnapshotUnavailable(RefusedExecution):
    """A named account/transport observation failure; never a scenario fill."""


def _canonical_sha(value: object) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


def _append(path: pathlib.Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existed = path.exists()
    payload = (json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode()
    descriptor = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        written = os.write(descriptor, payload)
        if written != len(payload):
            raise OSError(f"short snapshot exchange append {written}/{len(payload)}")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    if not existed:
        directory = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)


@dataclass(frozen=True)
class LandingSnapshot:
    mint: str
    bonding_curve: str
    modeled_target_unix_nanos: int
    minimum_context_slot: int
    request_started_unix_nanos: int
    response_received_unix_nanos: int
    context_slot: int
    state: ReserveState
    endpoint_scheme_host: str
    raw_response_sha256: str
    source: str = SOURCE

    def __post_init__(self) -> None:
        if not all(isinstance(value, str) and value for value in (
                self.mint, self.bonding_curve, self.endpoint_scheme_host)):
            raise RefusedExecution("PAC V2 snapshot identity is incomplete")
        for label, value in (("modeled target", self.modeled_target_unix_nanos),
                             ("minimum context slot", self.minimum_context_slot),
                             ("request start", self.request_started_unix_nanos),
                             ("response receive", self.response_received_unix_nanos),
                             ("context slot", self.context_slot)):
            if type(value) is not int or value < 0:
                raise RefusedExecution(f"PAC V2 snapshot {label} is not an exact coordinate")
        if not (self.modeled_target_unix_nanos <= self.request_started_unix_nanos
                <= self.response_received_unix_nanos):
            raise RefusedExecution("PAC V2 snapshot precedes its modeled landing target")
        if self.response_received_unix_nanos - self.modeled_target_unix_nanos > MAX_SNAPSHOT_STALENESS_NANOS:
            raise RefusedExecution("PAC V2 snapshot is too stale to represent the modeled landing")
        if self.context_slot < self.minimum_context_slot:
            raise RefusedExecution("PAC V2 snapshot context predates its decision evidence")
        if not isinstance(self.state, ReserveState):
            raise RefusedExecution("PAC V2 snapshot state is untyped")
        if (not isinstance(self.raw_response_sha256, str)
                or len(self.raw_response_sha256) != 64
                or any(c not in "0123456789abcdef" for c in self.raw_response_sha256)):
            raise RefusedExecution("PAC V2 snapshot response hash is invalid")
        if self.source != SOURCE:
            raise RefusedExecution("PAC V2 snapshot source cannot be relabelled")


class SnapshotProvider(Protocol):
    def capture(self, mint: str, modeled_target_unix_nanos: int,
                minimum_context_slot: int) -> LandingSnapshot: ...


def _decode_state(raw: bytes) -> ReserveState:
    """Decode only the exact BondingCurve layout in the pinned Pump IDL.

    Layout after the discriminator: five little-endian u64 values, bool, creator pubkey, mayhem bool,
    cashback bool, quote-mint pubkey.  Refusing any suffix makes an upstream layout extension visible
    instead of silently parsing old offsets as the current schema.
    """
    if not isinstance(raw, bytes) or len(raw) != _ACCOUNT_LENGTH or raw[:8] != _DISCRIMINATOR:
        raise RefusedExecution("PAC V2 account bytes differ from the pinned 115-byte BondingCurve schema")
    virtual_token, virtual_quote, real_token, real_quote, _supply = struct.unpack_from("<5Q", raw, 8)
    complete = raw[48]
    mayhem = raw[81]
    cashback = raw[82]
    if complete not in {0, 1} or mayhem not in {0, 1} or cashback not in {0, 1}:
        raise RefusedExecution("PAC V2 account contains a non-boolean schema byte")
    if mayhem:
        raise RefusedExecution("PAC V2 account entered unsupported mayhem mode")
    if raw[83:115] != _b58decode(_ACCOUNT_SOL_QUOTE_MINT):
        raise RefusedExecution("PAC V2 account is not native-SOL quoted")
    return ReserveState(
        virtual_quote=virtual_quote, virtual_token=virtual_token,
        real_quote=real_quote, real_token=real_token, complete=bool(complete))


class PublicRpcSnapshotProvider:
    """Read one processed account state.  This class has no signing or transaction method."""

    def __init__(self, *, url: str = PUBLIC_RPC_URL, exchange_path: pathlib.Path = EXCHANGES,
                 timeout_seconds: float = 8.0, opener=None):
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            raise RefusedExecution("PAC V2 snapshot URL is invalid")
        if type(timeout_seconds) not in {int, float} or timeout_seconds <= 0:
            raise RefusedExecution("PAC V2 snapshot timeout is invalid")
        self.url = url
        self.exchange_path = pathlib.Path(exchange_path)
        self.timeout_seconds = float(timeout_seconds)
        self.opener = opener

    def capture(self, mint: str, modeled_target_unix_nanos: int,
                minimum_context_slot: int) -> LandingSnapshot:
        if (not isinstance(mint, str) or not mint or type(modeled_target_unix_nanos) is not int
                or modeled_target_unix_nanos < 0 or type(minimum_context_slot) is not int
                or minimum_context_slot < 0):
            raise RefusedExecution("PAC V2 snapshot request is malformed")
        started = time.time_ns()
        if started < modeled_target_unix_nanos:
            raise RefusedExecution("PAC V2 snapshot requested before modeled landing target")
        curve = _bonding_curve_pda(mint)
        if not curve:
            raise RefusedExecution("PAC V2 cannot derive the bonding-curve PDA")
        request_body = {"jsonrpc": "2.0", "id": 1, "method": "getAccountInfo",
                        "params": [curve, {"encoding": "base64", "commitment": "processed",
                                           "minContextSlot": minimum_context_slot}]}
        encoded = json.dumps(request_body, separators=(",", ":")).encode()
        request = urllib.request.Request(
            self.url, data=encoded, headers={"Content-Type": "application/json"}, method="POST")
        status = None
        try:
            if self.opener is None:
                response = urllib.request.urlopen(request, timeout=self.timeout_seconds)
            else:
                response = self.opener(request, timeout=self.timeout_seconds)
            with response:
                status = getattr(response, "status", None)
                response_bytes = response.read()
            response_body = json.loads(response_bytes)
            transport_outcome = "RETRIEVED"
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            response_body = {"error_type": type(exc).__name__, "error": str(exc)}
            transport_outcome = "FAILED"
        received = time.time_ns()
        raw_sha = _canonical_sha(response_body)
        exchange = {
            "schema": SCHEMA, "source": SOURCE, "mint": mint, "bonding_curve": curve,
            "endpoint_scheme_host": self.url.split("/", 3)[:3],
            "modeled_target_unix_nanos": modeled_target_unix_nanos,
            "request_started_unix_nanos": started, "response_received_unix_nanos": received,
            "request_json": request_body, "http_status": status,
            "transport_outcome": transport_outcome, "response_json_or_error": response_body,
            "raw_response_sha256": raw_sha,
        }
        exchange["exchange_sha256"] = _canonical_sha(exchange)
        _append(self.exchange_path, exchange)
        if transport_outcome != "RETRIEVED" or status != 200:
            raise SnapshotUnavailable("PAC V2 snapshot transport unavailable; raw exchange preserved")
        if not isinstance(response_body, dict) or response_body.get("error") is not None:
            raise SnapshotUnavailable("PAC V2 snapshot RPC returned an error; raw exchange preserved")
        result = response_body.get("result")
        if not isinstance(result, dict) or not isinstance(result.get("context"), dict):
            raise RefusedExecution("PAC V2 snapshot lacks RPC context")
        slot = result["context"].get("slot")
        value = result.get("value")
        if type(slot) is not int or slot < 0 or not isinstance(value, dict):
            raise SnapshotUnavailable("PAC V2 snapshot account is missing")
        if value.get("owner") != PUMP_PROGRAM:
            raise RefusedExecution("PAC V2 snapshot account has the wrong owner")
        if type(value.get("lamports")) is not int or value["lamports"] <= 0:
            raise SnapshotUnavailable("PAC V2 snapshot account is closed")
        data = value.get("data")
        if not isinstance(data, list) or not data or not isinstance(data[0], str):
            raise RefusedExecution("PAC V2 snapshot account data is absent")
        try:
            raw = base64.b64decode(data[0], validate=True)
        except (ValueError, TypeError) as exc:
            raise RefusedExecution("PAC V2 snapshot account data is invalid base64") from exc
        endpoint = "/".join(self.url.split("/", 3)[:3])
        return LandingSnapshot(
            mint=mint, bonding_curve=curve, modeled_target_unix_nanos=modeled_target_unix_nanos,
            minimum_context_slot=minimum_context_slot,
            request_started_unix_nanos=started, response_received_unix_nanos=received,
            context_slot=slot, state=_decode_state(raw), endpoint_scheme_host=endpoint,
            raw_response_sha256=raw_sha)


def snapshot_to_dict(snapshot: LandingSnapshot) -> dict:
    raw = asdict(snapshot)
    raw["state"] = asdict(snapshot.state)
    return raw
