#!/usr/bin/env python3
"""WIDE formula sweep: Binance USD-M perp microstructure cross-section.

ONE vectorised harness, MANY structurally-different formulas. Everything is evaluated on a
DESIGN window; the HELD-OUT window is only touched with --holdout (and only for the shortlist
named on the command line), so the sweep itself cannot peek.

MECHANICS (identical for every formula, so only the FORMULA differs)
--------------------------------------------------------------------
* Grid: 1h UTC bars, S symbols x NH hours (research/data/perpmicro_cache/panel1h.npz).
* Universe at bar t: the TOP_N symbols by trailing-7d quote volume that have a finite feature.
  Point-in-time, so no survivorship and no untradeable names.
* Signal x(s,t) uses data through the CLOSE of bar t. Weights W(:,t) are formed from x(:,t).
* Holding at bar j = mean(W(:, j-H .. j-1))  -> lag >= 1 bar, H overlapping tranches.
  Entry and exit are therefore at the OPEN of a bar the signal cannot see.
* Bar return = open[j+1]/open[j] - 1  (open-to-open; the close that made the signal is never
  a fill price).
* P&L = price P&L + FUNDING accrual (charged/received at the bar a settlement lands in)
        - turnover * cost_per_side.
* Daily aggregation, Sharpe = mean/sd * sqrt(365).

COSTS. Binance USD-M taker fee is 4.5 bp/side (published exchange schedule, VIP0, no BNB
discount). Nobody in this programme has MEASURED perp slippage, so the extra half-spread is
declared, not measured: headline adds 1.0 bp/side for a top-120-by-volume universe, giving
5.5 bp/side. Gross and the BREAKEVEN cost per side are both reported so the reader can move
the number themselves.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import pathlib
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[2]
PANEL = ROOT / "research" / "data" / "perpmicro_cache" / "panel1h.npz"
OUTMD = ROOT / "research" / "trading_bot" / "SWEEP_crypto_perp_microstructure.md"
OUTJS = ROOT / "research" / "trading_bot" / "SWEEP_crypto_perp_microstructure.json"

HOUR = 3_600_000
T0 = int(dt.datetime(2021, 12, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)

DESIGN = ("2023-01-01", "2024-04-01")
HELDOUT = ("2024-04-01", "2025-01-01")

COST_SIDE_BP = 5.5      # 4.5 bp taker (published) + 1.0 bp declared half-spread
TOP_N = 120
MIN_NAMES = 30
QUANTILE = 0.20         # long top 20%, short bottom 20%


# ------------------------------------------------------------------ rolling helpers (causal)
def _csum(a):
    z = np.zeros((a.shape[0], 1), a.dtype)
    return np.concatenate([z, np.cumsum(a, axis=1)], axis=1)


def roll_sum(a, w):
    """causal trailing sum over w bars INCLUDING t; NaN-safe (NaN treated as 0, count tracked)."""
    m = np.isfinite(a)
    b = np.where(m, a, 0.0)
    cs = _csum(b); cn = _csum(m.astype(np.float32))
    n = a.shape[1]
    s = cs[:, w:] - cs[:, :-w]
    c = cn[:, w:] - cn[:, :-w]
    out = np.full(a.shape, np.nan, np.float32)
    out[:, w - 1:] = np.where(c >= max(1, int(0.6 * w)), s / np.maximum(c, 1) * w, np.nan)
    return out


def roll_mean(a, w):
    return roll_sum(a, w) / w


def roll_std(a, w):
    m = roll_mean(a, w)
    m2 = roll_mean(a * a, w)
    v = m2 - m * m
    return np.sqrt(np.maximum(v, 0.0))


def roll_max(a, w):
    n = a.shape[1]
    out = np.full(a.shape, np.nan, np.float32)
    # strided max via successive doubling (log w passes), NaN-safe
    cur = a.copy()
    step = 1
    while step < w:
        k = min(step, w - step)
        shifted = np.full_like(cur, np.nan)
        shifted[:, k:] = cur[:, :-k]
        cur = np.fmax(cur, shifted)
        step += k
    out[:, w - 1:] = cur[:, w - 1:]
    return out


def roll_min(a, w):
    return -roll_max(-a, w)


def lag(a, k):
    out = np.full(a.shape, np.nan, np.float32)
    if k > 0:
        out[:, k:] = a[:, :-k]
    elif k == 0:
        out = a.copy()
    return out


def dlog(a, k):
    with np.errstate(invalid="ignore", divide="ignore"):
        la = np.log(np.where(a > 0, a, np.nan))
    return la - lag(la, k)


def zs(a, w):
    """own-history z-score over trailing w bars."""
    m = roll_mean(a, w); s = roll_std(a, w)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(s > 0, (a - m) / s, np.nan).astype(np.float32)


def xrank(x, mask):
    """cross-sectional rank in [-1,1], NaN outside mask. x,mask: (S,NH)."""
    out = np.full(x.shape, np.nan, np.float32)
    v = np.where(mask & np.isfinite(x), x, np.nan)
    order = np.argsort(np.where(np.isfinite(v), v, np.inf), axis=0, kind="stable")
    n = np.isfinite(v).sum(axis=0)
    ranks = np.empty_like(order, dtype=np.float32)
    S = x.shape[0]
    rows = np.arange(S)[:, None]
    np.put_along_axis(ranks, order, np.broadcast_to(rows.astype(np.float32), order.shape), axis=0)
    good = n >= MIN_NAMES
    with np.errstate(invalid="ignore", divide="ignore"):
        r = np.where(np.isfinite(v) & good, (ranks / np.maximum(n - 1, 1)) * 2 - 1, np.nan)
    out[:] = r
    return out.astype(np.float32)


def xz(x, mask):
    """cross-sectional z-score (winsorised at +-4)."""
    v = np.where(mask & np.isfinite(x), x, np.nan)
    n = np.isfinite(v).sum(axis=0)
    mu = np.nanmean(np.where(np.isfinite(v), v, np.nan), axis=0)
    sd = np.nanstd(np.where(np.isfinite(v), v, np.nan), axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        z = (v - mu) / np.where(sd > 0, sd, np.nan)
    z = np.clip(z, -4, 4)
    return np.where(n >= MIN_NAMES, z, np.nan).astype(np.float32)


# ------------------------------------------------------------------ panel + features
class P:
    pass


def build_features(pan):
    p = P()
    p.sym = pan["symbols"]
    p.t = pan["t"]
    g = {k: pan[k].astype(np.float32) for k in
         ["o", "h", "l", "c", "qv", "ntr", "tbq", "oi", "oiv", "ttc", "tts", "glsr", "tlsr",
          "fund", "fund_age_h", "fund_next_h"]}
    p.g = g
    S, NH = g["c"].shape
    p.S, p.NH = S, NH

    # ---- tradability: open-to-open return, valid only when both opens exist
    o = g["o"]
    nxt = np.full_like(o, np.nan); nxt[:, :-1] = o[:, 1:]
    with np.errstate(invalid="ignore", divide="ignore"):
        p.ret = np.where((o > 0) & (nxt > 0), nxt / o - 1.0, 0.0).astype(np.float32)
    p.ret = np.clip(p.ret, -0.5, 0.5)

    # ---- liquidity universe (trailing 7d quote volume). Uses ONLY data through bar t:
    # a missing next-open is NOT allowed to filter the universe (that would be lookahead),
    # it simply yields a zero return for that bar.
    qv7 = roll_sum(g["qv"], 168)
    p.qv7 = qv7
    liq_ok = np.isfinite(qv7) & np.isfinite(g["o"]) & (g["o"] > 0) & (g["qv"] > 0)
    v = np.where(liq_ok, qv7, -np.inf)
    # rank descending: keep top TOP_N
    ordr = np.argsort(-v, axis=0, kind="stable")
    rk = np.empty_like(ordr, dtype=np.int32)
    np.put_along_axis(rk, ordr, np.broadcast_to(np.arange(S, dtype=np.int32)[:, None], ordr.shape), axis=0)
    p.univ = liq_ok & (rk < TOP_N)

    # ---- returns / vol
    p.lc = np.log(np.where(g["c"] > 0, g["c"], np.nan)).astype(np.float32)
    p.r1 = (p.lc - lag(p.lc, 1)).astype(np.float32)
    p.r4 = (p.lc - lag(p.lc, 4)).astype(np.float32)
    p.r24 = (p.lc - lag(p.lc, 24)).astype(np.float32)
    p.r72 = (p.lc - lag(p.lc, 72)).astype(np.float32)
    p.r168 = (p.lc - lag(p.lc, 168)).astype(np.float32)
    p.rv24 = roll_std(p.r1, 24)
    p.rv168 = roll_std(p.r1, 168)

    # ---- flow
    with np.errstate(invalid="ignore", divide="ignore"):
        p.ti1 = np.where(g["qv"] > 0, (2 * g["tbq"] - g["qv"]) / g["qv"], np.nan).astype(np.float32)
    tb24 = roll_sum(g["tbq"], 24); qq24 = roll_sum(g["qv"], 24)
    with np.errstate(invalid="ignore", divide="ignore"):
        p.ti24 = np.where(qq24 > 0, (2 * tb24 - qq24) / qq24, np.nan).astype(np.float32)
    p.ti_z = zs(p.ti24, 168)
    with np.errstate(invalid="ignore", divide="ignore"):
        p.ats = np.where(g["ntr"] > 0, g["qv"] / g["ntr"], np.nan).astype(np.float32)
    p.ats_z = zs(np.log(np.where(p.ats > 0, p.ats, np.nan)).astype(np.float32), 168)
    with np.errstate(invalid="ignore", divide="ignore"):
        p.churn = np.where(g["oiv"] > 0, qq24 / g["oiv"], np.nan).astype(np.float32)
        p.amihud = roll_mean(np.where(g["qv"] > 0, np.abs(p.r1) / g["qv"], np.nan).astype(np.float32), 24)

    # ---- open interest
    p.doi1 = dlog(g["oiv"], 1)
    p.doi24 = dlog(g["oiv"], 24)
    p.doiu24 = dlog(g["oi"], 24)     # contract units: price-move free
    p.doiu72 = dlog(g["oi"], 72)
    p.doiu4 = dlog(g["oi"], 4)
    p.doi_acc = (p.doiu24 - lag(p.doiu24, 24)).astype(np.float32)

    # ---- positioning ratios
    def L(a):
        return np.log(np.where(a > 0, a, np.nan)).astype(np.float32)
    p.lg = L(g["glsr"]); p.lt = L(g["tts"]); p.ltc = L(g["ttc"]); p.ltl = L(g["tlsr"])
    p.lg_z = zs(p.lg, 168); p.lt_z = zs(p.lt, 168); p.ltl_z = zs(p.ltl, 168)
    p.lg_chg = (p.lg - lag(p.lg, 24)).astype(np.float32)
    p.smart = (p.lt - p.lg).astype(np.float32)
    p.smart_chg = (p.smart - lag(p.smart, 24)).astype(np.float32)
    p.tsize = (p.lt - p.ltc).astype(np.float32)

    # ---- funding
    p.f = g["fund"]
    p.f_z = zs(p.f, 720)
    p.f_chg = (p.f - lag(p.f, 72)).astype(np.float32)
    with np.errstate(invalid="ignore", divide="ignore"):
        p.f_va = np.where(p.rv24 > 0, p.f / p.rv24, np.nan).astype(np.float32)
    p.settle = (np.isfinite(g["fund_age_h"]) & (g["fund_age_h"] < 1.0))
    p.next_h = g["fund_next_h"]

    # ---- drawdown / range
    hi168 = roll_max(g["h"], 168); lo24 = roll_min(g["l"], 24); hi24 = roll_max(g["h"], 24)
    with np.errstate(invalid="ignore", divide="ignore"):
        p.dd7 = np.where(hi168 > 0, g["c"] / hi168 - 1.0, np.nan).astype(np.float32)
        p.pos24 = np.where(hi24 > lo24, (g["c"] - lo24) / (hi24 - lo24), np.nan).astype(np.float32)
    return p


# ------------------------------------------------------------------ portfolio
def weights_from_signal(x, univ, scheme):
    m = univ & np.isfinite(x)
    if scheme == "rank":
        r = xrank(x, m)
        w = np.where(np.isfinite(r), r, 0.0).astype(np.float32)
    elif scheme == "quintile":
        r = xrank(x, m)
        thr = 1.0 - 2.0 * QUANTILE
        w = np.zeros_like(r, np.float32)
        w = np.where(np.isfinite(r) & (r >= thr), 1.0, w)
        w = np.where(np.isfinite(r) & (r <= -thr), -1.0, w)
    elif scheme == "ts":
        # TIME-SERIES bet: one scalar per bar (identical across rows) sets the DIRECTION of a
        # constant-gross equal-weight basket. No cross-sectional demeaning -- this is directional.
        s = np.where(np.isfinite(x[0]), np.sign(x[0]), 0.0).astype(np.float32)
        live = (univ).astype(np.float32)
        n = live.sum(axis=0)
        w = live * s[None, :]
        gross = np.abs(w).sum(axis=0)
        w = np.where(gross > 0, w / np.maximum(gross, 1e-9), 0.0).astype(np.float32)
        w[:, n < MIN_NAMES] = 0.0
        return w
    else:
        raise ValueError(scheme)
    # demean within the live universe, then normalise gross to 1
    live = m.astype(np.float32)
    n = live.sum(axis=0)
    w = w * live
    with np.errstate(invalid="ignore", divide="ignore"):
        w = w - live * (w.sum(axis=0) / np.maximum(n, 1))
    gross = np.abs(w).sum(axis=0)
    w = np.where(gross > 0, w / np.maximum(gross, 1e-9), 0.0).astype(np.float32)
    w[:, n < MIN_NAMES] = 0.0
    return w


def hold_from_weights(w, H):
    """holding at bar j = mean of W(:, j-H .. j-1). lag >= 1."""
    cs = _csum(w.astype(np.float64))
    S, NH = w.shape
    hold = np.zeros((S, NH), np.float32)
    if H >= NH:
        return hold
    hold[:, H:] = ((cs[:, H:NH] - cs[:, 0:NH - H]) / H).astype(np.float32)
    return hold


def evaluate(x, p, H, scheme, mask_t=None):
    """returns dict of daily arrays: gross price pnl, funding pnl, turnover."""
    w = weights_from_signal(x, p.univ, scheme)
    if mask_t is not None:
        w = w * mask_t[None, :].astype(np.float32)
    hold = hold_from_weights(w, H)
    r = np.where(np.isfinite(p.ret), p.ret, 0.0)
    pnl = (hold * r).sum(axis=0)
    fnd = np.where(np.isfinite(p.f) & p.settle, p.f, 0.0)
    pnl_f = -(hold * fnd).sum(axis=0)          # long pays positive funding
    dh = np.abs(np.diff(hold, axis=1, prepend=0.0)).sum(axis=0)
    return pnl.astype(np.float64), pnl_f.astype(np.float64), dh.astype(np.float64)


def to_daily(v, NH):
    n = (NH // 24) * 24
    return v[:n].reshape(-1, 24).sum(axis=1)


def _corr(a, b):
    a = np.asarray(a, float); b = np.asarray(b, float)
    m = np.isfinite(a) & np.isfinite(b)
    if m.sum() < 30 or a[m].std() == 0 or b[m].std() == 0:
        return float("nan")
    return float(np.corrcoef(a[m], b[m])[0, 1])


def _worst_roll(d, w):
    if len(d) < w:
        return float("nan")
    cs = np.concatenate([[0.0], np.cumsum(d)])
    return float(np.min(cs[w:] - cs[:-w]))


def sharpe(d):
    d = d[np.isfinite(d)]
    if len(d) < 60 or d.std() == 0:
        return float("nan")
    return float(d.mean() / d.std() * math.sqrt(365))


# ------------------------------------------------------------------ formula catalogue
def catalogue(p):
    """(name, signal array, horizon_h, scheme, time-mask, description)"""
    F = []
    A = F.append
    U = p.univ

    # --- open interest family
    A(("XS_OI24", p.doiu24, 24, "quintile", None,
       "cross-sec rank of 24h log change in open interest (contracts)"))
    A(("XS_OI72", p.doiu72, 24, "quintile", None, "72h log change in open interest"))
    A(("XS_OI4", p.doiu4, 4, "quintile", None, "4h log change in open interest, 4h hold"))
    A(("XS_OI_ACCEL", p.doi_acc, 24, "quintile", None,
       "second difference of OI: 24h OI change minus its own value 24h ago"))
    A(("XS_OI_MINUS_RET", xz(p.doiu24, U) - xz(p.r24, U), 24, "quintile", None,
       "z(OI growth) - z(24h return): OI built while price fell (trapped/crowded shorts)"))
    A(("XS_OI_PLUS_RET", xz(p.doiu24, U) + xz(p.r24, U), 24, "quintile", None,
       "z(OI growth) + z(24h return): new money chasing (fresh-leverage momentum)"))
    A(("XS_OI_NORM", xz(p.doiu24, U) - xz(np.abs(p.r24), U), 24, "quintile", None,
       "OI growth in excess of what its own price volatility explains"))
    A(("XS_CHURN", p.churn, 24, "quintile", None,
       "24h quote volume / open-interest notional (position churn rate)"))

    # --- taker / aggressor flow
    A(("XS_TAKER1", p.ti1, 4, "quintile", None, "1h taker buy-sell notional imbalance, 4h hold"))
    A(("XS_TAKER24", p.ti24, 24, "quintile", None, "24h taker buy-sell notional imbalance"))
    A(("XS_TAKER_Z", p.ti_z, 24, "quintile", None,
       "24h taker imbalance z-scored against its own 7d history (flow surprise)"))
    A(("XS_TAKER_DIV", xz(p.ti24, U) - xz(p.r24, U), 24, "quintile", None,
       "aggressive buying that did NOT move price (absorbed flow divergence)"))
    A(("XS_TLSR", roll_mean(p.ltl, 24), 24, "quintile", None,
       "Binance taker long/short volume ratio, 24h mean, cross-sec rank"))
    A(("XS_TLSR_Z", p.ltl_z, 24, "quintile", None,
       "taker long/short volume ratio z-scored vs its own 7d history"))
    A(("XS_ATS_Z", p.ats_z, 24, "quintile", None,
       "z of log average trade size (quote vol / trade count) vs 7d: whale-print detector"))
    A(("XS_ATS_REV", xz(p.ats_z, U) - xz(p.r24, U), 24, "quintile", None,
       "big prints against the 24h move (whale accumulation into weakness)"))

    # --- account positioning (long/short ratios)
    A(("XS_GLSR", p.lg, 24, "quintile", None,
       "log global account long/short ratio, cross-sec rank (retail crowding level)"))
    A(("XS_GLSR_Z", p.lg_z, 24, "quintile", None, "global L/S ratio z vs own 7d (crowding surprise)"))
    A(("XS_GLSR_CHG", p.lg_chg, 24, "quintile", None, "24h change in log global L/S ratio"))
    A(("XS_TTS", p.lt, 24, "quintile", None, "log top-trader POSITION long/short ratio"))
    A(("XS_TTS_Z", p.lt_z, 24, "quintile", None, "top-trader position ratio z vs own 7d"))
    A(("XS_SMART", p.smart, 24, "quintile", None,
       "log(top-trader position L/S) - log(global account L/S): smart-vs-crowd divergence"))
    A(("XS_SMART_CHG", p.smart_chg, 24, "quintile", None, "24h change in the smart-vs-crowd spread"))
    A(("XS_TSIZE", p.tsize, 24, "quintile", None,
       "log(top-trader POSITION ratio) - log(top-trader ACCOUNT ratio): size concentration"))
    A(("XS_CROWD_UNWIND", xz(p.lg, U) - xz(p.doiu24, U), 24, "quintile", None,
       "crowded long AND shrinking OI: the crowd is being forced out"))

    # --- funding / carry
    A(("XS_FUND", p.f, 8, "quintile", None, "cross-sec rank of last settled funding rate, 8h hold"))
    A(("XS_FUND_24", p.f, 24, "quintile", None, "same funding rank, 24h hold"))
    A(("XS_FUND_Z", p.f_z, 8, "quintile", None, "funding rate z-scored vs its own 30d history"))
    A(("XS_FUND_CHG", p.f_chg, 24, "quintile", None, "3-day change in the funding rate (funding momentum)"))
    A(("XS_FUND_VA", p.f_va, 8, "quintile", None, "funding rate divided by 24h realised vol (risk-adjusted carry)"))
    A(("XS_FUND_x_OI", xz(p.f, U) + xz(p.doiu24, U), 24, "quintile", None,
       "high funding AND rising OI: leverage piling into an expensive side"))
    A(("XS_FUND_MINUS_RET", xz(p.f, U) - xz(p.r24, U), 24, "quintile", None,
       "expensive funding without the price move to justify it"))
    hod = (((p.t - T0) // HOUR) % 24).astype(np.int64)
    A(("XS_FUND_PRE", p.f, 2, "quintile", np.isin(hod, [6, 7, 14, 15, 22, 23]),
       "funding rank held ONLY in the 2h BEFORE the 00/08/16 UTC settlement (capture window)"))
    A(("XS_FUND_POST", p.f, 2, "quintile", np.isin(hod, [0, 1, 8, 9, 16, 17]),
       "funding rank held ONLY in the 2h AFTER settlement (post-settlement reversion)"))

    # --- price / vol / liquidity controls and interactions
    A(("XS_REV4", -p.r4, 4, "quintile", None, "4h cross-sectional reversal"))
    A(("XS_REV24", -p.r24, 24, "quintile", None, "24h cross-sectional reversal"))
    A(("XS_MOM168", p.r168, 24, "quintile", None, "7d cross-sectional momentum"))
    A(("XS_REV_VA", -p.r24 / np.where(p.rv24 > 0, p.rv24, np.nan), 24, "quintile", None,
       "24h reversal scaled by own realised vol"))
    A(("XS_RANGEPOS", -p.pos24, 24, "quintile", None,
       "position of close inside the 24h high-low range, inverted"))
    A(("XS_AMIHUD", p.amihud, 24, "quintile", None, "Amihud illiquidity (|r|/quote vol), 24h mean"))
    A(("XS_LOWVOL", -p.rv168, 24, "quintile", None, "inverse 7d realised vol (bet-against-beta)"))
    A(("XS_TRAPPED", xz(p.dd7, U) - xz(p.doiu24, U), 24, "quintile", None,
       "deep below the 7d high while OI keeps growing: trapped longs"))
    A(("XS_LIQPROX", xz(-np.abs(p.dd7), U) + xz(p.rv24, U), 24, "quintile", None,
       "liquidation proximity: far from the 7d high and high realised vol"))

    # --- attention / activity shocks
    A(("XS_NTR_Z", zs(np.log(np.where(p.g["ntr"] > 0, p.g["ntr"], np.nan)).astype(np.float32), 168),
       24, "quintile", None, "z of log hourly trade count vs 7d (attention shock)"))
    A(("XS_QV_Z", zs(np.log(np.where(p.g["qv"] > 0, p.g["qv"], np.nan)).astype(np.float32), 168),
       24, "quintile", None, "z of log hourly quote volume vs 7d (volume shock)"))
    A(("XS_VOLEXP", xz(p.rv24, U) - xz(p.rv168, U), 24, "quintile", None,
       "volatility expansion: 24h realised vol relative to 7d realised vol"))
    A(("XS_SQUEEZE", xz(-p.doiu24, U) + xz(p.r24, U), 24, "quintile", None,
       "OI destroyed while price rose: short-squeeze covering signature"))
    A(("XS_SMART_x_FUND", xz(p.smart, U) - xz(p.f, U), 24, "quintile", None,
       "top traders long where funding is cheap (informed carry positioning)"))
    A(("XS_OI_PER_VOL", xz(p.doiu24, U) - xz(zs(np.log(np.where(p.g["qv"] > 0, p.g["qv"], np.nan)
                                                   ).astype(np.float32), 168), U),
       24, "quintile", None, "OI growth in excess of the volume shock that produced it"))

    # --- weighting-scheme variants of the two most natural signals
    A(("XS_OI24_RANK", p.doiu24, 24, "rank", None, "OI-24h signal, full rank-weighted book"))
    A(("XS_FUND_RANK", p.f, 8, "rank", None, "funding signal, full rank-weighted book"))

    # --- time-series (market-timing) formulas: one scalar, whole equal-weight basket
    ones = np.ones((p.S, p.NH), np.float32)
    live_n = np.maximum(p.univ.sum(0), 1)
    mkt_f = (np.nansum(np.where(p.univ & np.isfinite(p.f), p.f, 0.0), axis=0) / live_n).astype(np.float32)
    mkt_oi = (np.nansum(np.where(p.univ & np.isfinite(p.doiu24), p.doiu24, 0.0), axis=0) / live_n).astype(np.float32)
    mkt_ti = (np.nansum(np.where(p.univ & np.isfinite(p.ti24), p.ti24, 0.0), axis=0) / live_n).astype(np.float32)
    z1 = lambda v: zs(v[None, :], 720)[0]
    A(("TS_MKT_FUND", ones * z1(mkt_f)[None, :], 8, "ts", None,
       "TIME-SERIES: sign of universe-mean funding z-scored vs 30d, applied to the whole basket"))
    A(("TS_MKT_OI", ones * z1(mkt_oi)[None, :], 24, "ts", None,
       "TIME-SERIES: sign of universe-mean 24h OI growth (z vs 30d), whole basket"))
    A(("TS_MKT_TAKER", ones * z1(mkt_ti)[None, :], 24, "ts", None,
       "TIME-SERIES: sign of universe-mean taker imbalance (z vs 30d), whole basket"))
    A(("TS_TOD_ASIA", ones * np.where(hod < 8, 1.0, -1.0).astype(np.float32)[None, :], 8, "ts", None,
       "TIME-SERIES: long the basket 00-08 UTC, short 08-24 UTC (time-of-day)"))
    A(("TS_TOD_SETTLE", ones * np.where(np.isin(hod, [0, 8, 16]), 1.0, -1.0).astype(np.float32)[None, :],
       1, "ts", None, "TIME-SERIES: long the basket only in the settlement hour, short elsewhere"))
    return F


# ------------------------------------------------------------------ run
def window_mask(t, a, b):
    ta = int(dt.datetime.fromisoformat(a).replace(tzinfo=dt.timezone.utc).timestamp() * 1000)
    tb = int(dt.datetime.fromisoformat(b).replace(tzinfo=dt.timezone.utc).timestamp() * 1000)
    return (t >= ta) & (t < tb)


def run_window(F, p, wmask, signs=None):
    """returns list of result dicts + (N,D) daily net pnl matrix."""
    NH = p.NH
    ndays = NH // 24
    dm = wmask[:ndays * 24].reshape(-1, 24).any(axis=1)
    # equal-weight universe basket, for a market-beta diagnostic
    nlive = np.maximum(p.univ.sum(0), 1)
    mkt_h = (np.where(p.univ, p.ret, 0.0).sum(axis=0) / nlive).astype(np.float64)
    mkt_d = to_daily(mkt_h, NH)[dm]
    res = []
    mat = []
    for name, x, H, scheme, tmask, desc in F:
        if x.ndim == 1:
            x = np.broadcast_to(x[None, :], (p.S, p.NH))
        x = np.ascontiguousarray(x.astype(np.float32))
        if tmask is not None and np.ndim(tmask) == 1:
            tm = np.asarray(tmask)
        else:
            tm = None
        pnl, pf, dh = evaluate(x, p, H, scheme, tm)
        dp = to_daily(pnl, NH)[dm]
        df = to_daily(pf, NH)[dm]
        dt_ = to_daily(dh, NH)[dm]
        gross = dp + df
        # ORIENTATION. A formula and its negation are the SAME hypothesis: the sign is picked
        # from the design gross P&L, and the noise bar below is two-sided to pay for that bit.
        # Costs are sign-invariant, so they are charged AFTER orienting -- a large negative net
        # Sharpe is cost drag, not an edge waiting to be flipped.
        if signs is not None and name in signs:
            s = float(signs[name])          # HELD-OUT: sign frozen from the design window
        else:
            s = 1.0 if np.nanmean(gross) >= 0 else -1.0
        og = s * gross
        cost = dt_ * COST_SIDE_BP * 1e-4
        net = og - cost
        tpd = float(np.nanmean(dt_))
        be = float(np.nanmean(og) / tpd * 1e4) if tpd > 0 else float("nan")
        res.append(dict(name=name, desc=desc, H=H, scheme=scheme, sign=s,
                        sharpe_gross=sharpe(og), sharpe_net=sharpe(net),
                        sharpe_gross_signed=sharpe(gross),
                        ann_ret_gross=float(np.nanmean(og) * 365),
                        ann_ret_net=float(np.nanmean(net) * 365),
                        cost_drag_ann=float(np.nanmean(cost) * 365),
                        turnover_per_day=tpd,
                        breakeven_cost_bp_per_side=be,
                        ndays=int(len(net)),
                        ann_ret_funding=float(s * np.nanmean(df) * 365),
                        ann_ret_price=float(s * np.nanmean(dp) * 365),
                        corr_market=_corr(og, mkt_d), ar1=_corr(og[1:], og[:-1]),
                        hit_rate=float(np.mean(net > 0)),
                        worst_60d_net=float(_worst_roll(net, 60))))
        mat.append(gross)
    return res, np.array(mat)


def noise_bar(mat, nboot=4000, block=5, seed=7):
    """sign-flip block bootstrap of max |Sharpe| across the WHOLE tested set,
    preserving cross-formula correlation."""
    rng = np.random.default_rng(seed)
    N, D = mat.shape
    nb = (D + block - 1) // block
    mu = mat.mean(axis=1, keepdims=True)
    dm = mat - mu           # centre so the null is truly zero-mean
    sd = dm.std(axis=1)
    sd = np.where(sd > 0, sd, np.nan)
    mx = np.empty(nboot)
    for i in range(nboot):
        s = rng.choice([-1.0, 1.0], size=nb)
        s = np.repeat(s, block)[:D]
        m = (dm * s[None, :]).mean(axis=1)
        sh = np.abs(m / sd) * math.sqrt(365)
        mx[i] = np.nanmax(sh)
    return dict(mean=float(mx.mean()), p95=float(np.percentile(mx, 95)),
                p50=float(np.percentile(mx, 50)))


def lookahead_audit(pan, F_names=None, cut_frac=0.6):
    """Destroy every input after bar K and re-derive the panel. Any weight at t < K that
    moves proves a formula reached forward. Nothing is trusted here -- it is asserted."""
    raw = {k: pan[k] for k in pan.files}
    K = int(raw["c"].shape[1] * cut_frac)
    trunc = dict(raw)
    for k in ["o", "h", "l", "c", "qv", "ntr", "tbq", "oi", "oiv", "ttc", "tts", "glsr",
              "tlsr", "fund", "fund_age_h", "fund_next_h"]:
        a = raw[k].copy()
        a[:, K:] = np.nan
        trunc[k] = a
    pa = build_features(pan)
    pb = build_features(trunc)
    Fa, Fb = catalogue(pa), catalogue(pb)
    bad = []
    for (na, xa, H, sc, tm, _), (nb, xb, *_rest) in zip(Fa, Fb):
        if F_names and na not in F_names:
            continue
        xa = np.ascontiguousarray(np.broadcast_to(xa, (pa.S, pa.NH)).astype(np.float32))
        xb = np.ascontiguousarray(np.broadcast_to(xb, (pa.S, pa.NH)).astype(np.float32))
        wa = weights_from_signal(xa, pa.univ, sc)[:, :K - 1]
        wb = weights_from_signal(xb, pb.univ, sc)[:, :K - 1]
        d = np.nanmax(np.abs(wa - wb)) if wa.size else 0.0
        if not (d <= 1e-6):
            bad.append((na, float(d)))
    return dict(cut_bar=K, n_checked=len(Fa), violations=bad)


def write_md(out):
    r = out["design"]
    nb = out["noise_bar"]
    L = []
    L.append("# SWEEP: crypto-perp microstructure (Binance USD-M)\n")
    L.append(f"Design window **{out['design_window'][0]} -> {out['design_window'][1]}** "
             f"({out['design_days']} days). Held out and untouched during the sweep: "
             f"**{out['heldout_window'][0]} -> {out['heldout_window'][1]}**.\n")
    L.append(f"Panel: {out['panel']['symbols']} perps, 1h bars, point-in-time top-"
             f"{out['panel']['top_n']} by trailing-7d quote volume. "
             f"P&L = price + funding accrual - {out['panel']['cost_bp_per_side']} bp/side turnover.\n")
    L.append("## Noise bar\n")
    L.append(f"- formulas tested: **{out['n_formulas']}**")
    L.append(f"- analytic expected max |Sharpe| under the null, sqrt(2 ln 2N)/sqrt(T): "
             f"**{nb['analytic_sqrt_2ln2N']:.2f}**")
    L.append(f"- sign-flip block bootstrap of max |Sharpe| over the ACTUAL correlated formula set: "
             f"mean **{nb['bootstrap']['mean']:.2f}**, median {nb['bootstrap']['p50']:.2f}, "
             f"95th pct **{nb['bootstrap']['p95']:.2f}**\n")
    if "lookahead_audit" in out:
        la = out["lookahead_audit"]
        L.append(f"- lookahead audit: {la['n_checked']} formulas re-derived with all data after "
                 f"bar {la['cut_bar']} destroyed; violations = **{len(la['violations'])}**\n")
    L.append("\nSign convention: each formula is ORIENTED by its design gross P&L (a formula and "
             "its negation are one hypothesis), which is why the bar is two-sided. `gross SR` below "
             "is therefore |Sharpe| and is the number the bar applies to. Costs are sign-invariant "
             "and charged after orienting.\n")
    L.append("## Full design distribution (every formula, ranked by gross |Sharpe|)\n")
    L.append("| # | formula | H | gross SR | net SR | ann gross | ann net | turn/day | "
             "breakeven bp/side | corr(mkt) | sign | signal |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for i, x in enumerate(r, 1):
        L.append(f"| {i} | `{x['name']}` | {x['H']}h | {x['sharpe_gross']:.2f} | "
                 f"{x['sharpe_net']:+.2f} | {x['ann_ret_gross']*100:+.1f}% | {x['ann_ret_net']*100:+.1f}% | "
                 f"{x['turnover_per_day']:.2f} | {x['breakeven_cost_bp_per_side']:.2f} | "
                 f"{x.get('corr_market', float('nan')):+.2f} | "
                 f"{x['sign']:+.0f} | {x['desc']} |")
    if "heldout" in out:
        L.append("\n## HELD-OUT results (shortlist only; sign FROZEN from the design window)\n")
        L.append("| formula | H | gross SR | net SR | ann net | breakeven bp/side |")
        L.append("|---|---|---|---|---|---|")
        for x in out["heldout"]:
            L.append(f"| `{x['name']}` | {x['H']}h | {x['sharpe_gross']:+.2f} | "
                     f"{x['sharpe_net']:+.2f} | "
                     f"{x['ann_ret_net']*100:+.1f}% | {x['breakeven_cost_bp_per_side']:.2f} |")
    L.append("\n" + out.get("verdict", ""))
    OUTMD.write_text("\n".join(L) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--holdout", nargs="*", default=None,
                    help="formula names to ALSO evaluate on the held-out window")
    ap.add_argument("--audit", action="store_true")
    a = ap.parse_args()

    pan = np.load(PANEL, allow_pickle=True)
    p = build_features(pan)
    F = catalogue(p)
    print(f"panel {p.S} symbols x {p.NH} hours; {len(F)} formulas", flush=True)

    dmask = window_mask(p.t, *DESIGN)
    res, mat = run_window(F, p, dmask)
    nb = noise_bar(mat)
    N = len(F)
    T_years = mat.shape[1] / 365.0
    analytic = math.sqrt(2 * math.log(2 * N)) / math.sqrt(T_years)

    res.sort(key=lambda r: -r["sharpe_gross"] if np.isfinite(r["sharpe_gross"]) else 0)
    out = dict(theme="crypto_perp_microstructure",
               panel=dict(symbols=int(p.S), hours=int(p.NH), top_n=TOP_N,
                          cost_bp_per_side=COST_SIDE_BP),
               design_window=list(DESIGN), heldout_window=list(HELDOUT),
               n_formulas=N, design_days=int(mat.shape[1]),
               noise_bar=dict(bootstrap=nb, analytic_sqrt_2ln2N=analytic),
               design=res)

    if a.audit:
        del p, F
        out["lookahead_audit"] = lookahead_audit(pan)
        print("AUDIT", out["lookahead_audit"], flush=True)
        pan = np.load(PANEL, allow_pickle=True)
        p = build_features(pan); F = catalogue(p)

    if a.holdout:
        hmask = window_mask(p.t, *HELDOUT)
        sel = [f for f in F if f[0] in set(a.holdout)]
        signs = {r_["name"]: r_["sign"] for r_ in res}
        hres, _ = run_window(sel, p, hmask, signs=signs)
        out["heldout"] = hres

    OUTJS.write_text(json.dumps(out, indent=1))
    write_md(out)
    print(json.dumps(dict(noise=out["noise_bar"], top=[{k: r[k] for k in
          ("name", "sharpe_net", "sharpe_gross", "breakeven_cost_bp_per_side")} for r in res[:8]]), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
