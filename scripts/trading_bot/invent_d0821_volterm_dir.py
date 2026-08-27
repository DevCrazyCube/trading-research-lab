#!/usr/bin/env python3
"""
INVENT D0821 -- theme: TERM STRUCTURE OF VOLATILITY as a DIRECTIONAL / TIMING
signal for EQUITY.

WHAT MAKES THIS DIFFERENT FROM WHAT IS ALREADY DEAD
---------------------------------------------------
* NOT VRP harvesting (dead).  Nothing here is short vol.
* NOT the volatility-ETP roll sweep of 2026-08-20 (NEWTERR_volatility_etp_term_
  structure, 39 formulas, NOISE): every one of those traded SVXY/VIXY/VIXM/UVXY,
  i.e. the tradable leg WAS the vol curve.  Here the vol curve is only the
  SIGNAL and every tradable leg is plain equity (SPY / QQQ / IWM).
* NOT a regime conditioner or gate on an alive basket leg.  Round 3's meta-result
  (0/107 gates survived, gating is harmful) is respected: no formula below
  multiplies an existing alive leg by a vol-curve condition.  Every formula is a
  standalone directional book in equity whose only input is the vol curve.
* NOT the VIX9D/VIX3M "gamma-sign proxy" of the dealer-positioning theme (dead):
  that used a curve sign as a proxy for dealer gamma and traded intraday
  momentum.  A3/D3 here are capitulation-reversal, opposite mechanism and sign,
  and the headline legs are close-to-close.

MECHANISMS (each formula carries one, and an A-PRIORI SIGN; the search is NOT
sign-agnostic and every formula is scored exactly as written)

  M1 PANIC IMPULSE.  Near-dated implied vol is bought by hedgers who are forced
     to buy it -- risk limits, VaR budgets, mandate triggers -- not because they
     forecast anything.  That demand hits the front of the curve first, flattens
     or inverts it, and is mechanically unwound.  Equity is cheap while the
     forced buyer is paying up.  => long equity.
  M2 CALM SUPPLY.  A steep, steepening curve means the front is being sold and
     dealers are accumulating long gamma, which damps realised moves.  A market
     whose realised vol is being suppressed drifts up.  => long equity.
  M3 REPRICING LAG.  When realised vol runs above implied, options are
     underpriced relative to what is actually happening; the catch-up repricing
     is accompanied by further de-risking.  => short equity.
  M4 CONVEXITY BID.  VVIX rich to VIX means somebody is paying up for crash
     convexity specifically.  Same forced-hedger logic as M1, one derivative up.

DATA (all free, all cached, no network call in this script)
  research/data/volterm_cache/raw   ^VIX ^VIX9D ^VIX3M ^VIX6M ^VVIX SPY ^GSPC
  research/data/volts_cache/raw     QQQ IWM ^VXN ^VXD ^SKEW
  Yahoo chart API v8, keyless.  ^RVX is 404 on that surface and is not used.

WINDOWS
  panel   20110103..(last cached day)   -- ^VIX9D's first print bounds it
  design  20110103..20191231
  holdout 20200101..now                 -- NOT read until the design pass is
                                           frozen and written to disk

LAG SEMANTICS
  lag0 (HEADLINE): the vol indices are published continuously 09:30-16:15 ET, so
        a 15:55 read is a real, executable input to a 16:00 MOC fill.  Signal
        from close t, filled MOC at close t, earns t -> t+1.
  lag1 (DECAY TEST): one full extra day of delay.  A one-day mean-reversion
        signal is not required to survive lag1 -- but the ratio is reported,
        and a formula whose lag1 is BETTER than its lag0 is flagged as suspect.
  For the overnight leg the fill is MOC at close t and MOO at open t+1, i.e. the
  same 15:55 read; the intraday leg is MOO at open t+1 to MOC at close t+1 and
  therefore carries an extra overnight of delay by construction.

COSTS  per side, in bp of notional, charged on entry AND exit (the T6 correction)
  SPY 1.0, QQQ 1.0, IWM 1.5 at the close; +0.5 bp on any open (MOO) fill.
  Session legs (overnight / intraday) round-trip EVERY day, so they are charged
  on |W| every day, not on |dW|.  Borrow accrues on any negative weight.
  A survivor gets a cost ladder at 0.5x / 1x / 2x.

USAGE
  python3 scripts/trading_bot/invent_d0821_volterm_dir.py selftest
  python3 scripts/trading_bot/invent_d0821_volterm_dir.py design
  python3 scripts/trading_bot/invent_d0821_volterm_dir.py holdout
"""
from __future__ import annotations

import argparse
import datetime
import json
import math
import pathlib
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[2]
RAW1 = ROOT / "research" / "data" / "volterm_cache" / "raw"
RAW2 = ROOT / "research" / "data" / "volts_cache" / "raw"
OUT = ROOT / "research" / "trading_bot"
TAG = "INVENT_D0821_volterm_dir"

PANEL_START = 20110103
DESIGN_START, DESIGN_END = 20110103, 20191231
HOLD_START, HOLD_END = 20200101, 20991231
ANN = 252.0
ZWIN = 252
CLIP = 2.0

# tradable legs.  "c2c" = close-to-close, cost on |dW|.
#                 "on"  = close t -> open t+1, cost on |W| every day (2 sides).
#                 "id"  = open t+1 -> close t+1, cost on |W| every day (2 sides).
LEGS = {
    "SPY":     ("c2c", 1.0, 0.003),
    "QQQ":     ("c2c", 1.0, 0.003),
    "IWM":     ("c2c", 1.5, 0.005),
    "TLT":     ("c2c", 2.0, 0.003),
    "SPY_ON":  ("on",  1.5, 0.003),   # 1.0 close + 0.5 open
    "SPY_ID":  ("id",  1.5, 0.003),
}
ASSETS = list(LEGS)
AIDX = {a: i for i, a in enumerate(ASSETS)}
K = len(ASSETS)

SPLICE_GUARD = 0.75   # |daily log return| above this is a bad splice, not a day


# --------------------------------------------------------------------- loaders
def _load(sym: str):
    for base in (RAW1, RAW2):
        p = base / (sym + ".json")
        if p.exists():
            break
    else:
        raise FileNotFoundError(sym)
    d = json.loads(p.read_text())["chart"]["result"][0]
    ts = d["timestamp"]
    q = d["indicators"]["quote"][0]
    adj = d["indicators"].get("adjclose")

    def arr(x):
        return np.array([np.nan if v is None else float(v) for v in x], dtype=float)

    close = arr(q["close"])
    op = arr(q["open"])
    ac = arr(adj[0]["adjclose"]) if adj else close.copy()
    dates = np.array(
        [int(datetime.datetime.fromtimestamp(t, datetime.UTC).strftime("%Y%m%d"))
         for t in ts], dtype=np.int64)
    ok = np.isfinite(close) & (close > 0)
    return dates[ok], op[ok], close[ok], ac[ok]


class Panel:
    """Everything aligned to the SPY trading calendar.  Forward-filled, never
    back-filled.  Adjusted opens are raw opens scaled by the same adjclose/close
    factor, so splits AND dividends land in the overnight leg correctly."""

    def __init__(self, start=PANEL_START):
        sd, so, sc, sa = _load("SPY")
        m = sd >= start
        self.dates = sd[m]
        self.T = len(self.dates)
        self._c, self._a, self._o = {}, {}, {}
        for s in ("SPY", "QQQ", "IWM", "TLT", "^VIX", "^VIX9D", "^VIX3M", "^VIX6M",
                  "^VVIX", "^VXN", "^VXD", "^SKEW", "^GSPC"):
            try:
                d, o, c, a = _load(s)
            except FileNotFoundError:
                continue
            self._c[s] = self._align(d, c)
            self._a[s] = self._align(d, a)
            f = np.where(np.isfinite(c) & (c > 0), a / c, np.nan)
            self._o[s] = self._align(d, o * f)

    def _align(self, d, v):
        out = np.full(self.T, np.nan)
        j = 0
        last = np.nan
        for i, day in enumerate(self.dates):
            while j < len(d) and d[j] <= day:
                if np.isfinite(v[j]):
                    last = v[j]
                j += 1
            out[i] = last          # forward fill only; NaN before first print
        return out

    def lvl(self, s):
        return self._c[s].copy()

    def ret_c2c(self, s):
        a = self._a[s]
        r = np.full(self.T, np.nan)
        r[1:] = a[1:] / a[:-1] - 1.0
        bad = np.abs(np.log1p(np.clip(r, -0.99, None))) > SPLICE_GUARD
        r[bad] = np.nan
        return r

    def ret_on(self, s):
        """close t-1 -> open t, stamped on day t."""
        a, o = self._a[s], self._o[s]
        r = np.full(self.T, np.nan)
        r[1:] = o[1:] / a[:-1] - 1.0
        r[np.abs(r) > 0.35] = np.nan
        return r

    def ret_id(self, s):
        """open t -> close t, stamped on day t."""
        a, o = self._a[s], self._o[s]
        r = np.full(self.T, np.nan)
        r[:] = a / o - 1.0
        r[np.abs(r) > 0.35] = np.nan
        return r

    def lr(self, s):
        r = self.ret_c2c(s)
        return np.log1p(np.clip(r, -0.99, None))


# ------------------------------------------------------------------ primitives
def roll_mean(x, w):
    out = np.full(len(x), np.nan)
    for i in range(w - 1, len(x)):
        s = x[i - w + 1:i + 1]
        if np.isfinite(s).all():
            out[i] = s.mean()
    return out


def roll_std(x, w):
    out = np.full(len(x), np.nan)
    for i in range(w - 1, len(x)):
        s = x[i - w + 1:i + 1]
        if np.isfinite(s).all():
            out[i] = s.std(ddof=1)
    return out


def z(x, w=ZWIN):
    m, s = roll_mean(x, w), roll_std(x, w)
    out = np.full(len(x), np.nan)
    ok = np.isfinite(m) & np.isfinite(s) & (s > 1e-12)
    out[ok] = (x[ok] - m[ok]) / s[ok]
    return out


def d1(x):
    out = np.full(len(x), np.nan)
    out[1:] = x[1:] - x[:-1]
    return out


def dk(x, k):
    out = np.full(len(x), np.nan)
    out[k:] = x[k:] - x[:-k]
    return out


def w_from_z(x):
    """Bounded continuous book: clip(z,±2)/2 so |w| <= 1."""
    zz = z(x)
    return np.nan_to_num(np.clip(zz, -CLIP, CLIP) / CLIP, nan=0.0)


def roll_resid(y, x, w=ZWIN):
    """PIT rolling-OLS residual of y on x (intercept + slope), fit on the
    trailing w observations ENDING AT t-1, evaluated at t.  Strictly causal."""
    out = np.full(len(y), np.nan)
    for i in range(w, len(y)):
        ys, xs = y[i - w:i], x[i - w:i]
        ok = np.isfinite(ys) & np.isfinite(xs)
        if ok.sum() < w // 2 or not (np.isfinite(y[i]) and np.isfinite(x[i])):
            continue
        X = np.column_stack([np.ones(ok.sum()), xs[ok]])
        try:
            b, *_ = np.linalg.lstsq(X, ys[ok], rcond=None)
        except np.linalg.LinAlgError:
            continue
        out[i] = y[i] - (b[0] + b[1] * x[i])
    return out


# ---------------------------------------------------------------------- engine
class Sweep:
    def __init__(self):
        P = self.P = Panel()
        self.T, self.dates = P.T, P.dates
        self.R = np.column_stack([
            P.ret_c2c("SPY"), P.ret_c2c("QQQ"), P.ret_c2c("IWM"),
            P.ret_c2c("TLT"), P.ret_on("SPY"), P.ret_id("SPY"),
        ])
        self.kind = [LEGS[a][0] for a in ASSETS]
        self.cost = np.array([LEGS[a][1] / 1e4 for a in ASSETS])
        self.borrow = np.array([LEGS[a][2] / ANN for a in ASSETS])
        self._signals()

    def _signals(self):
        P = self.P
        self.vix = P.lvl("^VIX")
        self.v9 = P.lvl("^VIX9D")
        self.v3 = P.lvl("^VIX3M")
        self.v6 = P.lvl("^VIX6M")
        self.vvix = P.lvl("^VVIX")
        self.vxn = P.lvl("^VXN")

        def lg(a, b):
            o = np.full(self.T, np.nan)
            ok = np.isfinite(a) & np.isfinite(b) & (a > 0) & (b > 0)
            o[ok] = np.log(a[ok] / b[ok])
            return o

        # positive = upward sloping = contango
        self.s_near = lg(self.vix, self.v9)      # 9d  -> 30d
        self.s_main = lg(self.v3, self.vix)      # 30d -> 93d
        self.s_back = lg(self.v6, self.v3)       # 93d -> 186d
        self.fly = (np.log(self.v9) - 2.0 * np.log(self.vix) + np.log(self.v3))

        lr = P.lr("SPY")
        self.rv5 = roll_std(lr, 5) * math.sqrt(ANN)
        self.rv10 = roll_std(lr, 10) * math.sqrt(ANN)
        self.rv21 = roll_std(lr, 21) * math.sqrt(ANN)
        self.dlvix = d1(np.log(self.vix))
        self.dlrv5 = d1(np.log(np.where(self.rv5 > 1e-6, self.rv5, np.nan)))
        self.rvov = roll_std(self.dlvix, 21) * math.sqrt(ANN)
        self.lvvr = lg(self.vvix, self.vix)
        self.lvxn = lg(self.vxn, self.vix)

    # ---- weight builders
    def blank(self):
        return np.zeros((self.T, K))

    def one(self, sym, series):
        W = self.blank()
        W[:, AIDX[sym]] = np.nan_to_num(series, nan=0.0)
        return W

    def pair(self, longsym, shortsym, u):
        W = self.blank()
        u = np.nan_to_num(u, nan=0.0)
        W[:, AIDX[longsym]] = 0.5 * u
        W[:, AIDX[shortsym]] = -0.5 * u
        return W


def _legs(S: Sweep, W, lag: int):
    """(gross, cost, effective weights) for return rows 1..T-1.

    Return row t is the day-t return of each leg:
      c2c : close t-1 -> close t
      on  : close t-1 -> open t
      id  : open t   -> close t
    W[t] is the book decided from close-t information.  At lag L the book is
    applied to return row t+1+L.  So lag0 = decided at close t, earns the t->t+1
    close-to-close (or the t->t+1 overnight).  The intraday leg at lag0 earns the
    t+1 open->close, which is one extra session of delay by construction.
    """
    Wf = np.where(np.isfinite(S.R), np.nan_to_num(W, nan=0.0), 0.0)
    Weff = np.zeros_like(Wf)
    if lag > 0:
        Weff[lag:] = Wf[:-lag]
    else:
        Weff = Wf
    R = np.nan_to_num(S.R, nan=0.0)
    gross = (Weff[:-1] * R[1:]).sum(axis=1)

    dW = np.abs(np.diff(np.vstack([np.zeros((1, K)), Weff]), axis=0))
    aW = np.abs(Weff)
    per_day = np.zeros_like(aW)
    for j, kd in enumerate(S.kind):
        if kd == "c2c":
            per_day[:, j] = dW[:, j] * S.cost[j]
        else:                      # full round trip every single day
            per_day[:, j] = 2.0 * aW[:, j] * S.cost[j]
    spread = per_day.sum(axis=1)[:-1]
    borrow = np.zeros(S.T)
    for j, kd in enumerate(S.kind):
        if kd == "c2c":
            borrow += np.maximum(-Weff[:, j], 0.0) * S.borrow[j]
        else:                      # a session leg is held a fraction of a day
            borrow += np.maximum(-Weff[:, j], 0.0) * S.borrow[j] * 0.5
    return gross, spread + borrow[:-1], Weff


def _stats(r, yrs):
    r = np.asarray(r, dtype=float)
    n = len(r)
    if n < 100:
        return None
    sd = r.std(ddof=1)
    if sd < 1e-14:
        return None
    sh = r.mean() / sd * math.sqrt(ANN)
    eq = np.cumprod(1.0 + r)
    peak = np.maximum.accumulate(eq)
    srt = np.sort(r)
    k = max(1, int(0.05 * n))
    return {
        "sharpe": float(sh),
        "t_stat": float(sh * math.sqrt(yrs)),
        "ann_ret": float(r.mean() * ANN),
        "ann_vol": float(sd * math.sqrt(ANN)),
        "max_dd": float((eq / peak - 1.0).min()),
        "worst_day": float(srt[0]),
        "cvar5": float(srt[:k].mean()),
        "hit": float((r > 0).mean()),
    }


def evaluate(S: Sweep, W, lo, hi, lag: int, bench=None, cost_mult=1.0):
    gross, cost, Weff = _legs(S, W, lag)
    cost = cost * cost_mult
    dts = S.dates[1:]
    m = (dts >= lo) & (dts <= hi)
    if m.sum() < 250:
        return None
    live = np.abs(Weff[:-1]).sum(axis=1)[m] > 1e-9
    if live.sum() < 200:
        return None
    yrs = float(m.sum()) / ANN
    net = (gross - cost)[m]
    st = _stats(net, yrs)
    if st is None:
        return None
    gs = _stats(gross[m], yrs)
    out = {
        **st,
        "gross_sharpe": gs["sharpe"],
        "cost_drag_annual": float(cost[m].sum() / max(yrs, 1e-9)),
        "n_days": int(m.sum()), "years": round(yrs, 2),
        "frac_days_live": float(live.mean()),
        "avg_gross_exposure": float(np.abs(Weff[:-1]).sum(axis=1)[m].mean()),
        "first": int(dts[m][0]), "last": int(dts[m][-1]),
    }
    if bench is not None:
        b = np.asarray(bench)[m]
        vb = float(b.var(ddof=1))
        beta = float(np.cov(net, b, ddof=1)[0, 1] / vb) if vb > 1e-18 else 0.0
        resid = net - beta * b
        rs = resid.std(ddof=1)
        out["beta_vs_spy"] = beta
        out["alpha_annual"] = float(resid.mean() * ANN)
        out["alpha_t"] = float(resid.mean() / rs * math.sqrt(len(resid))) if rs > 1e-14 else 0.0
    return out


def null_max(S, Ws, lo, hi, lag, B=2000, seed=821):
    """Circular-shift null of the SEARCH STATISTIC actually used: the max over
    formulas of the AS-WRITTEN net Sharpe.  Preserves turnover, the cost line,
    return autocorrelation, cross-leg correlation and the correlation structure
    BETWEEN formulas -- which is exactly what sqrt(2 ln N) does not."""
    rng = np.random.default_rng(seed)
    dts = S.dates[1:]
    m = (dts >= lo) & (dts <= hi)
    n = int(m.sum())
    prepped = []
    for W in Ws:
        _, cost, Weff = _legs(S, W, lag)
        prepped.append((Weff[:-1][m], cost[m]))
    Rn = np.nan_to_num(S.R, nan=0.0)[1:][m]
    maxes = np.empty(B)
    for b in range(B):
        k = int(rng.integers(21, n - 21))
        Rs = np.roll(Rn, k, axis=0)
        best = -9.0
        for Wm, c in prepped:
            r = (Wm * Rs).sum(axis=1) - c
            sd = r.std(ddof=1)
            if sd < 1e-14:
                continue
            sh = r.mean() / sd * math.sqrt(ANN)
            best = max(best, sh)
        maxes[b] = best
    return {"B": B,
            "statistic": "max over all tested formulas of as-written net Sharpe",
            "expected_max_sharpe": float(maxes.mean()),
            "p95_max_sharpe": float(np.percentile(maxes, 95)),
            "p99_max_sharpe": float(np.percentile(maxes, 99)),
            "_draws": maxes}


# -------------------------------------------------------------------- formulas
M1 = ("PANIC IMPULSE: forced hedgers buy near-dated vol on a risk-limit trigger, "
      "flattening or inverting the front of the curve; that demand is "
      "non-informational and unwinds, so equity is cheap while they pay up.")
M2 = ("CALM SUPPLY: a steep / steepening curve means the front is being sold and "
      "dealers accumulate long gamma, damping realised moves; a market whose "
      "realised vol is suppressed drifts up.")
M3 = ("REPRICING LAG: realised running above implied means options are "
      "underpriced against what is actually happening; the catch-up repricing "
      "comes with further de-risking.")
M4 = ("CONVEXITY BID: VVIX rich to VIX means somebody is paying up specifically "
      "for crash convexity -- the same forced-hedger trade, one derivative up.")


def build(S: Sweep):
    F = []

    def add(name, why, sign, W, group):
        F.append({"name": name, "why": why, "a_priori_sign": sign,
                  "group": group, "W": W})

    # ---- A: shape and dynamics of the implied curve -> SPY close-to-close
    add("A1_NEAR_FLATTEN_REV",
        "One-day FLATTENING of the 9d->30d segment. " + M1,
        "long equity after the front flattens", S.one("SPY", w_from_z(-d1(S.s_near))), "A")
    add("A2_MAIN_FLATTEN_REV",
        "One-day flattening of the 30d->93d segment. " + M1,
        "long equity after the belly flattens", S.one("SPY", w_from_z(-d1(S.s_main))), "A")
    add("A3_NEAR_INVERT_BINARY",
        "Front inverted outright (VIX9D above VIX). " + M1,
        "long equity while the front is inverted",
        S.one("SPY", np.where(np.isfinite(S.s_near) & (S.s_near < 0), 1.0, 0.0)), "A")
    add("A4_NEAR_INVERT_DEPTH",
        "Depth of front inversion in its own trailing sigma. " + M1,
        "long equity in proportion to inversion depth",
        S.one("SPY", np.nan_to_num(
            np.clip(-np.where(np.isfinite(S.s_near), S.s_near, 0.0)
                    / np.where(roll_std(S.s_near, ZWIN) > 1e-9,
                               roll_std(S.s_near, ZWIN), np.nan), 0.0, CLIP) / CLIP,
            nan=0.0)), "A")
    add("A5_NEAR_SLOPE_TILT",
        "Level of the 9d->30d slope, continuous. " + M1,
        "long equity when the front is flat/inverted, short when very steep",
        S.one("SPY", -w_from_z(S.s_near)), "A")
    add("A6_BACK_SLOPE_TILT",
        "Level of the 93d->186d slope, continuous. " + M2,
        "long equity when the BACK end is steep",
        S.one("SPY", w_from_z(S.s_back)), "A")
    add("A7_CURVATURE_FLY",
        "9d/30d/93d butterfly: wings rich to the belly means date-specific event "
        "hedging that resolves. " + M1,
        "long equity when the fly is high", S.one("SPY", w_from_z(S.fly)), "A")
    add("A8_NEAR_SLOPE_ACCEL",
        "Second difference of the 9d->30d slope: the front flattening FASTER. " + M1,
        "long equity on accelerating flattening",
        S.one("SPY", w_from_z(-d1(d1(S.s_near)))), "A")
    add("A9_TWIST_NEARFAR",
        "Front moving more than the 6-month point on the day (a twist, not a "
        "parallel shift). " + M1,
        "long equity when the near end jumps relative to the far end",
        S.one("SPY", w_from_z(d1(np.log(S.v9)) - d1(np.log(S.v6)))), "A")
    add("A10_MAIN_STEEPEN_5D",
        "Five-day STEEPENING of the 30d->93d segment. " + M2,
        "long equity while the belly steepens",
        S.one("SPY", w_from_z(dk(S.s_main, 5))), "A")

    # ---- B: realised vs implied dynamics (direction of EQUITY, not vol)
    g21 = S.rv21 - S.vix / 100.0
    add("B1_RVIV_GAP_DIR",
        "21d realised minus 30d implied, in vol points. " + M3,
        "short equity when realised runs above implied",
        S.one("SPY", -w_from_z(g21)), "B")
    add("B2_RVIV_GAP_SHOCK",
        "One-day change in that gap. " + M3,
        "short equity when realised gains on implied",
        S.one("SPY", -w_from_z(d1(g21))), "B")
    g10 = S.rv10 - S.v9 / 100.0
    add("B3_RVIV_NEAR_GAP",
        "10d realised minus 9d implied: the same gap at the front. " + M3,
        "short equity when near realised runs above near implied",
        S.one("SPY", -w_from_z(g10)), "B")
    resid = roll_resid(S.dlvix, S.dlrv5, ZWIN)
    add("B4_IV_OVERSHOOT_RESID",
        "Today's VIX move minus what a PIT rolling regression on the realised-vol "
        "move says it should be: pure implied OVERSHOOT. " + M1,
        "long equity when implied overshoots realised",
        S.one("SPY", w_from_z(resid)), "B")
    rvterm = np.log(np.where((S.rv5 > 1e-6) & (S.rv21 > 1e-6), S.rv5 / S.rv21, np.nan))
    add("B5_RV_TERM_SLOPE",
        "Term structure of REALISED vol, 5d over 21d: the front of the realised "
        "curve inverted is a fresh shock. " + M1,
        "long equity when realised short-horizon vol spikes above its base",
        S.one("SPY", w_from_z(rvterm)), "B")
    mism = S.s_near + rvterm   # s_near<0 is implied inversion; rvterm>0 is realised inversion
    add("B6_IMPL_VS_REAL_CURVE",
        "Implied front curve minus the realised front curve: how much MORE "
        "inverted implied is than realised justifies. " + M1,
        "long equity when implied is inverted beyond what realised justifies",
        S.one("SPY", -w_from_z(mism)), "B")

    # ---- C: vol-of-vol
    add("C1_VVIX_RICH_Z",
        "log(VVIX/VIX): the price of VIX convexity per unit of vol. " + M4,
        "long equity when convexity is bid rich",
        S.one("SPY", w_from_z(S.lvvr)), "C")
    add("C2_VVIX_SHOCK_REV",
        "One-day VVIX jump. " + M1,
        "long equity the day after a VVIX spike",
        S.one("SPY", w_from_z(d1(np.log(S.vvix)))), "C")
    gvov = S.rvov - S.vvix / 100.0
    add("C3_REAL_VOV_GAP",
        "Realised vol-of-VIX (21d) minus VVIX. " + M3,
        "short equity when the VIX is realising more than VVIX priced",
        S.one("SPY", -w_from_z(gvov)), "C")
    add("C4_VOV_DRAIN_5D",
        "Five-day change in log(VVIX/VIX): the convexity bid draining. " + M2,
        "long equity while the convexity bid drains",
        S.one("SPY", -w_from_z(dk(S.lvvr, 5))), "C")

    # ---- D: which SESSION the reversal lives in
    add("D1_NEAR_FLATTEN_REV_ON",
        "A1's signal, held close->open only. " + M1 +
        " The unwind should concentrate where the alive T7 ex-open leg says "
        "dislocations resolve.",
        "long the overnight session after the front flattens",
        S.one("SPY_ON", w_from_z(-d1(S.s_near))), "D")
    add("D2_NEAR_FLATTEN_REV_ID",
        "A1's signal, held open->close only. " + M1,
        "long the intraday session after the front flattens",
        S.one("SPY_ID", w_from_z(-d1(S.s_near))), "D")
    add("D3_NEAR_INVERT_ON",
        "A3's binary inversion state, overnight session only. " + M1,
        "long the overnight session while the front is inverted",
        S.one("SPY_ON", np.where(np.isfinite(S.s_near) & (S.s_near < 0), 1.0, 0.0)), "D")

    # ---- E: curve-driven rotation (dollar-neutral, no market beta)
    u = w_from_z(S.s_main)
    add("E1_CURVE_BETA_ROTATE",
        "Belly slope drives high-beta vs the index. " + M2,
        "long QQQ / short SPY when the curve is steep", S.pair("QQQ", "SPY", u), "E")
    add("E2_CURVE_SIZE_ROTATE",
        "Belly slope drives small-cap vs the index. " + M2,
        "long IWM / short SPY when the curve is steep", S.pair("IWM", "SPY", u), "E")
    add("E3_VXN_RICH_ROTATE",
        "NDX implied rich to SPX implied: crowded index hedging in tech. " + M1,
        "long QQQ / short SPY when VXN is rich to VIX",
        S.pair("QQQ", "SPY", w_from_z(S.lvxn)), "E")
    add("E4_VXN_RICH_MOM5",
        "Five-day change in log(VXN/VIX): the tech hedge draining. " + M2,
        "long QQQ / short SPY while the tech hedge bid drains",
        S.pair("QQQ", "SPY", -w_from_z(dk(S.lvxn, 5))), "E")

    # =====================================================================
    # BATCH 2.  Same mechanisms, a STRUCTURAL axis batch 1 does not sweep:
    # the HOLDING HORIZON, the EVENT trigger, and a risk-off tradable leg.
    # Batch 1's books are all one-day holds of a continuous z-score; the vol
    # curve is a slow variable and a forced-hedger unwind takes days, so a
    # 1-day hold may be measuring the wrong horizon.  These are added AFTER
    # batch 1 was scored, so the reported N and the bootstrap null cover all
    # 41 formulas jointly -- that is the whole point of reporting N.
    # =====================================================================
    a1 = w_from_z(-d1(S.s_near))
    a4 = np.nan_to_num(
        np.clip(-np.where(np.isfinite(S.s_near), S.s_near, 0.0)
                / np.where(roll_std(S.s_near, ZWIN) > 1e-9,
                           roll_std(S.s_near, ZWIN), np.nan), 0.0, CLIP) / CLIP, nan=0.0)
    a5 = -w_from_z(S.s_near)
    a10 = w_from_z(dk(S.s_main, 5))

    def hold(w, k):
        """Overlapping k-day portfolio: the book is the mean of the last k
        daily targets.  Same signal, k-day horizon, 1/k the turnover."""
        out = np.zeros(len(w))
        c = np.cumsum(np.concatenate([[0.0], np.nan_to_num(w, nan=0.0)]))
        for i in range(len(w)):
            lo = max(0, i - k + 1)
            out[i] = (c[i + 1] - c[lo]) / (i + 1 - lo)
        return out

    for k in (5, 21):
        add(f"H{k}_A1_FLATTEN_HOLD",
            f"A1's front-flattening impulse held {k} days. " + M1,
            "long equity", S.one("SPY", hold(a1, k)), "H")
        add(f"H{k}_A4_INVERT_HOLD",
            f"A4's inversion depth held {k} days. " + M1,
            "long equity", S.one("SPY", hold(a4, k)), "H")
        add(f"H{k}_A5_SLOPE_HOLD",
            f"A5's front-slope tilt held {k} days. " + M1,
            "long equity when the front is flat/inverted", S.one("SPY", hold(a5, k)), "H")
        add(f"H{k}_A10_STEEPEN_HOLD",
            f"A10's belly steepening held {k} days. " + M2,
            "long equity", S.one("SPY", hold(a10, k)), "H")

    def after(trig, k):
        """Long 1.0 for the k sessions following each trigger day."""
        out = np.zeros(S.T)
        idx = np.nonzero(np.nan_to_num(trig, nan=0.0) > 0)[0]
        for i in idx:
            out[i:min(S.T, i + k)] = 1.0
        return out

    ds = d1(S.s_near)
    q95 = np.full(S.T, np.nan)
    for i in range(ZWIN, S.T):
        w = ds[i - ZWIN:i]
        w = w[np.isfinite(w)]
        if len(w) > 100:
            q95[i] = np.percentile(w, 5.0)     # 5th pct = biggest flattening
    add("G1_FLATTEN_SHOCK_5D",
        "Enter long SPY for 5 sessions after a front-curve flattening in the "
        "worst 5% of its own trailing year. " + M1,
        "long equity for 5 days after a flattening shock",
        S.one("SPY", after((ds < q95).astype(float), 5)), "G")
    fresh_inv = np.zeros(S.T)
    fresh_inv[1:] = ((S.s_near[1:] < 0) & (S.s_near[:-1] >= 0)).astype(float)
    add("G2_FRESH_INVERSION_5D",
        "Enter long SPY for 5 sessions on the day the front first inverts. " + M1,
        "long equity for 5 days after a fresh inversion",
        S.one("SPY", after(fresh_inv, 5)), "G")
    add("G3_FRESH_INVERSION_21D",
        "The same trigger held a month: if the unwind is slow this is where it "
        "shows. " + M1,
        "long equity for 21 days after a fresh inversion",
        S.one("SPY", after(fresh_inv, 21)), "G")
    un_inv = np.zeros(S.T)
    un_inv[1:] = ((S.s_near[1:] >= 0) & (S.s_near[:-1] < 0)).astype(float)
    add("G4_UNINVERSION_10D",
        "Enter long SPY for 10 sessions on the day the front RE-STEEPENS out of "
        "inversion: the all-clear, when dealers start selling the front again. " + M2,
        "long equity for 10 days after the front un-inverts",
        S.one("SPY", after(un_inv, 10)), "G")
    dm = d1(S.s_main)
    qm = np.full(S.T, np.nan)
    for i in range(ZWIN, S.T):
        w = dm[i - ZWIN:i]
        w = w[np.isfinite(w)]
        if len(w) > 100:
            qm[i] = np.percentile(w, 5.0)
    add("G5_BELLY_SHOCK_10D",
        "Enter long SPY for 10 sessions after a bottom-5% one-day collapse in the "
        "30d->93d slope. " + M1,
        "long equity for 10 days after a belly collapse",
        S.one("SPY", after((dm < qm).astype(float), 10)), "G")

    # ---- risk-off rotation leg: the curve says WHICH asset, not whether to be long
    add("V1_CURVE_RISKOFF_ROTATE",
        "Front-curve slope drives duration against equity: an inverted front is "
        "the flight-to-quality bid arriving. " + M3,
        "long TLT / short SPY when the front is flat or inverted",
        S.pair("TLT", "SPY", -w_from_z(S.s_near)), "V")
    add("V2_BELLY_RISKON_ROTATE",
        "Belly slope drives equity against duration. " + M2,
        "long SPY / short TLT when the belly is steep",
        S.pair("SPY", "TLT", w_from_z(S.s_main)), "V")
    add("V3_VVIX_RISKOFF_ROTATE",
        "The convexity bid drives duration against equity. " + M4,
        "long TLT / short SPY when VVIX is rich to VIX",
        S.pair("TLT", "SPY", w_from_z(S.lvvr)), "V")
    return F


def benchmarks(S):
    ones = np.ones(S.T)
    return [
        {"name": "Z0_SPY_LONG", "W": S.one("SPY", ones)},
        {"name": "Z1_SPY_ON_LONG", "W": S.one("SPY_ON", ones)},
        {"name": "Z2_SPY_ID_LONG", "W": S.one("SPY_ID", ones)},
        {"name": "Z3_QQQ_MINUS_SPY", "W": S.pair("QQQ", "SPY", ones)},
    ]


# -------------------------------------------------------------------- selftest
def selftest(S):
    out = {}
    dts = S.dates[1:]
    dm = (dts >= DESIGN_START) & (dts <= DESIGN_END)

    # 1. the overnight + intraday legs must reconstruct close-to-close
    ron, rid, rcc = S.R[:, AIDX["SPY_ON"]], S.R[:, AIDX["SPY_ID"]], S.R[:, AIDX["SPY"]]
    ok = np.isfinite(ron) & np.isfinite(rid) & np.isfinite(rcc)
    comp = (1 + ron[ok]) * (1 + rid[ok]) - 1.0
    out["session_reconstruction_max_abs_err"] = float(np.abs(comp - rcc[ok]).max())
    out["session_reconstruction_median_abs_err"] = float(np.median(np.abs(comp - rcc[ok])))

    # 2. a signal that is pure future information must score huge (harness can see)
    cheat = np.full(S.T, 0.0)
    cheat[:-1] = np.sign(rcc[1:])
    r = evaluate(S, S.one("SPY", cheat), DESIGN_START, DESIGN_END, 0)
    out["oracle_next_day_sign_sharpe"] = round(r["sharpe"], 2)

    # 3. the same oracle delayed by one day must collapse (no leakage in _legs)
    r1 = evaluate(S, S.one("SPY", cheat), DESIGN_START, DESIGN_END, 1)
    out["oracle_at_lag1_sharpe"] = round(r1["sharpe"], 2)

    # 4. cost must be strictly positive and scale with turnover
    a = evaluate(S, S.one("SPY", np.ones(S.T)), DESIGN_START, DESIGN_END, 0)
    flip = np.where(np.arange(S.T) % 2 == 0, 1.0, -1.0)
    b = evaluate(S, S.one("SPY", flip), DESIGN_START, DESIGN_END, 0)
    out["cost_buyhold_annual"] = round(a["cost_drag_annual"], 5)
    out["cost_dailyflip_annual"] = round(b["cost_drag_annual"], 5)

    # 5. no signal may be finite before its inputs exist
    fs = build(S)
    bad = []
    for f in fs:
        nz = np.nonzero(np.abs(f["W"]).sum(axis=1) > 1e-12)[0]
        if len(nz):
            bad.append((f["name"], int(S.dates[nz[0]])))
    out["first_live_date_per_formula"] = dict(bad)

    # 6. weights are bounded
    out["max_abs_gross_exposure"] = float(max(
        np.abs(f["W"]).sum(axis=1).max() for f in fs))

    # 7. staleness: how often each vol index repeats its previous print
    st = {}
    for s in ("^VIX", "^VIX9D", "^VIX3M", "^VIX6M", "^VVIX", "^VXN"):
        v = S.P.lvl(s)
        d = np.diff(v[np.isfinite(v)])
        st[s] = round(float((d == 0).mean()), 4)
    out["frac_days_index_unchanged"] = st
    out["design_days"] = int(dm.sum())
    return out


# ------------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["selftest", "design", "holdout"])
    ap.add_argument("--boot", type=int, default=2000)
    a = ap.parse_args()

    S = Sweep()
    print(f"panel {S.dates[0]}..{S.dates[-1]}  T={S.T}", flush=True)

    if a.mode == "selftest":
        r = selftest(S)
        (OUT / f"{TAG}_SELFTEST.json").write_text(json.dumps(r, indent=2))
        print(json.dumps(r, indent=2))
        return

    F = build(S)
    B = benchmarks(S)
    spy_net = None
    g, c, _ = _legs(S, S.one("SPY", np.ones(S.T)), 0)
    spy_net = g - c

    if a.mode == "design":
        rows = []
        for f in F:
            r0 = evaluate(S, f["W"], DESIGN_START, DESIGN_END, 0, bench=spy_net)
            r1 = evaluate(S, f["W"], DESIGN_START, DESIGN_END, 1, bench=spy_net)
            r2 = evaluate(S, f["W"], DESIGN_START, DESIGN_END, 2, bench=spy_net)
            rf = evaluate(S, -f["W"], DESIGN_START, DESIGN_END, 0)
            rows.append({
                "name": f["name"], "group": f["group"], "why": f["why"],
                "a_priori_sign": f["a_priori_sign"],
                "lag0": r0, "lag1": r1, "lag2": r2,
                "flipped_sign_sharpe_would_be": None if rf is None else round(rf["sharpe"], 3),
            })
            print(f"  {f['name']:26s} SR0={r0['sharpe']:+.2f} SR1={r1['sharpe']:+.2f} "
                  f"SR2={r2['sharpe']:+.2f} gross={r0['gross_sharpe']:+.2f} "
                  f"cost={r0['cost_drag_annual']*100:.2f}%/yr "
                  f"alphat={r0.get('alpha_t', float('nan')):+.2f}", flush=True)
        bench_rows = []
        for b in B:
            r = evaluate(S, b["W"], DESIGN_START, DESIGN_END, 0)
            bench_rows.append({"name": b["name"], "lag0": r})
            print(f"  [bench] {b['name']:22s} SR={r['sharpe']:+.2f}", flush=True)

        nm = null_max(S, [f["W"] for f in F], DESIGN_START, DESIGN_END, 0, B=a.boot)
        draws = nm.pop("_draws")
        n = len(F)
        yrs = rows[0]["lag0"]["years"]
        analytic_t = math.sqrt(2.0 * math.log(n))
        out = {
            "key": TAG, "created": str(datetime.date.today()),
            "theme": "term structure of volatility as a directional/timing signal for equity",
            "design_window": f"{DESIGN_START}..{DESIGN_END}",
            "holdout_window_reserved": f"{HOLD_START}..now  (NOT evaluated here)",
            "n_formulas_tested": n,
            "search_is_sign_agnostic": False,
            "headline_lag": 0,
            "lag_semantics": "lag0 = 15:55 read of the vol indices, MOC fill, earns t->t+1",
            "analytic_expected_max_t_sqrt2lnN": analytic_t,
            "analytic_expected_max_sharpe": analytic_t / math.sqrt(yrs),
            "bootstrap_null": nm,
            "design_sharpe_distribution": {
                "n": n,
                "best": max(r["lag0"]["sharpe"] for r in rows),
                "median": float(np.median([r["lag0"]["sharpe"] for r in rows])),
                "n_above_bootstrap_expected_max": sum(
                    1 for r in rows if r["lag0"]["sharpe"] > nm["expected_max_sharpe"]),
                "n_above_bootstrap_p95": sum(
                    1 for r in rows if r["lag0"]["sharpe"] > nm["p95_max_sharpe"]),
            },
            "benchmarks": bench_rows,
            "results": sorted(rows, key=lambda r: -r["lag0"]["sharpe"]),
            "bootstrap_p_values": {
                r["name"]: float((draws >= r["lag0"]["sharpe"]).mean()) for r in rows},
        }
        (OUT / f"{TAG}_DESIGN.json").write_text(json.dumps(out, indent=2))
        print(f"\nanalytic E[max SR] = {out['analytic_expected_max_sharpe']:.2f}")
        print(f"bootstrap E[max SR] = {nm['expected_max_sharpe']:.2f}  "
              f"p95={nm['p95_max_sharpe']:.2f}  p99={nm['p99_max_sharpe']:.2f}")
        print(f"best design SR = {out['design_sharpe_distribution']['best']:.2f}")
        return

    # holdout
    rows = []
    for f in F:
        d = evaluate(S, f["W"], DESIGN_START, DESIGN_END, 0, bench=spy_net)
        h = evaluate(S, f["W"], HOLD_START, HOLD_END, 0, bench=spy_net)
        h1 = evaluate(S, f["W"], HOLD_START, HOLD_END, 1)
        h2x = evaluate(S, f["W"], HOLD_START, HOLD_END, 0, cost_mult=2.0)
        rows.append({"name": f["name"], "group": f["group"],
                     "design_lag0": d, "holdout_lag0": h, "holdout_lag1": h1,
                     "holdout_lag0_double_cost": h2x})
        print(f"  {f['name']:26s} design SR={d['sharpe']:+.2f} | HELD-OUT SR="
              f"{h['sharpe']:+.2f} t={h['t_stat']:+.2f} alpha_t={h.get('alpha_t', 0):+.2f} "
              f"| 2x cost {h2x['sharpe']:+.2f}", flush=True)
    bench_rows = []
    for b in B:
        r = evaluate(S, b["W"], HOLD_START, HOLD_END, 0)
        bench_rows.append({"name": b["name"], "holdout_lag0": r})
        print(f"  [bench] {b['name']:22s} HELD-OUT SR={r['sharpe']:+.2f}", flush=True)
    (OUT / f"{TAG}_HOLDOUT.json").write_text(
        json.dumps({"rows": rows, "benchmarks": bench_rows}, indent=2))


if __name__ == "__main__":
    sys.exit(main())
