#!/usr/bin/env python3
"""
INVENT 0822 · LOW-TURNOVER · sector-rotation sleeve (11 SPDR sectors, monthly clock).

Declared underpowered BY CONSTRUCTION and reported as such: 11 assets, a monthly hold, and
72 design months. A cross-section of 11 cannot produce a t-statistic that clears a
multiple-testing bar of ~2.8 unless the effect is enormous. It is run because the theme
names sector rotation, and a measured zero on a pre-declared underpowered test is still
worth more than an unmeasured opinion -- but no promotion is possible from this sleeve.

Long-minus-short top-3 / bottom-3, entered at the next open, held 21 days as 21 overlapping
sub-books. Costs: 2 bp one-way half-spread (sector SPDRs are among the tightest US ETFs)
+ 0.5 bp fee, stressed at 5 bp.

Usage: python3 invent0822_slow_sector.py
"""
import json, os, math
import numpy as np

CACHE = "/home/anont/meme/research/data/inv0822_cache"
RES = "/home/anont/meme/research/trading_bot"
DESIGN = ("2016-01-04", "2021-12-31")
HOLDOUT = ("2022-01-03", "2026-08-14")
HS = 2e-4
HS5 = 5e-4
FEE = 0.5e-4
HOLD = 21
K = 3


def rmean(x, w, minfrac=0.8):
    m = np.isfinite(x).astype(float)
    xf = np.where(np.isfinite(x), x, 0.0)
    cs = np.cumsum(xf, axis=0); cn = np.cumsum(m, axis=0)
    s = cs.copy(); n = cn.copy()
    s[w:] = cs[w:] - cs[:-w]; n[w:] = cn[w:] - cn[:-w]
    out = np.where(n >= w * minfrac, s / np.maximum(n, 1), np.nan)
    out[:w - 1] = np.nan
    return out


def rstd(x, w):
    m1 = rmean(x, w); m2 = rmean(x * x, w)
    return np.sqrt(np.maximum(m2 - m1 * m1, 0.0))


def lag(x, k):
    o = np.full_like(x, np.nan); o[k:] = x[:-k]; return o


def sharpe_t(x):
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 200:
        return dict(n=int(n), sharpe=0.0, t=0.0, mean_bps=0.0)
    mu, sd = float(x.mean()), float(x.std(ddof=1))
    if sd <= 0:
        return dict(n=int(n), sharpe=0.0, t=0.0, mean_bps=0.0)
    return dict(n=int(n), sharpe=mu / sd * math.sqrt(252), t=mu / sd * math.sqrt(n), mean_bps=mu * 1e4)


def topk_weights(sig, ok):
    T, N = sig.shape
    w = np.zeros((T, N))
    s = np.where(ok & np.isfinite(sig), sig, np.nan)
    for t in range(T):
        r = s[t]
        v = np.isfinite(r)
        if v.sum() < 2 * K + 2:
            continue
        idx = np.argsort(np.where(v, r, -np.inf))
        idx = idx[v[idx]]
        w[t, idx[-K:]] = 0.5 / K
        w[t, idx[:K]] = -0.5 / K
    return w


def book(w, r):
    T, N = w.shape
    b = np.zeros((T, N))
    for k in range(HOLD):
        b[1 + k:] += w[:T - 1 - k]
    b /= HOLD
    prev = np.zeros_like(b); prev[1:] = b[:-1]
    dw = np.abs(b - prev)
    rr = np.where(np.isfinite(r), r, 0.0)
    g = (b * rr).sum(axis=1)
    turn = dw.sum(axis=1)
    return g, turn * (HS + FEE), turn * (HS5 + FEE), turn


def main():
    z = np.load(os.path.join(CACHE, "sectors.npz"), allow_pickle=False)
    dates = z["dates"].astype(str); syms = list(z["syms"].astype(str))
    O, C, V, DIV = [z[k].astype(np.float64) for k in ("O", "C", "V", "DIV")]
    sec = [i for i, s in enumerate(syms) if s != "SPY"]
    spy = syms.index("SPY")
    Cp = lag(C, 1)
    rc = (C + DIV) / Cp - 1.0
    Onx = np.full_like(O, np.nan); Onx[:-1] = O[1:]
    Dnx = np.full_like(DIV, np.nan); Dnx[:-1] = DIV[1:]
    roo = (Onx + Dnx) / O - 1.0
    ok = np.isfinite(C) & np.isfinite(roo)
    ok[:, spy] = False

    mkt = rc[:, spy]
    m = np.broadcast_to(mkt[:, None], C.shape)
    cov = rmean(rc * m, 250) - rmean(rc, 250) * rmean(m, 250)
    var = rmean(m * m, 250) - rmean(m, 250) ** 2
    beta = cov / np.maximum(var, 1e-12)
    resid = rc - beta * m

    d = np.where(np.isfinite(DIV), DIV, 0.0)
    ttm = rmean(d, 252) * 252.0
    divy = ttm / np.maximum(C, 1e-9)
    sig250 = rstd(rc, 250)
    dv = C * V
    turn_prox = np.log(np.maximum(rmean(dv, 60), 1.0)) - np.log(np.maximum(rmean(dv, 500), 1.0))

    cands = [
        ("SEC_DIVY", "Sector cash-payout-to-price: the slowest, most structural cross-sector "
                     "value proxy available without fundamentals.", divy),
        ("SEC_LOWVOL", "Leverage-constrained allocators overpay for high-vol sectors.", -sig250),
        ("SEC_RESID_LTREV", "Multi-year over-extrapolation of a sector narrative corrects "
                            "slowly; residualised so it is not a market-beta bet.",
         -lag(rmean(resid, 250), 250) * 250.0),
        ("SEC_FLOW_DECAY", "Merton investor recognition at the sector level: sectors whose "
                           "traded interest is shrinking must offer more to be held.", -turn_prox),
    ]

    rows = []
    for name, mech, sig in cands:
        w = topk_weights(sig, ok)
        g, c, c5, t = book(w, roo)
        for tag, win in (("design", DESIGN), ("holdout", HOLDOUT)):
            msk = (dates >= win[0]) & (dates <= win[1])
            sg = sharpe_t(g[msk]); sn = sharpe_t((g - c)[msk]); s5 = sharpe_t((g - c5)[msk])
            gm = float(np.nanmean(g[msk])); tm = float(np.nanmean(t[msk]))
            rows.append(dict(name=name, mechanism=mech, window=tag,
                             gross_sharpe=sg["sharpe"], gross_t=sg["t"],
                             net_sharpe=sn["sharpe"], net_t=sn["t"],
                             net_sharpe_5bp=s5["sharpe"], turnover_per_day=tm,
                             breakeven_cost_bps=(gm / tm * 1e4) if tm > 0 else 0.0, n=sg["n"]))
    json.dump(dict(design=DESIGN, holdout=HOLDOUT, k=K, hold=HOLD, rows=rows),
              open(os.path.join(RES, "INVENT_0822_slowturn_SECTOR.json"), "w"), indent=1, default=float)
    for r in rows:
        print(f"{r['name']:<18s}{r['window']:<9s}gSR{r['gross_sharpe']:6.2f} t{r['gross_t']:6.2f} "
              f"nSR{r['net_sharpe']:6.2f} t{r['net_t']:6.2f} turn{r['turnover_per_day']:7.4f} "
              f"be{r['breakeven_cost_bps']:8.1f}bp")


if __name__ == "__main__":
    main()
