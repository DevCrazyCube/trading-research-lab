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
import hashlib
import json
import pathlib
import struct

PUMP_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"

# Anchor event discriminators = first 8 bytes of sha256("event:<Name>"). Verified against the live tape.
DISC_TRADE = bytes.fromhex("bddb7fd34ee661ee")   # TradeEvent  (confirmed live 2026-09-02)
DISC_CREATE = bytes.fromhex("1b72a94ddeeb6376")  # CreateEvent
DISC_COMPLETE = bytes.fromhex("5f72619cd42e9808")  # CompleteEvent (bonding curve full -> graduation/migrate)

LAMPORTS = 1_000_000_000       # SOL has 9 decimals
TOKEN_DECIMALS = 1_000_000     # pump.fun mints have 6 decimals
TOTAL_SUPPLY_TOKENS = 1_000_000_000  # every pump.fun mint is a fixed 1e9 supply
NATIVE_DEFAULT = "1" * 32
WRAPPED_SOL = "So11111111111111111111111111111111111111112"
PINNED_IDL = pathlib.Path(__file__).resolve().parents[3] / "research" / "pump_idl_9c82f61.json"
PINNED_IDL_SHA256 = "b90bc471327f671449271d5d1d42354d1fae6f5a06502f5834459a3108138e49"

# SEEN-vs-DECODED observability. A silent CompleteEvent drop (a stale/wrong discriminator) starved the
# MIGRATION_ACCEPTANCE_V1 arm with zero visible error — this makes it observable at the decode site.
# complete_seen counts raw CompleteEvent discriminators encountered; complete_decoded counts those that
# decoded to a mint; unknown_disc maps any UNrecognised pump-program discriminator -> count, so a future
# layout/discriminator drift shows up as a recurring unknown rather than a silent gap. Process-local.
EVENT_STATS = {"complete_seen": 0, "complete_decoded": 0, "unknown_disc": {}}

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

    def u16(self) -> int:
        return struct.unpack_from("<H", self.take(2))[0]

    def u32(self) -> int:
        return struct.unpack_from("<I", self.take(4))[0]

    def pubkey(self) -> str:
        return b58encode(self.take(32))

    def string(self) -> str:
        n = self.u32()
        return self.take(n).decode("utf-8", "replace")


def verify_pinned_idl(path: pathlib.Path = PINNED_IDL) -> str:
    """Bind the live decoder to Pump's pinned official IDL and the exact layouts used below."""
    raw = path.read_bytes()
    observed = hashlib.sha256(raw).hexdigest()
    if observed != PINNED_IDL_SHA256:
        raise ValueError("pinned Pump IDL hash drifted")
    value = json.loads(raw)
    events = {e["name"]: bytes(e["discriminator"]) for e in value["events"]}
    if events.get("TradeEvent") != DISC_TRADE or events.get("CreateEvent") != DISC_CREATE \
            or events.get("CompleteEvent") != DISC_COMPLETE:
        raise ValueError("pinned Pump event discriminators drifted")
    types = {t["name"]: t["type"]["fields"] for t in value["types"] if t.get("type", {}).get("kind") == "struct"}
    expected_trade = ["mint", "sol_amount", "token_amount", "is_buy", "user", "timestamp",
                      "virtual_sol_reserves", "virtual_token_reserves", "real_sol_reserves",
                      "real_token_reserves", "fee_recipient", "fee_basis_points", "fee", "creator",
                      "creator_fee_basis_points", "creator_fee", "track_volume", "total_unclaimed_tokens",
                      "total_claimed_tokens", "current_sol_volume", "last_update_timestamp", "ix_name",
                      "mayhem_mode", "cashback_fee_basis_points", "cashback", "buyback_fee_basis_points",
                      "buyback_fee", "shareholders", "quote_mint", "quote_amount",
                      "virtual_quote_reserves", "real_quote_reserves"]
    if [f["name"] for f in types.get("TradeEvent", [])] != expected_trade:
        raise ValueError("pinned Pump TradeEvent layout drifted")
    return observed


def _market_cap_sol(v_sol_lamports: int, v_tok_raw: int) -> float | None:
    """pump.fun marketCapSol = price_per_token_SOL * total_supply, matching PumpPortal's field."""
    if v_tok_raw <= 0:
        return None
    price_sol_per_token = (v_sol_lamports / LAMPORTS) / (v_tok_raw / TOKEN_DECIMALS)
    return price_sol_per_token * TOTAL_SUPPLY_TOKENS


def decode_trade(payload: bytes) -> dict | None:
    """Exact current-IDL TradeEvent -> legacy tape shape; non-SOL/Mayhem fail closed."""
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
        c.pubkey()          # fee_recipient
        c.u64(); c.u64()   # fee bps, fee
        c.pubkey()          # creator
        c.u64(); c.u64()   # creator fee bps, creator fee
        c.u8()              # track_volume
        c.u64(); c.u64(); c.u64(); c.i64()
        ix_name = c.string()
        mayhem_mode = c.u8() != 0
        c.u64(); c.u64(); c.u64(); c.u64()
        for _ in range(c.u32()):
            c.pubkey(); c.u16()
        quote_mint = c.pubkey()
        quote_amount = c.u64()
        virtual_quote = c.u64()
        real_quote = c.u64()
    except (ValueError, struct.error):
        return None
    if c.i != len(payload) or mayhem_mode or quote_mint not in {NATIVE_DEFAULT, WRAPPED_SOL}:
        return None
    # The unified v2 event publishes quote-generic reserves at the tail. For native SOL these are the
    # authoritative lamport fields; the legacy `virtual_sol_*` prefix can carry compatibility values.
    v_sol_sol = virtual_quote / LAMPORTS
    r_sol_sol = real_quote / LAMPORTS
    v_tok_tok = v_tok / TOKEN_DECIMALS
    # Reject a decode that violates pump.fun's fixed-launch invariant — it means this TradeEvent used a
    # different (PumpSwap / wrapper / legacy) layout than the classic offsets we read, so the reserves are
    # garbage. Dropping it keeps the tape honest: better a missing trade than a wrong price.
    if (not curve_consistent(v_sol_sol, v_tok_tok) or r_sol_sol < 0 or r_sol_sol > v_sol_sol
            or abs((v_sol_sol - r_sol_sol) - 30.0) > 0.05
            or abs((v_tok_tok - r_tok / TOKEN_DECIMALS) - 279_900_000.0) > 1.0):
        return None
    return {
        "txType": "buy" if is_buy else "sell",
        "mint": mint,
        "traderPublicKey": user,
        "tokenAmount": token_amount / TOKEN_DECIMALS,
        "solAmount": quote_amount / LAMPORTS,
        "vSolInBondingCurve": v_sol_sol,
        "vTokensInBondingCurve": v_tok_tok,
        "realSolInBondingCurve": r_sol_sol,
        "realTokensInBondingCurve": r_tok / TOKEN_DECIMALS,
        "marketCapSol": _market_cap_sol(v_sol, v_tok),
        "pool": "pump",
    }


def decode_create(payload: bytes) -> dict | None:
    """Exact current-IDL CreateEvent -> legacy tape shape; non-SOL/Mayhem fail closed."""
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
        c.pubkey()      # creator
        c.i64()         # timestamp
        v_tok_raw = c.u64()
        v_sol_lamports = c.u64()
        c.u64(); c.u64()  # real token, total supply
        c.pubkey()         # token program
        mayhem_mode = c.u8() != 0
        c.u8()             # cashback
        quote_mint = c.pubkey()
        virtual_quote = c.u64()
    except (ValueError, struct.error):
        return None
    if c.i != len(payload) or mayhem_mode or quote_mint not in {NATIVE_DEFAULT, WRAPPED_SOL}:
        return None
    v_sol_lamports = virtual_quote
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
        c.pubkey()          # bonding curve
        c.i64()
        quote_mint = c.pubkey()
    except (ValueError, struct.error):
        return None
    if c.i != len(payload) or quote_mint not in {NATIVE_DEFAULT, WRAPPED_SOL}:
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
            EVENT_STATS["complete_seen"] += 1              # observe graduations at the decode site
            ev = decode_complete(payload)                  # graduation/migration marker, carrying the mint
            if ev is not None:
                EVENT_STATS["complete_decoded"] += 1
        else:
            hx = disc.hex()                                # an unrecognised pump-program event discriminator
            EVENT_STATS["unknown_disc"][hx] = EVENT_STATS["unknown_disc"].get(hx, 0) + 1
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
    verify_pinned_idl()
    def _mk_trade(mint32, sol, tok, is_buy, user32, ts, vs, vt, rs, rt,
                  mayhem=False, quote_mint=bytes(32)):
        return (DISC_TRADE + mint32 + struct.pack("<QQ", sol, tok) + bytes([1 if is_buy else 0])
                + user32 + struct.pack("<q", ts) + struct.pack("<QQQQ", vs, vt, rs, rt)
                + bytes(32) + struct.pack("<QQ", 100, 1) + bytes(32) + struct.pack("<QQ", 100, 1)
                + b"\x00" + struct.pack("<QQQq", 0, 0, 0, ts) + struct.pack("<I", 3) + b"buy"
                + bytes([1 if mayhem else 0]) + struct.pack("<QQQQ", 0, 0, 0, 0)
                + struct.pack("<I", 0) + quote_mint + struct.pack("<QQQ", sol, vs, rs))
    m = bytes(range(32)); u = bytes(range(32, 64))
    t = decode_trade(_mk_trade(m, 5 * LAMPORTS, 1_000_000 * TOKEN_DECIMALS, True, u, 123,
                               31 * LAMPORTS, 1_050_000_000 * TOKEN_DECIMALS,
                               1 * LAMPORTS, 770_100_000 * TOKEN_DECIMALS))
    assert t["txType"] == "buy" and t["mint"] == b58encode(m), t
    assert abs(t["solAmount"] - 5.0) < 1e-9 and abs(t["vSolInBondingCurve"] - 31.0) < 1e-9, t
    assert t["marketCapSol"] and t["marketCapSol"] > 0, t
    # invariant gate: a wrong-layout decode (vSol=5 SOL < launch 30) must be DROPPED, not written
    bad = decode_trade(_mk_trade(m, LAMPORTS, TOKEN_DECIMALS, True, u, 1,
                                 5 * LAMPORTS, 1_060_000_000 * TOKEN_DECIMALS,
                                 0, 0))
    assert bad is None, f"garbage-reserve trade should be dropped, got {bad}"
    assert curve_consistent(31.0, 1.05e9) and not curve_consistent(5.0, 1.05e9)
    assert decode_trade(_mk_trade(m, 271 * LAMPORTS, TOKEN_DECIMALS, True, u, 1,
                                  271 * LAMPORTS, 1_050_000_000 * TOKEN_DECIMALS,
                                  LAMPORTS, 770_100_000 * TOKEN_DECIMALS, mayhem=True)) is None
    # CompleteEvent (graduation) round-trip — the untested link that let a wrong DISC_COMPLETE silently
    # drop every migration and starve MIGRATION_ACCEPTANCE_V1. Layout: user, mint, bonding_curve, i64 ts,
    # quote_mint; exact 144 bytes; quote must be native/wrapped SOL.
    bc = bytes(range(64, 96))
    comp = DISC_COMPLETE + u + m + bc + struct.pack("<q", 999) + bytes(32)   # quote_mint bytes(32)=native SOL
    ce = decode_complete(comp)
    assert ce and ce["txType"] == "migrate" and ce["mint"] == b58encode(m), ce
    assert decode_complete(DISC_TRADE + comp[8:]) is None                    # wrong discriminator -> drop
    assert decode_complete(comp[:-4]) is None                                # truncated -> drop
    assert decode_complete(DISC_COMPLETE + u + m + bc + struct.pack("<q", 1) + bytes(range(96, 128))) is None  # non-SOL quote -> drop
    # round-trips through the decode_logs program-stack walk as exactly one migrate row
    _logs = [f"Program {PUMP_PROGRAM} invoke [1]",
             "Program data: " + base64.b64encode(comp).decode(),
             f"Program {PUMP_PROGRAM} success"]
    _pre = EVENT_STATS["complete_decoded"]
    _outs = decode_logs(_logs)
    assert len(_outs) == 1 and _outs[0]["txType"] == "migrate" and _outs[0]["mint"] == b58encode(m), _outs
    assert EVENT_STATS["complete_seen"] >= 1 and EVENT_STATS["complete_decoded"] == _pre + 1, EVENT_STATS
    # base58 known vector: 32 zero bytes -> "1111...1" (32 ones)
    assert b58encode(bytes(32)) == "1" * 32
    print("helius_pump_decode.py self-check OK: trade + CompleteEvent round-trip + invariant gate + base58")
