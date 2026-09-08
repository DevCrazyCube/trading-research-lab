#!/usr/bin/env python3
"""Central PumpPortal feed BROKER — the SOLE reader of the funded key, fanning one connection out to two
sinks. PAPER / READ-ONLY: subscribes and decodes only; NO orders, NO wallet spend, key NEVER logged.

WHY: PumpPortal limits connections per api-key. The dashboard candle ingester and the AFTERSHOCK engine
both need the key. Running two connections starves one. So ONE broker holds the key, subscribes to
subscribeNewToken (all creates) + subscribeTokenTrade for (fresh-launch mints ∪ the memebot's open
positions), and fans every trade out to:
  (a) the existing candle cache  — unchanged schema, so the dashboard chart stays continuous;
  (b) the raw per-mint TRADE TAPE — research/data/memebot_cache/tape/{mint}.jsonl, what AFTERSHOCK reads.

This SUPERSEDES memestream.pumpportal_ingest (retire its cron; keep the file for reference). Its candle
path is reused verbatim (Aggregator + drain_completed), so candles are byte-identical.

Run detached under the memestream venv (async websockets):
    setsid nohup scripts/trading_bot/memestream/.venv/bin/python \
        -m scripts.trading_bot.memestream.pumpportal_broker \
        >> scripts/trading_bot/memestream/pumpportal_broker.log 2>&1 < /dev/null &
(pumpportal_broker_watchdog.sh + */2 cron keep it alive.)
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import pathlib
import sys
import time
from collections import OrderedDict

_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import websockets  # noqa: E402  (async client; memestream venv only)

from scripts.trading_bot.memestream.bitquery_ingest import Aggregator  # noqa: E402
from scripts.trading_bot.memestream.chainstack_ingest import (  # noqa: E402
    build_mint_pool_map, drain_completed, register_all,
)
# Reuse the key handling / scrub / url / candle-tick decode from the ingester (single source of truth).
from scripts.trading_bot.memestream.pumpportal_ingest import (  # noqa: E402
    _API_KEY, _scrub, _ws_url, _f, trade_to_tick, DATA_WS_URL,  # noqa: F401
)
from scripts.trading_bot.aftershock import tape as _tape  # noqa: E402

LOG = _ROOT / "scripts" / "trading_bot" / "memestream" / "pumpportal_broker.log"

MAP_REFRESH_S = 60.0
FLUSH_EVERY_S = 4.0
REAP_EVERY_S = 300.0
RECV_TIMEOUT_S = 30.0
MAX_FRESH_TRACKED = 600          # rolling cap on fresh-launch mints subscribed for the tape


def _log(msg: str) -> None:
    line = f"{dt.datetime.now(dt.timezone.utc).isoformat()} {msg}"
    try:
        with open(LOG, "a") as fh:
            fh.write(line + "\n")
    except OSError:
        pass
    print(line, flush=True)


def trade_to_tape_line(ev: dict) -> dict | None:
    """PumpPortal trade event -> a raw tape line (reserves + taker wallet). None if not a trade."""
    mint = ev.get("mint")
    side = ev.get("txType")
    if not mint or side not in ("buy", "sell"):
        return None
    recv_ns = time.time_ns()
    return {
        "ts": recv_ns / 1_000_000_000,
        "received_unix_nanos": recv_ns,
        "observation_source": "pumpportal",
        "mint": mint,
        "trader": ev.get("traderPublicKey"),
        "side": side,
        "sol_amount": _f(ev.get("solAmount")),
        "token_amount": _f(ev.get("tokenAmount")),
        "v_sol": _f(ev.get("vSolInBondingCurve")),
        "v_tokens": _f(ev.get("vTokensInBondingCurve")),
        "pool": ev.get("pool") or "pump",
        "sig": ev.get("signature"),
    }


async def _run_once() -> None:
    agg = Aggregator()
    mint_pool = build_mint_pool_map()          # memebot open positions -> candle sink targets
    register_all(mint_pool)
    fresh: "OrderedDict[str, float]" = OrderedDict()   # fresh-launch mints -> first_seen (tape sink)
    subscribed: set[str] = set()

    async with websockets.connect(_ws_url(), open_timeout=20, max_size=None, ping_interval=20) as ws:
        await ws.send(json.dumps({"method": "subscribeNewToken"}))
        if mint_pool:
            await ws.send(json.dumps({"method": "subscribeTokenTrade", "keys": list(mint_pool)}))
            subscribed |= set(mint_pool)
        _log(f"broker connected ({'keyed' if _API_KEY else 'KEYLESS'}); newTokens + "
             f"{len(subscribed)} tracked mints")

        last_flush = last_map = last_reap = time.monotonic()
        creates = trades = wrote = evicted = 0

        while True:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=RECV_TIMEOUT_S)
                ev = json.loads(raw)
            except asyncio.TimeoutError:
                ev = None
            except (json.JSONDecodeError, TypeError):
                continue

            if isinstance(ev, dict):
                tx = ev.get("txType")
                if tx == "create" and ev.get("mint"):
                    mint = ev["mint"]
                    if mint not in fresh:
                        fresh[mint] = time.time()
                        _tape.append_create({"ts": time.time(), "mint": mint,
                                             "symbol": ev.get("symbol"), "pool": ev.get("pool") or "pump"})
                        await ws.send(json.dumps({"method": "subscribeTokenTrade", "keys": [mint]}))
                        subscribed.add(mint)
                        creates += 1
                        # Evict oldest fresh mints past the cap to bound subscriptions. NEVER unsubscribe
                        # a memebot tracked position (would cut its candle feed, review #17). PumpPortal
                        # caps subscriptions, so at high create rates we can only SAMPLE fresh mints up to
                        # MAX_FRESH_TRACKED (the newest) -- a coverage limit we log rather than hide.
                        while len(fresh) > MAX_FRESH_TRACKED:
                            old = next((m for m in fresh if m not in mint_pool), None)
                            if old is None:
                                break                       # everything left is a protected candle pool
                            fresh.pop(old, None)
                            subscribed.discard(old)
                            evicted += 1
                            try:
                                await ws.send(json.dumps({"method": "unsubscribeTokenTrade", "keys": [old]}))
                            except Exception:  # noqa: BLE001
                                pass
                elif tx in ("buy", "sell"):
                    trades += 1
                    # (b) TAPE sink: every tracked pump.fun trade, with reserves + wallet.
                    tl = trade_to_tape_line(ev)
                    if tl is not None:
                        _tape.append_trade(tl)
                    # (a) CANDLE sink: only the memebot's tracked pools (reuse the ingester path).
                    if ev.get("mint") in mint_pool:
                        tick = trade_to_tick(ev)
                        if tick is not None:
                            agg.add(tick)

            now = time.monotonic()
            if now - last_flush >= FLUSH_EVERY_S:
                agg.prune(time.time())
                wrote += drain_completed(agg, mint_pool)
                last_flush = now
            if now - last_map >= MAP_REFRESH_S:
                new_map = build_mint_pool_map()
                add = set(new_map) - subscribed
                if add:
                    await ws.send(json.dumps({"method": "subscribeTokenTrade", "keys": list(add)}))
                    register_all({m: new_map[m] for m in add})
                    subscribed |= add
                mint_pool = new_map
                _log(f"heartbeat: {creates} creates, {trades} trades, {wrote} candles, "
                     f"{len(fresh)} fresh, {len(subscribed)} subs, {evicted} evicted (sampling cap)")
                last_map = now
            if now - last_reap >= REAP_EVERY_S:
                _tape.reap(3600.0)
                _tape.trim_creates()          # review #10: bound the creates log
                last_reap = now


def run() -> None:
    _log("pumpportal BROKER start (FREE key; PAPER / READ-ONLY; candle+tape fan-out; no orders/wallet)")
    backoff = 2.0
    while True:
        try:
            asyncio.run(_run_once())
        except Exception as e:  # noqa: BLE001
            _log(_scrub(f"stream dropped: {type(e).__name__}: {str(e)[:160]}")
                 + f" -- reconnect in {backoff:.0f}s")
            time.sleep(backoff)
            backoff = min(backoff * 2, 60.0)
        else:
            backoff = 2.0


if __name__ == "__main__":
    run()
