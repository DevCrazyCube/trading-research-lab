#!/usr/bin/env python3
"""Negative-control and end-to-end selftest for the PAC V2 challenger."""
from __future__ import annotations

import hashlib
import json
import pathlib
import struct
import tempfile
import time

from .execution import ReserveState, RefusedExecution
from .pac_v2_calibration import Calibration, CalibrationRefused, load as load_calibration
from . import pac_v2_detector as detector
from . import pac_v2_feed as feed
from . import pac_v2_manifest as manifest
from . import pac_v2_policy as policy
from . import pac_v2_runner as runner
from . import pac_v2_snapshot as snapshot


CHECKS = 0


def check(condition: bool, label: str) -> None:
    global CHECKS
    if not condition:
        raise AssertionError(label)
    CHECKS += 1
    print(f"[ok] {label}")


def refuses(exc_type, fn, label: str) -> None:
    try:
        fn()
    except exc_type:
        check(True, label)
    else:
        raise AssertionError(label)


def sha(value: object) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


def state(real_quote: int) -> ReserveState:
    return ReserveState(30_000_000_000 + real_quote, 1_000_000_000_000_000,
                        real_quote, 720_100_000_000_000, False)


def event(index: int, pre_quote: int, post_quote: int, *, base: int,
          trader: str, side: str) -> feed.ClockedEvent:
    source = base + index * 1_000_000_000
    return feed.ClockedEvent(
        event_id=hashlib.sha256(f"event-{index}".encode()).hexdigest(), collector_epoch="epoch",
        mint="mint", trader=trader, signature=f"sig-{index}", slot=index, side=side,
        source_received_unix_nanos=source, materialized_unix_nanos=source + 10,
        runner_seen_unix_nanos=source + 20, pre_state=state(pre_quote), post_state=state(post_quote))


def pac_events(base: int) -> tuple[feed.ClockedEvent, ...]:
    # Recovery 2 is faster, then three observed buyer addresses establish post-recovery breadth.
    return (
        event(0, 1_000_000_000, 900_000_000, base=base, trader="seller1", side="sell"),
        event(2, 900_000_000, 1_000_000_000, base=base, trader="buyer0", side="buy"),
        event(3, 1_000_000_000, 900_000_000, base=base, trader="seller2", side="sell"),
        event(4, 900_000_000, 1_000_000_000, base=base, trader="buyer1", side="buy"),
        event(5, 1_000_000_000, 1_010_000_000, base=base, trader="buyer2", side="buy"),
        event(6, 1_010_000_000, 1_020_000_000, base=base, trader="buyer3", side="buy"),
    )


def calibration_row(index: int, reaction: int) -> dict:
    decision = 1_000_000_000_000 + index * 2_000_000_000
    raw = {"transaction": f"raw-{index}", "land_slot": index + 1}
    body = {
        "schema": 1, "instrument_id": "AFTERSHOCK_PAC_V2",
        "transaction_signature": f"tx-{index}", "outcome": "LANDED",
        "clocks": {"decision_unix_nanos": decision, "build_start_unix_nanos": decision + 1,
                   "sign_done_unix_nanos": decision + 2, "send_start_unix_nanos": decision + 3,
                   "send_ack_unix_nanos": decision + 4,
                   "land_observed_unix_nanos": decision + reaction},
        "raw_evidence": raw, "raw_evidence_sha256": sha(raw),
    }
    return {**body, "sample_id": sha(body)}


class FakeSnapshots:
    def __init__(self, states: list[ReserveState]):
        self.states = list(states); self.calls = []

    def capture(self, mint: str, modeled_target_unix_nanos: int) -> snapshot.LandingSnapshot:
        self.calls.append((mint, modeled_target_unix_nanos))
        if not self.states:
            raise AssertionError("unexpected snapshot")
        return snapshot.LandingSnapshot(
            mint=mint, bonding_curve="curve", modeled_target_unix_nanos=modeled_target_unix_nanos,
            request_started_unix_nanos=modeled_target_unix_nanos,
            response_received_unix_nanos=modeled_target_unix_nanos + 1,
            context_slot=len(self.calls), state=self.states.pop(0), endpoint_scheme_host="https://rpc",
            raw_response_sha256=hashlib.sha256(f"snapshot-{len(self.calls)}".encode()).hexdigest())


class UnavailableSnapshots:
    def capture(self, mint: str, modeled_target_unix_nanos: int):
        raise snapshot.SnapshotUnavailable("synthetic RPC outage")


def append_runner_events(events_path: pathlib.Path, receipts_path: pathlib.Path,
                         events: tuple[feed.ClockedEvent, ...]) -> None:
    for item in events:
        body = {"schema": feed.SCHEMA, "source": feed.SOURCE,
                "collector_epoch": item.collector_epoch, "mint": item.mint,
                "trader": item.trader, "signature": item.signature, "slot": item.slot,
                "side": item.side, "source_received_unix_nanos": item.source_received_unix_nanos,
                "pre_state": runner.asdict(item.pre_state), "post_state": runner.asdict(item.post_state)}
        event_id = feed._canonical_sha(body)
        feed._append(events_path, {**body, "event_id": event_id})
        receipt = {"schema": feed.SCHEMA, "event_id": event_id,
                   "materialized_unix_nanos": item.materialized_unix_nanos}
        feed._append(receipts_path, {**receipt, "receipt_sha256": feed._canonical_sha(receipt)})


def main() -> int:
    with tempfile.TemporaryDirectory() as raw_tmp:
        tmp = pathlib.Path(raw_tmp)

        rows = [calibration_row(i, (i + 1) * 1_000_000) for i in range(100)]
        calibration_path = tmp / "calibration.jsonl"
        calibration_path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))
        artifact_sha = hashlib.sha256(calibration_path.read_bytes()).hexdigest()
        calibrated = load_calibration(calibration_path, expected_sha256=artifact_sha)
        check(calibrated.landed_samples == 100 and calibrated.reaction_p90_nanos == 90_000_000,
              "100 authentic-shaped samples derive exact nearest-rank p90")
        short_path = tmp / "short.jsonl"
        short_path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows[:99]))
        refuses(CalibrationRefused, lambda: load_calibration(
            short_path, expected_sha256=hashlib.sha256(short_path.read_bytes()).hexdigest()),
            "99 landed calibration samples REFUSE")
        tampered = calibration_path.read_bytes() + b" "
        tampered_path = tmp / "tampered.jsonl"; tampered_path.write_bytes(tampered)
        refuses(CalibrationRefused, lambda: load_calibration(
            tampered_path, expected_sha256=artifact_sha), "calibration byte tamper REFUSES")

        base = time.time_ns() - 10_000_000_000
        events = pac_events(base)
        qualified = detector.qualify(events, reaction_p90_nanos=1_000_000_000,
                                     quote_input_lamports=50_000_000)
        check(qualified is not None and qualified.buyer_breadth == 3,
              "PAC plus p90 dwell, breadth and 6x shock cover qualifies")
        narrow = tuple(item for item in events if item.trader != "buyer3")
        check(detector.qualify(narrow, reaction_p90_nanos=1_000_000_000,
                              quote_input_lamports=50_000_000) is None,
              "fewer than three observed dwell buyers refuses entry")
        eroded = list(events)
        eroded[-1] = event(6, 1_010_000_000, 990_000_000, base=base,
                           trader="buyer3", side="buy")
        check(detector.qualify(tuple(eroded), reaction_p90_nanos=1_000_000_000,
                              quote_input_lamports=50_000_000) is None,
              "post-recovery reserve erosion refuses entry")
        check(detector.qualify(events, reaction_p90_nanos=3_000_000_000,
                              quote_input_lamports=50_000_000) is None,
              "insufficient measured-p90 dwell refuses entry")

        position = policy.Position(1, 50_000_000, 1_000, peak_net_exit_lamports=1_000_000_000)
        horizon = policy.decide(position, now_unix_nanos=1_000 + policy.MAX_HOLD_NANOS,
                                net_exit_lamports=1, real_quote_lamports=1)
        check(horizon.action == policy.ExitAction.EXIT_HORIZON,
              "absolute horizon wins over simultaneous capacity and trail")
        unavailable = policy.decide(position, now_unix_nanos=1_000 + policy.MAX_HOLD_NANOS,
                                    net_exit_lamports=None, real_quote_lamports=None)
        check(unavailable.action == policy.ExitAction.UNEXITABLE_FULL_LOSS,
              "unavailable horizon releases as a full loss")

        # Pinned exact account decoder: wrong schema and non-SOL quote both refuse.
        account = (snapshot._DISCRIMINATOR
                   + struct.pack("<5Q", 1_000_000_000_000_000, 31_000_000_000,
                                 720_100_000_000_000, 1_000_000_000, 1_000_000_000_000_000)
                   + b"\x00" + b"\x01" * 32 + b"\x00\x00"
                   + snapshot._b58decode(snapshot._ACCOUNT_SOL_QUOTE_MINT))
        decoded = snapshot._decode_state(account)
        check(decoded.real_quote == 1_000_000_000 and not decoded.complete,
              "exact 115-byte native-SOL account snapshot decodes")
        refuses(RefusedExecution, lambda: snapshot._decode_state(account + b"\x00"),
                "account layout suffix drift REFUSES")

        # Incremental feed admits each authenticated event once and refuses an orphan receipt.
        events_path = tmp / "events.jsonl"; receipts_path = tmp / "receipts.jsonl"
        append_runner_events(events_path, receipts_path, events[:1])
        cursor = feed.Cursor()
        first = feed.consume(cursor, events_path=events_path, receipts_path=receipts_path,
                             runner_seen_unix_nanos=time.time_ns())
        check(len(first) == 1 and feed.consume(
            cursor, events_path=events_path, receipts_path=receipts_path,
            runner_seen_unix_nanos=time.time_ns()) == [],
            "durable byte cursor consumes an authenticated row exactly once")
        orphan = {"schema": feed.SCHEMA, "event_id": "f" * 64,
                  "materialized_unix_nanos": time.time_ns()}
        feed._append(receipts_path, {**orphan, "receipt_sha256": feed._canonical_sha(orphan)})
        refuses(RefusedExecution, lambda: feed.consume(
            cursor, events_path=events_path, receipts_path=receipts_path,
            runner_seen_unix_nanos=time.time_ns()), "orphan materialization receipt REFUSES")

        # Full runner: no later trade is appended after entry or after the horizon decision.
        run_events = tmp / "run_events.jsonl"; run_receipts = tmp / "run_receipts.jsonl"
        state_path = tmp / "runner_state.json"; ledger_path = tmp / "runner_ledger.jsonl"
        proof = runner.RuntimeProof("a" * 64, base - 1_000_000_000,
                                    Calibration("b" * 64, 100, 0, 1_000_000,
                                                base - 3_000_000_000, base - 2_000_000_000))
        fake = FakeSnapshots([state(1_020_000_000), state(1_020_000_000)])
        initialized = runner.run_once(
            proof, fake, now_unix_nanos=base, quote_input_lamports=50_000_000,
            state_path=state_path, ledger_path=ledger_path, events_path=run_events,
            receipts_path=run_receipts, initialize_at_eof=False)
        check(initialized["status"] == "INITIALIZED_NO_BACKFILL", "runner initializes without backfill")
        append_runner_events(run_events, run_receipts, events)
        decision_now = time.time_ns()
        decided = runner.run_once(
            proof, fake, now_unix_nanos=decision_now, quote_input_lamports=50_000_000,
            state_path=state_path, ledger_path=ledger_path, events_path=run_events,
            receipts_path=run_receipts, initialize_at_eof=False)
        check(decided["pending"] == 1 and decided["new_events"] == len(events),
              "entry decision is incremental and persists a future snapshot target")
        entered = runner.run_once(
            proof, fake, now_unix_nanos=decision_now + 2_000_000,
            quote_input_lamports=50_000_000, state_path=state_path, ledger_path=ledger_path,
            events_path=run_events, receipts_path=run_receipts, initialize_at_eof=False)
        check(entered["open"] == 1 and entered["new_events"] == 0 and len(fake.calls) == 1,
              "entry fills after target from account snapshot without another trade")
        stored = json.loads(state_path.read_text()); entry_time = stored["open_position"]["entry_unix_nanos"]
        horizon_now = entry_time + policy.MAX_HOLD_NANOS
        exit_decided = runner.run_once(
            proof, fake, now_unix_nanos=horizon_now, quote_input_lamports=50_000_000,
            state_path=state_path, ledger_path=ledger_path, events_path=run_events,
            receipts_path=run_receipts, initialize_at_eof=False)
        check(exit_decided["pending"] == 1 and exit_decided["new_events"] == 0,
              "wall-clock horizon decides an exit with no later trade")
        resolved = runner.run_once(
            proof, fake, now_unix_nanos=horizon_now + 2_000_000,
            quote_input_lamports=50_000_000, state_path=state_path, ledger_path=ledger_path,
            events_path=run_events, receipts_path=run_receipts, initialize_at_eof=False)
        ledger_rows = [json.loads(line) for line in ledger_path.read_text().splitlines()]
        check(resolved["open"] == resolved["pending"] == 0
              and sum(row["kind"] == "resolved" for row in ledger_rows) == 1
              and len(fake.calls) == 2,
              "horizon exit snapshots and resolves without a post-decision trade")
        check(runner.run_once(
            proof, fake, now_unix_nanos=horizon_now + 3_000_000,
            quote_input_lamports=50_000_000, state_path=state_path, ledger_path=ledger_path,
            events_path=run_events, receipts_path=run_receipts,
            initialize_at_eof=False)["new_events"] == 0,
            "restart cursor does not replay the signal")

        # A horizon snapshot outage has a bounded conservative terminal state, not an immortal lock.
        timeout_state_path = tmp / "timeout_state.json"; timeout_ledger = tmp / "timeout_ledger.jsonl"
        timeout_state = runner._new_state(proof, event_offset=0, receipt_offset=0)
        healthy = state(1_020_000_000)
        entry_accounting = runner.kernel_accounting(
            healthy, runner.OrderIntent(runner.IntentKind.EXACT_QUOTE_BUY, 50_000_000, 1))
        all_in = -entry_accounting["wallet_delta_lamports"]
        timeout_position = runner.OpenPosition(
            mint="timeout-mint", token_atoms=entry_accounting["out_amount"],
            quote_input_lamports=50_000_000,
            entry_all_in_lamports=all_in,
            entry_curve_fee_lamports=entry_accounting["curve_fee_lamports"],
            entry_attempt_cost_lamports=entry_accounting["attempt_cost_lamports"],
            ata_rent_lamports=entry_accounting["ata_rent_lamports"],
            entry_unix_nanos=base, peak_net_exit_lamports=0, failed_exit_cost_lamports=0,
            entry_id="c" * 64, last_state=runner.asdict(healthy))
        timeout_state["open_position"] = runner.asdict(timeout_position)
        runner._atomic_write(timeout_state_path, timeout_state)
        horizon_clock = base + policy.MAX_HOLD_NANOS
        runner.run_once(proof, UnavailableSnapshots(), now_unix_nanos=horizon_clock,
                        quote_input_lamports=50_000_000, state_path=timeout_state_path,
                        ledger_path=timeout_ledger, events_path=tmp / "none-events",
                        receipts_path=tmp / "none-receipts", initialize_at_eof=False)
        timeout_pending = json.loads(timeout_state_path.read_text())["pending_order"]
        terminal_clock = timeout_pending["target_unix_nanos"] + runner.SNAPSHOT_TIMEOUT_NANOS
        timed_out = runner.run_once(
            proof, UnavailableSnapshots(), now_unix_nanos=terminal_clock,
            quote_input_lamports=50_000_000, state_path=timeout_state_path,
            ledger_path=timeout_ledger, events_path=tmp / "none-events",
            receipts_path=tmp / "none-receipts", initialize_at_eof=False)
        timeout_rows = [json.loads(line) for line in timeout_ledger.read_text().splitlines()]
        check(timed_out["open"] == timed_out["pending"] == 0
              and timeout_rows[-1]["reason"] == "HORIZON_SNAPSHOT_TIMEOUT"
              and timeout_rows[-1]["unexitable_full_loss"] is True,
              "30-second horizon snapshot timeout books full loss and releases lock")

        tampered_state = json.loads(state_path.read_text())
        tampered_state["calibration_sha256"] = "0" * 64
        runner._atomic_write(tmp / "tampered_state.json", tampered_state)
        refuses(RefusedExecution, lambda: runner.run_once(
            proof, fake, now_unix_nanos=horizon_now + 4_000_000,
            quote_input_lamports=50_000_000, state_path=tmp / "tampered_state.json",
            ledger_path=tmp / "tampered_ledger.jsonl", events_path=run_events,
            receipts_path=run_receipts, initialize_at_eof=False),
            "runtime binding tamper REFUSES before feed or pricing")

        check(manifest.anchor_status() == "ANCHORED",
              "committed V2 dependency closure and seal re-anchor exactly")
        refuses(RefusedExecution, manifest.load_runtime_proof,
                "anchored runtime still refuses absent calibrated activation")

    print(f"PAC V2 SELFTEST: PASS — {CHECKS} checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
