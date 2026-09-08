#!/usr/bin/env python3
"""INVENT-R3 part 2 -- families B (peer sympathy, buyback-window) and E (attention /
reaction-session), plus the full gross+net table for everything.

Same rail and same statistics as inv3_run.py.  E03/E04 use a SECOND rail (enter at the
open of the reaction session, exit at that session's close) because the mechanism is an
opening-auction one; that rail is declared here and used for nothing else.
"""
import json
import math
import os
from collections import defaultdict

import numpy as np

import inv3_run as R

CACHE = R.CACHE


# ---------------------------------------------------------------- peer sets
def peer_sets(D, k=10):
    """peers[year] = {col: array of peer cols}, fitted on the PRIOR calendar year only."""
    years = sorted(set(D.year))
    out = {}
    for y in years:
        py = str(int(y) - 1)
        w = np.where(D.year == py)[0]
        if len(w) < 200:
            continue
        univ = np.where((D.tradable[:, w].sum(axis=1) >= 200)
                        & (np.median(D.advrank[:, w], axis=1) < 1500))[0]
        if len(univ) < 100:
            continue
        Rm = np.nan_to_num(D.rcc[np.ix_(univ, w)], nan=0.0).astype(np.float64)
        Rm -= Rm.mean(axis=1, keepdims=True)
        sd = Rm.std(axis=1)
        sd[sd == 0] = 1.0
        Rm /= sd[:, None]
        C = (Rm @ Rm.T) / Rm.shape[1]
        np.fill_diagonal(C, -9.0)
        idx = np.argpartition(-C, k, axis=1)[:, :k]
        out[y] = {int(univ[i]): univ[idx[i]] for i in range(len(univ))}
    return out


def peer_sympathy(D, peers, coh, h, sign):
    ann_by_day = defaultdict(set)
    for t, evs in coh.items():
        for e in evs:
            ann_by_day[t].add(e["col"])
    tr = []
    for t in range(260, D.nD - 30):
        y = D.year[t]
        pm = peers.get(y)
        if pm is None:
            continue
        ann = ann_by_day.get(t)
        if not ann or len(ann) < 3:
            continue
        cand, sc = [], []
        for j, pl in pm.items():
            if j in ann or not D.tradable[j, t]:
                continue
            if not any(int(p) in ann for p in pl):
                continue
            s = D.rcc[j, t] - D.mkt[t]
            if np.isfinite(s):
                cand.append(j)
                sc.append(s)
        if len(cand) < 20:
            continue
        cand = np.array(cand)
        order = np.argsort(np.array(sc))
        kk = max(5, int(len(cand) * 0.20))
        lowi, highi = cand[order[:kk]], cand[order[-kk:]]
        iL, iS = (highi, lowi) if sign > 0 else (lowi, highi)
        tr.append((t, iL, iS))
    return tr


def buyback_window(D, coh):
    """long the post-print open-repurchase window, short the pre-print blackout."""
    prints = defaultdict(list)
    for t, evs in coh.items():
        for e in evs:
            prints[e["col"]].append(t)
    openw = defaultdict(set)
    blackw = defaultdict(set)
    for j, ts in prints.items():
        for p in sorted(ts):
            for t in range(p + 3, min(p + 26, D.nD)):
                openw[t].add(j)
            q = p + 63                    # 91 calendar days ~ 63 sessions ahead
            for t in range(max(q - 25, 0), min(q, D.nD)):
                blackw[t].add(j)
    tr = []
    for t in range(260, D.nD - 5):
        L = np.array(sorted(j for j in openw.get(t, ()) if D.tradable[j, t]))
        S = np.array(sorted(j for j in blackw.get(t, ()) if D.tradable[j, t]))
        both = set(L.tolist()) & set(S.tolist())
        if both:
            L = np.array([j for j in L if j not in both])
            S = np.array([j for j in S if j not in both])
        if len(L) < 20 or len(S) < 20:
            continue
        tr.append((t, L, S))
    return tr


def attention_fade(D, coh, high, sign):
    """one-day cross-sectional return fade among NON-announcers, gated on how crowded
    the earnings calendar is that session."""
    cnt = np.zeros(D.nD)
    ann_by_day = defaultdict(set)
    for t, evs in coh.items():
        cnt[t] = len(evs)
        for e in evs:
            ann_by_day[t].add(e["col"])
    valid = cnt[260:D.nD - 30]
    thr_hi, thr_lo = np.quantile(valid, 0.80), np.quantile(valid, 0.50)
    tr = []
    for t in range(260, D.nD - 30):
        if high and cnt[t] < thr_hi:
            continue
        if (not high) and cnt[t] > thr_lo:
            continue
        ann = ann_by_day.get(t, set())
        univ = np.array([j for j in np.where(D.tradable[:, t] & (D.advrank[:, t] < 1000))[0]
                         if j not in ann])
        if len(univ) < 100:
            continue
        s = D.rcc[univ, t]
        ok = np.isfinite(s)
        univ, s = univ[ok], s[ok]
        order = np.argsort(s)
        k = max(5, int(len(univ) * 0.10))
        lowi, highi = univ[order[:k]], univ[order[-k:]]
        iL, iS = (highi, lowi) if sign > 0 else (lowi, highi)
        tr.append((t, iL, iS))
    return tr


# ------------------------------------------------- open->close reaction rail
def reaction_gap_fade(D, coh, sign):
    """announcers whose reaction session is day t: fade the overnight gap intraday.
    Entry at the 09:30 open of t (the gap is fully observable then), exit at the close."""
    tr = []
    for t, evs in coh.items():
        cand, sc = [], []
        for e in evs:
            j = e["col"]
            if e["hour"] < 9.5 or e["hour"] >= 16.0:
                # filed pre-open today or after yesterday's close -> today is the reaction
                pass
            g = D.o[j, t] / D.c[j, t - 1] - 1.0 if t > 0 else np.nan
            if np.isfinite(g) and abs(g) < 0.9 and D.tradable[j, t]:
                cand.append(j)
                sc.append(g)
        if len(cand) < 10:
            continue
        cand = np.array(cand)
        order = np.argsort(np.array(sc))
        k = max(3, int(len(cand) * 0.30))
        lowi, highi = cand[order[:k]], cand[order[-k:]]
        iL, iS = (highi, lowi) if sign > 0 else (lowi, highi)
        tr.append((t, iL, iS))
    return tr


def evaluate_oc(D, tranches, name, note):
    """same statistics as R.evaluate but on the same-session open->close return."""
    with np.errstate(invalid="ignore"):
        roc = D.c / D.o - 1.0
    roc[~np.isfinite(roc) | (np.abs(roc) > 0.9)] = np.nan
    rows = []
    for t0, iL, iS in tranches:
        rl = roc[iL, t0]
        rs = roc[iS, t0]
        rl, rs = rl[np.isfinite(rl)], rs[np.isfinite(rs)]
        if len(rl) < 3 or len(rs) < 3:
            continue
        rows.append((t0, 0.5 * rl.mean() - 0.5 * rs.mean()))
    if len(rows) < 12:
        return None
    t0s = np.array([r[0] for r in rows])
    ret = np.array([r[1] for r in rows]) * 1e4
    out = {"name": name, "note": note, "h": 0}
    dmax = R.__dict__  # noqa
    di = D.didx[max(d for d in D.days if d <= R.DESIGN_END)]
    hi = D.didx[min(d for d in D.days if d >= R.HOLDOUT_START)]
    for tag, mask in (("design", t0s <= di), ("holdout", t0s >= hi)):
        r = ret[mask]
        if len(r) < 12:
            out[tag] = None
            continue
        years = max(((t0s[mask].max() - t0s[mask].min()) + 1) / 252.0, 0.5)
        res = dict(n=int(len(r)), mean_bp=float(r.mean()), sd_bp=float(r.std(ddof=1)),
                   hit=float((r > 0).mean()), t_gross=float(R.nw_t(r, 1)),
                   breakeven_bp_per_side=float(r.mean() / 2.0), years=float(years),
                   events_per_year=float(len(r) / years))
        for cost, key in ((R.COST_LO, "lo"), (R.COST_HI, "hi")):
            net = r - 2.0 * cost
            res[f"mean_bp_net_{key}"] = float(net.mean())
            res[f"t_net_{key}"] = float(R.nw_t(net, 1))
            res[f"sharpe_net_{key}"] = float(net.mean() / r.std(ddof=1)
                                             * math.sqrt(len(r) / years))
        out[tag] = res
    return out


def main():
    D = R.Data()
    coh = R.announcer_cohorts(D)
    res = json.load(open(f"{CACHE}/partial_ACD.json"))

    def add(x):
        if x is None:
            print("  (dropped, too few events)", flush=True)
            return
        res.append(x)
        d, ho = x["design"], x.get("holdout")
        print("%-26s h=%-3d design n=%4d gross=%7.1fbp tg=%5.2f tnet=%5.2f | holdout tnet=%5.2f"
              % (x["name"], x["h"], d["n"], d["mean_bp"], d["t_gross"], d["t_net_lo"],
                 ho["t_net_lo"] if ho else float("nan")), flush=True)

    print("fitting peer sets...", flush=True)
    peers = peer_sets(D)
    print("peer years:", sorted(peers), flush=True)

    add(R.evaluate(D, peer_sympathy(D, peers, coh, 1, -1), 1, "B01_PEER_SYMPATHY_FADE_1",
                   "among NON-announcers that have >=1 of their 10 top-correlated peers "
                   "reporting tonight, fade today's market-relative move, hold 1 session"))
    add(R.evaluate(D, peer_sympathy(D, peers, coh, 3, -1), 3, "B02_PEER_SYMPATHY_FADE_3",
                   "B01 held 3 sessions"))
    add(R.evaluate(D, buyback_window(D, coh), 1, "B03_BUYBACK_WINDOW",
                   "long names inside the post-print open-repurchase window (+3..+25 "
                   "sessions), short names inside the predicted pre-print blackout "
                   "(-25..-1 sessions before last print + 63 sessions)"))
    add(R.evaluate(D, attention_fade(D, coh, True, -1), 1, "E01_CROWDED_CAL_XS_FADE",
                   "on the top-quintile busiest earnings sessions, fade the one-day "
                   "cross-sectional return of the NON-announcers (attention scarcity)"))
    add(R.evaluate(D, attention_fade(D, coh, False, -1), 1, "E02_QUIET_CAL_XS_FADE_CTRL",
                   "CONTROL: the same fade on the quietest half of earnings sessions"))
    add(evaluate_oc(D, reaction_gap_fade(D, coh, -1), "E03_EARN_GAP_OC_FADE",
                    "on the earnings reaction session, fade the overnight gap tercile "
                    "from the 09:30 open to the 16:00 close"))
    add(evaluate_oc(D, reaction_gap_fade(D, coh, +1), "E04_EARN_GAP_OC_CONT",
                    "the continuation sign of E03 (same hypothesis, other sign)"))

    with open(f"{CACHE}/all_results.json", "w") as fh:
        json.dump(res, fh, indent=1)
    print(f"\n{len(res)} formulas with usable statistics", flush=True)

    print("\n%-26s %4s %9s %6s %6s %9s %6s %6s" %
          ("formula", "n", "grossbp", "tg", "tnet", "H_grossbp", "H_tg", "H_tnet"))
    for x in sorted(res, key=lambda z: -abs(z["design"]["t_gross"])):
        d, ho = x["design"], x.get("holdout")
        print("%-26s %4d %9.1f %6.2f %6.2f %9.1f %6.2f %6.2f" %
              (x["name"], d["n"], d["mean_bp"], d["t_gross"], d["t_net_lo"],
               ho["mean_bp"] if ho else float("nan"),
               ho["t_gross"] if ho else float("nan"),
               ho["t_net_lo"] if ho else float("nan")))


if __name__ == "__main__":
    main()
