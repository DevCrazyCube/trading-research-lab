#!/usr/bin/env python3
"""Empirical expected-max-|t| bar + effective-N for the options-implied sweep.

The nominal bar sqrt(2 ln N) assumes N INDEPENDENT standard-normal t-stats.
Neither assumption holds here:
  * the signals are slow autocorrelated z-scores of random-walk-like vol indices,
    which inflates the sampling sd of the t-stat above 1.0;
  * the 60 formulas are mostly long the same stress factor, so the effective
    number of independent bets is far below 60.
Both are measured rather than assumed.
"""
from __future__ import annotations

import json
import math
import pathlib
import sys

import numpy as np

sys.path.insert(0, "/home/anont/meme/scripts")
from trading_bot.optimp_sweep import (CACHE, DESIGN, OUT, build_panel,
                                      evaluate, stats, wclip, zc)

dates, IV, PX = build_panel()
n = len(dates)
dt = np.array(dates)
des = ((dt >= DESIGN[0]) & (dt <= DESIGN[1])).astype(float)
ret = np.full(n, np.nan)
ret[1:] = PX["SPY"][1:] / PX["SPY"][:-1] - 1.0
rets = {"SPY": ret}

# ---- empirical null: random walks pushed through the identical pipeline
REPS, K = 40, 60
rng = np.random.default_rng(2026)
maxes = []
alltx = []
for r in range(REPS):
    ts = []
    for _ in range(K):
        z = zc(np.cumsum(rng.normal(0, 1, n)))
        ts.append(stats(evaluate({"SPY": wclip(z)}, rets, ["SPY"], 2,
                                 np.ones(n)), des)["t"])
    ts = np.array(ts)
    alltx.append(ts)
    maxes.append(np.abs(ts).max())
maxes = np.array(maxes)
alltx = np.concatenate(alltx)
nominal = math.sqrt(2 * math.log(K))
emp = dict(reps=REPS, k=K, nominal_bar=nominal,
           empirical_mean_max_abs_t=float(maxes.mean()),
           empirical_p90_max_abs_t=float(np.percentile(maxes, 90)),
           t_sampling_sd=float(alltx.std()),
           inflation_vs_nominal=float(maxes.mean() / nominal))
print(json.dumps(emp, indent=1))

# ---- effective N from the realised pnl correlation of the 60 real formulas
z = np.load(CACHE / "pnl_L2.npz")
names = [k for k in z.files if k != "dates"]
P = np.vstack([z[k] for k in names])
m = des.astype(bool)
P = P[:, m]
P = P[:, ~np.isnan(P).any(0)]
sd = P.std(1)
keep = sd > 0
P, names2 = P[keep], [nm for nm, k in zip(names, keep) if k]
C = np.corrcoef(P)
ev = np.linalg.eigvalsh(C)
ev = ev[ev > 1e-9]
part = float((ev.sum() ** 2) / (ev ** 2).sum())      # participation ratio
mean_abs_corr = float((np.abs(C).sum() - len(C)) / (len(C) ** 2 - len(C)))
eff = dict(n_formulas=len(names2), mean_abs_pairwise_corr=mean_abs_corr,
           effective_independent_bets=part,
           bar_at_effective_N=math.sqrt(2 * math.log(max(part, 2))),
           n_eigen_above_1=int((ev > 1).sum()),
           top_eigen_share=float(ev.max() / ev.sum()))
print(json.dumps(eff, indent=1))

json.dump(dict(empirical_null=emp, effective_n=eff),
          open(OUT / "NEWTERR_optimp_null.json", "w"), indent=1)
