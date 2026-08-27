#!/usr/bin/env python3
"""PumpPortal-fed real-time 1s candle ingester — a FREE, quota-independent fallback for the dashboard.

WHY THIS EXISTS
---------------
The Chainstack Solana WS (the sniper's live pump.fun feed and the primary candle source) hit its
MONTHLY Request-Unit quota on 2026-08-26 and now returns HTTP 403 (-32005) on every connect — so
`chainstack_ingest` reconnects forever and writes no candles, and the dashboard shows no live coins.
PumpPortal's data websocket (`wss://pumpportal.fun/api/data`), by contrast, is FREE, keyless, and
UNMETERED: it already powers new-token discovery here, and it can ALSO push per-token trades via
`subscribeTokenTrade`. This ingester rebuilds the SAME pool-keyed 1s candle cache from those free
trades, with ZERO dashboard/server changes — so live charts survive a Chainstack outage.

It writes the identical schema `candles.py` reads and REUSES chainstack_ingest's map/aggregate/write
helpers verbatim, so on-disk candles are byte-identical to the Chainstack ones and the two ingesters
can run side by side (candles.py was built anticipating two writers; O_APPEND lines are atomic and a
re-flushed second collapses to the most complete candle on read). Price is derived on the SAME
reserve-ratio basis and the SAME SOL_USD_DEFAULT as the Chainstack path, so the price scale is
continuous when Chainstack comes back.

DATA PATH
---------
    PumpPortal subscribeTokenTrade(keys=tracked mints)     # free, keyless pump.fun trade push
      -> tick {mint, t, price_usd, usd, side, family}
      -> bitquery_ingest.Aggregator                        # reused per-mint 1s OHLCV+flow aggregation
      -> candles._append_candles(pool, bars)               # reused writer (chainstack_ingest.drain_completed)
      -> dashboard get_candles(pool, '1s'|'1m')

The tracked mint set is the memebot's OPEN positions (chainstack_ingest.build_mint_pool_map), refreshed
every ~60s; new mints are subscribed as positions open. READ-ONLY: subscribes and decodes only. NO
orders, NO wallet, NO key, NO on-chain writes. PumpPortal is keyless; nothing secret is read or logged.

Run detached under the memestream venv (it has async ``websockets``; the system Python does not):
    setsid nohup scripts/trading_bot/memestream/.venv/bin/python \
        -m scripts.trading_bot.memestream.pumpportal_ingest \
        >> scripts/trading_bot/memestream/pumpportal_ingest.log 2>&1 < /dev/null &
(a watchdog + cron */2 keep it alive, mirroring chainstack_ingest).
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import pathlib
import sys
import time

# Ensure the repo root is importable whether launched as a module or a script.
ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import websockets  # noqa: E402  (async client; memestream venv only)

from scripts.trading_bot.memestream.bitquery_ingest import Aggregator  # noqa: E402
# Reuse the Chainstack ingester's env-agnostic helpers verbatim so both feeds write identically.
from scripts.trading_bot.memestream.chainstack_ingest import (  # noqa: E402
    build_mint_pool_map, drain_completed, register_all,
)
from scripts.trading_bot.sniper.data._common import SOL_USD_DEFAULT, read_env  # noqa: E402

LOG = ROOT / "scripts" / "trading_bot" / "memestream" / "pumpportal_ingest.log"
DATA_WS_URL = "wss://pumpportal.fun/api/data"

# The per-token trade stream (`subscribeTokenTrade`) requires a funded PumpPortal api-key. It is read
# from .env at connect time and appended to the WS URL query string. It is USED ONLY to subscribe to
# READ-ONLY data (subscribeNewToken / subscribeTokenTrade) -- this ingester NEVER sends a trade method,
# so the key's trading capability is never exercised here. It is NEVER logged: _scrub() strips it from
# every log line (a websockets connect error can otherwise echo the full URI, key and all).
_API_KEY = (read_env("LIGHTNING_API") or "").strip()


def _scrub(msg: str) -> str:
    """Remove the api-key from any string before it is logged. Belt-and-braces against URI echoes."""
    if _API_KEY and _API_KEY in msg:
        msg = msg.replace(_API_KEY, "***")
    return msg


def _ws_url() -> str:
    """The data WS URL with the funded api-key appended when present (never logged)."""
    return DATA_WS_URL + ("?api-key=" + _API_KEY if _API_KEY else "")

MAP_REFRESH_S = 60.0   # re-read the open-positions map this often (follows the bot's positions)
FLUSH_EVERY_S = 4.0    # append completed 1s candles to disk this often
RECV_TIMEOUT_S = 30.0  # recv timeout; a quiet stretch is normal, keep the socket open


def _log(msg: str) -> None:
    """Timestamped log line. Never receives or emits a secret (PumpPortal is keyless)."""
    line = f"{dt.datetime.now(dt.timezone.utc).isoformat()} {msg}"
    try:
        with open(LOG, "a") as fh:
            fh.write(line + "\n")
    except OSError:
        pass
    print(line, flush=True)


def _f(v) -> float:
    """Parse a PumpPortal numeric field that may be a float, a string, or missing."""
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def trade_to_tick(ev: dict) -> dict | None:
    """Turn a PumpPortal trade event into the Aggregator's tick shape, or None if unusable.

    Price basis mirrors the Chainstack path: the marginal bonding-curve price
    ``vSolInBondingCurve / vTokensInBondingCurve`` (in SOL), times SOL_USD_DEFAULT. For a migrated /
    AMM trade where the virtual reserves are absent, fall back to this trade's EXECUTED price
    ``solAmount / tokenAmount`` so post-migration coins still price. Trade USD size is ``solAmount`` in
    USD. Side is the PumpPortal ``txType`` (buy/sell).
    """
    mint = ev.get("mint")
    side = ev.get("txType")
    if not mint or side not in ("buy", "sell"):
        return None

    v_sol = _f(ev.get("vSolInBondingCurve"))
    v_tok = _f(ev.get("vTokensInBondingCurve"))
    sol_amount = _f(ev.get("solAmount"))
    tok_amount = _f(ev.get("tokenAmount"))

    if v_sol > 0 and v_tok > 0:
        price_sol = v_sol / v_tok
    elif sol_amount > 0 and tok_amount > 0:
        price_sol = sol_amount / tok_amount        # executed price (venue-agnostic fallback)
    else:
        return None                                 # no way to price this trade

    price_usd = price_sol * SOL_USD_DEFAULT
    usd = sol_amount * SOL_USD_DEFAULT
    if price_usd <= 0:
        return None
    return {
        "mint": mint,
        "t": dt.datetime.now(dt.timezone.utc).isoformat(),  # PumpPortal pushes live; receive time = trade time
        "price_usd": price_usd,
        "usd": usd,
        "side": side,
        "family": ev.get("pool") or "pumpfun",
    }


async def _run_once() -> None:
    """One WS session: subscribe to tracked mints, aggregate live trades, flush candles, follow the map."""
    agg = Aggregator()
    mint_pool = build_mint_pool_map()
    register_all(mint_pool)
    subscribed: set[str] = set()

    async with websockets.connect(_ws_url(), open_timeout=20, max_size=None, ping_interval=20) as ws:
        if mint_pool:
            await ws.send(json.dumps({"method": "subscribeTokenTrade", "keys": list(mint_pool)}))
            subscribed |= set(mint_pool)
        _log(f"connected ({'keyed' if _API_KEY else 'KEYLESS-no-trades'}); "
             f"subscribed {len(subscribed)} tracked mints")

        last_flush = time.monotonic()
        last_map = last_flush
        ticks = kept = wrote_total = 0

        while True:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=RECV_TIMEOUT_S)
                msg = json.loads(raw)
                if isinstance(msg, dict) and msg.get("txType") in ("buy", "sell"):
                    ticks += 1
                    if msg.get("mint") in mint_pool:
                        tick = trade_to_tick(msg)
                        if tick is not None:
                            agg.add(tick)
                            kept += 1
            except asyncio.TimeoutError:
                pass  # quiet stretch; fall through to the periodic flush/map refresh below
            except json.JSONDecodeError:
                continue

            now = time.monotonic()

            if now - last_flush >= FLUSH_EVERY_S:
                agg.prune(time.time())
                w = drain_completed(agg, mint_pool)
                wrote_total += w
                last_flush = now
                if w:
                    _log(f"flush +{w} candles ({wrote_total} total; {kept}/{ticks} trades tracked; "
                         f"{len(subscribed)} subs; {len(agg.open)} live mints)")

            if now - last_map >= MAP_REFRESH_S:
                mint_pool = build_mint_pool_map()
                new = set(mint_pool) - subscribed
                if new:
                    await ws.send(json.dumps({"method": "subscribeTokenTrade", "keys": list(new)}))
                    register_all({m: mint_pool[m] for m in new})
                    subscribed |= new
                    _log(f"map refresh: +{len(new)} new mints subscribed ({len(subscribed)} total)")
                last_map = now


def run() -> None:
    _log("pumpportal candle ingester start (FREE fallback; PAPER / READ-ONLY; no orders/wallet/key)")
    backoff = 2.0
    while True:
        try:
            asyncio.run(_run_once())
        except Exception as e:  # noqa: BLE001 -- any WS/parse fault: log, back off, reconnect
            _log(_scrub(f"stream dropped: {type(e).__name__}: {str(e)[:160]}")
                 + f" -- reconnect in {backoff:.0f}s")
            time.sleep(backoff)
            backoff = min(backoff * 2, 60.0)
        else:
            backoff = 2.0


if __name__ == "__main__":
    run()
