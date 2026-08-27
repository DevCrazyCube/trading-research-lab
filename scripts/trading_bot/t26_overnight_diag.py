#!/usr/bin/env python3
"""T26 diagnostics on the DESIGN window only: per-year stability and paired tests
against the T3 baseline. Reads the .npy net series the sweep wrote; touches no returns
outside 2016-2021.
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
    load_features, build_configs, evaluate, stats, window_rows,
    DESIGN_START, DESIGN_END, HALF_SPREAD_DESIGN_BP)


def main():
    F, RA, RB, valid, ctx = load_features()
    cfg = build_configs(F, valid, ctx)
    rows = window_rows(ctx["days"], DESIGN_START, DESIGN_END)
    series = {}
    for name, (rail, W, dmask, sn) in cfg.items():
        r = evaluate(W, dmask, rail, sn, RA, RB, ctx, rows, HALF_SPREAD_DESIGN_BP)
        if r is not None:
            series[name] = (r["dates"], r["net"])

    base_d, base_n = series["A01_T3_p10_c10"]
    out = {}
    for name, (d, n) in series.items():
        years = {}
        for y in sorted({x[:4] for x in d}):
            m = np.array([x[:4] == y for x in d])
            if m.sum() < 30:
                continue
            s = stats(n[m])
            years[y] = round(s["sharpe"], 2)
        # paired vs T3 on the common nights
        common = np.intersect1d(d, base_d)
        ia = np.searchsorted(d, common)
        ib = np.searchsorted(base_d, common)
        diff = n[ia] - base_n[ib]
        sd = diff.std(ddof=1)
        tpair = 0.0 if sd == 0 else diff.mean() / (sd / math.sqrt(diff.size))
        out[name] = {"per_year_sharpe": years,
                     "n_years_positive": sum(1 for v in years.values() if v > 0),
                     "n_years": len(years),
                     "paired_vs_T3_mean_bp": float(diff.mean() * 1e4),
                     "paired_vs_T3_t": float(tpair)}
        print(f"{name:26s} years+ {out[name]['n_years_positive']}/{out[name]['n_years']} "
              f"paired-vs-T3 {out[name]['paired_vs_T3_mean_bp']:+6.2f} bp t {tpair:+5.2f}  "
              f"{years}", flush=True)
    json.dump(out, open(WORK / "design_diagnostics.json", "w"), indent=1)


if __name__ == "__main__":
    main()
