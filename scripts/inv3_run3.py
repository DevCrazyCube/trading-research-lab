#!/usr/bin/env python3
"""INVENT-R3 part 3 -- family F: the POOLED, high-power versions.

The single-calendar tests (witching 4/yr, quarter-end 4/yr, FOMC 8/yr) are hopelessly
underpowered on a 6-year design window.  Family F pools event types so the same mechanism
gets tested with 3-20x the events, and pairs every gated book with the identical ungated
book so the question is always "what does the GATE buy", never "does reversal exist".
"""
import json

import numpy as np

import inv3_run as R
import inv3_run2 as R2

CACHE = R.CACHE


def event_masks(D):
    coh = R.announcer_cohorts(D)
    ann_day = {}
    last_print = np.full((D.nS, D.nD), -10**6, dtype=np.int32)
    next_pred = np.full((D.nS, D.nD), 10**6, dtype=np.int32)
    prints = {}
    for t, evs in coh.items():
        for e in evs:
            prints.setdefault(e["col"], []).append(t)
    for j, ts in prints.items():
        ts = sorted(ts)
        cur = -10**6
        k = 0
        for t in range(D.nD):
            while k < len(ts) and ts[k] <= t:
                cur = ts[k]
                k += 1
            last_print[j, t] = cur
        for p in ts:
            q = p + 63
            for t in range(max(q - 30, 0), min(q + 1, D.nD)):
                next_pred[j, t] = min(next_pred[j, t], q - t)
    return coh, last_print, next_pred


def rev5(D, u, t):
    return D.rcc[u, t - 4:t + 1].sum(axis=1)


def gated_rev_book(D, gate_fn, sign=-1, topn=1000, frac=0.10, minn=40):
    tr = []
    for t in range(280, D.nD - 30):
        univ = np.where(D.tradable[:, t] & (D.advrank[:, t] < topn))[0]
        univ = gate_fn(t, univ)
        if len(univ) < minn:
            continue
        s = rev5(D, univ, t)
        ok = np.isfinite(s)
        univ, s = univ[ok], s[ok]
        if len(univ) < minn:
            continue
        order = np.argsort(s)
        k = max(5, int(len(univ) * frac))
        lowi, highi = univ[order[:k]], univ[order[-k:]]
        iL, iS = (highi, lowi) if sign > 0 else (lowi, highi)
        tr.append((t, iL, iS))
    return tr


def main():
    D = R.Data()
    res = json.load(open(f"{CACHE}/all_results.json"))
    coh, last_print, next_pred = event_masks(D)

    def add(x):
        if x is None:
            print("  (dropped)", flush=True)
            return
        res.append(x)
        d, ho = x["design"], x.get("holdout")
        print("%-28s h=%-3d n=%4d gross=%7.1fbp tg=%5.2f tnet=%5.2f | H gross=%7.1f "
              "tg=%5.2f tnet=%5.2f"
              % (x["name"], x["h"], d["n"], d["mean_bp"], d["t_gross"], d["t_net_lo"],
                 ho["mean_bp"] if ho else float("nan"),
                 ho["t_gross"] if ho else float("nan"),
                 ho["t_net_lo"] if ho else float("nan")), flush=True)

    clv = lambda t, u: D.clv[u, t]          # noqa: E731
    dayret = lambda t, u: D.rcc[u, t]       # noqa: E731

    rebal = D.month_last | D.is_witch | D.quarter_end
    add(R.evaluate(D, R.xs_book(D, rebal, clv, -1), 1, "F01_REBAL_CLV_FADE_POOLED",
                   "POOLED index-rebalance closes (month-end OR triple witching OR "
                   "quarter-end): fade the close-location-in-range decile, hold 1 session"))
    macro = D.is_fomc | D.is_nfp
    add(R.evaluate(D, R.xs_book(D, macro, dayret, -1), 1, "F04_MACRO_POOLED_XS_FADE",
                   "POOLED scheduled macro sessions (FOMC statement OR payroll Friday): "
                   "fade the day's cross-sectional return decile, hold 1 session"))
    add(R.evaluate(D, R.xs_book(D, macro, dayret, +1), 1, "F05_MACRO_POOLED_XS_CONT",
                   "the continuation sign of F04 (same hypothesis, other sign)"))

    def pre_gate(t, u):
        return u[(next_pred[u, t] >= 1) & (next_pred[u, t] <= 5)]

    def post_gate(t, u):
        d = t - last_print[u, t]
        return u[(d >= 1) & (d <= 10)]

    def quiet_gate(t, u):
        d = t - last_print[u, t]
        return u[(d > 20) & (next_pred[u, t] > 20)]

    add(R.evaluate(D, gated_rev_book(D, pre_gate, minn=25), 5, "F08_REV5_PRE_EARN",
                   "5-session cross-sectional reversal restricted to names 1-5 sessions "
                   "BEFORE their point-in-time predicted earnings date, hold 5"))
    add(R.evaluate(D, gated_rev_book(D, post_gate, minn=25), 5, "F09_REV5_POST_EARN",
                   "the same 5-session reversal restricted to names 1-10 sessions AFTER a "
                   "realised print"))
    add(R.evaluate(D, gated_rev_book(D, quiet_gate, minn=25), 5, "F10_REV5_NOEVENT_CTRL",
                   "CONTROL: the same reversal on names with NO print within 20 sessions "
                   "either side -- the ungated benchmark the calendar gate must beat"))

    with open(f"{CACHE}/all_results.json", "w") as fh:
        json.dump(res, fh, indent=1)
    print(f"\n{len(res)} formulas total", flush=True)


if __name__ == "__main__":
    main()
