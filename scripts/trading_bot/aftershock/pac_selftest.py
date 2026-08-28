#!/usr/bin/env python3
"""Regression tests for the PAC V1 detector and full-position exit policy."""
from __future__ import annotations

from dataclasses import replace
import pathlib
import shutil
import tempfile
from unittest import mock

from . import Refused
from . import feasibility
from . import manifest
from . import pac_detector as detector
from .execution import (
    ExecutionContext, IntentKind, LatencyModel, OrderIntent, Outcome, RefusedExecution,
    SolUsdObservation, Unit, attempt_order, build_decision_record, q_lamports_for_usd,
)
from .pac_policy import ExitAction, MAX_HOLD_NANOS, PositionState, decide_exit

T0 = 2_100_000_000_000_000_000
INSTRUMENT = "AFTERSHOCK_PAC_V1"
DETECTOR_PATH = "scripts/trading_bot/aftershock/pac_detector.py"


def _events(points):
    tape = [{"mint": "PACMINT", "received_unix_nanos": t, "v_sol": float(v),
             "v_tokens": 30 * 1_073_000_000 / float(v), "pool": "pump"} for t, v in points]
    return tuple(feasibility.tape_to_events(tape))


def _base():
    # Eight warm-up observations, then a 0.10-SOL/400ms recovery and a
    # 0.12-SOL/200ms recovery at a non-eroding reserve baseline.
    points = [(T0 + (i + 1) * 100_000_000, 46.0) for i in range(8)]
    points += [(T0 + 900_000_000, 45.90), (T0 + 1_300_000_000, 46.00),
               (T0 + 1_400_000_000, 45.88), (T0 + 1_600_000_000, 46.02)]
    return points


def _check(name, condition):
    print(f"  [{'ok' if condition else 'FAIL'}] {name}")
    return bool(condition)


def _raises(fn):
    try:
        fn()
        return False
    except (RefusedExecution, Refused):
        return True


def _engine_composition() -> bool:
    """Positive path mocks only git anchoring and writes all ephemeral authority files under /tmp."""
    ok = True
    production = manifest.RESEARCH
    with tempfile.TemporaryDirectory(prefix="aftershock_pac_selftest_") as directory:
        fixture = pathlib.Path(directory)
        for name in (f"{INSTRUMENT}_PREREGISTRATION.md", f"{INSTRUMENT}_FROZEN.json"):
            shutil.copy2(production / name, fixture / name)
        with mock.patch.object(manifest, "RESEARCH", fixture):
            seal = manifest.write_seal(INSTRUMENT)
            detector_sha = seal["dependency_sha256"][DETECTOR_PATH]
            anchored = {manifest._seal_path(INSTRUMENT).resolve()}

            tape = _base() + [(T0 + 1_800_000_000, 46.03)]
            events = list(_events(tape))
            with mock.patch.object(manifest, "_git_committed",
                                   side_effect=lambda path: path.resolve() in anchored):
                with mock.patch.object(manifest.time, "time_ns", return_value=T0):
                    manifest.append_activation(INSTRUMENT, session_reason="first_activation", last_coord=None)
                global_warmup = [replace(event, mint=f"WARM{i % 2}")
                                 for i, event in enumerate(events[:8])]
                with mock.patch.object(manifest.time, "time_ns", return_value=T0 + 850_000_000):
                    warmup = manifest.append_warmup_complete(INSTRUMENT, global_warmup)
                manifest.write_activation_anchor(INSTRUMENT)
                ok &= _check("PAC uncommitted activation anchor refuses evidence",
                             _raises(lambda: manifest.load_session_proof(INSTRUMENT)))
                anchored.add(manifest._activation_anchor_path(
                    INSTRUMENT, warmup["event_sha256"]).resolve())
                proof = manifest.load_session_proof(INSTRUMENT)
                context = ExecutionContext(proof)
                ok &= _check("feed-global warm-up supports multiple mints without fake continuity",
                             proof.warmup_scope == "feed_global")
                decision_events = events[8:]  # feed-global warm-up is authority, not a fake mint prefix
                old_event = replace(decision_events[0],
                                    observation_unix_nanos=proof.warmup_completed_unix_nanos)
                ok &= _check("per-mint evidence at/before global warm-up completion refuses",
                             _raises(lambda: build_decision_record(
                                 [old_event, *decision_events[1:]], context,
                                 detector_module_path=DETECTOR_PATH,
                                 detector_callable_name="detector", detector_sha256=detector_sha,
                                 spec_sha256=proof.frozen_json_canonical_sha256)))
                with mock.patch("scripts.trading_bot.aftershock.execution.time.time_ns",
                                return_value=T0 + 1_600_000_000):
                    decision = build_decision_record(
                        decision_events, context, detector_module_path=DETECTOR_PATH,
                        detector_callable_name="detector", detector_sha256=detector_sha,
                        spec_sha256=proof.frozen_json_canonical_sha256)
                q = q_lamports_for_usd(
                    "10.00", SolUsdObservation("200.00", T0 + 1_590_000_000,
                                                "point-in-time-fixture", "d" * 64),
                    decision_unix_nanos=T0 + 1_600_000_000,
                    max_staleness_nanos=100_000_000)
                ok &= _check("sealed PAC decision binds the newest recovery and exact $10 coverage",
                             decision.signal_index == 3
                             and detector.position_size_is_covered(
                                 tuple(decision_events[:decision.evaluated_through_index + 1]),
                                                                   decision.evidence_indices, q))
                attempt = attempt_order(
                    decision_events, decision, OrderIntent(IntentKind.EXACT_QUOTE_BUY, q, 1),
                    LatencyModel(100_000_000), context, feasibility.kernel_price_fn())
                ok &= _check("PAC entry lands only at a later scenario boundary via the real kernel",
                             attempt.outcome is Outcome.SCENARIO_FILLED
                             and attempt.boundary_index == 4 and attempt.out_unit is Unit.ATOMS)
    return ok


def main() -> int:
    ok = True
    events = _events(_base())
    evidence = detector.detector(events, 8)
    ok &= _check("PAC fires on heavier/faster second recovery with preserved reserves",
                 evidence == (8, 9, 10, 11))
    metrics = detector.pac_metrics(events, evidence)
    ok &= _check("PAC metrics are exact and auditable",
                 metrics["withdrawal_2_lamports"] >= metrics["withdrawal_1_lamports"]
                 and metrics["recovery_2_nanos"] <= metrics["recovery_1_nanos"])
    ok &= _check("planned size must fit both observed withdrawals",
                 detector.position_size_is_covered(events, evidence, 50_000_000)
                 and not detector.position_size_is_covered(events, evidence, 150_000_000))
    ok &= _check("forged evidence cannot pass the position-size guard",
                 not detector.position_size_is_covered(events, (8, 9, 9, 11), 1))
    ok &= _check("a later observation makes the old pattern stale",
                 detector.detector(_events(_base() + [(T0 + 1_700_000_000, 46.03)]), 8) == ())

    weaker = _base(); weaker[10] = (T0 + 1_400_000_000, 45.95)
    ok &= _check("weaker second withdrawal refuses", detector.detector(_events(weaker), 8) == ())
    slower = _base(); slower[11] = (T0 + 2_000_000_000, 46.02)
    ok &= _check("slower second recovery refuses", detector.detector(_events(slower), 8) == ())
    eroded = _base(); eroded[9] = (T0 + 1_300_000_000, 46.00); eroded[10] = (T0 + 1_400_000_000, 45.80); eroded[11] = (T0 + 1_600_000_000, 45.95)
    ok &= _check("eroded reserve baseline refuses", detector.detector(_events(eroded), 8) == ())

    state = PositionState(1_000_000, 50_000_000, T0, 45_000_000)
    up = decide_exit(state, full_exit_quote_lamports=80_000_000,
                     external_reserve_lamports=1_000_000_000,
                     observation_unix_nanos=T0 + 1)
    ok &= _check("no fixed take-profit caps a winner", up.action is ExitAction.HOLD)
    trailed = decide_exit(up.state, full_exit_quote_lamports=70_000_000,
                          external_reserve_lamports=1_000_000_000,
                          observation_unix_nanos=T0 + 2)
    ok &= _check("12% drawdown requests a causal full-position exit",
                 trailed.action is ExitAction.ATTEMPT_FULL_EXIT_TRAIL)
    unavailable = decide_exit(state, full_exit_quote_lamports=None,
                              external_reserve_lamports=None, observation_unix_nanos=T0 + 2)
    ok &= _check("unavailable exit quote is an honest full loss, never a fictitious exit",
                 unavailable.action is ExitAction.UNEXITABLE_FULL_LOSS)
    horizon = decide_exit(state, full_exit_quote_lamports=45_000_000,
                          external_reserve_lamports=1_000_000_000,
                          observation_unix_nanos=T0 + MAX_HOLD_NANOS)
    ok &= _check("12-minute hard horizon requests an exit",
                 horizon.action is ExitAction.ATTEMPT_FULL_EXIT_HORIZON)
    ok &= _engine_composition()
    print("\nAFTERSHOCK PAC SELFTEST: " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
