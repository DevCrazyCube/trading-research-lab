#!/usr/bin/env python3
"""Empirical nulls for Family B, matched on PAIR-SET SIZE.

The only Family-B cells that survive the measured preferred half-spread hold SIX pairs and
carry one or two concurrent positions.  A t-statistic computed on such a book is not an honest
t, so the bar is measured, twice:

  N1  size-6 draws from GATED + LIQUID **cross-issuer** (untethered) pairs -- does the
      OU gate plus a liquidity screen manufacture this result with no tether at all?
  N2  size-6 draws from ALL same-issuer pairs (tether present, gate absent) -- does the OU
      gate add anything beyond simply holding six tethered pairs?
"""
from __future__ import annotations

import gzip
import itertools
import json
import pathlib
import re
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
import scripts.trading_bot.invent0822_preftether as PT  # noqa: E402
from scripts.trading_bot.invent0822_pairtether import (  # noqa: E402
    adf_t, ar1_ou, hurst_rs, rho1, summarise)

OUT = pathlib.Path(__file__).resolve().parents[2] / "research" / "trading_bot"
CACHE = PT.CACHE
DRAWS = 400
SIZE = 6


def main():
    adj, raw, q, flags = PT.load()
    pr = sorted(s for s in raw if re.match(r"^[A-Z]+\.PR[A-Z]$", s))
    grid = PT.build_grid(raw, True)
    d0 = sum(1 for d in grid if d <= PT.DESIGN_END)
    T = len(grid)
    syms = []
    for s in pr:
        v = np.array([raw[s].get(d, np.nan) for d in grid[:d0]], float)
        if np.isfinite(v).mean() < 0.70:
            continue
        m = float(np.nanmedian(v))
        if not (5.0 < m < 40.0):
            continue
        syms.append(s)
    si = {s: k for k, s in enumerate(syms)}
    RAW = np.full((T, len(syms)), np.nan)
    ADJ = np.full((T, len(syms)), np.nan)
    for s in syms:
        k = si[s]
        for t, d in enumerate(grid):
            v = raw[s].get(d)
            if v:
                RAW[t, k] = v
            v = adj.get(s, {}).get(d)
            if v:
                ADJ[t, k] = v
    RET = np.full_like(ADJ, np.nan)
    RET[:-1] = ADJ[1:] / ADJ[:-1] - 1.0
    HS = np.array([q.get(s, {}).get("median_half_bp", np.nan) for s in syms], float)
    HS = np.where(np.isfinite(HS), HS, np.nanmedian(HS))

    def stats(i, j):
        sp = np.log(RAW[:d0, i]) - np.log(RAW[:d0, j])
        f = np.isfinite(sp)
        if f.sum() < 100:
            return None
        spf = sp[f]
        return dict(i=int(i), j=int(j), rho1=rho1(np.diff(spf)), hurst=hurst_rs(spf),
                    adf=adf_t(spf), hs_bp=float(max(HS[i], HS[j])))

    def gate(p):
        return (p and np.isfinite(p["rho1"]) and p["rho1"] > -0.35
                and np.isfinite(p["hurst"]) and p["hurst"] < 0.5
                and np.isfinite(p["adf"]) and p["adf"] < -2.57 and p["hs_bp"] <= 30.0)

    byroot = {}
    for s in syms:
        byroot.setdefault(s.split(".")[0], []).append(s)
    tethered = []
    for root, ss in byroot.items():
        for a, b in itertools.combinations(sorted(ss), 2):
            p = stats(si[a], si[b])
            if p:
                tethered.append(p)
    print(f"tethered same-issuer pairs: {len(tethered)}", flush=True)

    rng = np.random.default_rng(31337)
    pool_gl = []
    seen = set()
    tries = 0
    while len(pool_gl) < 400 and tries < 300000:
        tries += 1
        i, j = rng.choice(len(syms), 2, replace=False)
        if syms[i].split(".")[0] == syms[j].split(".")[0]:
            continue
        k = (int(min(i, j)), int(max(i, j)))
        if k in seen:
            continue
        seen.add(k)
        p = stats(i, j)
        if gate(p):
            pool_gl.append(p)
    print(f"gated+liquid UNTETHERED pool: {len(pool_gl)} (from {tries} draws)", flush=True)

    def book(ps, *, K, X, maxhold, L, lo, hi, cost_mult=1.0):
        ia = np.array([p["i"] for p in ps])
        ib = np.array([p["j"] for p in ps])
        S = np.log(RAW[:, ia]) - np.log(RAW[:, ib])
        Z = np.full_like(S, np.nan)
        for t in range(L, T):
            w = S[t - L:t, :]
            n = np.isfinite(w).sum(0)
            mu = np.nanmean(w, 0)
            sd = np.nanstd(w, 0, ddof=1)
            Z[t] = np.where((n >= max(8, L // 2)) & (sd > 0), (S[t] - mu) / sd, np.nan)
        hsp = np.array([p["hs_bp"] for p in ps]) * 1e-4 * cost_mult
        n = len(ps)
        w = np.zeros(n)
        age = np.zeros(n, int)
        borrow = PT.BORROW_ANNUAL_BP * 1e-4 * 7.0 / 365.0
        g, nt = [], []
        for t in range(lo, hi):
            z = Z[t]
            nw = w.copy()
            nw[(w != 0) & np.isfinite(z) & (np.abs(z) <= X)] = 0.0
            nw[(w != 0) & (age >= maxhold)] = 0.0
            rr = RET[t]
            dead = ~np.isfinite(rr[ia]) | ~np.isfinite(rr[ib])
            nw[dead] = 0.0
            en = (nw == 0) & np.isfinite(z) & (np.abs(z) >= K) & ~dead
            nw[en] = -np.sign(z[en])
            a = nw != 0
            na = int(a.sum())
            if na == 0:
                w, age = nw, np.where(nw != 0, age + 1, 0)
                continue
            pr_ = nw * (rr[ia] - rr[ib])
            cost = np.abs(nw - w) * (2 * hsp + PT.SEC31_BP * 1e-4) + np.abs(nw) * borrow
            gv = float(np.nansum(pr_[a]) / na)
            g.append(gv)
            nt.append(gv - float(np.nansum(cost[a]) / na))
            w, age = nw, np.where(nw != 0, age + 1, 0)
        return np.array(g), np.array(nt)

    specs = {"B04_z52_K2_X0.5": dict(L=52, K=2.0, X=0.5, maxhold=26),
             "B16_z52_K3_X1.0": dict(L=52, K=3.0, X=1.0, maxhold=52)}
    out = {}
    for label, pool in (("N1_untethered_gated_liquid", pool_gl), ("N2_tethered_ungated",
                                                                  tethered)):
        for sname, sp in specs.items():
            dn, hn, h2 = [], [], []
            for d in range(DRAWS):
                ps = [pool[k] for k in rng.choice(len(pool), SIZE, replace=False)]
                _, a = book(ps, lo=sp["L"], hi=d0, **sp)
                _, b = book(ps, lo=d0, hi=T, **sp)
                _, c = book(ps, lo=d0, hi=T, cost_mult=2.0, **sp)
                dn.append(summarise(a)["ann_sharpe"])
                hn.append(summarise(b)["ann_sharpe"])
                h2.append(summarise(c)["ann_sharpe"])

            def qq(v):
                v = np.array([x for x in v if np.isfinite(x)], float)
                return dict(n=int(v.size), mean=float(v.mean()), sd=float(v.std(ddof=1)),
                            p50=float(np.percentile(v, 50)), p90=float(np.percentile(v, 90)),
                            p95=float(np.percentile(v, 95)), p99=float(np.percentile(v, 99)),
                            max=float(v.max()))
            out[f"{label}|{sname}"] = dict(design_net=qq(dn), held_net=qq(hn), held_2x=qq(h2))
            r = out[f"{label}|{sname}"]
            print(f"{label} {sname}: held_net p50 {r['held_net']['p50']:.2f} "
                  f"p90 {r['held_net']['p90']:.2f} p95 {r['held_net']['p95']:.2f} "
                  f"p99 {r['held_net']['p99']:.2f} max {r['held_net']['max']:.2f} | "
                  f"held2x p95 {r['held_2x']['p95']:.2f} max {r['held_2x']['max']:.2f}",
                  flush=True)

    (OUT / "INVENT_0822_pairtether_B_null.json").write_text(
        json.dumps(dict(draws=DRAWS, size=SIZE, null=out), indent=1, default=float))


if __name__ == "__main__":
    main()
