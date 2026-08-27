#!/usr/bin/env python3
"""Trade SOURCES -- normalise real, free, read-only trades into one shape the aggregator consumes.

Two sources, one normalised trade dict::

    {"pool": str, "mint": str, "ts": int_epoch, "price": float_usd,
     "vol": float_usd, "side": "buy"|"sell", "tx_hash": str}

1. geckoterminal_trades(pool, mint)   -- WORKING, FREE, KEYLESS (the default today).
   GET api.geckoterminal.com/.../pools/{pool}/trades through ``memebot.net.http_get_json`` so it
   inherits the exact same polite 2.1s throttle + 429 backoff + host allowlist the bot already uses.
   Each trade carries a second-resolution ``block_timestamp``, a ``kind`` (buy/sell), USD volume and
   per-side USD prices -- everything the 1s aggregator needs.

2. pumpportal_stream(...)             -- the realtime PUSH path, IMPLEMENTED but currently DORMANT.
   Opens ONLY wss://pumpportal.fun/api/data behind ``memebot.net.assert_data_ws`` and subscribes
   ``subscribeTokenTrade``. As of 2026-08-25 PumpPortal gates this behind an API key funded with
   >=0.02 SOL (real money + wallet), which this paper layer must never do -- so the connector detects
   that gating message, logs it honestly, and returns without funding anything. If PumpPortal restores
   the free tier (or an OWNER provides a funded key, which is a separate gated decision made elsewhere),
   the SAME normalizer feeds the SAME aggregator with no other change.

Holdings discovery (which pools to watch) reads the paper bot's OPEN positions straight from its
append-only ledgers -- no hash verification, so a long-running ingester never dies because an unrelated
frozen document moved.
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib

from . import Refused

ROOT = pathlib.Path(__file__).resolve().parents[3]
MEMEBOT_LEDGER_DIR = ROOT / "research" / "trading_bot" / "memebot"
GT_BASE = "https://api.geckoterminal.com/api/v2"
DATA_WS_URL = "wss://pumpportal.fun/api/data"

# The paper bot runs two parallel frozen instruments on the same coins; watch the union of both.
_LEDGER_PREFIXES = ("MEMEBOT", "MEMEBOT_FAST")

# Quote tokens that are NOT the memecoin base (used only as a price-side fallback).
_QUOTE_MINTS = frozenset({
    "So11111111111111111111111111111111111111112",   # wrapped SOL
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",   # USDC
    "Es9vMFrzaCERmJfrF4H2FYD4KConky11Mc6PWD2wZg",     # USDT
})


# --------------------------------------------------------------------------------------------------
# holdings
# --------------------------------------------------------------------------------------------------
def _read_jsonl(path: pathlib.Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def read_holdings() -> list[dict]:
    """Currently-HELD coins = frozen paper entries with no RESOLVED resolution yet, union of both
    instruments, de-duplicated by pool. Returns [{pool, mint, name}]. Read-only, no hash verify.
    """
    held: dict[str, dict] = {}
    for prefix in _LEDGER_PREFIXES:
        entries = [r for r in _read_jsonl(MEMEBOT_LEDGER_DIR / f"{prefix}_PREREGISTRATION_LOG.jsonl")
                   if r.get("kind") == "entry"]
        resolved = {r["setup_sha256"] for r in
                    _read_jsonl(MEMEBOT_LEDGER_DIR / f"{prefix}_RESOLUTION_LOG.jsonl")
                    if r.get("status") == "RESOLVED"}
        for e in entries:
            if e.get("setup_sha256") in resolved:
                continue
            pool = e.get("pool_address")
            if not pool:
                continue
            held.setdefault(pool, {"pool": pool, "mint": e.get("base_token"), "name": e.get("name")})
    return sorted(held.values(), key=lambda h: h["pool"])


# --------------------------------------------------------------------------------------------------
# source 1: GeckoTerminal per-pool trades (FREE, KEYLESS, the working default)
# --------------------------------------------------------------------------------------------------
def _to_epoch(ts_iso: str) -> int | None:
    if not ts_iso:
        return None
    try:
        return int(dt.datetime.fromisoformat(ts_iso.replace("Z", "+00:00")).timestamp())
    except ValueError:
        return None


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _base_price_usd(a: dict, mint: str | None) -> float | None:
    """USD price of the memecoin (base) token for this trade. Deterministic when the mint is known;
    otherwise falls back to the non-quote side implied by the trade direction."""
    frm, to = a.get("from_token_address"), a.get("to_token_address")
    if mint and frm == mint:
        return _f(a.get("price_from_in_usd"))
    if mint and to == mint:
        return _f(a.get("price_to_in_usd"))
    # Fallback: on a 'buy' the trader RECEIVES the base (to side); on a 'sell' they GIVE it (from side).
    if a.get("kind") == "buy":
        p = _f(a.get("price_to_in_usd"))
        if p is None and to in _QUOTE_MINTS:
            p = _f(a.get("price_from_in_usd"))
        return p
    p = _f(a.get("price_from_in_usd"))
    if p is None and frm in _QUOTE_MINTS:
        p = _f(a.get("price_to_in_usd"))
    return p


def geckoterminal_trades(pool: str, mint: str | None = None) -> list[dict]:
    """Fetch the most recent trades for one pool and normalise them. Free, keyless, throttled.

    Raises Refused (from memebot.net) on a hard host/allowlist violation; a transient miss returns [].
    """
    from scripts.trading_bot.memebot import net  # reuse the bot's throttle + allowlist + 429 backoff
    url = f"{GT_BASE}/networks/solana/pools/{pool}/trades"
    net.assert_free_host(url)  # explicit: api.geckoterminal.com only, no trade/RPC/wallet host
    try:
        payload = net.http_get_json(url)
    except Refused:
        raise
    except Exception:  # noqa: BLE001 -- transient network; treat as an empty poll, don't die
        return []
    out = []
    for row in payload.get("data") or []:
        a = row.get("attributes") or {}
        ts = _to_epoch(a.get("block_timestamp"))
        price = _base_price_usd(a, mint)
        side = "buy" if a.get("kind") == "buy" else "sell"
        tx = a.get("tx_hash") or f"{ts}:{a.get('block_number')}:{a.get('volume_in_usd')}"
        if ts is None or price is None:
            continue
        out.append({"pool": pool, "mint": mint, "ts": ts, "price": price,
                    "vol": _f(a.get("volume_in_usd")) or 0.0, "side": side, "tx_hash": tx})
    return out


# --------------------------------------------------------------------------------------------------
# source 2: PumpPortal per-token trade PUSH (implemented, gated/dormant behind assert_data_ws)
# --------------------------------------------------------------------------------------------------
def normalize_pumpportal_trade(ev: dict, pool_by_mint: dict[str, str]) -> dict | None:
    """Normalise a PumpPortal ``subscribeTokenTrade`` event into the common trade shape.

    Kept live so that IF the free push is restored (or an owner-gated funded key is supplied elsewhere)
    the same aggregator consumes it unchanged. Price is derived from the bonding-curve reserves the
    event carries; volume is the trade's SOL amount (documented as SOL, not USD, for this source).
    """
    mint = ev.get("mint")
    tx = ev.get("txType")
    if not mint or tx not in ("buy", "sell"):
        return None
    v_sol = _f(ev.get("vSolInBondingCurve"))
    v_tok = _f(ev.get("vTokensInBondingCurve"))
    price = (v_sol / v_tok) if (v_sol and v_tok) else None
    if price is None:
        sol_amt, tok_amt = _f(ev.get("solAmount")), _f(ev.get("tokenAmount"))
        price = (sol_amt / tok_amt) if (sol_amt and tok_amt) else None
    ts = int(dt.datetime.now(dt.timezone.utc).timestamp())  # push events carry no ts; stamp on receive
    return {
        "pool": pool_by_mint.get(mint, ev.get("pool") or mint),
        "mint": mint, "ts": ts, "price": price,
        "vol": _f(ev.get("solAmount")) or 0.0, "side": tx,
        "tx_hash": ev.get("signature") or f"{mint}:{ts}",
    }


def pumpportal_probe(mints: list[str], *, seconds: float = 8.0) -> dict:
    """Open the read-only data ws, attempt subscribeTokenTrade, and report whether it is free.

    Never funds a key, never sends an order. Detects the "funded API key" gating message and reports
    it honestly so the ingester logs the reason it is falling back to the free GeckoTerminal source.
    """
    try:
        import websocket  # websocket-client
    except ImportError:
        return {"available": False, "reason": "websocket-client not installed"}
    from scripts.trading_bot.memebot import net
    net.assert_data_ws(DATA_WS_URL)  # wss + exact /api/data path only; every trade REST path forbidden
    import time as _time
    try:
        ws = websocket.create_connection(DATA_WS_URL, timeout=20)
        ws.send(json.dumps({"method": "subscribeTokenTrade", "keys": list(mints)[:20]}))
        ws.settimeout(3)
        t0, trades = _time.time(), 0
        while _time.time() - t0 < seconds:
            try:
                ev = json.loads(ws.recv())
            except websocket.WebSocketTimeoutException:
                continue
            except Exception:  # noqa: BLE001
                break
            msg = ev.get("message")
            if msg and "API key" in msg:
                ws.close()
                return {"available": False, "reason": msg.strip()}
            if ev.get("txType") in ("buy", "sell"):
                trades += 1
        ws.close()
        return {"available": trades > 0, "reason": None if trades else "no trades and no gating msg",
                "trades_seen": trades}
    except Refused:
        raise
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "reason": f"connect error: {exc!r}"}
