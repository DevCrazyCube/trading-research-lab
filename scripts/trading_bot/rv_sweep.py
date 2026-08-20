#!/usr/bin/env python3
"""WIDE formula sweep: intraday equity/ETF relative value and mean reversion.

WHAT MAKES THIS HONEST RATHER THAN A DATA-MINING MACHINE
========================================================
1. Every config is scored on a DESIGN window only (2021-01-04 .. 2024-12-31). The held-out
   window (2025-01-01 .. 2026-08-15) is not read until the design sweep has been written to
   disk and a shortlist frozen -- `--stage design` physically cannot see it.
2. The noise bar is not sqrt(2 ln N) hand-waving alone. It is a stationary BLOCK BOOTSTRAP of
   the DEMEANED daily PnL of every config, resampling the SAME day indices across all configs
   so the cross-config correlation is preserved, then taking the max Sharpe per resample. That
   is the distribution of "best of this sweep" when nothing has an edge.
3. Costs are charged on turnover, per side, at three rungs. The headline rung is 1.0 bp/side.
   Provenance: ADVERSE_PROXY_FOR_AN_UNMEASURED_LEG -- the repo's own measured close-auction
   half-spread for liquid names is 1.13 bp (t3 design sample, 19,835 symbol-days) and mega-cap
   ETF intraday spreads are tighter than that, so 1.0 bp/side is a conservative stand-in for
   an intraday ETF leg nobody in this repo has measured directly.

EXECUTION MODEL
===============
Signal s_t is computed from CLOSES through bar t-1. The position is entered at the VWAP of bar
t and earns vwap[t+1]/vwap[t] - 1. So there is a full 5-minute bar between the last observed
price and the fill, and the fill is a bar VWAP rather than a touch print. Intraday configs are
forced flat at the last bar of every session.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

import numpy as np

CACHE = pathlib.Path(__file__).resolve().parents[2] / "research" / "data" / "rv_cache"
OUT = pathlib.Path(__file__).resolve().parents[2] / "research" / "trading_bot"

DESIGN = ("2021-01-04", "2024-12-31")
HELDOUT = ("2025-01-02", "2026-08-15")
COST_RUNGS_BP = (0.5, 1.0, 2.0, 2.5)
HEADLINE_BP = 1.0
# Regulatory pass-throughs, charged on EVERY unit of turnover regardless of the spread rung.
# SEC Section 31 is $27.80 per $1M of SALE proceeds = 0.278 bp, sell side only; FINRA TAF is
# $0.000166/share on sales, sub-0.06 bp on a $30+ ETF. Turnover here counts buys and sells
# together and sales are ~half of it, so the per-turnover rate is ~half the sell-side rate.
REG_BP_PER_TURNOVER = 0.15
# Borrow is deliberately ZERO and that is a claim with a reason, not an omission: every config
# in this sweep is forced flat at the closing bar, and US stock-borrow fees accrue on OVERNIGHT
# positions. An intraday-only short still needs a locate, which for the ETB mega-cap ETFs here
# is free at the broker; B22G's measured 0.33%/yr ETB rate would apply only to a held short.
BORROW_ANNUAL = 0.0
BARS_PER_DAY = 78

# ---------------------------------------------------------------- structure definitions

SIBLING_PAIRS = [
    ("SPY", "IVV"), ("SPY", "VOO"), ("IVV", "VOO"), ("SPY", "SPLG"),
    ("VTI", "ITOT"), ("VTI", "SCHB"), ("ITOT", "SCHB"), ("SPY", "VTI"),
    ("QQQ", "QQQM"), ("IWM", "VTWO"), ("IJH", "MDY"),
    ("GLD", "IAU"), ("GLD", "GLDM"), ("IAU", "GLDM"), ("SLV", "SIVR"),
    ("EFA", "IEFA"), ("EFA", "VEA"), ("IEFA", "VEA"),
    ("EEM", "IEMG"), ("EEM", "VWO"), ("IEMG", "VWO"),
    ("AGG", "BND"), ("LQD", "VCIT"), ("HYG", "JNK"), ("TLT", "VGLT"),
    ("XLK", "VGT"), ("XLF", "VFH"), ("XLE", "VDE"), ("XLV", "VHT"), ("XLI", "VIS"),
    ("XLY", "VCR"), ("XLP", "VDC"), ("XLU", "VPU"), ("XLB", "VAW"), ("XLRE", "VNQ"),
    ("SMH", "SOXX"), ("IWF", "VUG"), ("IWD", "VTV"), ("IWF", "SPYG"), ("IWD", "SPYV"),
]

# (levered, base, stated multiple)
LEVERED_PAIRS = [
    ("SSO", "SPY", 2.0), ("UPRO", "SPY", 3.0), ("SDS", "SPY", -2.0), ("SPXU", "SPY", -3.0),
    ("SH", "SPY", -1.0), ("QLD", "QQQ", 2.0), ("TQQQ", "QQQ", 3.0), ("SQQQ", "QQQ", -3.0),
    ("PSQ", "QQQ", -1.0), ("TNA", "IWM", 3.0), ("TZA", "IWM", -3.0),
    ("TMF", "TLT", 3.0), ("TMV", "TLT", -3.0),
]

SECTOR_BASKETS = {
    "XLK": ["AAPL", "MSFT", "NVDA", "AVGO", "ORCL", "CRM", "AMD", "INTC", "CSCO", "ADBE"],
    "XLV": ["UNH", "JNJ", "LLY", "ABBV", "MRK"],
    "XLP": ["PG", "PEP", "KO", "WMT", "COST"],
    "XLC": ["META", "GOOGL", "GOOG", "NFLX"],
    "XLE": ["XOM", "CVX"],
    "XLY": ["AMZN", "TSLA", "HD"],
    "XLF": ["JPM", "BAC", "V", "MA"],
    "SMH": ["NVDA", "AVGO", "AMD", "INTC"],
}

SECTORS = ["XLK", "XLF", "XLE", "XLV", "XLI", "XLY", "XLP", "XLU", "XLB", "XLRE", "XLC"]

MEGACAPS = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AVGO", "JPM", "XOM",
            "UNH", "JNJ", "V", "PG", "HD", "MA", "COST", "WMT", "BAC", "CVX", "LLY",
            "ABBV", "MRK", "PEP", "KO", "ORCL", "CRM", "AMD", "INTC", "NFLX", "ADBE", "CSCO"]

LIQUID_ETFS = ["SPY", "QQQ", "IWM", "DIA", "XLK", "XLF", "XLE", "XLV", "XLI", "XLY", "XLP",
               "XLU", "XLB", "XLRE", "XLC", "SMH", "SOXX", "KRE", "IBB", "XBI", "ITB", "XHB",
               "GDX", "EFA", "EEM", "TLT", "HYG", "LQD", "GLD", "SLV", "EWJ", "FXI", "EWZ",
               "IWF", "IWD", "MTUM", "USMV", "QUAL", "VLUE", "IJH", "IJR"]

# leader -> laggard, chosen on liquidity ordering, not on measured lead-lag
LEADLAG_PAIRS = [("SPY", "SPLG"), ("SPY", "IVV"), ("SPY", "VOO"), ("QQQ", "QQQM"),
                 ("GLD", "GLDM"), ("EFA", "VEA"), ("EEM", "VWO"), ("XLK", "VGT"),
                 ("SMH", "SOXX"), ("IWM", "VTWO"), ("TLT", "VGLT"), ("HYG", "JNK")]


# ---------------------------------------------------------------- rolling helpers

def _nan_roll(x: np.ndarray, n: int):
    """Rolling mean and std over axis 0, NaN-aware, causal, window n ending at t (inclusive)."""
    m = np.isfinite(x)
    xz = np.where(m, x, 0.0).astype(np.float64)
    cs = np.concatenate([np.zeros((1,) + x.shape[1:]), np.cumsum(xz, axis=0)])
    cs2 = np.concatenate([np.zeros((1,) + x.shape[1:]), np.cumsum(xz * xz, axis=0)])
    cn = np.concatenate([np.zeros((1,) + x.shape[1:]), np.cumsum(m, axis=0)])
    T = x.shape[0]
    i = np.arange(T)
    lo = np.maximum(i - n + 1, 0)
    s = cs[i + 1] - cs[lo]
    s2 = cs2[i + 1] - cs2[lo]
    c = cn[i + 1] - cn[lo]
    with np.errstate(invalid="ignore", divide="ignore"):
        mu = s / c
        var = s2 / c - mu * mu
    var = np.where(var > 0, var, np.nan)
    bad = c < max(5, n // 3)
    mu = np.where(bad, np.nan, mu)
    var = np.where(bad, np.nan, var)
    return mu, np.sqrt(var)


def _ewma(x: np.ndarray, halflife: float):
    """Causal EWMA over axis 0. NaNs are carried (the level holds through a hole).

    No scipy in this environment, so the recursion is unrolled with an exponential-weight
    trick instead of a Python loop over 110k bars: y_t = sum_k a(1-a)^k x_{t-k} is a
    cumulative sum once x is pre-divided by (1-a)^t. The exponent is bounded by rescaling
    in blocks, otherwise (1-a)^-t overflows within a few thousand bars.
    """
    a = 1.0 - 0.5 ** (1.0 / halflife)
    T = x.shape[0]
    xf = np.array(x, dtype=np.float64, copy=True)
    # forward-fill holes so the recursion does not restart at a missing bar
    idx = np.where(np.isfinite(xf), np.arange(T)[:, None], 0)
    idx = np.maximum.accumulate(idx, axis=0)
    xf = np.take_along_axis(np.where(np.isfinite(xf), xf, 0.0), idx, axis=0)
    out = np.empty_like(xf)
    prev = xf[0].copy()
    block = 512
    for start in range(0, T, block):
        stop = min(start + block, T)
        k = np.arange(stop - start)
        w = (1.0 - a) ** k
        seg = xf[start:stop]
        cs = np.cumsum(seg / w[:, None], axis=0)
        out[start:stop] = prev[None, :] * w[:, None] * (1 - a) + a * w[:, None] * cs
        prev = out[stop - 1]
    return out


def _shift(x: np.ndarray, k: int):
    """Shift DOWN by k (x_shift[t] = x[t-k]); fills with NaN."""
    out = np.full_like(x, np.nan, dtype=np.float64)
    if k <= 0:
        return x.astype(np.float64)
    out[k:] = x[:-k]
    return out


def _ffill_daily(x: np.ndarray, day: np.ndarray, fill_at_open=0.0):
    """Forward-fill NaNs along axis 0, RESETTING at every session open.

    Carrying a position across the overnight gap would make an intraday rule an overnight one,
    so the first bar of each session is forced to `fill_at_open` wherever it is missing.
    """
    x = np.array(x, dtype=np.float64, copy=True)
    first = np.zeros(x.shape[0], dtype=bool)
    first[0] = True
    first[1:] = day[1:] != day[:-1]
    x[first] = np.where(np.isfinite(x[first]), x[first], fill_at_open)
    idx = np.where(np.isfinite(x), np.arange(x.shape[0])[:, None], 0)
    idx = np.maximum.accumulate(idx, axis=0)
    return np.take_along_axis(np.where(np.isfinite(x), x, 0.0), idx, axis=0)


def _hysteresis(z: np.ndarray, day: np.ndarray, entry: float, exit_: float):
    """Classic pairs state machine, vectorised.

    +1 (long the spread) once z <= -entry, -1 once z >= +entry, flat once |z| < exit, and
    HOLD otherwise. Because the three trigger regions are disjoint when entry > exit, the
    machine is exactly a forward-fill of a sparse event series -- no Python scan needed.
    """
    ev = np.full(z.shape, np.nan)
    ev = np.where(z <= -entry, 1.0, ev)
    ev = np.where(z >= entry, -1.0, ev)
    ev = np.where(np.abs(z) < exit_, 0.0, ev)
    return _ffill_daily(ev, day, fill_at_open=0.0)


def _hold_every(w: np.ndarray, day: np.ndarray, slot: np.ndarray, every: int):
    """Refresh the target only every `every` bars; hold it in between, flat at each open."""
    upd = (slot % every) == 0
    x = np.where(upd[:, None], w, np.nan)
    return _ffill_daily(x, day, fill_at_open=0.0)


def _cross_demean(w: np.ndarray):
    """Dollar-neutralise each row and scale gross exposure to 1."""
    m = np.isfinite(w)
    w = np.where(m, w, 0.0)
    n = m.sum(axis=1, keepdims=True)
    with np.errstate(invalid="ignore"):
        w = w - np.where(n > 0, w.sum(axis=1, keepdims=True) / np.maximum(n, 1), 0.0) * m
    g = np.abs(w).sum(axis=1, keepdims=True)
    return np.where(g > 0, w / np.maximum(g, 1e-12), 0.0)


class Panel:
    def __init__(self, path=CACHE / "panel_rv.npz"):
        z = np.load(path, allow_pickle=False)
        self.ts = z["ts"]
        self.day = z["day"].astype(np.int64)
        self.slot = z["slot"].astype(np.int64)
        self.daykey = z["daykey"].astype(str)
        self.syms = list(z["syms"].astype(str))
        self.close = z["close"].astype(np.float64)
        self.open = z["open"].astype(np.float64)
        self.vwap = z["vwap"].astype(np.float64)
        self.dvol = z["dvol"].astype(np.float64)
        self.idx = {s: i for i, s in enumerate(self.syms)}
        self.T, self.S = self.close.shape
        self.logc = np.log(self.close)
        # execution price: bar VWAP, forward-filled through a hole so a gap does not fabricate
        # a return; a bar with no VWAP is simply untradable and its weight is zeroed.
        self.tradable = np.isfinite(self.vwap) & np.isfinite(self.close)
        px = self.vwap.copy()
        self.fwd_ret = np.full_like(px, np.nan)
        self.fwd_ret[:-1] = px[1:] / px[:-1] - 1.0
        self.fwd_ret[~(self.tradable & _shift_bool(self.tradable, -1))] = np.nan
        # day boundaries: a "forward return" that spans two sessions is an overnight return
        same_day = np.zeros(self.T, dtype=bool)
        same_day[:-1] = self.day[1:] == self.day[:-1]
        self.same_day = same_day

    def same_day_back(self):
        m = np.zeros(self.T, dtype=bool)
        m[1:] = self.day[1:] == self.day[:-1]
        return m[:, None] | np.zeros((1, self.S), dtype=bool)

    def col(self, sym):
        return self.idx.get(sym)

    def cols(self, syms):
        return [self.idx[s] for s in syms if s in self.idx]


def _shift_bool(m, k):
    out = np.zeros_like(m)
    if k < 0:
        out[:k] = m[-k:]
    elif k > 0:
        out[k:] = m[:-k]
    else:
        out = m
    return out


# ---------------------------------------------------------------- evaluation

def evaluate(P: Panel, W: np.ndarray, mask: np.ndarray, intraday_flat=True):
    """W[t,s] is the weight HELD during bar t (entered at vwap[t]), from info through t-1."""
    W = np.where(np.isfinite(W), W, 0.0)
    W[~P.tradable] = 0.0
    if intraday_flat:
        last_bar = np.zeros(P.T, dtype=bool)
        last_bar[:-1] = P.day[1:] != P.day[:-1]
        last_bar[-1] = True
        W[last_bar] = 0.0
    r = np.where(np.isfinite(P.fwd_ret), P.fwd_ret, 0.0)
    gross_pnl = (W * r).sum(axis=1)
    turn = np.abs(np.diff(np.vstack([np.zeros((1, P.S)), W]), axis=0)).sum(axis=1)
    return gross_pnl, turn


def daily_series(P: Panel, gross_pnl, turn, mask, cost_bp, reg_bp=REG_BP_PER_TURNOVER):
    pnl = gross_pnl - turn * (cost_bp + reg_bp) * 1e-4
    pnl = np.where(mask, pnl, 0.0)
    d = P.day
    nd = d.max() + 1
    out = np.bincount(d, weights=pnl, minlength=nd)
    keep = np.bincount(d, weights=mask.astype(float), minlength=nd) > 0
    return out[keep], keep


def sharpe(x):
    if x.size < 30:
        return float("nan")
    s = x.std(ddof=1)
    if not np.isfinite(s) or s <= 0:
        return float("nan")
    return float(x.mean() / s * np.sqrt(252))


# ---------------------------------------------------------------- formula library
# Each builder returns W[t,s] = weight held during bar t, using info through close of bar t-1.

def _pair_weights(P, pairs, sig_fn):
    """sig_fn(la, lb) -> signal[T] per pair, positive = long a / short b."""
    W = np.zeros((P.T, P.S))
    used = 0
    for a, b in pairs:
        ia, ib = P.col(a), P.col(b)
        if ia is None or ib is None:
            continue
        s = sig_fn(P.logc[:, ia], P.logc[:, ib])
        s = np.where(np.isfinite(s), s, 0.0)
        W[:, ia] += s
        W[:, ib] -= s
        used += 1
    if used == 0:
        return None
    g = np.abs(W).sum(axis=1, keepdims=True)
    return np.where(g > 0, W / np.maximum(g, 1e-12), 0.0)


def build(P: Panel, cfg: dict):
    k = cfg["kind"]
    T, S = P.T, P.S

    if k == "pair_z":
        n, thr, clip = cfg["win"], cfg.get("thr", 0.0), cfg.get("clip", 3.0)

        def f(la, lb):
            sp = (la - lb)[:, None]
            mu, sd = _nan_roll(sp, n)
            z = ((sp - mu) / sd)[:, 0]
            z = _shift(z, 1)
            z = np.clip(z, -clip, clip)
            return np.where(np.abs(z) >= thr, -z, 0.0)
        return _pair_weights(P, SIBLING_PAIRS, f)

    if k == "pair_z_band":
        # the textbook pairs implementation: discrete state with a no-trade band. This is the
        # variant that can survive turnover, so it is a different OBJECT from pair_z, not a
        # tweaked constant of it.
        n, entry, exit_ = cfg["win"], cfg["entry"], cfg["exit"]

        def f(la, lb):
            sp = (la - lb)[:, None]
            mu, sd = _nan_roll(sp, n)
            z = _shift((sp - mu) / sd, 1)
            st = _hysteresis(z, P.day, entry, exit_)[:, 0]
            return st
        return _pair_weights(P, SIBLING_PAIRS, f)

    if k == "levered_resid_band":
        n, entry, exit_ = cfg["win"], cfg["entry"], cfg["exit"]
        W = np.zeros((T, S))
        for lev, base, mult in LEVERED_PAIRS:
            il, ib = P.col(lev), P.col(base)
            if il is None or ib is None:
                continue
            sp = (P.logc[:, il] - mult * P.logc[:, ib])[:, None]
            mu, sd = _nan_roll(sp, n)
            z = _shift((sp - mu) / sd, 1)
            st = _hysteresis(z, P.day, entry, exit_)[:, 0]
            W[:, il] += st
            W[:, ib] -= st * mult
        g = np.abs(W).sum(axis=1, keepdims=True)
        return np.where(g > 0, W / np.maximum(g, 1e-12), 0.0)

    if k == "etf_basket_band":
        n, entry, exit_ = cfg["win"], cfg["entry"], cfg["exit"]
        W = np.zeros((T, S))
        for etf, members in SECTOR_BASKETS.items():
            ie = P.col(etf)
            cols = P.cols(members)
            if ie is None or len(cols) < 2:
                continue
            lb = np.nanmean(P.logc[:, cols], axis=1)
            sp = (P.logc[:, ie] - lb)[:, None]
            mu, sd = _nan_roll(sp, n)
            z = _shift((sp - mu) / sd, 1)
            st = _hysteresis(z, P.day, entry, exit_)[:, 0]
            W[:, ie] += st
            for c in cols:
                W[:, c] -= st / len(cols)
        g = np.abs(W).sum(axis=1, keepdims=True)
        return np.where(g > 0, W / np.maximum(g, 1e-12), 0.0)

    if k == "pair_z_intraday":
        thr = cfg.get("thr", 0.0)
        dayid = P.day

        def f(la, lb):
            sp = la - lb
            # running same-day mean/std, causal
            out = np.full(T, np.nan)
            s = 0.0; s2 = 0.0; c = 0; prev = -1
            for t in range(T):
                if dayid[t] != prev:
                    s = s2 = 0.0; c = 0; prev = dayid[t]
                if c >= 6:
                    mu = s / c
                    var = s2 / c - mu * mu
                    out[t] = (sp[t] - mu) / np.sqrt(var) if var > 1e-18 else np.nan
                v = sp[t]
                if np.isfinite(v):
                    s += v; s2 += v * v; c += 1
            z = _shift(out, 1)
            z = np.clip(z, -3, 3)
            return np.where(np.abs(z) >= thr, -z, 0.0)
        return _pair_weights(P, SIBLING_PAIRS, f)

    if k == "pair_bar_reversal":
        lag = cfg.get("lag", 1)

        def f(la, lb):
            sp = la - lb
            d = np.full(T, np.nan)
            d[lag:] = sp[lag:] - sp[:-lag]
            return -_shift(d, 1)
        return _pair_weights(P, SIBLING_PAIRS, f)

    if k == "pair_open_anchor":
        dayid = P.day
        first = np.zeros(T, dtype=bool)
        first[0] = True
        first[1:] = dayid[1:] != dayid[:-1]
        anchor_idx = np.maximum.accumulate(np.where(first, np.arange(T), 0))

        def f(la, lb):
            sp = la - lb
            dev = sp - sp[anchor_idx]
            return -_shift(dev, 1)
        return _pair_weights(P, SIBLING_PAIRS, f)

    if k == "pair_ewma_z":
        hl = cfg["hl"]

        def f(la, lb):
            sp = (la - lb)[:, None]
            mu = _ewma(sp, hl)
            dev = sp - mu
            sd = np.sqrt(_ewma(dev * dev, hl))
            z = np.where(sd > 1e-12, dev / sd, np.nan)[:, 0]
            return -np.clip(_shift(z, 1), -3, 3)
        return _pair_weights(P, SIBLING_PAIRS, f)

    if k == "pair_beta_resid":
        n = cfg["win"]

        def f(la, lb):
            ra = np.diff(la, prepend=np.nan)[:, None]
            rb = np.diff(lb, prepend=np.nan)[:, None]
            ma, _ = _nan_roll(ra, n)
            mb, _ = _nan_roll(rb, n)
            cov, _ = _nan_roll(ra * rb, n)
            vb, _ = _nan_roll(rb * rb, n)
            beta = (cov - ma * mb) / np.maximum(vb - mb * mb, 1e-18)
            beta = np.clip(beta, 0.2, 5.0)
            resid = ra - beta * rb
            cum = np.nancumsum(np.where(np.isfinite(resid), resid, 0.0), axis=0)
            mu, sd = _nan_roll(cum, n)
            z = ((cum - mu) / sd)[:, 0]
            return -np.clip(_shift(z, 1), -3, 3)
        return _pair_weights(P, SIBLING_PAIRS, f)

    if k == "levered_resid":
        n = cfg["win"]
        W = np.zeros((T, S))
        for lev, base, mult in LEVERED_PAIRS:
            il, ib = P.col(lev), P.col(base)
            if il is None or ib is None:
                continue
            sp = (P.logc[:, il] - mult * P.logc[:, ib])[:, None]
            mu, sd = _nan_roll(sp, n)
            z = np.clip(_shift(((sp - mu) / sd)[:, 0], 1), -3, 3)
            s = np.where(np.isfinite(z), -z, 0.0)
            W[:, il] += s
            W[:, ib] -= s * mult
        g = np.abs(W).sum(axis=1, keepdims=True)
        return np.where(g > 0, W / np.maximum(g, 1e-12), 0.0)

    if k in ("etf_vs_basket", "basket_leads_etf", "etf_leads_basket"):
        n = cfg.get("win", 78)
        lag = cfg.get("lag", 1)
        W = np.zeros((T, S))
        for etf, members in SECTOR_BASKETS.items():
            ie = P.col(etf)
            cols = P.cols(members)
            if ie is None or len(cols) < 2:
                continue
            lb = np.nanmean(P.logc[:, cols], axis=1)
            le = P.logc[:, ie]
            if k == "etf_vs_basket":
                sp = (le - lb)[:, None]
                mu, sd = _nan_roll(sp, n)
                s = -np.clip(_shift(((sp - mu) / sd)[:, 0], 1), -3, 3)
                s = np.where(np.isfinite(s), s, 0.0)
                W[:, ie] += s
                for c in cols:
                    W[:, c] -= s / len(cols)
            else:
                db = np.full(T, np.nan); db[lag:] = lb[lag:] - lb[:-lag]
                de = np.full(T, np.nan); de[lag:] = le[lag:] - le[:-lag]
                drive = _shift(db if k == "basket_leads_etf" else de, 1)
                drive = np.where(np.isfinite(drive), drive, 0.0)
                if k == "basket_leads_etf":
                    W[:, ie] += drive
                    for c in cols:
                        W[:, c] -= drive / len(cols)
                else:
                    for c in cols:
                        W[:, c] += drive / len(cols)
                    W[:, ie] -= drive
        g = np.abs(W).sum(axis=1, keepdims=True)
        return np.where(g > 0, W / np.maximum(g, 1e-12), 0.0)

    if k == "spy_vs_sector_composite":
        n = cfg.get("win", 78)
        ie = P.col("SPY")
        cols = P.cols(SECTORS)
        if ie is None or len(cols) < 6:
            return None
        lb = np.nanmean(P.logc[:, cols], axis=1)
        sp = (P.logc[:, ie] - lb)[:, None]
        mu, sd = _nan_roll(sp, n)
        s = -np.clip(_shift(((sp - mu) / sd)[:, 0], 1), -3, 3)
        s = np.where(np.isfinite(s), s, 0.0)
        W = np.zeros((T, S))
        W[:, ie] += s
        for c in cols:
            W[:, c] -= s / len(cols)
        g = np.abs(W).sum(axis=1, keepdims=True)
        return np.where(g > 0, W / np.maximum(g, 1e-12), 0.0)

    if k == "xs_reversal":
        univ = {"etf": LIQUID_ETFS, "mega": MEGACAPS, "sector": SECTORS}[cfg["univ"]]
        cols = P.cols(univ)
        lb = cfg["lb"]
        R = np.full((T, len(cols)), np.nan)
        L = P.logc[:, cols]
        R[lb:] = L[lb:] - L[:-lb]
        # a lookback that straddles the open is an overnight gap, not an intraday move
        straddle = np.zeros(T, dtype=bool)
        straddle[:lb] = True
        straddle[lb:] = P.day[lb:] != P.day[:-lb]
        R[straddle] = np.nan
        sig = -_shift(R, 1)
        if cfg.get("vol_scale"):
            _, sd = _nan_roll(np.vstack([np.full((1, len(cols)), np.nan), np.diff(L, axis=0)]),
                              cfg.get("volwin", 390))
            sig = sig / np.maximum(_shift(sd, 1), 1e-6)
        if cfg.get("rank"):
            order = np.argsort(np.argsort(np.where(np.isfinite(sig), sig, np.inf), axis=1), axis=1)
            n_ok = np.isfinite(sig).sum(axis=1, keepdims=True)
            sig = np.where(np.isfinite(sig), order - (n_ok - 1) / 2.0, np.nan)
        if cfg.get("mktneutral"):
            mkt = np.nanmean(sig, axis=1, keepdims=True)
            sig = sig - mkt
        cond = cfg.get("cond")
        if cond:
            dv = P.dvol[:, cols]
            mu, sd = _nan_roll(dv, 78 * 5)
            zv = _shift((dv - mu) / np.maximum(sd, 1e-9), 1)
            if cond == "high_vol":
                sig = np.where(zv > 1.0, sig, np.nan)
            elif cond == "low_vol":
                sig = np.where(zv < 0.0, sig, np.nan)
        slots = cfg.get("slots")
        Wc = _cross_demean(sig)
        if slots is not None:
            keep = (P.slot >= slots[0]) & (P.slot < slots[1])
            Wc[~keep] = 0.0
        W = np.zeros((T, S))
        W[:, cols] = Wc
        return W

    if k == "resid_reversal":
        univ = {"etf": LIQUID_ETFS, "mega": MEGACAPS, "sector": SECTORS}[cfg["univ"]]
        cols = P.cols(univ)
        lb = cfg["lb"]
        L = P.logc[:, cols]
        r = np.vstack([np.full((1, len(cols)), np.nan), np.diff(L, axis=0)])
        r[~P.same_day_back()[:, :len(cols)]] = np.nan
        mkt = np.nanmean(r, axis=1, keepdims=True)
        n = cfg.get("betawin", 78 * 10)
        cov, _ = _nan_roll(r * mkt, n)
        var, _ = _nan_roll(mkt * mkt, n)
        beta = np.clip(cov / np.maximum(var, 1e-18), -1.0, 3.0)
        resid = r - beta * mkt
        rz = np.where(np.isfinite(resid), resid, 0.0)
        cum = np.zeros_like(rz)
        for i in range(lb):
            cum += _shift(rz, i)
        sig = -_shift(cum, 1)
        straddle = np.zeros(T, dtype=bool)
        straddle[:lb + 1] = True
        straddle[lb + 1:] = P.day[lb + 1:] != P.day[:-(lb + 1)]
        sig[straddle] = np.nan
        Wc = _cross_demean(sig)
        W = np.zeros((T, S))
        W[:, cols] = Wc
        return W

    if k == "pca_resid":
        cols = P.cols(SECTORS + ["SPY", "QQQ", "IWM"])
        lb = cfg["lb"]
        L = P.logc[:, cols]
        r = np.vstack([np.full((1, len(cols)), np.nan), np.diff(L, axis=0)])
        r[~P.same_day_back()[:, :len(cols)]] = np.nan
        rz = np.where(np.isfinite(r), r, 0.0)
        cum = np.zeros_like(rz)
        for i in range(lb):
            cum += _shift(rz, i)
        # remove the first principal direction cross-sectionally at each bar (equal-weight
        # proxy plus a rolling loading) -- cheap, and it is the market factor
        mkt = cum.mean(axis=1, keepdims=True)
        n = 78 * 10
        cov, _ = _nan_roll(cum * mkt, n)
        var, _ = _nan_roll(mkt * mkt, n)
        load = np.clip(cov / np.maximum(var, 1e-18), -1.0, 3.0)
        resid = cum - load * mkt
        sig = -_shift(resid, 1)
        Wc = _cross_demean(sig)
        W = np.zeros((T, S))
        W[:, cols] = Wc
        return W

    if k in ("gap_reversal", "gap_continuation", "gap_resid_reversal"):
        univ = {"etf": LIQUID_ETFS, "mega": MEGACAPS}[cfg["univ"]]
        cols = P.cols(univ)
        first = np.zeros(T, dtype=bool)
        first[0] = True
        first[1:] = P.day[1:] != P.day[:-1]
        L = P.logc[:, cols]
        O = np.log(P.open[:, cols])
        prev_close = _shift(L, 1)
        gap = np.where(first[:, None], O - prev_close, np.nan)
        # hold the gap value for the whole session
        gap_day = np.full_like(gap, np.nan)
        cur = np.full(len(cols), np.nan)
        for t in range(T):
            if first[t]:
                cur = gap[t]
            gap_day[t] = cur
        sig = gap_day if k == "gap_continuation" else -gap_day
        if k == "gap_resid_reversal":
            m = np.nanmean(gap_day, axis=1, keepdims=True)
            sig = -(gap_day - m)
        keep = P.slot < cfg.get("hold_bars", 12)
        Wc = _cross_demean(sig)
        Wc[~keep] = 0.0
        W = np.zeros((T, S))
        W[:, cols] = Wc
        return W

    if k == "first30_reversal":
        univ = {"etf": LIQUID_ETFS, "mega": MEGACAPS}[cfg["univ"]]
        cols = P.cols(univ)
        nb = cfg.get("meas_bars", 6)
        L = P.logc[:, cols]
        first = np.zeros(T, dtype=bool)
        first[0] = True
        first[1:] = P.day[1:] != P.day[:-1]
        anchor_idx = np.maximum.accumulate(np.where(first, np.arange(T), 0))
        move = L - L[anchor_idx]
        sig = np.full_like(move, np.nan)
        at = P.slot == nb
        sig[at] = -move[at]
        cur = np.full(len(cols), np.nan)
        for t in range(T):
            if first[t]:
                cur = np.full(len(cols), np.nan)
            if at[t]:
                cur = sig[t]
            sig[t] = cur
        lo, hi = cfg.get("slots", (nb + 1, BARS_PER_DAY))
        keep = (P.slot >= lo) & (P.slot < hi)
        Wc = _cross_demean(sig)
        Wc[~keep] = 0.0
        W = np.zeros((T, S))
        W[:, cols] = Wc
        return W

    if k == "leadlag":
        lag = cfg.get("lag", 1)
        sign = cfg.get("sign", 1.0)
        W = np.zeros((T, S))
        for lead, lagger in LEADLAG_PAIRS:
            il, ig = P.col(lead), P.col(lagger)
            if il is None or ig is None:
                continue
            d = np.full(T, np.nan)
            d[lag:] = P.logc[lag:, il] - P.logc[:-lag, il]
            drive = _shift(d, 1)
            drive = np.where(np.isfinite(drive), drive, 0.0) * sign
            W[:, ig] += drive
            W[:, il] -= drive
        g = np.abs(W).sum(axis=1, keepdims=True)
        return np.where(g > 0, W / np.maximum(g, 1e-12), 0.0)

    if k == "vwap_reversion":
        # distance of the last price from the session's own volume-weighted average price,
        # cross-sectionally demeaned so it is a relative-value trade, not a market bet
        univ = {"etf": LIQUID_ETFS, "mega": MEGACAPS, "sector": SECTORS}[cfg["univ"]]
        cols = P.cols(univ)
        first = np.zeros(T, dtype=bool)
        first[0] = True
        first[1:] = P.day[1:] != P.day[:-1]
        pv = P.vwap[:, cols] * np.maximum(P.dvol[:, cols], 0.0)
        vv = np.maximum(P.dvol[:, cols], 0.0)
        pv = np.where(np.isfinite(pv), pv, 0.0)
        cum_pv = np.zeros_like(pv)
        cum_v = np.zeros_like(vv)
        apv = np.zeros(len(cols)); av = np.zeros(len(cols))
        for t in range(T):
            if first[t]:
                apv = np.zeros(len(cols)); av = np.zeros(len(cols))
            apv = apv + pv[t]; av = av + vv[t]
            cum_pv[t] = apv; cum_v[t] = av
        sess_vwap = np.where(cum_v > 0, cum_pv / np.maximum(cum_v, 1e-9), np.nan)
        dev = P.logc[:, cols] - np.log(np.where(sess_vwap > 0, sess_vwap, np.nan))
        sig = -_shift(dev, 1)
        if cfg.get("min_slot"):
            sig[P.slot < cfg["min_slot"]] = np.nan
        Wc = _cross_demean(sig)
        W = np.zeros((T, S))
        W[:, cols] = Wc
        return W

    if k == "pair_z_hlgate":
        # trade a sibling pair only while its OWN trailing spread looks fast-mean-reverting:
        # the AR(1) coefficient of the spread over the trailing window implies a half-life,
        # and a spread that is drifting (phi near 1) is not a reversion trade
        n, maxhl = cfg["win"], cfg["maxhl"]

        def f(la, lb):
            sp = (la - lb)[:, None]
            mu, sd = _nan_roll(sp, n)
            dev = sp - mu
            d1 = _shift(dev, 1)
            c1, _ = _nan_roll(dev * d1, n)
            c0, _ = _nan_roll(d1 * d1, n)
            phi = np.clip(c1 / np.maximum(c0, 1e-24), -0.99, 0.999)
            with np.errstate(divide="ignore", invalid="ignore"):
                hl = np.log(0.5) / np.log(np.maximum(phi, 1e-6))
            z = np.clip(_shift((dev / sd)[:, 0], 1), -3, 3)
            gate = _shift(hl[:, 0], 1)
            return np.where(np.isfinite(gate) & (gate <= maxhl), -z, 0.0)
        return _pair_weights(P, SIBLING_PAIRS, f)

    if k == "pair_z_riskparity":
        # same z signal, but pairs are sized by INVERSE spread volatility rather than equal
        # notional -- a structurally different portfolio construction on the same alpha
        n = cfg["win"]
        W = np.zeros((T, S))
        for a, b in SIBLING_PAIRS:
            ia, ib = P.col(a), P.col(b)
            if ia is None or ib is None:
                continue
            sp = (P.logc[:, ia] - P.logc[:, ib])[:, None]
            mu, sd = _nan_roll(sp, n)
            z = np.clip(_shift(((sp - mu) / sd)[:, 0], 1), -3, 3)
            inv = 1.0 / np.maximum(_shift(sd[:, 0], 1), 1e-5)
            s = np.where(np.isfinite(z) & np.isfinite(inv), -z * inv, 0.0)
            W[:, ia] += s
            W[:, ib] -= s
        g = np.abs(W).sum(axis=1, keepdims=True)
        return np.where(g > 0, W / np.maximum(g, 1e-12), 0.0)

    if k == "spy_leads_sectors":
        lag = cfg.get("lag", 1)
        sign = cfg.get("sign", 1.0)
        im = P.col("SPY")
        cols = P.cols(SECTORS)
        if im is None or len(cols) < 6:
            return None
        d = np.full(T, np.nan)
        d[lag:] = P.logc[lag:, im] - P.logc[:-lag, im]
        drive = _shift(d, 1)
        # cross-sectional beta dispersion: high-beta sectors should lag the index move more
        r = np.vstack([np.full((1, len(cols)), np.nan), np.diff(P.logc[:, cols], axis=0)])
        mkt = np.diff(P.logc[:, im], prepend=np.nan)[:, None]
        cov, _ = _nan_roll(r * mkt, 78 * 20)
        var, _ = _nan_roll(mkt * mkt, 78 * 20)
        beta = np.clip(cov / np.maximum(var, 1e-24), 0.0, 3.0)
        sig = sign * beta * drive[:, None]
        Wc = _cross_demean(sig)
        W = np.zeros((T, S))
        W[:, cols] = Wc
        return W

    if k == "triplet_resid":
        n = cfg["win"]
        ia, ib, ic = P.col("SPY"), P.col("QQQ"), P.col("IWM")
        if None in (ia, ib, ic):
            return None
        ra = np.diff(P.logc[:, ia], prepend=np.nan)[:, None]
        rb = np.diff(P.logc[:, ib], prepend=np.nan)[:, None]
        rc = np.diff(P.logc[:, ic], prepend=np.nan)[:, None]
        cb, _ = _nan_roll(ra * rb, n); vb, _ = _nan_roll(rb * rb, n)
        cc, _ = _nan_roll(ra * rc, n); vc, _ = _nan_roll(rc * rc, n)
        b1 = np.clip(cb / np.maximum(vb, 1e-18), 0.0, 2.0)
        b2 = np.clip(cc / np.maximum(vc, 1e-18), 0.0, 2.0)
        resid = ra - 0.5 * (b1 * rb + b2 * rc)
        cum = np.nancumsum(np.where(np.isfinite(resid), resid, 0.0), axis=0)
        mu, sd = _nan_roll(cum, n)
        z = -np.clip(_shift(((cum - mu) / sd)[:, 0], 1), -3, 3)
        z = np.where(np.isfinite(z), z, 0.0)
        W = np.zeros((T, S))
        W[:, ia] += z
        W[:, ib] -= 0.5 * z
        W[:, ic] -= 0.5 * z
        g = np.abs(W).sum(axis=1, keepdims=True)
        return np.where(g > 0, W / np.maximum(g, 1e-12), 0.0)

    raise ValueError(f"unknown kind {k}")


def config_list():
    cfgs = []
    add = cfgs.append
    # A -- same-claim ETF pairs
    for win in (12, 39, 78, 234):
        add({"name": f"A1_pair_z_w{win}", "kind": "pair_z", "win": win})
    add({"name": "A1b_pair_z_w78_thr1", "kind": "pair_z", "win": 78, "thr": 1.0})
    add({"name": "A1c_pair_z_w78_thr2", "kind": "pair_z", "win": 78, "thr": 2.0})
    add({"name": "A2_pair_z_intraday", "kind": "pair_z_intraday"})
    add({"name": "A2b_pair_z_intraday_thr1", "kind": "pair_z_intraday", "thr": 1.0})
    for lag in (1, 2, 6):
        add({"name": f"A3_pair_bar_reversal_l{lag}", "kind": "pair_bar_reversal", "lag": lag})
    add({"name": "A4_pair_open_anchor", "kind": "pair_open_anchor"})
    for hl in (20.0, 78.0):
        add({"name": f"A5_pair_ewma_z_hl{int(hl)}", "kind": "pair_ewma_z", "hl": hl})
    for win in (78, 390):
        add({"name": f"A6_pair_beta_resid_w{win}", "kind": "pair_beta_resid", "win": win})
    for win in (78, 390):
        add({"name": f"A7_levered_resid_w{win}", "kind": "levered_resid", "win": win})
    # B -- ETF vs basket, sector composite, lead-lag on the basket
    for win in (39, 78, 390):
        add({"name": f"B1_etf_vs_basket_w{win}", "kind": "etf_vs_basket", "win": win})
    for lag in (1, 3):
        add({"name": f"B2_basket_leads_etf_l{lag}", "kind": "basket_leads_etf", "lag": lag})
        add({"name": f"B3_etf_leads_basket_l{lag}", "kind": "etf_leads_basket", "lag": lag})
    for win in (78, 390):
        add({"name": f"B4_spy_vs_sectors_w{win}", "kind": "spy_vs_sector_composite", "win": win})
    # C -- cross-sectional short-horizon reversal
    for univ in ("etf", "mega", "sector"):
        for lb in (1, 3, 6, 12):
            add({"name": f"C1_xs_rev_{univ}_lb{lb}", "kind": "xs_reversal", "univ": univ, "lb": lb})
    add({"name": "C3_xs_rev_etf_lb6_vol", "kind": "xs_reversal", "univ": "etf", "lb": 6, "vol_scale": True})
    add({"name": "C3b_xs_rev_mega_lb6_vol", "kind": "xs_reversal", "univ": "mega", "lb": 6, "vol_scale": True})
    add({"name": "C4_xs_rev_etf_lb6_hivol", "kind": "xs_reversal", "univ": "etf", "lb": 6, "cond": "high_vol"})
    add({"name": "C5_xs_rev_etf_lb6_lovol", "kind": "xs_reversal", "univ": "etf", "lb": 6, "cond": "low_vol"})
    add({"name": "C6_xs_rev_etf_lb6_open", "kind": "xs_reversal", "univ": "etf", "lb": 6, "slots": (0, 6)})
    add({"name": "C7_xs_rev_etf_lb6_close", "kind": "xs_reversal", "univ": "etf", "lb": 6, "slots": (72, 78)})
    add({"name": "C8_xs_rev_etf_lb6_mid", "kind": "xs_reversal", "univ": "etf", "lb": 6, "slots": (18, 54)})
    add({"name": "C9_xs_rev_etf_lb6_rank", "kind": "xs_reversal", "univ": "etf", "lb": 6, "rank": True})
    add({"name": "C9b_xs_rev_mega_lb6_rank", "kind": "xs_reversal", "univ": "mega", "lb": 6, "rank": True})
    for univ in ("etf", "mega"):
        for lb in (3, 12):
            add({"name": f"C2_resid_rev_{univ}_lb{lb}", "kind": "resid_reversal", "univ": univ, "lb": lb})
    add({"name": "F2_pca_resid_lb6", "kind": "pca_resid", "lb": 6})
    add({"name": "F2b_pca_resid_lb12", "kind": "pca_resid", "lb": 12})
    # D -- gap / opening / first-30 reversion
    for univ in ("etf", "mega"):
        add({"name": f"D1_gap_rev_{univ}", "kind": "gap_reversal", "univ": univ})
        add({"name": f"D2_gap_cont_{univ}", "kind": "gap_continuation", "univ": univ})
        add({"name": f"D3_gap_resid_rev_{univ}", "kind": "gap_resid_reversal", "univ": univ})
        add({"name": f"D4_first30_rev_{univ}", "kind": "first30_reversal", "univ": univ})
    add({"name": "D1b_gap_rev_etf_hold78", "kind": "gap_reversal", "univ": "etf", "hold_bars": 78})
    add({"name": "D4b_first30_rev_etf_close", "kind": "first30_reversal", "univ": "etf", "slots": (72, 78)})
    # E -- lead-lag between correlated names
    for lag in (1, 2, 6):
        add({"name": f"E1_leadlag_l{lag}", "kind": "leadlag", "lag": lag})
    add({"name": "E2_leadlag_l1_rev", "kind": "leadlag", "lag": 1, "sign": -1.0})
    # F -- multi-leg cointegration
    for win in (78, 390):
        add({"name": f"F1_triplet_resid_w{win}", "kind": "triplet_resid", "win": win})
    # G -- session-VWAP anchored reversion (a different anchor from every family above)
    for univ in ("etf", "mega", "sector"):
        add({"name": f"G1_vwap_rev_{univ}", "kind": "vwap_reversion", "univ": univ})
    add({"name": "G1b_vwap_rev_etf_after10", "kind": "vwap_reversion", "univ": "etf", "min_slot": 6})
    # H -- construction / gating variants that are genuinely different objects
    add({"name": "H1_pair_z_hlgate_w78_hl30", "kind": "pair_z_hlgate", "win": 78, "maxhl": 30.0})
    add({"name": "H1b_pair_z_hlgate_w390_hl60", "kind": "pair_z_hlgate", "win": 390, "maxhl": 60.0})
    add({"name": "H2_pair_z_riskparity_w78", "kind": "pair_z_riskparity", "win": 78})
    add({"name": "H3_spy_leads_sectors_beta", "kind": "spy_leads_sectors", "lag": 1})
    add({"name": "H3b_spy_leads_sectors_beta_rev", "kind": "spy_leads_sectors", "lag": 1, "sign": -1.0})
    add({"name": "C2c_resid_rev_sector_lb6", "kind": "resid_reversal", "univ": "sector", "lb": 6})
    # I -- no-trade-band / holding-period constructions. These exist because a 5-minute
    # z-score rewrites the whole book every bar; the band and the hold are what make an RV
    # rule implementable at all, so they are searched, not bolted on afterwards.
    for win in (78, 390):
        for entry, exit_ in ((2.0, 0.5), (2.5, 1.0), (1.5, 0.25)):
            add({"name": f"I1_pair_band_w{win}_e{entry}_x{exit_}", "kind": "pair_z_band",
                 "win": win, "entry": entry, "exit": exit_})
    add({"name": "I2_levered_band_w390_e2_x0.5", "kind": "levered_resid_band",
         "win": 390, "entry": 2.0, "exit": 0.5})
    add({"name": "I2b_levered_band_w78_e2_x0.5", "kind": "levered_resid_band",
         "win": 78, "entry": 2.0, "exit": 0.5})
    add({"name": "I3_etfbasket_band_w390_e2_x0.5", "kind": "etf_basket_band",
         "win": 390, "entry": 2.0, "exit": 0.5})
    for hold in (6, 13, 39):
        add({"name": f"I4_xs_rev_etf_lb6_hold{hold}", "kind": "xs_reversal", "univ": "etf",
             "lb": 6, "hold": hold})
        add({"name": f"I5_xs_rev_mega_lb6_hold{hold}", "kind": "xs_reversal", "univ": "mega",
             "lb": 6, "hold": hold})
    add({"name": "I6_vwap_rev_etf_hold13", "kind": "vwap_reversion", "univ": "etf", "hold": 13})
    add({"name": "I7_pair_z_w390_hold13", "kind": "pair_z", "win": 390, "hold": 13})
    add({"name": "I8_resid_rev_etf_lb12_hold13", "kind": "resid_reversal", "univ": "etf",
         "lb": 12, "hold": 13})
    return cfgs


# ---------------------------------------------------------------- driver

def window_mask(P, lo, hi):
    return (P.daykey >= lo) & (P.daykey <= hi)


def run(stage: str):
    P = Panel()
    lo, hi = DESIGN if stage == "design" else HELDOUT
    mask = window_mask(P, lo, hi)
    print(f"stage={stage} window {lo}..{hi}  bars={mask.sum()}  days={len(set(P.day[mask]))}",
          flush=True)
    cfgs = config_list()
    results = []
    daily = {}
    daily_gross = {}
    for i, cfg in enumerate(cfgs):
        try:
            W = build(P, cfg)
        except Exception as exc:  # noqa: BLE001
            print(f"  {cfg['name']} BUILD FAILED {exc}", flush=True)
            continue
        if W is None:
            print(f"  {cfg['name']} SKIPPED (missing symbols)", flush=True)
            continue
        if cfg.get("hold"):
            # refresh the target only every `hold` bars. Turnover, not signal quality, is what
            # kills a 5-minute reversal rule, so the holding period is a first-class dimension
            # of the search rather than a constant to be tuned afterwards.
            W = _hold_every(W, P.day, P.slot, cfg["hold"])
            g = np.abs(W).sum(axis=1, keepdims=True)
            W = np.where(g > 0, W / np.maximum(g, 1e-12), 0.0)
        intraday_flat = True   # every config in this theme is flat overnight
        g, turn = evaluate(P, W, mask, intraday_flat=intraday_flat)
        row = {"name": cfg["name"], "kind": cfg["kind"]}
        for bp in COST_RUNGS_BP:
            d, keep = daily_series(P, g, turn, mask, bp)
            row[f"sharpe_{bp}bp"] = sharpe(d)
            if bp == HEADLINE_BP:
                daily[cfg["name"]] = d
                row["ann_ret"] = float(d.mean() * 252)
                row["ann_vol"] = float(d.std(ddof=1) * np.sqrt(252))
                row["n_days"] = int(d.size)
        gd, _ = daily_series(P, g, turn, mask, 0.0, reg_bp=0.0)   # true before-cost
        row["sharpe_gross"] = sharpe(gd)
        daily_gross[cfg["name"]] = gd
        # day indices are GLOBAL, so bincount emits a zero for every day outside the window;
        # averaging over those would understate turnover by the ratio of the two windows.
        # Average over the days the window actually contains, which is exactly `keep`.
        tpd = np.bincount(P.day[mask], weights=turn[mask], minlength=P.day.max() + 1)
        row["daily_turnover"] = float(tpd[keep].mean()) if keep.any() else float("nan")
        # The TOTAL charge per unit of turnover this config's gross edge can bear before it
        # is exactly consumed. Reported this way rather than "bp per side" because several
        # configs cannot even pay REG_BP_PER_TURNOVER (the SEC 31 / FINRA TAF pass-through),
        # and a per-side figure would come out negative and read as a bug rather than a fact.
        gross_ret = row["sharpe_gross"] * row["ann_vol"]
        row["breakeven_bp_per_turnover"] = (
            float(gross_ret / (row["daily_turnover"] * 252 * 1e-4))
            if row["daily_turnover"] > 0 and np.isfinite(gross_ret) else float("nan"))
        row["can_pay_regulatory_floor"] = bool(
            row["breakeven_bp_per_turnover"] > REG_BP_PER_TURNOVER)
        results.append(row)
        print(f"  [{i+1}/{len(cfgs)}] {cfg['name']:32s} gross={row['sharpe_gross']:+.2f} "
              f"net@1bp={row['sharpe_1.0bp']:+.2f} turn/day={row['daily_turnover']:.2f}",
              flush=True)
        del W
    return P, results, daily, daily_gross


def block_bootstrap_max(daily: dict, n_boot=500, block=5, seed=20260820):
    names = list(daily)
    M = np.vstack([daily[n] for n in names])          # [C, D]
    M = M - M.mean(axis=1, keepdims=True)             # H0: zero mean, keep the correlations
    C, D = M.shape
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(D / block))
    maxes = np.empty(n_boot)
    for b in range(n_boot):
        starts = rng.integers(0, D, size=nb)
        idx = (starts[:, None] + np.arange(block)[None, :]).ravel()[:D] % D
        R = M[:, idx]
        s = R.mean(axis=1) / np.maximum(R.std(axis=1, ddof=1), 1e-18) * np.sqrt(252)
        maxes[b] = np.nanmax(s)
    return maxes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["design", "heldout"], required=True)
    ap.add_argument("--only", default=None, help="comma-separated config names (heldout stage)")
    args = ap.parse_args()

    if args.stage == "heldout" and not args.only:
        raise SystemExit("heldout stage requires --only with the FROZEN shortlist")

    global config_list_filter
    if args.only:
        keep = set(args.only.split(","))
        base = config_list
        globals()["config_list"] = lambda: [c for c in base() if c["name"] in keep]

    P, results, daily, daily_gross = run(args.stage)
    results.sort(key=lambda r: -(r["sharpe_1.0bp"] if np.isfinite(r["sharpe_1.0bp"]) else -9))

    payload = {
        "stage": args.stage,
        "window": list(DESIGN if args.stage == "design" else HELDOUT),
        "n_configs": len(results),
        "cost_rungs_bp_per_side": list(COST_RUNGS_BP),
        "headline_bp_per_side": HEADLINE_BP,
        "cost_provenance": "ADVERSE_PROXY_FOR_AN_UNMEASURED_LEG -- repo-measured liquid-name "
                           "close half-spread is 1.13 bp (t3, 19,835 symbol-days); intraday "
                           "mega-cap ETF spreads are tighter, so 1.0 bp/side is conservative. "
                           "The 2.5 bp rung is retail_taker_costs()'s own default half-spread.",
        "regulatory_bp_per_turnover": REG_BP_PER_TURNOVER,
        "regulatory_provenance": "BROKER_SCHEDULE -- SEC Section 31 ($27.80/$1M of sales, "
                                 "0.278 bp sell-side) plus FINRA TAF; charged on every rung",
        "borrow_annual": BORROW_ANNUAL,
        "borrow_note": "zero because every config is flat at the closing bar; US borrow fees "
                       "accrue overnight. A variant that held overnight would owe B22G's "
                       "measured 0.33%/yr ETB median and is not what was tested here.",
        "execution": "signal from closes through bar t-1, fill at bar-t VWAP, return vwap[t+1]/vwap[t]-1",
        "results": results,
    }
    def dist(key):
        v = np.array([r[key] for r in results if np.isfinite(r.get(key, np.nan))])
        if v.size == 0:
            return None
        return {"n": int(v.size), "min": float(v.min()), "p10": float(np.percentile(v, 10)),
                "p25": float(np.percentile(v, 25)), "median": float(np.median(v)),
                "p75": float(np.percentile(v, 75)), "p90": float(np.percentile(v, 90)),
                "max": float(v.max()), "mean": float(v.mean()), "sd": float(v.std(ddof=1))}

    payload["distribution"] = {k: dist(k) for k in
                               ("sharpe_gross", "sharpe_0.5bp", "sharpe_1.0bp", "sharpe_2.0bp", "sharpe_2.5bp")}
    if args.stage == "design":
        maxes = block_bootstrap_max(daily)
        maxes_gross = block_bootstrap_max(daily_gross)
        payload["null_max_sharpe"] = {
            "method": "stationary block bootstrap (block=5 days) of DEMEANED daily PnL, same "
                      "day indices across all configs so cross-config correlation is preserved",
            "n_boot": int(maxes.size),
            "mean": float(np.mean(maxes)),
            "p50": float(np.percentile(maxes, 50)),
            "p90": float(np.percentile(maxes, 90)),
            "p95": float(np.percentile(maxes, 95)),
            "p99": float(np.percentile(maxes, 99)),
        }
        n = len(results)
        yrs = results[0]["n_days"] / 252 if results else 4.0
        payload["null_max_sharpe"]["naive_sqrt_2lnN"] = float(np.sqrt(2 * np.log(max(n, 2))) / np.sqrt(yrs))
        payload["null_max_sharpe_gross"] = {
            "note": "same bootstrap on the BEFORE-COST daily PnL -- answers 'is there any "
                    "signal at all', separately from 'does it survive frictions'",
            "mean": float(np.mean(maxes_gross)), "p95": float(np.percentile(maxes_gross, 95)),
            "p99": float(np.percentile(maxes_gross, 99))}
        np.savez_compressed(CACHE / "rv_design_daily.npz", **daily)

    out = OUT / f"SWEEP_intraday_rv_{args.stage}.json"
    out.write_text(json.dumps(payload, indent=1))
    print(f"wrote {out}", flush=True)


if __name__ == "__main__":
    main()
