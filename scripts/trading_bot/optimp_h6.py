#!/usr/bin/env python3
"""Does H6 contain any OPTION information, or is it a realised-vol signal?

H6 ranks assets on z(ownIV / ownRV5).  That is a ratio of two things.  If the
whole effect lives in the DENOMINATOR, the formula is a low-realised-vol
cross-sectional tilt with an implied-vol decoration on top, it carries zero
option content, and it belongs to a family this programme already mined.

So decompose:
    H6      z(IV / RV5)        both legs
    H6-RVonly   z(1  / RV5)    denominator alone, NO option data
    H6-IVonly   z(IV)          numerator alone, option data only
    H6-resid    z(IV / RV5) orthogonalised to z(1/RV5) cross-sectionally
                              -- the option content with the realised leg removed
Also run the SIGN-FLIPPED book properly (borrow follows the new short side).
"""
from __future__ import annotations

import json
import math
import sys

import numpy as np

sys.path.insert(0, "/home/anont/meme/scripts")
from trading_bot.optimp_sweep import (DESIGN, HOLDOUT, build_panel, evaluate,
                                      rv, stats, zc)

dates, IV, PX = build_panel()
n = len(dates)
dt = np.array(dates)
des = ((dt >= DESIGN[0]) & (dt <= DESIGN[1])).astype(float)
hol = ((dt >= HOLDOUT[0]) & (dt <= HOLDOUT[1])).astype(float)
rets = {}
for s in ["SPY", "QQQ", "IWM", "DIA", "EEM", "EWZ", "GLD", "USO", "SLV", "TLT",
          "FXI", "GDX", "XLE", "EFA", "AAPL"]:
    r = np.full(n, np.nan)
    r[1:] = PX[s][1:] / PX[s][:-1] - 1.0
    rets[s] = r
PAIRS = [("QQQ", "VXN"), ("IWM", "RVX"), ("DIA", "VXD"), ("EEM", "VXEEM"),
         ("EWZ", "VXEWZ"), ("USO", "OVX"), ("GLD", "GVZ"), ("SLV", "VXSLV"),
         ("TLT", "VXTLT"), ("FXI", "VXFXI"), ("GDX", "VXGDX"),
         ("XLE", "VXEFA"), ("EFA", "VXEFA"), ("AAPL", "VXAPL")]
PAIRS = [("QQQ", "VXN"), ("IWM", "RVX"), ("DIA", "VXD"), ("EEM", "VXEEM"),
         ("EWZ", "VXEWZ"), ("USO", "OVX"), ("GLD", "GVZ"), ("SLV", "VXSLV"),
         ("TLT", "VXTLT"), ("FXI", "VXFXI"), ("GDX", "VXGDX"),
         ("XLE", "VXXLE"), ("EFA", "VXEFA"), ("AAPL", "VXAPL")]
U = [p[0] for p in PAIRS]
RV5 = {s: rv(PX[s], 5) for s in U}


def book(score, sign):
    M = np.vstack([score[s] for s in U])
    Wt = np.zeros_like(M)
    for t in range(M.shape[1]):
        v = M[:, t]
        m = ~np.isnan(v)
        if m.sum() < 6:
            continue
        r = np.argsort(np.argsort(v[m])).astype(float)
        r = 2 * r / (m.sum() - 1) - 1
        r -= r.mean()
        r /= np.abs(r).sum()
        Wt[m, t] = sign * r
    return {s: Wt[i] for i, s in enumerate(U)}


def show(tag, w):
    p = evaluate(w, rets, U, 2, np.ones(n))
    p3 = evaluate(w, rets, U, 3, np.ones(n))
    d, h, d3 = stats(p, des), stats(p, hol), stats(p3, des)
    print(f"  {tag:34s} design {d['sharpe']:+5.2f} (t {d['t']:+5.2f})   "
          f"L3 {d3['sharpe']:+5.2f}   holdout {h['sharpe']:+5.2f} (t {h['t']:+5.2f})")
    return dict(tag=tag, design=d, design_L3=d3, holdout=h)


both = {s: zc(IV[o] / np.maximum(RV5[s], 1e-6)) for s, o in PAIRS}
rvonly = {s: zc(1.0 / np.maximum(RV5[s], 1e-6)) for s, o in PAIRS}
ivonly = {s: zc(IV[o]) for s, o in PAIRS}
ivlvl = {s: zc(np.log(IV[o])) - zc(np.log(np.maximum(RV5[s], 1e-6)))
         for s, o in PAIRS}

res = []
print("H6 DECOMPOSITION (as-stated sign +1; negative = the stated mechanism is backwards)")
res.append(show("H6 both legs  z(IV/RV5)", book(both, +1)))
res.append(show("H6-RVonly  z(1/RV5)  NO OPTIONS", book(rvonly, +1)))
res.append(show("H6-IVonly  z(IV)     OPTIONS ONLY", book(ivonly, +1)))
res.append(show("H6-logdiff z(lnIV)-z(lnRV5)", book(ivlvl, +1)))

# cross-sectionally orthogonalise the option leg against the realised leg
orth = {}
M_b = np.vstack([both[s] for s in U])
M_r = np.vstack([rvonly[s] for s in U])
O = np.full_like(M_b, np.nan)
for t in range(n):
    b, r = M_b[:, t], M_r[:, t]
    m = ~(np.isnan(b) | np.isnan(r))
    if m.sum() < 6:
        continue
    A = np.vstack([r[m], np.ones(m.sum())]).T
    c, *_ = np.linalg.lstsq(A, b[m], rcond=None)
    O[m, t] = b[m] - (c[0] * r[m] + c[1])
for i, s in enumerate(U):
    orth[s] = O[i]
res.append(show("H6-resid  option leg, RV removed", book(orth, +1)))

print("\nSIGN-FLIPPED (this is what flipping the mechanism would actually earn,")
print("with borrow correctly charged on the new short side):")
res.append(show("H6 FLIPPED  z(IV/RV5) sign -1", book(both, -1)))
res.append(show("H6-resid FLIPPED", book(orth, -1)))
res.append(show("H6-RVonly FLIPPED  NO OPTIONS", book(rvonly, -1)))

json.dump(res, open("/home/anont/meme/research/trading_bot/NEWTERR_optimp_h6.json",
                    "w"), indent=1, default=float)
