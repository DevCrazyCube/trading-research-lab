#!/usr/bin/env python3
"""INVENT R3 -- MECHANICAL FLOW / STRUCTURE.  25 original formulas, one harness.

Design window is scored first and written out; the holdout is only scored when
called with --holdout, and the design file is never rewritten afterwards.

Panels
  ALP  Alpaca SIP daily bars, raw + split/div adjusted, 185 ETFs, 2016-01-04..2026-08-14
  AUC  Alpaca official opening/closing auction prints, same universe + t3 pool
  RV   research/data/rv_cache 5-minute bars, 137 names, 2021-01-04..2026-08-14

Windows (frozen here, before any result is seen)
  ALP/AUC daily   DESIGN <= 2021-12-31   HOLDOUT >= 2022-01-03
  RV intraday     DESIGN <= 2024-06-28   HOLDOUT >= 2024-07-01
"""
from __future__ import annotations

import gzip
import json
import math
import pathlib
import sys
from collections import defaultdict

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
CACHE = ROOT / "research" / "data" / "invr3flow_cache"
RVC = ROOT / "research" / "data" / "rv_cache"
T3C = ROOT / "research" / "data" / "t3_cache"
OUT = ROOT / "research" / "trading_bot"

DESIGN_END_D = "2021-12-31"
HOLD_START_D = "2022-01-03"
DESIGN_END_I = "2024-06-28"
HOLD_START_I = "2024-07-01"

BORROW_BP_YR = 50.0


# --------------------------------------------------------------------------
# universe definitions (mirrors invr3_flow_data.py)
# --------------------------------------------------------------------------
LETF_FAMILIES = {
    "SPY": [("SSO", 2), ("UPRO", 3), ("SPXL", 3), ("SH", -1), ("SDS", -2),
            ("SPXU", -3), ("SPXS", -3)],
    "QQQ": [("QLD", 2), ("TQQQ", 3), ("PSQ", -1), ("QID", -2), ("SQQQ", -3)],
    "IWM": [("UWM", 2), ("TNA", 3), ("RWM", -1), ("TWM", -2), ("TZA", -3)],
    "TLT": [("UBT", 2), ("TMF", 3), ("TBT", -2), ("TMV", -3), ("TBF", -1)],
    "SOXX": [("SOXL", 3), ("SOXS", -3), ("USD", 2), ("SSG", -2)],
    "XBI": [("LABU", 3), ("LABD", -3)],
    "GDX": [("NUGT", 2), ("DUST", -2), ("JNUG", 2), ("JDST", -2)],
    "XLF": [("FAS", 3), ("FAZ", -3)],
    "XLE": [("ERX", 2), ("ERY", -2), ("GUSH", 2), ("DRIP", -2)],
    "FXI": [("YINN", 3), ("YANG", -3)],
    "EEM": [("EDC", 3), ("EDZ", -3)],
    "IYR": [("DRN", 3), ("DRV", -3)],
    "KRE": [("DPST", 3), ("WDRW", -3)],
    "USO": [("UCO", 2), ("SCO", -2)],
    "UNG": [("BOIL", 2), ("KOLD", -2)],
}

SIBLING_GROUPS = {
    "sp500": ["SPY", "IVV", "VOO", "SPLG"],
    "nasdaq100": ["QQQ", "QQQM"],
    "r2000": ["IWM", "VTWO"],
    "midcap": ["IJH", "MDY", "IVOO"],
    "totalus": ["VTI", "ITOT", "SCHB"],
    "emerging": ["EEM", "IEMG", "VWO", "SPEM"],
    "eafe": ["EFA", "IEFA", "VEA", "SPDW"],
    "agg": ["AGG", "BND", "SPAB"],
    "hy": ["HYG", "JNK", "USHY", "SPHY"],
    "ig": ["LQD", "VCIT", "IGIB", "SPIB"],
}

BOND_ETFS = ["LQD", "HYG", "JNK", "AGG", "BND", "TLT", "IEF", "SHY", "TIP",
             "EMB", "MUB", "VCIT", "VGLT", "VGSH", "BKLN", "SRLN", "PFF",
             "VCSH", "IGSB", "SJNK", "SHYG", "USHY", "ANGL", "EMLC", "IGIB",
             "HYD", "PCY", "VWOB", "FLOT", "STIP", "SCHP", "GOVT", "BIV",
             "BLV", "MBB", "CMBS", "SPAB", "SPIB", "SPHY", "BSV", "IEI",
             "TLH", "SHV"]

INTL_ETFS = ["EEM", "IEMG", "VWO", "EFA", "IEFA", "VEA", "EWJ", "EWZ", "FXI",
             "EWY", "EWT", "EWG", "EWU", "EWA", "EWC", "EWH", "EWS", "EWW",
             "EPP", "VGK", "ILF", "EPI", "INDA", "ASHR", "EZU", "SCZ", "MCHI",
             "EWL", "EWP", "EWI", "EWN", "EWD", "EIS", "TUR", "EZA", "THD",
             "SPEM", "SPDW", "IXUS", "ACWX", "VEU", "VSS", "DXJ", "HEDJ"]


# --------------------------------------------------------------------------
# loading
# --------------------------------------------------------------------------
def _load(name):
    with gzip.open(CACHE / f"{name}.json.gz", "rt") as fh:
        return json.load(fh)


class Panel:
    """Aligned date x symbol float matrices."""

    def __init__(self, dates, syms, mats):
        self.dates = dates
        self.syms = syms
        self.idx = {s: i for i, s in enumerate(syms)}
        for k, v in mats.items():
            setattr(self, k, v)

    def col(self, sym):
        j = self.idx.get(sym)
        return None if j is None else j

    def sub(self, names):
        return [self.idx[s] for s in names if s in self.idx]


def build_daily_panel():
    raw = _load("daily_raw")
    adj = _load("daily_all")
    auc = _load("auctions")
    syms = sorted(raw)
    dates = sorted({d for s in syms for d in raw[s]})
    di = {d: i for i, d in enumerate(dates)}
    T, K = len(dates), len(syms)
    shape = (T, K)
    C = np.full(shape, np.nan, np.float64)      # raw close
    O = np.full(shape, np.nan, np.float64)      # raw open
    V = np.full(shape, np.nan, np.float64)      # share volume
    AC = np.full(shape, np.nan, np.float64)     # adjusted close
    AUO = np.full(shape, np.nan, np.float64)    # opening auction print
    AUC_ = np.full(shape, np.nan, np.float64)   # closing auction print
    for j, s in enumerate(syms):
        for d, r in raw[s].items():
            i = di[d]
            O[i, j], C[i, j], V[i, j] = r[0], r[3], r[4]
        for d, r in adj[s].items():
            AC[di[d], j] = r[3]
        for d, r in (auc.get(s) or {}).items():
            i = di.get(d)
            if i is None:
                continue
            if "o" in r:
                AUO[i, j] = r["o"][0]
            if "c" in r:
                AUC_[i, j] = r["c"][0]
    DV = C * V
    return Panel(dates, syms, dict(O=O, C=C, V=V, AC=AC, AUO=AUO, AUC=AUC_, DV=DV))


def build_intraday_panel():
    """Per-day intraday features for the rv_cache 137, plus t3 auction prints."""
    files = sorted(p for p in RVC.glob("*.npz") if p.stem.isupper() and "_" not in p.stem)
    syms, per = [], {}
    for p in files:
        z = np.load(p)
        t, c, v = z["t"].astype(np.int64), z["c"].astype(np.float64), z["v"].astype(np.float64)
        # ET minute of day from the epoch second; RTH bars only, DST handled by
        # bucketing on the calendar day in US/Eastern via a fixed -4/-5 offset table.
        day = ((t - 4 * 3600) // 86400)     # UTC-4; a -5 day would shift 09:30 to 08:30
        # bar index within its trading day
        order = np.argsort(t, kind="stable")
        t, c, v, day = t[order], c[order], v[order], day[order]
        bounds = np.flatnonzero(np.diff(day)) + 1
        starts = np.concatenate(([0], bounds))
        ends = np.concatenate((bounds, [len(t)]))
        rows = {}
        for a, b in zip(starts, ends):
            n = b - a
            if n < 60:
                continue
            sec = t[a:b]
            m0 = sec[0]
            mins = (sec - m0) // 60
            # bars are 5-minute; 09:30 open bar has mins 0, 15:30 has mins 360
            i1530 = np.searchsorted(mins, 360, "left")
            i1555 = n - 1
            if i1530 >= n:
                continue
            import datetime as _dt
            d = _dt.datetime.utcfromtimestamp(int(m0) - 4 * 3600).date().isoformat()
            rows[d] = (float(c[a]), float(c[a + i1530]), float(c[a + i1555]),
                       float(np.dot(c[a:b], v[a:b])), float(v[a:b].sum()))
        if rows:
            syms.append(p.stem)
            per[p.stem] = rows
    dates = sorted({d for s in syms for d in per[s]})
    di = {d: i for i, d in enumerate(dates)}
    T, K = len(dates), len(syms)
    C0 = np.full((T, K), np.nan)     # 09:30-09:35 close (first bar close)
    C1530 = np.full((T, K), np.nan)
    C1555 = np.full((T, K), np.nan)
    DV = np.full((T, K), np.nan)
    for j, s in enumerate(syms):
        for d, r in per[s].items():
            i = di[d]
            C0[i, j], C1530[i, j], C1555[i, j], DV[i, j] = r[0], r[1], r[2], r[3]
    # auction prints from the t3 pool
    with gzip.open(T3C / "auctions.json.gz", "rt") as fh:
        au = json.load(fh)
    AUO = np.full((T, K), np.nan)
    AUC_ = np.full((T, K), np.nan)
    sidx = {s: j for j, s in enumerate(syms)}
    for k, rec in au.items():
        s, d = k.split("|", 1)
        j = sidx.get(s)
        i = di.get(d)
        if j is None or i is None:
            continue
        if "o" in rec:
            AUO[i, j] = rec["o"]
        if "c" in rec:
            AUC_[i, j] = rec["c"]
    return Panel(dates, syms, dict(C0=C0, C1530=C1530, C1555=C1555, DV=DV,
                                   AUO=AUO, AUC=AUC_))


# --------------------------------------------------------------------------
# cost model
# --------------------------------------------------------------------------
def half_spread_bp(DV):
    """Per-symbol half-spread in bp from median dollar volume, M0-style tiers.

    >= $500M/day -> 1.0   $100-500M -> 1.5   $20-100M -> 3.0
    $5-20M -> 6.0         < $5M     -> 15.0
    """
    med = np.nanmedian(DV, axis=0)
    hs = np.full(med.shape, 15.0)
    hs[med >= 5e6] = 6.0
    hs[med >= 2e7] = 3.0
    hs[med >= 1e8] = 1.5
    hs[med >= 5e8] = 1.0
    hs[~np.isfinite(med)] = 15.0
    return hs


# --------------------------------------------------------------------------
# generic helpers
# --------------------------------------------------------------------------
def zscore_ts(X, win, minp=None):
    """Trailing z-score using data through t (inclusive), causal."""
    minp = minp or max(20, win // 4)
    T, K = X.shape
    out = np.full_like(X, np.nan)
    M = np.where(np.isfinite(X), X, 0.0)
    G = np.isfinite(X).astype(float)
    cs = np.cumsum(np.vstack([np.zeros((1, K)), M]), axis=0)
    cs2 = np.cumsum(np.vstack([np.zeros((1, K)), M * M]), axis=0)
    cg = np.cumsum(np.vstack([np.zeros((1, K)), G]), axis=0)
    for t in range(T):
        a = max(0, t + 1 - win)
        n = cg[t + 1] - cg[a]
        s = cs[t + 1] - cs[a]
        s2 = cs2[t + 1] - cs2[a]
        with np.errstate(invalid="ignore", divide="ignore"):
            mu = s / n
            var = s2 / n - mu * mu
            sd = np.sqrt(np.maximum(var, 0.0))
            z = (X[t] - mu) / np.where(sd > 0, sd, np.nan)
        z[n < minp] = np.nan
        out[t] = z
    return out


def xs_demean(S):
    ok = np.isfinite(S)
    n = ok.sum(axis=1, keepdims=True)
    mu = np.nansum(np.where(ok, S, 0.0), axis=1, keepdims=True) / np.maximum(n, 1)
    out = np.where(ok, S - mu, np.nan)
    out[(n < 4).ravel()] = np.nan
    return out


def xs_rank_weights(S, min_names=6):
    """Dollar-neutral, gross-1 weights from the cross-sectional rank of S."""
    T, K = S.shape
    W = np.zeros((T, K))
    for t in range(T):
        row = S[t]
        ok = np.isfinite(row)
        n = int(ok.sum())
        if n < min_names:
            continue
        v = row[ok]
        r = np.argsort(np.argsort(v)).astype(float)
        r = (r - r.mean())
        if np.abs(r).sum() == 0:
            continue
        r = r / np.abs(r).sum()
        W[t, ok] = r
    return W


def overlap(W, h):
    """Average the last h target books -> daily positions with 1/h turnover."""
    if h <= 1:
        return W
    T, K = W.shape
    acc = np.zeros((T, K))
    for k in range(h):
        acc[k:] += W[:T - k]
    return acc / h


def book_pnl(W, R, hs_bp, borrow=True, periods=252, roundtrip=False):
    """W is the target book known at the close of t; R[t] is the return earned
    from that close forward over the holding step recorded in R.

    roundtrip=True means the book is fully liquidated at the end of every step
    (overnight close->open books, intraday 15:30->close books): turnover is
    2x gross every day, never the day-to-day change in the target."""
    T, K = W.shape
    Wl = np.vstack([np.zeros((1, K)), W[:-1]])
    turn = 2.0 * np.abs(W) if roundtrip else np.abs(W - Wl)
    cost = turn @ (hs_bp / 1e4)
    gross = np.nansum(np.where(np.isfinite(R), W * R, 0.0), axis=1)
    # a position on a name with no return that day is not held
    live = np.nansum(np.abs(np.where(np.isfinite(R), W, 0.0)), axis=1)
    net = gross - cost
    if borrow:
        shortn = np.nansum(np.clip(-W, 0, None), axis=1)
        net = net - shortn * (BORROW_BP_YR / 1e4) / periods
    return net, gross, turn.sum(axis=1), live


def sharpe(x, periods=252):
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    if len(x) < 30 or x.std(ddof=1) == 0:
        return float("nan")
    return float(x.mean() / x.std(ddof=1) * math.sqrt(periods))


def fwd_ret(P, kind, h=1):
    """Forward return matrices aligned so R[t] is earned after the close of t."""
    C = P.AUC if hasattr(P, "AUC") else None
    if kind == "on":                       # closing auction t -> opening auction t+1
        num = np.vstack([P.AUO[1:], np.full((1, P.AUO.shape[1]), np.nan)])
        return num / C - 1.0
    if kind == "cc":                       # closing auction t -> closing auction t+h
        num = np.vstack([C[h:], np.full((h, C.shape[1]), np.nan)])
        return num / C - 1.0
    raise ValueError(kind)


# --------------------------------------------------------------------------
# null bar: joint block sign-flip on the family PnL matrix
# --------------------------------------------------------------------------
def joint_null_max(pnl_mat, block=21, reps=2000, periods=252, seed=7):
    rng = np.random.default_rng(seed)
    T, N = pnl_mat.shape
    X = np.where(np.isfinite(pnl_mat), pnl_mat, 0.0)
    ok = np.isfinite(pnl_mat)
    nb = int(np.ceil(T / block))
    sd = np.array([np.nanstd(pnl_mat[:, j], ddof=1) for j in range(N)])
    cnt = ok.sum(axis=0)
    maxes = np.empty(reps)
    for r in range(reps):
        s = rng.choice([-1.0, 1.0], size=nb)
        sig = np.repeat(s, block)[:T][:, None]
        m = (X * sig).sum(axis=0) / np.maximum(cnt, 1)
        with np.errstate(invalid="ignore", divide="ignore"):
            sr = m / sd * math.sqrt(periods)
        maxes[r] = np.nanmax(np.abs(sr))
    return dict(mean=float(maxes.mean()), p50=float(np.percentile(maxes, 50)),
                p95=float(np.percentile(maxes, 95)), p99=float(np.percentile(maxes, 99)))


# ==========================================================================
# FORMULAS
# ==========================================================================
def month_flags(dates):
    """last2 = last two sessions of a month; qend5 = last five of a quarter;
    first3 = first three sessions of a month."""
    n = len(dates)
    mon = [d[:7] for d in dates]
    last2 = np.zeros(n, bool); first3 = np.zeros(n, bool); qend5 = np.zeros(n, bool)
    starts = [0] + [i for i in range(1, n) if mon[i] != mon[i - 1]] + [n]
    for a, b in zip(starts[:-1], starts[1:]):
        last2[max(a, b - 2):b] = True
        first3[a:min(b, a + 3)] = True
        if dates[b - 1][5:7] in ("03", "06", "09", "12"):
            qend5[max(a, b - 5):b] = True
    return last2, first3, qend5


def letf_features(P):
    """Per-family flow proxies from raw dollar volume. Returns dict of matrices
    indexed by the family list order."""
    fams = [f for f in LETF_FAMILIES if f in P.idx]
    T = len(P.dates)
    Iflow = np.full((T, len(fams)), np.nan)
    Asym = np.full((T, len(fams)), np.nan)
    Turn = np.full((T, len(fams)), np.nan)
    Rday = np.full((T, len(fams)), np.nan)     # underlying open->close-auction
    for fi, f in enumerate(fams):
        u = P.idx[f]
        du = P.DV[:, u]
        num = np.zeros(T); pos = np.zeros(T); neg = np.zeros(T); tot = np.zeros(T)
        for s, L in LETF_FAMILIES[f]:
            j = P.idx.get(s)
            if j is None:
                continue
            dv = np.where(np.isfinite(P.DV[:, j]), P.DV[:, j], 0.0)
            num += abs(L * (L - 1)) * dv
            tot += dv
            (pos if L > 0 else neg).__iadd__(dv)
        with np.errstate(invalid="ignore", divide="ignore"):
            Iflow[:, fi] = num / du
            Asym[:, fi] = (pos - neg) / np.where(tot > 0, tot, np.nan)
            Turn[:, fi] = tot / du
            Rday[:, fi] = P.AUC[:, u] / P.O[:, u] - 1.0
    return fams, Iflow, Asym, Turn, Rday


def rolling_resid(R, H, win=120, minp=60):
    """Causal rolling OLS residual of each column of R on the hedge columns H
    (intercept included), betas estimated on [t-win, t-1]."""
    T, K = R.shape
    m = H.shape[1]
    X = np.column_stack([np.ones(T), H])
    res = np.full((T, K), np.nan)
    okX = np.isfinite(X).all(axis=1)
    for k in range(K):
        y = R[:, k]
        oky = okX & np.isfinite(y)
        idx = np.flatnonzero(oky)
        if len(idx) < minp + 5:
            continue
        # incremental normal equations over a trailing window of valid rows
        for t in range(T):
            if not oky[t]:
                continue
            lo = np.searchsorted(idx, max(0, t - win))
            hi = np.searchsorted(idx, t)          # strictly before t
            if hi - lo < minp:
                continue
            sl = idx[lo:hi]
            Xi, yi = X[sl], y[sl]
            try:
                b = np.linalg.lstsq(Xi, yi, rcond=None)[0]
            except np.linalg.LinAlgError:
                continue
            res[t, k] = y[t] - X[t] @ b
    return res


def cum(X, k):
    T, K = X.shape
    out = np.zeros((T, K)); cntb = np.zeros((T, K))
    M = np.where(np.isfinite(X), X, 0.0); G = np.isfinite(X).astype(float)
    for i in range(k):
        out[i:] += M[:T - i]; cntb[i:] += G[:T - i]
    out[cntb < k] = np.nan
    return out


# ==========================================================================
def trailing_median_ratio(A, B, win=21, minp=8):
    """Median of A/B over the trailing `win` rows (inclusive of t).

    Used to put a RAW auction print into the same adjusted price units as a
    back-adjusted intraday bar cache; on a split day the ratio steps and the
    trailing median follows within `win` sessions, so split days themselves are
    dropped by the winsoriser rather than trusted.
    """
    with np.errstate(invalid="ignore", divide="ignore"):
        R = A / B
    T, K = R.shape
    out = np.full((T, K), np.nan)
    for t in range(T):
        lo = max(0, t + 1 - win)
        w = R[lo:t + 1]
        n = np.isfinite(w).sum(axis=0)
        with np.errstate(invalid="ignore"):
            m = np.nanmedian(w, axis=0)
        m[n < minp] = np.nan
        out[t] = m
    return out


def winsor(R, lim):
    R = np.where(np.isfinite(R) & (np.abs(R) <= lim), R, np.nan)
    return R


def run_all(window):
    """window in {'design','holdout'}.  Returns list of result dicts."""
    D = build_daily_panel()
    I = build_intraday_panel()
    dd = np.array(D.dates)
    ii = np.array(I.dates)
    mD = (dd <= DESIGN_END_D) if window == "design" else (dd >= HOLD_START_D)
    mI = (ii <= DESIGN_END_I) if window == "design" else (ii >= HOLD_START_I)
    hsD = half_spread_bp(D.DV)
    hsI = half_spread_bp(I.DV)
    res = []
    pnls = {}

    def record(name, desc, pnl, turn, hold, panel, gross=None, cost=None):
        s = sharpe(pnl)
        n = int(np.isfinite(pnl).sum())
        yrs = n / 252.0
        g = sharpe(gross) if gross is not None else float("nan")
        mg = float(np.nanmean(gross)) * 1e4 if gross is not None else float("nan")
        mc = float(np.nanmean(cost)) * 1e4 if cost is not None else float("nan")
        tp = float(np.nanmean(turn))
        res.append(dict(name=name, desc=desc, sharpe=round(float(s), 4),
                        gross_sharpe=round(float(g), 4),
                        mean_bp_per_day=round(float(np.nanmean(pnl)) * 1e4, 3),
                        gross_bp_per_day=round(mg, 3), cost_bp_per_day=round(mc, 3),
                        breakeven_hs_bp=(round(mg / tp, 3) if tp > 1e-9 else None),
                        n_days=n, years=round(yrs, 2),
                        turnover_per_day=round(tp, 4), hold=hold, panel=panel))
        pnls[name] = pnl

    def bk(W, R, hs, mask, roundtrip, borrow=True):
        Wm = W.copy()
        Wm[~mask] = 0.0
        net, gross, turn, live = book_pnl(Wm, R, hs, borrow=borrow, roundtrip=roundtrip)
        cost = gross - net
        return net[mask], gross[mask], cost[mask], turn[mask]

    # ---- price units -----------------------------------------------------
    # Alpaca daily bars were pulled BOTH raw and split/dividend adjusted; the
    # auction feed is raw prints.  f = adjusted_close / raw_close is the factor
    # that puts a raw print into adjusted units, so every auction-to-auction
    # return below is a genuine total return across splits and ex-dates.
    with np.errstate(invalid="ignore", divide="ignore"):
        f = D.AC / D.C
    AUCd = D.AUC * f
    AUOd = D.AUO * f
    Od = D.O * f

    def on_ret(AUCx, AUOx, lim=0.15):
        nxt = np.vstack([AUOx[1:], np.full((1, AUOx.shape[1]), np.nan)])
        return winsor(nxt / AUCx - 1.0, lim)

    def cc_ret(AUCx, h=1, lim=0.30):
        nxt = np.vstack([AUCx[h:], np.full((h, AUCx.shape[1]), np.nan)])
        return winsor(nxt / AUCx - 1.0, lim)

    ON_D = on_ret(AUCd, AUOd)
    CC1_D = cc_ret(AUCd, 1)

    # ---------------- Family A : leveraged-ETF rebalance flow --------------
    fams, Iflow, Asym, Turn, _ = letf_features(D)
    fcols = [D.idx[f_] for f_ in fams]
    hsF = hsD[fcols]
    Rday = winsor(AUCd[:, fcols] / Od[:, fcols] - 1.0, 0.30)

    # intraday arm on the four underlyings rv_cache carries
    iu = [x for x in ("SPY", "QQQ", "IWM", "TLT") if x in I.idx]
    ci = [I.idx[x] for x in iu]
    scaleC = trailing_median_ratio(I.AUC, I.C1555)
    scaleO = trailing_median_ratio(I.AUO, I.C0)
    AUCi = I.AUC / scaleC          # auction close in the 5-min cache's price units
    AUOi = I.AUO / scaleO
    r_to1530 = winsor(I.C1530 / I.C0 - 1.0, 0.30)[:, ci]
    r_push = winsor(AUCi[:, ci] / I.C1530[:, ci] - 1.0, 0.10)
    hsI4 = hsI[ci]

    absmu = np.full_like(r_to1530, np.nan)
    for k in range(r_to1530.shape[1]):
        a = np.abs(r_to1530[:, k])
        g = np.isfinite(a)
        cs = np.concatenate(([0.0], np.cumsum(np.where(g, a, 0.0))))
        cn = np.concatenate(([0.0], np.cumsum(g.astype(float))))
        for t in range(len(a)):
            lo = max(0, t - 60)
            nn = cn[t] - cn[lo]
            absmu[t, k] = (cs[t] - cs[lo]) / nn if nn >= 30 else np.nan

    def ts_book(sig):
        W = np.where(np.isfinite(sig), np.sign(sig), 0.0)
        ssum = np.abs(W).sum(axis=1, keepdims=True)
        return np.divide(W, np.where(ssum > 0, ssum, 1.0))

    n, g, c, t_ = bk(ts_book(r_to1530), r_push, hsI4, mI, True, borrow=False)
    record("A1_LETF_PUSH_TS", "sign(underlying 09:30->15:30) held 15:30 -> closing "
           "auction on SPY/QQQ/IWM/TLT; the levered-ETF rebalance trade is same-signed "
           "as the day's move, so it should push the last 30 minutes",
           n, t_, "1530->close", "RV4", g, c)

    big = np.abs(r_to1530) > 1.5 * absmu
    n, g, c, t_ = bk(ts_book(np.where(big, r_to1530, np.nan)), r_push, hsI4, mI, True, False)
    record("A2_LETF_PUSH_BIG", "A1 only when |09:30->15:30| exceeds 1.5x its trailing-60d "
           "mean absolute move -- rebalance dollars are linear in the move",
           n, t_, "1530->close", "RV4", g, c)

    idx_d = {d: k for k, d in enumerate(D.dates)}
    Ifi = np.full((len(I.dates), len(iu)), np.nan)
    for k, sname in enumerate(iu):
        if sname in fams:
            fi = fams.index(sname)
            for t, d in enumerate(I.dates):
                kd = idx_d.get(d)
                if kd is not None:
                    Ifi[t, k] = Iflow[kd, fi]
    Ifz = zscore_ts(Ifi, 250)
    n, g, c, t_ = bk(ts_book(np.where(Ifz > 0.5, r_to1530, np.nan)), r_push, hsI4, mI, True, False)
    record("A3_LETF_PUSH_HIINT", "A1 only when the family's rebalance-intensity proxy "
           "sum|L(L-1)|*LETF$vol / underlying$vol is >0.5sd above its own 250d mean",
           n, t_, "1530->close", "RV4", g, c)

    n, g, c, t_ = bk(ts_book(-Rday), ON_D[:, fcols], hsF, mD, True, False)
    record("A4_LETF_ON_GIVEBACK", "equal-weight short the day's open->close move across "
           "the 15 levered-ETF families, closing auction -> next opening auction",
           n, t_, "overnight", "ALP15", g, c)

    Ifz_d = zscore_ts(Iflow, 250)
    W = xs_rank_weights(-(Rday * Ifz_d), min_names=6)
    n, g, c, t_ = bk(W, ON_D[:, fcols], hsF, mD, True)
    record("A5_LETF_ON_XS", "cross-section of the 15 families: short (day move x "
           "rebalance-intensity z), dollar-neutral, closing -> opening auction",
           n, t_, "overnight", "ALP15", g, c)

    Az = zscore_ts(Asym, 60)
    W = xs_rank_weights(-Az, min_names=6)
    n, g, c, t_ = bk(W, CC1_D[:, fcols], hsF, mD, False)
    record("A6_LETF_ASYM_XS", "fade retail levered positioning: short the families whose "
           "long-levered share of family $volume is high vs their own 60d norm, 1d hold",
           n, t_, "1d", "ALP15", g, c)

    n, g, c, t_ = bk(W, ON_D[:, fcols], hsF, mD, True)
    record("A7_LETF_ASYM_ON", "A6 held only over the overnight auction-to-auction gap",
           n, t_, "overnight", "ALP15", g, c)

    Tz = zscore_ts(Turn, 60)
    r5 = np.full_like(Rday, np.nan)
    r5[5:] = AUCd[:, fcols][5:] / AUCd[:, fcols][:-5] - 1.0
    W = overlap(xs_rank_weights(-(Tz * np.sign(r5)), min_names=6), 5)
    n, g, c, t_ = bk(W, CC1_D[:, fcols], hsF, mD, False)
    record("A8_LETF_TURN_XS", "fade levered-flow chasing: short (family LETF turnover z x "
           "sign of its 5d move), 5d overlapping hold", n, t_, "5d", "ALP15", g, c)

    # ---------------- Family B : non-CEF premium/discount ------------------
    RET = np.full_like(D.AC, np.nan)
    RET[1:] = D.AC[1:] / D.AC[:-1] - 1.0
    RET = winsor(RET, 0.30)

    def hedge(names):
        cols = [D.idx[x] for x in names if x in D.idx]
        return RET[:, cols]

    bcols = [D.idx[x] for x in BOND_ETFS if x in D.idx]
    icols = [D.idx[x] for x in INTL_ETFS if x in D.idx]
    resB = rolling_resid(RET[:, bcols], hedge(["IEF", "SPY"]))
    resI = rolling_resid(RET[:, icols], hedge(["SPY", "UUP"]))
    hsB, hsIn = hsD[bcols], hsD[icols]

    zB = zscore_ts(cum(resB, 5), 120)
    W = overlap(xs_rank_weights(-zB), 3)
    n, g, c, t_ = bk(W, CC1_D[:, bcols], hsB, mD, False)
    record("B1_BOND_PREM_FADE", "43 bond ETFs: fade the 5d cumulative residual after "
           "hedging IEF+SPY -- the stale-NAV premium/discount -- 3d overlapping hold",
           n, t_, "3d", "BOND", g, c)

    disp = np.nanstd(zB, axis=1)
    thr = np.full(len(disp), np.nan)
    for t in range(len(disp)):
        w = disp[max(0, t - 250):t]
        w = w[np.isfinite(w)]
        if len(w) >= 60:
            thr[t] = np.percentile(w, 66)
    stress = disp > thr
    W = overlap(xs_rank_weights(-np.where(stress[:, None], zB, np.nan)), 3)
    n, g, c, t_ = bk(W, CC1_D[:, bcols], hsB, mD, False)
    record("B2_BOND_PREM_STRESS", "B1 only on days when the cross-sectional dispersion of "
           "bond-ETF premia is above its own trailing 66th percentile",
           n, t_, "3d", "BOND", g, c)

    zI = zscore_ts(cum(resI, 5), 120)
    W = overlap(xs_rank_weights(-zI), 3)
    n, g, c, t_ = bk(W, CC1_D[:, icols], hsIn, mD, False)
    record("B3_INTL_PREM_FADE", "44 international/EM ETFs: fade the 5d cumulative residual "
           "after hedging SPY+UUP (closed-home-market NAV staleness), 3d hold",
           n, t_, "3d", "INTL", g, c)

    z1 = zscore_ts(resI, 120)
    W = xs_rank_weights(-z1)
    n, g, c, t_ = bk(W, ON_D[:, icols], hsIn, mD, True)
    record("B4_INTL_PREM_ON", "the same international residual, 1-day, held only closing "
           "auction -> next opening auction, the window in which the home market reprices",
           n, t_, "overnight", "INTL", g, c)

    colsAll = bcols + icols
    zAll = np.concatenate([zB, zI], axis=1)
    hsAll = np.concatenate([hsB, hsIn])
    W = overlap(xs_rank_weights(np.where(np.abs(zAll) > 2.0, -zAll, np.nan), min_names=4), 2)
    n, g, c, t_ = bk(W, CC1_D[:, colsAll], hsAll, mD, False)
    record("B5_PREM_EXTREME_2D", "bond+international pooled, only the names whose premium z "
           "exceeds |2|, 2d overlapping hold", n, t_, "2d", "BOND+INTL", g, c)

    # sibling groups: group-neutral books
    r5all = np.full_like(D.AC, np.nan)
    r5all[5:] = D.AC[5:] / D.AC[:-5] - 1.0
    r5all = winsor(r5all, 0.5)
    Ssib = np.full_like(RET, np.nan)
    groups = []
    for gname, names in SIBLING_GROUPS.items():
        cols = [D.idx[x] for x in names if x in D.idx]
        if len(cols) < 2:
            continue
        groups.append(cols)
        sub = r5all[:, cols]
        Ssib[:, cols] = sub - np.nanmean(sub, axis=1, keepdims=True)
    sib_cols = sorted({c_ for gg in groups for c_ in gg})
    pos = {c_: k for k, c_ in enumerate(sib_cols)}

    def group_book(S_full, gate=None):
        """Equal risk per group, dollar-neutral inside each group."""
        T = S_full.shape[0]
        W = np.zeros((T, len(sib_cols)))
        for gg in groups:
            sub = S_full[:, gg].copy()
            if gate is not None:
                sub = np.where(gate[:, [pos[c_] for c_ in gg]], sub, np.nan)
            w = xs_rank_weights(sub, min_names=2)
            for k, c_ in enumerate(gg):
                W[:, pos[c_]] += w[:, k]
        tot = np.abs(W).sum(axis=1, keepdims=True)
        return np.divide(W, np.where(tot > 0, tot, 1.0))

    zS = zscore_ts(Ssib[:, sib_cols], 120)
    zSf = np.full_like(RET, np.nan)
    zSf[:, sib_cols] = zS
    W = overlap(group_book(-zSf), 3)
    n, g, c, t_ = bk(W, CC1_D[:, sib_cols], hsD[sib_cols], mD, False)
    record("B6_SIB_PREM_FADE", "inside 10 same-exposure wrapper groups, fade each wrapper's "
           "5d return gap to its own group mean, group-neutral, 3d hold",
           n, t_, "3d", "SIB", g, c)

    # ---------------- Family C : closing-auction dislocation ---------------
    disl = winsor(AUCi / I.C1555 - 1.0, 0.05)
    r30 = winsor(I.C1555 / I.C1530 - 1.0, 0.15)
    ON_I = on_ret(AUCi, AUOi)
    CC_I = cc_ret(AUCi, 1)
    zd = zscore_ts(disl, 60)
    W = xs_rank_weights(-zd, min_names=20)
    n, g, c, t_ = bk(W, ON_I, hsI, mI, True)
    record("C1_AUCT_DISLOC_ON", "cross-section of 137 names: fade the closing-auction print's "
           "own dislocation from the 15:55 price, held to the next opening print",
           n, t_, "overnight", "RV137", g, c)

    resid = np.full_like(disl, np.nan)
    for t in range(disl.shape[0]):
        y, x = disl[t], r30[t]
        ok = np.isfinite(y) & np.isfinite(x)
        if ok.sum() < 20:
            continue
        X = np.column_stack([np.ones(int(ok.sum())), x[ok]])
        b = np.linalg.lstsq(X, y[ok], rcond=None)[0]
        resid[t, ok] = y[ok] - X @ b
    zr = zscore_ts(resid, 60)
    W = xs_rank_weights(-zr, min_names=20)
    n, g, c, t_ = bk(W, ON_I, hsI, mI, True)
    record("C2_AUCT_RESID_ON", "C1 after removing, cross-sectionally each day, the part of "
           "the dislocation explained by the last-30-minute return (T3's own feature)",
           n, t_, "overnight", "RV137", g, c)

    l2I, f3I, q5I = month_flags(I.dates)
    W = xs_rank_weights(np.where((l2I | f3I)[:, None], -zr, np.nan), min_names=20)
    n, g, c, t_ = bk(W, ON_I, hsI, mI, True)
    record("C3_AUCT_RESID_MEND", "C2 restricted to the last two and first three sessions of "
           "each month, when index-rebalance MOC imbalances are largest",
           n, t_, "overnight", "RV137", g, c)

    W = xs_rank_weights(-zr, min_names=20)
    n, g, c, t_ = bk(W, CC_I, hsI, mI, False)
    record("C4_AUCT_RESID_D1", "C2 held a full session (closing auction -> next closing "
           "auction) rather than only overnight", n, t_, "1d", "RV137", g, c)

    # ---------------- Family D : distribution / reinvestment flows ---------
    RAWR = np.full_like(D.C, np.nan)
    RAWR[1:] = D.C[1:] / D.C[:-1] - 1.0
    divy = np.clip(winsor(RET - RAWR, 0.10), 0.0, None)
    ann = cum(divy, 252)
    l2D, f3D, q5D = month_flags(D.dates)
    W = overlap(xs_rank_weights(np.where(f3D[:, None], ann[:, bcols], np.nan)), 3)
    n, g, c, t_ = bk(W, CC1_D[:, bcols], hsB, mD, False)
    record("D1_BONDETF_EXWEEK", "monthly-paying bond ETFs nearly all go ex on the first "
           "business day: long the high trailing-12m-yield third against the low third "
           "over the first three sessions of each month (coupon reinvestment demand)",
           n, t_, "3d", "BOND", g, c)

    W = overlap(xs_rank_weights(np.where(f3D[:, None], ann, np.nan)), 3)
    n, g, c, t_ = bk(W, CC1_D, hsD, mD, False)
    record("D2_HIYIELD_EXWEEK", "the same first-three-sessions reinvestment bid but across "
           "the whole 185-ETF universe, sorted on trailing 12m distribution yield",
           n, t_, "3d", "ALL185", g, c)

    # ---------------- Family E : creation/redemption pressure proxy --------
    logdv = np.log(np.where(D.DV > 0, D.DV, np.nan))
    Vrel = np.full_like(logdv, np.nan)
    for gg in groups:
        sub = logdv[:, gg]
        Vrel[:, gg] = sub - np.nanmean(sub, axis=1, keepdims=True)
    zV = zscore_ts(Vrel[:, sib_cols], 60)
    zVf = np.full_like(logdv, np.nan)
    zVf[:, sib_cols] = zV
    W = group_book(-zVf)
    n, g, c, t_ = bk(W, CC1_D[:, sib_cols], hsD[sib_cols], mD, False)
    record("E1_CR_VOLZ_XS", "inside a wrapper group, fade the wrapper whose own dollar "
           "volume is anomalously high against its siblings -- a primary-market "
           "creation/redemption pressure proxy -- 1d hold", n, t_, "1d", "SIB", g, c)

    W = overlap(group_book(-zSf, gate=(zV > 0.5)), 3)
    n, g, c, t_ = bk(W, CC1_D[:, sib_cols], hsD[sib_cols], mD, False)
    record("E2_CR_GATED_RV", "B6's wrapper-gap fade but only on wrappers currently carrying "
           "an anomalous own-volume z (flow-gated sibling relative value)",
           n, t_, "3d", "SIB", g, c)

    # ---------------- Family F : month/quarter-end mechanical flow ---------
    W = xs_rank_weights(np.where((l2D | f3D)[:, None], -(Rday * Ifz_d), np.nan), min_names=6)
    n, g, c, t_ = bk(W, ON_D[:, fcols], hsF, mD, True)
    record("F1_MEND_LETF_ON", "A5 restricted to the last two and first three sessions of "
           "each month", n, t_, "overnight", "ALP15", g, c)

    W = overlap(group_book(np.where(l2D[:, None], -zSf, np.nan)), 3)
    n, g, c, t_ = bk(W, CC1_D[:, sib_cols], hsD[sib_cols], mD, False)
    record("F2_MEND_SIB_RV", "B6 restricted to the last two sessions of the month, when "
           "index-fund creation flow spikes", n, t_, "3d", "SIB", g, c)

    W = overlap(xs_rank_weights(np.where(q5D[:, None], -zB, np.nan)), 3)
    n, g, c, t_ = bk(W, CC1_D[:, bcols], hsB, mD, False)
    record("F3_QEND_BOND_PREM", "B1 restricted to the last five sessions of a quarter "
           "(pension and insurer duration rebalance)", n, t_, "3d", "BOND", g, c)

    return res, pnls, (mD, mI, D, I)


def main():
    window = "holdout" if "--holdout" in sys.argv else "design"
    res, pnls, _ = run_all(window)
    names = [r["name"] for r in res]
    # joint null on the two panels separately (different T), then pooled analytic
    Tmax = max(len(v) for v in pnls.values())
    M = np.full((Tmax, len(names)), np.nan)
    for j, n in enumerate(names):
        v = pnls[n]
        M[-len(v):, j] = v
    null = joint_null_max(M, block=21, reps=2000)
    N = len(names)
    out = dict(window=window, n_formulas=N,
               analytic_expected_max_SE=round(math.sqrt(2 * math.log(N)), 3),
               analytic_expected_max_SE_sign_agnostic=round(math.sqrt(2 * math.log(2 * N)), 3),
               joint_block_signflip_null=null,
               results=sorted(res, key=lambda r: -(r["sharpe"] if r["sharpe"] == r["sharpe"] else -9)))
    path = OUT / f"INVENT_R3_flow_{window}.json"
    path.write_text(json.dumps(out, indent=1))
    print(json.dumps({k: v for k, v in out.items() if k != "results"}, indent=1))
    for r in out["results"]:
        print(f"net {r['sharpe']:>7}  gross {r['gross_sharpe']:>7}  {r['name']:<22} "
              f"{r['hold']:<13} turn/d {r['turnover_per_day']:.3f}  "
              f"g{r['gross_bp_per_day']:+.3f} c{r['cost_bp_per_day']:.3f} bp  "
              f"be={r['breakeven_hs_bp']}  n={r['n_days']}")
    np.save(OUT / f"INVENT_R3_flow_{window}_pnl.npy", M)
    (OUT / f"INVENT_R3_flow_{window}_names.json").write_text(json.dumps(names))


if __name__ == "__main__":
    main()
