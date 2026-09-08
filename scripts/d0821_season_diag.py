#!/usr/bin/env python3
"""D0821 diagnostics on the P family (balanced-fund month-end rebalance), the only
mechanism whose design statistic clears both the analytic and the empirical bar.

Asks the four questions that kill most survivors in this programme:
  1. is it one crisis?           -> year-by-year, and design excluding 2008-09
  2. is it the WINDOW or just the signal? -> the identical signal on mid-month windows
  3. which leg carries it?       -> SPY-only and IEF-only attribution
  4. does the family hold up as one book, out of sample, net of cost?
"""
from __future__ import annotations
import json, os, sys
import numpy as np

sys.path.insert(0, "/home/anont/meme/scripts")
from d0821_season_lib import (EtfBook, calendar_features, trailing_vol, run_weights,
                              stats, etf_cost_bp)

CACHE = "/home/anont/meme/research/data/d0821_cache"
DESIGN = ("1900-01-01", "2014-01-01"); HELD = ("2014-01-01", "2099-01-01")
VOL_FLOOR, CAP, K = 0.001, 4.0, 0.01


def main():
    bk = EtfBook(["SPY", "IEF", "RSP", "EFA", "HYG", "SHY", "TLT", "AGG", "LQD",
                  "TIP", "EEM", "GLD", "IWM", "QQQ", "DIA", "MDY", "OEF", "XLP",
                  "XLU", "XLK", "VNQ"], start="2003-05-01")
    n = len(bk.dates); cf = calendar_features(bk.dates); tom = cf["tom"]
    vol = trailing_vol(bk.ret, 60, VOL_FLOOR); I = bk.i; RET = bk.ret
    d = np.nan_to_num(RET[I["SPY"]] - RET[I["IEF"]], nan=0.0)
    key = cf["ym"]; mtd = np.zeros(n); acc = 0.0
    for t in range(n):
        if t == 0 or key[t] != key[t - 1]:
            acc = 0.0
        acc += d[t]; mtd[t] = acc
    sig = np.zeros(n)
    for t in range(n):
        s = np.std(mtd[max(0, t - 750):t + 1]) if t > 60 else np.nan
        sig[t] = -np.clip(mtd[t] / s, -2.5, 2.5) / 2.5 if (s and s > 0) else 0.0

    def book(name, mask, legs=("SPY", "IEF"), sigov=None):
        ss = np.where(mask, sig if sigov is None else sigov, 0.0)
        W, R, cb = [], [], []
        for j, (lg, sgn) in enumerate(zip(legs, (1.0, -1.0))):
            if lg is None:
                continue
            W.append(sgn * ss * np.clip(K / vol[I[lg]], 0, CAP))
            R.append(RET[I[lg]]); cb.append(etf_cost_bp(lg))
        return run_weights(name, "", "P", bk.dates, np.vstack(W), np.vstack(R), cb)

    win = (tom >= -4) & (tom <= -1)
    out = {}

    base = book("P02", win)
    out["P02_base"] = dict(design=stats(base.net, bk.dates, *DESIGN),
                           held=stats(base.net, bk.dates, *HELD),
                           design_gross=stats(base.gross, bk.dates, *DESIGN),
                           held_gross=stats(base.gross, bk.dates, *HELD))

    # 1. year by year (gross, so the sign question is clean)
    yr = {}
    for y in sorted(set(cf["year"])):
        m = cf["year"] == y
        x = base.net[m]
        yr[int(y)] = dict(total_bp=float(x.sum() * 1e4), sharpe=float(
            x.mean() / x.std(ddof=1) * np.sqrt(252)) if x.std(ddof=1) > 0 else 0.0)
    out["by_year_net"] = yr
    ex = np.array([d[:4] not in ("2008", "2009") for d in bk.dates])
    xd = base.net[ex & np.array([DESIGN[0] <= d < DESIGN[1] for d in bk.dates])]
    out["design_excl_2008_09"] = dict(
        n=int(xd.size), sharpe=float(xd.mean() / xd.std(ddof=1) * np.sqrt(252)),
        t=float(xd.mean() / xd.std(ddof=1) * np.sqrt(xd.size)))

    # 2. the same signal, same holding length, on WINDOWS WITH NO REBALANCE DEADLINE
    for lo, hi, lbl in [(1, 4, "sessions_2to5_of_month"), (6, 9, "sessions_7to10"),
                        (11, 14, "sessions_12to15")]:
        cnt = np.zeros(n, int); c = 0
        for t in range(n):
            if t == 0 or key[t] != key[t - 1]:
                c = 0
            c += 1; cnt[t] = c
        b = book("ctrl_" + lbl, (cnt >= lo) & (cnt <= hi))
        out["placebo_window_" + lbl] = dict(
            design=stats(b.net, bk.dates, *DESIGN), held=stats(b.net, bk.dates, *HELD),
            design_gross=stats(b.gross, bk.dates, *DESIGN))

    # 3. leg attribution
    for legs, lbl in [(("SPY", None), "spy_leg_only"), ((None, "IEF"), "ief_leg_only")]:
        b = book("leg_" + lbl, win, legs=legs)
        out["attrib_" + lbl] = dict(design=stats(b.net, bk.dates, *DESIGN),
                                    held=stats(b.net, bk.dates, *HELD))

    # 3b. is it just SPY month-end mean reversion regardless of the bond leg?
    b = book("spy_only_mtdrev", win, legs=("SPY", None))
    out["spy_only_signal_is_spy_mtd"] = dict(design=stats(b.net, bk.dates, *DESIGN),
                                             held=stats(b.net, bk.dates, *HELD))

    # 4. the family as ONE equal-risk book (P01,P02,P05,P06,P07 -- the month-end members)
    parts = []
    for nm in ["P01_PENSION_MEQ_SIGN", "P02_PENSION_MEQ_MAG", "P05_PENSION_LASTDAY",
               "P06_PENSION_GLOBAL", "P07_PENSION_CREDIT"]:
        a = np.load(os.path.join(CACHE, nm + ".npy"))
        parts.append(a)
    G = np.mean([p[0] for p in parts], axis=0)
    Nt = np.mean([p[1] for p in parts], axis=0)
    St = np.mean([p[2] for p in parts], axis=0)
    out["P_family_composite"] = dict(
        design_gross=stats(G, bk.dates, *DESIGN), design_net=stats(Nt, bk.dates, *DESIGN),
        held_gross=stats(G, bk.dates, *HELD), held_net=stats(Nt, bk.dates, *HELD),
        held_stress=stats(St, bk.dates, *HELD),
        design_stress=stats(St, bk.dates, *DESIGN))
    # held-out year by year for the composite
    hy = {}
    for y in sorted(set(cf["year"])):
        if y < 2014:
            continue
        m = cf["year"] == y
        hy[int(y)] = float(Nt[m].sum() * 1e4)
    out["P_family_heldout_by_year_bp"] = hy

    # 5. correlation of the composite with the existing alive basket legs is not
    #    computable here (different panels); report its own autonomy instead
    out["P02_vs_family_corr"] = float(np.corrcoef(base.net, Nt)[0, 1])

    json.dump(out, open(os.path.join(CACHE, "p_diag.json"), "w"), indent=1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
