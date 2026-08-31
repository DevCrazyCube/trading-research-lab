#!/usr/bin/env python3
"""Hostile controls for PAC V2.6's one-change all-cost risk budget."""
from __future__ import annotations

from dataclasses import asdict
import json
import pathlib
import tempfile

from .execution import RefusedExecution, ReserveState
from . import pac_v26_policy as policy
from . import pac_v26_runner as runner


CHECKS = 0


def check(value: bool, label: str) -> None:
    global CHECKS
    if not value:
        raise AssertionError(label)
    CHECKS += 1
    print(f"[ok] {label}")


def reserve(quote: int = 2_000_000_000) -> ReserveState:
    return ReserveState(virtual_quote=32_000_000_000,
                        virtual_token=1_000_000_000_000_000,
                        real_quote=quote, real_token=900_000_000_000_000,
                        complete=False)


def position(*, entry_id: str = "e" * 64) -> runner.core.OpenPosition:
    return runner.core.OpenPosition(
        mint="mint", token_atoms=2_000_000_000_000,
        quote_input_lamports=97_000_000, entry_all_in_lamports=100_000_000,
        entry_curve_fee_lamports=855_720, entry_attempt_cost_lamports=105_000,
        ata_rent_lamports=2_039_280, entry_unix_nanos=10,
        peak_net_exit_lamports=120_000_000, failed_exit_cost_lamports=0,
        entry_id=entry_id, last_context_slot=10,
        last_state=asdict(reserve()), last_refresh_unix_nanos=100)


def write_book(path: pathlib.Path, entry_id: str, floor: int = 1_000_000_000) -> None:
    decision_id = "d" * 64
    rows = [
        {"schema": 2, "instrument_id": runner.INSTRUMENT, "seal_sha256": "a" * 64,
         "calibration_sha256": "b" * 64, "activation_unix_nanos": 1,
         "kind": "entry_decision", "mint": "mint", "decision_id": decision_id,
         "reserve_cover_lamports": floor},
        {"schema": 2, "instrument_id": runner.INSTRUMENT, "seal_sha256": "a" * 64,
         "calibration_sha256": "b" * 64, "activation_unix_nanos": 1,
         "kind": "entry_filled", "mint": "mint", "decision_id": decision_id,
         "entry_id": entry_id},
    ]
    for row in rows:
        row["event_id"] = runner.core._hash(row)
    path.write_text("".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n"
                            for row in rows))


def main() -> int:
    p = position()
    equality_net = (p.entry_all_in_lamports - p.ata_rent_lamports
                    + runner.ATA_CLOSE_GAS_LAMPORTS
                    - policy.RISK_BUDGET_NUM * p.entry_all_in_lamports
                    // policy.RISK_BUDGET_DEN)
    check(runner._settlement_num(p, equality_net) == -8_000_000,
          "all-cost mark reconciles entry, failed attempts, rent refund, and close gas")
    check(runner._risk_budget_breached(p, equality_net),
          "exactly minus eight percent breaches the frozen risk budget")
    check(not runner._risk_budget_breached(p, equality_net + 1),
          "one lamport above the exact boundary does not breach")
    p.failed_exit_cost_lamports = 105_000
    check(runner._risk_budget_breached(p, equality_net + 1),
          "a prior failed-exit cost is included in the all-cost risk mark")
    p.failed_exit_cost_lamports = 0

    with tempfile.TemporaryDirectory() as directory:
        ledger = pathlib.Path(directory) / "ledger.jsonl"
        write_book(ledger, p.entry_id)
        previous_ledger = runner._ACTIVE_LEDGER
        original_accounting = runner.kernel_accounting
        original_service = runner._ORIGINAL_SERVICE
        original_instrument = runner.core.INSTRUMENT
        runner._ACTIVE_LEDGER = ledger
        runner.core.INSTRUMENT = runner.INSTRUMENT
        runner.kernel_accounting = lambda *_args, **_kwargs: {
            "out_amount": equality_net + 1_000_000,
            "wallet_delta_lamports": equality_net,
        }
        state = {
            "schema": 2, "instrument_id": runner.INSTRUMENT,
            "seal_sha256": "a" * 64, "calibration_sha256": "b" * 64,
            "activation_unix_nanos": 1, "reaction_p90_nanos": 5,
            "pending_order": None, "open_position": asdict(p),
        }
        try:
            rows = runner._service_position(state, object(), object(), now=101)
            check(rows[0]["action"] == "EXIT_RISK_BUDGET"
                  and state["pending_order"]["action"] == "EXIT_RISK_BUDGET",
                  "breach creates a typed full-position executable exit")
            check(state["pending_order"]["amount"] == p.token_atoms
                  and state["pending_order"]["target_unix_nanos"] == 106,
                  "risk exit retains the full size and calibrated causal landing delay")
            check(rows[0]["decision_settlement_num"] == -8_000_000
                  and rows[0]["decision_settlement_den"] == 100_000_000,
                  "ledger records the exact all-cost decision fraction")

            state["pending_order"] = None
            runner.kernel_accounting = lambda *_args, **_kwargs: {
                "out_amount": equality_net + 1_000_001,
                "wallet_delta_lamports": equality_net + 1,
            }
            runner._ORIGINAL_SERVICE = lambda *_args, **_kwargs: [{"delegated": True}]
            rows = runner._service_position(state, object(), object(), now=102)
            check(rows == [{"delegated": True}],
                  "one lamport above risk and above premise delegates unchanged to V2.5 policy")

            horizon_now = p.entry_unix_nanos + policy.MAX_HOLD_NANOS
            horizon_position = position(entry_id=p.entry_id)
            horizon_position.last_refresh_unix_nanos = horizon_now
            state["open_position"] = asdict(horizon_position)
            state["pending_order"] = None
            runner.kernel_accounting = lambda *_args, **_kwargs: {
                "out_amount": equality_net + 1_000_000,
                "wallet_delta_lamports": equality_net,
            }
            rows = runner._service_position(state, object(), object(), now=horizon_now)
            check(rows == [{"delegated": True}],
                  "absolute horizon retains priority over a simultaneous risk breach")

            forged = json.loads(ledger.read_text().splitlines()[0])
            forged["instrument_id"] = "AFTERSHOCK_PAC_V25"
            forged["event_id"] = runner.core._hash(forged)
            ledger.write_text(json.dumps(forged) + "\n")
            try:
                runner._history(ledger)
            except RefusedExecution:
                refused = True
            else:
                refused = False
            check(refused, "cross-instrument ledger evidence refuses")
        finally:
            runner._ACTIVE_LEDGER = previous_ledger
            runner.kernel_accounting = original_accounting
            runner._ORIGINAL_SERVICE = original_service
            runner.core.INSTRUMENT = original_instrument

    check("EXIT_RISK_BUDGET" in {item.value for item in policy.ExitAction},
          "risk-budget action is part of the sealed exit vocabulary")
    check(policy.RISK_BUDGET_NUM == 8 and policy.RISK_BUDGET_DEN == 100,
          "risk threshold is exact and frozen without floats")
    from . import pac_v26_manifest as manifest
    seal = manifest.compute_seal()
    check(seal["instrument_id"] == runner.INSTRUMENT and len(seal["seal_sha256"]) == 64,
          "manifest closes the preregistration, frozen constants, and runtime dependencies")
    original_num = policy.RISK_BUDGET_NUM
    policy.RISK_BUDGET_NUM = original_num + 1
    try:
        try:
            manifest.compute_seal()
        except RefusedExecution:
            refused = True
        else:
            refused = False
    finally:
        policy.RISK_BUDGET_NUM = original_num
    check(refused, "engine threshold drift refuses through the actual seal path")
    print(f"PAC V2.6 SELFTEST: PASS — {CHECKS} checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
