#!/usr/bin/env python3
"""INVENT 0822 crypto-tether: the EVENT-LEVEL power check for family A.

A stablecoin peg trade is flat most of the time and makes (or loses) its money in
a handful of depeg episodes.  Its daily-Sharpe t-stat therefore massively
overstates its evidence: the independent unit is the EPISODE, not the day.
This script re-scores the leading peg formulas per episode and per calendar
cluster, and prints the per-instrument attribution.
"""
from __future__ import annotations
import os, json
import numpy as np
import invent0822_tether_lib as L
import invent0822_tether_sweep as SW

OUT = "/home/anont/meme/research/trading_bot"
bp = 1e-4


def main():
    P = L.Panels()
    dates = P.dates()
    T = P.T
    stab = SW.stable_universe(P)
    K = len(stab)
    devA = np.full((T, K), np.nan); rA = np.full((T, K), np.nan); qvA = np.full((T, K), np.nan)
    for j, s in enumerate(stab):
        c, o, qv = P.bn(s, "c"), P.bn(s, "o"), P.bn(s, "qv")
        devA[:, j] = np.log(c)
        rA[:-1, j] = np.log(o[1:] / o[:-1])
        qvA[:, j] = qv
    age = np.cumsum(np.isfinite(devA), axis=0)

    def mk(enter, exitb, side="both", seasoned=False):
        w = np.column_stack([SW.band_state(devA[:, j], enter * bp, exitb * bp, side) for j in range(K)])
        if seasoned:
            w = w * (age >= 250)
        ws = np.zeros_like(w); ws[1:] = w[:-1]
        return L.normalize_eq(ws), ws

    books = {
        "A2_PEG_BAND20": mk(20, 5),
        "A12_PEG_BAND20_SEASONED": mk(20, 5, seasoned=True),
        "A3_PEG_BAND50": mk(50, 15),
        "A6_PEG_PREM_ONLY": mk(20, 5, "prem"),
        "A5_PEG_DISC_ONLY": mk(20, 5, "disc"),
    }
    legs = np.ones(K)

    # ---- calendar clusters of stress: any name >100bp off peg, merged across
    #      names, episodes separated by >=30 quiet days.  This is the honest n.
    big = np.any(np.isfinite(devA) & (np.abs(devA) > 100 * bp), axis=1)
    clusters = []
    t = 0
    while t < T:
        if big[t]:
            t0 = t; last = t
            while t < T and (t - last) <= 30:
                if big[t]:
                    last = t
                t += 1
            clusters.append((t0, last))
        else:
            t += 1
    print(f"independent stress clusters (any name >100bp, 30 quiet days apart): {len(clusters)}")
    for a, b in clusters:
        nm = [stab[j] for j in range(K)
              if np.nanmax(np.abs(np.where(np.isfinite(devA[a:b + 1, j]), devA[a:b + 1, j], 0))) > 100 * bp]
        print(f"   {dates[a]}..{dates[b]}  {b - a + 1:4d}d  {','.join(x[:-4] for x in nm)}")

    out = {"n_clusters": len(clusters),
           "clusters": [dict(start=int(dates[a]), end=int(dates[b])) for a, b in clusters]}

    for name, (w, _) in books.items():
        bk = L.book_pnl(w, rA, legs, SW.FEE_BP)
        net = np.nan_to_num(bk["net"])
        # episode P&L = the book's net over the cluster window + a 30-day tail
        ep = []
        for a, b in clusters:
            hi = min(T, b + 31)
            ep.append(float(np.sum(net[a:hi])))
        ep = np.array(ep)
        # everything outside any cluster: the "quiet carry"
        inmask = np.zeros(T, bool)
        for a, b in clusters:
            inmask[a:min(T, b + 31)] = True
        quiet = float(np.sum(net[~inmask]))
        des_ep = np.array([e for (a, _), e in zip(clusters, ep) if dates[a] < SW.SPLIT])
        hld_ep = np.array([e for (a, _), e in zip(clusters, ep) if dates[a] >= SW.SPLIT])
        row = dict(n_episodes=len(ep),
                   mean_bp_per_episode=round(float(ep.mean()), 1),
                   median_bp_per_episode=round(float(np.median(ep)), 1),
                   t_across_episodes=round(float(ep.mean() / (ep.std(ddof=1) / np.sqrt(ep.size))), 2),
                   pct_episodes_positive=round(float(np.mean(ep > 0)), 2),
                   worst_episode_bp=round(float(ep.min()), 1),
                   best_episode_bp=round(float(ep.max()), 1),
                   quiet_period_total_bp=round(quiet, 1),
                   design_episodes=len(des_ep), held_episodes=len(hld_ep),
                   design_mean_bp=round(float(des_ep.mean()), 1) if des_ep.size else None,
                   held_mean_bp=round(float(hld_ep.mean()), 1) if hld_ep.size else None,
                   t_across_episodes_exUST=None)
        keep = np.array([not (20220501 <= dates[a] <= 20220601) for a, _ in clusters])
        e2 = ep[keep]
        row["t_across_episodes_exUST"] = round(float(e2.mean() / (e2.std(ddof=1) / np.sqrt(e2.size))), 2)
        row["mean_bp_per_episode_exUST"] = round(float(e2.mean()), 1)
        # per-instrument attribution over the whole sample
        contrib = {}
        for j, s in enumerate(stab):
            pj = float(np.nansum(np.where(np.isfinite(rA[:, j]), w[:, j] * rA[:, j], 0.0)) * 1e4)
            dj = int(np.sum(np.abs(w[:, j]) > 0))
            if dj:
                contrib[s] = dict(gross_bp=round(pj, 1), days_on=dj)
        row["per_instrument_gross"] = contrib
        out[name] = row
        print("\n" + name)
        print("  ", json.dumps({k: v for k, v in row.items() if k != "per_instrument_gross"}))
        print("   attribution:", json.dumps(contrib))

    with open(os.path.join(OUT, "INVENT_0822_crypto_tether_EVENTS.json"), "w") as fh:
        json.dump(out, fh, indent=1, default=float)


if __name__ == "__main__":
    main()
