#!/usr/bin/env python3
"""INVENT_0822 Family B -- SAME-ISSUER PREFERRED-SERIES relative value.

THE TETHER.  Two preferred series of the same issuer are claims of the SAME seniority on the
SAME balance sheet.  They differ only in coupon and call date.  Their prices therefore cannot
diverge permanently: the ratio of two same-credit perpetual claims is pinned by the ratio of
their coupons plus a call-option term.  This is a stronger structural anchor than a
cross-listing (no FX, no time-zone), stronger than a holdco (no NAV opacity, no discount
regime), and it exists at scale -- 85 issuers with >=2 listed series, 518 within-issuer pairs.

WHAT IS BEING TESTED, AND IN WHAT ORDER (the programme's own rule):
  1. GROSS first.  A signal that does not clear the multiple-testing bar at ZERO cost is dead
     and no cost-fix can save it.
  2. Only then the measured spread, and only then borrow (34 of 361 series are shortable, so
     the tradable pair set is 16 -- reported honestly whatever the gross number says).

Spread = log RAW price ratio (adjusted prices would inject a coupon-difference drift).
Returns = adjusted (total-return) closes, so the coupon carry the trade actually earns is in
the P&L.

Weekly sampling (Wednesday-anchored) because preferreds are illiquid and the daily close is a
stale/bouncing print; a daily variant is run as a declared control.
"""
from __future__ import annotations

import gzip
import itertools
import json
import math
import pathlib
import re
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from scripts.trading_bot.invent0822_pairtether import (  # noqa: E402
    adf_t, ar1_ou, block_boot, hurst_rs, rho1, summarise)

ROOT = pathlib.Path(__file__).resolve().parents[2]
CACHE = ROOT / "research" / "data" / "inv0822_tether"
OUT = ROOT / "research" / "trading_bot"

SEC31_BP = 0.278
BORROW_ANNUAL_BP = 200.0
DESIGN_END = "2023-12-31"


def load():
    adj = json.load(gzip.open(CACHE / "pref_bars.json.gz"))
    raw = json.load(gzip.open(CACHE / "pref_bars_raw.json.gz"))
    q = json.load(gzip.open(CACHE / "pref_halfspread.json.gz"))
    flags = json.load(gzip.open(CACHE / "pref_flags.json.gz"))
    return adj, raw, q, flags


def build_grid(raw, weekly=True):
    days = sorted({d for s in raw.values() for d in s})
    if not weekly:
        return days
    # Wednesday anchor: take every 5th session, which on a normal week is mid-week
    return days[::5]


def main(weekly=True):
    adj, raw, q, flags = load()
    pr = sorted(s for s in raw if re.match(r"^[A-Z]+\.PR[A-Z]$", s))
    grid = build_grid(raw, weekly)
    d0 = sum(1 for d in grid if d <= DESIGN_END)
    T = len(grid)
    print(f"grid {grid[0]} .. {grid[-1]} T={T} design={d0} weekly={weekly}", flush=True)

    # coverage screen: quoted on >=70% of the design grid, raw price in [3, 40] (a $25-par
    # preferred; anything outside is a broken/odd security), median price > $5
    syms = []
    for s in pr:
        r = raw[s]
        v = np.array([r.get(d, np.nan) for d in grid[:d0]], float)
        f = np.isfinite(v)
        if f.mean() < 0.70:
            continue
        med = float(np.nanmedian(v))
        if not (5.0 < med < 40.0):
            continue
        syms.append(s)
    n_pref = len(syms)
    print(f"screened preferred series: {n_pref} of {len(pr)}", flush=True)

    # the COMMON of each issuer, appended after the preferreds -- used only for the
    # pref-vs-common block the brief asks for (a deliberately WEAKER tether: different
    # seniority, so the ratio has no reason to be stationary; tested rather than assumed)
    roots_with_pref = sorted({s.split(".")[0] for s in syms})
    commons = []
    for c in roots_with_pref:
        r = raw.get(c)
        if not r:
            continue
        v = np.array([r.get(d, np.nan) for d in grid[:d0]], float)
        if np.isfinite(v).mean() < 0.70 or not np.isfinite(np.nanmedian(v)):
            continue
        if float(np.nanmedian(v)) < 5.0:
            continue
        commons.append(c)
    syms = syms + commons
    print(f"screened commons: {len(commons)}", flush=True)

    si = {s: k for k, s in enumerate(syms)}
    RAW = np.full((T, len(syms)), np.nan)
    ADJ = np.full((T, len(syms)), np.nan)
    for s in syms:
        k = si[s]
        rr, aa = raw[s], adj.get(s, {})
        for t, d in enumerate(grid):
            v = rr.get(d)
            if v:
                RAW[t, k] = v
            v = aa.get(d)
            if v:
                ADJ[t, k] = v
    RET = np.full_like(ADJ, np.nan)
    RET[:-1] = ADJ[1:] / ADJ[:-1] - 1.0

    # half-spread from the point-in-time quote snapshot
    HS = np.array([(q.get(s, {}).get("median_half_bp", np.nan)) for s in syms], float)
    med_hs = float(np.nanmedian(HS[np.isfinite(HS)])) if np.isfinite(HS).any() else np.nan
    HS = np.where(np.isfinite(HS), HS, med_hs)
    SHORT = np.array([bool(flags.get(s, {}).get("shortable")) for s in syms])
    print(f"measured half-spread bp: median {med_hs:.1f}  "
          f"p25 {np.nanpercentile(HS,25):.1f}  p75 {np.nanpercentile(HS,75):.1f}  "
          f"p90 {np.nanpercentile(HS,90):.1f}", flush=True)
    print(f"shortable series in screened set: {int(SHORT.sum())}", flush=True)

    # pairs: same issuer root
    byroot = {}
    for s in syms[:n_pref]:
        byroot.setdefault(s.split(".")[0], []).append(s)
    pairs = []
    for root, ss in byroot.items():
        for a, b in itertools.combinations(sorted(ss), 2):
            i, j = si[a], si[b]
            sp = np.log(RAW[:d0, i]) - np.log(RAW[:d0, j])
            f = np.isfinite(sp)
            if f.sum() < 100:
                continue
            spf = sp[f]
            pairs.append(dict(i=i, j=j, a=a, b=b, root=root,
                              rho1=rho1(np.diff(spf)), hurst=hurst_rs(spf),
                              adf=adf_t(spf), hl=ar1_ou(spf)[2],
                              sd_bp=float(spf.std(ddof=1) * 1e4),
                              both_short=bool(SHORT[i] and SHORT[j]),
                              any_short=bool(SHORT[i] or SHORT[j]),
                              short_a=bool(SHORT[i]), short_b=bool(SHORT[j]),
                              hs_bp=float(max(HS[i], HS[j]))))
    print(f"within-issuer pairs passing coverage: {len(pairs)}", flush=True)

    # pref-vs-common of the SAME issuer (the brief's item; a weaker tether, tested not assumed)
    pvc = []
    for c in commons:
        jc = si[c]
        for s in byroot.get(c, []):
            i = si[s]
            sp = np.log(RAW[:d0, i]) - np.log(RAW[:d0, jc])
            f = np.isfinite(sp)
            if f.sum() < 100:
                continue
            spf = sp[f]
            pvc.append(dict(i=i, j=jc, a=s, b=c, root=c,
                            rho1=rho1(np.diff(spf)), hurst=hurst_rs(spf), adf=adf_t(spf),
                            hl=ar1_ou(spf)[2], sd_bp=float(spf.std(ddof=1) * 1e4),
                            both_short=bool(SHORT[i] and SHORT[jc]),
                            any_short=bool(SHORT[i] or SHORT[jc]),
                            short_a=bool(SHORT[i]), short_b=bool(SHORT[jc]),
                            hs_bp=float(max(HS[i], HS[jc]))))
    print(f"pref-vs-common pairs: {len(pvc)}", flush=True)

    # placebo: cross-issuer preferred pairs -- same asset class, NO issuer tether
    rng = np.random.default_rng(20260822)
    plac = []
    while len(plac) < 500:
        i, j = rng.choice(n_pref, 2, replace=False)
        if syms[i].split(".")[0] == syms[j].split(".")[0]:
            continue
        sp = np.log(RAW[:d0, i]) - np.log(RAW[:d0, j])
        f = np.isfinite(sp)
        if f.sum() < 100:
            continue
        spf = sp[f]
        plac.append(dict(i=int(i), j=int(j), a=syms[i], b=syms[j], root="PLACEBO",
                         rho1=rho1(np.diff(spf)), hurst=hurst_rs(spf), adf=adf_t(spf),
                         hl=ar1_ou(spf)[2], sd_bp=float(spf.std(ddof=1) * 1e4),
                         both_short=bool(SHORT[i] and SHORT[j]),
                         any_short=bool(SHORT[i] or SHORT[j]),
                         short_a=bool(SHORT[i]), short_b=bool(SHORT[j]),
                         hs_bp=float(max(HS[i], HS[j]))))
    print(f"placebo cross-issuer pairs: {len(plac)}", flush=True)

    def gate(p):
        return (np.isfinite(p["rho1"]) and p["rho1"] > -0.35
                and np.isfinite(p["hurst"]) and p["hurst"] < 0.5
                and np.isfinite(p["adf"]) and p["adf"] < -2.57)

    tethers = {
        "PB_all_issuer": pairs,
        "PB_gated": [p for p in pairs if gate(p)],
        "PB_liquid": [p for p in pairs if p["hs_bp"] <= 30.0],
        "PB_gated_liquid": [p for p in pairs if gate(p) and p["hs_bp"] <= 30.0],
        "PB_shortable": [p for p in pairs if p["both_short"]],
        "PB_one_short": [p for p in pairs if p["any_short"]],
        "PB_gated_liquid_short": [p for p in pairs
                                  if gate(p) and p["hs_bp"] <= 30.0 and p["any_short"]],
        "PC_pref_vs_common": pvc,
        "PC_pvc_gated": [p for p in pvc if gate(p)],
        "PP_placebo": plac,
        "PP_placebo_gated": [p for p in plac if gate(p)],
    }
    for k, v in tethers.items():
        print(f"  {k:18s} n={len(v)}", flush=True)

    def spread_z(pairs, L):
        ia = np.array([p["i"] for p in pairs])
        ib = np.array([p["j"] for p in pairs])
        S = np.log(RAW[:, ia]) - np.log(RAW[:, ib])
        Z = np.full_like(S, np.nan)
        for t in range(L, T):
            w = S[t - L:t, :]
            n = np.isfinite(w).sum(0)
            mu = np.nanmean(np.where(np.isfinite(w), w, np.nan), 0)
            sd = np.nanstd(w, 0, ddof=1)
            Z[t] = np.where((n >= max(8, L // 2)) & (sd > 0), (S[t] - mu) / sd, np.nan)
        return Z

    def book(pairs, Z, *, K, X, maxhold, lo, hi, cost_mult=1.0, gross=False):
        ia = np.array([p["i"] for p in pairs])
        ib = np.array([p["j"] for p in pairs])
        hsp = np.array([p["hs_bp"] for p in pairs]) * 1e-4 * cost_mult
        n = len(pairs)
        w = np.zeros(n)
        age = np.zeros(n, int)
        borrow = BORROW_ANNUAL_BP * 1e-4 * 7.0 / 365.0 * (1 if weekly else 1 / 5.0)
        g_out, n_out, act_out = [], [], []
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
            dw = np.abs(nw - w)
            cost = dw * (2.0 * hsp + SEC31_BP * 1e-4) + np.abs(nw) * borrow
            gv = float(np.nansum(pr_[a]) / na)
            cv = float(np.nansum(cost[a]) / na)
            g_out.append(gv)
            n_out.append(gv if gross else gv - cv)
            act_out.append(na)
            w, age = nw, np.where(nw != 0, age + 1, 0)
        return np.array(g_out), np.array(n_out), np.array(act_out)

    cat = []

    def add(name, desc, tether, L, K, X, maxhold):
        cat.append(dict(name=name, desc=desc, tether=tether, L=L, K=K, X=X, maxhold=maxhold))

    add("B01", "same-issuer preferred pairs, log raw price ratio z52w, |z|>=2 -> 0.5, 26w cap",
        "PB_all_issuer", 52, 2.0, 0.5, 26)
    add("B02", "OU-gated same-issuer pairs (rho1>-.35,H<.5,ADF<-2.57), z52, |z|>=2 -> 0.5",
        "PB_gated", 52, 2.0, 0.5, 26)
    add("B03", "liquid same-issuer pairs (half-spread<=30bp), z52, |z|>=2 -> 0.5",
        "PB_liquid", 52, 2.0, 0.5, 26)
    add("B04", "OU-gated AND liquid, z52, |z|>=2 -> 0.5", "PB_gated_liquid", 52, 2.0, 0.5, 26)
    add("B05", "PLACEBO cross-issuer preferred pairs, z52, |z|>=2 -> 0.5",
        "PP_placebo", 52, 2.0, 0.5, 26)
    add("B06", "PLACEBO cross-issuer, OU-gated, z52, |z|>=2 -> 0.5",
        "PP_placebo_gated", 52, 2.0, 0.5, 26)
    add("B07", "same-issuer, SHORT normalisation z13, |z|>=2 -> 0.5",
        "PB_all_issuer", 13, 2.0, 0.5, 26)
    add("B08", "OU-gated, short normalisation z13, |z|>=2 -> 0.5", "PB_gated", 13, 2.0, 0.5, 26)
    add("B09", "same-issuer, wide band |z52|>=3 -> exit 1.0 (Bertram-flavoured)",
        "PB_all_issuer", 52, 3.0, 1.0, 52)
    add("B10", "OU-gated, wide band |z52|>=3 -> exit 1.0", "PB_gated", 52, 3.0, 1.0, 52)
    add("B11", "liquid, wide band |z52|>=3 -> exit 1.0", "PB_liquid", 52, 3.0, 1.0, 52)
    add("B12", "same-issuer, low band |z52|>=1 -> 0.25 (bounce control)",
        "PB_all_issuer", 52, 1.0, 0.25, 26)
    add("B13", "OU-gated, low band |z52|>=1 -> 0.25 (bounce control)",
        "PB_gated", 52, 1.0, 0.25, 26)
    add("B14", "same-issuer, full-reversion exit |z52|>=2 -> 0.0, 52w cap",
        "PB_all_issuer", 52, 2.0, 0.0, 52)
    add("B15", "OU-gated, full-reversion exit |z52|>=2 -> 0.0, 52w cap",
        "PB_gated", 52, 2.0, 0.0, 52)
    add("B16", "gated+liquid, wide band |z52|>=3 -> 1.0", "PB_gated_liquid", 52, 3.0, 1.0, 52)
    add("B17", "gated+liquid, z13 |z|>=2 -> 0.5", "PB_gated_liquid", 13, 2.0, 0.5, 26)
    add("B18", "BOTH-SHORTABLE pairs only (the actually-tradable set), z52 |z|>=2 -> 0.5",
        "PB_shortable", 52, 2.0, 0.5, 26)
    add("B19", "liquid, z26 |z|>=2.5 -> 0.5", "PB_liquid", 26, 2.5, 0.5, 26)
    add("B20", "same-issuer, z26 |z|>=2.5 -> 0.5", "PB_all_issuer", 26, 2.5, 0.5, 26)
    add("B21", "OU-gated, z26 |z|>=2.5 -> 0.5", "PB_gated", 26, 2.5, 0.5, 26)
    add("B22", "PLACEBO cross-issuer, z26 |z|>=2.5 -> 0.5", "PP_placebo", 26, 2.5, 0.5, 26)
    add("B23", "PREFERRED vs its OWN COMMON, same issuer, z52 |z|>=2 -> 0.5 (weak-tether test)",
        "PC_pref_vs_common", 52, 2.0, 0.5, 26)
    add("B24", "PREFERRED vs OWN COMMON, OU-gated, z52 |z|>=2 -> 0.5",
        "PC_pvc_gated", 52, 2.0, 0.5, 26)
    add("B25", "PREFERRED vs OWN COMMON, wide band z52 |z|>=3 -> 1.0",
        "PC_pref_vs_common", 52, 3.0, 1.0, 52)
    add("B26", "at-least-one-leg-shortable same-issuer pairs, z52 |z|>=2 -> 0.5",
        "PB_one_short", 52, 2.0, 0.5, 26)
    add("B27", "gated + liquid + one leg shortable, z52 |z|>=2 -> 0.5",
        "PB_gated_liquid_short", 52, 2.0, 0.5, 26)

    Zc = {}
    res = []
    for f in cat:
        ps = tethers[f["tether"]]
        if len(ps) < 3:
            res.append(dict(f, skipped="too few pairs", n_pairs=len(ps)))
            print(f"{f['name']} SKIP n={len(ps)}", flush=True)
            continue
        key = (f["tether"], f["L"])
        if key not in Zc:
            Zc[key] = spread_z(ps, f["L"])
        Z = Zc[key]
        kw = dict(K=f["K"], X=f["X"], maxhold=f["maxhold"])
        gD, nD, aD = book(ps, Z, lo=f["L"], hi=d0, **kw)
        gH, nH, aH = book(ps, Z, lo=d0, hi=T, **kw)
        _, nDx, _ = book(ps, Z, lo=f["L"], hi=d0, cost_mult=2.0, **kw)
        _, nHx, _ = book(ps, Z, lo=d0, hi=T, cost_mult=2.0, **kw)
        r = dict(f, n_pairs=len(ps),
                 design_gross=summarise(gD), design_net=summarise(nD),
                 design_2x=summarise(nDx),
                 held_gross=summarise(gH), held_net=summarise(nH), held_2x=summarise(nHx),
                 held_net_boot=block_boot(nH),
                 avg_active_design=float(np.mean(aD)) if len(aD) else 0.0,
                 avg_active_held=float(np.mean(aH)) if len(aH) else 0.0)
        res.append(r)
        print(f"{f['name']} {f['tether']:17s} np={len(ps):4d} "
              f"Dg={r['design_gross']['ann_sharpe']:6.2f}/t{r['design_gross']['t']:5.2f} "
              f"Dn={r['design_net']['ann_sharpe']:6.2f}/t{r['design_net']['t']:5.2f} "
              f"Hg={r['held_gross']['ann_sharpe']:6.2f} "
              f"Hn={r['held_net']['ann_sharpe']:6.2f}/t{r['held_net']['t']:5.2f} "
              f"H2x={r['held_2x']['ann_sharpe']:6.2f} act={r['avg_active_design']:.0f}",
              flush=True)

    scored = [r for r in res if "skipped" not in r and not r["tether"].startswith("PP")]
    N = len(scored)
    bar = math.sqrt(2 * math.log(2 * N)) if N else float("nan")
    payload = dict(family="B_same_issuer_preferred_series",
                   grid=[grid[0], grid[-1]], design_end=DESIGN_END, weekly=weekly,
                   n_series=n_pref, n_commons=len(commons),
                   n_pairs=len(pairs), n_pvc=len(pvc), n_placebo=len(plac),
                   median_half_spread_bp=med_hs,
                   n_shortable_series=int(SHORT.sum()),
                   tether_counts={k: len(v) for k, v in tethers.items()},
                   n_scored=N, noise_bar_t=bar, pair_stats=pairs, results=res)
    (OUT / "INVENT_0822_pairtether_B.json").write_text(
        json.dumps(payload, indent=1, default=float))
    print(f"\nN scored = {N}, noise bar sqrt(2 ln 2N) = {bar:.3f}")


if __name__ == "__main__":
    main(weekly=("--daily" not in sys.argv))
