#!/usr/bin/env python3
"""Adversarial regression suite for the handoff-424 execution-measurement chain.

The public attempt path is exercised with a manifest-derived SessionProof. Positive fixtures patch only
the external git-anchor predicate to emulate the later owner-gated commits; negative anchor tests use the
real uncommitted state. No test can set ``verified`` or ``warmup_complete`` because those fields no longer
exist.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from unittest import mock

from . import Refused
from . import execution as _execution
from . import feasibility as _feas
from . import manifest as _manifest
from .execution import (
    Calibration, CanonicalCoord, DecisionRecord, ExecutionContext, IntentKind, LatencyModel,
    ObservedEvent, OrderIntent, Outcome, PriceResult, PriceUnavailable, RefusedExecution,
    RentStatus, ReserveState, SolUsdObservation, Source, Unit, attempt_order,
    build_decision_record, q_lamports_for_usd, rent_outcome, validate_stream,
)

INSTRUMENT = "AFTERSHOCK_EXECTEST"
T0 = 2_000_000_000_000_000_000
GOOD_HASH = "a" * 64
DETECTOR_PATH = "scripts/trading_bot/aftershock/execution_fixture_detector.py"
DETECTOR_CALLABLE = "all_post_warmup_evidence"


class Checks:
    def __init__(self) -> None:
        self.count = 0
        self.ok = True

    def check(self, name: str, condition: bool, detail: str = "") -> None:
        self.count += 1
        self.ok &= bool(condition)
        print(f"  [{'ok' if condition else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))


def _raises(fn, exception=None) -> bool:
    expected = (RefusedExecution, Refused) if exception is None else exception
    try:
        fn()
        return False
    except expected:
        return True
    except Exception:
        return False


def _fixture_paths() -> list:
    fixed = [
        _manifest.RESEARCH / f"{INSTRUMENT}_PREREGISTRATION.md",
        _manifest.RESEARCH / f"{INSTRUMENT}_FROZEN.json",
        _manifest._seal_path(INSTRUMENT),
        _manifest._activation_path(INSTRUMENT),
    ]
    return fixed + list(_manifest.RESEARCH.glob(f"{INSTRUMENT}_ACTIVATION_ANCHOR_*.json"))


def _cleanup() -> None:
    for path in _fixture_paths():
        path.unlink(missing_ok=True)


def _write_frozen_fixture() -> tuple[dict, str]:
    prereg = _manifest.RESEARCH / f"{INSTRUMENT}_PREREGISTRATION.md"
    frozen_path = _manifest.RESEARCH / f"{INSTRUMENT}_FROZEN.json"
    prereg.write_text("# AFTERSHOCK execution self-test fixture\n")
    prereg_sha = hashlib.sha256(prereg.read_bytes()).hexdigest()
    experiment = [DETECTOR_PATH]
    dependencies = sorted(set(_manifest.BASE_DEPENDENCY_PATHS) | set(experiment))
    frozen = {
        "instrument_id": INSTRUMENT,
        "frozen_utc": "2026-08-28T00:00:00+00:00",
        "preregistration_sha256": prereg_sha,
        "execution_realism": {
            "warmup_min_events": 2,
            "warmup_min_span_nanos": 100,
            "experiment_dependency_paths": experiment,
            "dependency_paths": dependencies,
        },
    }
    frozen_path.write_text(json.dumps(frozen, indent=2, sort_keys=True) + "\n")
    seal = _manifest.write_seal(INSTRUMENT)
    detector_sha = seal["dependency_sha256"][experiment[0]]
    return seal, detector_sha


def _tape(times: list[int], v_sols: list[int], *, slot0: int = 100) -> list[dict]:
    constant = 30 * 1_073_000_000
    return [
        {
            "mint": "MINT",
            "provider_event_time": f"provider-{index}",
            "received_unix_nanos": timestamp,
            "v_sol": float(v_sol),
            "v_tokens": constant / float(v_sol),
            "pool": "pump",
            "slot": slot0 + index,
            "transaction_index": 0,
            "outer_index": 0,
            "inner_index": 0,
        }
        for index, (timestamp, v_sol) in enumerate(zip(times, v_sols, strict=True))
    ]


def _price(out: int, unit: Unit, cost: int = 105_000):
    return lambda _state, _intent: PriceResult(out, unit, cost)


def _backdate_and_rehash_activation(path) -> str:
    raw = path.read_text()
    rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
    old_to_new = {}
    previous = None
    for index, row in enumerate(rows):
        old_sha = row["event_sha256"]
        body = {key: value for key, value in row.items() if key != "event_sha256"}
        if index == 0:
            body["recorded_unix_nanos"] = 0
        body["prev_event_sha256"] = previous
        if body["event_kind"] == "warmup_complete":
            body["session_event_sha256"] = old_to_new[body["session_event_sha256"]]
        new_sha = _manifest._event_sha(body)
        rows[index] = {**body, "event_sha256": new_sha}
        old_to_new[old_sha] = new_sha
        previous = new_sha
    path.write_text("".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows))
    return raw


def _schema_checks(c: Checks) -> None:
    state = ReserveState(60_000_000_000, 500_000_000_000_000,
                         30_000_000_000, 200_000_000_000_000, False)
    c.check("negative reserve REFUSES", _raises(lambda: ReserveState(1, 1, -1, 0, False)))
    c.check("zero virtual reserve REFUSES", _raises(lambda: ReserveState(0, 1, 0, 0, False)))
    c.check("float/bool coordinate REFUSES",
            _raises(lambda: CanonicalCoord(1.0, 0, 0, 0)) and
            _raises(lambda: CanonicalCoord(True, 0, 0, 0)))
    c.check("bad intent enum REFUSES", _raises(lambda: OrderIntent("BAD", 1, 1)))
    c.check("zero min_out REFUSES", _raises(lambda: OrderIntent(IntentKind.EXACT_QUOTE_BUY, 1, 0)))
    c.check("negative price cost REFUSES", _raises(lambda: PriceResult(1, Unit.ATOMS, -1)))
    c.check("wrong price unit type REFUSES", _raises(lambda: PriceResult(1, "atoms", 0)))
    c.check("caller cannot assert verified/warmup",
            _raises(lambda: ExecutionContext(session="caller-says-verified")))
    c.check("canonical source without coordinate REFUSES",
            _raises(lambda: ObservedEvent("M", 1, state, state, Source.CANONICAL_RPC, GOOD_HASH)))
    e1 = ObservedEvent("M", 1, state, state, Source.PUMPPORTAL, GOOD_HASH)
    e2 = ObservedEvent("M", 2, state, state, Source.CANONICAL_RPC, GOOD_HASH, CanonicalCoord(2, 0, 0, 0))
    c.check("mixed source/partial coordinate stream REFUSES", _raises(lambda: validate_stream([e1, e2])))


def _sizing_and_rent_checks(c: Checks) -> None:
    quote = SolUsdObservation("200.00", T0, "point-in-time-feed", GOOD_HASH)
    c.check("Decimal $10 at $200 is 50,000,000 lamports",
            q_lamports_for_usd("10.00", quote, decision_unix_nanos=T0 + 10,
                               max_staleness_nanos=100) == 50_000_000)
    c.check("tiny USD rounding to zero REFUSES",
            _raises(lambda: q_lamports_for_usd("0.00000000001", quote,
                                               decision_unix_nanos=T0 + 10,
                                               max_staleness_nanos=100)))
    c.check("float freshness bound REFUSES",
            _raises(lambda: q_lamports_for_usd("10", quote, decision_unix_nanos=T0 + 10,
                                               max_staleness_nanos=100.0)))
    c.check("missing quote evidence hash REFUSES",
            _raises(lambda: SolUsdObservation("200", T0, "feed", "bad")))
    c.check("future/stale quote REFUSES",
            _raises(lambda: q_lamports_for_usd("10", quote, decision_unix_nanos=T0 - 1,
                                               max_staleness_nanos=100)) and
            _raises(lambda: q_lamports_for_usd("10", quote, decision_unix_nanos=T0 + 101,
                                               max_staleness_nanos=100)))

    not_created = rent_outcome(
        ata_preexisting=False, ata_created=False, token_balance_after=0, close_attempted=False,
        close_succeeded=False, reached_horizon=False, rent_lamports=0, close_cost_lamports=None)
    stranded = rent_outcome(
        ata_preexisting=False, ata_created=True, token_balance_after=1, close_attempted=False,
        close_succeeded=False, reached_horizon=True, rent_lamports=2_039_280,
        close_cost_lamports=None)
    reclaimed = rent_outcome(
        ata_preexisting=False, ata_created=True, token_balance_after=0, close_attempted=True,
        close_succeeded=True, reached_horizon=False, rent_lamports=2_039_280,
        close_cost_lamports=5_000)
    c.check("NOT_CREATED rent state is reachable and reconciled",
            not_created.status is RentStatus.NOT_CREATED and not_created.locked_lamports == 0)
    c.check("rug rent remains locked/stranded",
            stranded.status is RentStatus.STRANDED_AT_HORIZON and stranded.locked_lamports == 2_039_280)
    c.check("clean close reclaims rent minus measured close cost",
            reclaimed.status is RentStatus.RECLAIMED_FULL_SELL_CLOSE and
            reclaimed.settled_delta_lamports == 2_034_280)
    c.check("negative rent and impossible close REFUSE",
            _raises(lambda: rent_outcome(
                ata_preexisting=False, ata_created=True, token_balance_after=0,
                close_attempted=False, close_succeeded=False, reached_horizon=False,
                rent_lamports=-1, close_cost_lamports=None)) and
            _raises(lambda: rent_outcome(
                ata_preexisting=False, ata_created=True, token_balance_after=1,
                close_attempted=True, close_succeeded=True, reached_horizon=False,
                rent_lamports=1, close_cost_lamports=1)))
    c.check("preexisting and created ATA contradiction REFUSES",
            _raises(lambda: rent_outcome(
                ata_preexisting=True, ata_created=True, token_balance_after=0,
                close_attempted=False, close_succeeded=False, reached_horizon=False,
                rent_lamports=0, close_cost_lamports=None)))


def _manifest_and_execution_checks(c: Checks) -> None:
    seal, detector_sha = _write_frozen_fixture()
    frozen_path = _manifest.RESEARCH / f"{INSTRUMENT}_FROZEN.json"
    activation_path = _manifest._activation_path(INSTRUMENT)

    c.check("unanchored seal REFUSES activation through public path",
            _raises(lambda: _manifest.append_activation(
                INSTRUMENT, session_reason="first_activation", last_coord=None)))
    c.check("dependency closure uses real b10b path and pins b9i/IDL",
            "scripts/b10b_position_path.py" in _manifest.BASE_DEPENDENCY_PATHS and
            "scripts/b10b_path_dataset.py" not in _manifest.BASE_DEPENDENCY_PATHS and
            "scripts/b9i_quote_reproduction.py" in _manifest.BASE_DEPENDENCY_PATHS and
            "research/pump_idl_9c82f61.json" in _manifest.BASE_DEPENDENCY_PATHS)

    anchored: set = {_manifest._seal_path(INSTRUMENT).resolve()}

    def committed(path) -> bool:
        return path.resolve() in anchored

    first_tape = _tape([T0 + 100, T0 + 200, T0 + 300, T0 + 500], [60, 58, 50, 45])
    first_events = _feas.tape_to_events(first_tape)
    with mock.patch.object(_manifest, "_git_committed", side_effect=committed):
        with mock.patch.object(_manifest.time, "time_ns", return_value=T0):
            activation = _manifest.append_activation(
                INSTRUMENT, session_reason="first_activation", last_coord=None)
        c.check("activation time is internal", activation["recorded_unix_nanos"] == T0)
        c.check("second first_activation REFUSES",
                _raises(lambda: _manifest.append_activation(
                    INSTRUMENT, session_reason="first_activation", last_coord=None)))

        with mock.patch.object(_manifest.time, "time_ns", return_value=T0 + 250):
            warmup = _manifest.append_warmup_complete(INSTRUMENT, first_events[:2])
        anchor = _manifest.write_activation_anchor(INSTRUMENT)
        c.check("uncommitted activation root REFUSES SessionProof",
                _raises(lambda: _manifest.load_session_proof(INSTRUMENT)))
        anchor_path = _manifest._activation_anchor_path(INSTRUMENT, warmup["event_sha256"])
        anchored.add(anchor_path.resolve())
        proof = _manifest.load_session_proof(INSTRUMENT)
        ctx = ExecutionContext(proof)
        c.check("SessionProof is manifest-derived after both anchors",
                proof.activation_root_sha256 == warmup["event_sha256"] and
                proof.activation_anchor_sha256 == anchor["anchor_sha256"])

        forged = replace(proof, activation_anchor_sha256="b" * 64)
        c.check("caller-forged SessionProof REFUSES at the public decision path",
                _raises(lambda: build_decision_record(
                    first_events, ExecutionContext(forged), detector_module_path=DETECTOR_PATH,
                    detector_callable_name=DETECTOR_CALLABLE, detector_sha256=detector_sha,
                    spec_sha256=seal["frozen_json_canonical_sha256"])))

        with mock.patch("scripts.trading_bot.aftershock.execution.time.time_ns", return_value=T0 + 350):
            decision = build_decision_record(
                first_events, ctx, detector_module_path=DETECTOR_PATH,
                detector_callable_name=DETECTOR_CALLABLE, detector_sha256=detector_sha,
                spec_sha256=seal["frozen_json_canonical_sha256"])
        sell = OrderIntent(IntentKind.EXACT_TOKEN_SELL, 1_000_000, 1)
        record = attempt_order(first_events, decision, sell, LatencyModel(100), ctx,
                               _price(1_000_000, Unit.LAMPORTS))
        c.check("anchored causal scenario reaches post-target boundary",
                record.outcome is Outcome.SCENARIO_FILLED and record.boundary_index == 3)
        c.check("unmeasured build/send/land clocks remain NULL",
                record.clocks.build_unix_nanos is None and record.clocks.send_unix_nanos is None and
                record.clocks.land_unix_nanos is None and
                record.clocks.modeled_land_target_unix_nanos == T0 + 450)
        c.check("AttemptRecord references seal, activation root, and DecisionRecord",
                record.seal_sha256 == proof.seal_sha256 and
                record.activation_root_sha256 == proof.activation_root_sha256 and
                record.decision_id == decision.decision_id)
        c.check("DecisionRecord pins full receive-time prefix and sealed detector output",
                decision.evaluated_through_index == 2 and decision.evidence_indices == (2,)
                and decision.stream_snapshot_count == 4
                and decision.stream_snapshot_sha256 == _execution._hash_json([
                    _execution.event_commitment(event) for event in first_events]))

        # A row can materialise after the committed processed snapshot with a receive clock before
        # the decision.  It remains in the reserve chain but cannot rewrite detector evidence.
        with mock.patch("scripts.trading_bot.aftershock.execution.time.time_ns", return_value=T0 + 350):
            snapshot_decision = build_decision_record(
                first_events[:3], ctx, detector_module_path=DETECTOR_PATH,
                detector_callable_name=DETECTOR_CALLABLE, detector_sha256=detector_sha,
                spec_sha256=seal["frozen_json_canonical_sha256"])
        late = replace(
            first_events[3], observation_unix_nanos=T0 + 340,
            post_state=first_events[3].pre_state, evidence_sha="b" * 64,
            coord=CanonicalCoord(103, 0, 0, 0))
        boundary = replace(first_events[3], coord=CanonicalCoord(104, 0, 0, 0),
                           evidence_sha="c" * 64)
        lag_record = attempt_order(
            first_events[:3] + [late, boundary], snapshot_decision, sell,
            LatencyModel(100), ctx, _price(1_000_000, Unit.LAMPORTS))
        c.check("post-snapshot pipeline lag preserves reserve chain without changing decision prefix",
                lag_record.outcome is Outcome.SCENARIO_FILLED
                and lag_record.boundary_index == 4
                and snapshot_decision.evidence_indices == (2,))

        incomplete = replace(
            decision, evaluated_through_index=3,
            evaluated_prefix_sha256=_execution._hash_json([
                _execution.event_commitment(event) for event in first_events]),
            decision_unix_nanos=T0 + 550)
        incomplete = replace(
            incomplete, decision_id=_execution._hash_json(_execution._decision_body(incomplete)))
        c.check("rehashed record omitting sealed-detector evidence REFUSES",
                _raises(lambda: attempt_order(
                    first_events, incomplete, sell, LatencyModel(100), ctx,
                    _price(1, Unit.LAMPORTS))))

        c.check("signal earlier than maximum declared evidence REFUSES",
                _raises(lambda: replace(decision, evidence_indices=(2, 3),
                                        evidence_commitments=(decision.evidence_commitments[0], GOOD_HASH),
                                        signal_index=2)))
        c.check("tampered DecisionRecord digest REFUSES",
                _raises(lambda: attempt_order(
                    first_events, replace(decision, decision_id="b" * 64), sell,
                    LatencyModel(100), ctx, _price(1, Unit.LAMPORTS))))

        zero = attempt_order(first_events, decision, sell, LatencyModel(100), ctx,
                             _price(0, Unit.LAMPORTS))
        c.check("zero output is unavailable with NULL cost, never a fill",
                zero.outcome is Outcome.SCENARIO_UNAVAILABLE and zero.cost_lamports is None)
        c.check("wrong output unit REFUSES",
                _raises(lambda: attempt_order(
                    first_events, decision, sell, LatencyModel(100), ctx,
                    _price(1, Unit.ATOMS))))
        high_min = OrderIntent(IntentKind.EXACT_TOKEN_SELL, 1_000_000, 2_000_000)
        slip = attempt_order(first_events, decision, high_min, LatencyModel(100), ctx,
                             _price(1_000_000, Unit.LAMPORTS))
        c.check("typed slippage failure charges this attempt only",
                slip.outcome is Outcome.SCENARIO_FAILED_SLIPPAGE and slip.cost_lamports == 105_000)

        def unavailable(_state, _intent):
            raise PriceUnavailable("known unavailable")

        unavailable_record = attempt_order(first_events, decision, sell, LatencyModel(100), ctx, unavailable)
        c.check("named quote unavailability is not a fill and invents no cost",
                unavailable_record.outcome is Outcome.SCENARIO_UNAVAILABLE and
                unavailable_record.cost_lamports is None)

        short_events = first_events[:3]
        censored = attempt_order(short_events, snapshot_decision, sell, LatencyModel(100), ctx,
                                 _price(1, Unit.LAMPORTS))
        c.check("missing future boundary is right-censored, not 'never sent'",
                censored.outcome is Outcome.RIGHT_CENSORED_NO_BOUNDARY and
                censored.cost_lamports is None and censored.clocks.send_unix_nanos is None)

        retry = attempt_order(first_events, decision, sell, LatencyModel(100), ctx,
                              _price(1_000_000, Unit.LAMPORTS), attempt_index=1,
                              retry_of=record.attempt_id)
        c.check("retry is a distinct, correctly chained AttemptRecord",
                retry.attempt_id != record.attempt_id and retry.retry_of == record.attempt_id)
        c.check("negative/mismatched retry metadata REFUSES",
                _raises(lambda: attempt_order(first_events, decision, sell, LatencyModel(100), ctx,
                                              _price(1, Unit.LAMPORTS), attempt_index=-1)) and
                _raises(lambda: attempt_order(first_events, decision, sell, LatencyModel(100), ctx,
                                              _price(1, Unit.LAMPORTS), attempt_index=1,
                                              retry_of="b" * 64)))

        # The feasibility adapter uses failed_attempts=0; a RuntimeError is not translated to availability.
        buy = OrderIntent(IntentKind.EXACT_QUOTE_BUY, 50_000_000, 1)
        with mock.patch.object(_feas._B10A, "price_entry", side_effect=RuntimeError("kernel bug")):
            c.check("adapter unknown RuntimeError PROPAGATES",
                    _raises(lambda: attempt_order(
                        first_events, decision, buy, LatencyModel(100), ctx,
                        _feas.kernel_price_fn()), exception=RuntimeError))
        c.check("kernel policy embeds zero hidden failed attempts",
                _feas._POLICY["failed_attempts"] == 0)
        with mock.patch("scripts.trading_bot.aftershock.execution.time.time_ns", return_value=T0 + 350):
            demo = _feas.demo_attempt(
                first_tape, buy, 100, ctx=ctx, detector_module_path=DETECTOR_PATH,
                detector_callable_name=DETECTOR_CALLABLE, detector_sha256=detector_sha,
                spec_sha256=seal["frozen_json_canonical_sha256"])
        c.check("real-kernel adapter records one-attempt gas only",
                demo["outcome"] == Outcome.SCENARIO_FILLED.value and
                demo["cost_lamports"] == 105_000 and demo["clocks"]["send"] is None)

        # A restart immediately invalidates the old proof. No pre-resume or short/gapped warm-up passes.
        with mock.patch.object(_manifest.time, "time_ns", return_value=T0 + 600):
            _manifest.append_activation(
                INSTRUMENT, session_reason="restart_resume",
                last_coord=list(proof.warmup_max_coord))
        c.check("old SessionProof REFUSES after restart before new warm-up",
                _raises(lambda: attempt_order(
                    first_events, decision, sell, LatencyModel(100), ctx,
                    _price(1, Unit.LAMPORTS))))
        too_short = _feas.tape_to_events(_tape([T0 + 700], [44], slot0=200))
        c.check("post-restart incomplete warm-up REFUSES",
                _raises(lambda: _manifest.append_warmup_complete(INSTRUMENT, too_short)))
        pre_resume = _feas.tape_to_events(_tape([T0 + 700, T0 + 900], [44, 43], slot0=100))
        c.check("pre-resume warm-up coordinates REFUSE",
                _raises(lambda: _manifest.append_warmup_complete(INSTRUMENT, pre_resume)))
        restart_tape = _tape([T0 + 700, T0 + 900, T0 + 1_000, T0 + 1_200],
                             [44, 43, 42, 41], slot0=200)
        restart_events = _feas.tape_to_events(restart_tape)
        with mock.patch.object(_manifest.time, "time_ns", return_value=T0 + 950):
            restart_warmup = _manifest.append_warmup_complete(INSTRUMENT, restart_events[:2])
        second_anchor = _manifest.write_activation_anchor(INSTRUMENT)
        c.check("new restart activation root must itself be externally anchored",
                _raises(lambda: _manifest.load_session_proof(INSTRUMENT)))
        second_anchor_path = _manifest._activation_anchor_path(
            INSTRUMENT, restart_warmup["event_sha256"])
        anchored.add(second_anchor_path.resolve())
        restart_proof = _manifest.load_session_proof(INSTRUMENT)
        restart_ctx = ExecutionContext(restart_proof)
        c.check("restart proof carries monotonic resume coordinate",
                restart_proof.resume_after_coord == proof.warmup_max_coord and
                second_anchor["activation_root_sha256"] == restart_proof.activation_root_sha256)
        c.check("new context rejects old-session warm-up prefix",
                _raises(lambda: build_decision_record(
                    first_events, restart_ctx, detector_module_path=DETECTOR_PATH,
                    detector_callable_name=DETECTOR_CALLABLE, detector_sha256=detector_sha,
                    spec_sha256=seal["frozen_json_canonical_sha256"])))
        with mock.patch("scripts.trading_bot.aftershock.execution.time.time_ns", return_value=T0 + 1_050):
            restart_decision = build_decision_record(
                restart_events, restart_ctx, detector_module_path=DETECTOR_PATH,
                detector_callable_name=DETECTOR_CALLABLE, detector_sha256=detector_sha,
                spec_sha256=seal["frozen_json_canonical_sha256"])
        restart_record = attempt_order(
            restart_events, restart_decision, sell, LatencyModel(100), restart_ctx,
            _price(1_000_000, Unit.LAMPORTS))
        c.check("post-restart anchored warm-up admits only new causal evidence",
                restart_record.outcome is Outcome.SCENARIO_FILLED and restart_record.boundary_index == 3)

        raw_activation = _backdate_and_rehash_activation(activation_path)
        c.check("fully rehashed back-dated activation REFUSES against committed roots",
                _raises(lambda: _manifest.load_session_proof(INSTRUMENT)))
        activation_path.write_text(raw_activation)
        c.check("restored activation chain re-verifies", _manifest.load_session_proof(INSTRUMENT) == restart_proof)

        # Closed dependency set and whole-seal equality: omission/drift both refuse.
        raw_frozen = frozen_path.read_text()
        mutated = json.loads(raw_frozen)
        mutated["execution_realism"]["dependency_paths"].remove("scripts/b9i_quote_reproduction.py")
        frozen_path.write_text(json.dumps(mutated, indent=2, sort_keys=True) + "\n")
        c.check("declared dependency omission REFUSES compute_seal",
                _raises(lambda: _manifest.compute_seal(INSTRUMENT)))
        frozen_path.write_text(raw_frozen)
        mutated = json.loads(raw_frozen)
        mutated["unsealed_edit"] = True
        frozen_path.write_text(json.dumps(mutated, indent=2, sort_keys=True) + "\n")
        c.check("canonical frozen JSON drift REFUSES verify_seal",
                _raises(lambda: _manifest.verify_seal(INSTRUMENT)))
        frozen_path.write_text(raw_frozen)
        c.check("seal restores byte-independent canonical verification",
                _manifest.verify_seal(INSTRUMENT) == seal)


def main() -> int:
    checks = Checks()
    _cleanup()
    try:
        _schema_checks(checks)
        _sizing_and_rent_checks(checks)
        _manifest_and_execution_checks(checks)
    finally:
        _cleanup()
    print(f"\nAFTERSHOCK EXECUTION SELFTEST: {'PASS' if checks.ok else 'FAIL'} — {checks.count} checks")
    return 0 if checks.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
