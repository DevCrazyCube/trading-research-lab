#!/usr/bin/env python3
"""EXO_0822C diagnostics — tick grid, drop ratio, event-vs-placebo, capacity."""
from __future__ import annotations

import json
import sys

import numpy as np

from exo0822c_sweep import (OUTDIR, Panel, expanding_tercile, real_returns,
                            shuffle_rate)


def clustered_t(vals, day, minn=1):
    """mean and t of `vals`, clustering by day (each day one observation)."""
    ok = np.isfinite(vals)
    v, d = vals[ok], day[ok]
    o = np.argsort(d, kind="stable")
    v, d = v[o], d[o]
    b = np.flatnonzero(np.r_[True, d[1:] != d[:-1], True])
    means = np.array([v[a:c].mean() for a, c in zip(b[:-1], b[1:])])
    m = means.mean()
    se = means.std(ddof=1) / np.sqrt(means.size)
    return float(m * 1e4), float(m / se), int(means.size)


def main():
    win = sys.argv[1] if len(sys.argv) > 1 else "design"
    P = Panel()
    rng = np.random.default_rng(7)
    q33, q67 = expanding_tercile(P.y, P.evd, P.nd)
    ctx = {"q33": q33, "q67": q67, "yshuf": shuffle_rate(P.y, P.evd, rng)}
    r = real_returns(P, ctx["yshuf"])
    ordinary = P.typ == 0
    m = ordinary & ((P.evd < P.cut) if win == "design" else (P.evd >= P.cut))
    eps = r["eps_h"]
    out = {"window": win, "n_events": int(m.sum())}

    tick_bp = 1e4 * 0.01 / P.price
    out["tick_bp_median"] = float(np.median(tick_bp[m]))
    out["price_median"] = float(np.median(P.price[m]))
    out["abs_eps_in_ticks_median"] = float(np.median(np.abs(eps[m]) / (tick_bp[m] / 1e4)))
    out["mean_eps_in_ticks"] = float(np.nanmean(eps[m]) / (np.median(tick_bp[m]) / 1e4))

    mm, tt, nd_ = clustered_t(eps[m], P.evd[m])
    out["mean_eps_h_bp"] = mm
    out["t_day_clustered"] = tt
    out["n_days"] = nd_
    pm, pt, _ = clustered_t(r["pl"][m], P.evd[m])
    out["mean_placebo_bp"] = pm
    out["t_placebo_day_clustered"] = pt
    diff = eps[m] - r["pl"][m]
    dm, dt, _ = clustered_t(diff, P.evd[m])
    out["mean_event_minus_placebo_bp"] = dm
    out["t_event_minus_placebo"] = dt

    # drop ratio: eps = (1 - k) * y  =>  k = 1 - slope
    y = P.y[m]
    e = eps[m]
    ok = np.isfinite(e) & np.isfinite(y)
    slope = float(np.polyfit(y[ok], e[ok], 1)[0])
    out["drop_ratio"] = 1.0 - slope
    out["slope_eps_on_yield"] = slope

    def terciles(x, lab):
        q = np.nanquantile(x[m], [1 / 3, 2 / 3])
        res = {}
        for i, nm in enumerate(("lo", "mid", "hi")):
            if i == 0:
                sel = m & (x <= q[0])
            elif i == 1:
                sel = m & (x > q[0]) & (x <= q[1])
            else:
                sel = m & (x > q[1])
            a, b, c = clustered_t(eps[sel], P.evd[sel])
            res[nm] = {"mean_bp": a, "t": b, "n_days": c, "n": int(sel.sum())}
        out[f"by_{lab}"] = res

    terciles(P.price, "price")
    terciles(P.y, "yield")
    terciles(P.adv, "adv")
    terciles(tick_bp, "tick_bp")

    # calendar-year stability
    yr = np.array([d[:4] for d in P.dates])[P.evd]
    cy = {}
    for u in sorted(set(yr[m])):
        sel = m & (yr == u)
        a, b, c = clustered_t(eps[sel], P.evd[sel])
        cy[u] = {"mean_bp": a, "t": b, "n": int(sel.sum())}
    out["by_year"] = cy

    # capacity
    out["adv_median_usd"] = float(np.median(P.adv[m]))
    out["adv_p10_usd"] = float(np.percentile(P.adv[m], 10))
    cohort = np.bincount(P.evd[m], minlength=P.nd)
    cohort = cohort[cohort > 0]
    out["cohort_size_median"] = float(np.median(cohort))
    out["cohort_size_mean"] = float(cohort.mean())
    # 1% of ADV per name, summed over the day's cohort, median over days
    cap = np.zeros(P.nd)
    np.add.at(cap, P.evd[m], 0.01 * P.adv[m])
    cap = cap[cap > 0]
    out["capacity_1pct_adv_median_usd"] = float(np.median(cap))

    json.dump(out, open(OUTDIR / f"INVENT_0822C_gaptether_DIAG_{win}.json", "w"), indent=1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
