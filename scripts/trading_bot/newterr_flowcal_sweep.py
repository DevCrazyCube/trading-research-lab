#!/usr/bin/env python3
"""PRECISE CALENDAR / FORCED-FLOW sweep -- design scoring + empirical max-|z| null.

Pre-registration: research/trading_bot/NEWTERR_flowcal_PREREGISTRATION.md (committed
before this file produced a number).

Design notes that matter for reading the output
-----------------------------------------------
* Every `xs` formula reduces to a fixed integer vector `pos[t] in {-1,0,+1}` (the calendar
  gate and its direction) plus a *score key* naming which cross-sectional ranking supplies
  the book. The book is always the top decile long / bottom decile short of that score
  among the day's eligible names, dollar-neutral, L1 = 1.
* The null rotates the panel's ROWS circularly against the fixed calendar. Decile
  membership is a row-wise property, so rotating the pre-computed rank masks jointly with
  the returns is exactly equivalent to rotating the raw data and recomputing -- and it makes
  each replicate nearly free.
* Sharpe is computed on the FULL daily series with zeros on flat days: it is the Sharpe of
  the deployed capital, not the Sharpe of the active days. A formula that trades 4 days a
  month is penalised for the 17 it sits idle, which is the honest economics.
* t17 daily bars are NOT split-adjusted. Splits are detected by the joint price/volume
  signature and divided out; unmatched >30% moves are clipped. Dividends are not adjusted
  either -- for a dollar-neutral decile spread that biases the long-mega-cap books
  DOWNWARD (mega caps yield more), i.e. conservative for this family's main hypothesis.
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[2]
PANEL = ROOT / "research" / "data" / "newterr_flowcal" / "panel.npz"
OUT = ROOT / "research" / "trading_bot"

XS_SPLIT = "2023-06-30"
ETF_SPLIT = "2016-12-31"
FOMC_SPLIT = "2019-12-31"

COST_XS_BP = 2.5
COST_ETF_BP = 1.0
BORROW_BP_YR = 50.0
ADV_MIN = 30e6
PX_MIN = 5.0
DEC = 0.10
NULL_REPS = int(__import__("os").environ.get("NEWTERR_REPS", "400"))
RNG_SEED = 20260820

# FOMC statement dates, scheduled meetings only. The March 2020 emergency actions are
# excluded a priori: an unscheduled action has no pre-announcement window.
FOMC = """
2011-01-26 2011-03-15 2011-04-27 2011-06-22 2011-08-09 2011-09-21 2011-11-02 2011-12-13
2012-01-25 2012-03-13 2012-04-25 2012-06-20 2012-08-01 2012-09-13 2012-10-24 2012-12-12
2013-01-30 2013-03-20 2013-05-01 2013-06-19 2013-07-31 2013-09-18 2013-10-30 2013-12-18
2014-01-29 2014-03-19 2014-04-30 2014-06-18 2014-07-30 2014-09-17 2014-10-29 2014-12-17
2015-01-28 2015-03-18 2015-04-29 2015-06-17 2015-07-29 2015-09-17 2015-10-28 2015-12-16
2016-01-27 2016-03-16 2016-04-27 2016-06-15 2016-07-27 2016-09-21 2016-11-02 2016-12-14
2017-02-01 2017-03-15 2017-05-03 2017-06-14 2017-07-26 2017-09-20 2017-11-01 2017-12-13
2018-01-31 2018-03-21 2018-05-02 2018-06-13 2018-08-01 2018-09-26 2018-11-08 2018-12-19
2019-01-30 2019-03-20 2019-05-01 2019-06-19 2019-07-31 2019-09-18 2019-10-30 2019-12-11
2020-01-29 2020-04-29 2020-06-10 2020-07-29 2020-09-16 2020-11-05 2020-12-16
2021-01-27 2021-03-17 2021-04-28 2021-06-16 2021-07-28 2021-09-22 2021-11-03 2021-12-15
2022-01-26 2022-03-16 2022-05-04 2022-06-15 2022-07-27 2022-09-21 2022-11-02 2022-12-14
2023-02-01 2023-03-22 2023-05-03 2023-06-14 2023-07-26 2023-09-20 2023-11-01 2023-12-13
2024-01-31 2024-03-20 2024-05-01 2024-06-12 2024-07-31 2024-09-18 2024-11-07 2024-12-18
2025-01-29 2025-03-19 2025-05-07 2025-06-18 2025-07-30 2025-09-17 2025-10-29 2025-12-10
2026-01-28 2026-03-18 2026-04-29 2026-06-17 2026-07-29
""".split()

SPLIT_FACTORS = np.array([1/20, 1/10, 1/8, 1/7, 1/6, 1/5, 1/4, 1/3, 1/2.5, 1/2, 1/1.5,
                          1.5, 2, 2.5, 3, 4, 5, 6, 7, 8, 10, 20])


# =====================================================================================
# calendar
# =====================================================================================

def calfeat(dates):
    D = [dt.date.fromisoformat(str(x)) for x in dates]
    n = len(D)
    month = np.array([d.month for d in D])
    year = np.array([d.year for d in D])
    day = np.array([d.day for d in D])
    dow = np.array([d.weekday() for d in D])
    ym = year * 12 + month
    tdom = np.zeros(n, int)
    rtdom = np.zeros(n, int)
    c = 0
    for i in range(n):
        if i == 0 or ym[i] != ym[i - 1]:
            c = 0
        c += 1
        tdom[i] = c
    c = 0
    for i in range(n - 1, -1, -1):
        if i == n - 1 or ym[i] != ym[i + 1]:
            c = 0
        c += 1
        rtdom[i] = c
    pre_hol = np.zeros(n, bool)
    post_hol = np.zeros(n, bool)
    long_wk = np.zeros(n, bool)
    for i in range(n - 1):
        gap = (D[i + 1] - D[i]).days
        normal = 3 if dow[i] == 4 else 1
        if gap > normal:
            pre_hol[i] = True
            post_hol[i + 1] = True
            if gap >= 3:
                long_wk[i] = True
    opex = np.zeros(n, bool)
    opex_week = np.zeros(n, bool)
    for m in np.unique(ym):
        sel = np.where(ym == m)[0]
        y, mo = D[sel[0]].year, D[sel[0]].month
        first = dt.date(y, mo, 1)
        tf = first + dt.timedelta(days=((4 - first.weekday()) % 7) + 14)
        cand = [i for i in sel if D[i] <= tf]
        if not cand:
            continue
        opex[cand[-1]] = True
        wk0 = tf - dt.timedelta(days=tf.weekday())
        for i in sel:
            if wk0 <= D[i] <= tf:
                opex_week[i] = True
    quad = np.isin(month, [3, 6, 9, 12])
    refund = np.isin(month, [2, 5, 8, 11])
    # first session on or after the 15th ("mid-month payday / settlement")
    mid15 = np.zeros(n, bool)
    for m in np.unique(ym):
        sel = np.where((ym == m) & (day >= 15))[0]
        if len(sel):
            mid15[sel[0]] = True
    # Russell reconstitution: last session on or before the last Friday of June
    recon = np.zeros(n, bool)
    may1 = np.zeros(n, bool)
    for y in np.unique(year):
        jun = [i for i in range(n) if D[i].year == y and D[i].month == 6]
        if not jun:
            continue
        fridays = [i for i in jun if dow[i] == 4]
        if fridays:
            recon[fridays[-1]] = True
        mays = [i for i in range(n) if D[i].year == y and D[i].month == 5]
        if mays:
            may1[mays[0]] = True
    fomc = np.zeros(n, bool)
    ds = {str(x): i for i, x in enumerate(dates)}
    fd = sorted(set(FOMC))
    darr = np.array([str(x) for x in dates])
    for f in fd:
        if f in ds:
            fomc[ds[f]] = True
        else:  # meeting on a non-session (none expected) -> next session
            p = int(np.searchsorted(darr, f))
            if p < n:
                fomc[p] = True
    return dict(D=D, month=month, year=year, day=day, dow=dow, ym=ym, tdom=tdom,
                rtdom=rtdom, pre_hol=pre_hol, post_hol=post_hol, long_wk=long_wk,
                opex=opex, opex_week=opex_week, quad=quad, refund=refund, mid15=mid15,
                recon=recon, may1=may1, fomc=fomc)


def shift_true(mask, k):
    """mask shifted forward by k sessions."""
    out = np.zeros_like(mask)
    if k == 0:
        return mask.copy()
    if k > 0:
        out[k:] = mask[:-k]
    else:
        out[:k] = mask[-k:]
    return out


def window_after(mask, k1, k2):
    """union of shifts k1..k2 (inclusive) of mask."""
    out = np.zeros_like(mask)
    for k in range(k1, k2 + 1):
        out |= shift_true(mask, k)
    return out


# =====================================================================================
# xs panel preparation
# =====================================================================================

def roll_mean(X, w):
    """trailing mean over w rows, ending at t-1 (strictly past). NaN-safe via zero fill."""
    Z = np.nan_to_num(X, nan=0.0).astype(np.float64)
    M = np.isfinite(X).astype(np.float64)
    cz = np.vstack([np.zeros((1, X.shape[1])), np.cumsum(Z, axis=0)])
    cm = np.vstack([np.zeros((1, X.shape[1])), np.cumsum(M, axis=0)])
    n = X.shape[0]
    out = np.full(X.shape, np.nan)
    s = cz[w:] - cz[:-w]
    c = cm[w:] - cm[:-w]
    with np.errstate(invalid="ignore", divide="ignore"):
        val = np.where(c > 0.5 * w, s / np.maximum(c, 1), np.nan)
    out[w:] = val[:-1]
    return out.astype(np.float32)


def prep_xs(z):
    dates = np.array([str(x) for x in z["dates"]])
    syms = np.array([str(x) for x in z["syms"]])
    C = z["C"].astype(np.float32)
    V = z["V"].astype(np.float32)
    SV = z["SV"].astype(np.float32)
    TV = z["TV"].astype(np.float32)
    SI = z["SI"].astype(np.float32)
    SIP = z["SIP"].astype(np.float32)
    n, k = C.shape

    prev = np.vstack([np.full((1, k), np.nan, np.float32), C[:-1]])
    prevV = np.vstack([np.full((1, k), np.nan, np.float32), V[:-1]])
    with np.errstate(invalid="ignore", divide="ignore"):
        ratio = prev / C
        vratio = V / np.maximum(prevV, 1.0)
    big = np.isfinite(ratio) & (np.abs(np.log(np.maximum(ratio, 1e-9))) > 0.26)
    lr = np.log(np.maximum(ratio, 1e-9))
    lv = np.log(np.maximum(vratio, 1e-9))
    # a genuine r:1 split divides price by r AND multiplies volume by r
    cand = big & (np.abs(lr - lv) < 0.40)
    lf = np.log(SPLIT_FACTORS)
    ci, cj = np.where(cand)
    adjf = np.ones((n, k), np.float32)
    n_split = 0
    if len(ci):
        lrc = lr[ci, cj]
        near = lf[np.argmin(np.abs(lrc[:, None] - lf[None, :]), axis=1)]
        hit = np.abs(lrc - near) < 0.05
        adjf[ci[hit], cj[hit]] = np.exp(near[hit]).astype(np.float32)
        n_split = int(hit.sum())
    with np.errstate(invalid="ignore", divide="ignore"):
        ret = (C * adjf) / prev - 1.0
    ret = np.where(np.isfinite(ret), ret, np.nan)
    n_clip = int((np.abs(np.nan_to_num(ret)) > 0.30).sum())
    ret = np.clip(ret, -0.30, 0.30)

    dv = C * V
    adv = roll_mean(dv, 60)
    pxprev = np.vstack([np.full((1, k), np.nan, np.float32), C[:-1]])
    elig = np.isfinite(adv) & (adv >= ADV_MIN) & np.isfinite(pxprev) & (pxprev >= PX_MIN) \
        & np.isfinite(ret)
    keep = elig.sum(axis=0) >= 60
    print(f"  splits divided out: {n_split}; >30% moves clipped: {n_clip}")
    print(f"  universe kept {int(keep.sum())} of {k}; mean eligible/day "
          f"{elig[:, keep].sum(1).mean():.0f}")
    syms, ret, adv, elig = syms[keep], ret[:, keep], adv[:, keep], elig[:, keep]
    C, V, SV, TV, SI, SIP = (X[:, keep] for X in (C, V, SV, TV, SI, SIP))
    ret = np.nan_to_num(ret, nan=0.0)
    k = len(syms)

    with np.errstate(invalid="ignore", divide="ignore"):
        svr_raw = np.where(TV > 0, SV / TV, np.nan)
    svr = roll_mean(svr_raw.astype(np.float32), 20)
    volm = roll_mean(V, 60)
    with np.errstate(invalid="ignore", divide="ignore"):
        absvol = np.where(volm > 0, V / volm, np.nan)     # abnormal volume, known at close t
    r2 = ret.copy()
    rollvar = roll_mean((r2 ** 2).astype(np.float32), 20)
    vol20 = np.sqrt(np.maximum(rollvar, 0))
    with np.errstate(invalid="ignore", divide="ignore"):
        dtc_now = np.where(adv > 0, SI * np.nan_to_num(C, nan=0.0) / adv, np.nan)
        dsi_now = np.where(adv > 0, (SI - SIP) * np.nan_to_num(C, nan=0.0) / adv, np.nan)
    dtc = ffill(dtc_now.astype(np.float32))
    dsi = ffill(dsi_now.astype(np.float32))
    prevret = ret.copy()      # ret[t] is known at close t; used as the signal for t+1

    # size proxy: trailing dollar volume (no shares-outstanding source is free here)
    scores = dict(size=adv, svr=svr, absvol=absvol, prevret=prevret, vol20=vol20,
                  dtc=dtc, dsi=dsi)
    return dict(dates=dates, syms=syms, ret=ret, elig=elig, scores=scores, adv=adv)


def ffill(X):
    out = X.copy()
    n = out.shape[0]
    last = np.full(out.shape[1], np.nan, np.float32)
    for i in range(n):
        row = out[i]
        m = np.isfinite(row)
        last = np.where(m, row, last)
        out[i] = last
    return out


def decile_masks(score, elig, lo=DEC, hi=1.0 - DEC, sub=None):
    """Per-row top/bottom decile membership of `score` among eligible names."""
    n, k = score.shape
    ok = elig & np.isfinite(score)
    if sub is not None:
        ok = ok & sub
    S = np.where(ok, score, np.nan)
    order = np.argsort(np.where(np.isfinite(S), S, np.inf), axis=1, kind="stable")
    cnt = ok.sum(axis=1)
    rankpos = np.empty((n, k), np.int32)
    rows = np.arange(n)[:, None]
    rankpos[rows, order] = np.arange(k, dtype=np.int32)[None, :]
    with np.errstate(invalid="ignore", divide="ignore"):
        q = rankpos / np.maximum(cnt - 1, 1)[:, None]
    TOP = ok & (q >= hi)
    BOT = ok & (q < lo)
    ntop = TOP.sum(1)
    nbot = BOT.sum(1)
    good = (cnt >= 50) & (ntop > 0) & (nbot > 0)
    TOP &= good[:, None]
    BOT &= good[:, None]
    return TOP, BOT, TOP.sum(1), BOT.sum(1), good


class ScoreBook:
    """Everything a decile book needs, reduced to 1-D vectors where possible."""

    def __init__(self, name, score, elig, ret, sub=None):
        TOP, BOT, ntop, nbot, good = decile_masks(score, elig, sub=sub)
        self.name = name
        self.TOP, self.BOT = TOP, BOT
        self.ntop = np.maximum(ntop, 1).astype(np.float32)
        self.nbot = np.maximum(nbot, 1).astype(np.float32)
        self.good = good
        W = (0.5 * TOP / self.ntop[:, None]) - (0.5 * BOT / self.nbot[:, None])
        self.G = (W * ret).sum(axis=1).astype(np.float64)          # gross of the long book
        Wp = np.vstack([np.zeros((1, W.shape[1]), np.float32), W[:-1]])
        self.TNS = np.abs(W - Wp).sum(1).astype(np.float64)        # same-sign turnover
        self.TNF = np.abs(W + Wp).sum(1).astype(np.float64)        # sign-flip turnover
        self.L1 = np.abs(W).sum(1).astype(np.float64)
        del W, Wp

    def wrow(self, i):
        return (0.5 * self.TOP[i] / self.ntop[i]) - (0.5 * self.BOT[i] / self.nbot[i])


# =====================================================================================
# formula evaluation
# =====================================================================================

def xs_eval(book, pos, r, n, ret=None, src=None, cost_bp=COST_XS_BP):
    """Daily net pnl series on the CALENDAR index, with the panel rotated by r rows."""
    idx = (np.arange(n) + r) % n
    if src is None:
        gross = pos * book.G[idx]
        l1 = np.where(pos != 0, book.L1[idx], 0.0)
    else:
        sidx = (src + r) % n
        gross = np.zeros(n)
        l1 = np.zeros(n)
        act = np.where(pos != 0)[0]
        if len(act):
            Wa = np.stack([book.wrow(i) for i in sidx[act]])
            gross[act] = pos[act] * (Wa * ret[idx[act]]).sum(1)
            l1[act] = np.abs(Wa).sum(1)
    prev = np.concatenate([[0], pos[:-1]])
    turn = np.zeros(n)
    if src is None:
        same = (pos != 0) & (pos == prev)
        flip = (pos != 0) & (prev != 0) & (pos != prev)
        turn = np.where(same, book.TNS[idx], turn)
        turn = np.where(flip, book.TNF[idx], turn)
    else:
        chg = (pos != 0) & (prev != 0)
        turn = np.where(chg, 2.0 * (pos != prev), turn)
    opn = (pos != 0) & (prev == 0)
    cls = (pos == 0) & (prev != 0)
    turn = np.where(opn, l1, turn)
    turn = np.where(cls, np.concatenate([[0], l1[:-1]]), turn)
    borrow = np.where(pos != 0, 0.5 * BORROW_BP_YR * 1e-4 / 252.0, 0.0)
    return gross - turn * cost_bp * 1e-4 - borrow


def etf_eval(W, ERET, r, live_rows):
    n = ERET.shape[0]
    idx = (np.arange(n) + r) % n
    gross = (W * ERET[idx]).sum(1)
    Wp = np.vstack([np.zeros((1, W.shape[1]), np.float32), W[:-1]])
    turn = np.abs(W - Wp).sum(1)
    net = gross - turn * COST_ETF_BP * 1e-4
    return np.where(live_rows, net, 0.0)


def sharpe(x, ann=252.0):
    s = x.std()
    if s <= 0 or len(x) < 60:
        return 0.0
    return float(x.mean() / s * np.sqrt(ann))


# =====================================================================================
# the formula family
# =====================================================================================

class XSF:
    __slots__ = ("name", "book", "pos", "src", "mech")

    def __init__(self, name, book, pos, src, mech):
        self.name, self.book, self.pos, self.src, self.mech = name, book, pos, src, mech


class ETFF:
    __slots__ = ("name", "W", "live", "mech", "window")

    def __init__(self, name, W, live, mech, window):
        self.name, self.W, self.live, self.mech, self.window = name, W, live, mech, window


def build_xs_family(X, F):
    n = len(X["dates"])
    ret, elig, sc = X["ret"], X["elig"], X["scores"]
    print("  ranking score matrices ...", flush=True)
    size = ScoreBook("size", sc["size"], elig, ret)
    svr = ScoreBook("svr", sc["svr"], elig, ret)
    absvol = ScoreBook("absvol", sc["absvol"], elig, ret)
    prevret = ScoreBook("prevret", sc["prevret"], elig, ret)
    vol20 = ScoreBook("vol20", sc["vol20"], elig, ret)
    dtc = ScoreBook("dtc", sc["dtc"], elig, ret)
    dsi = ScoreBook("dsi", sc["dsi"], elig, ret)
    # mega-cap subset for the OPEX-gamma variant: top size tercile among eligible
    T3, _, _, _, _ = decile_masks(sc["size"], elig, lo=0.0, hi=2.0 / 3.0)
    prevret_mega = ScoreBook("prevret_mega", sc["prevret"], elig, ret, sub=T3)

    tdom, rtdom = F["tdom"], F["rtdom"]
    quad_month = F["quad"]
    all_days = np.ones(n, bool)

    tom = (rtdom == 1) | (tdom <= 3)                       # last session + first 3
    tom_unwind = (tdom >= 4) & (tdom <= 6)
    mid = F["mid15"] | shift_true(F["mid15"], 1)
    qe = (rtdom <= 3) & quad_month
    qe_next = window_after(qe & (rtdom == 1), 1, 3)
    me_nonq = (rtdom <= 3) & (~quad_month)
    ye = (rtdom <= 3) & (F["month"] == 12)
    prehol = F["pre_hol"]
    posthol = F["post_hol"]
    prehol_lw = F["long_wk"]
    quadfri = F["opex"] & quad_month
    quadrev = shift_true(quadfri, 1)
    quadrev5 = window_after(quadfri, 1, 5)
    merev = shift_true(rtdom == 1, 1)
    opexrev = shift_true(F["opex"] & (~quad_month), 1)
    opexwk = F["opex_week"]
    postopex = window_after(F["opex"], 1, 3)
    # SI dissemination rows: the panel marks the row a settlement date is published on
    pub = X["pub_rows"]
    sipub = window_after(pub, 1, 2)
    settle = X["settle_rows"]
    sisettle = window_after(settle, -2, -1) if settle.any() else np.zeros(n, bool)
    # Russell recon
    recon_win = np.zeros(n, bool)
    src_recon = np.arange(n)
    ridx = np.where(F["recon"])[0]
    midx = np.where(F["may1"])[0]
    for m0 in midx:
        later = ridx[ridx > m0]
        if not len(later):
            continue
        r0 = later[0]
        recon_win[m0:r0 + 1] = True
        src_recon[m0:r0 + 1] = m0
    recon_rev = np.zeros(n, bool)
    src_reconrev = np.arange(n)
    for r0 in ridx:
        hi = min(n, r0 + 6)
        recon_rev[r0 + 1:hi] = True
        src_reconrev[r0 + 1:hi] = r0

    src_q5 = np.arange(n)
    for i in np.where(quadfri)[0]:
        hi = min(n, i + 6)
        src_q5[i + 1:hi] = i
    src_pub = np.arange(n)
    for i in np.where(pub)[0]:
        hi = min(n, i + 3)
        src_pub[i + 1:hi] = i

    def P(mask, s=1):
        return (mask.astype(np.int8) * s)

    fam = [
        # A -- turn-of-month index-fund inflow, cap-weighted forced buying
        XSF("XS_TOM_SIZE", size, P(tom, +1), None,
            "semimonthly retirement inflows are invested in a cap-weighted index basket at a close"),
        XSF("XS_TOM_SIZE_UNWIND", size, P(tom_unwind, -1), None,
            "the inflow impact decays once the contribution flow stops"),
        XSF("XS_MID15_SIZE", size, P(mid, +1), None,
            "the other semimonthly payday carries the same forced cap-weighted purchase"),
        XSF("XS_TOM_SIZE_CTRL", size, P(all_days, +1), None, "UNGATED CONTROL for XS_TOM_SIZE"),
        XSF("XS_TOM_LOWVOL", vol20, P(tom, -1), None,
            "DISCRIMINATOR: index inflow buys a beta-1 basket, so it must not be a low-vol effect"),
        # B -- quarter-end dealer balance-sheet contraction
        XSF("XS_QE_SQUEEZE", svr, P(qe, +1), None,
            "quarter-end G-SIB reporting shrinks dealer stock-loan supply; a recalled short must buy back"),
        XSF("XS_QE_SQUEEZE_UNWIND", svr, P(qe_next, -1), None,
            "loan supply returns on the first days of the new quarter"),
        XSF("XS_ME_SQUEEZE", svr, P(me_nonq, +1), None,
            "same mechanism at non-quarter month-ends, where reporting pressure is weaker"),
        XSF("XS_SQUEEZE_CTRL", svr, P(all_days, +1), None, "UNGATED CONTROL for XS_QE_SQUEEZE"),
        XSF("XS_YE_SQUEEZE", svr, P(ye, +1), None,
            "the December reporting date is the largest balance-sheet snapshot of the year"),
        # C -- pre-holiday inventory flattening
        XSF("XS_PREHOL_COVER", svr, P(prehol, +1), None,
            "a market maker cannot hedge across a closure, so risk limits force the crowded shorts flat"),
        XSF("XS_POSTHOL_UNWIND", svr, P(posthol, -1), None,
            "the flattened inventory is re-established when the market reopens"),
        XSF("XS_PREHOL_LONGWK", svr, P(prehol_lw, +1), None,
            "same, restricted to closures of three or more calendar days"),
        # D -- index-rebalance forced print, identified by abnormal volume
        XSF("XS_QUADREV", absvol, P(quadrev, -1), None,
            "every tracker trades the rebalance in one print; abnormal volume measures who was printed and impact reverts"),
        XSF("XS_QUADREV_5D", absvol, P(quadrev5, -1), src_q5,
            "same print, held five sessions while impact decays"),
        XSF("XS_MEREV", absvol, P(merev, -1), None,
            "month-end effective dates for the non-quarterly index families"),
        XSF("XS_VOLREV_CTRL", absvol, P(all_days, -1), None,
            "UNGATED CONTROL: is it rebalance flow or ordinary liquidity provision?"),
        XSF("XS_OPEXREV", absvol, P(opexrev, -1), None,
            "the monthly non-quad expiry print"),
        # E -- OPEX gamma
        XSF("XS_OPEXWK_MR", prevret, P(opexwk, -1), None,
            "dealers long gamma must trade against moves to stay delta-hedged, which manufactures reversion"),
        XSF("XS_POSTOPEX_MOM", prevret, P(postopex, +1), None,
            "at expiry that hedging demand disappears at once, so moves extend"),
        XSF("XS_MR_CTRL", prevret, P(all_days, -1), None, "UNGATED CONTROL for XS_OPEXWK_MR"),
        XSF("XS_OPEXWK_MR_MEGA", prevret_mega, P(opexwk, -1), None,
            "listed-option open interest concentrates in the largest names"),
        # F -- Russell reconstitution (pre-declared underpowered)
        XSF("XS_RECON_RUNUP", size, P(recon_win, -1), src_recon,
            "every Russell tracker must buy the additions at one closing print on the last Friday of June"),
        XSF("XS_RECON_REV", size, P(recon_rev, +1), src_reconrev,
            "the one-print impact of the reconstitution reverts"),
        # G -- FINRA short-interest dissemination
        XSF("XS_SIPUB_SQUEEZE", dsi, P(sipub, +1), src_pub,
            "short interest is released on a published schedule and days-to-cover screens fire off it"),
        XSF("XS_SISETTLE_COVER", dtc, P(sisettle, +1), None,
            "shorts have a reporting reason to be flat on the settlement date itself"),
        XSF("XS_SIPUB_CTRL", dsi, P(all_days, +1), None, "UNGATED CONTROL for XS_SIPUB_SQUEEZE"),
    ]
    return fam


def build_etf_family(E, F):
    n, m = E["ERET"].shape
    col = {s: j for j, s in enumerate(E["esyms"])}
    live = E["live"]
    tdom, rtdom = F["tdom"], F["rtdom"]

    def mk(name, legs, mask, mech, window=None):
        W = np.zeros((n, m), np.float32)
        lv = np.ones(n, bool)
        for s, w in legs:
            j = col[s]
            W[mask, j] = w
            lv &= live[:, col[s]]
        idx = np.where(lv)[0]
        if len(idx):
            lo, hi = idx[0], idx[-1]
            keep = np.zeros(n, bool)
            keep[lo:hi + 1] = True
        else:
            keep = np.zeros(n, bool)
        W[~keep] = 0.0
        return ETFF(name, W, keep, mech, window or "full")

    me2 = rtdom <= 2
    me2_ref = me2 & F["refund"]
    ms2 = tdom <= 2
    allday = np.ones(n, bool)
    settle15 = F["mid15"] & F["refund"]
    settle_win = settle15 | shift_true(settle15, 1)
    apr_tax = (F["month"] == 4) & (F["day"] >= 15) & (F["day"] <= 20)
    qtax = F["mid15"] & np.isin(F["month"], [4, 6, 9, 12])
    qtax_win = qtax | shift_true(qtax, 1) | shift_true(qtax, 2)
    pre_auc = shift_true(settle15, -3) | shift_true(settle15, -2)
    post_auc = shift_true(settle15, 1) | shift_true(settle15, 2)
    mid_all = F["mid15"]
    tom = (rtdom == 1) | (tdom <= 3)
    tom_unw = (tdom >= 4) & (tdom <= 6)
    fomc = F["fomc"]
    pre24 = shift_true(fomc, -1)
    postf = shift_true(fomc, 1)

    fam = [
        mk("ETF_MEEXT_CURVE", [("TLT", 0.5), ("IEF", -0.5)], me2,
           "bond index funds must match a duration that extends on the last calendar day of the month"),
        mk("ETF_MEEXT_REFUND", [("TLT", 0.5), ("IEF", -0.5)], me2_ref,
           "extension is largest in the quarterly refunding months"),
        mk("ETF_MEEXT_UNWIND", [("TLT", -0.5), ("IEF", 0.5)], ms2,
           "the extension trade is unwound once the index has reset"),
        mk("ETF_MEEXT_CTRL", [("TLT", 0.5), ("IEF", -0.5)], allday,
           "UNGATED CONTROL for ETF_MEEXT_CURVE"),
        mk("ETF_REFUND_SETTLE", [("SPY", -1.0)], settle_win,
           "refunding settlement drains cash from the banking system into the Treasury General Account"),
        mk("ETF_TAXDRAIN_APR", [("SPY", -1.0)], apr_tax,
           "the April individual tax date is the largest single TGA build of the year"),
        mk("ETF_TAXDRAIN_CREDIT", [("HYG", -0.5), ("IEF", 0.5)], qtax_win,
           "credit is the funding-sensitive leg of a reserve drain"),
        mk("ETF_AUCTION_CONCESSION", [("TLT", -1.0)], pre_auc,
           "dealers demand a price concession to take down the refunding auctions"),
        mk("ETF_AUCTION_RELIEF", [("TLT", 1.0)], post_auc,
           "the concession is released once the inventory is distributed"),
        mk("ETF_MIDMONTH_CTRL", [("SPY", -1.0)], mid_all,
           "UNGATED CONTROL for ETF_REFUND_SETTLE: the 15th of every month"),
        mk("ETF_TOM_CAPWT", [("SPY", 0.5), ("RSP", -0.5)], tom,
           "index inflow is cap-weighted, so it must show up as cap-weighted beating equal-weight"),
        mk("ETF_TOM_CAPWT_UNWIND", [("SPY", -0.5), ("RSP", 0.5)], tom_unw,
           "the cap-weighted impact decays after the inflow"),
        mk("ETF_TOM_OEF_IWM", [("OEF", 0.5), ("IWM", -0.5)], tom,
           "the same tilt observed across the whole size spectrum"),
        mk("ETF_PREFOMC_24H", [("SPY", 1.0)], pre24,
           "risk is cut into a scheduled binary event and must be re-established after it", "fomc"),
        mk("ETF_PREFOMC_BETA", [("QQQ", 0.5), ("SPY", -0.5)], pre24,
           "the risk premium resolved into the event is a beta premium", "fomc"),
        mk("ETF_POSTFOMC_REV", [("SPY", -1.0)], postf,
           "the pre-event premium is given back once the event has passed", "fomc"),
        mk("ETF_FOMCDAY", [("SPY", 1.0)], fomc,
           "the announcement session itself", "fomc"),
    ]
    return fam


# =====================================================================================
# driver
# =====================================================================================

def prep_etf(z):
    edates = np.array([str(x) for x in z["edates"]])
    esyms = np.array([str(x) for x in z["esyms"]])
    A = z["EA"].astype(np.float32)
    n, m = A.shape
    prev = np.vstack([np.full((1, m), np.nan, np.float32), A[:-1]])
    with np.errstate(invalid="ignore", divide="ignore"):
        R = A / prev - 1.0
    live = np.isfinite(R) & (np.abs(np.nan_to_num(R)) < 0.9)
    R = np.where(live, R, 0.0).astype(np.float32)
    return dict(edates=edates, esyms=esyms, ERET=R, live=live)


def main():
    z = np.load(PANEL, allow_pickle=False)
    print("preparing xs panel ...", flush=True)
    X = prep_xs(z)
    n = len(X["dates"])
    X["pub_rows"] = np.isfinite(z["SI"]).sum(1) > 100
    X["settle_rows"] = z["SETTLE"].astype(bool)
    FX = calfeat(X["dates"])
    print("preparing etf panel ...", flush=True)
    E = prep_etf(z)
    del z
    FE = calfeat(E["edates"])

    xs_fam = build_xs_family(X, FX)
    etf_fam = build_etf_family(E, FE)
    N = len(xs_fam) + len(etf_fam)
    print(f"family size N = {N}", flush=True)

    xd = X["dates"] <= XS_SPLIT
    xh = X["dates"] > XS_SPLIT
    ed = E["edates"] <= ETF_SPLIT
    eh = E["edates"] > ETF_SPLIT
    fd = (E["edates"] <= FOMC_SPLIT) & (E["edates"] >= "2011-01-01")
    fh = E["edates"] > FOMC_SPLIT

    def masks(f):
        if isinstance(f, ETFF):
            if f.window == "fomc":
                return fd, fh
            return ed, eh
        return xd, xh

    def score_all(rx, re_):
        out = {}
        for f in xs_fam:
            pnl = xs_eval(f.book, f.pos, rx, n, ret=X["ret"], src=f.src)
            out[f.name] = pnl
        for f in etf_fam:
            out[f.name] = etf_eval(f.W, E["ERET"], re_, f.live)
        return out

    print("design pass ...", flush=True)
    base = score_all(0, 0)
    design = {}
    for f in xs_fam + etf_fam:
        dm, _ = masks(f)
        design[f.name] = sharpe(base[f.name][dm])

    print(f"null: {NULL_REPS} replicates ...", flush=True)
    rng = np.random.default_rng(RNG_SEED)
    nn = len(E["edates"])
    S = {k: np.zeros(NULL_REPS) for k in base}
    for rep in range(NULL_REPS):
        rx = int(rng.integers(200, n - 200))
        re_ = int(rng.integers(400, nn - 400))
        cur = score_all(rx, re_)
        for f in xs_fam + etf_fam:
            dm, _ = masks(f)
            S[f.name][rep] = sharpe(cur[f.name][dm])
        if (rep + 1) % 50 == 0:
            print(f"  rep {rep+1}/{NULL_REPS}", flush=True)

    zs = {}
    for k in base:
        mu, sd = S[k].mean(), S[k].std()
        zs[k] = (design[k] - mu) / sd if sd > 0 else 0.0
    Z = np.zeros((NULL_REPS, len(base)))
    keys = list(base)
    for j, k in enumerate(keys):
        mu, sd = S[k].mean(), S[k].std()
        Z[:, j] = (S[k] - mu) / (sd if sd > 0 else 1.0)
    maxz = np.abs(Z).max(axis=1)

    mech = {f.name: f.mech for f in xs_fam + etf_fam}
    rows = []
    for f in xs_fam + etf_fam:
        k = f.name
        dm, _ = masks(f)
        act = int((f.pos != 0).sum()) if isinstance(f, XSF) else int((np.abs(f.W).sum(1) > 0).sum())
        rows.append(dict(name=k, dataset=("xs" if isinstance(f, XSF) else
                                          ("fomc" if f.window == "fomc" else "etf")),
                         design_sharpe=round(design[k], 4),
                         null_mean=round(float(S[k].mean()), 4),
                         null_sd=round(float(S[k].std()), 4),
                         z=round(float(zs[k]), 3),
                         active_sessions=act,
                         mechanism=mech[k]))
    rows.sort(key=lambda r: -abs(r["z"]))
    res = dict(
        generated_utc=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        n_formulas=N,
        analytic_sqrt_2lnN=round(float(np.sqrt(2 * np.log(N))), 3),
        null_reps=NULL_REPS,
        expected_max_abs_z=round(float(maxz.mean()), 3),
        p90_max_abs_z=round(float(np.percentile(maxz, 90)), 3),
        p95_max_abs_z=round(float(np.percentile(maxz, 95)), 3),
        p99_max_abs_z=round(float(np.percentile(maxz, 99)), 3),
        observed_max_abs_z=round(float(max(abs(r["z"]) for r in rows)), 3),
        windows=dict(
            xs_design=f"{X['dates'][0]}..{XS_SPLIT} ({int(xd.sum())} sessions)",
            xs_holdout=f"2023-07-01..{X['dates'][-1]} ({int(xh.sum())} sessions)",
            etf_design=f"{E['edates'][0]}..{ETF_SPLIT} ({int(ed.sum())} sessions)",
            etf_holdout=f"2017-01-01..{E['edates'][-1]} ({int(eh.sum())} sessions)",
            fomc_design=f"2011-01-01..{FOMC_SPLIT} ({int(fd.sum())} sessions)",
            fomc_holdout=f"2020-01-01..{E['edates'][-1]} ({int(fh.sum())} sessions)",
        ),
        costs=dict(xs_bp_per_side=COST_XS_BP, etf_bp_per_side=COST_ETF_BP,
                   short_borrow_bp_yr=BORROW_BP_YR),
        universe=dict(n_symbols=int(len(X["syms"])), adv_min_usd=ADV_MIN, px_min=PX_MIN),
        formulas=rows,
    )
    (OUT / "NEWTERR_flowcal_DESIGN.json").write_text(json.dumps(res, indent=2))
    np.savez_compressed(ROOT / "research" / "data" / "newterr_flowcal" / "design_pnl.npz",
                        **{k: v for k, v in base.items()})
    print(json.dumps({k: res[k] for k in
                      ("n_formulas", "expected_max_abs_z", "p95_max_abs_z",
                       "observed_max_abs_z")}, indent=2))
    for r in rows[:12]:
        print(f"  z={r['z']:+6.2f}  S={r['design_sharpe']:+.3f}  {r['dataset']:4s} {r['name']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
