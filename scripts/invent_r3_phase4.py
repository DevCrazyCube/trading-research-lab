#!/usr/bin/env python3
"""INVENT R3 phase 4 -- stress and subperiod stability of the ONE thing that worked:
equal-risk combination of the alive legs.

Rungs
  headline : each leg at its own frozen cost model (T7 on the auction rail, M0 outstanding)
  stressed : T7 charged a real 1.13 bp half-spread per leg (the T7 stress rung that takes its
             standalone Sharpe to ~0.2), T3 charged 2x entry half-spread + a real exit spread
             instead of a free opening cross, CEF charged 1.5x its measured 11.53 bp.
"""
from __future__ import annotations
import json, math, pathlib, datetime, sys
import numpy as np

ROOT = pathlib.Path("/home/anont/meme"); sys.path.insert(0, str(ROOT))
from scripts.invent_r3_conditioning import (   # noqa: E402
    load, load_legs, ann_sharpe, to_weekly, DESIGN_END, HOLD_START, OUT, D)


def weekly(dates, r, weeklyleg=False):
    if weeklyleg:
        w = {}
        for dd, x in zip(dates, r):
            dt = datetime.date.fromisoformat(dd)
            w[(dt - datetime.timedelta(days=dt.weekday())).isoformat()] = float(x)
        return w
    return to_weekly(dates, r)


def book(V, sd, keys, names, w):
    out = np.zeros(len(keys))
    for n, ww in zip(names, w):
        out += ww * V[n] / sd[n]
    return out


def main():
    legs = load_legs()
    t3s = load("t3_stress.json"); t7s = load("t7d1_stress.json")
    cefw = legs["CEF"]
    # CEF stressed: charge 0.5x the measured half-spread again on realised turnover.
    # H=4 decile tilt turns over ~2x0.5 notional every 4 weeks -> ~ (11.53/2) bp per 4 weeks.
    cef_stress = np.array(cefw["net"]) - (11.53 / 2) / 1e4 / 4.0

    rungs = {
        "headline": {"T3": (legs["T3"]["dates"], legs["T3"]["net"], False),
                     "T7D1": (legs["T7D1"]["dates"], legs["T7D1"]["net"], False),
                     "CEF": (cefw["dates"], cefw["net"], True)},
        "stressed": {"T3": (t3s["dates"], np.array(t3s["net"]), False),
                     "T7D1": (t7s["dates"], np.array(t7s["net"]), False),
                     "CEF": (cefw["dates"], cef_stress, True)},
    }
    names = ["T3", "T7D1", "CEF"]
    res = {}
    for rung, spec in rungs.items():
        wk = {n: weekly(*spec[n]) for n in names}
        cef_start = min(wk["CEF"])
        keys = sorted(k for k in set().union(*[set(v) for v in wk.values()]) if k >= cef_start)
        kd = np.array(keys)
        dm, hm = kd <= DESIGN_END, kd >= HOLD_START
        V = {n: np.array([wk[n].get(k, 0.0) for k in keys]) for n in names}
        sd = {n: (V[n][dm].std(ddof=1) or 1.0) for n in names}
        eq = book(V, sd, keys, names, [1 / 3] * 3)
        two_keys = sorted(set(wk["T3"]) | set(wk["T7D1"]))
        k2 = np.array(two_keys)
        V2 = {n: np.array([wk[n].get(k, 0.0) for k in two_keys]) for n in ("T3", "T7D1")}
        d2, h2 = k2 <= DESIGN_END, k2 >= HOLD_START
        sd2 = {n: (V2[n][d2].std(ddof=1) or 1.0) for n in V2}
        e2 = 0.5 * V2["T3"] / sd2["T3"] + 0.5 * V2["T7D1"] / sd2["T7D1"]
        # subperiods of the holdout
        hk = kd[hm]
        thirds = np.array_split(np.where(hm)[0], 3)
        sub = [{"from": keys[ix[0]], "to": keys[ix[-1]], "n": len(ix),
                "sharpe": ann_sharpe(eq[ix], 52)} for ix in thirds]
        res[rung] = {
            "legs_design": {n: ann_sharpe(V[n][dm], 52) for n in names},
            "legs_holdout": {n: ann_sharpe(V[n][hm], 52) for n in names},
            "eq3_design": ann_sharpe(eq[dm], 52), "eq3_holdout": ann_sharpe(eq[hm], 52),
            "eq3_holdout_subperiods": sub,
            "eq3_holdout_worst_third": min(s["sharpe"] for s in sub),
            "two_leg_T3_T7_full": {"design": ann_sharpe(e2[d2], 52),
                                   "holdout": ann_sharpe(e2[h2], 52),
                                   "n_design_wk": int(d2.sum()), "n_hold_wk": int(h2.sum())},
            "n_weeks": {"design": int(dm.sum()), "holdout": int(hm.sum())},
        }
    (OUT / "INVENT_R3_condition_combine_phase4.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
