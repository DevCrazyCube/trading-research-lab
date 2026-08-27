#!/usr/bin/env python3
"""Hermetic wiring check -- no network, no ledger written. Proves the enforcement and the R-math.

Verifies, on synthetic data only:
  * the frozen spec loads and its pre-registration hash matches;
  * the proposer REJECTS a missing stop, R:R < 2, a wrong-direction stop/target, an over-1% risk, a
    6th concurrent setup, and an unknown instrument -- and ACCEPTS a clean 2:1 setup;
  * the freeze produces a stable, re-verifiable sha256;
  * the resolver's R-math is correct (target -> +R:R, stop -> -1, adverse tie -> stop, horizon mark);
  * the forward-only assertion DISCARDS a pre-freeze bar;
  * the kill switch HALTS a significantly-negative stream past N_min and spares a noisy positive.
"""

from __future__ import annotations

import json
import sys

from . import Refused
from .frozen import frozen_spec
from . import proposer, resolve as resolver, scoring


def _expect_refused(fn, label):
    try:
        fn()
    except Refused:
        return
    raise Refused(f"selftest FAILED: expected a Refused for {label}, got none")


def run_selftest() -> int:
    spec = frozen_spec()
    out = {"framing": "hermetic wiring check; no network, no ledger, no orders"}

    base = {"instrument": "SPY", "asset_class": "equity", "direction": "long",
            "entry_ref": 100.0, "stop": 99.0, "target": 103.0, "horizon_hours": 24,
            "thesis": "synthetic clean setup for the wiring test with a >=2:1 reward to risk ratio.",
            "confidence": 0.5, "event_ids": ["deadbeef"]}

    # ACCEPT a clean 2:1 (reward 3, risk 1 -> R:R 3.0).
    good = proposer.validate_setup(base, spec, n_open=0)
    assert abs(good["reward_to_risk"] - 3.0) < 1e-9, "R:R computed wrong"
    frozen = proposer.freeze_setup(good, proposed_utc="2026-08-23T12:00:00+00:00")
    assert proposer.freeze_setup(dict(good), proposed_utc="2026-08-23T12:00:00+00:00")["setup_sha256"] \
        == frozen["setup_sha256"], "freeze hash not stable"
    out["accepts_clean_2to1"] = True
    out["freeze_hash_stable"] = True

    # REJECTIONS.
    _expect_refused(lambda: proposer.validate_setup(dict(base, stop=None), spec), "missing stop")
    _expect_refused(lambda: proposer.validate_setup(dict(base, target=101.0), spec), "R:R < 2 (=1.0)")
    _expect_refused(lambda: proposer.validate_setup(dict(base, stop=101.0), spec),
                    "long with stop above entry")
    _expect_refused(lambda: proposer.validate_setup(dict(base, account_risk_pct=2.0), spec),
                    "risk > 1%")
    _expect_refused(lambda: proposer.validate_setup(base, spec, n_open=5), "6th concurrent setup")
    _expect_refused(lambda: proposer.validate_setup(dict(base, instrument="ENRON"), spec),
                    "unknown instrument")
    _expect_refused(lambda: proposer.validate_setup(dict(base, horizon_hours=999), spec),
                    "horizon out of bounds")
    out["rejects_all_rule_violations"] = True

    # RESOLVER R-math on synthetic bars. entry 100, stop 99, target 103, risk 1, R:R 3.
    fe = 1_000_000  # freeze epoch
    # Drive the private walker directly on synthetic bars (long, entry 100, stop 99, target 103).
    def _run(bars):
        return resolver._walk("long", 100.0, 99.0, 103.0, 1.0, bars,
                              spec["rules"]["adverse_tie_break"])

    hit_target = _run([(fe + 10, 103.5, 100.0, 103.0)])
    assert hit_target[1] == "target" and abs(hit_target[0] - 3.0) < 1e-9, f"target R wrong: {hit_target}"
    hit_stop = _run([(fe + 10, 100.2, 98.5, 99.0)])
    assert hit_stop[1] == "stop" and abs(hit_stop[0] + 1.0) < 1e-9, f"stop R wrong: {hit_stop}"
    tie = _run([(fe + 10, 103.5, 98.5, 100.0)])
    assert tie[1] == "stop_adverse_tie" and abs(tie[0] + 1.0) < 1e-9, f"adverse tie wrong: {tie}"
    horizon = _run([(fe + 10, 101.0, 99.5, 101.0)])  # neither touched -> mark at 101 -> +1R
    assert horizon[1] == "horizon_mark" and abs(horizon[0] - 1.0) < 1e-9, f"horizon mark wrong: {horizon}"
    out["resolver_r_math_correct"] = True

    # Forward-only assertion discards a pre-freeze bar.
    pre = [(fe - 5, 200.0, 0.1, 103.0), (fe + 5, 101.0, 100.0, 101.0)]
    kept = resolver._assert_forward(pre, fe, "SPY")
    assert kept == [(fe + 5, 101.0, 100.0, 101.0)], "forward-only assertion did not drop pre-freeze bar"
    out["forward_only_drops_pre_freeze_bar"] = True

    # Kill switch: a steady loser past N_min HALTS; a noisy positive does not.
    losers = [-1.0 if i % 3 else -0.5 for i in range(35)]  # all negative, n>=N_min
    winners = [3.0 if i % 2 else -1.0 for i in range(35)]  # noisy but positive mean
    kL = scoring.kill_check(losers, spec)
    kW = scoring.kill_check(winners, spec)
    assert kL["verdict"].startswith("HALTED"), f"kill did not halt a steady loser: {kL['verdict']}"
    assert not kW["verdict"].startswith("HALTED"), f"kill wrongly halted a noisy winner: {kW['verdict']}"
    out["kill_halts_loser_spares_winner"] = True

    # Expectancy arithmetic.
    exp = scoring._expectancy([3.0, 3.0, -1.0, -1.0])  # winrate .5, avgWin 3, avgLoss 1 -> +1.0
    assert abs(exp["expectancy_R"] - 1.0) < 1e-9, f"expectancy wrong: {exp}"
    out["expectancy_arithmetic_correct"] = True

    out["ALL_PASSED"] = True
    json.dump(out, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    return 0
