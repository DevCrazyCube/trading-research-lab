#!/usr/bin/env python3
"""PAC V2 causal feed with three non-interchangeable local clocks and incremental consumption.

The collector has its own public-RPC subscription so changing this module cannot drift PAC V1's sealed
feed.  An event is appended first; only after that append succeeds is a materialisation receipt written.
The strategy admits the event only after reading both and adds its own runner-seen clock.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import os
import pathlib
import time
import uuid

from scripts import b15a_websocket as ws_client
from scripts.trading_bot.aftershock.execution import ReserveState, RefusedExecution
_COMMON_PATH = pathlib.Path(__file__).resolve().parents[1] / "sniper" / "data" / "_common.py"
_COMMON_SPEC = importlib.util.spec_from_file_location("pac_v2_sniper_common", _COMMON_PATH)
if _COMMON_SPEC is None or _COMMON_SPEC.loader is None:  # pragma: no cover - filesystem invariant
    raise ImportError("cannot load the pinned sniper common decoder")
_COMMON = importlib.util.module_from_spec(_COMMON_SPEC)
_COMMON_SPEC.loader.exec_module(_COMMON)
PUMP_PROGRAM = _COMMON.PUMP_PROGRAM
SOL_USD_DEFAULT = _COMMON.SOL_USD_DEFAULT
decode_pump_trades_from_logs = _COMMON.decode_pump_trades_from_logs


ROOT = pathlib.Path(__file__).resolve().parents[3]
DATA = ROOT / "research" / "data" / "aftershock" / "pac_v2"
EVENTS = DATA / "feed_events.jsonl"
RECEIPTS = DATA / "feed_materialization.jsonl"
PUBLIC_WS_URL = "wss://api.mainnet-beta.solana.com"
SOURCE = "public_rpc_processed_pac_v2"
SCHEMA = 1


def _canonical_sha(body: dict) -> str:
    return hashlib.sha256(json.dumps(
        body, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


def _append(path: pathlib.Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode()
    descriptor = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        written = os.write(descriptor, payload)
        if written != len(payload):
            raise OSError(f"short append {written}/{len(payload)}")
    finally:
        os.close(descriptor)


def _state(ev: dict) -> ReserveState:
    values = {
        "virtual_quote": ev.get("virtual_sol"), "virtual_token": ev.get("virtual_tok"),
        "real_quote": ev.get("real_sol"), "real_token": ev.get("real_tok"),
    }
    if any(type(value) is not int or value < 0 for value in values.values()):
        raise RefusedExecution("PAC V2 decoded trade lacks exact non-negative reserves")
    return ReserveState(**values, complete=False)


@dataclass(frozen=True)
class ClockedEvent:
    event_id: str
    collector_epoch: str
    mint: str
    trader: str
    signature: str
    slot: int
    side: str
    source_received_unix_nanos: int
    materialized_unix_nanos: int
    runner_seen_unix_nanos: int
    pre_state: ReserveState
    post_state: ReserveState

    @property
    def observation_unix_nanos(self) -> int:
        return self.source_received_unix_nanos

    def __post_init__(self):
        for label, value in (("source_received", self.source_received_unix_nanos),
                             ("materialized", self.materialized_unix_nanos),
                             ("runner_seen", self.runner_seen_unix_nanos), ("slot", self.slot)):
            if type(value) is not int or value < 0:
                raise RefusedExecution(f"PAC V2 {label} clock/coordinate is invalid")
        if not (self.source_received_unix_nanos <= self.materialized_unix_nanos
                <= self.runner_seen_unix_nanos):
            raise RefusedExecution("PAC V2 source/materialized/runner clocks are backward")
        if self.side not in {"buy", "sell"} or not all(
                isinstance(value, str) and value for value in (
                    self.event_id, self.collector_epoch, self.mint, self.trader, self.signature)):
            raise RefusedExecution("PAC V2 event identity is incomplete")


class FeedWriter:
    def __init__(self, *, events_path: pathlib.Path = EVENTS, receipts_path: pathlib.Path = RECEIPTS,
                 epoch: str | None = None):
        self.events_path = pathlib.Path(events_path)
        self.receipts_path = pathlib.Path(receipts_path)
        self.epoch = epoch or uuid.uuid4().hex
        self.previous: dict[str, ReserveState] = {}

    def append_decoded(self, ev: dict, *, signature: str, slot: int,
                       source_received_unix_nanos: int) -> str:
        if (not isinstance(signature, str) or not signature or type(slot) is not int or slot < 0
                or type(source_received_unix_nanos) is not int or source_received_unix_nanos < 0):
            raise RefusedExecution("PAC V2 source observation identity/clock is invalid")
        mint, trader, side = ev.get("mint"), ev.get("user"), ev.get("side")
        if not all(isinstance(value, str) and value for value in (mint, trader)) or side not in {"buy", "sell"}:
            raise RefusedExecution("PAC V2 decoded trade lacks mint/trader/side")
        post = _state(ev); pre = self.previous.get(mint, post)
        body = {
            "schema": SCHEMA, "source": SOURCE, "collector_epoch": self.epoch,
            "mint": mint, "trader": trader, "signature": signature, "slot": slot, "side": side,
            "source_received_unix_nanos": source_received_unix_nanos,
            "pre_state": asdict(pre), "post_state": asdict(post),
        }
        event_id = _canonical_sha(body)
        _append(self.events_path, {**body, "event_id": event_id})
        materialized = time.time_ns()
        receipt_body = {"schema": SCHEMA, "event_id": event_id,
                        "materialized_unix_nanos": materialized}
        _append(self.receipts_path, {**receipt_body, "receipt_sha256": _canonical_sha(receipt_body)})
        self.previous[mint] = post
        return event_id


def _read_complete(path: pathlib.Path, offset: int) -> tuple[list[dict], int]:
    if type(offset) is not int or offset < 0:
        raise RefusedExecution("PAC V2 incremental offset is invalid")
    try:
        size = path.stat().st_size
    except FileNotFoundError:
        return [], offset
    if size < offset:
        raise RefusedExecution("PAC V2 append-only feed truncated behind its durable cursor")
    with path.open("rb") as handle:
        handle.seek(offset); payload = handle.read()
    if not payload:
        return [], offset
    end = payload.rfind(b"\n")
    if end < 0:
        return [], offset
    complete = payload[:end + 1]
    rows = []
    for raw in complete.splitlines():
        try:
            row = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RefusedExecution("PAC V2 append-only feed contains invalid JSON") from exc
        if not isinstance(row, dict):
            raise RefusedExecution("PAC V2 feed row is not an object")
        rows.append(row)
    return rows, offset + len(complete)


@dataclass
class Cursor:
    event_offset: int = 0
    receipt_offset: int = 0
    pending: dict[str, dict] | None = None

    def __post_init__(self):
        if self.pending is None:
            self.pending = {}


def consume(cursor: Cursor, *, events_path: pathlib.Path = EVENTS,
            receipts_path: pathlib.Path = RECEIPTS,
            runner_seen_unix_nanos: int | None = None) -> list[ClockedEvent]:
    if not isinstance(cursor, Cursor):
        raise RefusedExecution("PAC V2 Cursor required")
    events, event_offset = _read_complete(pathlib.Path(events_path), cursor.event_offset)
    receipts, receipt_offset = _read_complete(pathlib.Path(receipts_path), cursor.receipt_offset)
    for row in events:
        if row.get("schema") != SCHEMA or row.get("source") != SOURCE:
            raise RefusedExecution("PAC V2 event schema/source mismatch")
        event_id = row.get("event_id")
        body = {key: value for key, value in row.items() if key != "event_id"}
        if not isinstance(event_id, str) or _canonical_sha(body) != event_id or event_id in cursor.pending:
            raise RefusedExecution("PAC V2 event id is forged or duplicated")
        cursor.pending[event_id] = row
    materialized: dict[str, int] = {}
    for row in receipts:
        body = {key: value for key, value in row.items() if key != "receipt_sha256"}
        if (row.get("schema") != SCHEMA or _canonical_sha(body) != row.get("receipt_sha256")
                or type(row.get("materialized_unix_nanos")) is not int):
            raise RefusedExecution("PAC V2 materialization receipt is invalid")
        event_id = row.get("event_id")
        if event_id in materialized:
            raise RefusedExecution("PAC V2 materialization receipt is duplicated")
        materialized[event_id] = row["materialized_unix_nanos"]
    seen = time.time_ns() if runner_seen_unix_nanos is None else runner_seen_unix_nanos
    if type(seen) is not int or seen < 0:
        raise RefusedExecution("PAC V2 runner-seen clock is invalid")
    out = []
    for event_id, stamp in materialized.items():
        row = cursor.pending.get(event_id)
        if row is None:
            raise RefusedExecution("PAC V2 receipt does not reference a pending event")
        try:
            pre = ReserveState(**row["pre_state"]); post = ReserveState(**row["post_state"])
        except (KeyError, TypeError, ValueError) as exc:
            raise RefusedExecution("PAC V2 reserve state is invalid") from exc
        out.append(ClockedEvent(
            event_id=event_id, collector_epoch=row["collector_epoch"], mint=row["mint"],
            trader=row["trader"], signature=row["signature"], slot=row["slot"], side=row["side"],
            source_received_unix_nanos=row["source_received_unix_nanos"],
            materialized_unix_nanos=stamp, runner_seen_unix_nanos=seen,
            pre_state=pre, post_state=post))
        del cursor.pending[event_id]
    cursor.event_offset = event_offset; cursor.receipt_offset = receipt_offset
    return sorted(out, key=lambda event: (
        event.runner_seen_unix_nanos, event.source_received_unix_nanos, event.event_id))


def run_collector() -> None:
    writer = FeedWriter()
    subscription = {"jsonrpc": "2.0", "id": 1, "method": "logsSubscribe",
                    "params": [{"mentions": [PUMP_PROGRAM]}, {"commitment": "processed"}]}
    while True:
        ws = None
        try:
            ws = ws_client.WebSocket(PUBLIC_WS_URL, timeout=30.0).connect()
            ws.send_json(subscription); ws.recv()
            while True:
                raw = ws.recv()
                if raw is None:
                    raise ws_client.WebSocketRefused("public RPC closed the PAC V2 subscription")
                message = json.loads(raw)
                result = ((message.get("params") or {}).get("result") or {})
                value = result.get("value") or {}; context = result.get("context") or {}
                signature, slot = value.get("signature"), context.get("slot")
                if value.get("err") is not None:
                    continue
                for event in decode_pump_trades_from_logs(value.get("logs") or [], SOL_USD_DEFAULT):
                    # Sequential decoder-observation clocks: multiple TradeEvents may share one
                    # transaction, but the decision engine observes them one after another.
                    received = time.time_ns()
                    writer.append_decoded(event, signature=signature, slot=slot,
                                          source_received_unix_nanos=received)
        except Exception as exc:  # noqa: BLE001 - collector visibly retries, never authorizes a trade
            print(f"{dt.datetime.now(dt.timezone.utc).isoformat()} PAC_V2_FEED_REFUSED "
                  f"{type(exc).__name__}:{str(exc)[:180]}", flush=True)
            time.sleep(2.0)
        finally:
            if ws is not None:
                ws.close()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="PAC V2 read-only causal feed collector")
    parser.parse_args(argv)
    run_collector()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
