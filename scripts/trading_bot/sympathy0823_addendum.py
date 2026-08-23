#!/usr/bin/env python3
"""Addendum to INVENT_0823 `sympathy`, run AFTER the shortlist and held-out stages:

  1. the zero-spread lower bound -- how many formulas lose money even if the half-spread were
     literally zero and only the SEC 31 / FINRA TAF pass-through were charged;
  2. rho1 of the first difference of every traded hedged spread (pre-registration gate 5);
  3. a post-hoc held-out read on C3b, the ONLY formula whose gross Sharpe does not decay as the
     fill is pushed later. This is explicitly OUTSIDE the pre-registered shortlist and is
     labelled as a diagnostic, not evidence.
"""
import json

import numpy as np

from scripts.trading_bot.sympathy0823 import (
    DESIGN, HELDOUT, OUT, GROUPS, Panel, all_formulas, evaluate, sharpe, rolling_stats,
    INDEX_HEAVIES, check_prereg,
)

check_prereg()
P = Panel()
F = all_formulas(P)
m = P.window(DESIGN)
res = {}

# ---- 1. zero-spread lower bound (only the 0.15 bp/turnover regulatory pass-through survives)
full = P.cost_rt.copy()
P.cost_rt = np.full_like(full, 2.0 * 0.15 * 1e-4)
zero = {}
for n, tr in F.items():
    pnl, _ = evaluate(P, tr, m, lag=1)
    zero[n] = round(sharpe(pnl), 3)
P.cost_rt = full
res["zero_spread_net_sharpe_design"] = zero
res["n_negative_at_zero_spread"] = int(sum(1 for v in zero.values() if v < 0))
res["n_formulas"] = len(zero)

# ---- 2. rho1 of the first difference of each traded hedged spread
rho = {}
c = P.close.astype(np.float64)
for gname, (leader, peers) in list(GROUPS.items()) + [(f"IDX_{h}", (h, ["QQQ"])) for h in INDEX_HEAVIES]:
    cols = [P.idx[p] for p in peers if p in P.idx]
    if not cols:
        continue
    beta, _ = rolling_stats(P, leader, cols)
    L = P.idx[leader]
    for j, col in enumerate(cols):
        b = np.nanmedian(beta[m][:, j])
        s = np.log(c[m][:, :, col]) - b * np.log(c[m][:, :, L])
        ds = np.diff(s, axis=1).ravel()
        ds = ds[np.isfinite(ds)]
        r1 = float(np.corrcoef(ds[:-1], ds[1:])[0, 1])
        rho[f"{gname}:{P.syms[col]}-{b:.2f}x{leader}"] = round(r1, 3)
vals = np.array(list(rho.values()))
res["rho1_hedged_spreads"] = rho
res["rho1_summary"] = {"n": len(rho), "min": float(vals.min()), "median": float(np.median(vals)),
                       "max": float(vals.max()),
                       "n_failing_gate_-0.35": int((vals <= -0.35).sum())}

# ---- 3. post-hoc held-out read on C3b (NOT a promotion; outside the pre-registration)
mh = P.window(HELDOUT)
ph = {}
for n in ["C3b_HEAVY_TO_INDEX_k3_h6_HEDGED", "C3a_HEAVY_TO_INDEX_k3_h6"]:
    row = {}
    for lag in (0, 1, 2, 3, 6):
        pnl, dg = evaluate(P, F[n], mh, lag=lag)
        row[f"net_sharpe_lag{lag}"] = round(sharpe(pnl), 3)
        g, _ = evaluate(P, F[n], mh, lag=lag, gross_only=True)
        row[f"gross_sharpe_lag{lag}"] = round(sharpe(g), 3)
        if lag == 1:
            row.update(dg)
    ph[n] = row
res["POSTHOC_heldout_unregistered"] = {
    "warning": "read AFTER the shortlist was frozen and outside it; a diagnostic, not evidence",
    "formulas": ph,
}

(OUT / "INVENT_0823_sympathy_ADDENDUM.json").write_text(json.dumps(res, indent=1))
print(json.dumps({k: v for k, v in res.items() if k != "rho1_hedged_spreads"}, indent=1))
