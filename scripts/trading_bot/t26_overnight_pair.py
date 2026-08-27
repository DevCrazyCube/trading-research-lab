#!/usr/bin/env python3
"""T26: paired SHARPE-difference bootstrap against the T3 baseline, plus the
conditioner subgroup tests (does the conditioner actually add anything, or is the
subsample just a smaller draw of the same edge?). DESIGN window only.
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
from scripts.trading_bot.t26_overnight_sweep import (  # noqa: E402
    load_features, build_configs, evaluate, window_rows,
    DESIGN_START, DESIGN_END, HALF_SPREAD_DESIGN_BP)

ANN = math.sqrt(252.0)


def sharpe(x):
    sd = x.std(ddof=1)
    return 0.0 if sd == 0 else x.mean() / sd * ANN


def main():
    F, RA, RB, valid, ctx = load_features()
    cfg = build_configs(F, valid, ctx)
    rows = window_rows(ctx["days"], DESIGN_START, DESIGN_END)
    S = {}
    for name, (rail, W, dmask, sn) in cfg.items():
        r = evaluate(W, dmask, rail, sn, RA, RB, ctx, rows, HALF_SPREAD_DESIGN_BP)
        if r is not None:
            S[name] = (r["dates"], r["net"])

    rng = np.random.default_rng(7)
    bd, bn = S["A01_T3_p10_c10"]
    out = {}
    for name, (d, n) in S.items():
        common = np.intersect1d(d, bd)
        a = n[np.searchsorted(d, common)]
        b = bn[np.searchsorted(bd, common)]
        obs = sharpe(a) - sharpe(b)
        idx = rng.integers(0, a.size, size=(2000, a.size))
        boot = np.array([sharpe(a[i]) - sharpe(b[i]) for i in idx])
        out[name] = {"n_common": int(a.size), "sharpe": round(sharpe(a), 3),
                     "d_sharpe_vs_T3": round(obs, 3),
                     "d_sharpe_ci95": [round(float(np.quantile(boot, .025)), 3),
                                       round(float(np.quantile(boot, .975)), 3)],
                     "p_two_sided": round(float(2 * min((boot <= 0).mean(),
                                                        (boot >= 0).mean())), 4)}
        o = out[name]
        print(f"{name:26s} SR {o['sharpe']:+6.2f}  dSR vs T3 {o['d_sharpe_vs_T3']:+6.2f} "
              f"CI {o['d_sharpe_ci95']}  p {o['p_two_sided']}", flush=True)

    # conditioner subgroup tests: is the ON group's mean per night different from the OFF group's?
    pairs = [("A36_p10_hivolregime", "A37_p10_lovolregime"),
             ("A38_p10_downmkt", "A39_p10_upmkt"),
             ("A40_p10_tom", "A41_p10_nontom"),
             ("A43_p10_friday", "A42_p10_no_friday")]
    sub = {}
    for on, off in pairs:
        x = S[on][1]
        y = S[off][1]
        se = math.sqrt(x.var(ddof=1) / x.size + y.var(ddof=1) / y.size)
        t = (x.mean() - y.mean()) / se
        sub[f"{on} vs {off}"] = {"mean_on_bp": round(float(x.mean() * 1e4), 2),
                                 "mean_off_bp": round(float(y.mean() * 1e4), 2),
                                 "n_on": int(x.size), "n_off": int(y.size),
                                 "welch_t": round(float(t), 2)}
        print(f"CONDITIONER {on} vs {off}: {x.mean()*1e4:+.2f} vs {y.mean()*1e4:+.2f} bp, "
              f"Welch t {t:+.2f}", flush=True)
    json.dump({"paired_sharpe": out, "conditioners": sub},
              open(WORK / "design_paired.json", "w"), indent=1)


if __name__ == "__main__":
    main()
