#!/usr/bin/env python3
"""INVENT 0822B -- CROSS-SECTIONAL CRYPTO SPOT momentum/reversal/volume/vol, done with
the rho1 bounce gate applied FIRST and a size-matched placebo null.

Differences from the killed D0821 crypto-spot round (which this must not re-run):
  * Signals AND execution are on the daily VWAP (= quote_volume / base_volume), the true
    volume-weighted traded price, not the close/open.  A close-price signal fades the
    closing bid-ask bounce; a VWAP signal cannot.  D0821 formed on closes, executed at opens.
  * Every formula is run at three OVERLAPPING-TRANCHE holds H in {1,5,20}.  Turnover scales
    as ~1/H, which is the only lever that attacks the 10 bp spot fee directly.  D0821
    rebalanced daily (turnover 1.3) throughout.
  * The book is the EXTREMES (long top-10 / short bottom-10 of the ~50-name universe),
    equal weight, not a rank-z tilt across the whole cross-section.
  * Null is a SIZE-MATCHED circular-shift placebo (weights fixed, returns rotated), not a
    sign-flip bootstrap: it holds turnover, universe, cost and cross-sectional return
    covariance exactly fixed and destroys only the signal/return alignment.

Conventions:
  * signal for day d uses information through the CLOSE of day d-1;
  * book executed at the VWAP of day d, marked to the VWAP of day d+1;
  * cost = fee_bp * sum|dw| the day weights move, subtracted AFTER the sign flip;
  * Sharpe annualised sqrt(365) over every day in the window, flat days included.
"""
from __future__ import annotations
import numpy as np, datetime as dt

CACHE = "/home/anont/meme/research/data/xspot_cache"
ANN = np.sqrt(365.0)
TOP = 50
EXTREME = 10
ADV_FLOOR = 1_000_000.0
FEE_BP = 10.0
HOLDS = (1, 5, 20)

STABLE_BASES = {
    "USDC", "FDUSD", "TUSD", "BUSD", "DAI", "USDP", "PAX", "SUSD", "USDS", "USDSB",
    "EUR", "GBP", "AUD", "USD1", "AEUR", "EURI", "XUSD", "PYUSD", "USTC", "UST",
    "BVND", "IDRT", "NGN", "RUB", "TRY", "BRL", "ZAR", "UAH", "VAI", "BIDR", "USD",
    "BFUSD", "USDE", "RLUSD", "U", "XAUT", "PAXG", "WBTC", "WBETH", "BETH", "BNSOL",
}


# ------------------------------------------------------------------ rolling helpers
def roll_mean(x, w):
    v = np.where(np.isfinite(x), x, 0.0).astype(np.float64)
    m = np.isfinite(x).astype(np.float64)
    cs = np.cumsum(v, axis=1); cm = np.cumsum(m, axis=1)
    out = np.full(x.shape, np.nan, np.float64)
    s = cs[:, w - 1:].copy(); c = cm[:, w - 1:].copy()
    s[:, 1:] -= cs[:, :-w]; c[:, 1:] -= cm[:, :-w]
    with np.errstate(invalid="ignore", divide="ignore"):
        out[:, w - 1:] = np.where(c > w * 0.6, s / np.maximum(c, 1), np.nan)
    return out


def roll_sum_ok(x, w):
    """Trailing sum requiring all w observations finite."""
    v = np.where(np.isfinite(x), x, 0.0).astype(np.float64)
    m = np.isfinite(x).astype(np.float64)
    cs = np.cumsum(v, axis=1); cm = np.cumsum(m, axis=1)
    out = np.full(x.shape, np.nan, np.float64)
    s = cs[:, w - 1:].copy(); c = cm[:, w - 1:].copy()
    s[:, 1:] -= cs[:, :-w]; c[:, 1:] -= cm[:, :-w]
    out[:, w - 1:] = np.where(c >= w, s, np.nan)
    return out


def roll_std(x, w):
    m = roll_mean(x, w); m2 = roll_mean(x * x, w)
    return np.sqrt(np.maximum(m2 - m * m, 0.0))


def shift(x, k):
    out = np.full(x.shape, np.nan, np.float64)
    if k == 0:
        return np.asarray(x, np.float64).copy()
    out[:, k:] = x[:, :-k]
    return out


# ------------------------------------------------------------------ panel
def load(path=f"{CACHE}/spot_daily.npz"):
    z = np.load(path, allow_pickle=False)
    P = {k: z[k] for k in z.files}
    P["dates"] = np.array([dt.datetime.fromtimestamp(x / 1000, dt.timezone.utc).date()
                           for x in P["days"]])
    return P


def features(P):
    """All coin-space feature panels.  F[:,t] uses data through the CLOSE of day t."""
    c = P["c"].astype(np.float64); v = P["v"].astype(np.float64)
    qv = P["qv"].astype(np.float64); n = P["n"].astype(np.float64)
    tbq = P["tbq"].astype(np.float64)
    good = np.isfinite(c) & (c > 0) & np.isfinite(v) & (v > 0) & np.isfinite(qv) & (qv > 0)
    vw = np.where(good, qv / np.maximum(v, 1e-18), np.nan)
    # sanity: VWAP must sit inside the day's range (allow 1% slack for rounding)
    lo = P["l"].astype(np.float64); hi = P["h"].astype(np.float64)
    inside = (vw >= lo * 0.99) & (vw <= hi * 1.01)
    vw = np.where(inside, vw, np.nan)
    lvw = np.log(np.where(np.isfinite(vw) & (vw > 0), vw, np.nan))
    lc = np.log(np.where(good, c, np.nan))
    F = dict(vw=vw, lvw=lvw, lc=lc, qv=np.where(good, qv, np.nan),
             n=np.where(good & (n > 0), n, np.nan), tbq=np.where(good, tbq, np.nan),
             c=np.where(good, c, np.nan))
    F["r_v"] = lvw - shift(lvw, 1)          # vwap-to-vwap log return, day t
    F["r_c"] = lc - shift(lc, 1)            # close-to-close log return, day t
    for k in ("r_v", "r_c"):
        F[k] = np.where(np.abs(F[k]) < 1.5, F[k], np.nan)
    return F


def universe(P, F, top=TOP, adv_floor=ADV_FLOOR, lookback=30):
    """Boolean (S,T) mask of names tradable in a book ENTERED at the VWAP of day t.

    Selection uses trailing ADV through day t-1 only.  Requires a usable VWAP on day t
    (entry) and day t+1 (mark)."""
    syms = P["syms"]
    base = np.array([s[:-4] for s in syms])
    tradable = np.array([b not in STABLE_BASES for b in base])
    adv = roll_mean(F["qv"], lookback)
    cnt = roll_sum_ok(np.isfinite(F["qv"]).astype(np.float64), lookback)
    ok = (cnt >= lookback) & (adv >= adv_floor) & tradable[:, None]
    advs = shift(np.where(ok, adv, np.nan), 1)
    S, T = advs.shape
    U = np.zeros((S, T), bool)
    for t in range(T):
        col = advs[:, t]
        m = np.isfinite(col)
        if m.sum() < 15:
            continue
        idx = np.where(m)[0]
        k = min(top, idx.size)
        U[idx[np.argsort(-col[idx])[:k]], t] = True
    live = np.isfinite(F["vw"]) & (F["vw"] > 0)
    U &= live
    U[:, :-1] &= live[:, 1:]
    U[:, -1] = False
    return U


def fwd_ret(F):
    """VWAP(t) -> VWAP(t+1) simple return earned by a book entered on day t."""
    vw = F["vw"]
    r = np.full(vw.shape, np.nan)
    with np.errstate(invalid="ignore", divide="ignore"):
        r[:, :-1] = vw[:, 1:] / vw[:, :-1] - 1.0
    r[~np.isfinite(r)] = np.nan
    r[np.abs(r) > 2.0] = np.nan
    return r


def fwd_ret_px(px):
    r = np.full(px.shape, np.nan)
    with np.errstate(invalid="ignore", divide="ignore"):
        r[:, :-1] = px[:, 1:] / px[:, :-1] - 1.0
    r[~np.isfinite(r)] = np.nan
    r[np.abs(r) > 2.0] = np.nan
    return r


# ------------------------------------------------------------------ book construction
def extremes_book(sig, U, k=EXTREME):
    """Long top-k / short bottom-k of the daily cross-section, equal weight, unit gross."""
    s = np.where(U & np.isfinite(sig), sig, np.nan)
    S, T = s.shape
    w = np.zeros((S, T), np.float64)
    for t in range(T):
        col = s[:, t]
        m = np.isfinite(col)
        nn = int(m.sum())
        if nn < 2 * k + 5:
            continue
        idx = np.where(m)[0]
        order = idx[np.argsort(col[idx])]
        w[order[-k:], t] = 0.5 / k
        w[order[:k], t] = -0.5 / k
    return w


def tranche(w, H):
    """Overlapping tranches: hold each day's target book for H days, 1/H of capital each."""
    if H <= 1:
        return w
    acc = np.zeros_like(w)
    for j in range(H):
        acc += shift(w, j)
    return np.nan_to_num(acc / H)


def evaluate(w, r, fee_bp=FEE_BP):
    ww = np.nan_to_num(w)
    rr = np.where(np.isfinite(r), r, 0.0)
    gross = (ww * rr).sum(0)
    dw = np.abs(np.diff(ww, axis=1, prepend=0.0)).sum(0)
    return gross, gross - dw * fee_bp * 1e-4, dw


def sharpe(x):
    x = np.asarray(x, float)
    if x.size < 30 or x.std() == 0:
        return 0.0
    return float(x.mean() / x.std() * ANN)


def tstat(x):
    x = np.asarray(x, float)
    if x.size < 30 or x.std() == 0:
        return 0.0
    return float(x.mean() / (x.std() / np.sqrt(x.size)))


def breakeven_bp(gross, dw):
    g, d = float(np.nansum(gross)), float(np.nansum(dw))
    return float(1e4 * g / d) if d > 0 else 0.0


def rho1(x):
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    if x.size < 40:
        return np.nan
    x = x - x.mean()
    d = float((x * x).sum())
    return float((x[1:] * x[:-1]).sum() / d) if d > 0 else np.nan
