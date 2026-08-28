#!/usr/bin/env python3
"""Hostile regression battery for the PAC schema-2 causal runner."""
from __future__ import annotations

from dataclasses import replace
import inspect
import json
import pathlib
import shutil
import tempfile
from unittest import mock

from . import Refused, execution, feasibility, manifest
from . import pac_runner as runner
from .execution import (
    LatencyModel, Outcome, PriceUnavailable, RefusedExecution, SolUsdObservation,
    q_lamports_for_usd,
)

T0 = 2_100_000_000_000_000_000
INSTRUMENT = runner.INSTRUMENT


def _events(points):
    tape = [{"mint": "PACMINT", "received_unix_nanos": t, "v_sol": float(v),
             "v_tokens": 30 * 1_073_000_000 / float(v), "pool": "pump"} for t, v in points]
    return list(feasibility.tape_to_events(tape))


def _tape():
    points = [(T0 + (i + 1) * 100_000_000, 46.0) for i in range(8)]
    points += [(T0 + 900_000_000, 45.90), (T0 + 1_300_000_000, 46.00),
               (T0 + 1_400_000_000, 45.88), (T0 + 1_600_000_000, 46.02),
               (T0 + 1_800_000_000, 46.03),
               (T0 + 2_000_000_000, 52.00), (T0 + 2_200_000_000, 52.00),
               (T0 + 2_400_000_000, 40.00), (T0 + 2_600_000_000, 40.00)]
    return points


def _check(name, condition):
    print(f"  [{'ok' if condition else 'FAIL'}] {name}")
    return bool(condition)


def _raises(fn, *types):
    try:
        fn()
        return False
    except types or (RefusedExecution, Refused):
        return True


def _rows():
    path = runner._ledger_path()
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def _reset_files():
    for path in (runner._state_path(), runner._ledger_path(), runner._lock_path()):
        if path.exists():
            path.unlink()


def main() -> int:
    ok = True
    production = manifest.RESEARCH
    with tempfile.TemporaryDirectory(prefix="pac_runner_selftest_") as directory:
        fixture = pathlib.Path(directory)
        for name in (f"{INSTRUMENT}_PREREGISTRATION.md", f"{INSTRUMENT}_FROZEN.json"):
            shutil.copy2(production / name, fixture / name)
        with mock.patch.object(manifest, "RESEARCH", fixture):
            manifest.write_seal(INSTRUMENT)
            anchored = {manifest._seal_path(INSTRUMENT).resolve()}
            full = _events(_tape())
            events = full[8:]
            latency = LatencyModel(100_000_000)
            price_fn = feasibility.kernel_price_fn()

            with mock.patch.object(manifest, "_git_committed",
                                   side_effect=lambda path: path.resolve() in anchored):
                with mock.patch.object(manifest.time, "time_ns", return_value=T0):
                    manifest.append_activation(INSTRUMENT, session_reason="first_activation", last_coord=None)
                global_warmup = [replace(event, mint=f"WARM{i % 2}") for i, event in enumerate(full[:8])]
                with mock.patch.object(manifest.time, "time_ns", return_value=T0 + 850_000_000):
                    warmup = manifest.append_warmup_complete(INSTRUMENT, global_warmup)
                manifest.write_activation_anchor(INSTRUMENT)
                ok &= _check("unanchored session still refuses before producing state or fills",
                             _raises(runner.session_context) and not runner._state_path().exists())
                anchored.add(manifest._activation_anchor_path(
                    INSTRUMENT, warmup["event_sha256"]).resolve())
                ctx = runner.session_context()
                q = q_lamports_for_usd(
                    "10.00", SolUsdObservation("200.00", T0 + 1_590_000_000,
                                               "point-in-time-fixture", "d" * 64),
                    decision_unix_nanos=T0 + 1_600_000_000, max_staleness_nanos=100_000_000)

                # Reproduce the production liveness defect: the admitted prefix ends at +1.6s,
                # decision time is +1.9s, and a +1.8s observation appears on the next read.  It must
                # invalidate the incomplete decision and release the book, never fill retrospectively.
                state = runner.load_state()
                with mock.patch.object(execution.time, "time_ns", return_value=T0 + 1_900_000_000):
                    runner.drive_once(events[:4], state, ctx, q_lamports=q,
                                      latency=latency, price_fn=price_fn)
                with mock.patch.object(runner.time, "time_ns", return_value=T0 + 2_100_000_000):
                    with mock.patch.object(execution.time, "time_ns", return_value=T0 + 2_100_000_000):
                        runner.drive_once(events[:6], state, ctx, q_lamports=q,
                                          latency=latency, price_fn=price_fn)
                ok &= _check("late pre-decision observation invalidates instead of wedging/filling",
                             not state["pending_orders"] and not state["open_positions"]
                             and not _rows()
                             and state["last_measurement_refusal"]["reason"]
                             == "LATE_PREDECISION_OBSERVATION")

                # A decision with no post-landing observation is one closed censored attempt, not an
                # indefinitely fillable pseudo-order that monopolises the one-position book.
                _reset_files()
                state = runner.load_state()
                with mock.patch.object(execution.time, "time_ns", return_value=T0 + 1_600_000_000):
                    runner.drive_once(events[:4], state, ctx, q_lamports=q,
                                      latency=latency, price_fn=price_fn)
                with mock.patch.object(runner.time, "time_ns", return_value=T0 + 1_900_000_000):
                    with mock.patch.object(execution.time, "time_ns", return_value=T0 + 1_900_000_000):
                        runner.drive_once(events[:4], state, ctx, q_lamports=q,
                                          latency=latency, price_fn=price_fn)
                ok &= _check("right-censored entry releases the book as a no-trade diagnostic",
                             not state["pending_orders"] and not state["open_positions"]
                             and not _rows()
                             and state["last_measurement_refusal"]["reason"]
                             == "RIGHT_CENSORED_NO_BOUNDARY")

                _reset_files()
                state = runner.load_state()
                with mock.patch.object(execution.time, "time_ns", return_value=T0 + 1_600_000_000):
                    runner.drive_once(events[:4], state, ctx, q_lamports=q,
                                      latency=latency, price_fn=price_fn)
                ok &= _check("entry decision is durable and does not fill at its signal state",
                             len(state["pending_orders"]) == 1 and not state["open_positions"]
                             and not _rows())
                pending_decision = state["pending_orders"][0]["decision"]["decision_id"]
                reloaded = runner.load_state()
                ok &= _check("restart preserves the exact pending DecisionRecord",
                             reloaded["pending_orders"][0]["decision"]["decision_id"] == pending_decision)

                with mock.patch.object(execution.time, "time_ns", return_value=T0 + 1_900_000_000):
                    runner.drive_once(events[:5], state, ctx, q_lamports=q,
                                      latency=latency, price_fn=price_fn)
                position = runner.position_from_dict(state["open_positions"][0])
                opened = [r for r in _rows() if r["kind"] == "opened"]
                ok &= _check("entry lands strictly later and persists an exact all-in cost",
                             len(opened) == 1 and not state["pending_orders"]
                             and position.entry_observation_unix_nanos > T0 + 1_600_000_000
                             and position.entry_all_in_lamports == position.quote_input_lamports
                             + position.entry_curve_fee_lamports
                             + position.entry_attempt_cost_lamports + position.ata_rent_lamports)
                entry_attempt_id = position.entry_attempt_id

                before_hold_rows = len(_rows())
                with mock.patch.object(execution.time, "time_ns", return_value=T0 + 2_100_000_000):
                    runner.drive_once(events[:6], state, ctx, q_lamports=q,
                                      latency=latency, price_fn=price_fn)
                ok &= _check("HOLD observes a net exit quote but creates no sell attempt or fee",
                             len(_rows()) == before_hold_rows and not state["pending_orders"]
                             and state["open_positions"][0]["peak_full_exit_quote_lamports"] > 0)

                with mock.patch.object(execution.time, "time_ns", return_value=T0 + 2_500_000_000):
                    runner.drive_once(events[:8], state, ctx, q_lamports=q,
                                      latency=latency, price_fn=price_fn)
                ok &= _check("trail trigger persists a sell decision before attempting it",
                             len(state["pending_orders"]) == 1
                             and state["pending_orders"][0]["side"] == "EXIT"
                             and len(_rows()) == before_hold_rows)
                exit_decision_id = state["pending_orders"][0]["decision"]["decision_id"]

                with mock.patch.object(execution.time, "time_ns", return_value=T0 + 2_700_000_000):
                    runner.drive_once(events, state, ctx, q_lamports=q,
                                      latency=latency, price_fn=price_fn)
                resolved = [r for r in _rows() if r["kind"] == "resolved"]
                row = resolved[0]
                ok &= _check("exit lands later through a chain distinct from entry",
                             len(resolved) == 1 and not state["open_positions"]
                             and row["exit_decision_id"] == exit_decision_id
                             and row["exit_decision_id"] != pending_decision
                             and row["exit_attempt_id"] != entry_attempt_id
                             and row["exit_boundary_observation_unix_nanos"]
                             > row["entry_observation_unix_nanos"])
                ok &= _check("resolved return reconciles gross, fees, gas, ATA and net exactly",
                             row["exit_net_proceeds_lamports"] == row["exit_gross_quote_lamports"]
                             - row["exit_curve_fee_lamports"] - row["exit_attempt_cost_lamports"]
                             and row["net_return_num"] == row["exit_net_proceeds_lamports"]
                             - row["entry_all_in_lamports"]
                             and row["net_return_den"] == row["entry_all_in_lamports"]
                             and row["ata_rent_treatment"].startswith("CHARGED_ON_ENTRY"))
                ok &= _check("all schema-2 ledger events are self-authenticating",
                             all(runner._validate_row(item) is item for item in _rows()))

                # Quote-unavailable is a policy decision, never a fictitious attempted fill.
                _reset_files()
                state = runner._new_state()
                state["session_event_sha256"] = ctx.session.session_event_sha256
                state["activation_root_sha256"] = ctx.session.activation_root_sha256
                state["open_positions"] = [runner.position_to_dict(position)]
                runner.save_state(state)
                with mock.patch.object(feasibility, "kernel_accounting",
                                       side_effect=PriceUnavailable("complete")):
                    with mock.patch.object(execution.time, "time_ns", return_value=T0 + 2_100_000_000):
                        runner.drive_once(events[:6], state, ctx, q_lamports=q,
                                          latency=latency, price_fn=price_fn)
                loss = [r for r in _rows() if r["kind"] == "resolved"][0]
                ok &= _check("unavailable decision quote is exact full loss with no invented attempt",
                             loss["unexitable_full_loss"] is True
                             and loss["net_return_num"] == -loss["net_return_den"]
                             and loss["exit_attempt_id"] is None)

                # A priceable exit whose gas exceeds gross proceeds is economically zero, not a
                # ValueError/refusal loop.  It may HOLD for recovery, but an actual horizon trigger
                # settles conservatively as an exact full loss without inventing a sell attempt.
                _reset_files()
                state = runner._new_state()
                state["session_event_sha256"] = ctx.session.session_event_sha256
                state["activation_root_sha256"] = ctx.session.activation_root_sha256
                state["open_positions"] = [runner.position_to_dict(position)]
                runner.save_state(state)
                negative_exit = {
                    "side": "EXIT", "out_amount": 100_000, "out_unit": execution.Unit.LAMPORTS,
                    "gross_quote_lamports": 100_000, "curve_fee_lamports": 10_000,
                    "attempt_cost_lamports": 200_000, "ata_rent_lamports": 0,
                    "wallet_delta_lamports": -110_000,
                }
                horizon_time = T0 + 800_000_000_000
                with mock.patch.object(feasibility, "kernel_accounting", return_value=negative_exit):
                    with mock.patch.object(execution.time, "time_ns", return_value=horizon_time):
                        runner.drive_once(events[:6], state, ctx, q_lamports=q,
                                          latency=latency, price_fn=price_fn)
                dust_loss = [r for r in _rows() if r["kind"] == "resolved"][0]
                ok &= _check("net-nonpositive horizon exit settles full loss and releases lock",
                             not state["open_positions"] and not state["pending_orders"]
                             and dust_loss["unexitable_full_loss"] is True
                             and dust_loss["net_return_num"] == -dust_loss["net_return_den"]
                             and "NET_EXIT_NONPOSITIVE_AT_ATTEMPT_FULL_EXIT_HORIZON"
                             in dust_loss["labels"])

                # A positive horizon quote can still lack a later execution boundary.  At the hard
                # horizon that censor is stressed to full loss, so one dead tape cannot wedge forever.
                _reset_files()
                state = runner._new_state()
                state["session_event_sha256"] = ctx.session.session_event_sha256
                state["activation_root_sha256"] = ctx.session.activation_root_sha256
                state["open_positions"] = [runner.position_to_dict(position)]
                runner.save_state(state)
                with mock.patch.object(execution.time, "time_ns", return_value=horizon_time):
                    runner.drive_once(events[:6], state, ctx, q_lamports=q,
                                      latency=latency, price_fn=price_fn)
                with mock.patch.object(runner.time, "time_ns", return_value=horizon_time + 1):
                    with mock.patch.object(execution.time, "time_ns", return_value=horizon_time + 1):
                        runner.drive_once(events[:6], state, ctx, q_lamports=q,
                                          latency=latency, price_fn=price_fn)
                censored_loss = [r for r in _rows() if r["kind"] == "resolved"][0]
                ok &= _check("right-censored hard-horizon exit becomes full loss, never a permanent lock",
                             not state["open_positions"] and not state["pending_orders"]
                             and censored_loss["unexitable_full_loss"] is True
                             and "HORIZON_EXIT_RIGHT_CENSORED_FULL_LOSS"
                             in censored_loss["labels"])

                # Write-ahead ledger: crash before append and crash after append each recover once.
                for crash_point in ("before_append", "after_append"):
                    _reset_files()
                    state = runner._new_state()
                    state["session_event_sha256"] = ctx.session.session_event_sha256
                    state["activation_root_sha256"] = ctx.session.activation_root_sha256
                    body = {"kind": "attempt_cost", "side": "ENTRY", "mint": "PACMINT",
                            "attempt_id": "a" * 64, "entry_attempt_id": None,
                            "outcome": Outcome.SCENARIO_FAILED_SLIPPAGE.value,
                            "attempt_cost_lamports": 210_000, "cost_observed": True,
                            "denominator_lamports": q, "labels": []}
                    journal_row = runner._ledger_row(body, ctx)
                    if crash_point == "before_append":
                        with mock.patch.object(runner, "_append_ledger", side_effect=OSError("crash")):
                            _raises(lambda: runner._commit(state, [journal_row]), OSError)
                    else:
                        original_save = runner.save_state
                        calls = {"n": 0}

                        def flaky_save(value):
                            calls["n"] += 1
                            if calls["n"] == 2:
                                raise OSError("crash")
                            original_save(value)

                        with mock.patch.object(runner, "save_state", side_effect=flaky_save):
                            _raises(lambda: runner._commit(state, [journal_row]), OSError)
                    recovered = runner.load_state()
                    ok &= _check(f"crash journal recovers exactly once ({crash_point})",
                                 len(_rows()) == 1 and not recovered["pending_ledger_rows"])

                tampered = dict(_rows()[0])
                tampered["attempt_cost_lamports"] += 1
                ok &= _check("ledger byte tampering refuses instead of silently deduplicating",
                             _raises(lambda: runner._append_ledger(tampered)))
                ok &= _check("production API has no caller-supplied decision clock",
                             "now_unix_nanos" not in inspect.signature(runner.drive_once).parameters)
                ok &= _check("continuous runner requires latency explicitly (no research default)",
                             inspect.signature(runner.run_cycle).parameters["reaction_nanos"].default
                             is inspect.Parameter.empty)

                _reset_files()
                with mock.patch.object(runner.time, "time_ns", return_value=T0 + 3_000_000_000):
                    initialized = runner._run_cycle_unlocked(reaction_nanos=100_000_000)
                initialized_state = runner.load_state()
                ok &= _check("first continuous cycle writes a watermark and refuses all backlog",
                             initialized["status"] == "WATERMARK_INITIALIZED_NO_BACKFILL"
                             and initialized_state["scan_watermark_unix_nanos"]
                             == T0 + 3_000_000_000 and not _rows())
                empty_tapes = fixture / "empty_tapes"; empty_tapes.mkdir()
                with mock.patch.object(runner.tape, "TAPE_DIR", empty_tapes), \
                        mock.patch.object(runner, "_probe_lamports", return_value=q), \
                        mock.patch.object(runner.time, "time_ns", return_value=T0 + 4_000_000_000):
                    quiet = runner._run_cycle_unlocked(reaction_nanos=100_000_000)
                ok &= _check("next continuous cycle advances only its newly admitted interval",
                             quiet["status"] == "NO_ELIGIBLE_SIGNAL"
                             and runner.load_state()["scan_watermark_unix_nanos"]
                             == T0 + 4_000_000_000)
                lock = runner.runner_lock()
                try:
                    ok &= _check("second runner process is refused by the state lock",
                                 _raises(runner.runner_lock))
                finally:
                    lock.close()

    print("PAC runner selftest:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
