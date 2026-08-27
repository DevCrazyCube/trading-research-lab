#!/usr/bin/env python3
"""INVENT 0823 -- RATES / TREASURY TERM-STRUCTURE.  Published-anchor relative value.

CENTRAL THESIS APPLIED
======================
Free data prices a STATISTIC, never a CLAIM.  The surviving edges in this programme (CEF
discount, ETF-sibling RV) work because a THIRD PARTY PUBLISHES THE TETHER VALUE.  In the
Treasury complex the third party is the **US Treasury / Federal Reserve H.15 constant-maturity
par yield curve** (FRED DGS3MO..DGS30, DFII5..DFII30, T5YIE/T10YIE), published every business
day, free, permanent, and *the exact object every Treasury ETF is a wrapper on*.

That gives three genuinely tethered structures, none of which is a "statistic":

  A. LADDER RESIDUAL vs THE PUBLISHED CURVE.  Each wrapper is a claim on ONE segment.  Strip
     out the move its OWN published key rate explains (rolling single-factor sensitivity,
     known at t-1); cross-sectionally demean across a six-segment ladder of DISTINCT segments
     (which also removes the 15:30 published-snapshot vs 16:00 ETF-close timing artifact);
     trade it duration-neutral with 1/duration weights.

  C. PUBLISHED-BREAKEVEN GAP.  FRED publishes the 5y and 10y breakeven inflation rate daily.
     A TIPS wrapper against a duration-matched nominal wrapper is a tradable long-breakeven
     book.  Its return must track the PUBLISHED breakeven.  When it does not, that is the
     CEF-NAV structure exactly: a tradable claim against a published anchor value.

  D. PUBLISHED ROLL-DOWN / CARRY.  The shape of the published curve IS the term premium.
     Carry + roll-down per unit duration is computable from the published curve alone and is
     the structural (not data-mined) reason one maturity bucket out-earns another.

  F. PUBLISHED-BUTTERFLY GAP.  The published curve pins curvature too; a duration-weighted
     belly-vs-wings ETF book is the tradable expression of that published number.

  G. PUBLISHED REAL-CURVE LADDER.  Family A on the published TIPS real curve (DFII5/10/30).

  B. SIBLING WRAPPERS.  SHY/VGSH/SCHO, IEI/VGIT/SCHR, TLT/VGLT/SPTL, EDV/ZROZ are pairs of
     wrappers over the SAME published curve segment from different sponsors with different
     authorised participants.  Same tether as ETF-sibling RV, but inside a complex with no
     borrow wall at all.

DISCIPLINE (from the programme's hard lessons)
==============================================
 * NO regime conditioning or gating on macro state.  Not one formula switches on a regime.
 * rho1(Delta spread) BOUNCE GATE runs BEFORE the gross bar.  For a book whose spread is the
   cumulative residual return, Delta(spread) IS the daily residual return, so the gate is
   simply rho1 of the residual return series measured on the DESIGN window.  rho1 < -0.35 =
   measurement-error bounce = dead on arrival.  Inside a tethered family a HIGH gross Sharpe
   at short horizon is EVIDENCE AGAINST, not for.
 * The bar is applied to GROSS first.  N is pre-registered, the analytic bar sqrt(2 ln 2N) is
   reported, and a SIZE-MATCHED PLACEBO (cross-sectional signal permutation for XS books,
   circular block shift for time-series books, same N, same books, 400 draws) gives the
   empirical max-|t| null.  The bar is the LARGER of the two.
 * Design window is scored alone.  --stage design REFUSES to return held-out data.
 * Every book is long-short INSIDE the Treasury complex; every short leg is a mega-liquid ETB
   Treasury ETF.  Borrow is charged at the ETB floor anyway.
 * Costs: per-symbol half-spread = max(dollar-volume tier, half-a-penny tick floor), charged
   on both legs, plus 0.15 bp/turnover regulatory, plus borrow on short notional.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[2]
CACHE = ROOT / "research" / "data" / "ratescredit_cache"
OUT = ROOT / "research" / "trading_bot"

START = "2010-08-06"
DESIGN_LO, DESIGN_HI = "2010-08-06", "2020-12-31"
HELD_LO, HELD_HI = "2021-01-01", "2026-08-18"
END = "2026-08-18"

REG_BP = 0.15          # SEC 31 + FINRA TAF per unit turnover
BORROW_ETB = 0.0033    # B22G easy-to-borrow general-collateral median, per year
BETA_WIN = 250
BETA_MIN = 200

# The published-curve key rate each wrapper is a claim on.
KEYRATE = {
    "SHY": "DGS2", "VGSH": "DGS2", "SCHO": "DGS2",
    "IEI": "DGS5", "VGIT": "DGS5", "SCHR": "DGS5",
    "IEF": "DGS7",
    "TLH": "DGS20", "TLT": "DGS20", "VGLT": "DGS20", "SPTL": "DGS20",
    "EDV": "DGS30", "ZROZ": "DGS30",
    # TIPS wrappers are claims on the published REAL curve
    "STIP": "DFII5", "VTIP": "DFII5", "SCHP": "DFII10", "TIP": "DFII10", "LTPZ": "DFII30",
}
# one wrapper per DISTINCT published curve segment -- no sponsor siblings, so the
# cross-section cannot be contaminated by sibling tick bounce
LADDER = ["SHY", "IEI", "IEF", "TLH", "TLT", "EDV"]
LADDER_WIDE = ["SHY", "VGSH", "SCHO", "IEI", "VGIT", "SCHR", "IEF",
               "TLH", "TLT", "VGLT", "SPTL", "EDV", "ZROZ"]
TIPS_LADDER = ["STIP", "SCHP", "LTPZ"]
TIPS = ["TIP", "SCHP", "STIP", "LTPZ"]
# breakeven books: TIPS wrapper vs the duration-nearest NOMINAL wrapper, anchored on
# the published breakeven series
BE_BOOKS = [("TIP", "IEF", "T10YIE"), ("STIP", "SHY", "T5YIE"), ("LTPZ", "TLT", "T10YIE")]
PAIRS = [("EDV", "ZROZ"), ("TLT", "VGLT"), ("TLT", "SPTL"), ("IEI", "VGIT"),
         ("SHY", "VGSH"), ("SHY", "SCHO"), ("IEI", "SCHR")]
# published butterfly: belly against the two wings, duration-weighted
FLY = ("IEF", "SHY", "TLT", 7.0, 2.0, 20.0)

# published maturity grid for interpolation (years)
GRID = [("DGS3MO", 0.25), ("DGS1", 1.0), ("DGS2", 2.0), ("DGS5", 5.0),
        ("DGS7", 7.0), ("DGS10", 10.0), ("DGS20", 20.0), ("DGS30", 30.0)]

UNIVERSE = sorted(set(list(KEYRATE) + LADDER + LADDER_WIDE + TIPS_LADDER + TIPS
                      + [s for p in PAIRS for s in p]
                      + [s for b in BE_BOOKS for s in b[:2]]
                      + list(FLY[:3]) + ["BIL", "SHV"]) - {"VTIP"})


def _to_date(ts: int) -> str:
    """Yahoo daily bars in this cache are stamped at the SESSION OPEN, 13:30 UTC (09:30
    EDT) / 14:30 UTC (09:30 EST) -- both on the correct UTC calendar day.  Adding a
    12-hour offset (as scripts/trading_bot/newterr_ratescredit.py does) rolls every bar
    forward one day and decorrelates the ETF panel from the published FRED curve:
    corr(r_TLT, dDGS20) is -0.20 shifted, -0.74 aligned."""
    return dt.datetime.fromtimestamp(ts, dt.UTC).strftime("%Y-%m-%d")


# --------------------------------------------------------------------- panel
class Panel:
    def __init__(self, end: str):
        px = json.loads((CACHE / "etf_daily.json").read_text())
        fred = json.loads((CACHE / "fred_daily.json").read_text())

        dates = [_to_date(t) for t in px["TLT"]["t"]]
        dates = [d for d in dates if START <= d <= end]
        self.dates = np.array(dates)
        pos = {d: i for i, d in enumerate(dates)}
        T = len(dates)
        self.T = T

        self.syms = list(UNIVERSE)
        S = len(self.syms)
        self.sidx = {s: i for i, s in enumerate(self.syms)}
        self.R = np.full((T, S), np.nan)
        self.PX = np.full((T, S), np.nan)
        self.ADV = np.zeros(S)
        for s in self.syms:
            j = self.sidx[s]
            d = px[s]
            ac = [np.nan if v is None else v for v in d["adjclose"]]
            cl = [np.nan if v is None else v for v in (d["close"] or [])]
            vol = [0.0 if v is None else v for v in (d["volume"] or [])]
            prev = np.nan
            dv = []
            for k, ts in enumerate(d["t"]):
                i = pos.get(_to_date(ts))
                v = ac[k]
                if i is not None:
                    if np.isfinite(v) and np.isfinite(prev) and prev > 0:
                        self.R[i, j] = v / prev - 1.0
                    if k < len(cl) and np.isfinite(cl[k]):
                        self.PX[i, j] = cl[k]
                        dv.append(vol[k] * cl[k])
                if np.isfinite(v):
                    prev = v
            self.ADV[j] = float(np.median(dv)) if dv else 0.0

        dd = [dt.date.fromisoformat(x) for x in dates]
        self.caldays = np.array([1.0] + [(dd[i] - dd[i - 1]).days for i in range(1, T)])

        # FRED forward-filled onto trading days with a 7-calendar-day staleness cap
        self.F = {}
        for sid, series in fred.items():
            arr = np.full(T, np.nan)
            kv = sorted(series.items())
            p, last_d, last_v = 0, None, np.nan
            for i, d in enumerate(dates):
                while p < len(kv) and kv[p][0] <= d:
                    last_d, last_v = kv[p]
                    p += 1
                if last_d is not None and (dt.date.fromisoformat(d)
                                           - dt.date.fromisoformat(last_d)).days <= 7:
                    arr[i] = last_v
            self.F[sid] = arr

        # half-spread bp: dollar-volume tier, floored by half a penny of tick
        self.hs = np.zeros(S)
        for s in self.syms:
            j = self.sidx[s]
            a = self.ADV[j]
            tier = (0.7 if a > 500e6 else 1.2 if a > 100e6 else
                    2.5 if a > 20e6 else 4.0 if a > 5e6 else 8.0)
            p = np.nanmedian(self.PX[:, j])
            tick = 100.0 * 0.005 / p if np.isfinite(p) and p > 0 else tier
            self.hs[j] = max(tier, tick)

    def r(self, s):
        return self.R[:, self.sidx[s]]

    def mask(self, lo, hi):
        return (self.dates >= lo) & (self.dates <= hi)


# ------------------------------------------------------- rolling primitives
def _roll_sum(x, w):
    """Rolling sum over the w rows ENDING at t (inclusive). NaN counts as 0."""
    c = np.concatenate([[0.0], np.cumsum(np.nan_to_num(x))])
    out = np.full(len(x), np.nan)
    out[w - 1:] = c[w:] - c[:-w]
    return out


def _roll_strict(x, w):
    """Rolling sum ENDING at t, NaN if ANY value in the window is missing."""
    s = _roll_sum(x, w)
    n = _roll_sum(np.isfinite(x).astype(float), w)
    return np.where(n >= w - 1e-9, s, np.nan)


def rolling_ols(y, X, w=BETA_WIN, minobs=BETA_MIN, ridge=1e-10):
    """beta[t] from rows [t-w+1 .. t].  NaN rows are dropped from the window."""
    T, k = X.shape
    ok = np.isfinite(y) & np.all(np.isfinite(X), axis=1)
    yv = np.where(ok, y, 0.0)
    Xv = np.where(ok[:, None], X, 0.0)
    n = _roll_sum(ok.astype(float), w)
    XtX = np.empty((T, k, k))
    Xty = np.empty((T, k))
    for a in range(k):
        Xty[:, a] = _roll_sum(Xv[:, a] * yv, w)
        for b in range(a, k):
            v = _roll_sum(Xv[:, a] * Xv[:, b], w)
            XtX[:, a, b] = v
            XtX[:, b, a] = v
    beta = np.full((T, k), np.nan)
    eye = np.eye(k) * ridge
    for t in range(T):
        if not np.isfinite(n[t]) or n[t] < minobs:
            continue
        try:
            beta[t] = np.linalg.solve(XtX[t] + eye, Xty[t])
        except np.linalg.LinAlgError:
            pass
    return beta


def zscore(x, w):
    """z of x against its own trailing w-day distribution (window INCLUDES t)."""
    n = _roll_sum(np.isfinite(x).astype(float), w)
    m = _roll_sum(x, w) / np.maximum(n, 1)
    s2 = _roll_sum(x * x, w) / np.maximum(n, 1) - m * m
    s = np.sqrt(np.maximum(s2, 1e-24))
    z = (x - m) / s
    return np.where(n >= 0.8 * w, z, np.nan)


def cum_k(x, k):
    """Sum of the k values ENDING at t; NaN if any is missing."""
    return _roll_strict(x, k)


def interp_y(F, m):
    """Linear interpolation of the published par curve at maturity m (years)."""
    ms = [g[1] for g in GRID]
    for i in range(len(ms) - 1):
        if ms[i] <= m <= ms[i + 1]:
            a = (m - ms[i]) / (ms[i + 1] - ms[i])
            return (1 - a) * F[GRID[i][0]] + a * F[GRID[i + 1][0]]
    return F[GRID[-1][0]] if m > ms[-1] else F[GRID[0][0]]


# ------------------------------------------------------------------- engine
class Engine:
    """One stable primitive: each wrapper's sensitivity to the PUBLISHED yield it is a
    claim on, estimated by a rolling single-factor regression.  No matrix inversion, so
    no exploding hedge.  Duration = -beta is in return per +1pp of the published yield."""

    def __init__(self, P: Panel):
        self.P = P
        T = P.T
        self.dY = {}
        for k in set(KEYRATE.values()) | {"DGS10", "DGS3MO"}:
            y = P.F[k]
            self.dY[k] = np.concatenate([[np.nan], np.diff(y)])
        self.beta, self.dur = {}, {}
        for s in set(KEYRATE) & set(P.syms):
            b = rolling_ols(P.r(s), self.dY[KEYRATE[s]][:, None])[:, 0]
            self.beta[s] = b
            self.dur[s] = -b * 100.0        # years: return-per-pp expressed in percent
        # residual of the wrapper against its OWN published key rate, using a
        # sensitivity known at t-1 (no look-ahead in the anchor either)
        self.resid = {}
        for s in self.beta:
            bl = np.concatenate([[np.nan], self.beta[s][:-1]])
            self.resid[s] = P.r(s) - bl * self.dY[KEYRATE[s]]

    def lag_dur(self, s):
        d = np.concatenate([[np.nan], self.dur[s][:-1]])
        return np.where(np.isfinite(d) & (d > 0.15), d, np.nan)

    def pair_weights(self, a, b_):
        """+1 in a, -beta in b, beta = rolling OLS of r_a on r_b."""
        P = self.P
        bt = rolling_ols(P.r(a), P.r(b_)[:, None])[:, 0]
        W = np.zeros((P.T, len(P.syms)))
        W[:, P.sidx[a]] = 1.0
        W[:, P.sidx[b_]] = -np.nan_to_num(bt)
        W[~np.isfinite(bt)] = 0.0
        return W, bt


# ------------------------------------------------------------------ scoring
def score(P: Panel, W: np.ndarray, m: np.ndarray, lag: int = 1):
    """W[t] is the DESIRED weight formed from data through close(t).  Shift by `lag`
    so the book held over day t (earning r[t]) was decided at close(t-lag)."""
    Wl = np.zeros_like(W)
    if lag > 0:
        Wl[lag:] = W[:-lag]
    else:
        Wl = W.copy()
    g = np.sum(np.nan_to_num(P.R) * Wl, axis=1)
    dW = np.abs(np.diff(Wl, axis=0, prepend=np.zeros((1, W.shape[1]))))
    cost = np.sum(dW * (P.hs[None, :] + REG_BP) / 1e4, axis=1)
    shorts = np.sum(np.maximum(-Wl, 0.0), axis=1)
    borrow = shorts * BORROW_ETB * P.caldays / 365.0
    n = g - cost - borrow
    mm = m & np.any(Wl != 0, axis=1)
    return _stats(g[mm], n[mm], np.sum(dW, axis=1)[mm], cost[mm])


def _stats(g, n, tov, cost):
    k = len(g)
    if k < 60:
        return None
    sg, sn = np.std(g, ddof=1), np.std(n, ddof=1)
    out = {
        "n_days": int(k),
        "gross_bps": float(np.mean(g) * 1e4),
        "net_bps": float(np.mean(n) * 1e4),
        "gross_sharpe": float(np.mean(g) / sg * np.sqrt(252)) if sg > 0 else 0.0,
        "net_sharpe": float(np.mean(n) / sn * np.sqrt(252)) if sn > 0 else 0.0,
        "gross_t": float(np.mean(g) / sg * np.sqrt(k)) if sg > 0 else 0.0,
        "net_t": float(np.mean(n) / sn * np.sqrt(k)) if sn > 0 else 0.0,
        "turnover": float(np.mean(tov)),
        "cost_bps": float(np.mean(cost) * 1e4),
    }
    out["breakeven_hs_bp"] = (float(out["gross_bps"] / out["turnover"])
                              if out["turnover"] > 1e-9 else 0.0)
    return out


def rho1(x):
    x = x[np.isfinite(x)]
    if len(x) < 100:
        return float("nan")
    x = x - x.mean()
    return float(np.sum(x[1:] * x[:-1]) / np.sum(x * x))


def norm_rows(W):
    W = np.nan_to_num(W)
    g = np.sum(np.abs(W), axis=1, keepdims=True)
    out = np.zeros_like(W)
    np.divide(W, g, out=out, where=g > 1e-12)
    return out


# ---------------------------------------------------------------- formulas
def build(P: Panel, E: Engine):
    T, S = P.T, len(P.syms)
    F = P.F
    fs = []

    def add(**kw):
        fs.append(kw)

    # ========== A. LADDER RESIDUAL AGAINST THE PUBLISHED CURVE ==========
    A_MECH = (
        "Every Treasury wrapper is a claim on one segment of the SAME published "
        "constant-maturity curve, and the US Treasury publishes that curve every business "
        "day for free.  Strip out each wrapper's move that its OWN published key rate "
        "explains and what remains is the wrapper dislocating from the published claim.  "
        "Index funds are mandate-locked to their maturity bucket and cannot move to the "
        "cheap segment; only authorised participants can, and only at T+1 with a real "
        "Treasury basket to source, so the dislocation is closed with a lag.")

    def ladder_sigs(panel, k, sign, band=0.0, zwin=252):
        s = np.full((T, len(panel)), np.nan)
        for i, sym in enumerate(panel):
            z = zscore(cum_k(E.resid[sym], k), zwin)
            if band > 0:
                z = np.where(np.abs(z) >= band, z, 0.0)
            s[:, i] = sign * z
        # cross-sectional demean: removes the common component, which is exactly the
        # 15:30 published-curve snapshot vs the 16:00 ETF close timing artifact
        return s - np.nanmean(s, axis=1, keepdims=True)

    def ladder_assemble(sg, panel):
        W = np.zeros((T, S))
        for i, sym in enumerate(panel):
            W[:, P.sidx[sym]] += np.nan_to_num(sg[:, i] / E.lag_dur(sym))
        return norm_rows(W)   # duration-neutral: sum_i w_i D_i propto sum_i s_i = 0

    for j, k in enumerate((1, 3, 5, 10, 21), start=1):
        add(name=f"A{j}_ladder_resid_fade_{k}d", family="ladder_resid", kind="xs",
            mech=A_MECH, panel=LADDER,
            sigs=lambda k=k: ladder_sigs(LADDER, k, -1.0),
            assemble=lambda sg: ladder_assemble(sg, LADDER))
    add(name="A6_ladder_resid_fade_5d_band15", family="ladder_resid", kind="xs",
        mech=A_MECH + "  Act only when the dislocation exceeds its own bounce: |z|>=1.5.",
        panel=LADDER, sigs=lambda: ladder_sigs(LADDER, 5, -1.0, band=1.5),
        assemble=lambda sg: ladder_assemble(sg, LADDER))
    add(name="A7_ladder_resid_ride_63d", family="ladder_resid", kind="xs",
        mech=("Competing mechanism, OPPOSITE sign, pre-registered as such: sponsor-level "
              "flow into a maturity bucket is persistent because advisor model portfolios "
              "reallocate duration over quarters, so a segment that has richened against "
              "the published curve keeps richening."),
        panel=LADDER, sigs=lambda: ladder_sigs(LADDER, 63, +1.0),
        assemble=lambda sg: ladder_assemble(sg, LADDER))
    add(name="A8_ladderwide_resid_fade_5d", family="ladder_resid", kind="xs",
        mech=A_MECH + "  Widened to all 13 nominal wrappers.  FLAGGED: this panel contains "
                      "sponsor siblings, so part of any score here is sibling tick bounce "
                      "rather than a curve-segment dislocation.",
        panel=LADDER_WIDE, sigs=lambda: ladder_sigs(LADDER_WIDE, 5, -1.0),
        assemble=lambda sg: ladder_assemble(sg, LADDER_WIDE))

    # ========== B. SIBLING WRAPPERS OVER THE SAME PUBLISHED SEGMENT ==========
    B_MECH = ("Two wrappers on the SAME published curve segment from different sponsors "
              "with different authorised-participant sets.  The claim is identical; only "
              "the flow differs, so divergence is flow and creation/redemption restores it.")
    pw, pr = {}, {}
    for a, b_ in PAIRS:
        W, bt = E.pair_weights(a, b_)
        pw[(a, b_)] = W
        rr = np.sum(np.nan_to_num(P.R) * W, axis=1)
        rr[~np.isfinite(bt)] = np.nan
        pr[(a, b_)] = rr

    def pair_sig(pair, band=1.0, zwin=252, k=60):
        z = zscore(cum_k(pr[pair], k), zwin)
        return -np.where(np.abs(z) >= band, z, 0.0)

    for i, pair in enumerate(PAIRS, start=1):
        add(name=f"B{i}_sib_{pair[0]}_{pair[1]}", family="sibling", kind="ts", mech=B_MECH,
            sigs=lambda pair=pair: pair_sig(pair)[:, None],
            assemble=lambda sg, pair=pair: norm_rows(
                np.nan_to_num(sg[:, 0])[:, None] * pw[pair]))

    def sib_pool_assemble(sg):
        W = np.zeros((T, S))
        for i, p in enumerate(PAIRS):
            W += np.nan_to_num(sg[:, i])[:, None] * pw[p]
        return norm_rows(W)

    add(name="B8_sib_pool_band10", family="sibling", kind="xs",
        mech=B_MECH + "  Pooled across all seven sponsor pairs.",
        sigs=lambda: np.column_stack([pair_sig(p, 1.0) for p in PAIRS]),
        assemble=sib_pool_assemble)
    add(name="B9_sib_pool_band20", family="sibling", kind="xs",
        mech=B_MECH + "  Pooled, and only once the dislocation clears twice its own sigma "
                      "-- the OU lesson that a low band fades measurement-error bounce.",
        sigs=lambda: np.column_stack([pair_sig(p, 2.0) for p in PAIRS]),
        assemble=sib_pool_assemble)

    # ========== C. PUBLISHED-BREAKEVEN GAP (the CEF-NAV structure, in rates) ==========
    C_MECH = (
        "FRED publishes the 5y and 10y breakeven inflation rate every business day.  A "
        "TIPS wrapper held against a duration-matched NOMINAL wrapper is a tradable "
        "long-breakeven book, so its return must track the PUBLISHED breakeven.  The gap "
        "between the two is a tradable claim priced against a third-party published anchor "
        "-- structurally the same object as a closed-end fund's discount to NAV.  TIPS are "
        "the least liquid Treasury instrument and the first leg a levered relative-value "
        "book liquidates, so the gap opens on forced flow, not on information.")
    bew, ber = {}, {}
    for tp, nom, anch in BE_BOOKS:
        W, bt = E.pair_weights(tp, nom)
        bew[tp] = W
        rr = np.sum(np.nan_to_num(P.R) * W, axis=1)
        rr[~np.isfinite(bt)] = np.nan
        ber[tp] = rr

    dBE = {a: np.concatenate([[np.nan], np.diff(F[a])]) for a in {b[2] for b in BE_BOOKS}}

    def be_gap(tp, anch, k, band=0.0, zwin=252):
        c = rolling_ols(ber[tp], dBE[anch][:, None])[:, 0]
        cl = np.concatenate([[np.nan], c[:-1]])
        u = ber[tp] - cl * dBE[anch]          # signal only; the P&L stays fully tradable
        z = zscore(cum_k(u, k), zwin)
        if band > 0:
            z = np.where(np.abs(z) >= band, z, 0.0)
        return -z

    for i, k in enumerate((5, 10, 21), start=1):
        add(name=f"C{i}_begap_TIP_IEF_{k}d", family="breakeven", kind="ts", mech=C_MECH,
            sigs=lambda k=k: be_gap("TIP", "T10YIE", k)[:, None],
            assemble=lambda sg: norm_rows(np.nan_to_num(sg[:, 0])[:, None] * bew["TIP"]))
    add(name="C4_begap_STIP_SHY_10d", family="breakeven", kind="ts",
        mech=C_MECH + "  Front segment against the published 5y breakeven, where the "
                      "seasonal NSA-CPI accrual makes the wrapper hardest to price.",
        sigs=lambda: be_gap("STIP", "T5YIE", 10)[:, None],
        assemble=lambda sg: norm_rows(np.nan_to_num(sg[:, 0])[:, None] * bew["STIP"]))
    add(name="C5_begap_LTPZ_TLT_10d", family="breakeven", kind="ts",
        mech=C_MECH + "  Long segment, the thinnest TIPS wrapper of all.",
        sigs=lambda: be_gap("LTPZ", "T10YIE", 10)[:, None],
        assemble=lambda sg: norm_rows(np.nan_to_num(sg[:, 0])[:, None] * bew["LTPZ"]))

    def be_pool_assemble(sg):
        W = np.zeros((T, S))
        for i, (tp, nom, anch) in enumerate(BE_BOOKS):
            W += np.nan_to_num(sg[:, i])[:, None] * bew[tp]
        return norm_rows(W)

    add(name="C6_begap_pool_10d", family="breakeven", kind="xs",
        mech=C_MECH + "  Pooled across the three TIPS segments.",
        sigs=lambda: np.column_stack([be_gap(tp, anch, 10) for tp, nom, anch in BE_BOOKS]),
        assemble=be_pool_assemble)

    # ========== D. PUBLISHED ROLL-DOWN / CARRY, DURATION-NEUTRAL ==========
    D_MECH = (
        "The shape of the published curve IS the term premium.  Carry plus roll-down per "
        "unit duration is computable from the published curve alone -- no estimation, no "
        "fitting -- and it is the structural reason one maturity bucket out-earns another.  "
        "Index funds are mandate-locked to their bucket and cannot migrate to the richest "
        "point on the curve, so the compensation survives inside the complex.")
    ROLL_M = {"SHY": 2.0, "IEI": 4.5, "IEF": 8.5, "TLH": 14.0, "TLT": 25.0, "EDV": 25.0}
    y3m = F["DGS3MO"]
    cr = np.full((T, len(LADDER)), np.nan)
    for i, s in enumerate(LADDER):
        m = ROLL_M[s]
        ym, ym1 = interp_y(F, m), interp_y(F, max(m - 1.0, 0.25))
        d = E.lag_dur(s)
        with np.errstate(invalid="ignore", divide="ignore"):
            cr[:, i] = (ym - y3m) / d + (ym - ym1)

    def roll_sigs(smooth=1):
        x = cr if smooth <= 1 else np.column_stack(
            [cum_k(cr[:, i], smooth) / smooth for i in range(cr.shape[1])])
        return x - np.nanmean(x, axis=1, keepdims=True)

    def roll_assemble(sg, rebal=1):
        W = ladder_assemble(sg, LADDER)
        if rebal > 1:
            keep = np.arange(T) % rebal != 0
            for t in range(1, T):
                if keep[t] and np.any(W[t] != 0):
                    W[t] = W[t - 1]
        return W

    add(name="D1_rolldown_daily", family="rolldown", kind="xs", mech=D_MECH,
        panel=LADDER, sigs=lambda: roll_sigs(1),
        assemble=lambda sg: roll_assemble(sg, 1))
    add(name="D2_rolldown_weekly", family="rolldown", kind="xs",
        mech=D_MECH + "  Weekly refresh; the published shape moves slowly.",
        panel=LADDER, sigs=lambda: roll_sigs(1),
        assemble=lambda sg: roll_assemble(sg, 5))
    add(name="D3_rolldown_smooth21_weekly", family="rolldown", kind="xs",
        mech=D_MECH + "  Month-averaged published shape, to price the term premium rather "
                      "than the day's curve noise.",
        panel=LADDER, sigs=lambda: roll_sigs(21),
        assemble=lambda sg: roll_assemble(sg, 5))
    add(name="D4_rolldown_smooth21_monthly", family="rolldown", kind="xs",
        mech=D_MECH + "  Monthly refresh -- the cheapest expression of the same shape.",
        panel=LADDER, sigs=lambda: roll_sigs(21),
        assemble=lambda sg: roll_assemble(sg, 21))

    # ========== F. PUBLISHED-BUTTERFLY GAP ==========
    F_MECH = (
        "The published curve pins CURVATURE as well as level and slope: the 2s-7s-30s "
        "butterfly is a number the Treasury publishes daily.  A duration-weighted "
        "belly-versus-wings ETF book is the tradable expression of exactly that number, so "
        "the gap between the two is a published-anchor dislocation.  Mortgage servicers "
        "and GSEs are structurally short convexity and must hedge at the wings on a "
        "schedule set by lock periods, which is what opens the gap.")
    belly, wl, wr, mb, ml, mr = FLY
    flyW = np.zeros((T, S))
    db, dl, dr = E.lag_dur(belly), E.lag_dur(wl), E.lag_dur(wr)
    with np.errstate(invalid="ignore", divide="ignore"):
        flyW[:, P.sidx[belly]] = 2.0 / db
        flyW[:, P.sidx[wl]] = -1.0 / dl
        flyW[:, P.sidx[wr]] = -1.0 / dr
    flyW = np.nan_to_num(flyW)
    fly_r = np.sum(np.nan_to_num(P.R) * flyW, axis=1)
    fly_r[~(np.isfinite(db) & np.isfinite(dl) & np.isfinite(dr))] = np.nan
    fly_pub = 2 * interp_y(F, mb) - interp_y(F, ml) - interp_y(F, mr)
    dfly = np.concatenate([[np.nan], np.diff(fly_pub)])

    def fly_gap(k, band=0.0):
        c = rolling_ols(fly_r, dfly[:, None])[:, 0]
        cl = np.concatenate([[np.nan], c[:-1]])
        u = fly_r - cl * dfly
        z = zscore(cum_k(u, k), 252)
        if band > 0:
            z = np.where(np.abs(z) >= band, z, 0.0)
        return -z

    for i, k in enumerate((10, 21), start=1):
        add(name=f"F{i}_flygap_{k}d", family="butterfly", kind="ts", mech=F_MECH,
            sigs=lambda k=k: fly_gap(k)[:, None],
            assemble=lambda sg: norm_rows(np.nan_to_num(sg[:, 0])[:, None] * flyW))

    # ========== G. PUBLISHED REAL-CURVE LADDER (TIPS) ==========
    G_MECH = ("FRED publishes the TIPS real-yield curve (DFII5/10/30) daily.  The same "
              "wrapper-versus-published-claim argument as family A, on the real curve, "
              "where the wrappers are far thinner and the authorised-participant channel "
              "far narrower -- so if the mechanism exists anywhere it should be largest "
              "here.")
    for i, k in enumerate((5, 10), start=1):
        add(name=f"G{i}_realladder_resid_fade_{k}d", family="real_ladder", kind="xs",
            mech=G_MECH, panel=TIPS_LADDER,
            sigs=lambda k=k: ladder_sigs(TIPS_LADDER, k, -1.0),
            assemble=lambda sg: ladder_assemble(sg, TIPS_LADDER))

    # ========== E. DECOYS / NEGATIVE CONTROLS ==========
    bilu = P.r("BIL") - np.concatenate([[np.nan], F["DTB3"][:-1]]) / 25200.0
    bilW = np.zeros((T, S))
    bilW[:, P.sidx["BIL"]] = 1.0
    bilW[:, P.sidx["SHV"]] = -1.0
    add(name="E1_decoy_BIL_vs_publishedbill", family="decoy", kind="ts",
        mech=("NEGATIVE CONTROL.  BIL has essentially no duration, so its return IS the "
              "published 3-month bill yield over 252 and nothing else.  Any 'residual' here "
              "is pure tick bounce.  If this scores, a high gross Sharpe in this complex "
              "means bounce, not edge."),
        sigs=lambda: (-zscore(cum_k(bilu, 5), 252))[:, None],
        assemble=lambda sg: norm_rows(np.nan_to_num(sg[:, 0])[:, None] * bilW))

    tlhW = np.zeros((T, S))
    tlhW[:, P.sidx["TLH"]] = 1.0
    tlhW[:, P.sidx["TLT"]] = -1.0
    add(name="E2_decoy_TLH_follows_TLT", family="decoy", kind="ts",
        mech=("DECOY / positive control for the lag test.  TLH is the thinnest nominal "
              "Treasury wrapper (51k shares/day) and should LAG TLT's print.  A large lag-0 "
              "diagnostic here with nothing at lag 1 is the signature of quote staleness."),
        sigs=lambda: np.sign(np.nan_to_num(P.r("TLT")))[:, None],
        assemble=lambda sg: norm_rows(np.nan_to_num(sg[:, 0])[:, None] * tlhW))

    diag = {"ladder_resid": {s: E.resid[s] for s in LADDER_WIDE},
            "sibling": {f"{a}/{b}": pr[(a, b)] for a, b in PAIRS},
            "breakeven": {b[0]: ber[b[0]] for b in BE_BOOKS},
            "real_ladder": {s: E.resid[s] for s in TIPS_LADDER},
            "butterfly": {"IEF_SHY_TLT": fly_r}}
    return fs, diag


# ------------------------------------------------------------------- placebo
def placebo(P, fs, built, m, draws, seed=20260823):
    """SIZE-MATCHED null: same books, same N, signal destroyed.
    XS books -> permute the signal across panel slots each day (keeps the book's own
    cross-sectional structure and its return covariance; kills only the assignment).
    TS books -> circular block shift of the signal series against the returns."""
    rng = np.random.default_rng(seed)
    T = P.T
    maxts = []
    for d in range(draws):
        best = 0.0
        for f, sg in zip(fs, built):
            s = np.array(sg, float, copy=True)
            if f["kind"] == "xs" and s.shape[1] > 1:
                idx = np.argsort(rng.random(s.shape), axis=1)
                s = np.take_along_axis(s, idx, axis=1)
            else:
                sh = int(rng.integers(63, T - 63))
                s = np.roll(s, sh, axis=0)
            W = f["assemble"](s)
            st = score(P, W, m)
            if st:
                best = max(best, abs(st["gross_t"]))
        maxts.append(best)
    a = np.array(maxts)
    return {"draws": draws, "p50": float(np.percentile(a, 50)),
            "p95": float(np.percentile(a, 95)), "mean": float(a.mean()),
            "max": float(a.max())}


# ---------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["design", "holdout"], required=True)
    ap.add_argument("--draws", type=int, default=400)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    end = DESIGN_HI if a.stage == "design" else END
    P = Panel(end)
    E = Engine(P)
    fs, diag = build(P, E)
    built = [f["sigs"]() for f in fs]

    N = len(fs)
    bar1 = float(np.sqrt(2 * np.log(N)))
    bar2 = float(np.sqrt(2 * np.log(2 * N)))

    lo, hi = (DESIGN_LO, DESIGN_HI) if a.stage == "design" else (HELD_LO, HELD_HI)
    m = P.mask(lo, hi)

    # rho1 bounce gate -- measured on the DESIGN window only, always
    dm = P.mask(DESIGN_LO, DESIGN_HI)
    gate = {}
    for fam, d in diag.items():
        for k, v in d.items():
            gate[f"{fam}:{k}"] = rho1(np.asarray(v)[dm])

    rows = []
    for f, sg in zip(fs, built):
        W = f["assemble"](sg)
        r1 = score(P, W, m, lag=1)
        r2 = score(P, W, m, lag=2)
        r0 = score(P, W, m, lag=0)
        row = {"name": f["name"], "family": f["family"], "kind": f["kind"],
               "mechanism": f["mech"], "lag1": r1, "lag2": r2, "lag0_diag": r0}
        rows.append(row)

    pl = placebo(P, fs, built, m, a.draws)

    res_out = {
        "stage": a.stage, "window": [lo, hi], "n_formulas": N,
        "analytic_bar_1sided_sqrt2lnN": bar1,
        "analytic_bar_2sided_sqrt2ln2N": bar2,
        "placebo_size_matched": pl,
        "bar_used": max(bar2, pl["p95"]),
        "rho1_delta_spread_design": gate,
        "half_spread_bp": {s: float(P.hs[P.sidx[s]]) for s in P.syms},
        "median_dollar_volume": {s: float(P.ADV[P.sidx[s]]) for s in P.syms},
        "rows": rows,
    }
    out = pathlib.Path(a.out) if a.out else OUT / f"INVENT_0823_rates_{a.stage}.json"
    out.write_text(json.dumps(res_out, indent=1))
    print(f"wrote {out}  N={N} bar2={bar2:.3f} placebo_p95={pl['p95']:.3f}")
    rr = sorted(rows, key=lambda r: -abs(r["lag1"]["gross_t"]) if r["lag1"] else 0)
    for r in rr[:12]:
        g = r["lag1"]
        if not g:
            continue
        print(f"  {r['name']:34s} grossSR {g['gross_sharpe']:+6.2f} t {g['gross_t']:+6.2f} "
              f"netSR {g['net_sharpe']:+6.2f} t {g['net_t']:+6.2f} "
              f"be_hs {g['breakeven_hs_bp']:6.2f}bp tov {g['turnover']:.3f}")


if __name__ == "__main__":
    main()
