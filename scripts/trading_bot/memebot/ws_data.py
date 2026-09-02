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
import tempfile
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
STREAM_HEALTH_PATH = CACHE / "pumpportal_stream_health.json"
_MAX_BUFFER_LINES = 6000  # bound the on-disk buffer so a long run never grows without limit
_MAX_TRADE_BYTES = 1024 * 1024 * 1024
_RESERVE_BYTES = 10 * 1024 * 1024 * 1024
_GENESIS = "0" * 64
_HEALTH_SCHEMA = 1
_HTTP_403_COOLDOWN_S = 3600.0
_HEALTH_FLUSH_S = 2.0
_TRADE_IDLE_UNSUBSCRIBE_S = 900.0
_MAX_ACTIVE_TRADE_SUBSCRIPTIONS = 5000


def _feed_configured() -> bool:
    """True if a trade-data feed is configured. Since PumpPortal IP-banned us (2026-09-02), the feed is the
    pump.fun program's own on-chain anchor events via our FUNDED Helius logsSubscribe — so a Helius endpoint
    (env or repo .env) authorizes trade data. A legacy PUMPPORTAL_DATA_API_KEY still counts."""
    for key in ("HELIUS_RPC_URL", "HELIUS_API_KEY", "PUMPPORTAL_DATA_API_KEY"):
        if os.environ.get(key, "").strip():
            return True
    try:
        env = pathlib.Path(__file__).resolve().parents[3] / ".env"
        for line in env.read_text().splitlines():
            line = line.strip()
            if "=" not in line or line.startswith("#"):
                continue
            name, value = line.split("=", 1)
            if (name.strip() in ("HELIUS_RPC_URL", "HELIUS_API_KEY", "PUMPPORTAL_DATA_API_KEY")
                    and value.strip().strip('"').strip("'")):
                return True
    except OSError:
        pass
    return False


def trade_data_authorized() -> bool:
    """Trade data is authorized when a trade feed is configured (now Helius; see _feed_configured)."""
    return _feed_configured()


def _data_ws_url() -> str:
    key = os.environ.get("PUMPPORTAL_DATA_API_KEY", "").strip()
    return DATA_WS_URL if not key else f"{DATA_WS_URL}?api-key={urllib.parse.quote(key, safe='')}"


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _write_stream_health(record: dict, path: pathlib.Path = STREAM_HEALTH_PATH) -> None:
    """Atomically persist non-secret stream health. Never store the endpoint or API key."""
    body = {"schema": _HEALTH_SCHEMA, **record, "updated_unix_nanos": time.time_ns()}
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(body, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def assess_stream_health(record: dict | None, *, now_ns: int | None = None,
                         max_stale_s: float = 30.0) -> dict:
    """Pure fail-closed health verdict used by runners and dashboard."""
    now_ns = time.time_ns() if now_ns is None else now_ns
    if not isinstance(record, dict) or record.get("schema") != _HEALTH_SCHEMA:
        return {"ok": False, "status": "MISSING", "reason": "stream health is missing"}
    status = record.get("status")
    if status != "CONNECTED":
        return {"ok": False, "status": status or "UNKNOWN",
                "reason": record.get("reason") or "stream is not connected",
                "next_retry_unix_nanos": record.get("next_retry_unix_nanos")}
    last = record.get("last_message_unix_nanos")
    if type(last) is not int or last <= 0 or last > now_ns:
        return {"ok": False, "status": "INVALID_CLOCK", "reason": "stream message clock is invalid"}
    age_s = (now_ns - last) / 1e9
    if age_s > max_stale_s:
        return {"ok": False, "status": "STALE", "reason": f"last stream message is {age_s:.1f}s old",
                "age_s": age_s}
    return {"ok": True, "status": "CONNECTED", "reason": "stream is fresh", "age_s": age_s,
            "last_message_unix_nanos": last,
            "last_trade_unix_nanos": record.get("last_trade_unix_nanos"),
            "last_create_unix_nanos": record.get("last_create_unix_nanos")}


def stream_health(*, path: pathlib.Path = STREAM_HEALTH_PATH, now_ns: int | None = None,
                  max_stale_s: float = 30.0) -> dict:
    try:
        record = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        record = None
    return assess_stream_health(record, now_ns=now_ns, max_stale_s=max_stale_s)


def require_trade_stream_fresh(*, max_stale_s: float = 30.0) -> dict:
    verdict = stream_health(max_stale_s=max_stale_s)
    if not verdict["ok"]:
        raise Refused(f"realtime trade stream {verdict['status']}: {verdict['reason']}")
    return verdict


def _normalize_event(ev: dict, *, received_unix_nanos: int | None = None,
                     source: str = "pumpportal") -> dict | None:
    """Keep only new-token CREATE events, stamped with a local receive time for the age filter."""
    if ev.get("txType") != "create" or not ev.get("mint"):
        return None
    return {
        "source": source,
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


def _trade_body(ev: dict, raw_text: str, received_unix_nanos: int,
                source: str = "PUMPPORTAL_READ_ONLY_DATA_WS") -> dict | None:
    if ev.get("txType") not in {"buy", "sell", "migrate", "migration"} \
            or not isinstance(ev.get("mint"), str):
        return None
    return {
        "schema": 2, "source": source, "mint": ev["mint"],
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
    health = {"status": "CONNECTING", "reason": "listener starting", "reconnects": 0,
              "last_message_unix_nanos": None, "last_trade_unix_nanos": None,
              "last_create_unix_nanos": None, "http_status": None,
              "next_retry_unix_nanos": None}
    _write_stream_health(health)
    last_health_flush = 0.0
    subscribed = {row["mint"]: time.monotonic() for row in read_buffer(
        max_age_minutes=_TRADE_IDLE_UNSUBSCRIBE_S / 60.0) if isinstance(row.get("mint"), str)}
    subscriptions_total = len(subscribed)
    unsubscriptions_total = 0
    trade_events = 0
    while True:
        try:
            ws = websocket.create_connection(endpoint, timeout=30)
            health.update(status="CONNECTED", reason="websocket connected", http_status=None,
                          next_retry_unix_nanos=None, reconnects=reconnects)
            _write_stream_health(health)
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
                health["last_message_unix_nanos"] = received_ns
                try:
                    ev = json.loads(msg)
                except json.JSONDecodeError:
                    continue
                rec = _normalize_event(ev, received_unix_nanos=received_ns)
                if rec is not None:
                    creates += 1
                    health["last_create_unix_nanos"] = received_ns
                    _append(rec)
                    mint = rec["mint"]
                    if mint not in subscribed:
                        if trades_enabled and len(subscribed) < _MAX_ACTIVE_TRADE_SUBSCRIPTIONS:
                            subscribed[mint] = time.monotonic()
                            subscriptions_total += 1
                            ws.send(json.dumps({"method": "subscribeTokenTrade", "keys": [mint]}))
                    if len(samples) < 5:
                        samples.append(rec)
                    if creates % 200 == 0:
                        _trim_buffer()
                trade = _trade_body(ev, msg, received_ns)
                # Migration is a free global subscription and must reach the migration arm even after the
                # per-token paid trade lease expired. Buy/sell events are admitted only for active leases.
                if trade is not None and (trade["tx_type"] in {"migrate", "migration"}
                                          or trade["mint"] in subscribed):
                    trade_head = _append_trade(trade, trade_head)
                    health["last_trade_unix_nanos"] = received_ns
                    trade_events += 1
                    if trade["mint"] in subscribed:
                        subscribed[trade["mint"]] = time.monotonic()
                now_monotonic = time.monotonic()
                if trades_enabled:
                    expired = [mint for mint, last in subscribed.items()
                               if now_monotonic - last >= _TRADE_IDLE_UNSUBSCRIBE_S]
                    if expired:
                        for offset in range(0, len(expired), 5000):
                            ws.send(json.dumps({"method": "unsubscribeTokenTrade",
                                                "keys": expired[offset:offset + 5000]}))
                        for mint in expired:
                            subscribed.pop(mint, None)
                        unsubscriptions_total += len(expired)
                if time.monotonic() - last_health_flush >= _HEALTH_FLUSH_S:
                    health["reconnects"] = reconnects
                    health["active_trade_subscriptions"] = len(subscribed)
                    health["subscriptions_total"] = subscriptions_total
                    health["unsubscriptions_total"] = unsubscriptions_total
                    health["trade_events"] = trade_events
                    _write_stream_health(health)
                    last_health_flush = time.monotonic()
        except Refused:
            raise
        except websocket.WebSocketBadStatusException as exc:
            reconnects += 1
            status = getattr(exc, "status_code", None)
            if status == 403:
                retry_ns = time.time_ns() + int(_HTTP_403_COOLDOWN_S * 1e9)
                health.update(status="HTTP_403_COOLDOWN",
                              reason="provider refused the handshake; cooling down before one retry",
                              reconnects=reconnects, http_status=403,
                              next_retry_unix_nanos=retry_ns)
                _write_stream_health(health)
                if verbose:
                    print(f"[{_now_iso()}] PumpPortal HTTP 403; cooling down for "
                          f"{int(_HTTP_403_COOLDOWN_S)}s", flush=True)
                if seconds is not None:
                    return {"connected": received > 0, "seconds": round(time.time() - t0, 1),
                            "messages_received": received, "create_events": creates,
                            "reconnects": reconnects, "buffer_path": str(BUFFER_PATH),
                            "trade_data_authorized": trades_enabled,
                            "sample_mints": [s.get("mint") for s in samples[:5]],
                            "status": "HTTP_403_COOLDOWN"}
                time.sleep(_HTTP_403_COOLDOWN_S)
                continue
            delay = min(60.0, 2.0 ** min(reconnects, 6))
            health.update(status="HTTP_ERROR", reason=f"websocket handshake HTTP {status}",
                          reconnects=reconnects, http_status=status,
                          next_retry_unix_nanos=time.time_ns() + int(delay * 1e9))
            _write_stream_health(health)
            time.sleep(delay)
        except Exception as exc:  # noqa: BLE001 -- transient socket drop; reconnect politely
            reconnects += 1
            delay = min(60.0, 2.0 ** min(reconnects, 6))
            health.update(status="DISCONNECTED", reason=type(exc).__name__, reconnects=reconnects,
                          http_status=None,
                          next_retry_unix_nanos=time.time_ns() + int(delay * 1e9))
            _write_stream_health(health)
            if verbose:
                print(f"[{_now_iso()}] stream dropped ({exc!r}); reconnecting", flush=True)
            if seconds is not None and time.time() - t0 >= seconds:
                return {"connected": received > 0, "seconds": round(time.time() - t0, 1),
                        "messages_received": received, "create_events": creates,
                        "reconnects": reconnects, "buffer_path": str(BUFFER_PATH),
                        "trade_data_authorized": trades_enabled,
                        "sample_mints": [s.get("mint") for s in samples[:5]]}
            time.sleep(delay)
