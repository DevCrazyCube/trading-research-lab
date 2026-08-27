#!/usr/bin/env python3
"""Two diagnoses that decide how to read the null.

D1  GROSS vs NET.  The 109 live formulas have mean design t = -0.62.  Either the
    mechanism runs systematically BACKWARDS, or that tilt is nothing but turnover
    cost.  Re-run every formula with costs and borrow set to zero and compare.

D2  IS THE ONE ABOVE-BAR RESULT AN OPTIONS SIGNAL AT ALL?  H6_XS_IVoverRV5 hits
    |t|=3.36 on design and -2.02 on holdout -- but in the sign OPPOSITE to its
    stated mechanism.  Before anyone is tempted to flip it, check whether its
    weights are a near-STATIC long/short tilt across assets (short the high-vol
    ETFs, long the low-vol ones), in which case it is an asset-class factor bet
    wearing an options costume and carries no option information at all.
"""
from __future__ import annotations

import json
import math
import sys

import numpy as np

sys.path.insert(0, "/home/anont/meme/scripts")
import trading_bot.optimp_sweep as SW
from trading_bot.optimp_sweep import (DESIGN, HOLDOUT, build_panel, build_formulas,
                                      evaluate, stats, wclip)

dates, IV, PX = build_panel()
n = len(dates)
dt = np.array(dates)
des = ((dt >= DESIGN[0]) & (dt <= DESIGN[1])).astype(float)
hol = ((dt >= HOLDOUT[0]) & (dt <= HOLDOUT[1])).astype(float)
F, rets, XS_UNIV = build_formulas(dates, IV, PX)


def run(free):
    old_c, old_b = dict(SW.COST_BP), dict(SW.BORROW_PCT)
    if free:
        for k in SW.COST_BP:
            SW.COST_BP[k] = 0.0
            SW.BORROW_PCT[k] = 0.0
    out = {}
    for f in F:
        syms = list(f["sig"])
        if f["family"] == "crosssec":
            w = {s: f["sign"] * np.nan_to_num(f["sig"][s]) for s in syms}
        else:
            w = {s: f["sign"] * wclip(f["sig"][s]) for s in syms}
        p = evaluate(w, rets, syms, 2, np.ones(n))
        out[f["name"]] = stats(p, des)["t"]
    SW.COST_BP.update(old_c)
    SW.BORROW_PCT.update(old_b)
    return out


net, gross = run(False), run(True)
ks = list(net)
dn = [net[k] for k in ks]
dg = [gross[k] for k in ks]
print("D1  GROSS vs NET, design window, lag 2, 60 base formulas")
print(f"    NET   mean t = {np.mean(dn):+.3f}   sd = {np.std(dn):.2f}   max = {max(dn):+.2f}")
print(f"    GROSS mean t = {np.mean(dg):+.3f}   sd = {np.std(dg):.2f}   max = {max(dg):+.2f}")
print(f"    cost drag on the mean t = {np.mean(dn) - np.mean(dg):+.3f}")
print(f"    -> the tilt is {'COST, not a reversed mechanism' if abs(np.mean(dg)) < 0.25 else 'NOT explained by cost'}")

print("\nD2  H6_XS_IVoverRV5 -- is it an options signal or a static asset tilt?")
h6 = [f for f in F if f["name"] == "H6_XS_IVoverRV5"][0]
W = {s: np.nan_to_num(h6["sig"][s]) for s in h6["sig"]}
m = des.astype(bool)
rows = []
for s in XS_UNIV:
    w = W[s][m]
    w = w[np.abs(np.vstack([np.abs(W[q][m]) for q in XS_UNIV]).sum(0)) > 0]
    rows.append((s, w.mean(), w.std(), np.abs(w).mean()))
rows.sort(key=lambda r: -r[1])
print(f"    {'sym':6s} {'mean w':>8s} {'sd w':>8s} {'|w|':>8s}  {'static share':>12s}")
for s, mu, sd, ab in rows:
    print(f"    {s:6s} {mu:8.4f} {sd:8.4f} {ab:8.4f}  {abs(mu)/max(ab,1e-9):12.2f}")
static = sum(abs(r[1]) for r in rows) / sum(r[3] for r in rows)
print(f"    STATIC SHARE of gross exposure = {static:.1%}")

# static-replica: freeze the average weights, no options input at all
frozen = {s: np.full(n, mu) for s, mu, _, _ in rows}
pf = evaluate(frozen, rets, XS_UNIV, 2, np.ones(n))
sd_, sh_ = stats(pf, des), stats(pf, hol)
print(f"    STATIC REPLICA (frozen average weights, ZERO options information):")
print(f"        design  Sharpe {sd_['sharpe']:+.2f}  t {sd_['t']:+.2f}")
print(f"        holdout Sharpe {sh_['sharpe']:+.2f}  t {sh_['t']:+.2f}")
live = {s: np.nan_to_num(h6["sig"][s]) - np.full(n, mu)
        for s, mu, _, _ in rows}
pl = evaluate(live, rets, XS_UNIV, 2, np.ones(n))
ld, lh = stats(pl, des), stats(pl, hol)
print(f"    DEMEANED (the part that actually varies with the option chains):")
print(f"        design  Sharpe {ld['sharpe']:+.2f}  t {ld['t']:+.2f}")
print(f"        holdout Sharpe {lh['sharpe']:+.2f}  t {lh['t']:+.2f}")

json.dump(dict(gross_mean_t=float(np.mean(dg)), net_mean_t=float(np.mean(dn)),
               h6_static_share=float(static),
               h6_static_replica=dict(design=sd_, holdout=sh_),
               h6_demeaned=dict(design=ld, holdout=lh),
               h6_mean_weights={r[0]: float(r[1]) for r in rows}),
          open("/home/anont/meme/research/trading_bot/NEWTERR_optimp_diag.json", "w"),
          indent=1)
