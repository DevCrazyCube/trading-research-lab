#!/usr/bin/env python3
"""WIDE calendar / session / structural-flow formula sweep.

Design discipline
-----------------
* Every formula is written a-priori (no constant is fitted on the data).
* Each formula is scored on a DESIGN window only. A later HOLDOUT window exists in the
  same arrays and is never inspected during the sweep -- the reporting code prints
  held-out numbers ONLY for the handful of names passed on the command line at the end.
* The multiple-testing bar is not sqrt(2 ln N) alone. The formulas are heavily
  correlated (they share instruments and overlapping calendars), so the primary bar is an
  EMPIRICAL max-|Sharpe| null: rotate each dataset's return arrays circularly against a
  FIXED calendar, re-run all formulas, take the max |Sharpe| across the whole family, and
  repeat. That preserves autocorrelation, vol clustering and the cross-sectional
  correlation structure while destroying every calendar alignment.
* Costs are charged per side on |dw|, never zero.

Costs (per side, basis points)
------------------------------
  ETF daily close:      1.0 bp   (M0 tier-A measured close half-spread ~1.3bp for the
                                  general liquid tape; SPY/QQQ/TLT sit well inside that,
                                  1.0 is a deliberately non-generous round number)
  US single stocks:     2.5 bp   (M0 tier A/B close half-spread ~1.3bp + impact headroom)
  Binance USD-M perp:   5.0 bp   (4bp VIP0 taker fee + ~1bp spread crossing)
"""

from __future__ import annotations

import csv
import datetime as dt
import gzip
import json
import pathlib
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[2]
CAL = ROOT / "research" / "data" / "calendar_cache"
OUT = ROOT / "research" / "trading_bot"

COST_ETF_BP = 1.0
COST_STOCK_BP = 2.5
COST_PERP_BP = 5.0

# ---- design / holdout splits (fixed before any result was looked at) -------------------
SPLIT_DAILY = "2016-12-31"     # ETF panel: design 1993..2016, holdout 2017..2026
SPLIT_XS = "2021-12-31"        # t9 stock panel starts 2016; design 2016..2021
SPLIT_CRYPTO = "2023-12-31"    # perp hourly starts 2020-07; design 2020-07..2023


# =======================================================================================
# data loading
# =======================================================================================

def load_daily():
    syms, rows_by = [], {}
    for p in sorted(CAL.glob("*.json")):
        d = json.loads(p.read_text())
        s = d["symbol"]
        rows_by[s] = d["rows"]
        syms.append(s)
    # master calendar = SPY sessions (NYSE)
    spy = {r[0]: r for r in rows_by["SPY"]}
    dates = sorted(spy)
    idx = {d: i for i, d in enumerate(dates)}
    n = len(dates)
    A = {}
    for s in syms:
        adj = np.full(n, np.nan)
        op = np.full(n, np.nan)
        cl = np.full(n, np.nan)
        for r in rows_by[s]:
            i = idx.get(r[0])
            if i is None:
                continue
            op[i], cl[i], adj[i] = r[1], r[4], r[6]
        A[s] = (op, cl, adj)
    return dates, syms, A


def daily_returns(A, syms, n):
    """close-to-close total return, plus the intraday / overnight decomposition."""
    c2c = np.zeros((n, len(syms)))
    intr = np.zeros((n, len(syms)))
    ovn = np.zeros((n, len(syms)))
    live = np.zeros((n, len(syms)), dtype=bool)
    for j, s in enumerate(syms):
        op, cl, adj = A[s]
        r = np.zeros(n)
        ok = np.isfinite(adj)
        prev = np.roll(adj, 1)
        with np.errstate(invalid="ignore", divide="ignore"):
            r = adj / prev - 1.0
        good = ok & np.roll(ok, 1)
        good[0] = False
        r = np.where(good, r, 0.0)
        r = np.clip(np.nan_to_num(r), -0.9, 0.9)
        with np.errstate(invalid="ignore", divide="ignore"):
            ir = cl / op - 1.0
        ir = np.where(np.isfinite(ir), ir, 0.0)
        ir = np.clip(ir, -0.9, 0.9)
        onr = (1.0 + r) / (1.0 + ir) - 1.0
        onr = np.where(np.isfinite(onr), onr, 0.0)
        c2c[:, j] = r
        intr[:, j] = ir
        ovn[:, j] = np.clip(onr, -0.9, 0.9)
        live[:, j] = good
    return c2c, intr, ovn, live


def calendar_features(dates):
    D = [dt.date.fromisoformat(x) for x in dates]
    n = len(D)
    dow = np.array([d.weekday() for d in D])            # 0=Mon
    month = np.array([d.month for d in D])
    year = np.array([d.year for d in D])
    day = np.array([d.day for d in D])
    ym = year * 12 + month
    tdom = np.zeros(n, int)      # 1-based trading day of month
    rtdom = np.zeros(n, int)     # 1 = last trading day of month
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
    # holiday gaps
    pre_hol = np.zeros(n, bool)
    post_hol = np.zeros(n, bool)
    for i in range(n - 1):
        gap = (D[i + 1] - D[i]).days
        normal = 3 if dow[i] == 4 else 1
        if gap > normal:
            pre_hol[i] = True
            post_hol[i + 1] = True
    # monthly OPEX = last session on or before the third Friday
    opex = np.zeros(n, bool)
    opex_week = np.zeros(n, bool)
    for m in np.unique(ym):
        sel = np.where(ym == m)[0]
        y, mo = D[sel[0]].year, D[sel[0]].month
        # third Friday
        first = dt.date(y, mo, 1)
        offs = (4 - first.weekday()) % 7
        tf = first + dt.timedelta(days=offs + 14)
        cand = [i for i in sel if D[i] <= tf]
        if not cand:
            continue
        oi = cand[-1]
        opex[oi] = True
        wk_start = tf - dt.timedelta(days=tf.weekday())
        for i in sel:
            if wk_start <= D[i] <= tf:
                opex_week[i] = True
    quad = np.isin(month, [3, 6, 9, 12])
    return dict(D=D, dow=dow, month=month, year=year, day=day, ym=ym,
                tdom=tdom, rtdom=rtdom, pre_hol=pre_hol, post_hol=post_hol,
                opex=opex, opex_week=opex_week, quad=quad)


def load_crypto_hourly(symbols):
    out = {}
    base = None
    for s in symbols:
        p = CAL / f"{s}_1h.csv"
        ms, c = [], []
        with p.open() as f:
            rd = csv.reader(f)
            next(rd)
            for row in rd:
                ms.append(int(row[0]))
                c.append(float(row[4]))
        out[s] = (np.array(ms, dtype=np.int64), np.array(c))
    # align on BTC's hour grid
    ref_ms = out[symbols[0]][0]
    idx = {m: i for i, m in enumerate(ref_ms)}
    n = len(ref_ms)
    R = np.zeros((n, len(symbols)))
    for j, s in enumerate(symbols):
        m, c = out[s]
        px = np.full(n, np.nan)
        for k in range(len(m)):
            i = idx.get(m[k])
            if i is not None:
                px[i] = c[k]
        r = px / np.roll(px, 1) - 1.0
        r[0] = 0.0
        R[:, j] = np.clip(np.nan_to_num(r), -0.5, 0.5)
    return ref_ms, R


def crypto_features(ms):
    n = len(ms)
    hod = ((ms // 3600000) % 24).astype(int)
    days = ms // 86400000
    dow = ((days + 3) % 7).astype(int)       # 1970-01-01 = Thursday; 0=Mon -> Thu=3
    dates = [dt.datetime.utcfromtimestamp(int(m) / 1000).date() for m in ms]
    iso = np.array([d.isoformat() for d in dates])
    day_idx = days - days[0]
    return dict(hod=hod, dow=dow, iso=iso, day_idx=day_idx, dates=dates)


def load_funding():
    p = ROOT / "research" / "data" / "btc_perp_funding_binance_2019_2026.csv"
    ms, rate = [], []
    with p.open() as f:
        rd = csv.reader(f)
        next(rd)
        for row in rd:
            ms.append(int(row[0]))
            rate.append(float(row[1]))
    return np.array(ms, dtype=np.int64), np.array(rate)


def load_xs_panel():
    p = ROOT / "research" / "data" / "t9_cache" / "daily_bars.json.gz"
    with gzip.open(p, "rt") as f:
        raw = json.load(f)
    syms = [s for s, v in raw.items() if len(v) > 2400]
    alldates = sorted({d for s in syms for d in raw[s]})
    idx = {d: i for i, d in enumerate(alldates)}
    n, k = len(alldates), len(syms)
    R = np.zeros((n, k))
    LIVE = np.zeros((n, k), bool)
    for j, s in enumerate(syms):
        px = np.full(n, np.nan)
        for d, b in raw[s].items():
            px[idx[d]] = b["c"]
        r = px / np.roll(px, 1) - 1.0
        ok = np.isfinite(r)
        ok[0] = False
        R[:, j] = np.where(ok, np.clip(np.nan_to_num(r), -0.5, 0.5), 0.0)
        LIVE[:, j] = ok
    del raw
    return alldates, syms, R, LIVE


# =======================================================================================
# scoring
# =======================================================================================

def net_pnl(W, R, cost_bp):
    """W: (n,k) target weights held over period t (decided at t-1 close). R: (n,k)."""
    gross = (W * R).sum(axis=1)
    prev = np.vstack([np.zeros((1, W.shape[1])), W[:-1]])
    turn = np.abs(W - prev).sum(axis=1)
    return gross - turn * cost_bp * 1e-4


def sharpe(x, ann):
    s = x.std()
    if s <= 0 or len(x) < 30:
        return 0.0
    return float(x.mean() / s * np.sqrt(ann))


# =======================================================================================
# formula family
# =======================================================================================

class Family:
    """Holds every formula. `run(rot)` re-evaluates all of them on rotated returns."""

    def __init__(self):
        print("loading daily ETF panel ...", flush=True)
        self.dates, self.syms, A = load_daily()
        self.n = len(self.dates)
        self.c2c, self.intr, self.ovn, self.live = daily_returns(A, self.syms, self.n)
        del A
        self.F = calendar_features(self.dates)
        self.si = {s: j for j, s in enumerate(self.syms)}
        self.first_live = np.array([
            int(np.where(self.live[:, j])[0][0]) if self.live[:, j].any() else 0
            for j in range(len(self.syms))])
        self.dates_arr = np.array(self.dates)
        self.d_design = self.dates_arr <= SPLIT_DAILY
        self.d_hold = self.dates_arr > SPLIT_DAILY

        print("loading crypto hourly ...", flush=True)
        self.cs = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]
        self.cms, self.cR = load_crypto_hourly(self.cs)
        self.CF = crypto_features(self.cms)
        ciso = self.CF["iso"]
        self.c_design = ciso <= SPLIT_CRYPTO
        self.c_hold = ciso > SPLIT_CRYPTO
        fms, frate = load_funding()
        # for each hour, the LAST funding rate settled strictly before that hour starts
        pos = np.searchsorted(fms, self.cms, side="left") - 1
        self.f_prev = np.where(pos >= 0, frate[np.clip(pos, 0, len(frate) - 1)], 0.0)
        self.f_next_ms = np.where(
            np.searchsorted(fms, self.cms, side="right") < len(fms),
            fms[np.clip(np.searchsorted(fms, self.cms, side="right"), 0, len(fms) - 1)],
            0,
        )

        print("loading t9 stock panel ...", flush=True)
        self.xdates, self.xsyms, self.xR, self.xLIVE = load_xs_panel()
        self.xF = calendar_features(self.xdates)
        xa = np.array(self.xdates)
        self.x_design = xa <= SPLIT_XS
        self.x_hold = xa > SPLIT_XS

        self.reg = []
        self._register()

    # ---- helpers ----------------------------------------------------------------------
    def _w(self, n, k):
        return np.zeros((n, k))

    def _one(self, sym, mask, sign=1.0, kind="c2c"):
        """single-instrument daily weight matrix"""
        W = np.zeros((self.n, len(self.syms)))
        j = self.si[sym]
        W[mask, j] = sign
        return W, kind

    # ---- registration -----------------------------------------------------------------
    def add(self, name, desc, ds, fn, syms=None):
        first = 0
        if ds == "daily" and syms:
            for sm in syms:
                col = self.live[:, self.si[sm]]
                nz = np.where(col)[0]
                if len(nz):
                    first = max(first, int(nz[0]))
        self.reg.append((name, desc, ds, fn, first))

    def _register(self):
        F = self.F
        dow, tdom, rtdom = F["dow"], F["tdom"], F["rtdom"]
        month = F["month"]

        # ---------------- A. day of week -------------------------------------------
        dnames = ["MON", "TUE", "WED", "THU", "FRI"]
        for d in range(5):
            self.add(f"DOW_{dnames[d]}_SPY",
                     f"long SPY close-to-close only on {dnames[d]} (weekday effect)",
                     "daily", lambda R, d=d: self._one_pnl("SPY", dow == d, R, "c2c"), ["SPY"])
        self.add("DOW_MON_BASKET",
                 "long an equal-weight 9-sector-ETF basket only on Mondays",
                 "daily", lambda R: self._basket_pnl(
                     ["XLF", "XLK", "XLE", "XLV", "XLP", "XLY", "XLI", "XLU", "XLB"],
                     dow == 0, R, "c2c"), ["XLF","XLK","XLE","XLV","XLP","XLY","XLI","XLU","XLB"])
        self.add("DOW_MON_OVERNIGHT",
                 "long SPY over the weekend gap only (Fri close -> Mon open)",
                 "daily", lambda R: self._one_pnl("SPY", dow == 0, R, "ovn"), ["SPY"])
        self.add("DOW_MON_INTRADAY",
                 "long SPY Monday open->close only (no weekend gap)",
                 "daily", lambda R: self._one_pnl("SPY", dow == 0, R, "intr"), ["SPY"])
        self.add("DOW_FRI_OVERNIGHT",
                 "long SPY overnight into every Friday (Thu close -> Fri open)",
                 "daily", lambda R: self._one_pnl("SPY", dow == 4, R, "ovn"), ["SPY"])

        # ---------------- B. turn of month -----------------------------------------
        tom = (rtdom == 1) | (tdom <= 3)
        tom_tight = (rtdom == 1) | (tdom == 1)
        mid = (tdom >= 8) & (tdom <= 15)
        self.add("TOM_ARIEL_SPY", "long SPY on the last session of the month + first 3 of the next",
                 "daily", lambda R: self._one_pnl("SPY", tom, R, "c2c"), ["SPY"])
        self.add("TOM_TIGHT_SPY", "long SPY only on the last session of the month and the first",
                 "daily", lambda R: self._one_pnl("SPY", tom_tight, R, "c2c"), ["SPY"])
        self.add("MIDMONTH_SHORT_SPY", "short SPY on trading days 8-15 of each month",
                 "daily", lambda R: self._one_pnl("SPY", mid, R, "c2c", sign=-1.0), ["SPY"])
        self.add("TOM_TLT", "long TLT over the turn-of-month window (bond-side flow)",
                 "daily", lambda R: self._one_pnl("TLT", tom, R, "c2c"), ["TLT"])
        self.add("TOM_SPY_MINUS_TLT", "long SPY / short TLT over the turn-of-month window",
                 "daily", lambda R: self._pair_pnl("SPY", "TLT", tom, R), ["SPY","TLT"])
        self.add("TOM_IWM_MINUS_SPY", "long IWM / short SPY over the turn-of-month window",
                 "daily", lambda R: self._pair_pnl("IWM", "SPY", tom, R), ["IWM","SPY"])
        self.add("TOM_EFA_MINUS_SPY", "long EFA / short SPY over the turn-of-month window",
                 "daily", lambda R: self._pair_pnl("EFA", "SPY", tom, R), ["EFA","SPY"])
        self.add("TOQ_ARIEL_SPY", "turn-of-month SPY window restricted to QUARTER ends only",
                 "daily", lambda R: self._one_pnl(
                     "SPY", tom & np.isin(month, [1, 4, 7, 10]) | (tom & (rtdom == 1) & np.isin(month, [3, 6, 9, 12])),
                     R, "c2c"), ["SPY"])
        self.add("TOM_XSEC_BASKET", "long a 6-ETF cross-asset basket over the turn-of-month window",
                 "daily", lambda R: self._basket_pnl(
                     ["SPY", "QQQ", "IWM", "EFA", "EEM", "TLT"], tom, R, "c2c"),
                 ["SPY","QQQ","IWM","EFA","EEM","TLT"])

        # ---------------- C. rebalance flow (conditional) ---------------------------
        self.add("REBAL_FLOW_2D",
                 "last 2 sessions of the month: short SPY / long TLT when equities beat bonds "
                 "month-to-date, reversed when they lagged (pension rebalance direction)",
                 "daily", lambda R: self._rebal_pnl(R, window="end", sign=-1.0), ["SPY","TLT"])
        self.add("REBAL_UNWIND_2D",
                 "first 2 sessions of the month: the REBAL_FLOW_2D position reversed (flow unwind)",
                 "daily", lambda R: self._rebal_pnl(R, window="start", sign=+1.0), ["SPY","TLT"])
        self.add("REBAL_FLOW_QTR",
                 "REBAL_FLOW_2D restricted to quarter ends, conditioned on quarter-to-date spread",
                 "daily", lambda R: self._rebal_pnl(R, window="end", sign=-1.0, qtr_only=True), ["SPY","TLT"])

        # ---------------- D. OPEX ---------------------------------------------------
        ow, opx, quad = F["opex_week"], F["opex"], F["quad"]
        post_opex = np.zeros(self.n, bool)
        oi = np.where(opx)[0]
        for i in oi:
            post_opex[i + 1: i + 4] = True
        self.add("OPEX_WEEK_LONG_SPY", "long SPY every session of monthly OPEX week",
                 "daily", lambda R: self._one_pnl("SPY", ow, R, "c2c"), ["SPY"])
        self.add("OPEX_POST_SHORT_SPY", "short SPY the 3 sessions after monthly OPEX",
                 "daily", lambda R: self._one_pnl("SPY", post_opex, R, "c2c", sign=-1.0), ["SPY"])
        self.add("OPEX_QUAD_WEEK_SPY", "long SPY in OPEX week only in quad-witching months",
                 "daily", lambda R: self._one_pnl("SPY", ow & quad, R, "c2c"), ["SPY"])
        self.add("OPEX_QQQ_MINUS_SPY", "long QQQ / short SPY through OPEX week (mega-cap gamma pin)",
                 "daily", lambda R: self._pair_pnl("QQQ", "SPY", ow, R), ["QQQ","SPY"])
        self.add("OPEX_WEEK_CONT", "carry the sign of OPEX-week SPY return into the following 3 sessions",
                 "daily", lambda R: self._opex_cont_pnl(R), ["SPY"])
        self.add("OPEX_DAY_ONLY_SPY", "long SPY only on the OPEX session itself",
                 "daily", lambda R: self._one_pnl("SPY", opx, R, "c2c"), ["SPY"])

        # ---------------- E. holidays / annual seasonals ----------------------------
        ph, qh = F["pre_hol"], F["post_hol"]
        self.add("PREHOLIDAY_SPY", "long SPY on the last session before every exchange holiday",
                 "daily", lambda R: self._one_pnl("SPY", ph, R, "c2c"), ["SPY"])
        self.add("POSTHOLIDAY_SPY", "long SPY on the first session after every exchange holiday",
                 "daily", lambda R: self._one_pnl("SPY", qh, R, "c2c"), ["SPY"])
        santa = np.zeros(self.n, bool)
        yrs = F["year"]
        for y in np.unique(yrs):
            dec = np.where((yrs == y) & (month == 12))[0]
            jan = np.where((yrs == y + 1) & (month == 1))[0]
            if len(dec) >= 5:
                santa[dec[-5:]] = True
            if len(jan) >= 2:
                santa[jan[:2]] = True
        self.add("SANTA_SPY", "long SPY the last 5 sessions of December + first 2 of January",
                 "daily", lambda R: self._one_pnl("SPY", santa, R, "c2c"), ["SPY"])
        hall = np.isin(month, [11, 12, 1, 2, 3, 4])
        self.add("HALLOWEEN_SPY", "long SPY Nov-Apr, flat May-Oct ('sell in May')",
                 "daily", lambda R: self._one_pnl("SPY", hall, R, "c2c"), ["SPY"])
        self.add("JAN_IWM_MINUS_SPY", "long IWM / short SPY in January only (small-cap January effect)",
                 "daily", lambda R: self._pair_pnl("IWM", "SPY", month == 1, R), ["IWM","SPY"])
        self.add("YEAREND_TLT", "long TLT the last 3 sessions of December (index-extension buying)",
                 "daily", lambda R: self._one_pnl(
                     "TLT", santa & (month == 12), R, "c2c"), ["TLT"])
        self.add("DEC_GLD", "long GLD in December (year-end metals demand)",
                 "daily", lambda R: self._one_pnl("GLD", month == 12, R, "c2c"), ["GLD"])

        # ---------------- F. crypto session / 24-7 structure ------------------------
        hod, cdow = self.CF["hod"], self.CF["dow"]
        self.add("XT_WEEKEND_BTC", "long BTC perp over Sat+Sun UTC, flat on weekdays",
                 "crypto", lambda R: self._c_pnl(R, 0, cdow >= 5))
        self.add("XT_WEEKEND_ALTS", "long an equal-weight ETH/SOL/BNB perp basket over Sat+Sun UTC",
                 "crypto", lambda R: self._c_basket_pnl(R, [1, 2, 3], cdow >= 5))
        self.add("XT_ASIA_BTC", "long BTC perp only in the Asia session (00-08 UTC)",
                 "crypto", lambda R: self._c_pnl(R, 0, hod < 8))
        self.add("XT_EU_BTC", "long BTC perp only in the EU session (08-13 UTC)",
                 "crypto", lambda R: self._c_pnl(R, 0, (hod >= 8) & (hod < 13)))
        self.add("XT_US_BTC", "long BTC perp only in the US session (13-21 UTC)",
                 "crypto", lambda R: self._c_pnl(R, 0, (hod >= 13) & (hod < 21)))
        self.add("XT_HANDOFF_MOM", "sign of yesterday's US-session BTC return, held through the next Asia session",
                 "crypto", lambda R: self._c_handoff(R, src=(13, 21), dst=(0, 8), sign=+1.0))
        self.add("XT_HANDOFF_REV", "minus the sign of the Asia-session BTC return, held through the EU session",
                 "crypto", lambda R: self._c_handoff(R, src=(0, 8), dst=(8, 13), sign=-1.0))
        self.add("XT_FUNDING_PRE", "hour before each 8h funding settlement: long BTC perp when the "
                 "PREVIOUS settled funding rate was negative, short when positive",
                 "crypto", lambda R: self._c_funding(R, pre=True))
        self.add("XT_FUNDING_POST", "hour after each 8h funding settlement: the XT_FUNDING_PRE position reversed",
                 "crypto", lambda R: self._c_funding(R, pre=False))
        self.add("XT_MONDAY_BTC", "long BTC perp on UTC Mondays only",
                 "crypto", lambda R: self._c_pnl(R, 0, cdow == 0))
        self.add("XT_USOPEN_BTC", "long BTC perp only in the two hours spanning the US equity open (13-15 UTC)",
                 "crypto", lambda R: self._c_pnl(R, 0, (hod >= 13) & (hod < 15)))
        self.add("XT_TOM_BTC", "long BTC perp on the last UTC day of the month and the first",
                 "crypto", lambda R: self._c_tom(R))

        # ---------------- G. cross-sectional single-stock calendar ------------------
        self.add("XS_TOM_HIVOL", "turn-of-month: long the high-vol tercile of the stock panel, "
                 "short the low-vol tercile",
                 "xs", lambda R: self._xs_pnl(R, mode="tom_vol"))
        self.add("XS_MONTHEND_DRESS", "last 2 sessions of the month: long the month's winners, "
                 "short the losers (window dressing)",
                 "xs", lambda R: self._xs_pnl(R, mode="dress"))
        self.add("XS_MONTHSTART_UNWIND", "first 2 sessions of the month: the window-dressing "
                 "position reversed",
                 "xs", lambda R: self._xs_pnl(R, mode="unwind"))
        self.add("XS_DEC_TAXLOSS", "December: short the worst YTD tercile / long the best; "
                 "reversed over the first 5 sessions of January",
                 "xs", lambda R: self._xs_pnl(R, mode="taxloss"))
        self.add("XS_DOW_MON", "Mondays only: long the high-vol tercile, short the low-vol tercile",
                 "xs", lambda R: self._xs_pnl(R, mode="mon_vol"))
        self.add("XS_TOM_LONGONLY", "long the equal-weight stock panel over the turn-of-month window",
                 "xs", lambda R: self._xs_pnl(R, mode="tom_long"))

    # ---- daily formula bodies ---------------------------------------------------------
    def _pick(self, R, kind):
        return R[kind]

    def _one_pnl(self, sym, mask, R, kind, sign=1.0):
        r = R[kind][:, self.si[sym]]
        w = np.where(mask, sign, 0.0)
        prev = np.concatenate([[0.0], w[:-1]])
        turn = np.abs(w - prev)
        if kind in ("intr", "ovn"):
            turn = np.abs(w) * 2.0     # open and close both crossed
        return w * r - turn * COST_ETF_BP * 1e-4

    def _basket_pnl(self, symlist, mask, R, kind):
        js = [self.si[s] for s in symlist]
        r = R[kind][:, js].mean(axis=1)
        w = np.where(mask, 1.0, 0.0)
        prev = np.concatenate([[0.0], w[:-1]])
        return w * r - np.abs(w - prev) * COST_ETF_BP * 1e-4

    def _pair_pnl(self, a, b, mask, R):
        r = R["c2c"][:, self.si[a]] - R["c2c"][:, self.si[b]]
        w = np.where(mask, 0.5, 0.0)          # 0.5 long + 0.5 short = 1.0 gross
        prev = np.concatenate([[0.0], w[:-1]])
        return w * 2 * r * 0.5 - np.abs(w - prev) * 2 * COST_ETF_BP * 1e-4

    def _rebal_pnl(self, R, window, sign, qtr_only=False):
        c = R["c2c"]
        rs, rt = c[:, self.si["SPY"]], c[:, self.si["TLT"]]
        ym = self.F["ym"]
        tdom, rtdom, month = self.F["tdom"], self.F["rtdom"], self.F["month"]
        n = self.n
        # spread accumulated within the CURRENT month up to (and including) t-1
        cum = np.zeros(n)
        acc = 0.0
        for i in range(n):
            if i > 0 and ym[i] != ym[i - 1]:
                acc = 0.0
            cum[i] = acc                      # strictly prior-day information
            acc += rs[i] - rt[i]
        # previous month's full spread, for the start-of-month unwind
        prev_month_spread = np.zeros(n)
        last = 0.0
        run = 0.0
        for i in range(n):
            if i > 0 and ym[i] != ym[i - 1]:
                last = run
                run = 0.0
            prev_month_spread[i] = last
            run += rs[i] - rt[i]
        if window == "end":
            mask = rtdom <= 2
            cond = cum
        else:
            mask = tdom <= 2
            cond = prev_month_spread
        if qtr_only:
            mask = mask & np.isin(month, [3, 6, 9, 12])
        s = np.sign(cond) * sign
        w = np.where(mask, s, 0.0)            # w on SPY, -w on TLT
        prev = np.concatenate([[0.0], w[:-1]])
        gross = w * 0.5 * (rs - rt)
        turn = np.abs(w - prev)               # 0.5 each leg -> 1.0 gross notional
        return gross - turn * COST_ETF_BP * 1e-4

    def _opex_cont_pnl(self, R):
        c = R["c2c"][:, self.si["SPY"]]
        ow, opx = self.F["opex_week"], self.F["opex"]
        n = self.n
        w = np.zeros(n)
        oi = np.where(opx)[0]
        for i in oi:
            st = i
            while st > 0 and ow[st - 1]:
                st -= 1
            wk = c[st: i + 1].sum()
            w[i + 1: i + 4] = np.sign(wk)
        prev = np.concatenate([[0.0], w[:-1]])
        return w * c - np.abs(w - prev) * COST_ETF_BP * 1e-4

    # ---- crypto formula bodies --------------------------------------------------------
    def _c_pnl(self, R, j, mask):
        r = R[:, j]
        w = np.where(mask, 1.0, 0.0)
        prev = np.concatenate([[0.0], w[:-1]])
        return w * r - np.abs(w - prev) * COST_PERP_BP * 1e-4

    def _c_basket_pnl(self, R, js, mask):
        r = R[:, js].mean(axis=1)
        w = np.where(mask, 1.0, 0.0)
        prev = np.concatenate([[0.0], w[:-1]])
        return w * r - np.abs(w - prev) * COST_PERP_BP * 1e-4

    def _c_handoff(self, R, src, dst, sign):
        r = R[:, 0]
        hod = self.CF["hod"]
        di = self.CF["day_idx"]
        n = len(r)
        src_m = (hod >= src[0]) & (hod < src[1])
        # cumulative source-session return per UTC day
        ndays = int(di.max()) + 1
        sess = np.zeros(ndays)
        np.add.at(sess, di[src_m], r[src_m])
        s = np.sign(sess)
        dst_m = (hod >= dst[0]) & (hod < dst[1])
        # Asia session of the NEXT day follows a US session; EU session follows same-day Asia
        lag = 1 if dst[0] < src[0] else 0
        ref = np.clip(di - lag, 0, ndays - 1)
        w = np.where(dst_m & (di - lag >= 0), sign * s[ref], 0.0)
        prev = np.concatenate([[0.0], w[:-1]])
        return w * r - np.abs(w - prev) * COST_PERP_BP * 1e-4

    def _c_funding(self, R, pre):
        r = R[:, 0]
        hod = self.CF["hod"]
        # settlements at 00, 08, 16 UTC -> "hour before" = 23, 07, 15 ; "hour after" = 00, 08, 16
        m = np.isin(hod, [23, 7, 15]) if pre else np.isin(hod, [0, 8, 16])
        s = -np.sign(self.f_prev)
        if not pre:
            s = -s
        w = np.where(m, s, 0.0)
        prev = np.concatenate([[0.0], w[:-1]])
        return w * r - np.abs(w - prev) * COST_PERP_BP * 1e-4

    def _c_tom(self, R):
        r = R[:, 0]
        ds = self.CF["dates"]
        mon = np.array([d.year * 12 + d.month for d in ds])
        n = len(r)
        last_day = np.zeros(n, bool)
        first_day = np.zeros(n, bool)
        dnum = np.array([d.day for d in ds])
        for i in range(n):
            if dnum[i] <= 1:
                first_day[i] = True
        # last calendar day of month: the day index whose month differs from the next day's
        di = self.CF["day_idx"]
        for i in range(n - 1):
            if mon[i] != mon[i + 1]:
                last_day[di == di[i]] = True
        w = np.where(last_day | first_day, 1.0, 0.0)
        prev = np.concatenate([[0.0], w[:-1]])
        return w * r - np.abs(w - prev) * COST_PERP_BP * 1e-4

    # ---- cross-sectional stock bodies -------------------------------------------------
    def _xs_pnl(self, R, mode):
        n, k = R.shape
        F = self.xF
        tdom, rtdom, month = F["tdom"], F["rtdom"], F["month"]
        dow, ym, year = F["dow"], F["ym"], F["year"]
        live = self.xLIVE
        # trailing 60d vol, strictly prior information
        cs = np.cumsum(np.vstack([np.zeros((1, k)), R ** 2]), axis=0)
        vol = np.sqrt(np.maximum(cs[60:] - cs[:-60], 0) / 60.0)
        VOL = np.vstack([np.full((60, k), np.nan), vol[:-1] if len(vol) > n - 60 else vol])[:n]
        VOL = np.roll(VOL, 1, axis=0)
        # trailing 21d return
        lp = np.cumsum(np.vstack([np.zeros((1, k)), R]), axis=0)
        MOM = np.vstack([np.full((21, k), np.nan), (lp[21:] - lp[:-21])[:n - 21]])[:n]
        MOM = np.roll(MOM, 1, axis=0)
        # YTD return through the prior session
        YTD = np.zeros((n, k))
        acc = np.zeros(k)
        for i in range(n):
            if i > 0 and year[i] != year[i - 1]:
                acc = np.zeros(k)
            YTD[i] = acc
            acc = acc + R[i]

        tom = (rtdom == 1) | (tdom <= 3)
        if mode == "tom_long":
            act = tom
            score = None
        elif mode == "tom_vol":
            act, score = tom, VOL
        elif mode == "mon_vol":
            act, score = dow == 0, VOL
        elif mode == "dress":
            act, score = rtdom <= 2, MOM
        elif mode == "unwind":
            act, score = tdom <= 2, -MOM
        elif mode == "taxloss":
            jan5 = (month == 1) & (tdom <= 5)
            act = (month == 12) | jan5
            score = np.where(jan5[:, None], -YTD, YTD)
        else:
            raise ValueError(mode)

        W = np.zeros((n, k))
        for i in np.where(act)[0]:
            ok = live[i]
            if score is None:
                m = ok
                if m.sum() < 20:
                    continue
                W[i, m] = 1.0 / m.sum()
                continue
            sc = score[i]
            m = ok & np.isfinite(sc)
            if m.sum() < 30:
                continue
            idxs = np.where(m)[0]
            order = idxs[np.argsort(sc[idxs])]
            t = max(1, len(order) // 3)
            lo, hi = order[:t], order[-t:]
            W[i, hi] = 0.5 / t
            W[i, lo] = -0.5 / t
        return net_pnl(W, R, COST_STOCK_BP)

    # ---- evaluation -------------------------------------------------------------------
    def run(self, shift=None, window="design"):
        if shift is None:
            Rd = {"c2c": self.c2c, "intr": self.intr, "ovn": self.ovn}
            Rc, Rx = self.cR, self.xR
        else:
            kd, kc, kx = shift
            Rd = {k: rotate_live(v, self.first_live, kd) for k, v in
                  (("c2c", self.c2c), ("intr", self.intr), ("ovn", self.ovn))}
            Rc = np.roll(self.cR, kc, axis=0)
            Rx = np.roll(self.xR, kx, axis=0)
        out = {}
        for name, desc, ds, fn, first in self.reg:
            if ds == "daily":
                pn = fn(Rd)
                m = (self.d_design if window == "design" else self.d_hold).copy()
                m[:first] = False
                ann = 252
            elif ds == "crypto":
                pn = fn(Rc)
                m = self.c_design if window == "design" else self.c_hold
                ann = 24 * 365
            else:
                pn = fn(Rx)
                m = self.x_design if window == "design" else self.x_hold
                ann = 252
            out[name] = sharpe(pn[m], ann)
        return out

    def detail(self, name, window):
        for nm, desc, ds, fn, first in self.reg:
            if nm != name:
                continue
            Rd = {"c2c": self.c2c, "intr": self.intr, "ovn": self.ovn}
            if ds == "daily":
                pn = fn(Rd)
                m = (self.d_design if window == "design" else self.d_hold).copy()
                m[:first] = False
                ann = 252
            elif ds == "crypto":
                pn, m, ann = fn(self.cR), (self.c_design if window == "design" else self.c_hold), 24 * 365
            else:
                pn, m, ann = fn(self.xR), (self.x_design if window == "design" else self.x_hold), 252
            x = pn[m]
            nz = int((np.abs(x) > 1e-12).sum())
            eq = np.cumsum(x)
            dd = float((eq - np.maximum.accumulate(eq)).min() * 100)
            return dict(name=nm, desc=desc, dataset=ds, window=window,
                        sharpe=round(sharpe(x, ann), 3),
                        n_periods=int(len(x)), n_active_periods=nz,
                        years=round(len(x) / ann, 2),
                        ann_return_pct=round(float(x.mean() * ann * 100), 3),
                        ann_vol_pct=round(float(x.std() * np.sqrt(ann) * 100), 3),
                        total_return_pct=round(float(x.sum() * 100), 2),
                        max_drawdown_pct=round(dd, 2))
        return None


def rotate_live(arr, first_live, k):
    """Circular rotation applied INSIDE each column's live span.

    A flat np.roll would drag an instrument's pre-inception zeros into the evaluated
    window and quietly shrink its volatility, which flatters the null. Rotating within
    the live span keeps each column's zero pattern exactly where it was.
    """
    out = arr.copy()
    n = arr.shape[0]
    for j in range(arr.shape[1]):
        a = first_live[j]
        L = n - a
        if L > 10:
            out[a:, j] = np.roll(arr[a:, j], k % L)
    return out


def main():
    NREP = int(sys.argv[1]) if len(sys.argv) > 1 else 400
    fam = Family()
    N = len(fam.reg)
    print(f"{N} formulas registered", flush=True)
    design = fam.run(window="design")

    # ---- family-wide null -------------------------------------------------------------
    # Rotate every return array circularly against a FIXED calendar and re-score the whole
    # family. Two things matter here:
    #   1. deterministic COST DRIFT survives rotation (a formula that trades 3x a day still
    #      pays 3x a day), so raw max|Sharpe| across the family is dominated by the most
    #      over-traded formula rather than by luck. The family bar is therefore built on the
    #      STUDENTISED statistic z = (S - mean_null) / sd_null, which removes that drift.
    #   2. rotation preserves autocorrelation, vol clustering and cross-sectional structure.
    rng = np.random.default_rng(20260820)
    null = {k: [] for k in design}
    for rep in range(NREP):
        kd = int(rng.integers(200, fam.n - 200))
        kc = int(rng.integers(2000, len(fam.cms) - 2000))
        kx = int(rng.integers(100, len(fam.xdates) - 100))
        sh = fam.run(shift=(kd, kc, kx), window="design")
        for k, v in sh.items():
            null[k].append(v)
        if (rep + 1) % 20 == 0:
            print(f"  null rep {rep+1}/{NREP}", flush=True)

    names = [r[0] for r in fam.reg]
    M = np.array([null[k] for k in names])                 # (N, NREP)
    mu = M.mean(axis=1)
    sd = np.where(M.std(axis=1) > 1e-9, M.std(axis=1), 1e-9)
    Z = (M - mu[:, None]) / sd[:, None]
    maxz_null = np.abs(Z).max(axis=0)                       # per replicate
    design_vec = np.array([design[k] for k in names])
    zdes = (design_vec - mu) / sd

    rows = []
    for i, (name, desc, ds, fn, first) in enumerate(fam.reg):
        nl = M[i]
        rows.append(dict(
            name=name, desc=desc, dataset=ds,
            design_sharpe=round(float(design_vec[i]), 3),
            null_mean_sharpe=round(float(mu[i]), 3),
            null_sd_sharpe=round(float(sd[i]), 3),
            z_vs_own_null=round(float(zdes[i]), 2),
            p_two_sided=round(float((np.abs(nl - mu[i]) >= abs(design_vec[i] - mu[i])).mean()), 4),
            beats_family_bar=bool(abs(zdes[i]) > float(np.percentile(maxz_null, 95))),
        ))
    rows.sort(key=lambda r: -abs(r["z_vs_own_null"]))

    ndays = int(fam.d_design.sum())
    res = dict(
        theme="calendar_session_structural_flow",
        n_formulas=N,
        generated="2026-08-20",
        design_windows=dict(
            etf_daily=f"{fam.dates[0]}..{SPLIT_DAILY} ({ndays} sessions)",
            stock_panel=f"{fam.xdates[0]}..{SPLIT_XS} ({int(fam.x_design.sum())} sessions)",
            crypto_perp_hourly=f"{fam.CF['iso'][0]}..{SPLIT_CRYPTO} ({int(fam.c_design.sum())} hours)",
        ),
        holdout_windows=dict(
            etf_daily=f"2017-01-01..{fam.dates[-1]} ({int(fam.d_hold.sum())} sessions)",
            stock_panel=f"2022-01-01..{fam.xdates[-1]} ({int(fam.x_hold.sum())} sessions)",
            crypto_perp_hourly=f"2024-01-01..{fam.CF['iso'][-1]} ({int(fam.c_hold.sum())} hours)",
        ),
        costs_bp_per_side=dict(etf=COST_ETF_BP, stock=COST_STOCK_BP, perp=COST_PERP_BP),
        null=dict(
            method=("circular rotation of every return array against a fixed calendar "
                    "(inside each instrument's live span); the whole family re-scored per "
                    "replicate; statistic studentised per formula to strip deterministic "
                    "cost drift; max|z| across the family recorded"),
            replicates=NREP,
            expected_max_abs_z=round(float(maxz_null.mean()), 3),
            max_abs_z_p50=round(float(np.percentile(maxz_null, 50)), 3),
            max_abs_z_p90=round(float(np.percentile(maxz_null, 90)), 3),
            max_abs_z_p95=round(float(np.percentile(maxz_null, 95)), 3),
            analytic_sqrt_2lnN=round(float(np.sqrt(2 * np.log(N))), 3),
            note=("analytic sqrt(2 ln N) assumes N INDEPENDENT tries; these formulas are "
                  "heavily correlated, so the empirical number is the one that governs"),
        ),
        design_max_abs_z=round(float(np.abs(zdes).max()), 3),
        results=rows,
    )
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "SWEEP_calendar_session.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res["null"], indent=1))
    print(f"design max|z| = {res['design_max_abs_z']}")
    print(f"{'z':>7} {'Sharpe':>8} {'nullmu':>8} {'p':>7}  formula")
    for r in rows:
        print(f"{r['z_vs_own_null']:+7.2f} {r['design_sharpe']:+8.3f} "
              f"{r['null_mean_sharpe']:+8.3f} {r['p_two_sided']:7.4f}  "
              f"[{r['dataset']}] {r['name']}")


if __name__ == "__main__":
    main()
