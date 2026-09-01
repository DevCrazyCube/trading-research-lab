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
import hashlib
import json
import os
import pathlib
import shutil
import time
import urllib.parse

from . import Refused
from . import net
from .frozen import CACHE

try:
    import websocket  # websocket-client
except ImportError:  # pragma: no cover
    websocket = None

DATA_WS_URL = "wss://pumpportal.fun/api/data"
BUFFER_PATH = CACHE / "pumpportal_newtokens.jsonl"
TRADE_BUFFER_PATH = CACHE / "pumpportal_trades_v2.jsonl"
_MAX_BUFFER_LINES = 6000  # bound the on-disk buffer so a long run never grows without limit
_MAX_TRADE_BYTES = 1024 * 1024 * 1024
_RESERVE_BYTES = 10 * 1024 * 1024 * 1024
_GENESIS = "0" * 64


def trade_data_authorized() -> bool:
    """PumpPortal trade streams require a dedicated paid data key as of 2026-05-01.

    Source verified 2026-09-02: https://pumpportal.fun/data-api/real-time/ and /fees/.
    Deliberately do not fall back to LIGHTNING_API: transaction credentials are outside this reader.
    """
    return bool(os.environ.get("PUMPPORTAL_DATA_API_KEY", "").strip())


def _data_ws_url() -> str:
    key = os.environ.get("PUMPPORTAL_DATA_API_KEY", "").strip()
    return DATA_WS_URL if not key else f"{DATA_WS_URL}?api-key={urllib.parse.quote(key, safe='')}"


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _normalize_event(ev: dict, *, received_unix_nanos: int | None = None) -> dict | None:
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
        "received_unix_nanos": received_unix_nanos or time.time_ns(),
    }


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _trade_body(ev: dict, raw_text: str, received_unix_nanos: int) -> dict | None:
    if ev.get("txType") not in {"buy", "sell", "migrate", "migration"} \
            or not isinstance(ev.get("mint"), str):
        return None
    return {
        "schema": 2, "source": "PUMPPORTAL_READ_ONLY_DATA_WS", "mint": ev["mint"],
        "tx_type": ev["txType"], "trader": ev.get("traderPublicKey"),
        "signature": ev.get("signature"), "slot": ev.get("slot"),
        "token_amount": str(ev.get("tokenAmount")), "sol_amount": str(ev.get("solAmount")),
        "virtual_sol": str(ev.get("vSolInBondingCurve")),
        "virtual_tokens": str(ev.get("vTokensInBondingCurve")),
        "real_sol": str(ev.get("realSolInBondingCurve")),
        "real_tokens": str(ev.get("realTokensInBondingCurve")),
        "market_cap_sol": str(ev.get("marketCapSol")), "pool": ev.get("pool"),
        "received_unix_nanos": received_unix_nanos,
        "raw_message_sha256": hashlib.sha256(raw_text.encode()).hexdigest(),
    }


def _trade_head() -> tuple[int, str]:
    if not TRADE_BUFFER_PATH.exists():
        return 0, _GENESIS
    previous = _GENESIS; sequence = 0
    with TRADE_BUFFER_PATH.open() as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            row = json.loads(line); body = dict(row); observed = body.pop("record_sha256", None)
            if (body.get("sequence") != sequence + 1
                    or body.get("previous_record_sha256") != previous
                    or observed != hashlib.sha256(_canonical(body)).hexdigest()):
                raise Refused(f"PumpPortal trade tape chain refuses at line {line_number}")
            sequence += 1; previous = observed
    return sequence, previous


def _append_trade(body: dict, head: tuple[int, str]) -> tuple[int, str]:
    if TRADE_BUFFER_PATH.exists() and TRADE_BUFFER_PATH.stat().st_size >= _MAX_TRADE_BYTES:
        raise Refused("PumpPortal trade tape reached its frozen 1 GiB segment bound")
    if shutil.disk_usage(TRADE_BUFFER_PATH.parent).free < _RESERVE_BYTES:
        raise Refused("PumpPortal trade tape refuses below the 10 GiB filesystem reserve")
    sequence, previous = head
    record_body = {**body, "sequence": sequence + 1, "previous_record_sha256": previous}
    record = {**record_body,
              "record_sha256": hashlib.sha256(_canonical(record_body)).hexdigest()}
    TRADE_BUFFER_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = _canonical(record) + b"\n"
    descriptor = os.open(TRADE_BUFFER_PATH,
                         os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        if os.write(descriptor, payload) != len(payload):
            raise OSError("short PumpPortal trade-tape append")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return sequence + 1, record["record_sha256"]


def read_trade_buffer(*, after_sequence: int = 0) -> list[dict]:
    if type(after_sequence) is not int or after_sequence < 0:
        raise Refused("trade-tape cursor is invalid")
    _trade_head()  # full chain verification before consumer use
    if not TRADE_BUFFER_PATH.exists():
        return []
    output = []
    with TRADE_BUFFER_PATH.open() as handle:
        for line in handle:
            if line.strip():
                row = json.loads(line)
                if row["sequence"] > after_sequence:
                    output.append(row)
    return output


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
    endpoint = _data_ws_url()
    net.assert_data_ws(endpoint)  # refuses anything but the read-only wss data path
    trades_enabled = trade_data_authorized()

    t0 = time.time()
    received = 0
    creates = 0
    reconnects = 0
    samples: list[dict] = []
    trade_head = _trade_head()
    subscribed = {row.get("mint") for row in read_buffer(max_age_minutes=30)
                  if isinstance(row.get("mint"), str)}
    while True:
        try:
            ws = websocket.create_connection(endpoint, timeout=30)
            ws.send(json.dumps({"method": "subscribeNewToken"}))
            ws.send(json.dumps({"method": "subscribeMigration"}))
            if subscribed and trades_enabled:
                ws.send(json.dumps({"method": "subscribeTokenTrade",
                                    "keys": sorted(subscribed)}))
            if verbose:
                print(f"[{_now_iso()}] subscribed to PumpPortal new-token stream", flush=True)
            while True:
                if seconds is not None and time.time() - t0 >= seconds:
                    ws.close()
                    return {"connected": True, "seconds": round(time.time() - t0, 1),
                            "messages_received": received, "create_events": creates,
                            "reconnects": reconnects, "buffer_path": str(BUFFER_PATH),
                            "trade_data_authorized": trades_enabled,
                            "sample_mints": [s.get("mint") for s in samples[:5]]}
                ws.settimeout(30)
                try:
                    msg = ws.recv()
                except websocket.WebSocketTimeoutException:
                    continue  # quiet stretch; keep the connection open
                received += 1
                received_ns = time.time_ns()
                try:
                    ev = json.loads(msg)
                except json.JSONDecodeError:
                    continue
                rec = _normalize_event(ev, received_unix_nanos=received_ns)
                if rec is not None:
                    creates += 1
                    _append(rec)
                    mint = rec["mint"]
                    if mint not in subscribed:
                        subscribed.add(mint)
                        if trades_enabled:
                            ws.send(json.dumps({"method": "subscribeTokenTrade", "keys": [mint]}))
                    if len(samples) < 5:
                        samples.append(rec)
                    if creates % 200 == 0:
                        _trim_buffer()
                trade = _trade_body(ev, msg, received_ns)
                if trade is not None and trade["mint"] in subscribed:
                    trade_head = _append_trade(trade, trade_head)
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
                        "trade_data_authorized": trades_enabled,
                        "sample_mints": [s.get("mint") for s in samples[:5]]}
            time.sleep(min(5.0, 1.0 + reconnects))
