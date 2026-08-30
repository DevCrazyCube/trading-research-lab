#!/usr/bin/env python3
"""PAC V2.2 low-lag causal feed candidate.

This is a versioned successor to the sealed V2/V2.1 collector.  It fixes three operational defects
without mutating the active instrument: reconnect recovery reads only the single possible unmatched
tail event, the Pump logs subscription is created once (V2 accidentally created it twice), and every
raw frame is timestamped before JSON decoding.  An independent processed-head poll makes backlog
visible and fail-closed.  This module records observations only; it has no wallet or order path.
"""
from __future__ import annotations

from dataclasses import asdict
import contextlib
import datetime as dt
import hashlib
import json
import os
import pathlib
import threading
import time
import urllib.request
import uuid

from scripts import b15a_websocket as ws_client
from .execution import RefusedExecution
from . import pac_v2_feed as base


ROOT = pathlib.Path(__file__).resolve().parents[3]
DATA = ROOT / "research" / "data" / "aftershock" / "pac_v22"
EVENTS = DATA / "feed_events.jsonl"
RECEIPTS = DATA / "feed_materialization.jsonl"
HEALTH = DATA / "feed_health.json"
PUBLIC_WS_URL = base.PUBLIC_WS_URL
PUBLIC_HTTP_URL = "https://api.mainnet-beta.solana.com"
SOURCE = "public_rpc_processed_pac_v22"
SCHEMA = base.SCHEMA
MAX_HEAD_SLOT_LAG = 32
MAX_HEAD_AGE_NANOS = 5_000_000_000
MAX_HEALTH_AGE_NANOS = 5_000_000_000
HEAD_POLL_SECONDS = 1.0
ReserveState = base.ReserveState
ClockedEvent = base.ClockedEvent
Cursor = base.Cursor


def _canonical_sha(body: dict) -> str:
    return hashlib.sha256(json.dumps(
        body, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


def _atomic_json(path: pathlib.Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        if os.write(descriptor, payload) != len(payload):
            raise OSError("short PAC V2.2 health write")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.replace(temporary, path)


def _health_body(*, status: str, epoch: str, observed_unix_nanos: int,
                 head_slot: int | None, event_slot: int | None, reason: str | None) -> dict:
    if status not in {"FRESH", "DEGRADED"} or not isinstance(epoch, str) or not epoch:
        raise RefusedExecution("PAC V2.2 health identity is invalid")
    if type(observed_unix_nanos) is not int or observed_unix_nanos <= 0:
        raise RefusedExecution("PAC V2.2 health clock is invalid")
    for value in (head_slot, event_slot):
        if value is not None and (type(value) is not int or value < 0):
            raise RefusedExecution("PAC V2.2 health slot is invalid")
    lag = None if head_slot is None or event_slot is None else max(0, head_slot - event_slot)
    return {
        "schema": 1, "instrument_id": "AFTERSHOCK_PAC_V22_FEED",
        "status": status, "collector_epoch": epoch,
        "observed_unix_nanos": observed_unix_nanos,
        "head_slot": head_slot, "event_slot": event_slot, "head_slot_lag": lag,
        "reason": reason,
    }


def write_health(**kwargs) -> dict:
    body = _health_body(**kwargs)
    row = {**body, "health_sha256": _canonical_sha(body)}
    _atomic_json(HEALTH, row)
    return row


def load_health(path: pathlib.Path | None = None, *, now: int | None = None,
                require_fresh: bool = False) -> dict:
    clock = time.time_ns() if now is None else now
    target = HEALTH if path is None else pathlib.Path(path)
    try:
        row = json.loads(target.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise RefusedExecution("PAC V2.2 feed health is unreadable") from exc
    if not isinstance(row, dict) or set(row) != {
            "schema", "instrument_id", "status", "collector_epoch", "observed_unix_nanos",
            "head_slot", "event_slot", "head_slot_lag", "reason", "health_sha256"}:
        raise RefusedExecution("PAC V2.2 feed health schema is invalid")
    body = {key: value for key, value in row.items() if key != "health_sha256"}
    expected = _health_body(
        status=body["status"], epoch=body["collector_epoch"],
        observed_unix_nanos=body["observed_unix_nanos"], head_slot=body["head_slot"],
        event_slot=body["event_slot"], reason=body["reason"])
    if (body != expected or row["health_sha256"] != _canonical_sha(body)
            or type(clock) is not int or clock < body["observed_unix_nanos"]):
        raise RefusedExecution("PAC V2.2 feed health hash/clock refuses")
    if require_fresh and (body["status"] != "FRESH"
                          or clock - body["observed_unix_nanos"] > MAX_HEALTH_AGE_NANOS
                          or body["head_slot_lag"] is None
                          or body["head_slot_lag"] > MAX_HEAD_SLOT_LAG):
        raise RefusedExecution("PAC V2.2 feed is stale, degraded, or lagged")
    return row


def _last_complete(path: pathlib.Path, *, window: int = 1_048_576) -> dict | None:
    try:
        with path.open("rb") as handle:
            handle.seek(0, 2); size = handle.tell()
            if size == 0:
                return None
            handle.seek(max(0, size - window)); payload = handle.read()
    except FileNotFoundError:
        return None
    lines = [line for line in payload.splitlines() if line.strip()]
    if not lines:
        return None
    if len(lines[-1]) >= window and size > window:
        raise RefusedExecution("PAC V2.2 tail record exceeds recovery window")
    try:
        row = json.loads(lines[-1])
    except json.JSONDecodeError as exc:
        raise RefusedExecution("PAC V2.2 tail record is malformed") from exc
    if not isinstance(row, dict):
        raise RefusedExecution("PAC V2.2 tail record is not an object")
    return row


class FeedWriter:
    """Single-threaded event/receipt writer with O(1)-tail restart recovery."""

    def __init__(self, *, events_path: pathlib.Path = EVENTS,
                 receipts_path: pathlib.Path = RECEIPTS, epoch: str | None = None):
        self.events_path = pathlib.Path(events_path)
        self.receipts_path = pathlib.Path(receipts_path)
        self.epoch = epoch or uuid.uuid4().hex
        self.previous: dict[str, ReserveState] = {}
        self._last_source_received = 0
        self._recover_tail()

    def _recover_tail(self) -> None:
        event = _last_complete(self.events_path)
        receipt = _last_complete(self.receipts_path)
        if event is None:
            if receipt is not None:
                raise RefusedExecution("PAC V2.2 receipt exists without any event")
            return
        event_id = event.get("event_id")
        body = {key: value for key, value in event.items() if key != "event_id"}
        if (event.get("schema") != SCHEMA or event.get("source") != SOURCE
                or not isinstance(event_id, str) or _canonical_sha(body) != event_id):
            raise RefusedExecution("PAC V2.2 tail event is forged")
        if receipt is not None:
            receipt_body = {key: value for key, value in receipt.items()
                            if key != "receipt_sha256"}
            if (receipt.get("schema") != SCHEMA
                    or _canonical_sha(receipt_body) != receipt.get("receipt_sha256")):
                raise RefusedExecution("PAC V2.2 tail receipt is forged")
            if receipt.get("event_id") == event_id:
                return
        source_clock = event.get("source_received_unix_nanos")
        if type(source_clock) is not int or source_clock < 0:
            raise RefusedExecution("PAC V2.2 unmatched tail event clock is invalid")
        recovered = {
            "schema": SCHEMA, "event_id": event_id,
            "materialized_unix_nanos": max(time.time_ns(), source_clock),
            "recovered_after_crash": True,
        }
        base._append(self.receipts_path, {
            **recovered, "receipt_sha256": _canonical_sha(recovered)})

    def append_decoded(self, ev: dict, *, signature: str, slot: int,
                       frame_received_unix_nanos: int) -> str:
        if (not isinstance(signature, str) or not signature or type(slot) is not int or slot < 0
                or type(frame_received_unix_nanos) is not int
                or frame_received_unix_nanos <= 0):
            raise RefusedExecution("PAC V2.2 source observation identity/clock is invalid")
        source_clock = max(frame_received_unix_nanos, self._last_source_received + 1)
        self._last_source_received = source_clock
        mint, trader, side = ev.get("mint"), ev.get("user"), ev.get("side")
        if not all(isinstance(value, str) and value for value in (mint, trader)) \
                or side not in {"buy", "sell"}:
            raise RefusedExecution("PAC V2.2 decoded trade lacks mint/trader/side")
        post = base._state(ev); pre = self.previous.get(mint)
        body = {
            "schema": SCHEMA, "source": SOURCE, "collector_epoch": self.epoch,
            "mint": mint, "trader": trader, "signature": signature, "slot": slot,
            "side": side, "source_received_unix_nanos": source_clock,
            "continuity_proven": pre is not None,
            "pre_state": asdict(pre) if pre is not None else None,
            "post_state": asdict(post),
        }
        event_id = _canonical_sha(body)
        base._append(self.events_path, {**body, "event_id": event_id})
        materialized = max(time.time_ns(), source_clock)
        receipt = {"schema": SCHEMA, "event_id": event_id,
                   "materialized_unix_nanos": materialized,
                   "recovered_after_crash": False}
        base._append(self.receipts_path, {
            **receipt, "receipt_sha256": _canonical_sha(receipt)})
        self.previous[mint] = post
        return event_id


@contextlib.contextmanager
def _base_source():
    original = base.SOURCE
    base.SOURCE = SOURCE
    try:
        yield
    finally:
        base.SOURCE = original


def consume(cursor: Cursor, *, events_path: pathlib.Path = EVENTS,
            receipts_path: pathlib.Path = RECEIPTS,
            runner_seen_unix_nanos: int | None = None) -> list[ClockedEvent]:
    with _base_source():
        return base.consume(
            cursor, events_path=events_path, receipts_path=receipts_path,
            runner_seen_unix_nanos=runner_seen_unix_nanos)


class HeadState:
    def __init__(self):
        self._lock = threading.Lock()
        self.slot: int | None = None
        self.observed_unix_nanos: int | None = None
        self.error: str | None = "NOT_STARTED"

    def update(self, slot: int, observed_unix_nanos: int) -> None:
        if type(slot) is not int or slot < 0 or type(observed_unix_nanos) is not int \
                or observed_unix_nanos <= 0:
            raise RefusedExecution("PAC V2.2 head observation is invalid")
        with self._lock:
            self.slot, self.observed_unix_nanos, self.error = slot, observed_unix_nanos, None

    def fail(self, reason: str) -> None:
        with self._lock:
            self.error = str(reason)[:160]

    def snapshot(self) -> tuple[int | None, int | None, str | None]:
        with self._lock:
            return self.slot, self.observed_unix_nanos, self.error


def _get_processed_slot(*, opener=urllib.request.urlopen) -> int:
    request = urllib.request.Request(
        PUBLIC_HTTP_URL,
        data=b'{"jsonrpc":"2.0","id":1,"method":"getSlot","params":[{"commitment":"processed"}]}',
        headers={"content-type": "application/json"}, method="POST")
    with opener(request, timeout=5.0) as response:
        payload = json.loads(response.read())
    if (not isinstance(payload, dict) or payload.get("jsonrpc") != "2.0"
            or payload.get("id") != 1 or type(payload.get("result")) is not int
            or payload["result"] < 0):
        raise RefusedExecution("PAC V2.2 processed-head RPC identity/result refuses")
    return payload["result"]


def _head_loop(state: HeadState, stop: threading.Event, *, opener=urllib.request.urlopen) -> None:
    while not stop.is_set():
        try:
            observed = time.time_ns(); slot = _get_processed_slot(opener=opener)
            state.update(slot, observed)
        except Exception as exc:  # noqa: BLE001 - health stays visibly degraded
            state.fail(f"{type(exc).__name__}:{str(exc)[:120]}")
        stop.wait(HEAD_POLL_SECONDS)


def _require_head(state: HeadState, *, event_slot: int, received: int) -> int:
    head, observed, error = state.snapshot()
    if (head is None or observed is None or error is not None or observed > received
            or received - observed > MAX_HEAD_AGE_NANOS
            or head - event_slot > MAX_HEAD_SLOT_LAG):
        raise RefusedExecution("PAC V2.2 processed head is missing, stale, or lagged")
    return head


def _subscribe(ws) -> None:
    request = {"jsonrpc": "2.0", "id": 1, "method": "logsSubscribe",
               "params": [{"mentions": [base.PUMP_PROGRAM]}, {"commitment": "processed"}]}
    ws.send_json(request)
    ack = json.loads(ws.recv())
    if (not isinstance(ack, dict) or ack.get("jsonrpc") != "2.0" or ack.get("id") != 1
            or type(ack.get("result")) is not int):
        raise RefusedExecution("PAC V2.2 logsSubscribe acknowledgement refuses")


def _process_raw(raw: str, *, received: int, writer: FeedWriter,
                 head_state: HeadState) -> int:
    message = json.loads(raw)
    result = ((message.get("params") or {}).get("result") or {})
    value = result.get("value") or {}; context = result.get("context") or {}
    signature, slot = value.get("signature"), context.get("slot")
    if value.get("err") is not None:
        return 0
    if not isinstance(signature, str) or type(slot) is not int:
        raise RefusedExecution("PAC V2.2 logs notification identity refuses")
    head = _require_head(head_state, event_slot=slot, received=received)
    decoded = base.decode_pump_trades_from_logs(value.get("logs") or [], base.SOL_USD_DEFAULT)
    count = 0
    for event in decoded:
        writer.append_decoded(
            event, signature=signature, slot=slot,
            frame_received_unix_nanos=received)
        count += 1
    write_health(status="FRESH", epoch=writer.epoch, observed_unix_nanos=received,
                 head_slot=head, event_slot=slot, reason=None)
    return count


def run_collector() -> None:
    head_state = HeadState(); stop = threading.Event()
    threading.Thread(target=_head_loop, args=(head_state, stop), daemon=True).start()
    try:
        while True:
            ws = None; epoch = uuid.uuid4().hex
            try:
                ws = ws_client.WebSocket(PUBLIC_WS_URL, timeout=30.0).connect()
                _subscribe(ws)
                writer = FeedWriter(epoch=epoch)
                while True:
                    raw = ws.recv()
                    received = time.time_ns()  # captured before JSON parsing or trade decoding
                    if raw is None:
                        raise ws_client.WebSocketRefused("public RPC closed PAC V2.2")
                    _process_raw(raw, received=received, writer=writer, head_state=head_state)
            except Exception as exc:  # noqa: BLE001 - collector visibly retries, never trades
                now = time.time_ns(); head, _, _ = head_state.snapshot()
                write_health(status="DEGRADED", epoch=epoch, observed_unix_nanos=now,
                             head_slot=head, event_slot=None,
                             reason=f"{type(exc).__name__}:{str(exc)[:160]}")
                print(f"{dt.datetime.now(dt.timezone.utc).isoformat()} PAC_V22_FEED_REFUSED "
                      f"{type(exc).__name__}:{str(exc)[:180]}", flush=True)
                time.sleep(2.0)
            finally:
                if ws is not None:
                    ws.close()
    finally:
        stop.set()


if __name__ == "__main__":
    run_collector()
