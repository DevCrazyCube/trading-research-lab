#!/usr/bin/env python3
"""Theme-level multiple-testing bar over BOTH calendar batches (100 formulas).

Batch 1 and batch 2 are two families searched on the SAME theme, the same data and the
same design windows. The honest bar for "did anything calendar-shaped beat noise" is
therefore the max|z| over the POOLED family of 100, not over either batch alone.

This script rebuilds both families in one process, applies the SAME circular rotation to
both per replicate, studentises every formula against its own rotated null, and records
the max|z| across all 100. It also re-prints each formula's design z against that pooled
bar. No holdout data is touched.
"""
from __future__ import annotations

import json
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from scripts.trading_bot.cal_sweep import OUT, Family  # noqa: E402
from scripts.trading_bot.cal_sweep2 import Family2, build_funding_threshold  # noqa: E402


def main():
    NREP = int(sys.argv[1]) if len(sys.argv) > 1 else 400
    f1 = Family()
    f2 = Family2()
    f2.fund_thr = build_funding_threshold(f2)
    names = [("b1", r[0]) for r in f1.reg] + [("b2", r[0]) for r in f2.reg]
    N = len(names)
    print(f"pooled family: {N} formulas", flush=True)

    d1 = f1.run(window="design")
    d2 = f2.run(window="design")
    design = np.array([d1[n] if b == "b1" else d2[n] for b, n in names])

    rng = np.random.default_rng(20260820)
    cols = []
    for rep in range(NREP):
        kd = int(rng.integers(200, f1.n - 200))
        kc = int(rng.integers(2000, len(f1.cms) - 2000))
        kx = int(rng.integers(100, len(f1.xdates) - 100))
        s1 = f1.run(shift=(kd, kc, kx), window="design")
        s2 = f2.run(shift=(kd, kc, kx), window="design")
        cols.append([s1[n] if b == "b1" else s2[n] for b, n in names])
        if (rep + 1) % 20 == 0:
            print(f"  pooled null rep {rep+1}/{NREP}", flush=True)

    M = np.array(cols).T                                   # (N, NREP)
    mu = M.mean(axis=1)
    sd = np.where(M.std(axis=1) > 1e-9, M.std(axis=1), 1e-9)
    Z = (M - mu[:, None]) / sd[:, None]
    maxz = np.abs(Z).max(axis=0)
    zdes = (design - mu) / sd

    order = np.argsort(-np.abs(zdes))
    rows = [dict(batch=names[i][0], name=names[i][1],
                 design_sharpe=round(float(design[i]), 3),
                 z=round(float(zdes[i]), 2),
                 p=round(float((np.abs(M[i] - mu[i]) >= abs(design[i] - mu[i])).mean()), 4))
            for i in order]

    res = dict(
        n_formulas_pooled=N,
        replicates=NREP,
        pooled_expected_max_abs_z=round(float(maxz.mean()), 3),
        pooled_max_abs_z_p50=round(float(np.percentile(maxz, 50)), 3),
        pooled_max_abs_z_p90=round(float(np.percentile(maxz, 90)), 3),
        pooled_max_abs_z_p95=round(float(np.percentile(maxz, 95)), 3),
        pooled_max_abs_z_p99=round(float(np.percentile(maxz, 99)), 3),
        analytic_sqrt_2lnN=round(float(np.sqrt(2 * np.log(N))), 3),
        observed_design_max_abs_z=round(float(np.abs(zdes).max()), 3),
        family_wise_p_of_observed_max=round(
            float((maxz >= np.abs(zdes).max()).mean()), 4),
        ranked=rows,
    )
    (OUT / "SWEEP_calendar_session_POOLED_NULL.json").write_text(json.dumps(res, indent=1))
    print(json.dumps({k: v for k, v in res.items() if k != "ranked"}, indent=1))
    for r in rows[:20]:
        print(f"{r['z']:+7.2f} {r['design_sharpe']:+8.3f} {r['p']:7.4f}  [{r['batch']}] {r['name']}")


if __name__ == "__main__":
    main()
