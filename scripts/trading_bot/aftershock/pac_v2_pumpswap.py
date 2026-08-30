#!/usr/bin/env python3
"""Causal PAC V2 PumpSwap-AMM sell quotes for PAPER-SCENARIO exit pricing.

A pump.fun mint that graduates migrates its liquidity to the PumpSwap constant-product AMM
(``pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA``).  The bonding-curve feed goes permanently
silent at that moment, so a held position must be re-observed on the *new* venue or it can
never be exited honestly.  This module observes the live PumpSwap pool for a mint and prices
an exact-token sell from the pool's real vault reserves and its live GlobalConfig fees.

Like ``pac_v2_snapshot`` this is read-only: no signer, transaction builder, or sender.  Every
raw RPC exchange is durably appended before any economic interpretation is returned, and the
quote is a *modeled* constant-product price (documented, not a simulated on-chain swap).
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import json
import os
import pathlib
import struct
import time
import urllib.error
import urllib.request

from scripts.trading_bot.aftershock.execution import PriceUnavailable, RefusedExecution


ROOT = pathlib.Path(__file__).resolve().parents[3]
EXCHANGES = ROOT / "research" / "data" / "aftershock" / "pac_v2" / "pumpswap_exchanges.jsonl"
PUBLIC_RPC_URL = "https://api.mainnet-beta.solana.com"
SCHEMA = 1
SOURCE = "public_rpc_pumpswap_pool_snapshot"

# Chain-verified layout (research/pump_amm_idl_9c82f61.json + live mainnet decode 2026-08-30).
PUMPSWAP_PROGRAM = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
WSOL_MINT = "So11111111111111111111111111111111111111112"
GLOBAL_CONFIG = "ADyA8hdefvWN2dbGGWFotbzWxrAvLW83WG6QCVXvJKqw"
_POOL_DISCRIMINATOR = bytes.fromhex("f19a6d0411b16dbc")
_POOL_BASE_MINT_OFF = 43
_POOL_QUOTE_MINT_OFF = 75
_POOL_BASE_VAULT_OFF = 139
_POOL_QUOTE_VAULT_OFF = 171
_POOL_MIN_LEN = 211
_GLOBAL_LP_FEE_OFF = 40
_GLOBAL_PROTOCOL_FEE_OFF = 48
_GLOBAL_CREATOR_FEE_OFF = 313
_GLOBAL_MIN_LEN = _GLOBAL_CREATOR_FEE_OFF + 8
# SPL token account: mint[0:32], owner[32:64], amount u64 LE [64:72].
_TOKEN_MINT_OFF = 0
_TOKEN_AMOUNT_OFF = 64
_TOKEN_MIN_LEN = 72
_TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
_TOKEN_2022_PROGRAM = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
# Refuse a fee regime we were not designed for rather than silently misprice.
_MAX_TOTAL_FEE_BPS = 500
_FEE_DEN = 10_000

_B58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


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
    # The leading-zero prefix already supplies one '1' per zero byte, so an all-zero input encodes
    # to exactly len(raw) ones; an `or "1"` fallback would over-produce a 33rd character.
    return "1" * (len(raw) - len(raw.lstrip(b"\x00"))) + out


class PumpSwapUnavailable(RefusedExecution):
    """A named pool/transport observation failure; a bounded reason to keep holding, not a fill."""


@dataclass(frozen=True)
class PumpSwapReserves:
    base_reserve: int
    quote_reserve: int
    lp_fee_bps: int
    protocol_fee_bps: int
    creator_fee_bps: int

    def __post_init__(self) -> None:
        for name in ("base_reserve", "quote_reserve"):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise RefusedExecution(f"PumpSwap {name} is not a positive exact integer")
        for name in ("lp_fee_bps", "protocol_fee_bps", "creator_fee_bps"):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise RefusedExecution(f"PumpSwap {name} is not a non-negative exact integer")
        if self.total_fee_bps > _MAX_TOTAL_FEE_BPS:
            raise RefusedExecution(
                f"PumpSwap total fee {self.total_fee_bps}bps exceeds supported {_MAX_TOTAL_FEE_BPS}bps")

    @property
    def total_fee_bps(self) -> int:
        return self.lp_fee_bps + self.protocol_fee_bps + self.creator_fee_bps


def _ceil_div(numerator: int, denominator: int) -> int:
    return -(-numerator // denominator)


def sell_quote(base_in_atoms: int, reserves: PumpSwapReserves) -> dict:
    """Modeled constant-product exact-token sell: base atoms in -> net WSOL lamports out.

    gross = floor(quote_reserve * base_in / (base_reserve + base_in)); each fee is charged on
    the gross output and rounded UP (matches the pump-swap SDK); net = gross - all fees.
    """
    if not isinstance(reserves, PumpSwapReserves):
        raise RefusedExecution("PumpSwap sell_quote requires typed reserves")
    if type(base_in_atoms) is not int or base_in_atoms <= 0:
        raise PriceUnavailable("PumpSwap sell requires a positive token amount")
    gross = (reserves.quote_reserve * base_in_atoms) // (reserves.base_reserve + base_in_atoms)
    if gross <= 0:
        raise PriceUnavailable("PumpSwap sell prices zero lamports out")
    lp_fee = _ceil_div(gross * reserves.lp_fee_bps, _FEE_DEN)
    protocol_fee = _ceil_div(gross * reserves.protocol_fee_bps, _FEE_DEN)
    creator_fee = _ceil_div(gross * reserves.creator_fee_bps, _FEE_DEN)
    net = gross - lp_fee - protocol_fee - creator_fee
    if net <= 0:
        raise PriceUnavailable("PumpSwap sell net is non-positive after fees")
    return {
        "venue": "PUMPSWAP", "side": "EXIT", "gross_quote_lamports": gross,
        "lp_fee_lamports": lp_fee, "protocol_fee_lamports": protocol_fee,
        "creator_fee_lamports": creator_fee, "net_quote_lamports": net,
        "quote_reserve_lamports": reserves.quote_reserve,
    }


@dataclass(frozen=True)
class PumpSwapObservation:
    mint: str
    pool: str
    base_vault: str
    quote_vault: str
    reserves: PumpSwapReserves
    context_slot: int
    request_started_unix_nanos: int
    response_received_unix_nanos: int
    endpoint_scheme_host: str
    raw_response_sha256: str
    source: str = SOURCE

    def __post_init__(self) -> None:
        for value in (self.mint, self.pool, self.base_vault, self.quote_vault,
                      self.endpoint_scheme_host):
            if not isinstance(value, str) or not value:
                raise RefusedExecution("PumpSwap observation identity is incomplete")
        for label, value in (("context slot", self.context_slot),
                             ("request start", self.request_started_unix_nanos),
                             ("response receive", self.response_received_unix_nanos)):
            if type(value) is not int or value < 0:
                raise RefusedExecution(f"PumpSwap observation {label} is not an exact coordinate")
        if self.request_started_unix_nanos > self.response_received_unix_nanos:
            raise RefusedExecution("PumpSwap observation response precedes its request")
        if not isinstance(self.reserves, PumpSwapReserves):
            raise RefusedExecution("PumpSwap observation reserves are untyped")
        if (not isinstance(self.raw_response_sha256, str) or len(self.raw_response_sha256) != 64
                or any(c not in "0123456789abcdef" for c in self.raw_response_sha256)):
            raise RefusedExecution("PumpSwap observation response hash is invalid")
        if self.source != SOURCE:
            raise RefusedExecution("PumpSwap observation source cannot be relabelled")


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
            raise OSError(f"short pumpswap exchange append {written}/{len(payload)}")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    if not existed:
        directory = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)


def _pubkey_at(raw: bytes, offset: int) -> str:
    return _b58encode(raw[offset:offset + 32])


def _decode_pool(raw: bytes, *, mint: str) -> tuple[str, str]:
    if not isinstance(raw, bytes) or len(raw) < _POOL_MIN_LEN or raw[:8] != _POOL_DISCRIMINATOR:
        raise RefusedExecution("PumpSwap pool bytes differ from the pinned Pool layout")
    if _pubkey_at(raw, _POOL_BASE_MINT_OFF) != mint:
        raise RefusedExecution("PumpSwap pool base mint does not match the requested mint")
    if _pubkey_at(raw, _POOL_QUOTE_MINT_OFF) != WSOL_MINT:
        raise RefusedExecution("PumpSwap pool is not WSOL-quoted")
    return (_pubkey_at(raw, _POOL_BASE_VAULT_OFF), _pubkey_at(raw, _POOL_QUOTE_VAULT_OFF))


def _decode_token_amount(value: dict, *, expected_mint: str, label: str) -> int:
    if not isinstance(value, dict):
        raise PumpSwapUnavailable(f"PumpSwap {label} vault account is missing")
    owner = value.get("owner")
    if owner not in {_TOKEN_PROGRAM, _TOKEN_2022_PROGRAM}:
        raise RefusedExecution(f"PumpSwap {label} vault is not an SPL token account")
    raw = _decode_account_data(value)
    if len(raw) < _TOKEN_MIN_LEN:
        raise RefusedExecution(f"PumpSwap {label} vault data is too short")
    if _pubkey_at(raw, _TOKEN_MINT_OFF) != expected_mint:
        raise RefusedExecution(f"PumpSwap {label} vault holds the wrong mint")
    (amount,) = struct.unpack_from("<Q", raw, _TOKEN_AMOUNT_OFF)
    return amount


def _decode_fees(value: dict) -> tuple[int, int, int]:
    if not isinstance(value, dict):
        raise PumpSwapUnavailable("PumpSwap GlobalConfig account is missing")
    raw = _decode_account_data(value)
    if len(raw) < _GLOBAL_MIN_LEN:
        raise RefusedExecution("PumpSwap GlobalConfig data is too short")
    (lp,) = struct.unpack_from("<Q", raw, _GLOBAL_LP_FEE_OFF)
    (protocol,) = struct.unpack_from("<Q", raw, _GLOBAL_PROTOCOL_FEE_OFF)
    (creator,) = struct.unpack_from("<Q", raw, _GLOBAL_CREATOR_FEE_OFF)
    return (lp, protocol, creator)


def _decode_account_data(value: dict) -> bytes:
    data = value.get("data")
    if not isinstance(data, list) or not data or not isinstance(data[0], str):
        raise RefusedExecution("PumpSwap account data is absent")
    try:
        return base64.b64decode(data[0], validate=True)
    except (ValueError, TypeError) as exc:
        raise RefusedExecution("PumpSwap account data is invalid base64") from exc


class PumpSwapProvider:
    """Observe one live PumpSwap pool and its reserves.  No signing or transaction method."""

    def __init__(self, *, url: str = PUBLIC_RPC_URL, exchange_path: pathlib.Path = EXCHANGES,
                 timeout_seconds: float = 8.0, opener=None):
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            raise RefusedExecution("PumpSwap URL is invalid")
        if type(timeout_seconds) not in {int, float} or timeout_seconds <= 0:
            raise RefusedExecution("PumpSwap timeout is invalid")
        self.url = url
        self.exchange_path = pathlib.Path(exchange_path)
        self.timeout_seconds = float(timeout_seconds)
        self.opener = opener

    def _rpc(self, body: dict) -> tuple[object, int | None, str]:
        encoded = json.dumps(body, separators=(",", ":")).encode()
        request = urllib.request.Request(
            self.url, data=encoded, headers={"Content-Type": "application/json"}, method="POST")
        try:
            if self.opener is None:
                response = urllib.request.urlopen(request, timeout=self.timeout_seconds)
            else:
                response = self.opener(request, timeout=self.timeout_seconds)
            with response:
                status = getattr(response, "status", None)
                response_bytes = response.read()
            return (json.loads(response_bytes), status, "RETRIEVED")
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            return ({"error_type": type(exc).__name__, "error": str(exc)}, None, "FAILED")

    def capture(self, mint: str, minimum_context_slot: int) -> PumpSwapObservation:
        if (not isinstance(mint, str) or not mint or type(minimum_context_slot) is not int
                or minimum_context_slot < 0):
            raise RefusedExecution("PumpSwap capture request is malformed")
        started = time.time_ns()
        discover_body = {
            "jsonrpc": "2.0", "id": 1, "method": "getProgramAccounts",
            "params": [PUMPSWAP_PROGRAM, {
                "encoding": "base64", "commitment": "processed",
                "filters": [{"memcmp": {"offset": _POOL_BASE_MINT_OFF, "bytes": mint}}]}]}
        discover_body_error = None
        try:
            _b58decode(mint)
        except ValueError as exc:
            discover_body_error = str(exc)
        pool = base_vault = quote_vault = None
        reserves = None
        context_slot = None
        second_body = None
        second_response = None
        if discover_body_error is None:
            discover_response, discover_status, discover_outcome = self._rpc(discover_body)
        else:
            discover_response = {"error": f"invalid mint: {discover_body_error}"}
            discover_status, discover_outcome = None, "FAILED"
        received = time.time_ns()
        raw_sha = _canonical_sha(discover_response)

        def _log(extra_ok: bool) -> None:
            exchange = {
                "schema": SCHEMA, "source": SOURCE, "mint": mint,
                "endpoint_scheme_host": self.url.split("/", 3)[:3],
                "minimum_context_slot": minimum_context_slot,
                "request_started_unix_nanos": started, "response_received_unix_nanos": received,
                "discover_request": discover_body, "discover_http_status": discover_status,
                "discover_outcome": discover_outcome, "discover_response": discover_response,
                "reserve_request": second_body, "reserve_response": second_response,
                "pool": pool, "base_vault": base_vault, "quote_vault": quote_vault,
                "resolved": extra_ok,
            }
            exchange["exchange_sha256"] = _canonical_sha(exchange)
            _append(self.exchange_path, exchange)

        if discover_outcome != "RETRIEVED" or discover_status != 200:
            _log(False)
            raise PumpSwapUnavailable("PumpSwap discovery transport unavailable; raw exchange preserved")
        if not isinstance(discover_response, dict) or discover_response.get("error") is not None:
            _log(False)
            raise PumpSwapUnavailable("PumpSwap discovery RPC returned an error; raw exchange preserved")
        result = discover_response.get("result")
        if not isinstance(result, list) or not result:
            _log(False)
            raise PumpSwapUnavailable("PumpSwap pool not found for mint; raw exchange preserved")
        if len(result) != 1:
            _log(False)
            raise RefusedExecution("PumpSwap discovery returned multiple pools; refusing ambiguous venue")
        account = result[0]
        if not isinstance(account, dict) or not isinstance(account.get("account"), dict):
            _log(False)
            raise RefusedExecution("PumpSwap discovery account envelope is malformed")
        pool = account.get("pubkey")
        pool_value = account["account"]
        if not isinstance(pool, str) or not pool:
            _log(False)
            raise RefusedExecution("PumpSwap discovery pubkey is absent")
        if pool_value.get("owner") != PUMPSWAP_PROGRAM:
            _log(False)
            raise RefusedExecution("PumpSwap pool account has the wrong owner")
        base_vault, quote_vault = _decode_pool(_decode_account_data(pool_value), mint=mint)

        second_body = {
            "jsonrpc": "2.0", "id": 2, "method": "getMultipleAccounts",
            "params": [[base_vault, quote_vault, GLOBAL_CONFIG],
                       {"encoding": "base64", "commitment": "processed",
                        "minContextSlot": minimum_context_slot}]}
        second_response, second_status, second_outcome = self._rpc(second_body)
        received = time.time_ns()
        raw_sha = _canonical_sha({"discover": discover_response, "reserve": second_response})
        if second_outcome != "RETRIEVED" or second_status != 200:
            _log(False)
            raise PumpSwapUnavailable("PumpSwap reserve transport unavailable; raw exchange preserved")
        if not isinstance(second_response, dict) or second_response.get("error") is not None:
            _log(False)
            raise PumpSwapUnavailable("PumpSwap reserve RPC returned an error; raw exchange preserved")
        rvalue = second_response.get("result")
        if not isinstance(rvalue, dict) or not isinstance(rvalue.get("context"), dict):
            _log(False)
            raise RefusedExecution("PumpSwap reserve read lacks RPC context")
        context_slot = rvalue["context"].get("slot")
        accounts = rvalue.get("value")
        if type(context_slot) is not int or context_slot < 0 or not isinstance(accounts, list) \
                or len(accounts) != 3:
            _log(False)
            raise PumpSwapUnavailable("PumpSwap reserve read is incomplete")
        base_reserve = _decode_token_amount(accounts[0], expected_mint=mint, label="base")
        quote_reserve = _decode_token_amount(accounts[1], expected_mint=WSOL_MINT, label="quote")
        lp, protocol, creator = _decode_fees(accounts[2])
        reserves = PumpSwapReserves(
            base_reserve=base_reserve, quote_reserve=quote_reserve,
            lp_fee_bps=lp, protocol_fee_bps=protocol, creator_fee_bps=creator)
        _log(True)
        return PumpSwapObservation(
            mint=mint, pool=pool, base_vault=base_vault, quote_vault=quote_vault,
            reserves=reserves, context_slot=context_slot,
            request_started_unix_nanos=started, response_received_unix_nanos=received,
            endpoint_scheme_host="/".join(self.url.split("/", 3)[:3]), raw_response_sha256=raw_sha)


def observation_to_dict(observation: PumpSwapObservation) -> dict:
    return {
        "venue": "PUMPSWAP", "mint": observation.mint, "pool": observation.pool,
        "base_vault": observation.base_vault, "quote_vault": observation.quote_vault,
        "context_slot": observation.context_slot,
        "request_started_unix_nanos": observation.request_started_unix_nanos,
        "response_received_unix_nanos": observation.response_received_unix_nanos,
        "endpoint_scheme_host": observation.endpoint_scheme_host,
        "raw_response_sha256": observation.raw_response_sha256, "source": observation.source,
        "reserves": {
            "base_reserve": observation.reserves.base_reserve,
            "quote_reserve": observation.reserves.quote_reserve,
            "lp_fee_bps": observation.reserves.lp_fee_bps,
            "protocol_fee_bps": observation.reserves.protocol_fee_bps,
            "creator_fee_bps": observation.reserves.creator_fee_bps,
        },
    }
