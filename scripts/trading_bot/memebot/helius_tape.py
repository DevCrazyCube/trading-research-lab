#!/usr/bin/env python3
"""Helius-backed pump.fun tape — the drop-in replacement for the (now IP-banned) PumpPortal listener.

Background: on 2026-09-02 PumpPortal began returning 403 Forbidden on the WHOLE domain (WS, API, root) from
our IP — an nginx/IP-level block, not a key or header problem (both keyless and keyed 403; our egress is
fine: Helius + Binance both 200). PumpPortal was never a data source of its own; it re-serialised pump.fun's
own on-chain anchor events. Those same events ride in every pump.fun transaction's logs as
`Program data: <base64>` (an 8-byte Anchor discriminator + a borsh struct). We subscribe to the pump.fun
bonding-curve program via our FUNDED Helius `logsSubscribe`, decode CreateEvent / TradeEvent / CompleteEvent
(helius_pump_decode), and feed each — shaped exactly like a PumpPortal event — through ws_data's EXISTING
append + hash-chain path. The tape files stay byte-compatible, so every arena consumer works unchanged.

READ-ONLY: opens only the Helius read JSON-RPC websocket; no wallet, no orders, nothing written on-chain.
Runs as a detached background subprocess (`python -m scripts.trading_bot.memebot listen`), never in an agent
turn (the project's standing rule for long-lived streams). `--seconds N` gives a bounded connectivity test.
"""
from __future__ import annotations

import json
import os
import pathlib
import time

from . import Refused
from . import helius_pump_decode as DEC
from . import ws_data

_ROOT = pathlib.Path(__file__).resolve().parents[3]   # scripts/trading_bot/memebot/ -> repo root
_ENV_PATH = _ROOT / ".env"


def _env(key: str) -> str | None:
    """Resolve a config value from the process env first, then the repo .env (the dashboard/arbiter do the
    same). Long-lived background subprocesses aren't guaranteed the interactive shell's exported vars."""
    val = os.environ.get(key, "").strip()
    if val:
        return val
    try:
        for line in _ENV_PATH.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k.strip() == key:
                return v.strip().strip('"').strip("'") or None
    except OSError:
        return None
    return None

try:
    import websocket  # websocket-client
except ImportError:  # pragma: no cover
    websocket = None

SUBSCRIBE_WINDOW_MIN = 30.0   # tape trades only for mints created within this window (fresh coins we watch)
SOURCE = "HELIUS_LOGS_READ_ONLY"   # honest provenance stamped into every taped record
HEALTH_FLUSH_S = 2.0          # persist stream health at most this often (runners gate on its freshness)


def _ws_url() -> str:
    rpc = _env("HELIUS_RPC_URL")
    if not rpc:
        key = _env("HELIUS_API_KEY")
        if key:
            rpc = f"https://mainnet.helius-rpc.com/?api-key={key}"
    if not rpc:
        raise Refused("HELIUS_RPC_URL / HELIUS_API_KEY absent; cannot open the Helius pump tape")
    if rpc.startswith("https://"):
        return "wss://" + rpc[len("https://"):]
    if rpc.startswith("http://"):
        return "ws://" + rpc[len("http://"):]
    return rpc


def run_listener(seconds: float | None = None, *, verbose: bool = True) -> dict:
    """Connect to Helius, subscribe to the pump program's logs, decode + buffer every create/trade.

    `seconds=None` runs until interrupted (detached-subprocess mode). A finite `seconds` is a bounded
    connectivity test returning a small summary.
    """
    if websocket is None:
        raise Refused("websocket-client is not installed; cannot open the Helius pump tape")
    url = _ws_url()

    t0 = time.time()
    received = creates = trades = migrations = reconnects = 0
    samples: list[str] = []
    trade_head = ws_data._trade_head()
    subscribed = {r.get("mint") for r in ws_data.read_buffer(max_age_minutes=SUBSCRIBE_WINDOW_MIN)
                  if isinstance(r.get("mint"), str)}
    # Runners/arms call ws_data.require_trade_stream_fresh() and REFUSE to trade if this health record is
    # missing, not CONNECTED, or older than max_stale_s — so the tape owns it exactly like run_listener does.
    health = {"status": "CONNECTING", "reason": "helius tape starting", "reconnects": 0,
              "last_message_unix_nanos": None, "last_trade_unix_nanos": None,
              "last_create_unix_nanos": None, "http_status": None, "next_retry_unix_nanos": None}
    ws_data._write_stream_health(health)
    last_health_flush = 0.0

    def _summary(connected: bool) -> dict:
        return {"connected": connected, "seconds": round(time.time() - t0, 1),
                "messages_received": received, "create_events": creates, "trade_events": trades,
                "migration_events": migrations, "reconnects": reconnects,
                "buffer_path": str(ws_data.BUFFER_PATH), "trade_buffer_path": str(ws_data.TRADE_BUFFER_PATH),
                "sample_mints": samples[:5]}

    while True:
        try:
            ws = websocket.create_connection(url, timeout=30)
            ws.send(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "logsSubscribe",
                                "params": [{"mentions": [DEC.PUMP_PROGRAM]},
                                           {"commitment": "processed"}]}))
            ack = ws.recv()  # subscription id ack
            health.update(status="CONNECTED", reason="helius logsSubscribe connected",
                          http_status=None, next_retry_unix_nanos=None, reconnects=reconnects)
            ws_data._write_stream_health(health)
            if verbose:
                print(f"[{ws_data._now_iso()}] subscribed to Helius pump tape ({str(ack)[:70]})", flush=True)
            while True:
                if seconds is not None and time.time() - t0 >= seconds:
                    ws.close()
                    return _summary(True)
                ws.settimeout(30)
                try:
                    msg = ws.recv()
                except websocket.WebSocketTimeoutException:
                    # genuinely quiet: do NOT bump last_message_unix_nanos — let a real stall age to STALE.
                    continue
                received += 1
                recv_ns = time.time_ns()
                health["last_message_unix_nanos"] = recv_ns
                try:
                    d = json.loads(msg)
                except json.JSONDecodeError:
                    continue
                if d.get("method") != "logsNotification":
                    continue
                val = d.get("params", {}).get("result", {}).get("value", {})
                if val.get("err") is not None:
                    continue  # a failed transaction never moved the curve; ignore
                sig = val.get("signature")
                slot = d.get("params", {}).get("result", {}).get("context", {}).get("slot")
                for ev in DEC.decode_logs(val.get("logs", []), signature=sig, slot=slot):
                    rec = ws_data._normalize_event(ev, received_unix_nanos=recv_ns, source=SOURCE)
                    if rec is not None:                       # a CREATE
                        creates += 1
                        health["last_create_unix_nanos"] = recv_ns
                        ws_data._append(rec)
                        subscribed.add(rec["mint"])
                        if len(samples) < 5:
                            samples.append(rec["mint"])
                        if creates % 200 == 0:
                            ws_data._trim_buffer()
                        continue
                    trade = ws_data._trade_body(ev, msg, recv_ns, source=SOURCE)  # BUY/SELL/MIGRATE
                    # migration is mint-global (reaches the migration arm even without a fresh create);
                    # buy/sell only for mints we discovered (fresh coins the arms actually watch)
                    if trade is not None and (trade["tx_type"] in ("migrate", "migration")
                                              or trade["mint"] in subscribed):
                        trade_head = ws_data._append_trade(trade, trade_head)
                        health["last_trade_unix_nanos"] = recv_ns
                        if trade["tx_type"] in ("migrate", "migration"):
                            migrations += 1
                        else:
                            trades += 1
                now = time.monotonic()
                if now - last_health_flush >= HEALTH_FLUSH_S:
                    ws_data._write_stream_health(health)
                    last_health_flush = now
        except Refused:
            raise
        except Exception as exc:  # noqa: BLE001 — transient socket drop; reconnect politely
            reconnects += 1
            backoff = min(5.0, 1.0 + reconnects)
            health.update(status="DISCONNECTED", reason=f"stream dropped: {exc!r}"[:200],
                          reconnects=reconnects,
                          next_retry_unix_nanos=time.time_ns() + int(backoff * 1e9))
            ws_data._write_stream_health(health)
            last_health_flush = 0.0
            if verbose:
                print(f"[{ws_data._now_iso()}] helius tape dropped ({exc!r}); reconnecting", flush=True)
            if seconds is not None and time.time() - t0 >= seconds:
                return _summary(received > 0)
            time.sleep(backoff)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Helius-backed pump.fun read-only tape")
    ap.add_argument("--seconds", type=float, default=None, help="bounded connectivity test")
    args = ap.parse_args()
    print(json.dumps(run_listener(seconds=args.seconds), indent=2))
