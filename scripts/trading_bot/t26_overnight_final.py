#!/usr/bin/env python3
"""T26 final arithmetic: deflated Sharpe on the held-out window at the HONEST trial
count (every config the sweep evaluated), and the paired held-out difference between
the sweep winner and the T3 baseline.
"""
from __future__ import annotations

import json
import math
import pathlib
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[2]
WORK = ROOT / "research" / "data" / "t26_cache"
sys.path.insert(0, str(ROOT))
from scripts.trading_bot.stats import deflated_sharpe, sharpe_variance_from_trials  # noqa: E402

PICKS = ["A01_T3_p10_c10", "A08_p10_resid_day", "A09_p10_over_vol", "A36_p10_hivolregime"]


def main():
    design = json.load(open(WORK / "design_results.json"))
    trials = len(design)
    # variance of the per-observation Sharpes actually tried -- the honest input to the
    # deflation, not an assumed one.
    per_obs = [v["net"]["sharpe"] / math.sqrt(252.0) for v in design.values()]
    var = sharpe_variance_from_trials(per_obs)
    out = {"trials": trials, "sharpe_variance_of_trials": var,
           "expected_max_sharpe_under_null_SE_units": math.sqrt(2 * math.log(trials))}

    for name in PICKS:
        r = np.load(WORK / f"net_test_{name}.npy")
        d = deflated_sharpe(list(r), trials=trials, sharpe_variance=var)
        out[name] = d
        print(f"{name:26s} held-out DSR at {trials} trials: {d['dsr']:.4f}  "
              f"(bar {d['benchmark_sharpe_per_observation']:.5f}/obs, observed "
              f"{d['observed_sharpe_per_observation']:.5f}/obs, z {d['z']:.2f}, "
              f"passes {d['passes_at_0p95']})", flush=True)

    a = np.load(WORK / "net_test_A08_p10_resid_day.npy")
    b = np.load(WORK / "net_test_A01_T3_p10_c10.npy")
    diff = a - b
    t = diff.mean() / (diff.std(ddof=1) / math.sqrt(diff.size))
    out["A08_minus_A01_heldout"] = {"mean_bp": float(diff.mean() * 1e4), "t": float(t),
                                    "n": int(diff.size)}
    print(f"paired held-out A08 - A01: {diff.mean()*1e4:+.3f} bp, t {t:+.2f}", flush=True)
    json.dump(out, open(WORK / "final_stats.json", "w"), indent=1)


if __name__ == "__main__":
    main()
