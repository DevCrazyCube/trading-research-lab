#!/usr/bin/env python3
"""D0821 SEASONALITY-WITH-STRUCTURAL-MECHANISM: shared data + evaluation engine.

Every formula in this round must tie to a MECHANICAL FLOW (money that a fiduciary,
a plan document, a tax rule, or an index rulebook OBLIGES someone to move on a known
date), not to a bare calendar date. The engine below is deliberately dumb: it turns a
weight schedule into a net-of-cost daily return series, charges turnover per side, and
splits design/held-out at a date fixed BEFORE any formula was scored.
"""
from __future__ import annotations

import gzip
import json
import os
import numpy as np

ROOT = "/home/anont/meme"
CAL = os.path.join(ROOT, "research/data/calendar_cache")
PANEL_NPZ = os.path.join(ROOT, "research/data/inv3_cache/panel.npz")
CORPACT = os.path.join(ROOT, "research/data/t3_cache/corporate_actions.json.gz")

# ---------------------------------------------------------------- cost model
# Anchors, all from measurements already on disk in this repo:
#   M0_AUCTION_FILLS.json, tier A_rank_1_50 -> close half-spread median 0.90 bp,
#   mean 1.34 bp.  Mega-cap ETFs (SPY/QQQ/IWM/TLT/IEF/LQD/HYG) sit at or inside
#   that tier, second-tier ETFs (RSP/MDY/OEF/sector SPDRs) outside it.
#   Individual equities: the 3 bp/side figure this programme has used as its kill
#   bar throughout (INVENT_R3, FORMULA_SWEEP).
COST_BP = {
    "mega_etf": 1.0,      # SPY QQQ IWM DIA TLT IEF SHY LQD HYG AGG GLD EFA EEM
    "second_etf": 2.0,    # RSP MDY OEF XLx TIP VNQ
    "stock": 3.0,
}
STRESS_MULT = 2.0  # the adverse rung reported next to every headline number

MEGA = {"SPY", "QQQ", "IWM", "DIA", "TLT", "IEF", "SHY", "LQD", "HYG", "AGG",
        "GLD", "EFA", "EEM", "SLV"}


def etf_cost_bp(sym: str) -> float:
    return COST_BP["mega_etf"] if sym in MEGA else COST_BP["second_etf"]


# ---------------------------------------------------------------- ETF loading
def load_etf(sym: str):
    """-> (dates list[str], close np.float64, adjclose np.float64, volume)."""
    rows = json.load(open(os.path.join(CAL, sym + ".json")))["rows"]
    d = [r[0] for r in rows]
    c = np.array([r[4] for r in rows], dtype=np.float64)
    v = np.array([r[5] for r in rows], dtype=np.float64)
    a = np.array([r[6] for r in rows], dtype=np.float64)
    o = np.array([r[1] for r in rows], dtype=np.float64)
    return d, o, c, a, v


class EtfBook:
    """Aligned total-return and raw-price matrices on a common calendar."""

    def __init__(self, syms, start=None):
        raw = {s: load_etf(s) for s in syms}
        base = raw["SPY"][0]
        if start:
            base = [d for d in base if d >= start]
        self.dates = base
        idx = {d: i for i, d in enumerate(base)}
        n, m = len(base), len(syms)
        self.syms = list(syms)
        self.adj = np.full((m, n), np.nan)
        self.close = np.full((m, n), np.nan)
        self.open = np.full((m, n), np.nan)
        for k, s in enumerate(self.syms):
            d, o, c, a, v = raw[s]
            for t, dd in enumerate(d):
                j = idx.get(dd)
                if j is not None:
                    self.adj[k, j] = a[t]
                    self.close[k, j] = c[t]
                    self.open[k, j] = o[t]
        # total return (adjclose captures distributions AND splits)
        self.ret = np.full((m, n), np.nan)
        self.ret[:, 1:] = self.adj[:, 1:] / self.adj[:, :-1] - 1.0
        # price-only return (distribution shows up as a mechanical drop)
        self.pret = np.full((m, n), np.nan)
        self.pret[:, 1:] = self.close[:, 1:] / self.close[:, :-1] - 1.0
        # implied distribution yield on each date: total return minus price return
        self.distyield = self.ret - self.pret
        self.i = {s: k for k, s in enumerate(self.syms)}

    def r(self, sym):
        return self.ret[self.i[sym]]


# ---------------------------------------------------------------- calendar
def calendar_features(dates):
    """Per-session structural calendar positions.

    tom_idx : session index relative to the month boundary. 0 = LAST session of the
              month, -1 = one before it, +1 = FIRST session of the next month, etc.
    qom_idx : same relative to the quarter boundary (nan if not near one).
    dom     : calendar day of month; midm_idx = session offset from the first
              session on or after the 15th (the semi-monthly payroll date).
    """
    n = len(dates)
    ym = np.array([d[:7] for d in dates])
    yq = np.array([d[:4] + "Q" + str((int(d[5:7]) - 1) // 3) for d in dates])
    last_of_month = np.zeros(n, bool)
    last_of_month[:-1] = ym[1:] != ym[:-1]
    last_of_month[-1] = True
    last_of_q = np.zeros(n, bool)
    last_of_q[:-1] = yq[1:] != yq[:-1]
    last_of_q[-1] = True

    def rel_index(flags):
        out = np.full(n, 999, dtype=np.int64)
        ends = np.where(flags)[0]
        for e in ends:
            for k in range(-8, 9):
                j = e + k
                if 0 <= j < n and abs(k) < abs(out[j]):
                    out[j] = k
        return out

    tom = rel_index(last_of_month)
    qom = rel_index(last_of_q)
    # semi-monthly payroll: first session on/after the 15th
    dom = np.array([int(d[8:10]) for d in dates])
    mid_flag = np.zeros(n, bool)
    for k in range(n):
        if dom[k] >= 15 and (k == 0 or ym[k] != ym[k - 1] or dom[k - 1] < 15):
            mid_flag[k] = True
    mid = rel_index(mid_flag)
    month = np.array([int(d[5:7]) for d in dates])
    year = np.array([int(d[:4]) for d in dates])
    return dict(tom=tom, qom=qom, mid=mid, month=month, year=year,
                last_of_month=last_of_month, last_of_q=last_of_q, ym=ym)


# ---------------------------------------------------------------- vol scaling
def trailing_vol(ret, win=60, floor=0.003):
    """Causal trailing stdev; value at t uses returns up to and including t."""
    m, n = ret.shape
    out = np.full((m, n), np.nan)
    r = np.nan_to_num(ret, nan=0.0)
    ok = np.isfinite(ret).astype(np.float64)
    cs = np.cumsum(r, axis=1)
    cs2 = np.cumsum(r * r, axis=1)
    cn = np.cumsum(ok, axis=1)
    for t in range(win, n):
        s = cs[:, t] - cs[:, t - win]
        s2 = cs2[:, t] - cs2[:, t - win]
        c = cn[:, t] - cn[:, t - win]
        c = np.where(c < win * 0.8, np.nan, c)
        var = s2 / c - (s / c) ** 2
        out[:, t] = np.sqrt(np.maximum(var, 0.0))
    return np.maximum(out, floor)


# ---------------------------------------------------------------- engine
class Result:
    __slots__ = ("name", "desc", "gross", "net", "net_stress", "expo", "dates",
                 "turn", "family")

    def __init__(self, name, desc, family, dates, gross, net, net_stress, expo, turn):
        self.name, self.desc, self.family = name, desc, family
        self.dates, self.gross, self.net = dates, gross, net
        self.net_stress, self.expo, self.turn = net_stress, expo, turn


def run_weights(name, desc, family, dates, W, R, cost_bp_per_leg, target_vol=0.10):
    """W: (legs, n) weights DECIDED at close of t; R: (legs, n) close-to-close
    returns realised from t to t+1 (i.e. R[:, t+1]).  Returns a Result."""
    W = np.nan_to_num(W, nan=0.0)
    R = np.nan_to_num(R, nan=0.0)
    n = W.shape[1]
    pnl = np.zeros(n)
    pnl[1:] = np.sum(W[:, :-1] * R[:, 1:], axis=0)
    dW = np.zeros_like(W)
    dW[:, 0] = np.abs(W[:, 0])
    dW[:, 1:] = np.abs(W[:, 1:] - W[:, :-1])
    cb = np.array(cost_bp_per_leg, dtype=np.float64).reshape(-1, 1) * 1e-4
    cost = np.zeros(n)
    cost[1:] = np.sum(dW[:, :-1] * cb, axis=0)   # cost paid when position established
    gross = pnl
    net = pnl - cost
    net_s = pnl - STRESS_MULT * cost
    expo = np.sum(np.abs(W), axis=0)
    # rescale everything to a common target vol so Sharpes are comparable and
    # position sizes are honest (scaling is a constant, it cannot create Sharpe)
    sd = np.std(gross[gross != 0]) if np.any(gross != 0) else 1.0
    return Result(name, desc, family, dates, gross, net, net_s, expo,
                  float(np.sum(dW)))


def stats(series, dates, lo, hi, ann=252):
    m = np.array([(d >= lo) and (d < hi) for d in dates])
    x = series[m]
    if x.size < 30:
        return dict(n=int(x.size), sharpe=float("nan"), t=float("nan"),
                    mean_bp=float("nan"), hit=float("nan"), years=0.0)
    sd = x.std(ddof=1)
    yrs = x.size / ann
    sh = (x.mean() / sd) * np.sqrt(ann) if sd > 0 else 0.0
    nz = x[x != 0]
    return dict(n=int(x.size), n_active=int(nz.size), sharpe=float(sh),
                t=float(sh * np.sqrt(yrs)), years=float(yrs),
                mean_bp=float(x.mean() * 1e4),
                mean_active_bp=float(nz.mean() * 1e4) if nz.size else float("nan"),
                hit=float((nz > 0).mean()) if nz.size else float("nan"),
                total=float(x.sum()))


def block_bootstrap_p(series, dates, lo, hi, nrep=4000, block=21, seed=0):
    """Sign-flip on non-overlapping blocks: p(|t| >= observed) under a zero-mean null
    that keeps the series' own autocorrelation and its activity calendar."""
    m = np.array([(d >= lo) and (d < hi) for d in dates])
    x = series[m]
    if x.size < 60:
        return float("nan")
    nb = x.size // block
    xx = x[: nb * block].reshape(nb, block)
    obs = abs(x.mean() / (x.std(ddof=1) / np.sqrt(x.size)))
    rng = np.random.default_rng(seed)
    s = rng.choice([-1.0, 1.0], size=(nrep, nb))
    sim = (s[:, :, None] * xx[None, :, :]).reshape(nrep, -1)
    t = np.abs(sim.mean(1) / (sim.std(1, ddof=1) / np.sqrt(sim.shape[1])))
    return float((t >= obs).mean())
