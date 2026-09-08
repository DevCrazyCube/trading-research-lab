#!/usr/bin/env python3
"""AFTERSHOCK secondary-sell-resilience — detector unit tests + end-to-end engine composition.

Proves (a) the sealed detector fires on a two-proven-sell-and-recovery tape and refuses otherwise, and
(b) the full public admission chain composes on the handoff-424 engine as a SCENARIO: manifest session
proof (git-anchor mocked, as in execution_selftest) -> build_decision_record over the SS detector ->
attempt_order for a point-in-time $10 entry priced through the real b10a kernel. The positive path mocks
ONLY the owner-gated git-anchor predicate; nothing here is executable evidence.

    python -m scripts.trading_bot.aftershock.secondary_sell_selftest
"""
from __future__ import annotations

from dataclasses import replace
import pathlib
import shutil
import tempfile
from unittest import mock

from . import Refused
from . import feasibility as _feas
from . import manifest as _manifest
from . import secondary_sell_detector as _ssd
from .execution import (
    ExecutionContext, IntentKind, LatencyModel, Outcome, OrderIntent, RefusedExecution,
    SolUsdObservation, Unit, attempt_order, build_decision_record, q_lamports_for_usd,
)

INSTRUMENT = "AFTERSHOCK_SS"
DETECTOR_PATH = "scripts/trading_bot/aftershock/secondary_sell_detector.py"
T0 = 2_000_000_000_000_000_000


def _check(name, ok, detail=""):
    print(f"  [{'ok' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))
    return ok


def _raises(fn, exc=None):
    try:
        fn(); return False
    except (RefusedExecution, Refused) if exc is None else exc:
        return True
    except Exception:
        return False


def _events(specs):
    """specs = list of (received_unix_nanos, v_sol). Continuity + PumpPortal receive-time (no coords)."""
    tape = [{"mint": "MINT", "received_unix_nanos": rn, "v_sol": float(v),
             "v_tokens": 30 * 1_073_000_000 / float(v), "pool": "pump"} for rn, v in specs]
    return _feas.tape_to_events(tape)


def _warmup(n=8, base=T0 + 100_000_000, step=100_000_000, v=46.0):
    return [(base + k * step, v) for k in range(n)]


def main() -> int:
    ok = True

    # --- detector unit tests: two proven sell->recover cycles fire; fewer/none refuse ---
    # v_sol 46 -> 45.8 is a 0.2 SOL (200M lamports) external-SOL withdrawal (> the 50M threshold).
    two_cycles = _warmup() + [(T0 + 900_000_000, 45.8), (T0 + 1_000_000_000, 46.0),
                              (T0 + 1_100_000_000, 45.8), (T0 + 1_200_000_000, 46.0)]
    ev2 = _events(two_cycles)
    got = _ssd.detector(tuple(ev2), 8)
    ok &= _check("two observed withdrawal+recovery cycles FIRE exactly at recovery 2",
                 got == (8, 9, 10, 11), str(got))
    stale = two_cycles + [(T0 + 1_300_000_000, 46.0)]
    ok &= _check("completed pattern plus a later event is STALE -> no delayed entry",
                 _ssd.detector(tuple(_events(stale)), 8) == ())

    one_cycle = _warmup() + [(T0 + 900_000_000, 45.8), (T0 + 1_000_000_000, 46.0),
                             (T0 + 1_300_000_000, 46.0)]
    ok &= _check("only ONE cycle -> no trade (empty)", _ssd.detector(tuple(_events(one_cycle)), 8) == (), "")

    no_recovery = _warmup() + [(T0 + 900_000_000, 45.8), (T0 + 1_000_000_000, 45.7),
                               (T0 + 1_100_000_000, 45.6), (T0 + 1_300_000_000, 45.6)]
    ok &= _check("sells without recovery -> no trade (empty)", _ssd.detector(tuple(_events(no_recovery)), 8) == (), "")

    tiny_sells = _warmup() + [(T0 + 900_000_000, 45.99), (T0 + 1_000_000_000, 46.0),
                              (T0 + 1_100_000_000, 45.99), (T0 + 1_200_000_000, 46.0),
                              (T0 + 1_300_000_000, 46.0)]   # 0.01 SOL sells < 0.05 threshold
    ok &= _check("sells below our-size threshold -> no trade (empty)", _ssd.detector(tuple(_events(tiny_sells)), 8) == (), "")
    ok &= _check("0.05 SOL coverage is not mislabeled as universal $10 sizing",
                 _ssd.position_size_is_covered(50_000_000)
                 and _ssd.position_size_is_covered(25_000_000)
                 and not _ssd.position_size_is_covered(100_000_000))

    # --- end-to-end composition on the engine (git-anchor mocked = the owner-gated commit stand-in) ---
    ok &= _end_to_end()

    print("\nAFTERSHOCK SECONDARY-SELL SELFTEST: " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


def _fixture_paths():
    return [_manifest._seal_path(INSTRUMENT), _manifest._activation_path(INSTRUMENT),
            *_manifest.RESEARCH.glob(f"{INSTRUMENT}_ACTIVATION_ANCHOR_*.json")]


def _end_to_end() -> bool:
    ok = True
    # Keep every transient seal/activation artifact in a private temp directory.  A selftest must never
    # unlink a production evidence path, even after the real instrument is eventually anchored.
    production_research = _manifest.RESEARCH
    with tempfile.TemporaryDirectory(prefix="aftershock_ss_selftest_") as td:
      test_research = pathlib.Path(td)
      for name in (f"{INSTRUMENT}_PREREGISTRATION.md", f"{INSTRUMENT}_FROZEN.json"):
        shutil.copy2(production_research / name, test_research / name)
      with mock.patch.object(_manifest, "RESEARCH", test_research):
        seal = _manifest.write_seal(INSTRUMENT)
        detector_sha = seal["dependency_sha256"][DETECTOR_PATH]
        anchored = {_manifest._seal_path(INSTRUMENT).resolve()}
        committed = lambda path: path.resolve() in anchored   # noqa: E731

        # decision fires exactly on recovery 2 (T0+1200ms); a later event brackets the scenario fill
        full = _warmup() + [(T0 + 900_000_000, 45.8), (T0 + 1_000_000_000, 46.0),
                            (T0 + 1_100_000_000, 45.8), (T0 + 1_200_000_000, 46.0),
                            (T0 + 1_600_000_000, 46.0)]
        events = _events(full)
        warmup_events = events[:8]

        with mock.patch.object(_manifest, "_git_committed", side_effect=committed):
            with mock.patch.object(_manifest.time, "time_ns", return_value=T0):
                _manifest.append_activation(INSTRUMENT, session_reason="first_activation", last_coord=None)
            with mock.patch.object(_manifest.time, "time_ns", return_value=T0 + 850_000_000):
                warmup = _manifest.append_warmup_complete(INSTRUMENT, warmup_events)
            anchor = _manifest.write_activation_anchor(INSTRUMENT)
            ok &= _check("uncommitted activation root REFUSES SessionProof (owner-gate closed)",
                         _raises(lambda: _manifest.load_session_proof(INSTRUMENT)))
            anchored.add(_manifest._activation_anchor_path(INSTRUMENT, warmup["event_sha256"]).resolve())
            proof = _manifest.load_session_proof(INSTRUMENT)
            ctx = ExecutionContext(proof)

            forged = replace(proof, activation_anchor_sha256="b" * 64)
            ok &= _check("caller-forged SessionProof REFUSES at the SS decision path",
                         _raises(lambda: build_decision_record(
                             events, ExecutionContext(forged), detector_module_path=DETECTOR_PATH,
                             detector_callable_name="detector", detector_sha256=detector_sha,
                             spec_sha256=proof.frozen_json_canonical_sha256)))

            with mock.patch("scripts.trading_bot.aftershock.execution.time.time_ns", return_value=T0 + 1_200_000_000):
                decision = build_decision_record(events, ctx, detector_module_path=DETECTOR_PATH,
                                                 detector_callable_name="detector", detector_sha256=detector_sha,
                                                 spec_sha256=proof.frozen_json_canonical_sha256)
            ok &= _check("decision signal is recovery 2 (max evidence coord)", decision.signal_index == 11, str(decision.signal_index))

            # point-in-time $10 -> exact-quote buy through the real b10a kernel; lands at the later boundary
            solusd = SolUsdObservation("200.00", T0 + 1_190_000_000, "point-in-time-feed", "c" * 64)
            q = q_lamports_for_usd("10.00", solusd, decision_unix_nanos=T0 + 1_200_000_000, max_staleness_nanos=100_000_000)
            ok &= _check("point-in-time $10 size is covered by the fixed 0.05 SOL evidence floor",
                         _ssd.position_size_is_covered(q), f"q={q}")
            buy = OrderIntent(IntentKind.EXACT_QUOTE_BUY, q, 1)
            entry = attempt_order(events, decision, buy, LatencyModel(100_000_000), ctx, _feas.kernel_price_fn())
            ok &= _check("$10 entry composes on the engine -> SCENARIO_FILLED at a later boundary via real kernel",
                         entry.outcome is Outcome.SCENARIO_FILLED and entry.boundary_index == 12 and entry.out_unit is Unit.ATOMS,
                         f"outcome={entry.outcome} boundary={entry.boundary_index} q={q}")
            ok &= _check("scenario labels carried (uncalibrated, not executable)",
                         "SIMULATED_OBSERVED_PATH" in entry.labels and "CALIBRATION_UNCALIBRATED" in entry.labels)
    return ok


if __name__ == "__main__":
    raise SystemExit(main())
