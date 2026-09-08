#!/usr/bin/env python3
"""D0821 diag-2: the decisive test for the P mechanism.

diag-1's placebo was UNFAIR: a month-to-date signal read on session 3 has 3 days in it
and on session 20 has 20, so "month-end works, mid-month does not" could be entirely a
LOOKBACK-LENGTH artifact rather than a rebalance DEADLINE.  Here the signal is a FIXED
15-session trailing SPY return for every window, so the only thing that varies is where
in the month the position is held.  If the deadline is real, the last-4-sessions bucket
must stand out against the identical signal held elsewhere.
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
    bk = EtfBook(["SPY", "IEF", "SHY"], start="1993-02-01")
    n = len(bk.dates); cf = calendar_features(bk.dates); tom = cf["tom"]
    vol = trailing_vol(bk.ret, 60, VOL_FLOOR); I = bk.i
    r = np.nan_to_num(bk.ret[I["SPY"]], nan=0.0)
    cs = np.cumsum(r)
    lb15 = np.zeros(n); lb15[15:] = cs[15:] - cs[:-15]
    sig = np.zeros(n)
    for t in range(n):
        s = np.std(lb15[max(0, t - 750):t + 1]) if t > 100 else np.nan
        sig[t] = -np.clip(lb15[t] / s, -2.5, 2.5) / 2.5 if (s and s > 0) else 0.0

    cnt = np.zeros(n, int); c = 0
    for t in range(n):
        if t == 0 or cf["ym"][t] != cf["ym"][t - 1]:
            c = 0
        c += 1; cnt[t] = c

    def spy_book(mask, sg=None):
        ss = np.where(mask, sig if sg is None else sg, 0.0)
        W = (ss * np.clip(K / vol[I["SPY"]], 0, CAP))[None, :]
        return run_weights("x", "", "P", bk.dates, W, bk.ret[I["SPY"]][None, :],
                           [etf_cost_bp("SPY")])

    out = {}
    buckets = {"last4_of_month": (tom >= -4) & (tom <= -1),
               "sessions_1to4": (cnt >= 1) & (cnt <= 4),
               "sessions_5to8": (cnt >= 5) & (cnt <= 8),
               "sessions_9to12": (cnt >= 9) & (cnt <= 12),
               "sessions_13to16": (cnt >= 13) & (cnt <= 16),
               "every_session": np.ones(n, bool)}
    for k, m in buckets.items():
        b = spy_book(m)
        out["fixed15_" + k] = dict(design=stats(b.net, bk.dates, *DESIGN),
                                   held=stats(b.net, bk.dates, *HELD),
                                   design_gross=stats(b.gross, bk.dates, *DESIGN),
                                   held_gross=stats(b.gross, bk.dates, *HELD))

    # unconditional month-end direction: is this a BARE calendar effect?
    for lbl, s in [("uncond_short_spy", -np.ones(n)), ("uncond_long_spy", np.ones(n))]:
        b = spy_book((tom >= -4) & (tom <= -1), sg=s)
        out["bare_calendar_" + lbl] = dict(design=stats(b.net, bk.dates, *DESIGN),
                                           held=stats(b.net, bk.dates, *HELD))

    # the ORIGINAL P02 signal (MTD SPY-IEF divergence) on SPY only, but now measured on
    # the long SPY history so the design window is 1993-2013 rather than 2003-2013
    d = np.nan_to_num(bk.ret[I["SPY"]] - bk.ret[I["IEF"]], nan=0.0)
    d = np.where(np.isfinite(bk.ret[I["IEF"]]), d, r)   # pre-2002: SPY alone
    mtd = np.zeros(n); acc = 0.0
    for t in range(n):
        if t == 0 or cf["ym"][t] != cf["ym"][t - 1]:
            acc = 0.0
        acc += d[t]; mtd[t] = acc
    sg2 = np.zeros(n)
    for t in range(n):
        s = np.std(mtd[max(0, t - 750):t + 1]) if t > 100 else np.nan
        sg2[t] = -np.clip(mtd[t] / s, -2.5, 2.5) / 2.5 if (s and s > 0) else 0.0
    b = spy_book((tom >= -4) & (tom <= -1), sg=sg2)
    out["P02spy_long_history"] = dict(
        design_1993_2013=stats(b.net, bk.dates, *DESIGN),
        held_2014_2026=stats(b.net, bk.dates, *HELD),
        pre2003=stats(b.net, bk.dates, "1993-01-01", "2003-05-01"),
        gross_design=stats(b.gross, bk.dates, *DESIGN))
    # window-width robustness on the held-out only after design is fixed
    for lo in (-2, -3, -5, -6):
        bb = spy_book((tom >= lo) & (tom <= -1), sg=sg2)
        out[f"window_{lo}_to_-1"] = dict(design=stats(bb.net, bk.dates, *DESIGN),
                                         held=stats(bb.net, bk.dates, *HELD))
    yrs = {}
    for y in sorted(set(cf["year"])):
        m = cf["year"] == y
        yrs[int(y)] = round(float(b.net[m].sum() * 1e4))
    out["P02spy_by_year_net_bp"] = yrs
    out["mean_gross_exposure_when_active"] = float(np.mean(b.expo[b.expo > 0]))
    json.dump(out, open(os.path.join(CACHE, "p_diag2.json"), "w"), indent=1)
    for k, v in out.items():
        if k.endswith("by_year_net_bp") or isinstance(v, float):
            print(k, v); continue
        print(k)
        for a, s in v.items():
            print(f"    {a:20s} Sh={s['sharpe']:6.2f} t={s['t']:6.2f} n={s['n']}")


if __name__ == "__main__":
    main()
