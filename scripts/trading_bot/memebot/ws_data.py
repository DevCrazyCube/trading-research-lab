#!/usr/bin/env python3
"""PumpPortal realtime new-token listener -- a FASTER, PUSHED discovery source (read-only).

PumpPortal (`wss://pumpportal.fun/api/data`) is a FREE, keyless, read-only websocket that PUSHES a
`create` event the instant a new pump.fun token is minted -- seconds, versus the ~90s cadence of the
GeckoTerminal `new_pools` poll. This module opens ONLY that data websocket (gated by
`net.assert_data_ws`; every trade/Lightning REST path stays FORBIDDEN) and appends each new-token event
to a local buffer JSONL. It sends NO order, holds NO wallet, touches NO SOL, writes NOTHING on-chain.

The event itself (mint, name, symbol, marketCapSol, vSolInBondingCurve, ...) does NOT carry the
unique-buyer / buys / sells counts the frozen screen needs -- those only exist once the token has
traded. So the listener's job is DISCOVERY only: it records that a mint exists. `feed.py` later enriches
a buffered mint through the already-allowlisted GeckoTerminal token->pools endpoint to get the real
screen fields, then the identical deterministic screen decides PASS/REJECT. GeckoTerminal `new_pools`
remains the fallback/price-refresh source; PumpPortal just makes discovery earlier and broader.

Per the project's standing rule, a long-lived stream runs as a DETACHED background subprocess
(`python -m scripts.trading_bot.memebot listen`), never inside an agent turn. `--seconds N` gives a
bounded connectivity test.
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import time

from . import Refused
from . import net
from .frozen import CACHE

try:
    import websocket  # websocket-client
except ImportError:  # pragma: no cover
    websocket = None

DATA_WS_URL = "wss://pumpportal.fun/api/data"
BUFFER_PATH = CACHE / "pumpportal_newtokens.jsonl"
_MAX_BUFFER_LINES = 6000  # bound the on-disk buffer so a long run never grows without limit


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _normalize_event(ev: dict) -> dict | None:
    """Keep only new-token CREATE events, stamped with a local receive time for the age filter."""
    if ev.get("txType") != "create" or not ev.get("mint"):
        return None
    return {
        "source": "pumpportal",
        "mint": ev.get("mint"),
        "name": ev.get("name"),
        "symbol": ev.get("symbol"),
        "pool": ev.get("pool"),
        "signature": ev.get("signature"),
        "market_cap_sol": ev.get("marketCapSol"),
        "v_sol_in_curve": ev.get("vSolInBondingCurve"),
        "initial_buy": ev.get("initialBuy"),
        "sol_amount": ev.get("solAmount"),
        "received_utc": _now_iso(),
    }


def _trim_buffer() -> None:
    if not BUFFER_PATH.exists():
        return
    lines = BUFFER_PATH.read_text().splitlines()
    if len(lines) > _MAX_BUFFER_LINES:
        BUFFER_PATH.write_text("\n".join(lines[-_MAX_BUFFER_LINES:]) + "\n")


def _append(rec: dict) -> None:
    BUFFER_PATH.parent.mkdir(parents=True, exist_ok=True)
    with BUFFER_PATH.open("a") as fh:
        fh.write(json.dumps(rec, sort_keys=True) + "\n")


def read_buffer(max_age_minutes: float | None = None) -> list:
    """Read buffered new-token events, optionally only those received within max_age_minutes."""
    if not BUFFER_PATH.exists():
        return []
    now = dt.datetime.now(dt.timezone.utc)
    out = []
    for line in BUFFER_PATH.read_text().splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if max_age_minutes is not None:
            try:
                recv = dt.datetime.fromisoformat(rec["received_utc"])
            except (KeyError, ValueError):
                continue
            if (now - recv).total_seconds() / 60.0 > max_age_minutes:
                continue
        out.append(rec)
    return out


def run_listener(seconds: float | None = None, *, verbose: bool = True) -> dict:
    """Connect to the PumpPortal data websocket, subscribe to new tokens, buffer every create event.

    `seconds=None` runs until interrupted (the detached-subprocess mode). A finite `seconds` gives a
    bounded connectivity test that returns a small summary.
    """
    if websocket is None:
        raise Refused("websocket-client is not installed; cannot open the PumpPortal data stream")
    net.assert_data_ws(DATA_WS_URL)  # refuses anything but the read-only wss data path

    t0 = time.time()
    received = 0
    creates = 0
    reconnects = 0
    samples: list[dict] = []
    while True:
        try:
            ws = websocket.create_connection(DATA_WS_URL, timeout=30)
            ws.send(json.dumps({"method": "subscribeNewToken"}))
            if verbose:
                print(f"[{_now_iso()}] subscribed to PumpPortal new-token stream", flush=True)
            while True:
                if seconds is not None and time.time() - t0 >= seconds:
                    ws.close()
                    return {"connected": True, "seconds": round(time.time() - t0, 1),
                            "messages_received": received, "create_events": creates,
                            "reconnects": reconnects, "buffer_path": str(BUFFER_PATH),
                            "sample_mints": [s.get("mint") for s in samples[:5]]}
                ws.settimeout(30)
                try:
                    msg = ws.recv()
                except websocket.WebSocketTimeoutException:
                    continue  # quiet stretch; keep the connection open
                received += 1
                try:
                    ev = json.loads(msg)
                except json.JSONDecodeError:
                    continue
                rec = _normalize_event(ev)
                if rec is None:
                    continue
                creates += 1
                _append(rec)
                if len(samples) < 5:
                    samples.append(rec)
                if creates % 200 == 0:
                    _trim_buffer()
        except Refused:
            raise
        except Exception as exc:  # noqa: BLE001 -- transient socket drop; reconnect politely
            reconnects += 1
            if verbose:
                print(f"[{_now_iso()}] stream dropped ({exc!r}); reconnecting", flush=True)
            if seconds is not None and time.time() - t0 >= seconds:
                return {"connected": received > 0, "seconds": round(time.time() - t0, 1),
                        "messages_received": received, "create_events": creates,
                        "reconnects": reconnects, "buffer_path": str(BUFFER_PATH),
                        "sample_mints": [s.get("mint") for s in samples[:5]]}
            time.sleep(min(5.0, 1.0 + reconnects))
