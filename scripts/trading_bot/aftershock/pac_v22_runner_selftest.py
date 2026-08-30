#!/usr/bin/env python3
"""Isolation, feed-health and causal controls for the PAC V2.2 runner adapter."""
from __future__ import annotations

from dataclasses import asdict
import json
import pathlib
import tempfile
import time
from unittest.mock import patch

from .execution import RefusedExecution
from . import pac_v2_policy as policy
from . import pac_v2_runner as core
from . import pac_v21_runner_selftest as fixtures
from . import pac_v22_feed as feed
from . import pac_v22_runner as runner


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


def append_events(events_path: pathlib.Path, receipts_path: pathlib.Path, events) -> None:
    for item in events:
        body = {
            "schema": feed.SCHEMA, "source": feed.SOURCE,
            "collector_epoch": item.collector_epoch, "mint": item.mint,
            "trader": item.trader, "signature": item.signature, "slot": item.slot,
            "side": item.side, "source_received_unix_nanos": item.source_received_unix_nanos,
            "continuity_proven": True,
            "pre_state": asdict(item.pre_state), "post_state": asdict(item.post_state),
        }
        event_id = feed._canonical_sha(body)
        core.feed._append(events_path, {**body, "event_id": event_id})
        receipt = {"schema": feed.SCHEMA, "event_id": event_id,
                   "materialized_unix_nanos": item.materialized_unix_nanos,
                   "recovered_after_crash": False}
        core.feed._append(receipts_path, {
            **receipt, "receipt_sha256": feed._canonical_sha(receipt)})


def main() -> int:
    base = time.time_ns() + 20_000_000_000
    calibrated = fixtures.fake_calibration(base)
    proof = runner.RuntimeProof("a" * 64, base - 2_000_000_000, calibrated)
    refuses(lambda: runner.RuntimeProof("a" * 64, base - 4_000_000_000, calibrated),
            "activation at/before calibration refuses")

    with tempfile.TemporaryDirectory(prefix="pac_v22_runner_") as td:
        root = pathlib.Path(td)
        events_path, receipts_path = root / "events", root / "receipts"
        state_path, ledger_path = root / "state", root / "ledger"
        health_path = root / "health"
        snapshots = fixtures.Snapshots([
            fixtures.state(1_260_000_000), fixtures.state(1_260_000_000)])
        originals = core.INSTRUMENT, core.detector, core.feed

        initialized = runner._run_once_at(
            proof, snapshots, now=base - 1_000_000_000,
            quote_input_lamports=100_000_000, state_path=state_path,
            ledger_path=ledger_path, events_path=events_path,
            receipts_path=receipts_path, initialize_at_eof=False)
        check(initialized["status"] == "INITIALIZED_NO_BACKFILL",
              "V2.2 initializes an isolated no-backfill state")

        append_events(events_path, receipts_path, fixtures.passing(base))
        decision_now = base + 3_000_000_000
        with (patch.object(feed, "HEALTH", health_path),
              patch.object(feed.time, "time_ns", return_value=decision_now)):
            feed.write_health(
                status="DEGRADED", epoch="fixture", observed_unix_nanos=decision_now,
                head_slot=100, event_slot=None, reason="fixture lag")
            refuses(lambda: runner._run_once_at(
                proof, snapshots, now=decision_now, quote_input_lamports=100_000_000,
                state_path=state_path, ledger_path=ledger_path, events_path=events_path,
                receipts_path=receipts_path, initialize_at_eof=False),
                "degraded feed refuses a new entry decision")

            feed.write_health(
                status="FRESH", epoch="fixture", observed_unix_nanos=decision_now,
                head_slot=100, event_slot=99, reason=None)
            decided = runner._run_once_at(
                proof, snapshots, now=decision_now, quote_input_lamports=100_000_000,
                state_path=state_path, ledger_path=ledger_path, events_path=events_path,
                receipts_path=receipts_path, initialize_at_eof=False)
        stored = json.loads(state_path.read_text())
        check(decided["pending"] == 1 and stored["instrument_id"] == runner.INSTRUMENT,
              "fresh low-lag feed admits the unchanged V2.1 signal into V2.2")

        entered = runner._run_once_at(
            proof, snapshots, now=stored["pending_order"]["target_unix_nanos"] + 1,
            quote_input_lamports=100_000_000, state_path=state_path,
            ledger_path=ledger_path, events_path=events_path,
            receipts_path=receipts_path, initialize_at_eof=False)
        stored = json.loads(state_path.read_text())
        check(entered["open"] == 1, "causal post-target account snapshot fills only on paper")

        horizon = stored["open_position"]["entry_unix_nanos"] + policy.MAX_HOLD_NANOS
        with (patch.object(feed, "HEALTH", health_path),
              patch.object(feed.time, "time_ns", return_value=horizon)):
            feed.write_health(
                status="DEGRADED", epoch="fixture", observed_unix_nanos=horizon,
                head_slot=200, event_slot=None, reason="fixture outage")
            exited = runner._run_once_at(
                proof, snapshots, now=horizon, quote_input_lamports=100_000_000,
                state_path=state_path, ledger_path=ledger_path, events_path=events_path,
                receipts_path=receipts_path, initialize_at_eof=False)
        stored = json.loads(state_path.read_text())
        check(exited["pending"] == 1
              and stored["pending_order"]["action"] == policy.ExitAction.EXIT_HORIZON.value,
              "feed degradation cannot block an open-position horizon exit decision")
        check((core.INSTRUMENT, core.detector, core.feed) == originals,
              "every V2.2 call restores all frozen V2 core globals")

    print(f"PAC V2.2 RUNNER SELFTEST: PASS — {CHECKS} checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
