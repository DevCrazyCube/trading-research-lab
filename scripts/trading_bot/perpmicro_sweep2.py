#!/usr/bin/env python3
"""ROUND 2 of the crypto-perp microstructure sweep: ~50 formulas that are NOT in round 1.

Two things are different from round 1 and both are deliberate.

1. HEADLINE UNIVERSE IS TOP-50 BY VOLUME, not top-120.
   Round 1's single most important finding was that most of its "survivors" (XS_AMIHUD,
   XS_QV_Z, XS_NTR_Z, XS_ATS_Z, XS_LIQPROX, XS_CROWD_UNWIND) were illiquidity tilts living
   in the thin tail of the top-120 and went NEGATIVE out of sample on the top-50. So round 2
   designs on the top-50 from the start: every number here is one where a 5.5 bp/side fill
   is defensible.

2. A SECOND, VIRGIN HELD-OUT WINDOW: 2025-01-01 -> 2026-08-01.
   Round 1 evaluated all 56 of its formulas on 2024-04 -> 2025-01, so that window is burned.
   The Binance futures-METRICS feed (open interest, long/short ratios) stops at 2024-12 in
   the cache, which is why round 1 stopped there. But the 5m KLINES and the funding cache run
   to 2026-08. Every round-2 formula built only from price / volume / trade count / taker-buy
   volume / funding (class A) is therefore testable on 19 months that nothing in this theme
   has ever seen. Formulas that need the metrics feed (class B) can only use the burned
   window, and are labelled as such.

Everything else -- entry at the OPEN of the bar after the signal bar, H overlapping tranches,
funding accrual charged at the settlement bar, sign oriented on design and FROZEN out of
sample, sign-flip block-bootstrap noise bar -- is inherited unchanged from perpmicro_sweep.py.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import pathlib

import numpy as np

import perpmicro_sweep as ps
from perpmicro_sweep import (roll_sum, roll_mean, roll_std, roll_max, roll_min, lag, dlog,
                             zs, xrank, xz, evaluate, to_daily, sharpe, noise_bar,
                             weights_from_signal, window_mask, _corr, _worst_roll)

ROOT = pathlib.Path(__file__).resolve().parents[2]
PANEL_M = ROOT / "research" / "data" / "perpmicro_cache" / "panel1h.npz"       # with metrics
PANEL_X = ROOT / "research" / "data" / "perpmicro_cache" / "panel1h_ext_trim.npz"  # klines+funding
OUTDIR = ROOT / "research" / "trading_bot"

DESIGN = ("2023-01-01", "2024-04-01")
HOLD1 = ("2024-04-01", "2025-01-01")    # round 1 already used this on all 56 -> burned
HOLD2 = ("2025-01-01", "2026-08-01")    # VIRGIN. class-A formulas only.

N_ROUND1 = 56                            # for the cumulative multiple-testing count


# --------------------------------------------------------------------------- features
class P:
    pass


def build2(pan, has_metrics: bool, top_n: int, min_names: int):
    ps.TOP_N = top_n
    ps.MIN_NAMES = min_names
    p = P()
    p.sym = pan["symbols"]
    p.t = pan["t"]
    keys = ["o", "h", "l", "c", "qv", "ntr", "tbq", "fund", "fund_age_h", "fund_next_h"]
    if has_metrics:
        keys += ["oi", "oiv", "ttc", "tts", "glsr", "tlsr"]
    g = {k: pan[k].astype(np.float32) for k in keys}
    p.g = g
    p.has_metrics = has_metrics
    S, NH = g["c"].shape
    p.S, p.NH = S, NH

    o = g["o"]
    nxt = np.full_like(o, np.nan); nxt[:, :-1] = o[:, 1:]
    with np.errstate(invalid="ignore", divide="ignore"):
        p.ret = np.where((o > 0) & (nxt > 0), nxt / o - 1.0, 0.0).astype(np.float32)
    p.ret = np.clip(p.ret, -0.5, 0.5)

    qv7 = roll_sum(g["qv"], 168)
    liq_ok = np.isfinite(qv7) & np.isfinite(o) & (o > 0) & (g["qv"] > 0)
    v = np.where(liq_ok, qv7, -np.inf)
    ordr = np.argsort(-v, axis=0, kind="stable")
    rk = np.empty_like(ordr, dtype=np.int32)
    np.put_along_axis(rk, ordr, np.broadcast_to(np.arange(S, dtype=np.int32)[:, None],
                                                ordr.shape), axis=0)
    p.univ = liq_ok & (rk < top_n)
    U = p.univ

    # ---- returns / vol
    p.lc = np.log(np.where(g["c"] > 0, g["c"], np.nan)).astype(np.float32)
    p.r1 = (p.lc - lag(p.lc, 1)).astype(np.float32)
    p.r4 = (p.lc - lag(p.lc, 4)).astype(np.float32)
    p.r24 = (p.lc - lag(p.lc, 24)).astype(np.float32)
    p.r168 = (p.lc - lag(p.lc, 168)).astype(np.float32)
    p.rv24 = roll_std(p.r1, 24)
    p.rv168 = roll_std(p.r1, 168)

    # ---- market (equal-weight universe) return, for beta / residual work
    live = U.astype(np.float32)
    n = np.maximum(live.sum(0), 1)
    mr1 = (np.where(U & np.isfinite(p.r1), p.r1, 0.0).sum(0) / n).astype(np.float32)
    p.mr1 = mr1
    M = np.broadcast_to(mr1[None, :], (S, NH)).astype(np.float32)
    cov = roll_mean(p.r1 * M, 168) - roll_mean(p.r1, 168) * roll_mean(M, 168)
    var = roll_mean(M * M, 168) - roll_mean(M, 168) ** 2
    with np.errstate(invalid="ignore", divide="ignore"):
        p.beta = np.where(var > 0, cov / var, np.nan).astype(np.float32)
    p.resid1 = (p.r1 - p.beta * M).astype(np.float32)
    mR24 = np.broadcast_to((np.where(U & np.isfinite(p.r24), p.r24, 0.0).sum(0) / n
                            ).astype(np.float32)[None, :], (S, NH))
    mR168 = np.broadcast_to((np.where(U & np.isfinite(p.r168), p.r168, 0.0).sum(0) / n
                             ).astype(np.float32)[None, :], (S, NH))
    p.res24 = (p.r24 - p.beta * mR24).astype(np.float32)
    p.res168 = (p.r168 - p.beta * mR168).astype(np.float32)
    p.idiovol = roll_std(p.resid1, 168)

    # ---- return-distribution shape
    m1 = roll_mean(p.r1, 168); s1 = roll_std(p.r1, 168)
    with np.errstate(invalid="ignore", divide="ignore"):
        p.skew = np.where(s1 > 0, roll_mean((p.r1 - m1) ** 3, 168) / np.maximum(s1, 1e-12) ** 3,
                          np.nan).astype(np.float32)
        p.jumps = roll_mean((np.abs(p.r1) > 3.0 * lag(p.rv168, 1)).astype(np.float32), 168)
        ac = roll_mean(p.r1 * lag(p.r1, 1), 168) - m1 * roll_mean(lag(p.r1, 1), 168)
        p.ar1 = np.where(s1 > 0, ac / np.maximum(s1 * s1, 1e-14), np.nan).astype(np.float32)
        p.volvol = np.where(roll_mean(p.rv24, 168) > 0,
                            roll_std(p.rv24, 168) / np.maximum(roll_mean(p.rv24, 168), 1e-12),
                            np.nan).astype(np.float32)

    # ---- candle shape
    rng = (g["h"] - g["l"]).astype(np.float32)
    body_hi = np.maximum(g["o"], g["c"]); body_lo = np.minimum(g["o"], g["c"])
    with np.errstate(invalid="ignore", divide="ignore"):
        up = np.where(rng > 0, (g["h"] - body_hi) / rng, np.nan).astype(np.float32)
        dn = np.where(rng > 0, (body_lo - g["l"]) / rng, np.nan).astype(np.float32)
        bd = np.where(rng > 0, (body_hi - body_lo) / rng, np.nan).astype(np.float32)
        p.hlrange = np.where(g["c"] > 0, rng / g["c"], np.nan).astype(np.float32)
    p.upwick = roll_mean(up, 24)
    p.wickasym = roll_mean((dn - up).astype(np.float32), 24)
    p.bodyshare = roll_mean(bd, 24)
    p.range_z = zs(np.log(np.where(p.hlrange > 0, p.hlrange, np.nan)).astype(np.float32), 168)

    # ---- gaps between hourly bars (inter-bar jump vs continuous move)
    with np.errstate(invalid="ignore", divide="ignore"):
        lo_ = np.log(np.where(g["o"] > 0, g["o"], np.nan)).astype(np.float32)
    p.gap = (lo_ - lag(p.lc, 1)).astype(np.float32)
    p.gapsum = roll_sum(p.gap, 24)

    # ---- VWAP proxy
    tp = ((g["h"] + g["l"] + g["c"]) / 3.0).astype(np.float32)
    vw = roll_sum((tp * g["qv"]).astype(np.float32), 24)
    qs = roll_sum(g["qv"], 24)
    with np.errstate(invalid="ignore", divide="ignore"):
        vwap = np.where(qs > 0, vw / qs, np.nan).astype(np.float32)
        p.clvwap = np.where(vwap > 0, g["c"] / vwap - 1.0, np.nan).astype(np.float32)

    # ---- taker flow
    with np.errstate(invalid="ignore", divide="ignore"):
        p.ti1 = np.where(g["qv"] > 0, (2 * g["tbq"] - g["qv"]) / g["qv"], np.nan).astype(np.float32)
    tb24 = roll_sum(g["tbq"], 24); qq24 = roll_sum(g["qv"], 24)
    with np.errstate(invalid="ignore", divide="ignore"):
        p.ti24 = np.where(qq24 > 0, (2 * tb24 - qq24) / qq24, np.nan).astype(np.float32)
    p.qq24 = qq24
    p.flowaccel = (p.ti24 - lag(p.ti24, 24)).astype(np.float32)
    s_ti = np.sign(p.ti1).astype(np.float32)
    p.flowpersist = roll_mean((s_ti * lag(s_ti, 1)).astype(np.float32), 24)
    p.flowstreak = roll_mean((p.ti1 > 0).astype(np.float32), 24)
    with np.errstate(invalid="ignore", divide="ignore"):
        p.flow_va = np.where(p.rv24 > 0, p.ti24 / p.rv24, np.nan).astype(np.float32)

    # ---- price impact
    with np.errstate(invalid="ignore", divide="ignore"):
        num = roll_mean((p.r1 * p.ti1).astype(np.float32), 168)
        den = roll_mean((p.ti1 * p.ti1).astype(np.float32), 168)
        p.kyle = np.where(den > 0, num / den, np.nan).astype(np.float32)
        p.kyle_res = (np.abs(p.r24) - np.abs(p.kyle * roll_sum(p.ti1, 24))).astype(np.float32)
        p.illiq_trd = roll_mean(np.where(g["ntr"] > 0, np.abs(p.r1) / g["ntr"], np.nan
                                         ).astype(np.float32), 24)
        p.ats = np.where(g["ntr"] > 0, g["qv"] / g["ntr"], np.nan).astype(np.float32)
    lats = np.log(np.where(p.ats > 0, p.ats, np.nan)).astype(np.float32)
    p.ats_trend = (roll_mean(lats, 24) - roll_mean(lag(lats, 24), 24)).astype(np.float32)

    # ---- attention / rotation
    tot = np.where(U & np.isfinite(qq24), qq24, 0.0).sum(0)
    with np.errstate(invalid="ignore", divide="ignore"):
        p.volshare = np.where(tot[None, :] > 0, qq24 / np.maximum(tot[None, :], 1e-9),
                              np.nan).astype(np.float32)
    p.dvolshare = (dlog(p.volshare, 24)).astype(np.float32)

    # ---- funding path
    p.f = g["fund"]
    p.settle = (np.isfinite(g["fund_age_h"]) & (g["fund_age_h"] < 1.0))
    fs = np.where(p.settle & np.isfinite(p.f), p.f, 0.0).astype(np.float32)
    p.fpaid24 = roll_sum(fs, 24)
    p.fpaid168 = roll_sum(fs, 168)
    # funding settles 3x (later 6-24x) per day, so a settlement-stamped series is >85% empty and
    # the shared roll_sum() coverage gate (>=60% of the window observed) nulls it out. These two
    # need a gate on the number of SETTLEMENTS in the window, not on the number of hours.
    def _rawsum(a, w):
        z = np.zeros((a.shape[0], 1), np.float64)
        cs = np.concatenate([z, np.cumsum(np.where(np.isfinite(a), a, 0.0), axis=1, dtype=np.float64)],
                            axis=1)
        out = np.full(a.shape, np.nan, np.float64)
        out[:, w - 1:] = cs[:, w:] - cs[:, :-w]
        return out

    sg = np.where(p.settle & np.isfinite(p.f), np.sign(p.f), 0.0).astype(np.float32)
    have = (p.settle & np.isfinite(p.f)).astype(np.float32)
    nset = _rawsum(have, 168)
    with np.errstate(invalid="ignore", divide="ignore"):
        p.fpersist = np.where(nset >= 12, _rawsum(sg, 168) / np.maximum(nset, 1), np.nan
                              ).astype(np.float32)
    # sign flips between CONSECUTIVE settlements: compare each settlement to the previous one
    prev = np.full_like(sg, 0.0)
    last = np.zeros(sg.shape[0], np.float32)
    for j in range(sg.shape[1]):
        prev[:, j] = last
        h = have[:, j] > 0
        last = np.where(h, sg[:, j], last)
    flip = ((sg * prev < 0) & (have > 0)).astype(np.float32)
    with np.errstate(invalid="ignore", divide="ignore"):
        p.fflip = np.where(nset >= 12, _rawsum(flip, 168) / np.maximum(nset, 1), np.nan
                           ).astype(np.float32)
    p.fpath_rev = (xz(p.fpaid168, U) - xz(p.r168, U)).astype(np.float32)

    # ---- calendar
    hod = ((p.t // ps.HOUR) % 24).astype(np.int64)
    dow = (((p.t // ps.HOUR) // 24 + 3) % 7).astype(np.int64)   # 1970-01-01 = Thu -> 0=Mon
    p.hod, p.dow = hod, dow

    # ---- metrics-only block
    if has_metrics:
        def L(a):
            return np.log(np.where(a > 0, a, np.nan)).astype(np.float32)
        p.lg = L(g["glsr"]); p.lt = L(g["tts"]); p.ltc = L(g["ttc"]); p.ltl = L(g["tlsr"])
        p.smart = (p.lt - p.lg).astype(np.float32)
        p.doiu24 = dlog(g["oi"], 24)
        p.doiu1 = dlog(g["oi"], 1)
        p.doi_acc = (p.doiu24 - lag(p.doiu24, 24)).astype(np.float32)
        p.lg_slow = (p.lg - roll_mean(p.lg, 720)).astype(np.float32)
        p.lg_acc = ((p.lg - lag(p.lg, 24)) - (lag(p.lg, 24) - lag(p.lg, 48))).astype(np.float32)
        # forced-liquidation intensity: OI destroyed in an hour whose range is abnormally wide
        casc = np.where((p.doiu1 < 0) & np.isfinite(p.range_z),
                        (-p.doiu1) * np.maximum(p.range_z, 0.0), 0.0).astype(np.float32)
        p.cascade = roll_sum(casc, 24)
        p.oi_per_acct = (p.doiu24 - dlog(g["glsr"], 24)).astype(np.float32)
    return p


# --------------------------------------------------------------------------- catalogue
def catalogue2(p):
    """(name, signal, H, scheme, time-mask, class, description). class A = klines+funding only."""
    F = []
    A = F.append
    U = p.univ
    S, NH = p.S, p.NH
    ones = np.ones((S, NH), np.float32)

    # ================= candle / intrabar shape =================
    A(("X2_UPWICK", p.upwick, 24, "quintile", None, "A",
       "24h mean UPPER-wick share of the hourly range: supply hitting rallies"))
    A(("X2_WICKASYM", p.wickasym, 24, "quintile", None, "A",
       "24h mean (lower wick - upper wick)/range: which tail is being bought"))
    A(("X2_BODY", p.bodyshare, 24, "quintile", None, "A",
       "24h mean body/range: how much of the hour's range the net move kept (trend efficiency)"))
    A(("X2_GAPSUM", p.gapsum, 24, "quintile", None, "A",
       "24h sum of bar-to-bar gaps log(open_t)-log(close_t-1): jump flow vs continuous flow"))
    A(("X2_CLVWAP", p.clvwap, 24, "quintile", None, "A",
       "close vs 24h volume-weighted average price: where the marginal buyer sits"))
    A(("X2_RANGE_Z", p.range_z, 24, "quintile", None, "A",
       "z of log hourly high-low range vs own 7d (range expansion, not return vol)"))

    # ================= price impact / liquidity =================
    A(("X2_KYLE", p.kyle, 24, "quintile", None, "A",
       "Kyle lambda: 7d regression slope of 1h return on taker imbalance (impact per unit flow)"))
    A(("X2_KYLE_RES", p.kyle_res, 24, "quintile", None, "A",
       "24h move in excess of what its own Kyle lambda x realised flow explains (unsponsored move)"))
    A(("X2_ILLIQ_TRD", p.illiq_trd, 24, "quintile", None, "A",
       "|return| per TRADE rather than per notional (impact per ticket, size-free)"))

    # ================= flow structure =================
    A(("X2_FLOWPERSIST", p.flowpersist, 24, "quintile", None, "A",
       "24h mean sign agreement of consecutive hourly taker imbalances (order-flow autocorrelation)"))
    A(("X2_FLOWSTREAK", p.flowstreak, 24, "quintile", None, "A",
       "fraction of the last 24 hours with net taker BUYING (one-sidedness, not magnitude)"))
    A(("X2_FLOWACCEL", p.flowaccel, 24, "quintile", None, "A",
       "24h taker imbalance minus its own value 24h ago (flow acceleration)"))
    A(("X2_FLOW_VA", p.flow_va, 24, "quintile", None, "A",
       "24h taker imbalance divided by realised vol (aggression per unit of price response)"))
    A(("X2_FLOW_QUIET", np.where(xz(np.abs(p.r24), U) < 0.0, p.ti24, np.nan
                                 ).astype(np.float32), 24, "quintile", None, "A",
       "taker imbalance ONLY in names whose 24h move was below the cross-sec average (absorbed flow)"))

    # ================= return-distribution shape =================
    A(("X2_SKEW", p.skew, 24, "quintile", None, "A", "7d skewness of hourly returns (crash-prone names)"))
    A(("X2_JUMPS", p.jumps, 24, "quintile", None, "A",
       "fraction of the last 7d of hours that were >3-sigma jumps (jumpiness, not variance)"))
    A(("X2_AR1", p.ar1, 24, "quintile", None, "A",
       "own 7d 1h-return autocorrelation: trending vs mean-reverting microstructure"))
    A(("X2_VOLVOL", p.volvol, 24, "quintile", None, "A",
       "vol-of-vol: 7d std of the rolling 24h vol, scaled by its mean"))

    # ================= beta / residual =================
    A(("X2_BETA", p.beta, 24, "quintile", None, "A",
       "7d beta to the equal-weight perp basket (cross-sectional bet-against-beta)"))
    A(("X2_RESID_REV", -p.res24, 24, "quintile", None, "A",
       "reversal of the BETA-ADJUSTED 24h return (idiosyncratic reversal)"))
    A(("X2_RESID_MOM", p.res168, 24, "quintile", None, "A",
       "beta-adjusted 7d momentum (idiosyncratic momentum)"))
    A(("X2_IDIOVOL", p.idiovol, 24, "quintile", None, "A",
       "7d residual (idiosyncratic) volatility after removing the basket"))

    # ================= attention / rotation =================
    A(("X2_VOLSHARE", p.volshare, 24, "quintile", None, "A",
       "the symbol's share of total universe quote volume (attention dominance LEVEL)"))
    A(("X2_DVOLSHARE", p.dvolshare, 24, "quintile", None, "A",
       "24h log change in volume share (attention ROTATING into the name)"))
    A(("X2_ATS_TREND", p.ats_trend, 24, "quintile", None, "A",
       "24h change in mean trade size: tickets getting bigger (whales arriving) or smaller (retail)"))

    # ================= funding PATH (not level) =================
    A(("X2_FUNDPAID24", p.fpaid24, 24, "quintile", None, "A",
       "funding actually PAID over the last 24h (sum over settlements, not the last rate)"))
    A(("X2_FUNDPAID168", p.fpaid168, 24, "quintile", None, "A",
       "funding actually paid over the last 7d (slow realised carry)"))
    A(("X2_FUNDPERSIST", p.fpersist, 24, "quintile", None, "A",
       "fraction of the last 7d of settlements with POSITIVE funding (sign persistence, magnitude-free)"))
    A(("X2_FUNDFLIP", p.fflip, 24, "quintile", None, "A",
       "rate at which the funding SIGN flipped over 7d (carry-regime instability)"))
    A(("X2_FUNDPATH_REV", p.fpath_rev, 24, "quintile", None, "A",
       "7d realised funding paid minus 7d return: carry the price never justified"))

    # ================= time-of-day conditioning =================
    A(("X2_TOD_REV_ASIA", -p.r24, 24, "quintile", p.hod < 8, "A",
       "24h cross-sectional reversal held ONLY during 00-08 UTC (Asia session)"))
    A(("X2_TOD_MOM_US", p.r4, 4, "quintile", (p.hod >= 13) & (p.hod < 21), "A",
       "4h cross-sectional momentum held ONLY during 13-21 UTC (US session)"))
    A(("X2_TOD_FLOW_EU", p.ti24, 24, "quintile", (p.hod >= 7) & (p.hod < 15), "A",
       "24h taker imbalance held ONLY during 07-15 UTC (Europe session)"))

    # ================= time-series (basket timing) =================
    z1 = lambda v: zs(np.asarray(v, np.float32)[None, :], 720)[0]
    live = U.astype(np.float32)
    nlive = np.maximum(live.sum(0), 1)
    up24 = (np.where(U & np.isfinite(p.r24), (p.r24 > 0).astype(np.float32), 0.0).sum(0)
            / nlive).astype(np.float32)
    disp = np.array([np.nanstd(np.where(U[:, j] & np.isfinite(p.r24[:, j]), p.r24[:, j], np.nan))
                     if U[:, j].sum() > 5 else np.nan for j in range(NH)], np.float32)
    mvol = (np.where(U & np.isfinite(p.rv24), p.rv24, 0.0).sum(0) / nlive).astype(np.float32)
    mret = (np.where(U & np.isfinite(p.r24), p.r24, 0.0).sum(0) / nlive).astype(np.float32)
    mflowp = (np.where(U & np.isfinite(p.flowpersist), p.flowpersist, 0.0).sum(0)
              / nlive).astype(np.float32)
    A(("T2_BREADTH", ones * z1(up24)[None, :], 24, "ts", None, "A",
       "TIME-SERIES: z of the fraction of the universe up over 24h (breadth regime)"))
    A(("T2_DISPERSION", ones * z1(disp)[None, :], 24, "ts", None, "A",
       "TIME-SERIES: z of the cross-sectional dispersion of 24h returns"))
    A(("T2_MKTVOL", ones * z1(mvol)[None, :], 24, "ts", None, "A",
       "TIME-SERIES: z of universe-mean realised vol (vol-regime basket timing)"))
    A(("T2_MKTREV", ones * z1(mret)[None, :], 24, "ts", None, "A",
       "TIME-SERIES: z of universe-mean 24h return (basket momentum/reversal timing)"))
    A(("T2_MKTFLOWP", ones * z1(mflowp)[None, :], 24, "ts", None, "A",
       "TIME-SERIES: z of universe-mean order-flow autocorrelation (market trending-ness)"))
    A(("T2_WEEKEND", ones * np.where(p.dow >= 5, 1.0, -1.0).astype(np.float32)[None, :], 24,
       "ts", None, "A", "TIME-SERIES: long the basket on Sat/Sun, short Mon-Fri"))

    if not p.has_metrics:
        return F

    # ================= class B: needs the Binance futures-metrics feed =================
    A(("X2_CASCADE", p.cascade, 24, "quintile", None, "B",
       "24h forced-liquidation intensity: OI destroyed in hours whose range was abnormally wide"))
    A(("X2_LONGLIQ", (xz(-p.doiu24, U) * xz(-p.r24, U)).astype(np.float32), 24, "quintile", None, "B",
       "PRODUCT (conjunction) of OI destroyed AND price down: long liquidation, not voluntary exit"))
    A(("X2_CROWDCONJ", (xz(p.lg, U) * xz(-p.doiu24, U)).astype(np.float32), 24, "quintile", None, "B",
       "PRODUCT of retail crowding and OI destruction (round 1 only tested the SUM)"))
    A(("X2_OI_VS_FLOW", (xz(p.doiu24, U) * np.sign(xz(p.ti24, U))).astype(np.float32), 24,
       "quintile", None, "B",
       "OI growth SIGNED by the direction of the aggressor flow that built it (new longs vs new shorts)"))
    A(("X2_RETAIL_VS_TAKER", (xz(p.lg, U) - xz(p.ltl, U)).astype(np.float32), 24, "quintile", None, "B",
       "accounts positioned long while the aggressor flow sells (positioning/flow divergence)"))
    A(("X2_GLSR_SLOW", p.lg_slow, 24, "quintile", None, "B",
       "global L/S ratio vs its own 30d mean (SLOW crowding; round 1 used a 7d z)"))
    A(("X2_GLSR_ACCEL", p.lg_acc, 24, "quintile", None, "B",
       "second difference of the global L/S ratio (crowding acceleration)"))
    A(("X2_CROWD_x_VOL", (xz(p.lg, U) * xz(p.rv24, U)).astype(np.float32), 24, "quintile", None, "B",
       "crowded AND volatile: crowding weighted by how fragile the name is"))
    A(("X2_OI_PER_ACCT", p.oi_per_acct, 24, "quintile", None, "B",
       "OI growth in excess of account-count growth (position size per account rising)"))
    A(("X2_GLSR_ASIA", p.lg, 24, "quintile", p.hod < 8, "B",
       "retail crowding signal held ONLY 00-08 UTC (is the fade an Asia-hours effect?)"))
    A(("X2_SMART_CONF", np.where(np.abs(zs(p.smart, 720)) > 1.0, p.smart, np.nan).astype(np.float32),
       24, "quintile", None, "B",
       "smart-vs-crowd spread, but only in names where the spread is >1sd from its own 30d norm"))
    mglsr = (np.where(U & np.isfinite(p.lg), p.lg, 0.0).sum(0) / nlive).astype(np.float32)
    A(("T2_MKT_GLSR", ones * z1(mglsr)[None, :], 24, "ts", None, "B",
       "TIME-SERIES: z of universe-mean retail long/short ratio (aggregate positioning timing)"))
    return F


# --------------------------------------------------------------------------- run
def run_window(F, p, wmask, cost_bp, signs=None):
    NH = p.NH
    ndays = NH // 24
    dm = wmask[:ndays * 24].reshape(-1, 24).any(axis=1)
    yrs = np.array([dt.datetime.fromtimestamp(x / 1000, dt.timezone.utc).year
                    for x in p.t[:ndays * 24:24]])[dm]
    nlive = np.maximum(p.univ.sum(0), 1)
    mkt_h = (np.where(p.univ, p.ret, 0.0).sum(axis=0) / nlive).astype(np.float64)
    mkt_d = to_daily(mkt_h, NH)[dm]
    res, mat = [], []
    for name, x, H, scheme, tmask, cls, desc in F:
        if x.ndim == 1:
            x = np.broadcast_to(x[None, :], (p.S, p.NH))
        x = np.ascontiguousarray(x.astype(np.float32))
        tm = np.asarray(tmask) if (tmask is not None and np.ndim(tmask) == 1) else None
        pnl, pf, dh = evaluate(x, p, H, scheme, tm)
        dp = to_daily(pnl, NH)[dm]; df = to_daily(pf, NH)[dm]; dtn = to_daily(dh, NH)[dm]
        gross = dp + df
        if signs is not None and name in signs:
            s = float(signs[name])
        else:
            s = 1.0 if np.nanmean(gross) >= 0 else -1.0
        og = s * gross
        cost = dtn * cost_bp * 1e-4
        net = og - cost
        tpd = float(np.nanmean(dtn))
        be = float(np.nanmean(og) / tpd * 1e4) if tpd > 0 else float("nan")
        res.append(dict(name=name, desc=desc, cls=cls, H=H, scheme=scheme, sign=s,
                        sharpe_gross=sharpe(og), sharpe_net=sharpe(net),
                        ann_ret_gross=float(np.nanmean(og) * 365),
                        ann_ret_net=float(np.nanmean(net) * 365),
                        turnover_per_day=tpd, breakeven_cost_bp_per_side=be,
                        ndays=int(len(net)), corr_market=_corr(og, mkt_d),
                        hit_rate=float(np.mean(net > 0)),
                        worst_60d_net=float(_worst_roll(net, 60)),
                        net_sharpe_by_year={int(y): sharpe(net[yrs == y])
                                            for y in np.unique(yrs)}))
        mat.append(gross)
    return res, np.array(mat)


def audit(pan, has_metrics, top_n, min_names, cut_frac=0.6, slice_h=0):
    """destroy every input after bar K, re-derive, and assert no weight at t<K moves."""
    raw = {k: pan[k] for k in pan.files}
    if slice_h:
        raw = {k: (v[..., :slice_h] if k != "symbols" else v) for k, v in raw.items()}
    K = int(raw["c"].shape[1] * cut_frac)
    trunc = dict(raw)
    for k in raw:
        if k in ("t", "symbols"):
            continue
        a = raw[k].copy().astype(np.float32); a[:, K:] = np.nan
        trunc[k] = a
    pa = build2(raw, has_metrics, top_n, min_names)
    pb = build2(trunc, has_metrics, top_n, min_names)
    Fa, Fb = catalogue2(pa), catalogue2(pb)
    bad = []
    for (na, xa, H, sc, tm, cl, _), (nb, xb, *_r) in zip(Fa, Fb):
        xa = np.ascontiguousarray(np.broadcast_to(xa, (pa.S, pa.NH)).astype(np.float32))
        xb = np.ascontiguousarray(np.broadcast_to(xb, (pa.S, pa.NH)).astype(np.float32))
        wa = weights_from_signal(xa, pa.univ, sc)[:, :K - 1]
        wb = weights_from_signal(xb, pb.univ, sc)[:, :K - 1]
        d = float(np.nanmax(np.abs(wa - wb))) if wa.size else 0.0
        if not (d <= 1e-6):
            bad.append((na, d))
    return dict(cut_bar=K, n_checked=len(Fa), violations=bad)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--panel", choices=["metrics", "ext"], default="metrics")
    ap.add_argument("--top", type=int, default=50)
    ap.add_argument("--minnames", type=int, default=25)
    ap.add_argument("--cost", type=float, default=5.5)
    ap.add_argument("--stage", choices=["design", "holdout"], default="design")
    ap.add_argument("--audit", action="store_true")
    ap.add_argument("--auditonly", action="store_true")
    ap.add_argument("--auditslice", type=int, default=0,
                    help="restrict the lookahead audit to the first N hours (memory)")
    a = ap.parse_args()

    pth = PANEL_M if a.panel == "metrics" else PANEL_X
    has_m = (a.panel == "metrics")
    pan = np.load(pth, allow_pickle=True)
    tag = f"{a.panel}_top{a.top}"
    if a.auditonly:
        r = audit(pan, has_m, a.top, a.minnames, slice_h=a.auditslice)
        (OUTDIR / f"SWEEP_crypto_perp_microstructure_R2_{tag}_audit.json").write_text(
            json.dumps(r, indent=1))
        print("AUDIT", r["n_checked"], "violations:", r["violations"], flush=True)
        return 0
    p = build2(pan, has_m, a.top, a.minnames)
    F = catalogue2(p)
    print(f"[{tag}] panel {p.S}x{p.NH}; {len(F)} formulas", flush=True)

    dmask = window_mask(p.t, *DESIGN)
    res, mat = run_window(F, p, dmask, a.cost)
    nb = noise_bar(mat)
    N = len(F)
    Ty = mat.shape[1] / 365.0
    out = dict(theme="crypto_perp_microstructure_round2", panel=a.panel, top_n=a.top,
               cost_bp_per_side=a.cost,
               design_window=list(DESIGN), holdout1=list(HOLD1), holdout2=list(HOLD2),
               n_formulas_round2=N, n_formulas_cumulative=N + N_ROUND1,
               design_days=int(mat.shape[1]),
               noise_bar=dict(bootstrap=nb,
                              analytic_round2=math.sqrt(2 * math.log(2 * N)) / math.sqrt(Ty),
                              analytic_cumulative=math.sqrt(2 * math.log(2 * (N + N_ROUND1)))
                              / math.sqrt(Ty)),
               design=sorted(res, key=lambda r: -(r["sharpe_gross"] if
                                                  np.isfinite(r["sharpe_gross"]) else 0)))
    if a.audit:
        out["lookahead_audit"] = audit(pan, has_m, a.top, a.minnames, slice_h=a.auditslice)
        print("AUDIT", out["lookahead_audit"]["n_checked"],
              "violations:", out["lookahead_audit"]["violations"], flush=True)

    if a.stage == "holdout":
        signs = {r["name"]: r["sign"] for r in res}
        h1, _ = run_window(F, p, window_mask(p.t, *HOLD1), a.cost, signs=signs)
        out["heldout1"] = h1
        if not has_m:
            h2, _ = run_window(F, p, window_mask(p.t, *HOLD2), a.cost, signs=signs)
            out["heldout2"] = h2
            h2c, _ = run_window(F, p, window_mask(p.t, *HOLD2), 15.0, signs=signs)
            out["heldout2_cost15"] = h2c
        h1c, _ = run_window(F, p, window_mask(p.t, *HOLD1), 15.0, signs=signs)
        out["heldout1_cost15"] = h1c

    fn = OUTDIR / f"SWEEP_crypto_perp_microstructure_R2_{tag}_{a.stage}.json"
    fn.write_text(json.dumps(out, indent=1))
    print("wrote", fn, flush=True)
    print(json.dumps(dict(noise=out["noise_bar"],
                          top=[{k: r[k] for k in ("name", "cls", "sharpe_gross", "sharpe_net",
                                                  "breakeven_cost_bp_per_side")}
                               for r in out["design"][:10]]), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
