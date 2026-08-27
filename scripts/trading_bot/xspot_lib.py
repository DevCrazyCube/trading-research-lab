#!/usr/bin/env python3
"""Shared machinery for the D0821 crypto-spot cross-sectional invention sweep.

Conventions (inherited from scripts/trading_bot/perpmicro_sweep.py so numbers are comparable):
  * All data are Binance SPOT UTC daily klines. Bar d spans [d 00:00, d+1 00:00).
  * A signal for day d uses information through the CLOSE of day d-1 only.
  * The book is entered at the OPEN of day d and marked to the OPEN of day d+1.
  * Cost = fee_bp * sum|dw| charged on the day the weights change.
  * Sharpe is annualised sqrt(365) over EVERY day in the window, including flat days.
  * Signs are oriented on the DESIGN window with zero-cost P&L and then frozen.
"""
from __future__ import annotations
import numpy as np

CACHE = "/home/anont/meme/research/data/xspot_cache"
DAY = 86_400_000
ANN = np.sqrt(365.0)

# quote-side / wrapped / stable instruments that must never enter the tradable cross-section
STABLE_BASES = {
    "USDC", "FDUSD", "TUSD", "BUSD", "DAI", "USDP", "PAX", "SUSD", "USDS", "USDSB",
    "EUR", "GBP", "AUD", "USD1", "AEUR", "EURI", "XUSD", "PYUSD", "USTC", "UST",
    "BVND", "IDRT", "NGN", "RUB", "TRY", "BRL", "ZAR", "UAH", "VAI", "BIDR", "USD",
}


def load_panel(path=f"{CACHE}/spot_daily.npz"):
    z = np.load(path, allow_pickle=False)
    return {k: z[k] for k in z.files}


# ---------------------------------------------------------------- rolling helpers
def roll_mean(x, w):
    """Trailing mean over w columns, NaN-aware, ending AT column t (inclusive)."""
    v = np.where(np.isfinite(x), x, 0.0)
    m = np.isfinite(x).astype(np.float32)
    cs = np.cumsum(v, axis=1)
    cm = np.cumsum(m, axis=1)
    out = np.full_like(x, np.nan, dtype=np.float32)
    s = cs[:, w - 1:].copy()
    c = cm[:, w - 1:].copy()
    s[:, 1:] -= cs[:, :-w]
    c[:, 1:] -= cm[:, :-w]
    with np.errstate(invalid="ignore", divide="ignore"):
        out[:, w - 1:] = np.where(c > 0, s / np.maximum(c, 1), np.nan)
    return out


def roll_sum(x, w):
    v = np.where(np.isfinite(x), x, 0.0)
    cs = np.cumsum(v, axis=1)
    out = np.full_like(x, np.nan, dtype=np.float32)
    s = cs[:, w - 1:].copy()
    s[:, 1:] -= cs[:, :-w]
    out[:, w - 1:] = s
    return out


def roll_std(x, w):
    m = roll_mean(x, w)
    m2 = roll_mean(x * x, w)
    return np.sqrt(np.maximum(m2 - m * m, 0.0)).astype(np.float32)


def shift(x, k):
    """Shift columns right by k (x[:, t] becomes value from t-k)."""
    out = np.full_like(x, np.nan)
    if k == 0:
        return x.copy()
    out[:, k:] = x[:, :-k]
    return out


def zscore_ts(x, w):
    m = roll_mean(x, w)
    s = roll_std(x, w)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(s > 0, (x - m) / s, np.nan).astype(np.float32)


# ---------------------------------------------------------------- universe
def build_universe(P, top=60, min_days=40, lookback=30):
    """Top-`top` tradable symbols each day by trailing median-ish quote volume.

    Returns boolean (S,T) mask valid for a book ENTERED on day t (uses data <= t-1).
    """
    syms, qv, c = P["syms"], P["qv"], P["c"]
    base = np.array([s[:-4] for s in syms])
    tradable = np.array([b not in STABLE_BASES for b in base])
    alive = np.isfinite(c) & (c > 0) & (qv > 0)
    adv = roll_mean(np.where(alive, qv, np.nan), lookback)
    cnt = roll_sum(alive.astype(np.float32), lookback)
    ok = (cnt >= min_days * lookback / 60.0) & np.isfinite(adv) & tradable[:, None]
    advs = shift(np.where(ok, adv, np.nan), 1)      # info through t-1
    S, T = advs.shape
    univ = np.zeros((S, T), bool)
    for t in range(T):
        col = advs[:, t]
        m = np.isfinite(col)
        if m.sum() < 10:
            continue
        idx = np.where(m)[0]
        k = min(top, idx.size)
        sel = idx[np.argsort(-col[idx])[:k]]
        univ[sel, t] = True
    # must actually be tradable on day t and t+1 (open prices exist)
    o = P["o"]
    liveo = np.isfinite(o) & (o > 0)
    univ &= liveo
    univ[:, :-1] &= liveo[:, 1:]
    univ[:, -1] = False
    return univ


def fwd_open_ret(P):
    """Return earned by holding from open(t) to open(t+1)."""
    o = P["o"]
    r = np.full_like(o, np.nan)
    with np.errstate(invalid="ignore", divide="ignore"):
        r[:, :-1] = o[:, 1:] / o[:, :-1] - 1.0
    r[~np.isfinite(r)] = np.nan
    r[np.abs(r) > 3.0] = np.nan
    return r


# ---------------------------------------------------------------- weights
def xs_weights(sig, univ, mode="demean"):
    """Cross-sectional dollar-neutral unit-gross weights from a raw score."""
    s = np.where(univ & np.isfinite(sig), sig, np.nan).astype(np.float64)
    w = np.zeros(s.shape, np.float64)
    S, T = s.shape
    for t in range(T):
        col = s[:, t]
        m = np.isfinite(col)
        k = int(m.sum())
        if k < 10:
            continue
        v = col[m]
        r = np.argsort(np.argsort(v)).astype(np.float64)
        r = (r - r.mean()) / max(r.std(), 1e-9)      # cross-sectional rank z
        r -= r.mean()
        g = np.abs(r).sum()
        if g <= 0:
            continue
        w[m, t] = r / g
    return w


def xs_weights_from_mask(longm, shortm):
    """Equal-weight long/short books from two boolean masks."""
    w = np.zeros(longm.shape, np.float64)
    nl = longm.sum(0).astype(np.float64)
    ns = shortm.sum(0).astype(np.float64)
    ok = (nl > 0) & (ns > 0)
    w += np.where(longm & ok[None, :], 0.5 / np.maximum(nl, 1)[None, :], 0.0)
    w -= np.where(shortm & ok[None, :], 0.5 / np.maximum(ns, 1)[None, :], 0.0)
    return w


def ts_book(sig_ts, leg_w, clip=1.0):
    """Time-series scaled book: leg_w is a (S,T) unit-gross dollar-neutral leg."""
    z = np.clip(np.nan_to_num(sig_ts, nan=0.0), -clip, clip)
    return leg_w * z[None, :]


def tranche(w, H):
    """Average the last H daily target books (overlapping tranches) to cut turnover."""
    if H <= 1:
        return w
    acc = np.zeros_like(w)
    for k in range(H):
        acc += shift(w.astype(np.float32), k).astype(np.float64)
    return np.nan_to_num(acc / H)


# ---------------------------------------------------------------- evaluation
def evaluate(w, r, fee_bp, mask=None):
    """Daily net P&L of book w against forward open-to-open returns r."""
    ww = np.nan_to_num(w)
    rr = np.nan_to_num(np.where(np.isfinite(r), r, 0.0))
    gross = (ww * rr).sum(0)
    dw = np.abs(np.diff(ww, axis=1, prepend=0.0)).sum(0)
    cost = dw * fee_bp * 1e-4
    net = gross - cost
    exp_net = ww.sum(0)          # net dollar exposure (for beta attribution)
    return gross, net, dw, exp_net


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
    g, d = np.nan_to_num(gross).sum(), np.nan_to_num(dw).sum()
    return float(1e4 * g / d) if d > 0 else 0.0
