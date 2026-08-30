#!/usr/bin/env python3
"""Hostile controls for the low-lag PAC V2.2 feed candidate."""
from __future__ import annotations

import json
import pathlib
import tempfile
import time
from unittest.mock import patch

from .execution import RefusedExecution
from . import pac_v2_feed as base
from . import pac_v22_feed as feed


CHECKS = 0


def check(condition: bool, label: str) -> None:
    global CHECKS
    if not condition:
        raise AssertionError(label)
    CHECKS += 1
    print(f"[ok] {label}")


def refuses(fn, label: str) -> None:
    try:
        fn()
    except RefusedExecution:
        check(True, label)
    else:
        raise AssertionError(label)


def trade(real_quote: int, *, side: str = "buy", user: str = "buyer") -> dict:
    return {
        "mint": "mint", "user": user, "side": side,
        "virtual_sol": 30_000_000_000 + real_quote,
        "virtual_tok": 1_000_000_000_000_000,
        "real_sol": real_quote, "real_tok": 720_100_000_000_000,
    }


class FakeResponse:
    def __init__(self, payload: object):
        self.payload = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.payload


class FakeWs:
    def __init__(self):
        self.sent = []

    def send_json(self, value):
        self.sent.append(value)

    def recv(self):
        return json.dumps({"jsonrpc": "2.0", "id": 1, "result": 77})


def main() -> int:
    base_clock = time.time_ns() - 10_000_000
    with tempfile.TemporaryDirectory(prefix="pac_v22_feed_") as td:
        root = pathlib.Path(td)
        events, receipts, health = root / "events.jsonl", root / "receipts.jsonl", root / "health.json"

        with patch.object(base, "_read_complete", side_effect=AssertionError("full scan forbidden")):
            writer = feed.FeedWriter(
                events_path=events, receipts_path=receipts, epoch="epoch-one")
        check(not events.exists() and not receipts.exists(),
              "clean startup performs no full-history recovery scan")

        writer.append_decoded(
            trade(1_000_000_000), signature="sig-1", slot=10,
            frame_received_unix_nanos=base_clock)
        writer.append_decoded(
            trade(1_100_000_000, user="buyer-2"), signature="sig-2", slot=11,
            frame_received_unix_nanos=base_clock)
        event_rows = [json.loads(line) for line in events.read_text().splitlines()]
        check(len(event_rows) == 2
              and event_rows[0]["source_received_unix_nanos"] == base_clock
              and event_rows[1]["source_received_unix_nanos"] == base_clock + 1,
              "one raw-frame clock is preserved with exact one-nanosecond event ordering")

        cursor = feed.Cursor()
        consumed = feed.consume(
            cursor, events_path=events, receipts_path=receipts,
            runner_seen_unix_nanos=time.time_ns())
        check(len(consumed) == 1 and consumed[0].slot == 11
              and consumed[0].source_received_unix_nanos == base_clock + 1,
              "schema-compatible consumer omits only the epoch continuity seed")

        before = receipts.stat().st_size
        with patch.object(base, "_read_complete", side_effect=AssertionError("full scan forbidden")):
            feed.FeedWriter(events_path=events, receipts_path=receipts, epoch="epoch-two")
        check(receipts.stat().st_size == before,
              "matched event/receipt tails restart in O(1) without duplicate recovery")

        crash_events, crash_receipts = root / "crash-events.jsonl", root / "crash-receipts.jsonl"
        body = {
            "schema": feed.SCHEMA, "source": feed.SOURCE, "collector_epoch": "crash",
            "mint": "mint", "trader": "buyer", "signature": "crash-sig", "slot": 12,
            "side": "buy", "source_received_unix_nanos": base_clock,
            "continuity_proven": False, "pre_state": None,
            "post_state": {
                "virtual_quote": 31_000_000_000, "virtual_token": 1_000_000_000_000_000,
                "real_quote": 1_000_000_000, "real_token": 720_100_000_000_000,
                "complete": False,
            },
        }
        base._append(crash_events, {**body, "event_id": feed._canonical_sha(body)})
        with patch.object(base, "_read_complete", side_effect=AssertionError("full scan forbidden")):
            feed.FeedWriter(
                events_path=crash_events, receipts_path=crash_receipts, epoch="recovered")
        recovered = json.loads(crash_receipts.read_text())
        check(recovered["event_id"] == feed._canonical_sha(body)
              and recovered["recovered_after_crash"] is True,
              "only the single possible unmatched tail event is recovered")

        ws = FakeWs(); feed._subscribe(ws)
        check(len(ws.sent) == 1 and ws.sent[0]["method"] == "logsSubscribe",
              "collector creates exactly one Pump logs subscription")

        state = feed.HeadState(); state.update(100, base_clock)
        check(feed._require_head(state, event_slot=90, received=base_clock + 1) == 100,
              "fresh head within the frozen slot-lag bound admits")
        refuses(lambda: feed._require_head(state, event_slot=67, received=base_clock + 1),
                "head lag above 32 slots refuses")
        refuses(lambda: feed._require_head(
            state, event_slot=90, received=base_clock + feed.MAX_HEAD_AGE_NANOS + 1),
            "stale independent head refuses")

        response = FakeResponse({"jsonrpc": "2.0", "id": 1, "result": 12345})
        check(feed._get_processed_slot(opener=lambda *_args, **_kwargs: response) == 12345,
              "processed-head RPC identity is exact")
        refuses(lambda: feed._get_processed_slot(opener=lambda *_args, **_kwargs:
                                                  FakeResponse({"id": 1, "result": 12345})),
                "malformed processed-head RPC refuses")

        with patch.object(feed, "HEALTH", health):
            row = feed.write_health(
                status="FRESH", epoch="epoch", observed_unix_nanos=base_clock,
                head_slot=100, event_slot=99, reason=None)
            loaded = feed.load_health(health, now=base_clock + 1, require_fresh=True)
            check(loaded["health_sha256"] == row["health_sha256"]
                  and loaded["head_slot_lag"] == 1,
                  "fresh health is hash-bound and executable-lag checked")
            tampered = dict(row); tampered["head_slot"] = 200
            health.write_text(json.dumps(tampered))
            refuses(lambda: feed.load_health(health, now=base_clock + 1),
                    "tampered feed health refuses")

        raw = json.dumps({
            "params": {"result": {"context": {"slot": 101},
                                    "value": {"signature": "raw-sig", "err": None,
                                              "logs": ["fixture"]}}}})
        process_events, process_receipts = root / "process-events", root / "process-receipts"
        process_writer = feed.FeedWriter(
            events_path=process_events, receipts_path=process_receipts, epoch="process")
        process_head = feed.HeadState(); process_head.update(102, base_clock)
        with (patch.object(base, "decode_pump_trades_from_logs",
                           return_value=[trade(1_000_000_000)]),
              patch.object(feed, "HEALTH", health)):
            count = feed._process_raw(
                raw, received=base_clock + 1, writer=process_writer,
                head_state=process_head)
        process_row = json.loads(process_events.read_text())
        check(count == 1 and process_row["source_received_unix_nanos"] == base_clock + 1,
              "raw frame receive clock is captured before decoder work and preserved")

    print(f"PAC V2.2 FEED SELFTEST: PASS — {CHECKS} checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
