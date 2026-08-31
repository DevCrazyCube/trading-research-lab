#!/usr/bin/env python3
"""Focused hostile controls for PAC V2.5's new formula and admission guards."""
from __future__ import annotations

from dataclasses import asdict, replace
import hashlib
import json
import pathlib
import tempfile

from .execution import ReserveState, RefusedExecution
from .pac_v2_feed import ClockedEvent
from . import pac_v25_detector as detector
from . import pac_v25_runner as runner


CHECKS = 0


def check(value: bool, label: str) -> None:
    global CHECKS
    if not value:
        raise AssertionError(label)
    CHECKS += 1
    print(f"[ok] {label}")


def state(quote: int, token: int | None = None) -> ReserveState:
    if token is None:
        token = 900_000_000_000_000 - quote * 100_000
    return ReserveState(virtual_quote=30_000_000_000 + quote,
                        virtual_token=1_000_000_000_000_000,
                        real_quote=quote, real_token=token, complete=False)


def event(index: int, pre: int, post: int, *, side: str, trader: str,
          base: int = 1_000_000_000_000) -> ClockedEvent:
    clock = base + index * 500_000_000
    return ClockedEvent(
        event_id=hashlib.sha256(f"{index}|{pre}|{post}|{side}|{trader}".encode()).hexdigest(),
        collector_epoch="epoch", mint="mint", trader=trader, signature=f"sig-{index}",
        slot=index + 1, side=side, source_received_unix_nanos=clock,
        materialized_unix_nanos=clock + 1, runner_seen_unix_nanos=clock + 2,
        pre_state=state(pre), post_state=state(post))


def passing() -> tuple[ClockedEvent, ...]:
    return (
        event(0, 1_200_000_000, 1_050_000_000, side="sell", trader="seller"),
        event(1, 1_050_000_000, 1_160_000_000, side="buy", trader="buyer-1"),
        event(2, 1_160_000_000, 1_260_000_000, side="buy", trader="buyer-2"),
        event(3, 1_260_000_000, 1_310_000_000, side="buy", trader="buyer-3"),
        event(4, 1_310_000_000, 1_330_000_000, side="buy", trader="buyer-3"),
        event(5, 1_330_000_000, 1_320_000_000, side="sell", trader="small-seller"),
    )


def main() -> int:
    events = passing()
    result = detector.qualify(events, processed_p90_nanos=1_000_000_000,
                              quote_input_lamports=100_000_000)
    check(result is not None, "paid overshoot surviving a full p90 qualifies")
    assert result is not None
    check(result.paid_floor_lamports == 1_300_000_000
          and result.reserve_cover_lamports == 1_300_000_000,
          "premise floor is max(pre-shock plus probe, six-times shock cover)")
    check(result.paid_recovery_index == 3 and result.dwell_nanos == 1_000_000_000,
          "dwell begins only after the extra probe was actually paid")
    check(result.runway_required_token_atoms > result.decision_tokens_out,
          "runway includes the entry and two observed latency depletion windows")

    mere_recovery = tuple(replace(item, post_state=state(1_290_000_000))
                          if item is events[-1] else item for item in events)
    check(detector.qualify(mere_recovery, processed_p90_nanos=1_000_000_000,
                           quote_input_lamports=100_000_000) is None,
          "full recovery without a surviving paid overshoot refuses")
    short = events[:-1]
    check(detector.qualify(short, processed_p90_nanos=1_000_000_000,
                           quote_input_lamports=100_000_000) is None,
          "sub-p90 paid dwell refuses")

    with tempfile.TemporaryDirectory() as directory:
        ledger = pathlib.Path(directory) / "ledger.jsonl"
        original_instrument = runner.core.INSTRUMENT
        runner.core.INSTRUMENT = runner.INSTRUMENT
        try:
            body = {"schema": runner.core.LEDGER_SCHEMA, "instrument_id": runner.INSTRUMENT,
                    "seal_sha256": "a" * 64, "calibration_sha256": "b" * 64,
                    "activation_unix_nanos": 1, "kind": "entry_filled", "mint": "mint"}
            body["event_id"] = runner.core._hash(body)
            ledger.write_text(json.dumps(body, sort_keys=True, separators=(",", ":")) + "\n")
            rows = runner._history(ledger)
            check({row["mint"] for row in rows if row["kind"] == "entry_filled"} == {"mint"},
                  "filled-mint lifetime guard is recovered from the hashed ledger")
            forged = dict(body); forged["mint"] = "other"
            ledger.write_text(json.dumps(forged) + "\n")
            try:
                runner._history(ledger)
            except RefusedExecution:
                refused = True
            else:
                refused = False
            check(refused, "tampered one-entry history refuses rather than resetting")
        finally:
            runner.core.INSTRUMENT = original_instrument

    def open_position(*, reserve_quote: int, entry_id: str = "c" * 64):
        quote_input = 100_000_000
        return runner.core.OpenPosition(
            mint="mint", token_atoms=2_000_000_000_000, quote_input_lamports=quote_input,
            entry_all_in_lamports=103_000_000, entry_curve_fee_lamports=800_000,
            entry_attempt_cost_lamports=160_720, ata_rent_lamports=2_039_280,
            entry_unix_nanos=10, peak_net_exit_lamports=0, failed_exit_cost_lamports=0,
            entry_id=entry_id, last_context_slot=10,
            last_state=asdict(state(reserve_quote)), last_refresh_unix_nanos=100)

    basic = {
        "seal_sha256": "a" * 64, "calibration_sha256": "b" * 64,
        "activation_unix_nanos": 1, "reaction_p90_nanos": 5,
        "pending_order": None,
    }
    unpriceable = open_position(reserve_quote=0)
    unpriceable.last_state = asdict(ReserveState(
        virtual_quote=1, virtual_token=1, real_quote=0, real_token=1, complete=False))
    transition_state = {**basic, "open_position": asdict(unpriceable)}
    original_instrument = runner.core.INSTRUMENT
    runner.core.INSTRUMENT = runner.INSTRUMENT
    try:
        rows = runner._v25_service_position(
            transition_state, object(), object(), now=101)
        check(transition_state["pending_order"]["venue"] == "PUMPSWAP"
              and rows[0]["action"] == "EXIT_VENUE_TRANSITION",
              "throttled unpriceable curve routes to PumpSwap instead of terminal full loss")
    finally:
        runner.core.INSTRUMENT = original_instrument

    with tempfile.TemporaryDirectory() as directory:
        ledger = pathlib.Path(directory) / "premise.jsonl"
        decision_id, entry_id = "d" * 64, "e" * 64
        rows = [
            {"schema": 2, "instrument_id": runner.INSTRUMENT, "seal_sha256": "a" * 64,
             "calibration_sha256": "b" * 64, "activation_unix_nanos": 1,
             "kind": "entry_decision", "mint": "mint", "decision_id": decision_id,
             "reserve_cover_lamports": 1_300_000_000},
            {"schema": 2, "instrument_id": runner.INSTRUMENT, "seal_sha256": "a" * 64,
             "calibration_sha256": "b" * 64, "activation_unix_nanos": 1,
             "kind": "entry_filled", "mint": "mint", "decision_id": decision_id,
             "entry_id": entry_id},
        ]
        for row in rows:
            row["event_id"] = runner.core._hash(row)
        ledger.write_text("".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n"
                                  for row in rows))
        previous_ledger, original_instrument = runner._ACTIVE_LEDGER, runner.core.INSTRUMENT
        runner._ACTIVE_LEDGER = ledger; runner.core.INSTRUMENT = runner.INSTRUMENT
        premise_state = {**basic, "open_position": asdict(open_position(
            reserve_quote=1_250_000_000, entry_id=entry_id))}
        try:
            exit_rows = runner._v25_service_position(
                premise_state, object(), object(), now=101)
            check(premise_state["pending_order"]["action"] == "EXIT_PREMISE_BREAK"
                  and exit_rows[0]["premise_floor_lamports"] == 1_300_000_000,
                  "reserve-floor erosion creates an executable premise-break sell")
        finally:
            runner._ACTIVE_LEDGER = previous_ledger
            runner.core.INSTRUMENT = original_instrument

    check("EXIT_PREMISE_BREAK" in {item.value for item in runner.pac_v25_policy.ExitAction},
          "premise-break is a typed executable exit action")
    print(f"PAC V2.5 SELFTEST: PASS — {CHECKS} checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
