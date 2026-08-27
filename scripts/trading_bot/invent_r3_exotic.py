#!/usr/bin/env python3
"""INVENT ROUND 3 -- theme: EXOTIC / LEFT-FIELD original signals on free data.

27 formulas in six families that the 598-formula programme has NOT searched:

  A  new-listing first-week dynamics on Binance USD-M perps     (6)
  B  weekend / week-structure with cross-sectional structure     (5)
  C  vol-of-vol beyond a plain cross-sectional rank              (4)
  D  cross-crypto dispersion / average-correlation REGIMES       (5)
  E  positioning-crowding aggregates as PRIMARY signals          (4)
  F  stablecoin mint/burn impulse -> crypto direction            (3)

Data (all free, all already local except one DefiLlama pull):
  research/data/invr3_cache/daily.npz   -- daily UTC roll-up of perpmicro_cache/panel1h_ext.npz
  research/data/invr3_cache/sc_all.json -- DefiLlama aggregate stablecoin circulating supply

Conventions inherited from perpmicro_sweep.py so the numbers are comparable:
  * signal formed from data through the CLOSE of day d, entered at the OPEN of day d+1
  * H overlapping daily tranches, each 1/H of the book
  * funding charged at the settlement bars inside each held day (a long pays positive funding)
  * taker cost charged on |turnover| at cost_bp per side
  * sign oriented on the DESIGN window and FROZEN for the held-out window
  * headline liquid universe = top 50 by trailing 7-day quote volume

Windows:
  DESIGN  2022-01-01 -> 2025-01-01
  HELDOUT 2025-01-01 -> 2026-07-31   (never seen by these six families)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import pathlib

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[2]
CACHE = ROOT / "research" / "data" / "invr3_cache"
OUTDIR = ROOT / "research" / "trading_bot"

DESIGN = ("2022-01-01", "2025-01-01")
HELD = ("2025-01-01", "2026-07-31")

TOP_N = 50
MIN_NAMES = 20
COST_LIQ = 5.5        # bp/side, top-50 perp taker (perpmicro convention)
COST_LIQ_SHOCK = 15.0
COST_NEW = 20.0       # bp/side for the new-listing cohort (thin, hyped, wide)
COST_NEW_SHOCK = 40.0

EPOCH = dt.date(1970, 1, 1)


# ------------------------------------------------------------------ small helpers
def roll_sum(a, w):
    c = np.nancumsum(np.where(np.isfinite(a), a, 0.0), axis=1)
    out = np.full_like(a, np.nan, dtype=np.float32)
    out[:, w - 1:] = c[:, w - 1:] - np.concatenate(
        [np.zeros((a.shape[0], 1)), c[:, :-w]], axis=1)
    return out


def roll_mean(a, w, min_n=None):
    if min_n is None:
        min_n = max(3, w // 2)
    fin = np.isfinite(a).astype(np.float32)
    s = roll_sum(np.where(np.isfinite(a), a, 0.0), w)
    n = roll_sum(fin, w)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(n >= min_n, s / np.maximum(n, 1), np.nan).astype(np.float32)


def roll_std(a, w, min_n=None):
    m = roll_mean(a, w, min_n)
    m2 = roll_mean(a * a, w, min_n)
    v = m2 - m * m
    return np.sqrt(np.maximum(v, 0.0)).astype(np.float32)


def lag(a, k):
    out = np.full_like(a, np.nan)
    if k > 0:
        out[:, k:] = a[:, :-k]
    elif k == 0:
        out = a.copy()
    return out


def lag1(v, k):
    out = np.full_like(v, np.nan)
    if k > 0:
        out[k:] = v[:-k]
    return out


def zs(a, w):
    m = roll_mean(a, w)
    s = roll_std(a, w)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(s > 0, (a - m) / np.maximum(s, 1e-12), np.nan).astype(np.float32)


def zs1(v, w):
    a = v[None, :].astype(np.float32)
    return zs(a, w)[0]


def sharpe(d):
    d = np.asarray(d, float)
    d = d[np.isfinite(d)]
    if len(d) < 90 or d.std() == 0:
        return float("nan")
    return float(d.mean() / d.std() * math.sqrt(365))


def tstat(d):
    d = np.asarray(d, float)
    d = d[np.isfinite(d)]
    if len(d) < 90 or d.std() == 0:
        return float("nan")
    return float(d.mean() / (d.std() / math.sqrt(len(d))))


def dstr(x):
    return (EPOCH + dt.timedelta(days=int(x))).isoformat()


def dnum(s):
    y, m, d = (int(v) for v in s.split("-"))
    return (dt.date(y, m, d) - EPOCH).days


# ------------------------------------------------------------------ panel
class P:
    pass


def build():
    z = np.load(CACHE / "daily.npz", allow_pickle=True)
    p = P()
    p.sym = z["symbols"]
    p.day = z["day"].astype(np.int64)
    g = {k: z[k].astype(np.float32) for k in ("o", "h", "l", "c", "qv", "ntr", "tbq",
                                              "fnd", "nsettle", "nh")}
    p.g = g
    S, ND = g["c"].shape
    p.S, p.ND = S, ND

    o = g["o"]
    nxt = np.full_like(o, np.nan)
    nxt[:, :-1] = o[:, 1:]
    with np.errstate(invalid="ignore", divide="ignore"):
        r = np.where((o > 0) & (nxt > 0), nxt / o - 1.0, np.nan)
    p.roo = np.clip(r, -0.5, 0.5).astype(np.float32)          # open(d)->open(d+1)

    lc = np.log(np.where(g["c"] > 0, g["c"], np.nan)).astype(np.float32)
    p.lc = lc
    p.r1 = (lc - lag(lc, 1)).astype(np.float32)
    p.r3 = (lc - lag(lc, 3)).astype(np.float32)
    p.r7 = (lc - lag(lc, 7)).astype(np.float32)

    # ---- liquid universe: top-N by trailing 7d quote volume, data-complete
    qv7 = roll_sum(g["qv"], 7)
    ok = (np.isfinite(qv7) & (qv7 > 0) & (g["nh"] >= 20) & np.isfinite(o) & (o > 0)
          & np.isfinite(nxt) & (nxt > 0) & np.isfinite(p.r1))
    v = np.where(ok, qv7, -np.inf)
    ordr = np.argsort(-v, axis=0, kind="stable")
    rk = np.empty_like(ordr, dtype=np.int32)
    np.put_along_axis(rk, ordr, np.broadcast_to(
        np.arange(S, dtype=np.int32)[:, None], ordr.shape), axis=0)
    p.univ = ok & (rk < TOP_N)
    p.tradable = ok

    # ---- listing age (days since first finite close bar in the panel)
    fin = np.isfinite(g["c"])
    first = np.argmax(fin, axis=1)
    first[~fin.any(axis=1)] = 10 ** 6
    p.first = first
    idx = np.arange(ND)[None, :]
    p.age = (idx - first[:, None]).astype(np.float32)          # 0 on the listing day
    p.age[p.age < 0] = np.nan

    # a first bar landing on the 1st of a month is far more likely to be a
    # DOWNLOAD boundary (Binance monthly archives) than a real listing day
    firstday = np.array([p.day[min(f, ND - 1)] if f < ND else -1 for f in first])
    dom = np.array([(EPOCH + dt.timedelta(days=int(x))).day if x > 0 else 1 for x in firstday])
    p.real_listing = (dom > 1) & (first > 5) & (first < ND - 40)
    # partial first day is corroborating evidence of a genuine listing
    p.first_nh = np.array([g["nh"][i, first[i]] if first[i] < ND else np.nan
                           for i in range(S)], dtype=np.float32)

    # ---- market aggregates on the liquid universe
    U = p.univ
    n = np.maximum(U.sum(0), 1).astype(np.float32)
    p.nlive = U.sum(0)
    p.mr1 = (np.where(U & np.isfinite(p.r1), p.r1, 0.0).sum(0) / n).astype(np.float32)
    p.mroo = (np.where(U & np.isfinite(p.roo), p.roo, 0.0).sum(0) / n).astype(np.float32)

    # cross-sectional dispersion of daily returns over the live universe
    dev = np.where(U & np.isfinite(p.r1), p.r1 - p.mr1[None, :], np.nan)
    p.disp = np.sqrt(np.nanmean(dev ** 2, axis=0)).astype(np.float32)

    # ---- vol / vol-of-vol
    p.rv5 = roll_std(p.r1, 5)
    p.rv20 = roll_std(p.r1, 20)
    with np.errstate(invalid="ignore", divide="ignore"):
        p.vov_s = np.where(roll_mean(p.rv5, 10) > 0,
                           roll_std(p.rv5, 10) / np.maximum(roll_mean(p.rv5, 10), 1e-9),
                           np.nan).astype(np.float32)
        p.vov_l = np.where(roll_mean(p.rv5, 40) > 0,
                           roll_std(p.rv5, 40) / np.maximum(roll_mean(p.rv5, 40), 1e-9),
                           np.nan).astype(np.float32)

    # ---- beta / correlation to the equal-weight market
    M = np.broadcast_to(p.mr1[None, :], (S, ND)).astype(np.float32)
    for w, tag in ((20, "20"), (60, "60")):
        cov = roll_mean(p.r1 * M, w) - roll_mean(p.r1, w) * roll_mean(M, w)
        sa = roll_std(p.r1, w)
        sb = roll_std(M, w)
        with np.errstate(invalid="ignore", divide="ignore"):
            setattr(p, "corr" + tag, np.where((sa > 0) & (sb > 0),
                                              cov / np.maximum(sa * sb, 1e-14),
                                              np.nan).astype(np.float32))
    # aggregate implied correlation: var(market) / mean(var(name))
    mv = roll_std(M, 20)[0] ** 2
    av = np.nanmean(np.where(U, p.rv20 ** 2, np.nan), axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        p.avgcorr = np.where(av > 0, mv / np.maximum(av, 1e-18), np.nan).astype(np.float32)

    # ---- flow
    with np.errstate(invalid="ignore", divide="ignore"):
        p.tbr = np.where(g["qv"] > 0, g["tbq"] / np.maximum(g["qv"], 1e-9) - 0.5,
                         np.nan).astype(np.float32)

    # ---- calendar
    p.wd = ((p.day + 3) % 7).astype(np.int32)      # Mon=0 ... Sun=6
    return p


# ------------------------------------------------------------------ book machinery
def quintile_weights(x, mask, frac=0.2):
    S, ND = x.shape
    w = np.zeros((S, ND), np.float32)
    valid = mask & np.isfinite(x)
    xv = np.where(valid, x, np.nan)
    for d in range(ND):
        idx = np.flatnonzero(valid[:, d])
        if len(idx) < MIN_NAMES:
            continue
        v = xv[idx, d]
        order = idx[np.argsort(v, kind="stable")]
        k = max(2, int(round(len(idx) * frac)))
        w[order[-k:], d] = 1.0 / k
        w[order[:k], d] = -1.0 / k
    return w


def hold_from(w, H):
    S, ND = w.shape
    hold = np.zeros((S, ND), np.float32)
    for k in range(H):
        sh = np.zeros_like(w)
        if 1 + k < ND:
            sh[:, 1 + k:] = w[:, : ND - 1 - k]
        hold += sh / H
    return hold


def run_book(p, w, H, cost_bp):
    hold = hold_from(w, H)
    r = np.where(np.isfinite(p.roo), p.roo, 0.0)
    pnl = (hold * r).sum(axis=0)
    fnd = np.where(np.isfinite(p.g["fnd"]), p.g["fnd"], 0.0)
    pnl_f = -(hold * fnd).sum(axis=0)
    tno = np.abs(np.diff(hold, axis=1, prepend=0.0)).sum(axis=0)
    gross = pnl + pnl_f
    net = gross - tno * cost_bp * 1e-4
    return dict(gross=gross.astype(np.float64), net=net.astype(np.float64),
                tno=tno.astype(np.float64), price=pnl.astype(np.float64),
                fund=pnl_f.astype(np.float64), hold=hold)


def window_mask(p, lo, hi):
    return (p.day >= dnum(lo)) & (p.day < dnum(hi))


# ------------------------------------------------------------------ formulas
def catalogue(p):
    """returns list of (name, family, weights SxND, H, cost_bp, description)"""
    F = []
    A = F.append
    S, ND = p.S, p.ND
    U = p.univ

    # ============================================================ FAMILY A -- new listings
    # cohort = symbols whose first panel bar looks like a genuine mid-month listing,
    # with a minimum liquidity floor so the book is at least nominally executable
    qv3 = roll_mean(p.g["qv"], 3)
    liq_new = np.isfinite(qv3) & (qv3 > 3e6) & (p.g["nh"] >= 20) & p.tradable
    RL = p.real_listing[:, None]
    age = p.age

    def cohort(lo_age, hi_age):
        return RL & (age >= lo_age) & (age <= hi_age) & liq_new

    ones = np.ones((S, ND), np.float32)
    coh = cohort(1, 7)
    coh2 = cohort(8, 30)
    A(("A1_NL_WEEK1_HEDGED", "A_newlisting", cohort_book(p, ones, coh), 1, COST_NEW,
       "long the equal-weight cohort of perps aged 1-7 days since listing, short the "
       "equal-weight top-50 liquid basket, 1-day hold"))
    A(("A2_NL_MONTH1_HEDGED", "A_newlisting", cohort_book(p, ones, coh2), 3, COST_NEW,
       "long the cohort of perps aged 8-30 days since listing, hedged with the liquid "
       "basket, 3-day hold (the post-hype month)"))

    # day-1 (first full day) return, frozen per symbol
    d1ret = np.full((S, ND), np.nan, np.float32)
    for i in range(S):
        f = p.first[i]
        if p.real_listing[i] and f + 2 < ND:
            d1ret[i, f + 2:] = p.lc[i, f + 1] - p.lc[i, f]
    A(("A3_NL_D1_FADE", "A_newlisting", cohort_book(p, -d1ret, coh), 3, COST_NEW,
       "inside the aged 1-7d cohort, take the OPPOSITE side of each new perp's first "
       "full-day return (fade the listing-day move), hedged, 3-day hold"))

    # cumulative funding paid since listing -- positioning at birth
    fsum = np.full((S, ND), np.nan, np.float32)
    cf = np.nancumsum(np.where(np.isfinite(p.g["fnd"]), p.g["fnd"], 0.0), axis=1)
    for i in range(S):
        f = p.first[i]
        if f < ND:
            fsum[i, f:] = cf[i, f:] - cf[i, f]
    A(("A4_NL_FUND_SIGN", "A_newlisting", cohort_book(p, -fsum, coh), 3, COST_NEW,
       "inside the cohort, SHORT the new perps that have paid positive cumulative "
       "funding since listing (crowded-long births) and long the rest, hedged, 3-day hold"))

    # attention decay: last-3-day volume vs first-3-day volume, ranked against the
    # point-in-time distribution of ALL EARLIER listings
    cq = np.nancumsum(np.where(np.isfinite(p.g["qv"]), p.g["qv"], 0.0), axis=1)
    qv_first3 = np.full((S, ND), np.nan, np.float32)
    for i in range(S):
        f = p.first[i]
        if f + 3 < ND:
            qv_first3[i, f + 3:] = cq[i, f + 3] - cq[i, f]
    with np.errstate(invalid="ignore", divide="ignore"):
        decay = np.log(np.maximum(roll_mean(p.g["qv"], 3) * 3, 1.0)
                       / np.maximum(qv_first3, 1.0)).astype(np.float32)
    dec_at7 = np.full(S, np.nan, np.float32)
    for i in range(S):
        f = p.first[i]
        if p.real_listing[i] and f + 7 < ND:
            dec_at7[i] = decay[i, f + 7]
    pct = past_pctile(dec_at7, p.first, p.day)
    decsig = np.broadcast_to((pct - 0.5)[:, None], (S, ND)).astype(np.float32)
    A(("A5_NL_VOLDECAY", "A_newlisting", cohort_book(p, decsig, coh2), 5, COST_NEW,
       "attention decay: day-7 volume vs first-3-day volume, percentile-ranked against "
       "every EARLIER listing; long the persistent-attention half of the aged 8-30d "
       "cohort, short the fading half, hedged, 5-day hold"))

    # age tilt across the whole liquid top-50
    lage = np.where(np.isfinite(p.age), np.log(np.maximum(p.age, 1.0)), np.nan
                    ).astype(np.float32)
    A(("A6_NL_AGE_TILT", "A_newlisting", quintile_weights(-lage, U), 5, COST_LIQ,
       "cross-sectional tilt of the LIQUID top-50 toward recently listed perps "
       "(-log listing age), 5-day hold"))

    # ============================================================ FAMILY B -- weekend
    wd = p.wd
    is_sun = (wd == 6)      # signal column: known at Sunday close, traded Monday open
    is_fri = (wd == 4)
    # weekend return = close(Fri) -> close(Sun)
    wknd_r = np.full((S, ND), np.nan, np.float32)
    wknd_flow = np.full((S, ND), np.nan, np.float32)
    wknd_rv = np.full(ND, np.nan, np.float32)
    wknd_disp = np.full(ND, np.nan, np.float32)
    for d in range(ND):
        if not is_sun[d] or d < 3:
            continue
        wknd_r[:, d] = p.lc[:, d] - p.lc[:, d - 2]             # Fri close -> Sun close
        wknd_flow[:, d] = np.nanmean(p.tbr[:, d - 1:d + 1], axis=1)
        m = U[:, d]
        v = wknd_r[m, d]
        v = v[np.isfinite(v)]
        if len(v) >= MIN_NAMES:
            wknd_disp[d] = float(np.std(v))
            wknd_rv[d] = float(np.sqrt(np.nanmean(
                np.nanmean(p.r1[m][:, d - 1:d + 1] ** 2, axis=1))))
    A(("B1_WKND_XS_FADE", "B_weekend", quintile_weights(-wknd_r, U & is_sun[None, :]), 1,
       COST_LIQ, "cross-sectional book formed at Sunday 24:00 UTC that fades the "
       "Fri-close to Sun-close weekend return, entered Monday open, 1-day hold"))
    A(("B2_WKND_FLOW_FADE", "B_weekend",
       quintile_weights(-wknd_flow, U & is_sun[None, :]), 1, COST_LIQ,
       "fade the weekend taker-buy imbalance (tbq/qv-0.5 averaged over Sat+Sun), entered "
       "Monday open, 1-day hold"))
    fri_fund = np.where(is_fri[None, :], roll_mean(p.g["fnd"], 3), np.nan).astype(np.float32)
    A(("B3_WKND_FUND_CARRY", "B_weekend",
       quintile_weights(fri_fund, U & is_fri[None, :]), 3, COST_LIQ,
       "enter Friday-close on the cross-sectional funding rank and hold ONLY across the "
       "weekend (3 days) -- weekend funding is stickier because arb desks are flat"))
    # weekend vol-compression regime -> basket direction
    wrv = np.where(np.isfinite(wknd_rv), wknd_rv, np.nan)
    wkrv_ff = wrv.copy()
    for d in range(1, ND):
        if not np.isfinite(wkrv_ff[d]):
            wkrv_ff[d] = wkrv_ff[d - 1]
    base = np.full(ND, np.nan, np.float32)
    m20 = roll_mean(p.rv20, 20)
    base = np.nanmean(np.where(U, p.rv20, np.nan), axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        wratio = np.where(base > 0, wkrv_ff / np.maximum(base, 1e-9), np.nan)
    sig = zs1(wratio.astype(np.float32), 60)
    wts = ts_basket(p, np.where(is_sun, sig, np.nan))
    A(("B4_WKND_VOLRATIO_TS", "B_weekend", wts, 2, COST_LIQ,
       "TIME-SERIES: z of (weekend realised vol / trailing 20d universe vol) measured at "
       "Sunday close, applied to the whole equal-weight basket for 2 days from Monday"))
    wdisp_ff = wknd_disp.copy()
    for d in range(1, ND):
        if not np.isfinite(wdisp_ff[d]):
            wdisp_ff[d] = wdisp_ff[d - 1]
    sig = zs1(wdisp_ff.astype(np.float32), 60)
    A(("B5_WKND_DISP_TS", "B_weekend", ts_basket(p, np.where(is_sun, sig, np.nan)), 2,
       COST_LIQ, "TIME-SERIES: z of the CROSS-SECTIONAL dispersion of weekend returns "
       "(how much the universe pulled apart while desks were away), basket, 2-day hold"))

    # ============================================================ FAMILY C -- vol of vol
    vterm = (p.vov_s - p.vov_l).astype(np.float32)
    A(("C1_VOV_TERM_XS", "C_volofvol", quintile_weights(vterm, U), 5, COST_LIQ,
       "cross-sectional rank of the VOL-OF-VOL TERM STRUCTURE: 10-day vol-of-vol minus "
       "40-day vol-of-vol (vol regime destabilising vs settling), 5-day hold"))
    agg_vov = np.nanmean(np.where(U, p.vov_s, np.nan), axis=0).astype(np.float32)
    zvov = zs1(agg_vov, 90)
    A(("C2_VOV_TS", "C_volofvol", ts_basket(p, zvov), 3, COST_LIQ,
       "TIME-SERIES: z of the universe-mean vol-of-vol applied to the equal-weight "
       "basket, 3-day hold"))
    up = np.where(p.r1 > 0, p.rv5, np.nan).astype(np.float32)
    dn = np.where(p.r1 < 0, p.rv5, np.nan).astype(np.float32)
    vasym = (roll_std(up, 60, min_n=12) - roll_std(dn, 60, min_n=12)).astype(np.float32)
    A(("C3_VOV_ASYM_XS", "C_volofvol", quintile_weights(vasym, U), 5, COST_LIQ,
       "cross-sectional rank of VOL-OF-VOL ASYMMETRY: dispersion of realised vol on up "
       "days minus on down days, 5-day hold"))
    rev3 = quintile_weights(-p.r3, U)
    gate = (zvov > 0.5)
    A(("C4_VOV_GATE_REV", "C_volofvol", rev3 * gate[None, :].astype(np.float32), 3, COST_LIQ,
       "CONDITIONER: the plain 3-day cross-sectional reversal book, switched ON only "
       "when aggregate vol-of-vol z > 0.5 and flat otherwise"))

    # ============================================================ FAMILY D -- dispersion
    zdisp = zs1(p.disp, 90)
    A(("D1_DISP_TS", "D_dispersion", ts_basket(p, zdisp), 3, COST_LIQ,
       "TIME-SERIES: z of the cross-sectional dispersion of daily perp returns applied to "
       "the equal-weight basket, 3-day hold"))
    zcorr = zs1(p.avgcorr, 90)
    A(("D2_AVGCORR_TS", "D_dispersion", ts_basket(p, zcorr), 3, COST_LIQ,
       "TIME-SERIES: z of implied AVERAGE PAIRWISE CORRELATION (market variance / mean "
       "name variance) applied to the equal-weight basket, 3-day hold"))
    gate = (zcorr > 0.5)
    A(("D3_CORR_GATE_REV", "D_dispersion", rev3 * gate[None, :].astype(np.float32), 3,
       COST_LIQ, "CONDITIONER: 3-day cross-sectional reversal traded ONLY in the "
       "high-average-correlation regime (z>0.5)"))
    M7 = np.broadcast_to(np.nanmean(np.where(U, p.r7, np.nan), axis=0)[None, :],
                         (S, ND)).astype(np.float32)
    res7 = (p.r7 - M7).astype(np.float32)
    mom = quintile_weights(res7, U)
    gate = (zdisp > 0.5)
    A(("D4_DISP_GATE_MOM", "D_dispersion", mom * gate[None, :].astype(np.float32), 5,
       COST_LIQ, "CONDITIONER: 7-day market-neutral cross-sectional momentum traded ONLY "
       "in the high-dispersion regime (z>0.5), 5-day hold"))
    dcorr = (p.corr20 - lag(p.corr20, 10)).astype(np.float32)
    A(("D5_XS_CORRDROP", "D_dispersion", quintile_weights(dcorr, U), 5, COST_LIQ,
       "cross-sectional rank of the 10-day CHANGE in a name's correlation to the "
       "equal-weight market (decoupling vs recoupling), 5-day hold"))

    # ============================================================ FAMILY E -- crowding
    fnd = np.where(U, p.g["fnd"], np.nan)
    fdisp = np.nanstd(fnd, axis=0).astype(np.float32)
    zfd = zs1(fdisp, 90)
    A(("E1_FUNDDISP_TS", "E_crowding", ts_basket(p, zfd), 3, COST_LIQ,
       "TIME-SERIES: z of the CROSS-SECTIONAL DISPERSION of daily funding across the "
       "universe -- a leverage-crowding index -- applied to the basket, 3-day hold"))
    fbre = np.nanmean((fnd > 0).astype(np.float32) * np.where(np.isfinite(fnd), 1.0, np.nan),
                      axis=0).astype(np.float32)
    zfb = zs1(fbre, 90)
    A(("E2_FUNDBREADTH_TS", "E_crowding", ts_basket(p, zfb), 3, COST_LIQ,
       "TIME-SERIES: z of the FRACTION of the universe paying positive funding "
       "(aggregate long-positioning breadth), basket, 3-day hold"))
    fm = np.broadcast_to(np.nanmean(fnd, axis=0)[None, :], (S, ND)).astype(np.float32)
    covf = roll_mean(p.g["fnd"] * fm, 60) - roll_mean(p.g["fnd"], 60) * roll_mean(fm, 60)
    varf = roll_mean(fm * fm, 60) - roll_mean(fm, 60) ** 2
    with np.errstate(invalid="ignore", divide="ignore"):
        bf = np.where(varf > 0, covf / np.maximum(varf, 1e-18), np.nan).astype(np.float32)
    fres = (p.g["fnd"] - bf * fm).astype(np.float32)
    A(("E3_XS_FUND_RESID", "E_crowding", quintile_weights(-fres, U), 3, COST_LIQ,
       "cross-sectional book on funding RESIDUAL to each name's own 60-day beta to "
       "universe-mean funding: idiosyncratic positioning, not the carry level, 3-day hold"))
    gate = (zfd > 0.5)
    A(("E4_CROWD_GATE_REV", "E_crowding", rev3 * gate[None, :].astype(np.float32), 3,
       COST_LIQ, "CONDITIONER: 3-day cross-sectional reversal traded ONLY when the "
       "funding-dispersion crowding index is elevated (z>0.5)"))

    # ============================================================ FAMILY F -- stablecoins
    sc = load_stablecoin(p)
    zsc = zs1(sc["imp7"], 180)
    A(("F1_SC_IMPULSE_BASKET", "F_stablecoin", ts_basket(p, zsc), 7, COST_LIQ,
       "TIME-SERIES: z of the 7-day log change in aggregate USD-pegged stablecoin "
       "circulating supply (net mint/burn) applied to the equal-weight perp basket, "
       "7-day hold"))
    wb = np.zeros((S, ND), np.float32)
    bi = int(np.flatnonzero(p.sym == "BTCUSDT")[0])
    wb[bi, :] = np.where(np.isfinite(zsc) & p.tradable[bi, :], np.sign(zsc), 0.0)
    A(("F2_SC_IMPULSE_BTC", "F_stablecoin", wb, 7, COST_LIQ,
       "same stablecoin mint/burn impulse applied to the BTCUSDT perp alone, 7-day hold"))
    walt = np.zeros((S, ND), np.float32)
    for d in range(ND):
        u = np.flatnonzero(U[:, d])
        if len(u) < MIN_NAMES or not np.isfinite(zsc[d]) or not p.tradable[bi, d]:
            continue
        alts = u[u != bi]
        s = float(np.sign(zsc[d]))
        walt[alts, d] = s / len(alts)
        walt[bi, d] = -s
    A(("F3_SC_ALT_VS_BTC", "F_stablecoin", walt, 7, COST_LIQ,
       "stablecoin mint/burn impulse traded as ALTS-vs-BTC: fresh stablecoin supply is "
       "risk-on fuel that reaches alts, long alt basket / short BTC, 7-day hold"))

    return F


def controls(p):
    """NOT part of the 27-formula search. Three books whose sign and rough size are
    already known from the literature and from rounds 1-2, run through this exact harness
    to prove the harness is not the reason the 27 fail."""
    S, ND = p.S, p.ND
    U = p.univ
    out = []
    out.append(("CTRL_LONG_BASKET", ts_basket(p, np.ones(ND, np.float32)), 1, COST_LIQ,
                "long-only equal-weight top-50 perp basket (should track crypto beta)"))
    out.append(("CTRL_XS_REV3", quintile_weights(-p.r3, U), 3, COST_LIQ,
                "plain 3-day cross-sectional reversal (known real gross, known "
                "cost-killed net)"))
    out.append(("CTRL_XS_FUND", quintile_weights(-p.g["fnd"], U), 3, COST_LIQ,
                "plain cross-sectional funding carry: short the expensive, long the cheap "
                "(the single best-documented perp effect)"))
    out.append(("CTRL_XS_MOM7", quintile_weights(p.r7, U), 5, COST_LIQ,
                "plain 7-day cross-sectional momentum"))
    return out


def cohort_book(p, sig, coh, hedge=True, min_names=1):
    """equal-weight sign(sig) book inside a (very thin) cohort, net exposure hedged
    with the equal-weight liquid basket."""
    S, ND = p.S, p.ND
    w = np.zeros((S, ND), np.float32)
    U = p.univ
    for d in range(ND):
        idx = np.flatnonzero(coh[:, d] & np.isfinite(sig[:, d]))
        if len(idx) < min_names:
            continue
        s = np.sign(sig[idx, d]).astype(np.float32)
        s[s == 0] = 0.0
        if not np.any(s != 0):
            continue
        w[idx, d] = s / len(idx)
        if hedge:
            net = float(w[idx, d].sum())
            u = np.flatnonzero(U[:, d])
            if len(u) < MIN_NAMES:
                w[idx, d] = 0.0
                continue
            w[u, d] -= net / len(u)
    return w


def past_pctile(v, first, day):
    """point-in-time percentile of each listing's statistic vs all EARLIER listings."""
    S = len(v)
    out = np.full(S, np.nan, np.float32)
    order = np.argsort(first)
    seen = []
    for i in order:
        if not np.isfinite(v[i]):
            continue
        if len(seen) >= 8:
            out[i] = float(np.mean(np.array(seen) < v[i]))
        seen.append(v[i])
    return out


def ts_basket(p, sig):
    """time-series signal (per day) -> equal-weight long/short of the liquid universe."""
    S, ND = p.S, p.ND
    w = np.zeros((S, ND), np.float32)
    U = p.univ
    for d in range(ND):
        if not np.isfinite(sig[d]):
            continue
        u = np.flatnonzero(U[:, d])
        if len(u) < MIN_NAMES:
            continue
        w[u, d] = float(np.sign(sig[d])) / len(u)
    return w


def load_stablecoin(p):
    raw = json.loads((CACHE / "sc_all.json").read_text())
    ts = np.array([int(r["date"]) for r in raw], dtype=np.int64)
    sup = np.array([float(r.get("totalCirculating", {}).get("peggedUSD", np.nan))
                    for r in raw], dtype=np.float64)
    dd = ts // 86400
    m = np.isfinite(sup) & (sup > 0)
    dd, sup = dd[m], sup[m]
    ls = np.log(sup)
    grid = np.full(p.ND, np.nan)
    pos = {int(x): i for i, x in enumerate(dd)}
    for j, x in enumerate(p.day):
        i = pos.get(int(x))
        if i is not None:
            grid[j] = ls[i]
    # forward-fill at most 3 days
    last, gap = np.nan, 99
    for j in range(p.ND):
        if np.isfinite(grid[j]):
            last, gap = grid[j], 0
        else:
            gap += 1
            if gap <= 3:
                grid[j] = last
    imp7 = np.full(p.ND, np.nan, np.float32)
    imp7[7:] = (grid[7:] - grid[:-7]).astype(np.float32)
    return dict(logsup=grid, imp7=imp7)


# ------------------------------------------------------------------ noise bar
def null_max_sharpe(pnls, masks, n_rep=2000, block=10, seed=7):
    """sign-flip block bootstrap over the whole family, re-scoring the max each replicate."""
    rng = np.random.default_rng(seed)
    mats = []
    for d, m in zip(pnls, masks):
        v = np.where(m & np.isfinite(d), d, 0.0)
        mats.append(v)
    Mt = np.array(mats)                          # F x ND
    nd = Mt.shape[1]
    nb = int(math.ceil(nd / block))
    live = np.array([m.sum() for m in masks], float)
    sds = np.array([np.std(mats[i][masks[i]]) if masks[i].sum() > 90 else np.nan
                    for i in range(len(mats))])
    out = np.empty(n_rep)
    singles = []
    for rep in range(n_rep):
        s = rng.choice([-1.0, 1.0], size=nb)
        sgn = np.repeat(s, block)[:nd]
        X = Mt * sgn[None, :]
        best = -np.inf
        for i in range(len(mats)):
            mm = masks[i]
            if mm.sum() <= 90 or not np.isfinite(sds[i]) or sds[i] == 0:
                continue
            v = X[i][mm]
            sh = v.mean() / sds[i] * math.sqrt(365)
            if rep < 400:
                singles.append(sh)
            best = max(best, abs(sh))
        out[rep] = best
    return dict(mean=float(np.mean(out)), p95=float(np.percentile(out, 95)),
                p99=float(np.percentile(out, 99)),
                single_sd=float(np.std(singles)) if singles else float("nan"))


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="INVENT_R3_exotic")
    a = ap.parse_args()

    p = build()
    print(f"panel {p.S} symbols x {p.ND} days, {dstr(p.day[0])} -> {dstr(p.day[-1])}")
    print(f"real-listing flags: {int(p.real_listing.sum())} symbols")
    md = window_mask(p, *DESIGN)
    mh = window_mask(p, *HELD)
    print(f"design days {md.sum()}, heldout days {mh.sum()}")

    F = catalogue(p)
    print(f"{len(F)} formulas")

    rows = []
    dpnl, dmask = [], []
    for name, fam, w, H, cb, desc in F:
        # STEP 1 -- orient the sign on the DESIGN window using the ZERO-COST P&L, so the
        # orientation choice can never be contaminated by the cost term.
        r0 = run_book(p, w, H, 0.0)
        s0 = sharpe(r0["gross"][md])
        sgn = 1.0 if (not np.isfinite(s0) or s0 >= 0) else -1.0
        # STEP 2 -- re-run the ORIENTED book; costs are then always a subtraction.
        ws = (w * sgn).astype(np.float32)
        r5 = run_book(p, ws, H, cb)
        shock = COST_NEW_SHOCK if cb == COST_NEW else COST_LIQ_SHOCK
        rs = run_book(p, ws, H, shock)
        # Sharpe is measured over the FULL window, not only over days the book is on.
        # A book that only trades Mondays must pay for the days it earns nothing.
        act = np.abs(r5["hold"]).sum(axis=0) > 1e-9
        mdd, mhh = md, mh
        n_act_d, n_act_h = int((md & act).sum()), int((mh & act).sum())
        tno_d = float(np.mean(r5["tno"][mdd]))
        tno_h = float(np.mean(r5["tno"][mhh]))
        gmean_h = float(np.mean(r5["gross"][mhh]))
        be = (gmean_h / tno_h * 1e4) if (np.isfinite(gmean_h) and tno_h > 0) else float("nan")
        rows.append(dict(
            name=name, family=fam, H=H, cost_bp=cb, sign=sgn, desc=desc,
            n_design_days=int(mdd.sum()), n_held_days=int(mhh.sum()),
            n_active_design=n_act_d, n_active_held=n_act_h,
            gross_exposure_mean=float(np.mean(np.abs(r5["hold"]).sum(axis=0)[mhh])),
            design_sharpe_gross=sharpe(r5["gross"][mdd]),
            design_sharpe_net=sharpe(r5["net"][mdd]),
            held_sharpe_gross=sharpe(r5["gross"][mhh]),
            held_sharpe_net=sharpe(r5["net"][mhh]),
            held_sharpe_net_shock=sharpe(rs["net"][mhh]),
            held_t=tstat(r5["net"][mhh]), design_t=tstat(r5["net"][mdd]),
            turnover_design=tno_d, turnover_held=tno_h,
            breakeven_cost_bp_per_side=be,
            held_bp_per_day_net=float(np.mean(r5["net"][mhh]) * 1e4),
            design_bp_per_day_net=float(np.mean(r5["net"][mdd]) * 1e4),
            fund_share_held=float(np.mean(r5["fund"][mhh]) * 1e4),
        ))
        dpnl.append(r5["net"])
        dmask.append(mdd)
        np.save(CACHE / f"pnl_{name}.npy", r5["net"])

    nb = null_max_sharpe(dpnl, dmask)
    N = len(F)
    analytic = math.sqrt(2 * math.log(N))
    analytic2 = math.sqrt(2 * math.log(2 * N))
    print(f"\nnull-max design |Sharpe|: mean {nb['mean']:.2f} p95 {nb['p95']:.2f} "
          f"p99 {nb['p99']:.2f}; single-config SD {nb['single_sd']:.3f}")
    print(f"analytic sqrt(2 ln N)={analytic:.3f}  sign-agnostic sqrt(2 ln 2N)={analytic2:.3f}")

    rows.sort(key=lambda r: (-(r["design_sharpe_net"] if np.isfinite(r["design_sharpe_net"])
                               else -9)))
    print(f"\n{'name':26s} {'fam':14s} {'Ddes':>6s} {'Dnet':>6s} {'Hnet':>6s} "
          f"{'Hshk':>6s} {'Ht':>6s} {'BE':>7s}")
    for r in rows:
        print(f"{r['name']:26s} {r['family']:14s} {r['design_sharpe_gross']:6.2f} "
              f"{r['design_sharpe_net']:6.2f} {r['held_sharpe_net']:6.2f} "
              f"{r['held_sharpe_net_shock']:6.2f} {r['held_t']:6.2f} "
              f"{r['breakeven_cost_bp_per_side']:7.1f}")

    # ---- harness controls (excluded from the 27 and from the noise bar)
    ctrl = []
    for name, w, H, cb, desc in controls(p):
        r0 = run_book(p, w, H, 0.0)
        r5 = run_book(p, w, H, cb)
        ctrl.append(dict(name=name, desc=desc,
                         design_sharpe_gross=sharpe(r0["gross"][md]),
                         design_sharpe_net=sharpe(r5["net"][md]),
                         held_sharpe_gross=sharpe(r0["gross"][mh]),
                         held_sharpe_net=sharpe(r5["net"][mh]),
                         turnover_held=float(np.mean(r5["tno"][mh]))))
    print("\nHARNESS CONTROLS (not part of the 27):")
    for c in ctrl:
        print(f"  {c['name']:20s} design gross {c['design_sharpe_gross']:6.2f} "
              f"net {c['design_sharpe_net']:6.2f} | held gross {c['held_sharpe_gross']:6.2f} "
              f"net {c['held_sharpe_net']:6.2f}")

    out = dict(
        theme="exotic_leftfield_round3",
        created=dt.date.today().isoformat(),
        n_formulas=N,
        design_window=DESIGN, heldout_window=HELD,
        universe="Binance USD-M perps, top-50 by trailing 7d quote volume "
                 "(new-listing family uses its own >$3M/day cohort)",
        cost_model=dict(liquid_bp_per_side=COST_LIQ, liquid_shock=COST_LIQ_SHOCK,
                        newlisting_bp_per_side=COST_NEW, newlisting_shock=COST_NEW_SHOCK,
                        funding="charged at settlement, long pays positive"),
        noise_bar=dict(empirical=nb, analytic_sqrt_2lnN=analytic,
                       analytic_sign_agnostic=analytic2,
                       empirical_in_SE_units=nb["mean"] / nb["single_sd"]
                       if nb["single_sd"] else None),
        rows=rows,
        harness_controls=ctrl,
    )
    (OUTDIR / f"{a.out}.json").write_text(json.dumps(out, indent=1, default=float))
    print("\nwrote", OUTDIR / f"{a.out}.json")


if __name__ == "__main__":
    main()
