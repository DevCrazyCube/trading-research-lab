#!/usr/bin/env python3
"""DEEP MINE: ETF STRUCTURAL relative value, beyond same-index siblings.

SCOPE. The sibling leg (SPY/IVV/VOO, XLK/VGT, GLD/IAU ...) is already covered by `rv_sweep.py`
and is deliberately EXCLUDED here. This file searches the structurally different claims:

  N  ETF vs its own component sum          -- the free stand-in for iNAV
  O  overlapping-holdings ETF pairs        -- different indices, real but partial overlap
  L  leveraged / inverse decay and the levered-complex close rebalance
  C  country ETF vs stale NAV              -- the local market is shut while the ETF trades
  P  premium / discount, traded ETF-only   -- the NAV deviation as a signal, not as a leg

HONESTY MECHANICS (the parts that make this a test rather than a search for a nice number)
  * DESIGN window only for every scoring decision: 2021-01-04 .. 2024-12-31.
    HELDOUT 2025-01-02 .. 2026-08-15 is unreachable from `--stage design`. The shortlist rule
    is written into DEEPMINE_etf_structural_rv.md and hashed BEFORE the design run.
  * The noise bar is BOTH the naive sqrt(2 ln N) in SE units AND a stationary block bootstrap
    of the demeaned daily PnL with the SAME day indices across configs, so the cross-config
    correlation (which is large here -- these formulas share legs) is preserved.
  * Costs. Market-neutral RV pays BOTH legs. Turnover is charged per SYMBOL at that symbol's
    own half-spread proxy (`deepmine_spread_calib.py`, tick floor x adversity, min 1.0 bp),
    plus 0.15 bp/turnover of SEC 31 + FINRA TAF, plus -- for any config that holds overnight --
    borrow at B22G's measured 0.33 %/yr ETB median on the SHORT notional, per calendar day.
  * Shortability is a CONSTRAINT, not a cost. `borrow_screen.json` is the traded account's own
    /v2/assets answer. Every config reports what share of its short notional sits in names this
    broker will not lend, and that share is reported next to its Sharpe rather than netted into
    it. Leveraged/inverse ETPs are the usual offenders and that kills part of family L outright.

EXECUTION MODEL. Signal from closes through bar t-1; position entered at bar-t VWAP; the bar
earns vwap[t+1]/vwap[t]-1. Intraday configs are flat at the closing bar. Overnight configs
carry the last bar's book through the gap and pay borrow for it.
"""
from __future__ import annotations

import argparse
import json
import pathlib

import numpy as np

CACHE = pathlib.Path(__file__).resolve().parents[2] / "research" / "data" / "rv_cache"
OUT = pathlib.Path(__file__).resolve().parents[2] / "research" / "trading_bot"
KEY = "etf_structural_rv"

DESIGN = ("2021-01-04", "2024-12-31")
HELDOUT = ("2025-01-02", "2026-08-15")
REG_BP_PER_TURNOVER = 0.15
BORROW_ANNUAL = 0.0033          # B22G etb_general_collateral median, 0.33 %/yr
FLAT_RUNGS_BP = (1.0, 2.0, 2.5)
BARS_PER_DAY = 78

# ------------------------------------------------------------------ structures

# N -- ETF vs its own component sum. Members are the ones this cache actually holds; the
# COVERED SHARE of each index is small for SPY/QQQ and that is stated rather than hidden --
# a partial basket is why the beta-hedged variants exist at all.
SYNTH_BASKETS = {
    "XLK": ["AAPL", "MSFT", "NVDA", "AVGO", "ORCL", "CRM", "AMD", "INTC", "CSCO", "ADBE"],
    "XLV": ["UNH", "JNJ", "LLY", "ABBV", "MRK"],
    "XLP": ["PG", "PEP", "KO", "WMT", "COST"],
    "XLC": ["META", "GOOGL", "GOOG", "NFLX"],
    "XLE": ["XOM", "CVX"],
    "XLY": ["AMZN", "TSLA", "HD"],
    "XLF": ["JPM", "BAC", "V", "MA"],
    "SMH": ["NVDA", "AVGO", "AMD", "INTC"],
    "QQQ": ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "AVGO", "TSLA", "NFLX", "COST",
            "ADBE", "AMD", "INTC", "CSCO", "PEP", "ORCL", "CRM"],
    "SPY": ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "AVGO", "TSLA", "BRK.B", "JPM",
            "LLY", "V", "XOM", "UNH", "MA", "COST", "HD", "PG", "JNJ", "WMT", "ABBV", "MRK",
            "ORCL", "CRM", "BAC", "CVX", "PEP", "KO", "AMD", "NFLX", "ADBE", "CSCO", "INTC"],
}

# O -- overlapping holdings, DIFFERENT indices. A 1:1 notional hedge is wrong for these, which
# is why every O config estimates a rolling hedge ratio.
OVERLAP_PAIRS = [
    ("XLK", "QQQ"), ("XLK", "SMH"), ("SMH", "QQQ"), ("XLC", "QQQ"), ("IWF", "QQQ"),
    ("MTUM", "QQQ"), ("IWM", "IJR"), ("IJH", "IWM"), ("MDY", "IWM"), ("IBB", "XBI"),
    ("ITB", "XHB"), ("GDX", "GDXJ"), ("KRE", "XLF"), ("XLRE", "VNQ"), ("EEM", "FXI"),
    ("EFA", "EWJ"), ("EEM", "EWZ"), ("USMV", "XLP"), ("VLUE", "XLF"), ("TLT", "IEF"),
    ("HYG", "LQD"), ("LQD", "IEF"), ("GDX", "GLD"), ("XLE", "USO"),
]

# L -- (levered, base, stated multiple)
LEVERED = [("SSO", "SPY", 2.0), ("UPRO", "SPY", 3.0), ("SDS", "SPY", -2.0),
           ("SPXU", "SPY", -3.0), ("SH", "SPY", -1.0), ("QLD", "QQQ", 2.0),
           ("TQQQ", "QQQ", 3.0), ("SQQQ", "QQQ", -3.0), ("PSQ", "QQQ", -1.0),
           ("TNA", "IWM", 3.0), ("TZA", "IWM", -3.0), ("TMF", "TLT", 3.0), ("TMV", "TLT", -3.0)]
# opposite-signed pairs on the same index: the pure decay claim, no base leg at all
DECAY_PAIRS = [("SSO", "SDS"), ("UPRO", "SPXU"), ("TQQQ", "SQQQ"), ("TNA", "TZA"),
               ("TMF", "TMV"), ("QLD", "PSQ")]
# indices whose levered complexes are large enough that the close rebalance is a real flow
REBAL_UNIVERSE = ["QQQ", "IWM", "SPY", "SMH", "XLE", "XLF", "TLT", "GDX", "IBB", "XBI"]

# C -- country / region funds whose local market is shut for most or all of the US session
COUNTRY = ["EWJ", "FXI", "EWZ", "EEM", "IEMG", "VWO", "EFA", "IEFA", "VEA"]

# P -- the ETF-only premium/discount book
PD_ETFS = ["XLK", "XLV", "XLP", "XLC", "XLE", "XLY", "XLF", "SMH", "QQQ", "SPY"]


# ------------------------------------------------------------------ rolling helpers

def _nan_roll(x, n):
    """Causal rolling mean and std over axis 0, NaN-aware, window n ending at t inclusive."""
    m = np.isfinite(x)
    xz = np.where(m, x, 0.0).astype(np.float64)
    z0 = np.zeros((1,) + x.shape[1:])
    cs = np.concatenate([z0, np.cumsum(xz, axis=0)])
    cs2 = np.concatenate([z0, np.cumsum(xz * xz, axis=0)])
    cn = np.concatenate([z0, np.cumsum(m, axis=0)])
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
    return np.where(bad, np.nan, mu), np.sqrt(np.where(bad, np.nan, var))


def _roll_mean(x, n):
    return _nan_roll(x, n)[0]


def _shift(x, k=1):
    out = np.full(x.shape, np.nan, dtype=np.float64)
    if k <= 0:
        return np.asarray(x, dtype=np.float64)
    out[k:] = x[:-k]
    return out


def _ewma(x, halflife):
    a = 1.0 - 0.5 ** (1.0 / halflife)
    T = x.shape[0]
    xf = np.array(x, dtype=np.float64, copy=True)
    idx = np.where(np.isfinite(xf), np.arange(T).reshape((-1,) + (1,) * (xf.ndim - 1)), 0)
    idx = np.maximum.accumulate(idx, axis=0)
    xf = np.take_along_axis(np.where(np.isfinite(xf), xf, 0.0), idx, axis=0)
    out = np.empty_like(xf)
    prev = xf[0].copy()
    block = 512
    for start in range(0, T, block):
        stop = min(start + block, T)
        k = np.arange(stop - start)
        w = (1.0 - a) ** k
        wc = w.reshape((-1,) + (1,) * (xf.ndim - 1))
        cs = np.cumsum(xf[start:stop] / wc, axis=0)
        out[start:stop] = prev * wc * (1 - a) + a * wc * cs
        prev = out[stop - 1]
    return out


def _ffill_daily(x, day, fill_at_open=0.0):
    x = np.array(x, dtype=np.float64, copy=True)
    first = np.zeros(x.shape[0], dtype=bool)
    first[0] = True
    first[1:] = day[1:] != day[:-1]
    x[first] = np.where(np.isfinite(x[first]), x[first], fill_at_open)
    idx = np.where(np.isfinite(x), np.arange(x.shape[0]).reshape((-1,) + (1,) * (x.ndim - 1)), 0)
    idx = np.maximum.accumulate(idx, axis=0)
    return np.take_along_axis(np.where(np.isfinite(x), x, 0.0), idx, axis=0)


def _ffill_all(x):
    """Forward-fill across sessions too -- for a book that is ALLOWED to hold overnight."""
    x = np.asarray(x, dtype=np.float64)
    idx = np.where(np.isfinite(x), np.arange(x.shape[0]).reshape((-1,) + (1,) * (x.ndim - 1)), 0)
    idx = np.maximum.accumulate(idx, axis=0)
    return np.take_along_axis(np.where(np.isfinite(x), x, 0.0), idx, axis=0)


def _hysteresis(z, day, entry, exit_, overnight=False):
    ev = np.full(z.shape, np.nan)
    ev = np.where(z <= -entry, 1.0, ev)
    ev = np.where(z >= entry, -1.0, ev)
    ev = np.where(np.abs(z) < exit_, 0.0, ev)
    return _ffill_all(ev) if overnight else _ffill_daily(ev, day, 0.0)


def _hold_every(w, day, slot, every):
    upd = (slot % every) == 0
    x = np.where(upd.reshape((-1,) + (1,) * (w.ndim - 1)), w, np.nan)
    return _ffill_daily(x, day, 0.0)


def _cross_demean(w):
    m = np.isfinite(w)
    w = np.where(m, w, 0.0)
    n = m.sum(axis=1, keepdims=True)
    w = w - np.where(n > 0, w.sum(axis=1, keepdims=True) / np.maximum(n, 1), 0.0) * m
    g = np.abs(w).sum(axis=1, keepdims=True)
    return np.where(g > 0, w / np.maximum(g, 1e-12), 0.0)


def _norm(W):
    g = np.abs(W).sum(axis=1, keepdims=True)
    return np.where(g > 0, W / np.maximum(g, 1e-12), 0.0)


# ------------------------------------------------------------------ panel

class Panel:
    """Deliberately leaner than rv_sweep's: this host has ~4 GB free and the full float64
    panel plus one config's weights does not fit twice."""

    def __init__(self, path=CACHE / "panel.npz"):
        z = np.load(path, allow_pickle=False)
        self.day = z["day"].astype(np.int64)
        self.slot = z["slot"].astype(np.int64)
        self.daykey = z["daykey"].astype(str)
        self.syms = [s.replace("_", ".") if s == "BRK_B" else s for s in z["syms"].astype(str)]
        close = z["close"]
        vwap = z["vwap"]
        self.dvol = z["dvol"]
        self.idx = {s: i for i, s in enumerate(self.syms)}
        self.T, self.S = close.shape
        with np.errstate(invalid="ignore", divide="ignore"):
            self.logc = np.log(close.astype(np.float64))
        self.tradable = np.isfinite(vwap) & np.isfinite(close)
        px = vwap.astype(np.float64)
        self.fwd_ret = np.full(px.shape, np.nan)
        self.fwd_ret[:-1] = px[1:] / px[:-1] - 1.0
        nxt = np.zeros_like(self.tradable)
        nxt[:-1] = self.tradable[1:]
        self.fwd_ret[~(self.tradable & nxt)] = np.nan
        del close, vwap, px, nxt, z
        # returns, with the overnight gap blanked so an INTRADAY signal never reads one
        r = np.full(self.logc.shape, np.nan)
        r[1:] = self.logc[1:] - self.logc[:-1]
        same = np.zeros(self.T, dtype=bool)
        same[1:] = self.day[1:] == self.day[:-1]
        self.same_day_back = same
        r[~same] = np.nan
        self.r = r
        self.first_bar = ~same
        last = np.zeros(self.T, dtype=bool)
        last[:-1] = self.day[1:] != self.day[:-1]
        last[-1] = True
        self.last_bar = last
        # calendar days between the close of day d and the close of day d+1
        dk = np.array(sorted(set(self.daykey)))
        d64 = dk.astype("datetime64[D]")
        gap = np.empty(d64.size)
        gap[:-1] = (d64[1:] - d64[:-1]).astype(float)
        gap[-1] = 1.0
        self.day_gap = gap                        # indexed by day id (day ids are sorted)
        self.n_days = int(self.day.max()) + 1

    def col(self, s):
        return self.idx.get(s)

    def cols(self, syms):
        return [self.idx[s] for s in syms if s in self.idx]


# ------------------------------------------------------------------ costs

def load_costs(P, model="headline"):
    """`model="tickfloor"` charges the RAW half-tick and nothing else: no adversity multiplier,
    no 1.0 bp floor. That is not a realistic fill -- it is the arithmetic LOWER BOUND on what a
    US equity leg can cost, the number you would get if every order always rested at a
    one-cent-wide touch. It exists so the verdict can be shown not to depend on the adversity
    judgement: if a formula loses even at the lower bound, no execution skill rescues it."""
    doc = json.loads((CACHE / "spread_proxy.json").read_text())
    field = "half_tick_bp" if model == "tickfloor" else "headline_half_bp"
    hs = np.full(P.S, 2.5)
    for j, s in enumerate(P.syms):
        row = doc["symbols"].get(s.replace(".", "_")) or doc["symbols"].get(s)
        if row:
            hs[j] = row[field]
    scr = json.loads((CACHE / "borrow_screen.json").read_text())
    unshortable = np.zeros(P.S, dtype=bool)
    unknown = np.zeros(P.S, dtype=bool)
    for j, s in enumerate(P.syms):
        row = scr.get(s) or scr.get(s.replace("_", "."))
        if row is None or "error" in row:
            unknown[j] = True
        elif row.get("shortable") is False:
            unshortable[j] = True
    return hs, unshortable, unknown, doc["provenance"]


def evaluate(P, W, mask, hs_bp, overnight, scale_bp=1.0):
    """Return (daily net pnl over the masked days, diagnostics)."""
    W = np.where(np.isfinite(W), W, 0.0)
    W[~P.tradable] = 0.0
    if not overnight:
        W[P.last_bar] = 0.0
    W = _norm(W)
    r = np.where(np.isfinite(P.fwd_ret), P.fwd_ret, 0.0)
    gross = np.einsum("ts,ts->t", W, r)
    # peak RSS matters here: this host has ~4 GB free and a [T,S] float64 is 115 MB, so the
    # turnover difference is built with two temporaries rather than vstack+diff+abs+multiply
    prev = np.empty_like(W)
    prev[0] = 0.0
    prev[1:] = W[:-1]
    dW = np.abs(W - prev, out=prev)
    turn = dW.sum(axis=1)
    spread_cost = (dW @ hs_bp) * scale_bp * 1e-4
    reg_cost = turn * REG_BP_PER_TURNOVER * 1e-4
    borrow = np.zeros(P.T)
    if overnight:
        shortn = np.where(W < 0, -W, 0.0).sum(axis=1)
        gaps = P.day_gap[P.day]
        borrow = np.where(P.last_bar, shortn * BORROW_ANNUAL / 365.0 * gaps, 0.0)
    net = gross - spread_cost - reg_cost - borrow
    d = P.day
    nd = P.n_days
    keep = np.bincount(d, weights=mask.astype(float), minlength=nd) > 0
    def agg(x):
        return np.bincount(d, weights=np.where(mask, x, 0.0), minlength=nd)[keep]
    diag = {
        "daily_turnover": float(agg(turn).mean()),
        "daily_spread_bp": float(agg(spread_cost).mean() * 1e4),
        "daily_borrow_bp": float(agg(borrow).mean() * 1e4),
        "gross": agg(gross),
    }
    return agg(net), diag


def sharpe(x):
    if x.size < 30:
        return float("nan")
    s = x.std(ddof=1)
    if not np.isfinite(s) or s <= 0:
        return float("nan")
    return float(x.mean() / s * np.sqrt(252))


def short_notional_unshortable_share(P, W, mask, unshortable):
    Wm = W[mask]
    neg = np.where(Wm < 0, -Wm, 0.0)
    tot = neg.sum()
    if tot <= 0:
        return 0.0
    return float(neg[:, unshortable].sum() / tot)


# ------------------------------------------------------------------ signal pieces

def _basket_logprice(P, cols, mode, adv_win=BARS_PER_DAY * 20):
    """Weighted log basket price and the per-member weight matrix used to hedge it."""
    L = P.logc[:, cols]
    k = len(cols)
    if mode == "eq":
        w = np.full((P.T, k), 1.0 / k)
    elif mode == "adv":
        dv = P.dvol[:, cols].astype(np.float64)
        m = _roll_mean(dv, adv_win)
        m = _shift(m, 1)
        m = np.where(np.isfinite(m) & (m > 0), m, np.nan)
        tot = np.nansum(m, axis=1, keepdims=True)
        w = np.where(tot > 0, m / np.maximum(tot, 1e-9), 1.0 / k)
        w = np.where(np.isfinite(w), w, 1.0 / k)
    elif mode == "top3":
        dv = _shift(_roll_mean(P.dvol[:, cols].astype(np.float64), adv_win), 1)
        rank = np.argsort(np.argsort(-np.where(np.isfinite(dv), dv, -np.inf), axis=1), axis=1)
        w = np.where(rank < 3, 1.0 / 3.0, 0.0)
    else:
        raise ValueError(mode)
    # A member with no bar in this minute must not silently shrink the basket. Renormalise the
    # weights over the members that ARE quoted, and refuse the bar outright if less than 60 %
    # of the intended weight is present -- for the 33-name SPY proxy, demanding all 33 at once
    # would throw away a tenth of the sample for no gain, and demanding nothing would fabricate
    # a basket that is not the one being hedged.
    ok = np.isfinite(L)
    wok = np.where(ok, w, 0.0)
    tot = wok.sum(axis=1, keepdims=True)
    good = tot[:, 0] >= 0.60
    w = np.where(tot > 1e-9, wok / np.maximum(tot, 1e-9), 0.0)
    lb = (w * np.where(ok, L, 0.0)).sum(axis=1)
    lb = np.where(good, lb, np.nan)
    w = np.where(good[:, None], w, np.nan)
    return lb, w


def _rolling_beta(ry, rx, n, lo=0.2, hi=3.0):
    ry2 = ry[:, None] if ry.ndim == 1 else ry
    rx2 = rx[:, None] if rx.ndim == 1 else rx
    my = _roll_mean(ry2, n)
    mx = _roll_mean(rx2, n)
    cxy = _roll_mean(ry2 * rx2, n)
    vx = _roll_mean(rx2 * rx2, n)
    b = (cxy - my * mx) / np.maximum(vx - mx * mx, 1e-18)
    return np.clip(b, lo, hi)[:, 0]


def _entry(z, cfg, day, overnight=False):
    """Turn a standardised deviation into a target, applying this config's entry rule."""
    mode = cfg.get("entry", "linear")
    z = np.clip(_shift(z, 1), -3.0, 3.0)
    if mode == "linear":
        s = -z
    elif mode == "thr":
        s = np.where(np.abs(z) >= cfg["thr"], -z, 0.0)
    elif mode == "band":
        s = _hysteresis(z, day, cfg["entry_z"], cfg["exit_z"], overnight=overnight)
    else:
        raise ValueError(mode)
    return np.where(np.isfinite(s), s, 0.0)


# ------------------------------------------------------------------ builders

def build(P, cfg):
    k = cfg["kind"]
    T, S = P.T, P.S
    W = np.zeros((T, S))

    # ---------------- N: ETF vs its own component sum (the free iNAV stand-in)
    if k == "synth":
        used = 0
        for etf, members in SYNTH_BASKETS.items():
            ie = P.col(etf)
            cols = P.cols(members)
            if ie is None or len(cols) < 2:
                continue
            lb, wts = _basket_logprice(P, cols, cfg.get("weights", "eq"))
            le = P.logc[:, ie]
            spread_mode = cfg.get("spread", "level")
            if spread_mode == "level":
                sp = le - lb
                if cfg.get("ewma"):
                    mu = _ewma(sp[:, None], cfg["ewma"])[:, 0]
                    dev = sp - mu
                    sd = np.sqrt(_ewma((dev * dev)[:, None], cfg["ewma"])[:, 0])
                else:
                    mu, sd = _nan_roll(sp[:, None], cfg["win"])
                    mu, sd = mu[:, 0], sd[:, 0]
                    dev = sp - mu
                z = np.where(sd > 1e-12, dev / sd, np.nan)
                hedge = wts
            elif spread_mode == "resid":
                rm = P.r[:, cols]
                okr = np.isfinite(rm)
                wr = np.where(okr & np.isfinite(wts), wts, 0.0)
                tot = wr.sum(axis=1, keepdims=True)
                rb = np.where(tot[:, 0] >= 0.60,
                              (np.where(tot > 1e-9, wr / np.maximum(tot, 1e-9), 0.0)
                               * np.where(okr, rm, 0.0)).sum(axis=1), np.nan)
                re = P.r[:, ie]
                beta = _shift(_rolling_beta(re, rb, cfg.get("betawin", BARS_PER_DAY * 20)), 1)
                resid = re - beta * rb
                cum = np.cumsum(np.where(np.isfinite(resid), resid, 0.0))
                mu, sd = _nan_roll(cum[:, None], cfg["win"])
                z = ((cum - mu[:, 0]) / sd[:, 0])
                hedge = wts * beta[:, None]
            elif spread_mode == "dayanchor":
                # deviation measured from THIS SESSION's open only: no drift, no dividend step,
                # and the anchor is a price everyone saw
                anchor = np.maximum.accumulate(np.where(P.first_bar, np.arange(T), 0))
                sp = (le - lb) - (le - lb)[anchor]
                sd = _shift(_nan_roll(np.abs(sp)[:, None], BARS_PER_DAY * 20)[0][:, 0], 1)
                z = np.where(sd > 1e-12, sp / (1.2533 * sd), np.nan)
                hedge = wts
            else:
                raise ValueError(spread_mode)
            if cfg.get("hlgate"):
                mu2, _ = _nan_roll((le - lb)[:, None], cfg["win"])
                dev2 = ((le - lb) - mu2[:, 0])[:, None]
                c1 = _roll_mean(dev2 * _shift(dev2, 1), cfg["win"])[:, 0]
                c0 = _roll_mean(_shift(dev2, 1) ** 2, cfg["win"])[:, 0]
                phi = np.clip(c1 / np.maximum(c0, 1e-24), -0.99, 0.999)
                with np.errstate(divide="ignore", invalid="ignore"):
                    hl = np.log(0.5) / np.log(np.maximum(phi, 1e-6))
                z = np.where(_shift(hl, 1) <= cfg["hlgate"], z, np.nan)
            s = _entry(z, cfg, P.day)
            if cfg.get("min_slot"):
                s = np.where(P.slot >= cfg["min_slot"], s, 0.0)
            # A band rule HOLDS its state through a bar whose basket is unquotable. Holding the
            # ETF leg while the hedge legs silently become zero is a naked directional position
            # wearing a market-neutral label, so the whole pair stands down for that bar.
            hedge = _shift(hedge, 1)
            valid = np.isfinite(hedge).all(axis=1)
            s = np.where(valid, s, 0.0)
            hedge = np.where(np.isfinite(hedge), hedge, 0.0)
            W[:, ie] += s
            W[:, cols] -= s[:, None] * hedge
            used += 1
        return _norm(W) if used else None

    # ---------------- O: overlapping-holdings pairs, rolling hedge ratio
    if k == "overlap":
        used = 0
        n = cfg["win"]
        for a, b in OVERLAP_PAIRS:
            ia, ib = P.col(a), P.col(b)
            if ia is None or ib is None:
                continue
            if cfg.get("hedge", "beta") == "beta":
                beta = _shift(_rolling_beta(P.r[:, ia], P.r[:, ib],
                                            cfg.get("betawin", BARS_PER_DAY * 20)), 1)
                resid = P.r[:, ia] - beta * P.r[:, ib]
                cum = np.cumsum(np.where(np.isfinite(resid), resid, 0.0))
                if cfg.get("spread") == "dayanchor":
                    anchor = np.maximum.accumulate(np.where(P.first_bar, np.arange(T), 0))
                    sp = cum - cum[anchor]
                    sd = _shift(_nan_roll(np.abs(sp)[:, None], BARS_PER_DAY * 20)[0][:, 0], 1)
                    z = np.where(sd > 1e-12, sp / (1.2533 * sd), np.nan)
                else:
                    mu, sd = _nan_roll(cum[:, None], n)
                    z = (cum - mu[:, 0]) / sd[:, 0]
                hb = beta
            else:
                sp = P.logc[:, ia] - P.logc[:, ib]
                mu, sd = _nan_roll(sp[:, None], n)
                z = (sp - mu[:, 0]) / sd[:, 0]
                hb = np.ones(T)
            s = _entry(z, cfg, P.day)
            if cfg.get("riskparity"):
                inv = 1.0 / np.maximum(_shift(sd[:, 0] if sd.ndim > 1 else sd, 1), 1e-5)
                s = s * np.where(np.isfinite(inv), inv, 0.0)
            if cfg.get("hlgate"):
                d1 = _shift(z, 1)
                c1 = _roll_mean((z * d1)[:, None], n)[:, 0]
                c0 = _roll_mean((d1 * d1)[:, None], n)[:, 0]
                phi = np.clip(c1 / np.maximum(c0, 1e-24), -0.99, 0.999)
                with np.errstate(divide="ignore", invalid="ignore"):
                    hl = np.log(0.5) / np.log(np.maximum(phi, 1e-6))
                s = np.where(_shift(hl, 1) <= cfg["hlgate"], s, 0.0)
            hb = _shift(hb, 1)
            s = np.where(np.isfinite(s) & np.isfinite(hb), s, 0.0)
            W[:, ia] += s
            W[:, ib] -= s * np.where(np.isfinite(hb), hb, 0.0)
            used += 1
        return _norm(W) if used else None

    # ---------------- L: leveraged / inverse
    if k == "lev_drag":
        # short the levered ETP, hold `mult` of the base: a delta-neutral book whose whole
        # return is the daily-reset compounding drag. Held overnight -- the drag accrues there.
        for lev, base, mult in LEVERED:
            il, ib = P.col(lev), P.col(base)
            if il is None or ib is None:
                continue
            W[:, il] += -1.0
            W[:, ib] += mult
        return _norm(W)

    if k == "decay_pair":
        # the same claim with no base leg at all: short BOTH sides of an opposite-signed pair
        for a, b in DECAY_PAIRS:
            ia, ib = P.col(a), P.col(b)
            if ia is None or ib is None:
                continue
            W[:, ia] += -1.0
            W[:, ib] += -1.0
        return _norm(W)

    if k == "lev_beta_resid":
        # NOT the stated multiple: a rolling realised beta of the ETP to its base. When the ETP
        # has drifted from the multiple its issuer promises, that is the tradable deviation.
        n = cfg["win"]
        for lev, base, mult in LEVERED:
            il, ib = P.col(lev), P.col(base)
            if il is None or ib is None:
                continue
            beta = _shift(_rolling_beta(P.r[:, il], P.r[:, ib], cfg.get("betawin", BARS_PER_DAY * 20),
                                        lo=-3.5, hi=3.5), 1)
            resid = P.r[:, il] - beta * P.r[:, ib]
            cum = np.cumsum(np.where(np.isfinite(resid), resid, 0.0))
            mu, sd = _nan_roll(cum[:, None], n)
            z = (cum - mu[:, 0]) / sd[:, 0]
            s = _entry(z, cfg, P.day)
            W[:, il] += s
            W[:, ib] -= s * np.where(np.isfinite(beta), beta, mult)
        return _norm(W)

    if k == "rebal_flow":
        # levered complexes must rebalance IN THE DIRECTION of the day's move at the close.
        # Signal: the session's move measured at `meas_slot`, cross-sectionally demeaned so the
        # book is a relative-value bet on WHICH index gets the flow, not a market bet.
        cols = P.cols(REBAL_UNIVERSE)
        anchor = np.maximum.accumulate(np.where(P.first_bar, np.arange(T), 0))
        move = P.logc[:, cols] - P.logc[anchor][:, cols]
        ms = cfg["meas_slot"]
        sig = np.full(move.shape, np.nan)
        at = P.slot == ms
        sig[at] = move[at]
        sig = _ffill_daily(sig, P.day, np.nan)
        # the move is measured from the CLOSE of bar meas_slot, so the earliest bar it may be
        # traded in is meas_slot+1 -- without this shift the rule buys bar 66 knowing bar 66
        sig = _shift(sig, 1)
        sig = np.where(np.isfinite(sig), sig, 0.0)
        if cfg.get("sign", 1.0) < 0:
            sig = -sig
        Wc = _cross_demean(sig)
        if cfg["slots"] == "lastbar":
            keep = P.last_bar
        else:
            lo, hi = cfg["slots"]
            keep = (P.slot >= lo) & (P.slot < hi)
        Wc[~keep] = 0.0
        W[:, cols] = Wc
        return W

    # ---------------- C: country ETF vs a NAV that stopped updating hours ago
    if k == "stale_nav":
        cols = P.cols(COUNTRY)
        im = P.col("SPY")
        if im is None or len(cols) < 4:
            return None
        beta = np.vstack([_shift(_rolling_beta(P.r[:, c], P.r[:, im],
                                               BARS_PER_DAY * 40, lo=0.0, hi=2.5), 1)
                          for c in cols]).T
        resid = P.r[:, cols] - beta * P.r[:, im][:, None]
        resid = np.where(np.isfinite(resid), resid, 0.0)
        anchor = np.maximum.accumulate(np.where(P.first_bar, np.arange(T), 0))
        cum = np.cumsum(resid, axis=0)
        today = cum - cum[anchor]                # today's US-session residual move
        sig = cfg.get("sign", 1.0) * today
        # normalise by the trailing scale of a full day's residual move
        sd = _shift(_nan_roll(np.abs(today)[:, None][:, 0], BARS_PER_DAY * 40)[0], 1)
        sig = np.where(sd > 1e-12, sig / (1.2533 * sd), 0.0)
        sig = np.clip(_shift(sig, 1), -3, 3)
        Wc = _cross_demean(sig)
        if cfg["slots"] == "lastbar":
            # THE overnight formulation: put the book on at the closing bar's VWAP and take it
            # off at the next open. That is the window in which the local NAV actually updates,
            # so it is the only window in which a stale-NAV claim can be true.
            keep = P.last_bar
        else:
            lo, hi = cfg["slots"]
            keep = (P.slot >= lo) & (P.slot < hi)
        Wc[~keep] = 0.0
        W[:, cols] = Wc
        return W

    if k == "country_xs_rev":
        cols = P.cols(COUNTRY)
        lb = cfg["lb"]
        L = P.logc[:, cols]
        R = np.full(L.shape, np.nan)
        R[lb:] = L[lb:] - L[:-lb]
        straddle = np.zeros(T, dtype=bool)
        straddle[:lb] = True
        straddle[lb:] = P.day[lb:] != P.day[:-lb]
        R[straddle] = np.nan
        W[:, cols] = _cross_demean(-_shift(R, 1))
        return W

    # ---------------- P: the NAV deviation as a SIGNAL, traded ETF-only
    if k == "pd_xs":
        cols = []
        dev = []
        for etf in PD_ETFS:
            ie = P.col(etf)
            mem = P.cols(SYNTH_BASKETS[etf])
            if ie is None or len(mem) < 2:
                continue
            lb, _ = _basket_logprice(P, mem, cfg.get("weights", "eq"))
            sp = P.logc[:, ie] - lb
            mu, sd = _nan_roll(sp[:, None], cfg["win"])
            dev.append((sp - mu[:, 0]) / sd[:, 0])
            cols.append(ie)
        if len(cols) < 4:
            return None
        Z = np.clip(_shift(np.vstack(dev).T, 1), -3, 3)
        if cfg.get("entry") == "band":
            Z = np.vstack([_hysteresis(Z[:, j], P.day, cfg["entry_z"], cfg["exit_z"])
                           for j in range(Z.shape[1])]).T
            W[:, cols] = _cross_demean(Z)
        else:
            W[:, cols] = _cross_demean(-Z)
        return W

    if k == "pd_xs_members":
        # the mirror image: same NAV-deviation signal, but the BOOK is the component baskets.
        # Different instruments, different spreads, same claim -- a real robustness axis.
        W2 = np.zeros((T, S))
        devs, memcols = [], []
        for etf in PD_ETFS:
            ie = P.col(etf)
            mem = P.cols(SYNTH_BASKETS[etf])
            if ie is None or len(mem) < 2:
                continue
            lbp, wts = _basket_logprice(P, mem, "eq")
            sp = P.logc[:, ie] - lbp
            mu, sd = _nan_roll(sp[:, None], cfg["win"])
            devs.append((sp - mu[:, 0]) / sd[:, 0])
            memcols.append((mem, np.where(np.isfinite(_shift(wts, 1)), _shift(wts, 1), 0.0)))
        if len(devs) < 4:
            return None
        Z = np.clip(_shift(np.vstack(devs).T, 1), -3, 3)
        Z = Z - np.nanmean(Z, axis=1, keepdims=True)
        Z = np.where(np.isfinite(Z), Z, 0.0)
        for j, (mem, wts) in enumerate(memcols):
            for q, c in enumerate(mem):
                W2[:, c] += Z[:, j] * wts[:, q]      # ETF rich -> buy its components
        return _norm(W2)

    raise ValueError(f"unknown kind {k}")


# ------------------------------------------------------------------ config grid

def config_list():
    c = []
    a = c.append
    W20 = BARS_PER_DAY * 5      # 390 bars = one trading week
    W60 = BARS_PER_DAY * 15

    # --- N: ETF vs component sum -------------------------------------------------
    a({"name": "N01_synth_eq_lvl_z78", "kind": "synth", "win": 78, "weights": "eq"})
    a({"name": "N02_synth_eq_lvl_z390", "kind": "synth", "win": W20, "weights": "eq"})
    a({"name": "N03_synth_eq_lvl_z1170", "kind": "synth", "win": W60, "weights": "eq"})
    a({"name": "N04_synth_adv_lvl_z390", "kind": "synth", "win": W20, "weights": "adv"})
    a({"name": "N05_synth_top3_lvl_z390", "kind": "synth", "win": W20, "weights": "top3"})
    a({"name": "N06_synth_eq_resid_z390", "kind": "synth", "win": W20, "weights": "eq",
       "spread": "resid"})
    a({"name": "N07_synth_adv_resid_z390", "kind": "synth", "win": W20, "weights": "adv",
       "spread": "resid"})
    a({"name": "N08_synth_eq_dayanchor", "kind": "synth", "win": W20, "weights": "eq",
       "spread": "dayanchor"})
    a({"name": "N09_synth_eq_lvl_ewma78", "kind": "synth", "win": W20, "weights": "eq",
       "ewma": 78.0})
    a({"name": "N10_synth_eq_band_2.0_0.5", "kind": "synth", "win": W20, "weights": "eq",
       "entry": "band", "entry_z": 2.0, "exit_z": 0.5})
    a({"name": "N11_synth_eq_band_1.5_0.25", "kind": "synth", "win": W20, "weights": "eq",
       "entry": "band", "entry_z": 1.5, "exit_z": 0.25})
    a({"name": "N12_synth_eq_lvl_z390_hold13", "kind": "synth", "win": W20, "weights": "eq",
       "hold": 13})
    a({"name": "N13_synth_eq_lvl_z390_thr1.5", "kind": "synth", "win": W20, "weights": "eq",
       "entry": "thr", "thr": 1.5})
    a({"name": "N14_synth_eq_lvl_z390_hlgate", "kind": "synth", "win": W20, "weights": "eq",
       "hlgate": 40.0})
    a({"name": "N15_synth_eq_lvl_z390_noopen", "kind": "synth", "win": W20, "weights": "eq",
       "min_slot": 3})
    a({"name": "N16_synth_adv_resid_band", "kind": "synth", "win": W20, "weights": "adv",
       "spread": "resid", "entry": "band", "entry_z": 2.0, "exit_z": 0.5})
    a({"name": "N17_synth_top3_resid_z390", "kind": "synth", "win": W20, "weights": "top3",
       "spread": "resid"})
    a({"name": "N18_synth_eq_dayanchor_hold13", "kind": "synth", "win": W20, "weights": "eq",
       "spread": "dayanchor", "hold": 13})

    # --- O: overlapping-holdings pairs -------------------------------------------
    a({"name": "O01_overlap_beta_z78", "kind": "overlap", "win": 78})
    a({"name": "O02_overlap_beta_z390", "kind": "overlap", "win": W20})
    a({"name": "O03_overlap_beta_z1170", "kind": "overlap", "win": W60})
    a({"name": "O04_overlap_unit_lvl_z390", "kind": "overlap", "win": W20, "hedge": "unit"})
    a({"name": "O05_overlap_beta_band_2.0_0.5", "kind": "overlap", "win": W20,
       "entry": "band", "entry_z": 2.0, "exit_z": 0.5})
    a({"name": "O06_overlap_beta_band_1.5_0.25", "kind": "overlap", "win": W20,
       "entry": "band", "entry_z": 1.5, "exit_z": 0.25})
    a({"name": "O07_overlap_beta_z390_hold13", "kind": "overlap", "win": W20, "hold": 13})
    a({"name": "O08_overlap_beta_dayanchor", "kind": "overlap", "win": W20,
       "spread": "dayanchor"})
    a({"name": "O09_overlap_beta_z390_riskparity", "kind": "overlap", "win": W20,
       "riskparity": True})
    a({"name": "O10_overlap_beta_z390_hlgate", "kind": "overlap", "win": W20, "hlgate": 40.0})
    a({"name": "O11_overlap_beta_z390_thr1.5", "kind": "overlap", "win": W20,
       "entry": "thr", "thr": 1.5})
    a({"name": "O12_overlap_beta_z390_bw3900", "kind": "overlap", "win": W20,
       "betawin": BARS_PER_DAY * 50})

    # --- L: leveraged / inverse ---------------------------------------------------
    a({"name": "L01_lev_drag_carry", "kind": "lev_drag", "overnight": True})
    a({"name": "L02_decay_pair_short_both", "kind": "decay_pair", "overnight": True})
    a({"name": "L03_lev_beta_resid_z390", "kind": "lev_beta_resid", "win": W20})
    a({"name": "L04_lev_beta_resid_band", "kind": "lev_beta_resid", "win": W20,
       "entry": "band", "entry_z": 2.0, "exit_z": 0.5})
    a({"name": "L05_rebal_flow_cont_last30", "kind": "rebal_flow", "meas_slot": 66,
       "slots": (66, 78), "sign": 1.0})
    a({"name": "L06_rebal_flow_fade_last30", "kind": "rebal_flow", "meas_slot": 66,
       "slots": (66, 78), "sign": -1.0})
    a({"name": "L07_rebal_flow_fade_nextopen", "kind": "rebal_flow", "meas_slot": 77,
       "slots": (0, 6), "sign": -1.0})
    a({"name": "L08_rebal_flow_fade_overnight", "kind": "rebal_flow", "meas_slot": 72,
       "slots": "lastbar", "sign": -1.0, "overnight": True})
    a({"name": "L09_rebal_flow_cont_overnight", "kind": "rebal_flow", "meas_slot": 72,
       "slots": "lastbar", "sign": 1.0, "overnight": True})

    # --- C: country / stale NAV ---------------------------------------------------
    a({"name": "C01_stalenav_cont_close", "kind": "stale_nav", "slots": (72, 78), "sign": 1.0})
    a({"name": "C02_stalenav_fade_close", "kind": "stale_nav", "slots": (72, 78), "sign": -1.0})
    a({"name": "C03_stalenav_cont_overnight", "kind": "stale_nav", "slots": "lastbar",
       "sign": 1.0, "overnight": True})
    a({"name": "C04_stalenav_fade_overnight", "kind": "stale_nav", "slots": "lastbar",
       "sign": -1.0, "overnight": True})
    a({"name": "C05_stalenav_cont_nextopen", "kind": "stale_nav", "slots": (0, 6), "sign": 1.0})
    a({"name": "C06_country_xs_rev_lb6", "kind": "country_xs_rev", "lb": 6})
    a({"name": "C07_country_xs_rev_lb39", "kind": "country_xs_rev", "lb": 39})

    # --- P: premium/discount as a signal, ETF-only or component-only book ---------
    a({"name": "P01_pd_xs_etfonly_z390", "kind": "pd_xs", "win": W20})
    a({"name": "P02_pd_xs_etfonly_z1170", "kind": "pd_xs", "win": W60})
    a({"name": "P03_pd_xs_etfonly_band", "kind": "pd_xs", "win": W20, "entry": "band",
       "entry_z": 2.0, "exit_z": 0.5})
    a({"name": "P04_pd_xs_etfonly_hold13", "kind": "pd_xs", "win": W20, "hold": 13})
    a({"name": "P05_pd_xs_members_z390", "kind": "pd_xs_members", "win": W20})
    return c


# ------------------------------------------------------------------ driver

def run(stage, only=None, cost_model="headline"):
    P = Panel()
    hs_bp, unshortable, unknown, prov = load_costs(P, cost_model)
    lo, hi = DESIGN if stage == "design" else HELDOUT
    mask = (P.daykey >= lo) & (P.daykey <= hi)
    print(f"stage={stage} {lo}..{hi} bars={mask.sum()} days={len(set(P.day[mask]))} "
          f"syms={P.S}", flush=True)
    cfgs = config_list()
    if only:
        keep = set(only.split(","))
        cfgs = [c for c in cfgs if c["name"] in keep]
    rows, daily, daily_gross = [], {}, {}
    for i, cfg in enumerate(cfgs):
        try:
            W = build(P, cfg)
        except Exception as exc:                            # noqa: BLE001
            print(f"  {cfg['name']} BUILD FAILED {exc!r}", flush=True)
            continue
        if W is None:
            print(f"  {cfg['name']} SKIPPED (missing symbols)", flush=True)
            continue
        if cfg.get("hold"):
            W = _norm(_hold_every(W, P.day, P.slot, cfg["hold"]))
        overnight = bool(cfg.get("overnight"))
        net, diag = evaluate(P, W, mask, hs_bp, overnight)
        row = {"name": cfg["name"], "kind": cfg["kind"], "overnight": overnight,
               "sharpe_net": sharpe(net),
               "ann_ret": float(net.mean() * 252), "ann_vol": float(net.std(ddof=1) * np.sqrt(252)),
               "n_days": int(net.size),
               "daily_turnover": diag["daily_turnover"],
               "daily_spread_bp": diag["daily_spread_bp"],
               "daily_borrow_bp": diag["daily_borrow_bp"],
               "sharpe_gross": sharpe(diag["gross"]),
               "unshortable_short_share": short_notional_unshortable_share(P, W, mask, unshortable)}
        for bp in FLAT_RUNGS_BP:
            flat = np.full(P.S, bp)
            n2, _ = evaluate(P, W, mask, flat, overnight)
            row[f"sharpe_flat{bp}bp"] = sharpe(n2)
        daily[cfg["name"]] = net
        daily_gross[cfg["name"]] = diag["gross"]
        rows.append(row)
        print(f"  [{i+1}/{len(cfgs)}] {cfg['name']:34s} gross={row['sharpe_gross']:+.2f} "
              f"net={row['sharpe_net']:+.2f} turn/d={row['daily_turnover']:.2f} "
              f"spread={row['daily_spread_bp']:.1f}bp/d unshort={row['unshortable_short_share']:.0%}",
              flush=True)
        del W
    return P, rows, daily, daily_gross, prov


def block_bootstrap_max(daily, n_boot=800, block=5, seed=20260820):
    names = list(daily)
    M = np.vstack([daily[n] for n in names])
    M = M - M.mean(axis=1, keepdims=True)
    C, D = M.shape
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(D / block))
    out = np.empty(n_boot)
    for b in range(n_boot):
        starts = rng.integers(0, D, size=nb)
        idx = (starts[:, None] + np.arange(block)[None, :]).ravel()[:D] % D
        R = M[:, idx]
        s = R.mean(axis=1) / np.maximum(R.std(axis=1, ddof=1), 1e-18) * np.sqrt(252)
        out[b] = np.nanmax(s)
    return out


def dist(rows, key):
    v = np.array([r[key] for r in rows if np.isfinite(r.get(key, np.nan))])
    if v.size == 0:
        return None
    return {"n": int(v.size), "min": float(v.min()), "p10": float(np.percentile(v, 10)),
            "p25": float(np.percentile(v, 25)), "median": float(np.median(v)),
            "p75": float(np.percentile(v, 75)), "p90": float(np.percentile(v, 90)),
            "max": float(v.max()), "mean": float(v.mean()),
            "sd": float(v.std(ddof=1)) if v.size > 1 else 0.0,
            "n_positive": int((v > 0).sum())}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["design", "heldout"], required=True)
    ap.add_argument("--only", default=None)
    ap.add_argument("--cost", choices=["headline", "tickfloor"], default="headline",
                    help="tickfloor = raw half-tick lower bound, a SENSITIVITY rung, never the headline")
    args = ap.parse_args()
    if args.stage == "heldout" and not args.only:
        raise SystemExit("heldout requires --only with the FROZEN shortlist")

    P, rows, daily, daily_gross, prov = run(args.stage, args.only, args.cost)
    rows.sort(key=lambda r: -(r["sharpe_net"] if np.isfinite(r["sharpe_net"]) else -9))
    payload = {
        "key": KEY,
        "stage": args.stage,
        "window": list(DESIGN if args.stage == "design" else HELDOUT),
        "n_configs": len(rows),
        "cost_model": {
            "spread": "per-symbol half-spread, both legs, from spread_proxy.json",
            "spread_provenance": prov,
            "regulatory_bp_per_turnover": REG_BP_PER_TURNOVER,
            "borrow_annual": BORROW_ANNUAL,
            "borrow_provenance": "B22G etb_general_collateral median 0.33 %/yr, charged on "
                                 "SHORT notional per calendar day, for overnight configs only",
            "flat_sensitivity_rungs_bp": list(FLAT_RUNGS_BP),
        },
        "execution": "signal from closes through t-1, fill at bar-t VWAP, earn vwap[t+1]/vwap[t]-1",
        "results": rows,
        "distribution": {k: dist(rows, k) for k in
                         ("sharpe_gross", "sharpe_net", "sharpe_flat1.0bp",
                          "sharpe_flat2.0bp", "sharpe_flat2.5bp")},
    }
    if args.stage == "design" and len(daily) > 1:
        mx = block_bootstrap_max(daily)
        mg = block_bootstrap_max(daily_gross)
        n = len(rows)
        yrs = rows[0]["n_days"] / 252.0
        payload["noise_bar"] = {
            "n_formulas": n,
            "naive_sqrt_2lnN_in_sharpe_units": float(np.sqrt(2 * np.log(max(n, 2))) / np.sqrt(yrs)),
            "naive_note": "sqrt(2 ln N) is in SE units; one SE of an annualised Sharpe over "
                          f"{yrs:.2f} years is 1/sqrt(yrs), so the bar in Sharpe units is that "
                          "quantity divided by sqrt(years).",
            "bootstrap": {
                "method": "stationary block bootstrap (block=5 days) of DEMEANED daily NET pnl, "
                          "same day indices across every config so cross-config correlation is kept",
                "n_boot": int(mx.size), "mean": float(mx.mean()),
                "p50": float(np.percentile(mx, 50)), "p90": float(np.percentile(mx, 90)),
                "p95": float(np.percentile(mx, 95)), "p99": float(np.percentile(mx, 99)),
            },
            "bootstrap_gross": {"mean": float(mg.mean()), "p95": float(np.percentile(mg, 95))},
        }
        if args.cost == "headline":
            np.savez_compressed(CACHE / "deepmine_design_daily.npz", **daily)
    payload["cost_model"]["model"] = args.cost
    suffix = "" if args.cost == "headline" else f"_{args.cost}"
    out = OUT / f"DEEPMINE_{KEY}_{args.stage}{suffix}.json"
    out.write_text(json.dumps(payload, indent=1))
    print("wrote", out, flush=True)


if __name__ == "__main__":
    main()
