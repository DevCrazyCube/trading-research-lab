#!/usr/bin/env python3
"""INVENT_0822 -- STRUCTURALLY-ANCHORED COINTEGRATED SPREADS AT SCALE.

Family A: PAIRWISE closed-end-fund relative-premium reversion.

The tether under test is NOT "price reverts to NAV" (that is the incumbent L5 tilt, already
owned).  It is: **two closed-end funds run by the same manager against the same mandate hold
near-identical portfolios, so the DIFFERENCE of their premia has no fundamental reason to
drift permanently.**  That is a real economic anchor and it is a *pairwise* object, so it can
be tested with the OU / Hurst / ADF / rho1(ds) apparatus the programme adopted, which the
cross-sectional decile tilt cannot.

Everything is cached and free (research/data/t12_cache).  No network call.

Costs, windows and stresses are inherited verbatim from DEEPMINE_CEFNAV so the numbers are
directly comparable to the incumbent:
  * measured 11.53 bp CEF half-spread (p90 27.25 bp as a stress) on BOTH legs of turnover
  * SEC 31 fee 0.278 bp on sale notional
  * borrow at the REALISED 200 bp/yr short rate on the short leg
  * one-trading-day implementation lag (CEFConnect publishes NAV after the close)
  * design 2021-08-20 .. 2024-02-23   held out 2024-03-01 .. 2026-08-14
"""
from __future__ import annotations

import itertools
import json
import math
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from scripts.trading_bot.deepmine_cefnav import build_panel  # noqa: E402

OUT = pathlib.Path(__file__).resolve().parents[2] / "research" / "trading_bot"

HALF_SPREAD_BP = 11.53
HALF_SPREAD_P90_BP = 27.25
SEC31_BP = 0.278
BORROW_ANNUAL_BP = 200.0
DESIGN_END = "2024-02-23"

# --------------------------------------------------------------------------- stats


def rho1(x):
    x = x[np.isfinite(x)]
    if x.size < 20:
        return np.nan
    x = x - x.mean()
    d = (x * x).sum()
    return float((x[1:] * x[:-1]).sum() / d) if d > 0 else np.nan


def ar1_ou(s, dt=1.0):
    """Exact AR(1) fit -> (phi, theta, halflife, sigma_eq)."""
    s = s[np.isfinite(s)]
    if s.size < 30:
        return (np.nan,) * 4
    y, x = s[1:], s[:-1]
    xm, ym = x.mean(), y.mean()
    vx = ((x - xm) ** 2).sum()
    if vx <= 0:
        return (np.nan,) * 4
    phi = float(((x - xm) * (y - ym)).sum() / vx)
    a = ym - phi * xm
    res = y - (a + phi * x)
    sig = float(res.std(ddof=2))
    if not (0 < phi < 1):
        return (phi, np.nan, np.nan, np.nan)
    theta = -math.log(phi) / dt
    hl = math.log(2) / theta
    seq = sig / math.sqrt(1 - phi * phi)
    return (phi, theta, hl, seq)


def adf_t(s, lags=1):
    """ADF with a constant; MacKinnon CVs -3.43 / -2.86 / -2.57."""
    s = s[np.isfinite(s)]
    n = s.size
    if n < 40:
        return np.nan
    dy = np.diff(s)
    ylag = s[:-1]
    cols = [np.ones(n - 1), ylag]
    for L in range(1, lags + 1):
        c = np.full(n - 1, np.nan)
        c[L:] = dy[:-L]
        cols.append(c)
    X = np.column_stack(cols)
    ok = np.isfinite(X).all(1)
    X, yv = X[ok], dy[ok]
    if X.shape[0] <= X.shape[1] + 5:
        return np.nan
    try:
        XtX = X.T @ X
        beta = np.linalg.solve(XtX, X.T @ yv)
        r = yv - X @ beta
        dof = X.shape[0] - X.shape[1]
        s2 = float(r @ r) / dof
        se = math.sqrt(s2 * np.linalg.inv(XtX)[1, 1])
        return float(beta[1] / se) if se > 0 else np.nan
    except np.linalg.LinAlgError:
        return np.nan


def hurst_rs(s):
    s = s[np.isfinite(s)]
    n = s.size
    if n < 48:
        return np.nan
    x = np.diff(s)
    n = x.size
    sizes, rs = [], []
    m = 4
    while m <= n // 3:
        k = n // m
        vals = []
        for b in range(k):
            seg = x[b * m:(b + 1) * m]
            z = np.cumsum(seg - seg.mean())
            sd = seg.std(ddof=1)
            if sd > 0:
                vals.append((z.max() - z.min()) / sd)
        if vals:
            sizes.append(m)
            rs.append(np.mean(vals))
        m *= 2
    if len(sizes) < 3:
        return np.nan
    return float(np.polyfit(np.log(sizes), np.log(rs), 1)[0])


def block_boot(r, block=8, draws=4000, seed=7):
    r = np.asarray([v for v in r if np.isfinite(v)], float)
    if r.size < 3 * block:
        return dict(p_pos=np.nan, lo=np.nan, hi=np.nan)
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(r.size / block))
    starts = rng.integers(0, max(1, r.size - block), size=(draws, nb))
    means = np.empty(draws)
    for d in range(draws):
        seg = np.concatenate([r[s:s + block] for s in starts[d]])[:r.size]
        means[d] = seg.mean()
    return dict(p_pos=float((means > 0).mean()),
                lo=float(np.percentile(means, 2.5) * 1e4),
                hi=float(np.percentile(means, 97.5) * 1e4))


def summarise(r, per_year=52.0):
    r = np.asarray([v for v in r if np.isfinite(v)], float)
    n = r.size
    if n < 8:
        return dict(n=n, mean_bp=np.nan, t=np.nan, ann_sharpe=np.nan)
    mu, sd = float(r.mean()), float(r.std(ddof=1))
    t = mu / (sd / math.sqrt(n)) if sd > 0 else np.nan
    return dict(n=n, mean_bp=mu * 1e4, t=t,
                ann_sharpe=(mu / sd * math.sqrt(per_year)) if sd > 0 else np.nan)


# --------------------------------------------------------------------------- pairs


def build_pairs(pan, dsplit):
    """Every within-category CEF pair that is tradable, stamped with its tether attributes.

    Tether attributes are measured on the DESIGN window only (NAV-return correlation), or are
    static facts (sponsor, category).  No P&L is consulted.
    """
    tk, cat, spon, etb = pan["tickers"], pan["cat"], pan["spon"], pan["etb"]
    P, RVT, D = pan["P"], pan["RVT"], pan["D"]
    A = pan["A"]
    N = len(tk)
    d0 = dsplit

    # tradability: quoted on >=60% of the design grid, raw price > $5 throughout, both ETB
    ok = np.zeros(N, bool)
    for i in range(N):
        p = P[:d0, i]
        f = np.isfinite(p)
        ok[i] = (f.mean() > 0.60) and etb[i] and np.nanmin(p[f]) > 5.0 if f.any() else False

    pairs = []
    idx = [i for i in range(N) if ok[i]]
    for i, j in itertools.combinations(idx, 2):
        if cat[i] != cat[j]:
            continue
        a, b = RVT[:d0, i], RVT[:d0, j]
        m = np.isfinite(a) & np.isfinite(b)
        if m.sum() < 80:
            continue
        c = float(np.corrcoef(a[m], b[m])[0, 1])
        s = D[:d0, i] - D[:d0, j]
        sf = s[np.isfinite(s)]
        if sf.size < 80:
            continue
        pairs.append(dict(i=i, j=j, a=tk[i], b=tk[j], cat=str(cat[i]),
                          same_sponsor=bool(spon[i] == spon[j]),
                          navcorr=c,
                          rho1=rho1(np.diff(sf)),
                          hurst=hurst_rs(sf), adf=adf_t(sf),
                          hl=ar1_ou(sf)[2], sd=float(sf.std(ddof=1))))
    return pairs, ok


def random_pairs(pan, ok, dsplit, n=400, seed=20260822):
    """Placebo: cross-category pairs with NO tether at all."""
    rng = np.random.default_rng(seed)
    cat, D, tk = pan["cat"], pan["D"], pan["tickers"]
    idx = np.array([i for i in range(len(tk)) if ok[i]])
    out, tries = [], 0
    while len(out) < n and tries < 40 * n:
        tries += 1
        i, j = rng.choice(idx, 2, replace=False)
        if cat[i] == cat[j]:
            continue
        s = D[:dsplit, i] - D[:dsplit, j]
        sf = s[np.isfinite(s)]
        if sf.size < 80:
            continue
        out.append(dict(i=int(i), j=int(j), a=tk[i], b=tk[j], cat="PLACEBO",
                        same_sponsor=False, navcorr=np.nan, rho1=rho1(np.diff(sf)),
                        hurst=np.nan, adf=np.nan, hl=np.nan, sd=float(sf.std(ddof=1))))
    return out


# --------------------------------------------------------------------------- spreads


def spread_matrix(pan, pairs, kind):
    """(T, P) matrix of the pair spread."""
    D, A, P, V = pan["D"], pan["A"], pan["P"], pan["V"]
    T = D.shape[0]
    S = np.full((T, len(pairs)), np.nan)
    for k, p in enumerate(pairs):
        i, j = p["i"], p["j"]
        if kind == "prem":            # premium difference, percentage points
            S[:, k] = D[:, i] - D[:, j]
        elif kind == "logprem":       # log premium difference (P/V in logs)
            S[:, k] = np.log(P[:, i] / V[:, i]) - np.log(P[:, j] / V[:, j])
        elif kind == "pricecoint":    # pure price cointegration residual, NO NAV information
            x = np.log(A[:, i]) - np.log(A[:, j])
            S[:, k] = x
        else:
            raise ValueError(kind)
    return S


def rollz(S, L):
    T, P = S.shape
    Z = np.full_like(S, np.nan)
    for t in range(L, T):
        w = S[t - L:t, :]                      # STRICTLY past, excludes t
        n = np.isfinite(w).sum(0)
        mu = np.nanmean(w, 0)
        sd = np.nanstd(w, 0, ddof=1)
        good = (n >= max(20, L // 2)) & (sd > 0)
        z = np.where(good, (S[t] - mu) / sd, np.nan)
        Z[t] = z
    return Z


# --------------------------------------------------------------------------- book


def run_book(pan, pairs, Z, *, K, X, maxhold, rkey="R", hs_bp=HALF_SPREAD_BP,
             lo=0, hi=None, gross_only=False, resid_hedge=False):
    """Overlapping pair book.  Returns weekly portfolio return series over [lo, hi).

    Position convention: w=+1 -> long leg a, short leg b.  Entered when z <= -K (a cheap
    relative to b), w=-1 when z >= +K.  Exit on |z| <= X or after `maxhold` weeks.
    """
    R = pan[rkey]
    T = R.shape[0]
    hi = T if hi is None else hi
    npair = len(pairs)
    ia = np.array([p["i"] for p in pairs])
    ib = np.array([p["j"] for p in pairs])

    w = np.zeros(npair)
    age = np.zeros(npair, int)
    hs = hs_bp * 1e-4
    sec = SEC31_BP * 1e-4
    borrow_wk = BORROW_ANNUAL_BP * 1e-4 * 7.0 / 365.0

    gross_out, net_out, nact = [], [], []
    for t in range(lo, hi):
        z = Z[t]
        neww = w.copy()
        # exits
        ex = (w != 0) & (np.isfinite(z)) & (np.abs(z) <= X)
        neww[ex] = 0.0
        ex2 = (w != 0) & (age >= maxhold)
        neww[ex2] = 0.0
        # dead data -> flat
        rr = R[t]
        dead = ~np.isfinite(rr[ia]) | ~np.isfinite(rr[ib])
        neww[dead] = 0.0
        # entries
        en = (neww == 0) & np.isfinite(z) & (np.abs(z) >= K) & ~dead
        neww[en] = -np.sign(z[en])

        dw = np.abs(neww - w)
        act = neww != 0
        na = int(act.sum())
        if na == 0:
            w = neww
            age = np.where(neww != 0, age + 1, 0)
            continue
        pr = neww * (rr[ia] - rr[ib])
        # cost per unit of pair notional: turnover on BOTH legs
        cost = dw * (2.0 * hs + sec) + np.abs(neww) * borrow_wk
        g = float(np.nansum(pr[act]) / na)
        c = float(np.nansum(cost[act]) / na)
        gross_out.append(g)
        net_out.append(g if gross_only else g - c)
        nact.append(na)
        w = neww
        age = np.where(neww != 0, age + 1, 0)
    return np.array(gross_out), np.array(net_out), np.array(nact)


def run_book_fixed(pan, pairs, Z, *, K, H, rkey="R", hs_bp=HALF_SPREAD_BP, lo=0, hi=None):
    """Fixed-H-week hold with overlapping tranches (L5's own construction, pairwise)."""
    R = pan[rkey]
    T = R.shape[0]
    hi = T if hi is None else hi
    npair = len(pairs)
    ia = np.array([p["i"] for p in pairs])
    ib = np.array([p["j"] for p in pairs])
    hs = hs_bp * 1e-4
    sec = SEC31_BP * 1e-4
    borrow_wk = BORROW_ANNUAL_BP * 1e-4 * 7.0 / 365.0
    tranches = []                              # (expiry, w vector)
    gross_out, net_out, nact = [], [], []
    prev = np.zeros(npair)
    for t in range(lo, hi):
        z = Z[t]
        tranches = [(e, v) for (e, v) in tranches if e > t]
        sig = np.zeros(npair)
        m = np.isfinite(z) & (np.abs(z) >= K)
        sig[m] = -np.sign(z[m])
        if m.any():
            tranches.append((t + H, sig))
        if not tranches:
            prev = np.zeros(npair)
            continue
        w = np.mean([v for (_, v) in tranches], axis=0)
        rr = R[t]
        dead = ~np.isfinite(rr[ia]) | ~np.isfinite(rr[ib])
        w = np.where(dead, 0.0, w)
        tot = np.abs(w).sum()
        if tot <= 0:
            prev = w
            continue
        pr = w * (rr[ia] - rr[ib])
        dw = np.abs(w - prev)
        cost = dw * (2.0 * hs + sec) + np.abs(w) * borrow_wk
        g = float(np.nansum(pr) / tot)
        c = float(np.nansum(cost) / tot)
        gross_out.append(g)
        net_out.append(g - c)
        nact.append(int((np.abs(w) > 1e-9).sum()))
        prev = w
    return np.array(gross_out), np.array(net_out), np.array(nact)


# --------------------------------------------------------------------------- main

def main():
    pan = build_panel()
    grid = pan["grid"]
    d0 = sum(1 for d in grid if d <= DESIGN_END)
    print(f"grid {grid[0]} .. {grid[-1]}  T={len(grid)}  design weeks={d0}", flush=True)

    pairs_all, ok = build_pairs(pan, d0)
    print(f"within-category tradable pairs: {len(pairs_all)}", flush=True)
    plac = random_pairs(pan, ok, d0)
    print(f"placebo cross-category pairs: {len(plac)}", flush=True)

    def sel(pred):
        return [p for p in pairs_all if pred(p)]

    tethers = {
        "TA_sponsor_cat": sel(lambda p: p["same_sponsor"]),
        "TB_cat_nav97": sel(lambda p: p["navcorr"] >= 0.97),
        "TC_sponsor_nav95": sel(lambda p: p["same_sponsor"] and p["navcorr"] >= 0.95),
        "TD_cat_any": pairs_all,
        "TE_placebo_xcat": plac,
        "TF_gated": sel(lambda p: p["navcorr"] >= 0.95 and p["rho1"] > -0.35
                        and p["hurst"] < 0.5 and p["adf"] < -2.57),
    }
    # sub-class blocks: the whole block is added, so there is no cherry-picking inside it
    grp = pan["grp"]
    for g in ("MUNI", "TAXFI", "EQUITY", "HYBRID"):
        tethers[f"TG_{g}"] = sel(lambda p, g=g: grp[p["i"]] == g and p["navcorr"] >= 0.95)
    for k, v in tethers.items():
        print(f"  {k:20s} n_pairs={len(v)}", flush=True)

    S_cache = {}

    def get_Z(pairs, kind, L, key):
        ck = (key, kind, L)
        if ck not in S_cache:
            S_cache[ck] = rollz(spread_matrix(pan, pairs, kind), L)
        return S_cache[ck]

    # ---- the formula catalogue (structurally different cells, not a parameter grid)
    cat = []

    def add(name, desc, tether, kind, L, mode, **kw):
        cat.append(dict(name=name, desc=desc, tether=tether, kind=kind, L=L,
                        mode=mode, **kw))

    # band/threshold reverters on the premium spread, across tether definitions
    add("A01", "same-sponsor+same-category premium spread, z26, |z|>=2 -> 0.5, 20w cap",
        "TA_sponsor_cat", "prem", 26, "band", K=2.0, X=0.5, maxhold=20)
    add("A02", "same-category NAVcorr>=0.97 premium spread, z26, |z|>=2 -> 0.5",
        "TB_cat_nav97", "prem", 26, "band", K=2.0, X=0.5, maxhold=20)
    add("A03", "same-sponsor NAVcorr>=0.95 premium spread, z26, |z|>=2 -> 0.5",
        "TC_sponsor_nav95", "prem", 26, "band", K=2.0, X=0.5, maxhold=20)
    add("A04", "any same-category pair (loose tether control), z26, |z|>=2 -> 0.5",
        "TD_cat_any", "prem", 26, "band", K=2.0, X=0.5, maxhold=20)
    add("A05", "PLACEBO cross-category pairs, z26, |z|>=2 -> 0.5",
        "TE_placebo_xcat", "prem", 26, "band", K=2.0, X=0.5, maxhold=20)
    add("A06", "OU-gated pairs (rho1>-0.35, H<0.5, ADF<-2.57, corr>=.95), z26, |z|>=2 -> 0.5",
        "TF_gated", "prem", 26, "band", K=2.0, X=0.5, maxhold=20)

    # Bertram-flavoured band geometry (higher entry, higher exit) -- a different trade, not a tweak
    add("A07", "same-sponsor+cat, Bertram-flavoured band |z|>=3 -> exit 1.0",
        "TA_sponsor_cat", "prem", 26, "band", K=3.0, X=1.0, maxhold=26)
    add("A08", "OU-gated, Bertram-flavoured band |z|>=3 -> exit 1.0",
        "TF_gated", "prem", 26, "band", K=3.0, X=1.0, maxhold=26)

    # fixed-horizon overlapping tranches -- L5's own construction made pairwise
    add("A09", "same-sponsor+cat, |z26|>=1.5 signal, fixed 4-week overlapping tranches",
        "TA_sponsor_cat", "prem", 26, "fixed", K=1.5, H=4)
    add("A10", "OU-gated, |z26|>=1.5 signal, fixed 4-week overlapping tranches",
        "TF_gated", "prem", 26, "fixed", K=1.5, H=4)
    add("A11", "same-category NAVcorr>=0.97, |z26|>=1.5, fixed 8-week tranches",
        "TB_cat_nav97", "prem", 26, "fixed", K=1.5, H=8)
    add("A12", "PLACEBO cross-category, |z26|>=1.5, fixed 4-week tranches",
        "TE_placebo_xcat", "prem", 26, "fixed", K=1.5, H=4)

    # longer normalisation window: a genuinely different spread mean
    add("A13", "same-sponsor+cat, z52 (one-year mean), |z|>=2 -> 0.5",
        "TA_sponsor_cat", "prem", 52, "band", K=2.0, X=0.5, maxhold=20)
    add("A14", "OU-gated, z52, |z|>=2 -> 0.5", "TF_gated", "prem", 52, "band",
        K=2.0, X=0.5, maxhold=20)
    add("A15", "same-category NAVcorr>=0.97, z52, |z|>=2 -> 0.5", "TB_cat_nav97", "prem",
        52, "band", K=2.0, X=0.5, maxhold=20)

    # log-premium spread: a different functional form of the same tether
    add("A16", "same-sponsor+cat, LOG premium spread, z26, |z|>=2 -> 0.5",
        "TA_sponsor_cat", "logprem", 26, "band", K=2.0, X=0.5, maxhold=20)
    add("A17", "OU-gated, LOG premium spread, z26, |z|>=2 -> 0.5",
        "TF_gated", "logprem", 26, "band", K=2.0, X=0.5, maxhold=20)

    # PRICE-ONLY cointegration: the same pairs with the NAV information REMOVED.
    # This is the decisive discriminator -- if price-only does as well, the "tether" is not
    # doing any work and the object is a plain statistical pair trade.
    add("A18", "same-sponsor+cat, PRICE-ONLY log-ratio z26 (no NAV), |z|>=2 -> 0.5",
        "TA_sponsor_cat", "pricecoint", 26, "band", K=2.0, X=0.5, maxhold=20)
    add("A19", "OU-gated, PRICE-ONLY log-ratio z26 (no NAV), |z|>=2 -> 0.5",
        "TF_gated", "pricecoint", 26, "band", K=2.0, X=0.5, maxhold=20)
    add("A20", "PLACEBO cross-category, PRICE-ONLY log-ratio z26, |z|>=2 -> 0.5",
        "TE_placebo_xcat", "pricecoint", 26, "band", K=2.0, X=0.5, maxhold=20)

    # slow band: does the edge live at long holds (the CEF discount clock is ~7 weeks)?
    add("A21", "same-sponsor+cat, |z26|>=2, exit only at |z|<=0 (full reversion), 52w cap",
        "TA_sponsor_cat", "prem", 26, "band", K=2.0, X=0.0, maxhold=52)
    add("A22", "OU-gated, |z26|>=2, full-reversion exit, 52w cap",
        "TF_gated", "prem", 26, "band", K=2.0, X=0.0, maxhold=52)

    # low band -- deliberately inside the bounce, as the microstructure control
    add("A23", "same-sponsor+cat, LOW band |z26|>=1 -> 0.25 (bounce control)",
        "TA_sponsor_cat", "prem", 26, "band", K=1.0, X=0.25, maxhold=20)
    add("A24", "OU-gated, LOW band |z26|>=1 -> 0.25 (bounce control)",
        "TF_gated", "prem", 26, "band", K=1.0, X=0.25, maxhold=20)

    # sub-class blocks, added as a complete block (no selection inside it)
    for g in ("MUNI", "TAXFI", "EQUITY", "HYBRID"):
        add(f"A{25 + ('MUNI TAXFI EQUITY HYBRID'.split().index(g))}",
            f"{g} sub-class only, NAVcorr>=0.95 premium spread, z26, |z|>=2 -> 0.5",
            f"TG_{g}", "prem", 26, "band", K=2.0, X=0.5, maxhold=20)

    results = []
    T = len(grid)
    for f in cat:
        pairs = tethers[f["tether"]]
        if len(pairs) < 3:
            results.append(dict(f, skipped="too few pairs", n_pairs=len(pairs)))
            continue
        Z = get_Z(pairs, f["kind"], f["L"], f["tether"])

        def go(rkey, hs, lo, hi, gross_only=False):
            if f["mode"] == "band":
                return run_book(pan, pairs, Z, K=f["K"], X=f["X"], maxhold=f["maxhold"],
                                rkey=rkey, hs_bp=hs, lo=lo, hi=hi, gross_only=gross_only)
            return run_book_fixed(pan, pairs, Z, K=f["K"], H=f["H"], rkey=rkey,
                                  hs_bp=hs, lo=lo, hi=hi)

        gD, nD, aD = go("R", HALF_SPREAD_BP, f["L"], d0)
        gH, nH, aH = go("R", HALF_SPREAD_BP, d0, T)
        _, nDs, _ = go("R_LAG1", HALF_SPREAD_P90_BP, f["L"], d0)
        _, nHs, _ = go("R_LAG1", HALF_SPREAD_P90_BP, d0, T)
        _, nHlag, _ = go("R_LAG1", HALF_SPREAD_BP, d0, T)      # lag only
        _, nHp90, _ = go("R", HALF_SPREAD_P90_BP, d0, T)       # p90 spread only
        results.append(dict(
            f, n_pairs=len(pairs),
            design_gross=summarise(gD), design_net=summarise(nD),
            design_stressed=summarise(nDs),
            held_gross=summarise(gH), held_net=summarise(nH),
            held_stressed=summarise(nHs),
            held_lag_only=summarise(nHlag), held_p90_only=summarise(nHp90),
            held_gross_lag=summarise(gH),
            avg_active_design=float(np.mean(aD)) if len(aD) else 0.0,
            avg_active_held=float(np.mean(aH)) if len(aH) else 0.0,
            held_stressed_boot=block_boot(nHs),
        ))
        r = results[-1]
        print(f"{f['name']} {f['tether']:18s} np={len(pairs):5d} "
              f"Dg={r['design_gross']['ann_sharpe']:6.2f}/t{r['design_gross']['t']:5.2f} "
              f"Dn={r['design_net']['ann_sharpe']:6.2f} "
              f"Hn={r['held_net']['ann_sharpe']:6.2f}/t{r['held_net']['t']:5.2f} "
              f"Hs={r['held_stressed']['ann_sharpe']:6.2f}/t{r['held_stressed']['t']:5.2f} "
              f"Hlag={r['held_lag_only']['ann_sharpe']:6.2f} "
              f"Hp90={r['held_p90_only']['ann_sharpe']:6.2f} "
              f"Ds={r['design_stressed']['ann_sharpe']:6.2f} act={r['avg_active_design']:.0f}",
              flush=True)

    scored = [r for r in results if "skipped" not in r and not r["tether"].startswith("TE")]
    N = len(scored)
    bar = math.sqrt(2 * math.log(2 * N)) if N else float("nan")

    payload = dict(
        family="A_cef_pairwise_relative_premium",
        grid=[grid[0], grid[-1]], design_end=DESIGN_END, design_weeks=d0,
        n_pairs_within_category=len(pairs_all), n_placebo=len(plac),
        tether_counts={k: len(v) for k, v in tethers.items()},
        n_scored=N, noise_bar_t=bar,
        pair_stats=pairs_all, results=results,
    )
    (OUT / "INVENT_0822_pairtether_A.json").write_text(json.dumps(payload, indent=1,
                                                                 default=float))
    print(f"\nN scored = {N}, noise bar sqrt(2 ln 2N) = {bar:.3f}")


if __name__ == "__main__":
    main()
