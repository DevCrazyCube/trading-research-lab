#!/usr/bin/env python3
"""Public-RPC pump.fun ingester — a FREE, keyless, quota-independent feed for BOTH the candle cache and
the AFTERSHOCK trade tape. PAPER / READ-ONLY: subscribes and decodes only; NO orders, NO wallet, NO key.

WHY: the PumpPortal feed needs a funded key (>=0.02 SOL, currently paywalled), and the Chainstack WS is
on a monthly quota (spent). The free public Solana RPC WS supports `logsSubscribe` on the pump.fun
program — the same firehose the sniper already decodes — and the decoder carries the EXACT bonding-curve
reserves (`virtual_sol`/`virtual_tok`) the AFTERSHOCK ECR engine needs. One connection fans out to:
  (a) the candle cache  — for the memebot dashboard (only the memebot's tracked pools), and
  (b) the AFTERSHOCK trade tape — every pump.fun trade, with reserves + taker wallet.
A mint's FIRST observed trade is written as its create (AFTERSHOCK watches from first-seen).

Run detached under the memestream venv (async/sync websockets):
    setsid nohup scripts/trading_bot/memestream/.venv/bin/python \
        -m scripts.trading_bot.memestream.rpc_ingest \
        >> scripts/trading_bot/memestream/rpc_ingest.log 2>&1 < /dev/null &
(rpc_ingest_watchdog.sh + */2 cron keep it alive.)
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import sys
import time

_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from websockets.sync.client import connect  # noqa: E402

from scripts.trading_bot.sniper.data._common import (  # noqa: E402
    PUMP_PROGRAM, SOL_USD_DEFAULT, decode_pump_trades_from_logs, read_env,
)
from scripts.trading_bot.memestream.bitquery_ingest import Aggregator  # noqa: E402
from scripts.trading_bot.memestream.chainstack_ingest import (  # noqa: E402
    build_mint_pool_map, drain_completed, register_all,
)
from scripts.trading_bot.aftershock import tape as _tape  # noqa: E402

LOG = _ROOT / "scripts" / "trading_bot" / "memestream" / "rpc_ingest.log"
PUBLIC_WS_URL = "wss://api.mainnet-beta.solana.com"
LAMPORTS_PER_SOL = 1_000_000_000
TOKEN_ATOMS = 10 ** 6

MAP_REFRESH_S = 60.0
FLUSH_EVERY_S = 4.0
REAP_EVERY_S = 300.0
_MAX_SEEN = 200_000    # bound the first-seen set


def _log(msg: str) -> None:
    line = f"{dt.datetime.now(dt.timezone.utc).isoformat()} {msg}"
    try:
        with open(LOG, "a") as fh:
            fh.write(line + "\n")
    except OSError:
        pass
    print(line, flush=True)


def _ws_url() -> str:
    """Prefer an explicit SOLANA_WS_URL only if it is NOT the (quota-dead) Chainstack node; else public."""
    env = (read_env("SOLANA_WS_URL") or "").strip()
    # The Chainstack node is quota-capped; the public endpoint is the free firehose. Default to public.
    return PUBLIC_WS_URL


def _ev_to_tape(ev: dict, recv_ts: float) -> dict:
    """Decoded pump.fun TradeEvent -> a tape line in WHOLE-SOL / WHOLE-token units (matches ecr)."""
    return {
        "ts": recv_ts,
        "mint": ev["mint"],
        "trader": ev.get("user"),
        "side": ev["side"],
        "sol_amount": ev.get("sol_amount", 0) / LAMPORTS_PER_SOL,
        "token_amount": ev.get("token_amount", 0) / TOKEN_ATOMS,
        "v_sol": ev.get("virtual_sol", 0) / LAMPORTS_PER_SOL,
        "v_tokens": ev.get("virtual_tok", 0) / TOKEN_ATOMS,
        "pool": "pump",
        "sig": None,
    }


def _ev_to_tick(ev: dict, recv_ts: float) -> dict:
    """Decoded event -> the bitquery-shaped tick the candle Aggregator consumes."""
    return {"mint": ev["mint"],
            "t": dt.datetime.fromtimestamp(recv_ts, dt.timezone.utc).isoformat(),
            "price_usd": ev["price_usd"], "usd": ev["usd"], "side": ev["side"], "family": "pumpfun"}


def _run_once() -> None:
    agg = Aggregator()
    mint_pool = build_mint_pool_map()
    register_all(mint_pool)
    seen: set[str] = set()

    sub = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "logsSubscribe",
                      "params": [{"mentions": [PUMP_PROGRAM]}, {"commitment": "processed"}]})
    with connect(_ws_url(), open_timeout=20, max_size=None) as ws:
        ws.send(sub)
        ws.recv(timeout=20)   # subscription id ack
        _log(f"rpc_ingest connected (public WS logsSubscribe pump.fun); {len(mint_pool)} tracked pools")
        last_flush = last_map = last_reap = time.monotonic()
        trades = creates = wrote = 0

        while True:
            try:
                raw = ws.recv(timeout=30)
            except TimeoutError:
                raw = None
            if raw is not None:
                try:
                    msg = json.loads(raw)
                except (ValueError, TypeError):
                    msg = None
                if isinstance(msg, dict) and msg.get("method") == "logsNotification":
                    value = (((msg.get("params") or {}).get("result") or {}).get("value")) or {}
                    if value.get("err") is None:
                        recv_ts = time.time()
                        for ev in decode_pump_trades_from_logs(value.get("logs") or [], SOL_USD_DEFAULT):
                            mint = ev["mint"]
                            if mint not in seen:
                                seen.add(mint)
                                _tape.append_create({"ts": recv_ts, "mint": mint, "symbol": None, "pool": "pump"})
                                creates += 1
                                if len(seen) > _MAX_SEEN:
                                    seen.clear()   # cheap bound; a re-seen mint just re-emits a create
                            _tape.append_trade(_ev_to_tape(ev, recv_ts))
                            trades += 1
                            if mint in mint_pool:
                                agg.add(_ev_to_tick(ev, recv_ts))

            now = time.monotonic()
            if now - last_flush >= FLUSH_EVERY_S:
                agg.prune(time.time())
                wrote += drain_completed(agg, mint_pool)
                last_flush = now
            if now - last_map >= MAP_REFRESH_S:
                new_map = build_mint_pool_map()
                register_all({m: new_map[m] for m in set(new_map) - set(mint_pool)})
                mint_pool = new_map
                _log(f"heartbeat: {creates} creates, {trades} trades, {wrote} candles, {len(mint_pool)} pools")
                last_map = now
            if now - last_reap >= REAP_EVERY_S:
                _tape.reap(3600.0)
                _tape.trim_creates()
                last_reap = now


def run() -> None:
    _log("rpc_ingest start (FREE public-RPC pump.fun firehose; PAPER / READ-ONLY; candles+tape; no key)")
    backoff = 2.0
    while True:
        try:
            _run_once()
        except Exception as e:  # noqa: BLE001
            _log(f"stream dropped: {type(e).__name__}: {str(e)[:160]} -- reconnect in {backoff:.0f}s")
            time.sleep(backoff)
            backoff = min(backoff * 2, 60.0)
        else:
            backoff = 2.0


if __name__ == "__main__":
    run()
