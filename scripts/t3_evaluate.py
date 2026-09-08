#!/usr/bin/env python3
"""T3 -- design phase, freeze, and held-out test. Two commands, in that order, never merged.

    python3 scripts/t3_evaluate.py design   # 2016-2021 only. Writes FROZEN_CONFIG.json.
    python3 scripts/t3_evaluate.py test     # refuses unless FROZEN_CONFIG.json already exists.

The separation is the point: `test` reads the frozen file and cannot choose anything. If the
frozen file is absent, `test` refuses rather than picking a configuration on the spot.

Rule: research/trading_bot/T3_PREREGISTRATION.md
      sha256 401fd377ce1a6e3d60d618a86c36a7834bdafe81c0240e11540b9c038fe4f29f
"""

from __future__ import annotations

import gzip
import hashlib
import json
import math
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.t3_pressure_reversal as t3                                    # noqa: E402
from scripts.trading_bot.stats import (annualised_sharpe, cagr, deflated_sharpe,   # noqa: E402
                                       max_drawdown, moments, permutation_test,
                                       sharpe_variance_from_trials)

OUT = ROOT / "research" / "trading_bot"
FROZEN = OUT / "T3_FROZEN_CONFIG.json"
PREREG_SHA = "401fd377ce1a6e3d60d618a86c36a7834bdafe81c0240e11540b9c038fe4f29f"


def load_panel():
    with gzip.open(t3.CACHE / "panel.json.gz", "rt") as fh:
        blob = json.load(fh)
    return blob["panel"], blob["stats"]


def series_report(dates, rets, label):
    m = moments(rets)
    n = m["n"]
    sr = m["mean"] / m["sd"]
    curve = [1.0]
    for r in rets:
        curve.append(curve[-1] * (1.0 + r))
    import datetime
    ns = [int(datetime.datetime.fromisoformat(d).timestamp()) * 1_000_000_000 for d in dates]
    return {
        "label": label,
        "n_nights": n,
        "mean_per_night_bp": m["mean"] * 1e4,
        "sd_per_night_bp": m["sd"] * 1e4,
        "t_stat": sr * math.sqrt(n),
        "sharpe_per_observation": sr,
        "annualised_sharpe": annualised_sharpe(rets, 252),
        "annualised_return_pct": m["mean"] * 252 * 100,
        "cagr_pct": cagr(curve, ns[0], ns[-1] + 86_400 * 1_000_000_000) * 100,
        "max_drawdown_pct": max_drawdown(curve)["max_drawdown"] * 100,
        "skew": m["skew"],
        "kurtosis_non_excess": m["kurtosis"],
        "final_equity": curve[-1],
    }


def design():
    panel, pstats = load_panel()
    uni500 = t3.build_universe(500)
    days = [d for d in sorted(panel) if d <= t3.DESIGN_END]
    print(f"design nights available: {len(days)}", flush=True)

    hs = t3.cache_json("half_spread_design",
                       lambda: t3.measure_half_spread(panel, uni500, days))
    h = hs["median_half_spread_bp"]
    print("design-period half-spread:", json.dumps(hs), flush=True)

    grid, results = [], []
    for w in t3.SIGNAL_WINDOWS:
        for cut in t3.CUTS:
            for top in t3.UNIVERSES:
                d, net, gross, ctrl, mem, legs = t3.run_config(
                    panel, uni500, window=w, cut=cut, top_n=top, half_spread_bp=h,
                    day_filter=lambda x: x <= t3.DESIGN_END)
                rep = series_report(d, net, f"w{w}_cut{cut}_top{top}")
                rep.update({"window": w, "cut": cut, "top_n": top,
                            "gross_annualised_sharpe": annualised_sharpe(gross, 252),
                            "gross_mean_per_night_bp": moments(gross)["mean"] * 1e4,
                            "control_mean_per_night_bp": moments(ctrl)["mean"] * 1e4})
                results.append(rep)
                grid.append(rep["sharpe_per_observation"])
                print(f"  w={w:2d} cut={cut} top={top}: net {rep['mean_per_night_bp']:+.3f} bp/night "
                      f"t={rep['t_stat']:+.2f} SR={rep['annualised_sharpe']:+.2f} "
                      f"(gross {rep['gross_mean_per_night_bp']:+.3f} bp)", flush=True)

    best = max(results, key=lambda r: r["annualised_sharpe"])
    frozen = {
        "preregistration_sha256": PREREG_SHA,
        "design_period": [t3.START, t3.DESIGN_END],
        "trials_declared": 8,
        "trial_sharpes_per_observation": grid,
        "sharpe_variance_across_trials": sharpe_variance_from_trials(grid),
        "frozen_config": {"window": best["window"], "cut": best["cut"], "top_n": best["top_n"]},
        "design_half_spread": hs,
        "design_results": results,
        "panel_stats": pstats,
        "note": ("Frozen by highest design-period NET annualised Sharpe, as pre-registered. "
                 "The held-out period 2022-01-03..2026-08-14 has not been evaluated at the time "
                 "this file was written."),
    }
    FROZEN.write_text(json.dumps(frozen, indent=2))
    print("\nFROZEN:", json.dumps(frozen["frozen_config"]), flush=True)
    print("sha256:", hashlib.sha256(FROZEN.read_bytes()).hexdigest(), flush=True)


def test():
    if not FROZEN.exists():
        raise SystemExit("T3_FROZEN_CONFIG.json is absent. The design phase must run and freeze "
                         "a configuration BEFORE the held-out period is touched. Refusing.")
    frozen = json.loads(FROZEN.read_text())
    cfg = frozen["frozen_config"]
    print("frozen config:", cfg, "  frozen-file sha256:",
          hashlib.sha256(FROZEN.read_bytes()).hexdigest(), flush=True)

    panel, pstats = load_panel()
    uni500 = t3.build_universe(500)
    days = [d for d in sorted(panel) if d >= t3.TEST_START]
    print(f"held-out nights available: {len(days)}", flush=True)

    hs = t3.cache_json("half_spread_test",
                       lambda: t3.measure_half_spread(panel, uni500, days))
    h = hs["median_half_spread_bp"]
    print("test-period half-spread:", json.dumps(hs), flush=True)

    def run(half, exit_half=0.0):
        return t3.run_config(panel, uni500, window=cfg["window"], cut=cfg["cut"],
                             top_n=cfg["top_n"], half_spread_bp=half, exit_spread_bp=exit_half,
                             day_filter=lambda x: x >= t3.TEST_START)

    dates, net, gross, ctrl, members, legs = run(h)
    out = {
        "preregistration_sha256": PREREG_SHA,
        "frozen_config": cfg,
        "frozen_file_sha256": hashlib.sha256(FROZEN.read_bytes()).hexdigest(),
        "test_period": [t3.TEST_START, t3.END],
        "test_half_spread": hs,
        "net": series_report(dates, net, "net at measured half-spread"),
        "gross_zero_cost": series_report(dates, gross, "gross, zero cost (B19P diagnostic)"),
        "equal_weight_control": series_report(dates, ctrl, "equal-weight universe overnight"),
        # Each leg against the same-night equal-weight control: which side, if either, carries
        # the effect. A long-only or short-only result is a different (and worse) trade.
        "long_leg_vs_control": series_report(
            dates, [a - c for (a, _b), c in zip(legs, ctrl)], "fade-buy decile minus control"),
        "short_leg_vs_control": series_report(
            dates, [c - b for (_a, b), c in zip(legs, ctrl)], "control minus fade-sell decile"),
    }

    ladder = {}
    for name, (hh, ex) in {
        "h (measured)": (h, 0.0),
        "2h": (2 * h, 0.0),
        "4h": (4 * h, 0.0),
        "h entry + h exit (auction rail not free)": (h, h),
        "zero cost": (0.0, 0.0),
    }.items():
        _d, n_, _g, _c, _m, _l = run(hh, ex)
        mm = moments(n_)
        ladder[name] = {"mean_per_night_bp": mm["mean"] * 1e4,
                        "t_stat": mm["mean"] / mm["sd"] * math.sqrt(mm["n"]),
                        "annualised_sharpe": annualised_sharpe(n_, 252),
                        "annualised_return_pct": mm["mean"] * 252 * 100}
    out["stress_ladder"] = ladder

    # --- DSR: the paired instrument. The L/S spread IS the paired difference (the equal-weight
    # control cancels out of a dollar-neutral book by construction), which is why it is deflated
    # directly and the control is reported beside it rather than subtracted twice.
    sv = frozen["sharpe_variance_across_trials"]
    out["dsr_trials_8"] = deflated_sharpe(net, trials=8, sharpe_variance=sv)
    out["dsr_trials_24_sensitivity"] = deflated_sharpe(net, trials=24, sharpe_variance=sv)

    # --- the pre-registered cross-sectional label permutation
    out["label_permutation"] = t3.label_permutation_fast(members, trials=10_000, seed=20260816)

    # --- the T2 module's exposure-timing permutation. It is a WIRING CHECK here, not evidence:
    # this book's exposure is constant (fully invested, dollar neutral, every night), and a
    # constant exposure permutes to itself, so p MUST come back 1.0. The instrument that
    # actually bears on the claim is the cross-sectional label permutation above -- FINDINGS 5c,
    # "permutation for classifiers", and the label assignment is the classifier.
    out["exposure_timing_permutation_WIRING_CHECK_ONLY"] = permutation_test(
        [1.0] * len(net), net, trials=10_000, seed=20260816)

    # --- gross-only significance, so a friction kill is distinguishable from a signal kill
    mg = moments(gross)
    out["gross_t_stat"] = mg["mean"] / mg["sd"] * math.sqrt(mg["n"])

    verdict = []
    if out["net"]["mean_per_night_bp"] <= 0:
        verdict.append("KILL 1: net mean per night <= 0")
    if out["label_permutation"]["p_right_tail"] >= 0.05:
        verdict.append("KILL 2: label-permutation p >= 0.05")
    if out["dsr_trials_8"]["dsr"] < 0.95:
        verdict.append("KILL 3: DSR < 0.95 at trials=8")
    out["kill_conditions_triggered"] = verdict
    out["verdict"] = "DEAD" if verdict else "SURVIVES"

    (OUT / "T3_HELDOUT_RESULT.json").write_text(json.dumps(out, indent=2))
    print(json.dumps({k: v for k, v in out.items()
                      if k not in ("stress_ladder",)}, indent=2)[:4000], flush=True)
    print("\nSTRESS LADDER:", json.dumps(ladder, indent=2), flush=True)
    print("\nVERDICT:", out["verdict"], verdict, flush=True)


if __name__ == "__main__":
    {"design": design, "test": test}[sys.argv[1]]()
