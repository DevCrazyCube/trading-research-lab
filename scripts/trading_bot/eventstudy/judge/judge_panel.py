#!/usr/bin/env python3
"""JUDGE: independent panel loader. No code reused from the six study scripts."""
import csv, os, numpy as np

ROOT = "/home/anont/meme"
PERP = os.path.join(ROOT, "research/data/t23_cache/panel/perp_daily.csv")
FUND = os.path.join(ROOT, "research/data/t23_cache/panel/funding.csv")
DAY_MS = 86_400_000
CACHE = "/home/anont/meme/scripts/trading_bot/eventstudy/judge/_cache.npz"


def load():
    if os.path.exists(CACHE):
        z = np.load(CACHE, allow_pickle=True)
        return (list(z["syms"]), z["days"], z["close"], z["qv"], z["fund"])
    syms, days = {}, {}
    rows = []
    with open(PERP) as fh:
        r = csv.reader(fh); next(r)
        for s, d, c, q, t in r:
            d = int(d) // DAY_MS
            si = syms.setdefault(s, len(syms)); di = days.setdefault(d, len(days))
            rows.append((si, di, float(c), float(q)))
    sl = sorted(syms, key=lambda k: syms[k])
    dl = sorted(days)
    dmap = {d: i for i, d in enumerate(dl)}
    remap = np.array([dmap[d] for d in sorted(days, key=lambda k: days[k])])
    S, D = len(sl), len(dl)
    close = np.full((S, D), np.nan); qv = np.full((S, D), np.nan)
    for si, di, c, q in rows:
        j = remap[di]; close[si, j] = c; qv[si, j] = q
    # daily funding = SUM of the day's prints (matches an annualisation of ~365x)
    fund = np.full((S, D), np.nan)
    with open(FUND) as fh:
        r = csv.reader(fh); next(r)
        for s, t, ih, fr in r:
            si = syms.get(s)
            if si is None: continue
            j = dmap.get(int(t) // DAY_MS)
            if j is None: continue
            v = float(fr)
            fund[si, j] = v if np.isnan(fund[si, j]) else fund[si, j] + v
    days_arr = np.array(dl, dtype=np.int64)
    np.savez_compressed(CACHE, syms=np.array(sl, dtype=object), days=days_arr,
                        close=close, qv=qv, fund=fund)
    return sl, days_arr, close, qv, fund


def market_control(close):
    """Daily cross-sectional MEDIAN log return, built ONCE, vectorized."""
    lr = np.full_like(close, np.nan)
    lr[:, 1:] = np.log(close[:, 1:] / close[:, :-1])
    with np.errstate(invalid="ignore"):
        med = np.nanmedian(np.where(np.isfinite(lr), lr, np.nan), axis=0)
    cnt = np.isfinite(lr).sum(axis=0)
    med[cnt < 30] = np.nan
    return lr, med, cnt


def boot_cluster(vals, clusters, n=5000, seed=20260903):
    rng = np.random.default_rng(seed)
    uc, inv = np.unique(clusters, return_inverse=True)
    K = len(uc)
    order = np.argsort(inv, kind="stable")
    sv = vals[order]; si = inv[order]
    bounds = np.searchsorted(si, np.arange(K + 1))
    csum = np.concatenate([[0.0], np.cumsum(sv)])
    sums = csum[bounds[1:]] - csum[bounds[:-1]]
    sizes = np.diff(bounds).astype(float)
    idx = rng.integers(0, K, size=(n, K))
    bs = sums[idx].sum(axis=1) / sizes[idx].sum(axis=1)
    return bs
