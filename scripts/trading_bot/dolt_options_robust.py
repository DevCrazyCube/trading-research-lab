#!/usr/bin/env python3
"""Robustness/honesty checks on the DoltHub option-signal test."""
import sys, math
sys.path.insert(0, "/home/anont/meme/scripts/trading_bot")
import numpy as np
import dolt_options_analyze as A

dates, feats, px = A.load_panel()
recs = A.build_signals(dates, feats, px)
des = [r for r in recs if r["date"] <= A.DESIGN_END]
hold = [r for r in recs if r["date"] > A.DESIGN_END]

print("=== signal coverage & cross-sectional dispersion (design) ===")
for sg in A.SIGNALS:
    fin, disp = [], []
    for r in des:
        v = r[sg]; ok = np.isfinite(v)
        fin.append(ok.mean())
        if ok.sum() > 3:
            disp.append(np.nanstd(v[ok]))
    print(f"{sg:10s} finite={np.mean(fin):.2f}  xs-std(median)={np.median(disp):.4f}")

# --- IVLEVEL: is the long-high book just market beta / past-return momentum? ---
# Build the IVLEVEL long-high book return series and regress on equal-weight
# market (mean fwd return of the cross-section) each period.
def book_series(recs, sg, sign):
    pnl, mkt = [], []
    for r in recs:
        w = A.xs_weights(r[sg] * sign)
        if w is None: continue
        wok = np.nan_to_num(w)
        pnl.append(float(np.dot(wok, r["fwd"])))
        mkt.append(float(np.mean(r["fwd"])))
    return np.array(pnl), np.array(mkt)

for label, rr in [("design", des), ("held-out", hold)]:
    p, m = book_series(rr, "IVLEVEL", +1)
    # regress book on market
    b = np.polyfit(m, p, 1)
    resid = p - (b[0]*m + b[1])
    # alpha t-stat
    n = len(resid); alpha = resid.mean(); se = resid.std(ddof=1)/math.sqrt(n)
    raw_t = p.mean()/(p.std(ddof=1)/math.sqrt(n))
    print(f"\nIVLEVEL long-high {label}: n={n} raw_t={raw_t:.2f} beta_to_EWmkt={b[0]:.2f} "
          f"alpha/day={alpha:.5f} alpha_t={alpha/se:.2f}")

# --- SKEW_RR / PUT_SLOPE sign stability: split held-out in halves ---
print("\n=== held-out sub-period sign stability (t-stats) ===")
h1 = hold[:len(hold)//2]; h2 = hold[len(hold)//2:]
for sg in ["SKEW_RR","PUT_SLOPE","IVLEVEL"]:
    for nm, rr in [("H1",h1),("H2",h2)]:
        p,_ = book_series(rr, sg, +1)
        _,t,_ = A.sharpe_t(p)
        print(f"  {sg:10s} {nm} ({rr[0]['date']}..{rr[-1]['date']}) long-high t={t:+.2f}")
