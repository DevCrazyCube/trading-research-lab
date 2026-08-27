#!/usr/bin/env python3
"""Empirical null for Family A: what does a TETHER-LESS pair book score?

sqrt(2 ln 2N) is the right bar only when the individual test statistic is an honest t.  In
this family it is not: the pairs overlap, the weekly observations of a 20-week-hold book are
serially dependent, and every CEF pair shares a discount-sentiment factor.  So the bar is
measured instead: draw pair-sets of the SAME SIZE from cross-category (untethered) CEF pairs,
run the IDENTICAL formula, and read off the distribution of design t and held-out Sharpe.
"""
from __future__ import annotations

import json
import math
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from scripts.trading_bot.invent0822_pairtether import (  # noqa: E402
    DESIGN_END, HALF_SPREAD_BP, HALF_SPREAD_P90_BP, build_pairs, build_panel,
    random_pairs, rollz, run_book, spread_matrix, summarise)

OUT = pathlib.Path(__file__).resolve().parents[2] / "research" / "trading_bot"

DRAWS = 300
SIZES = (91, 46)


def main():
    pan = build_panel()
    grid = pan["grid"]
    d0 = sum(1 for d in grid if d <= DESIGN_END)
    T = len(grid)
    _, ok = build_pairs(pan, d0)
    pool = random_pairs(pan, ok, d0, n=1500, seed=99)
    print(f"null pool: {len(pool)} untethered cross-category pairs", flush=True)

    rng = np.random.default_rng(4242)
    out = {}
    for size in SIZES:
        dt, ds, hs, hn = [], [], [], []
        for d in range(DRAWS):
            idx = rng.choice(len(pool), size, replace=False)
            ps = [pool[k] for k in idx]
            Z = rollz(spread_matrix(pan, ps, "prem"), 26)
            gD, nD, _ = run_book(pan, ps, Z, K=2.0, X=0.5, maxhold=20, lo=26, hi=d0)
            _, nH, _ = run_book(pan, ps, Z, K=2.0, X=0.5, maxhold=20, lo=d0, hi=T)
            _, nHs, _ = run_book(pan, ps, Z, K=2.0, X=0.5, maxhold=20, rkey="R_LAG1",
                                 hs_bp=HALF_SPREAD_P90_BP, lo=d0, hi=T)
            dt.append(summarise(gD)["t"])
            ds.append(summarise(gD)["ann_sharpe"])
            hn.append(summarise(nH)["ann_sharpe"])
            hs.append(summarise(nHs)["ann_sharpe"])
            if (d + 1) % 50 == 0:
                print(f"  size {size}: {d+1}/{DRAWS}", flush=True)
        def q(v):
            v = np.array([x for x in v if np.isfinite(x)], float)
            return dict(n=int(v.size), mean=float(v.mean()), sd=float(v.std(ddof=1)),
                        p50=float(np.percentile(v, 50)), p90=float(np.percentile(v, 90)),
                        p95=float(np.percentile(v, 95)), p99=float(np.percentile(v, 99)),
                        max=float(v.max()))
        out[str(size)] = dict(design_gross_t=q(dt), design_gross_sharpe=q(ds),
                              held_net_sharpe=q(hn), held_stressed_sharpe=q(hs))
        print(f"size {size}: design gross t p50 {out[str(size)]['design_gross_t']['p50']:.2f} "
              f"p95 {out[str(size)]['design_gross_t']['p95']:.2f} "
              f"max {out[str(size)]['design_gross_t']['max']:.2f} | "
              f"held stressed Sharpe p95 "
              f"{out[str(size)]['held_stressed_sharpe']['p95']:.2f}", flush=True)

    (OUT / "INVENT_0822_pairtether_A_null.json").write_text(
        json.dumps(dict(draws=DRAWS, sizes=list(SIZES), null=out), indent=1, default=float))


if __name__ == "__main__":
    main()
