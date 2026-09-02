#!/usr/bin/env python3
"""Decode pump.fun anchor SELF-CPI events from a transaction's logs, into the SAME dict shape the
PumpPortal data websocket used to push. Pure functions, zero I/O, zero deps — so the Helius-backed tape
(helius_tape.py) can feed the existing ws_data append/hash-chain path unchanged.

Why this exists: PumpPortal IP-banned us (403 on the whole domain, 2026-09-02). PumpPortal was never a
data source of its own — it just re-serialised pump.fun's own on-chain anchor events. Those same events
ride in every pump.fun transaction's logs as `Program data: <base64>` lines (an 8-byte Anchor event
discriminator + a borsh struct). Subscribing to the pump.fun program via our FUNDED Helius `logsSubscribe`
gives us the identical firehose, decoded here.

Units match PumpPortal exactly: reserves/amounts are returned in SOL and whole tokens (lamports/1e9,
raw-token/1e6), NOT raw integers — because the arena's fill/curve code was written against PumpPortal's
SOL-denominated `vSolInBondingCurve` / `vTokensInBondingCurve`.
"""
from __future__ import annotations

import base64
import struct

PUMP_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"

# Anchor event discriminators = first 8 bytes of sha256("event:<Name>"). Verified against the live tape.
DISC_TRADE = bytes.fromhex("bddb7fd34ee661ee")   # TradeEvent  (confirmed live 2026-09-02)
DISC_CREATE = bytes.fromhex("1b72a94ddeeb6376")  # CreateEvent
DISC_COMPLETE = bytes.fromhex("95ec8eb5ddf72fd8")  # CompleteEvent (bonding curve full -> graduation/migrate)

LAMPORTS = 1_000_000_000       # SOL has 9 decimals
TOKEN_DECIMALS = 1_000_000     # pump.fun mints have 6 decimals
TOTAL_SUPPLY_TOKENS = 1_000_000_000  # every pump.fun mint is a fixed 1e9 supply

# pump.fun's global launch config is FIXED: initial_virtual_sol_reserves = 30 SOL,
# initial_virtual_token_reserves = 1.073e9 tokens. A bonding curve therefore ALWAYS has vSol >= 30 (it only
# rises as tokens are bought) and vTok <= 1.073e9 (it only falls). That gives a principled self-consistency
# gate: a `mentions:[pump]` subscription mixes in TradeEvents from PumpSwap and from third-party wrappers /
# an older program layout, which decode to reserves OUTSIDE this band. We keep only events whose decoded
# reserves obey the invariant, so a WRONG decode can never write a wrong price to the tape (it is dropped).
_VSOL_MIN_SOL = 29.5           # launch is exactly 30; a hair of tolerance
_VSOL_MAX_SOL = 500.0          # graduation is ~115 SOL; generous headroom before we distrust the decode
_VTOK_MIN_TOK = 2.0e8          # graduation floor ~2.79e8 tokens
_VTOK_MAX_TOK = 1.08e9         # launch is 1.073e9 tokens


def curve_consistent(v_sol_sol: float, v_tok_tok: float) -> bool:
    """True iff (vSol, vTok) obey pump.fun's fixed-launch bonding-curve invariant (see band constants)."""
    return (_VSOL_MIN_SOL <= v_sol_sol <= _VSOL_MAX_SOL
            and _VTOK_MIN_TOK <= v_tok_tok <= _VTOK_MAX_TOK)

_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def b58encode(raw: bytes) -> str:
    """Base58 (Bitcoin alphabet) encode a 32-byte pubkey. Small and dependency-free."""
    n = int.from_bytes(raw, "big")
    out = ""
    while n > 0:
        n, rem = divmod(n, 58)
        out = _B58[rem] + out
    pad = 0
    for b in raw:
        if b == 0:
            pad += 1
        else:
            break
    return "1" * pad + out


class _Cursor:
    __slots__ = ("buf", "i")

    def __init__(self, buf: bytes, i: int = 0):
        self.buf, self.i = buf, i

    def take(self, n: int) -> bytes:
        if self.i + n > len(self.buf):
            raise ValueError("anchor event truncated")
        chunk = self.buf[self.i:self.i + n]
        self.i += n
        return chunk

    def u64(self) -> int:
        return struct.unpack_from("<Q", self.take(8))[0]

    def i64(self) -> int:
        return struct.unpack_from("<q", self.take(8))[0]

    def u8(self) -> int:
        return self.take(1)[0]

    def pubkey(self) -> str:
        return b58encode(self.take(32))

    def string(self) -> str:
        n = struct.unpack_from("<I", self.take(4))[0]
        return self.take(n).decode("utf-8", "replace")


def _market_cap_sol(v_sol_lamports: int, v_tok_raw: int) -> float | None:
    """pump.fun marketCapSol = price_per_token_SOL * total_supply, matching PumpPortal's field."""
    if v_tok_raw <= 0:
        return None
    price_sol_per_token = (v_sol_lamports / LAMPORTS) / (v_tok_raw / TOKEN_DECIMALS)
    return price_sol_per_token * TOTAL_SUPPLY_TOKENS


def decode_trade(payload: bytes) -> dict | None:
    """TradeEvent -> PumpPortal-shaped buy/sell dict. Trailing (newer) fee fields are ignored: every field
    we read sits at a fixed offset from the front, so a longer struct is forward-compatible."""
    if payload[:8] != DISC_TRADE:
        return None
    c = _Cursor(payload, 8)
    try:
        mint = c.pubkey()
        sol_amount = c.u64()
        token_amount = c.u64()
        is_buy = c.u8() != 0
        user = c.pubkey()
        c.i64()  # timestamp (unused; we stamp local receive time)
        v_sol = c.u64()
        v_tok = c.u64()
        r_sol = c.u64()
        r_tok = c.u64()
    except (ValueError, struct.error):
        return None
    v_sol_sol = v_sol / LAMPORTS
    v_tok_tok = v_tok / TOKEN_DECIMALS
    # Reject a decode that violates pump.fun's fixed-launch invariant — it means this TradeEvent used a
    # different (PumpSwap / wrapper / legacy) layout than the classic offsets we read, so the reserves are
    # garbage. Dropping it keeps the tape honest: better a missing trade than a wrong price.
    if not curve_consistent(v_sol_sol, v_tok_tok):
        return None
    return {
        "txType": "buy" if is_buy else "sell",
        "mint": mint,
        "traderPublicKey": user,
        "tokenAmount": token_amount / TOKEN_DECIMALS,
        "solAmount": sol_amount / LAMPORTS,
        "vSolInBondingCurve": v_sol_sol,
        "vTokensInBondingCurve": v_tok_tok,
        "realSolInBondingCurve": r_sol / LAMPORTS,
        "realTokensInBondingCurve": r_tok / TOKEN_DECIMALS,
        "marketCapSol": _market_cap_sol(v_sol, v_tok),
        "pool": "pump",
    }


def decode_create(payload: bytes) -> dict | None:
    """CreateEvent -> PumpPortal-shaped create dict. Newer CreateEvents append virtual reserves after the
    three pubkeys; if present we read them, otherwise fall back to pump.fun's fixed launch reserves."""
    if payload[:8] != DISC_CREATE:
        return None
    c = _Cursor(payload, 8)
    try:
        name = c.string()
        symbol = c.string()
        c.string()  # uri (unused for the screen)
        mint = c.pubkey()
        c.pubkey()  # bonding_curve
        user = c.pubkey()
    except (ValueError, struct.error):
        return None
    v_sol_lamports, v_tok_raw = 30 * LAMPORTS, 1_073_000_000 * TOKEN_DECIMALS  # pump.fun launch defaults
    try:  # optional trailing fields on newer CreateEvent (creator, timestamp, then reserves/supply)
        c.pubkey()      # creator
        c.i64()         # timestamp
        v_tok_raw = c.u64()
        v_sol_lamports = c.u64()
    except (ValueError, struct.error):
        pass
    return {
        "txType": "create",
        "mint": mint,
        "name": name,
        "symbol": symbol,
        "traderPublicKey": user,
        "pool": "pump",
        "vSolInBondingCurve": v_sol_lamports / LAMPORTS,
        "marketCapSol": _market_cap_sol(v_sol_lamports, v_tok_raw),
        "solAmount": None,
        "initialBuy": None,
    }


def decode_complete(payload: bytes) -> dict | None:
    """CompleteEvent (bonding curve full -> graduation/migration) -> a migrate marker carrying the mint.
    Layout: user pubkey, mint pubkey, bonding_curve pubkey, timestamp."""
    if payload[:8] != DISC_COMPLETE:
        return None
    c = _Cursor(payload, 8)
    try:
        c.pubkey()          # user
        mint = c.pubkey()
    except (ValueError, struct.error):
        return None
    return {"txType": "migrate", "mint": mint, "pool": "pump"}


def decode_logs(logs: list[str], *, signature: str | None = None, slot: int | None = None) -> list[dict]:
    """Every decodable pump.fun BONDING-CURVE anchor event in a transaction's logs, as PumpPortal-shaped
    dicts, each stamped with the transaction signature + slot so downstream dedup/coverage works unchanged.

    A `mentions:[pump]` subscription also delivers txs that route through OTHER programs — most importantly
    the PumpSwap AMM, which emits a `TradeEvent` with the IDENTICAL anchor discriminator but a DIFFERENT
    struct (AMM pools, not a bonding curve). Decoding those with the bonding-curve layout yields garbage
    (vSol=0, impossible reserves). So we walk the `Program <id> invoke/success` stack and decode a
    `Program data:` line ONLY when the pump bonding-curve program is the one currently executing."""
    out: list[dict] = []
    stack: list[str] = []            # program-invocation stack; top = the program emitting log lines now
    for line in logs:
        parts = line.split()
        if len(parts) >= 3 and parts[0] == "Program":
            if parts[2] == "invoke":
                stack.append(parts[1]); continue
            if parts[2] == "success" or parts[2].startswith("failed"):
                if stack:
                    stack.pop()
                continue
        if not line.startswith("Program data:"):
            continue
        if not stack or stack[-1] != PUMP_PROGRAM:
            continue                 # emitted by another program (e.g. PumpSwap AMM) — not our tape
        try:
            payload = base64.b64decode(line.split("Program data:", 1)[1].strip())
        except Exception:  # noqa: BLE001
            continue
        if len(payload) < 8:
            continue
        disc = payload[:8]
        ev = None
        if disc == DISC_TRADE:
            ev = decode_trade(payload)
        elif disc == DISC_CREATE:
            ev = decode_create(payload)
        elif disc == DISC_COMPLETE:
            ev = decode_complete(payload)  # graduation/migration marker, carrying the mint
        if ev is None:
            continue
        if signature is not None:
            ev["signature"] = signature
        if slot is not None:
            ev["slot"] = slot
        out.append(ev)
    return out


if __name__ == "__main__":
    # Round-trip self-checks on hand-built borsh payloads (no network).
    def _mk_trade(mint32, sol, tok, is_buy, user32, ts, vs, vt, rs, rt):
        return (DISC_TRADE + mint32 + struct.pack("<QQ", sol, tok) + bytes([1 if is_buy else 0])
                + user32 + struct.pack("<q", ts) + struct.pack("<QQQQ", vs, vt, rs, rt)
                + b"\x00" * 64)  # trailing newer fields must be ignored
    m = bytes(range(32)); u = bytes(range(32, 64))
    t = decode_trade(_mk_trade(m, 5 * LAMPORTS, 1_000_000 * TOKEN_DECIMALS, True, u, 123,
                               31 * LAMPORTS, 1_050_000_000 * TOKEN_DECIMALS,
                               1 * LAMPORTS, 900_000_000 * TOKEN_DECIMALS))
    assert t["txType"] == "buy" and t["mint"] == b58encode(m), t
    assert abs(t["solAmount"] - 5.0) < 1e-9 and abs(t["vSolInBondingCurve"] - 31.0) < 1e-9, t
    assert t["marketCapSol"] and t["marketCapSol"] > 0, t
    # invariant gate: a wrong-layout decode (vSol=5 SOL < launch 30) must be DROPPED, not written
    bad = decode_trade(_mk_trade(m, LAMPORTS, TOKEN_DECIMALS, True, u, 1,
                                 5 * LAMPORTS, 1_060_000_000 * TOKEN_DECIMALS,
                                 0, 0))
    assert bad is None, f"garbage-reserve trade should be dropped, got {bad}"
    assert curve_consistent(31.0, 1.05e9) and not curve_consistent(5.0, 1.05e9)
    # base58 known vector: 32 zero bytes -> "1111...1" (32 ones)
    assert b58encode(bytes(32)) == "1" * 32
    print("helius_pump_decode.py self-check OK: trade decode + invariant gate + units + base58")
