#!/usr/bin/env python3
"""Isolation and causal end-to-end controls for the PAC V2.1 paper runner."""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import inspect
import json
import pathlib
import tempfile

from .execution import ReserveState, RefusedExecution
from . import pac_v21_calibration as calibration
from . import pac_v2_feed as feed
from . import pac_v2_policy as policy
from . import pac_v2_runner as v2_core
from . import pac_v21_runner as runner


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


def state(real_quote: int) -> ReserveState:
    return ReserveState(
        virtual_quote=30_000_000_000 + real_quote,
        virtual_token=1_000_000_000_000_000,
        real_quote=real_quote,
        real_token=720_100_000_000_000,
        complete=False,
    )


def event(index: int, pre_quote: int, post_quote: int, *, base: int,
          side: str, trader: str) -> feed.ClockedEvent:
    source = base + index * 500_000_000
    return feed.ClockedEvent(
        event_id=hashlib.sha256(f"v21-{index}".encode()).hexdigest(),
        collector_epoch="v21-epoch", mint="v21-mint", trader=trader,
        signature=f"v21-signature-{index}", slot=index + 10, side=side,
        source_received_unix_nanos=source,
        materialized_unix_nanos=source + 1,
        runner_seen_unix_nanos=source + 2,
        pre_state=state(pre_quote), post_state=state(post_quote),
    )


def passing(base: int) -> tuple[feed.ClockedEvent, ...]:
    return (
        event(0, 1_200_000_000, 1_050_000_000, base=base,
              side="sell", trader="seller"),
        event(1, 1_050_000_000, 1_120_000_000, base=base,
              side="buy", trader="buyer-1"),
        event(2, 1_120_000_000, 1_200_000_000, base=base,
              side="buy", trader="buyer-2"),
        event(3, 1_200_000_000, 1_240_000_000, base=base,
              side="buy", trader="buyer-3"),
        event(4, 1_240_000_000, 1_260_000_000, base=base,
              side="buy", trader="buyer-3"),
    )


def append_events(events_path: pathlib.Path, receipts_path: pathlib.Path,
                  events: tuple[feed.ClockedEvent, ...]) -> None:
    for item in events:
        body = {
            "schema": feed.SCHEMA, "source": feed.SOURCE,
            "collector_epoch": item.collector_epoch, "mint": item.mint,
            "trader": item.trader, "signature": item.signature, "slot": item.slot,
            "side": item.side,
            "source_received_unix_nanos": item.source_received_unix_nanos,
            "continuity_proven": True,
            "pre_state": asdict(item.pre_state), "post_state": asdict(item.post_state),
        }
        event_id = feed._canonical_sha(body)
        feed._append(events_path, {**body, "event_id": event_id})
        receipt = {
            "schema": feed.SCHEMA, "event_id": event_id,
            "materialized_unix_nanos": item.materialized_unix_nanos,
            "recovered_after_crash": False,
        }
        feed._append(receipts_path, {
            **receipt, "receipt_sha256": feed._canonical_sha(receipt)})


def fake_calibration(base: int) -> calibration.Calibration:
    return calibration.Calibration(
        artifact_sha256="b" * 64, attestation_sha256="c" * 64,
        campaign_sha256="d" * 64, campaign_id="e" * 64,
        processed_samples=100, failed_samples=0,
        processed_p90_nanos=1_000_000_000,
        first_decision_unix_nanos=base - 5_000_000_000,
        last_processed_unix_nanos=base - 4_000_000_000,
        last_attested_unix_nanos=base - 3_000_000_000,
    )


class Snapshots:
    def __init__(self, reserves: list[ReserveState]):
        self.reserves = list(reserves)
        self.calls = 0

    def capture(self, mint: str, modeled_target_unix_nanos: int,
                minimum_context_slot: int):
        if not self.reserves:
            raise AssertionError("unexpected snapshot")
        self.calls += 1
        return v2_core.LandingSnapshot(
            mint=mint, bonding_curve="curve",
            modeled_target_unix_nanos=modeled_target_unix_nanos,
            minimum_context_slot=minimum_context_slot,
            request_started_unix_nanos=modeled_target_unix_nanos,
            response_received_unix_nanos=modeled_target_unix_nanos + 1,
            context_slot=max(minimum_context_slot, 100 + self.calls),
            state=self.reserves.pop(0), endpoint_scheme_host="https://rpc.invalid",
            raw_response_sha256=hashlib.sha256(f"v21-snapshot-{self.calls}".encode()).hexdigest(),
        )


def main() -> int:
    base = 1_900_000_000_000_000_000
    calibrated = fake_calibration(base)
    proof = runner.RuntimeProof("a" * 64, base - 2_000_000_000, calibrated)
    refuses(lambda: runner.RuntimeProof("a" * 64, base - 4_000_000_000, calibrated),
            "activation at/before attested processed calibration refuses")
    check("now" not in inspect.signature(runner.run_once).parameters,
          "production runner exposes no caller-supplied clock")

    with tempfile.TemporaryDirectory(prefix="pac_v21_runner_") as temporary:
        root = pathlib.Path(temporary)
        events_path, receipts_path = root / "events.jsonl", root / "receipts.jsonl"
        state_path, ledger_path = root / "state.json", root / "ledger.jsonl"
        snapshots = Snapshots([state(1_260_000_000), state(1_260_000_000)])
        original_instrument, original_detector = v2_core.INSTRUMENT, v2_core.detector

        initialized = runner._run_once_at(
            proof, snapshots, now=base - 1_000_000_000,
            quote_input_lamports=100_000_000,
            state_path=state_path, ledger_path=ledger_path,
            events_path=events_path, receipts_path=receipts_path,
            initialize_at_eof=False)
        check(initialized["status"] == "INITIALIZED_NO_BACKFILL",
              "V2.1 initializes an isolated no-backfill state")

        events = passing(base)
        append_events(events_path, receipts_path, events)
        decision_now = base + 3_000_000_000
        decided = runner._run_once_at(
            proof, snapshots, now=decision_now, quote_input_lamports=100_000_000,
            state_path=state_path, ledger_path=ledger_path,
            events_path=events_path, receipts_path=receipts_path,
            initialize_at_eof=False)
        stored = json.loads(state_path.read_text())
        rows = [json.loads(line) for line in ledger_path.read_text().splitlines()]
        decision = rows[-1]
        check(decided["pending"] == 1
              and stored["instrument_id"] == runner.INSTRUMENT
              and stored["reaction_p90_nanos"] == calibrated.processed_p90_nanos,
              "processed p90 creates a future V2.1 entry target in isolated state")
        check(decision["instrument_id"] == runner.INSTRUMENT
              and decision["buyer_breadth"] == 3
              and decision["largest_observed_sell_lamports"] == 150_000_000,
              "ledger binds the V2.1 single-shock evidence, never the V2 formula")

        entered = runner._run_once_at(
            proof, snapshots, now=stored["pending_order"]["target_unix_nanos"] + 1,
            quote_input_lamports=100_000_000,
            state_path=state_path, ledger_path=ledger_path,
            events_path=events_path, receipts_path=receipts_path,
            initialize_at_eof=False)
        stored = json.loads(state_path.read_text())
        check(entered["open"] == 1 and stored["open_position"] is not None,
              "entry fills only from a strictly later account snapshot")

        horizon_now = stored["open_position"]["entry_unix_nanos"] + policy.MAX_HOLD_NANOS
        exit_decision = runner._run_once_at(
            proof, snapshots, now=horizon_now, quote_input_lamports=100_000_000,
            state_path=state_path, ledger_path=ledger_path,
            events_path=events_path, receipts_path=receipts_path,
            initialize_at_eof=False)
        stored = json.loads(state_path.read_text())
        check(exit_decision["pending"] == 1
              and stored["pending_order"]["action"] == policy.ExitAction.EXIT_HORIZON.value,
              "unchanged 12-minute horizon creates a separate causal exit decision")

        resolved = runner._run_once_at(
            proof, snapshots, now=stored["pending_order"]["target_unix_nanos"] + 1,
            quote_input_lamports=100_000_000,
            state_path=state_path, ledger_path=ledger_path,
            events_path=events_path, receipts_path=receipts_path,
            initialize_at_eof=False)
        rows = [json.loads(line) for line in ledger_path.read_text().splitlines()]
        check(resolved["open"] == resolved["pending"] == 0
              and rows[-1]["kind"] == "resolved"
              and rows[-1]["instrument_id"] == runner.INSTRUMENT,
              "V2.1 resolves through the inherited all-cost exit path and releases the lock")
        check(v2_core.INSTRUMENT == original_instrument and v2_core.detector is original_detector,
              "every V2.1 call restores the frozen V2 module globals")

    print(f"PAC V2.1 RUNNER SELFTEST: PASS — {CHECKS} checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
