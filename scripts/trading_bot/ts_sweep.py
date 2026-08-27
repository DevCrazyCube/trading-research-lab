#!/usr/bin/env python3
"""WIDE formula sweep: futures/commodities term structure, roll, seasonality, carry-momentum.

WHAT THIS IS
------------
30 STRUCTURALLY DIFFERENT signal formulas, each backtested on a DESIGN window only.
The held-out window is walled off behind a separate subcommand so the sweep cannot
peek at it.

THE ONE DATA FACT THAT DRIVES THE WHOLE DESIGN
----------------------------------------------
Yahoo's `X=F` continuous series is the FRONT CONTRACT'S PRICE, spliced. Its daily
return is therefore a SPOT-PRICE proxy, not the return of any position anyone can
hold: each contract drifts down to spot inside its life, and the splice gaps back
UP at every roll, so the roll yield is silently deleted from the series.

Measured: over 2007-01-03..2018-12-31 the CL=F price series fell ~25% while USO --
an actual front-month WTI position -- fell 80.4%. The 55pp gap IS the contango drag.
A backtest that P&Ls off CL=F returns books that 55pp as profit.

So: `=F` series are used ONLY as SIGNAL inputs (they are a fine spot proxy).
Every P&L leg is an ETF adjusted-close return, which is a real, holdable,
roll-and-fee-inclusive total return.

THE CARRY ESTIMATOR
-------------------
carry_i(t) = 252 * mean_k[ logret(ETF_i) - logret(FUT_i) ]
The ETF holds the futures (roll + fees + collateral); the futures price series is
spot-like. Their return difference over a window is the realised roll yield, plus a
CONSTANT per-name offset (expense ratio, collateral yield). Every formula consumes
carry only as (a) a z-score against its OWN trailing history or (b) a cross-sectional
RANK -- both of which are invariant to a constant per-name offset. That is deliberate:
it is what makes a 1.9%/yr expense ratio on CORN harmless.

A second, independent estimator is the maturity-ladder pair spread: USL/USO (12-month
vs front WTI), UNL/UNG (natgas), DBC/GSG (optimised-roll vs front-roll broad basket).
Those are pure maturity spreads with no fee-offset problem at all.

USAGE
    python3 scripts/trading_bot/ts_sweep.py design
    python3 scripts/trading_bot/ts_sweep.py holdout --names A,B,C
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
RAW = ROOT / "research" / "data" / "ts_cache" / "raw"
OUT = ROOT / "research" / "trading_bot"
THEME = "futures_term_structure"

DESIGN_START, DESIGN_END = 20070101, 20181231
HOLD_START, HOLD_END = 20190101, 20261231
ANN = 252.0

# --- tradable legs: ETF -> (cost bp per side of turnover) -------------------
COST_BP = {
    "SPY": 1.0, "GLD": 1.5, "IAU": 2.0, "SLV": 2.0, "TLT": 1.5, "IEF": 2.0, "SHY": 2.0,
    "USO": 3.0, "UNG": 4.0, "DBC": 4.0, "PDBC": 4.0, "GSG": 8.0, "USL": 10.0,
    "UNL": 15.0, "DBA": 8.0, "DBB": 10.0, "DBE": 10.0, "CORN": 12.0, "WEAT": 12.0,
    "SOYB": 12.0, "CANE": 15.0, "UGA": 12.0, "BNO": 10.0, "CPER": 15.0, "PPLT": 10.0,
    "SVXY": 8.0, "VIXY": 8.0, "DJP": 12.0,
}

# --- the carry panel: commodity -> (ETF leg, futures price proxy) -----------
CARRY_PAIRS = [
    ("crude",   "USO",  "CL=F"),
    ("brent",   "BNO",  "BZ=F"),
    ("natgas",  "UNG",  "NG=F"),
    ("gasoline","UGA",  "RB=F"),
    ("gold",    "GLD",  "GC=F"),
    ("silver",  "SLV",  "SI=F"),
    ("copper",  "CPER", "HG=F"),
    ("platinum","PPLT", "PL=F"),
    ("corn",    "CORN", "ZC=F"),
    ("wheat",   "WEAT", "ZW=F"),
    ("soy",     "SOYB", "ZS=F"),
    ("sugar",   "CANE", "SB=F"),
]


# ---------------------------------------------------------------------------
def _load_one(sym: str):
    p = RAW / (sym + ".json")
    if not p.exists():
        return None
    d = json.loads(p.read_text())["chart"]["result"][0]
    ts = d["timestamp"]
    q = d["indicators"]["quote"][0]
    adj = d["indicators"].get("adjclose")
    close = np.array([np.nan if x is None else float(x) for x in q["close"]])
    if adj:
        ac = np.array([np.nan if x is None else float(x) for x in adj[0]["adjclose"]])
    else:
        ac = close.copy()
    dates = np.array([int(datetime.datetime.fromtimestamp(t, datetime.UTC).strftime("%Y%m%d"))
                      for t in ts], dtype=np.int64)
    ok = np.isfinite(close)
    return dates[ok], close[ok], ac[ok]


class Panel:
    """Everything aligned to the SPY trading calendar. Forward-filled, never back-filled."""

    def __init__(self, start=20060101):
        d, c, a = _load_one("SPY")
        m = d >= start
        self.dates = d[m]
        self.T = len(self.dates)
        self.close = {}
        self.adj = {}
        self._cache = {}
        for sym in sorted({p.stem for p in RAW.glob("*.json")}):
            r = _load_one(sym)
            if r is None:
                continue
            sd, sc, sa = r
            idx = np.searchsorted(sd, self.dates, side="right") - 1
            valid = idx >= 0
            # forward fill; mask any point whose source bar is >7 calendar days stale
            cc = np.full(self.T, np.nan)
            aa = np.full(self.T, np.nan)
            cc[valid] = sc[idx[valid]]
            aa[valid] = sa[idx[valid]]
            stale = np.full(self.T, True)
            src = np.zeros(self.T, dtype=np.int64)
            src[valid] = sd[idx[valid]]
            for i in np.nonzero(valid)[0]:
                d0 = datetime.date(src[i] // 10000, src[i] // 100 % 100, src[i] % 100)
                d1 = datetime.date(self.dates[i] // 10000, self.dates[i] // 100 % 100,
                                   self.dates[i] % 100)
                stale[i] = (d1 - d0).days > 7
            cc[stale] = np.nan
            aa[stale] = np.nan
            self.close[sym] = cc
            self.adj[sym] = aa

    def ret(self, sym, adj=True):
        """Simple daily return; NaN where either endpoint is missing."""
        key = (sym, adj)
        if key in self._cache:
            return self._cache[key]
        p = (self.adj if adj else self.close).get(sym)
        if p is None:
            r = np.full(self.T, np.nan)
        else:
            r = np.full(self.T, np.nan)
            r[1:] = p[1:] / p[:-1] - 1.0
            r[~np.isfinite(r)] = np.nan
            r[np.abs(r) > 0.75] = np.nan          # splice / bad-print guard
        self._cache[key] = r
        return r

    def lr(self, sym, adj=True):
        r = self.ret(sym, adj)
        out = np.full(self.T, np.nan)
        ok = np.isfinite(r) & (r > -0.99)
        out[ok] = np.log1p(r[ok])
        return out


# --- small vector helpers (all strictly causal) ----------------------------
def roll_mean(x, k):
    out = np.full(len(x), np.nan)
    v = np.isfinite(x)
    xf = np.where(v, x, 0.0)
    cs = np.concatenate([[0.0], np.cumsum(xf)])
    cn = np.concatenate([[0.0], np.cumsum(v.astype(float))])
    n = cn[k:] - cn[:-k]
    s = cs[k:] - cs[:-k]
    good = n >= max(3, k * 0.6)
    res = np.full(len(n), np.nan)
    res[good] = s[good] / n[good]
    out[k - 1:] = res
    return out


def roll_std(x, k):
    m = roll_mean(x, k)
    m2 = roll_mean(x * x, k)
    v = m2 - m * m
    v[~np.isfinite(v)] = np.nan
    v[v < 0] = np.nan
    return np.sqrt(v)


def zscore(x, k):
    m = roll_mean(x, k)
    s = roll_std(x, k)
    out = np.full(len(x), np.nan)
    ok = np.isfinite(s) & (s > 1e-12) & np.isfinite(x) & np.isfinite(m)
    out[ok] = (x[ok] - m[ok]) / s[ok]
    return np.clip(out, -3, 3)


def lag(x, k=1):
    out = np.full(len(x), np.nan)
    if k > 0:
        out[k:] = x[:-k]
    return out


def cum_lr(x, k):
    """Sum of log returns over the trailing k days (causal, ends at t)."""
    return roll_mean(x, k) * k


# ---------------------------------------------------------------------------
class Sweep:
    def __init__(self):
        self.P = Panel()
        self.T = self.P.T
        self.dates = self.P.dates
        self.assets = sorted(COST_BP)
        self.ai = {a: i for i, a in enumerate(self.assets)}
        self.K = len(self.assets)
        self.R = np.column_stack([self.P.ret(a, adj=True) for a in self.assets])
        self.cost = np.array([COST_BP[a] / 1e4 for a in self.assets])
        self._build_carry()

    # -- carry panel --------------------------------------------------------
    def _build_carry(self):
        self.cnames, self.cetf = [], []
        rows_diff, rows_fut, rows_etf = [], [], []
        for name, etf, fut in CARRY_PAIRS:
            le = self.P.lr(etf, adj=True)
            lf = self.P.lr(fut, adj=False)
            d = le - lf
            self.cnames.append(name)
            self.cetf.append(etf)
            rows_diff.append(d)
            rows_fut.append(lf)
            rows_etf.append(le)
        self.CD = np.column_stack(rows_diff)   # daily roll-yield increment
        self.CF = np.column_stack(rows_fut)    # futures (spot-proxy) log return
        self.CE = np.column_stack(rows_etf)    # tradable ETF log return
        self.NC = len(self.cnames)

    def carry(self, k):
        return np.column_stack([roll_mean(self.CD[:, j], k) * ANN for j in range(self.NC)])

    def cmom(self, k, skip=0):
        out = []
        for j in range(self.NC):
            c = cum_lr(self.CE[:, j], k)
            out.append(c - cum_lr(self.CE[:, j], skip) if skip else c)
        return np.column_stack(out)

    # -- weight builders ----------------------------------------------------
    def blank(self):
        return np.zeros((self.T, self.K))

    def put(self, W, etf, series):
        s = np.nan_to_num(series, nan=0.0)
        W[:, self.ai[etf]] = s
        return W

    def xs_weights(self, score, n_side=4, vol_scale=None, mode="tercile"):
        """Cross-sectional long/short over the carry panel -> weights on its ETFs."""
        W = self.blank()
        S = score
        for t in range(self.T):
            row = S[t]
            ok = np.isfinite(row)
            if ok.sum() < 2 * n_side + 1:
                continue
            idx = np.nonzero(ok)[0]
            order = idx[np.argsort(row[idx])]
            ns = min(n_side, len(order) // 2)
            shorts, longs = order[:ns], order[-ns:]
            w = np.zeros(self.NC)
            if mode == "zscore":
                r = row[idx]
                z = (r - r.mean()) / (r.std() + 1e-12)
                w[idx] = z
            else:
                w[longs] = 1.0
                w[shorts] = -1.0
            if vol_scale is not None:
                vs = vol_scale[t]
                s = np.where(np.isfinite(vs) & (vs > 1e-6), 1.0 / vs, 0.0)
                w = w * s
            g = np.abs(w).sum()
            if g < 1e-12:
                continue
            w = w / g
            for j in range(self.NC):
                if w[j] != 0.0:
                    W[t, self.ai[self.cetf[j]]] += w[j]
        return W

    def ts_weights(self, score):
        """Per-name time-series sign over the carry panel, gross-normalised."""
        W = self.blank()
        S = np.sign(np.nan_to_num(score, nan=0.0))
        g = np.abs(S).sum(axis=1)
        g[g < 1e-12] = np.nan
        Wn = S / g[:, None]
        Wn = np.nan_to_num(Wn, nan=0.0)
        for j in range(self.NC):
            W[:, self.ai[self.cetf[j]]] += Wn[:, j]
        return W

    def cvol(self, k=63):
        return np.column_stack([roll_std(self.CE[:, j], k) for j in range(self.NC)]) * math.sqrt(ANN)


# ---------------------------------------------------------------------------
def month_of(dates):
    return (dates // 100) % 100


def bday_of_month(dates):
    """1-indexed trading-day-of-month within the panel calendar."""
    ym = dates // 100
    out = np.zeros(len(dates), dtype=int)
    c, prev = 0, -1
    for i, y in enumerate(ym):
        if y != prev:
            c, prev = 0, y
        c += 1
        out[i] = c
    return out


def bdays_left(dates):
    ym = dates // 100
    out = np.zeros(len(dates), dtype=int)
    n = len(dates)
    c, prev = 0, -1
    for i in range(n - 1, -1, -1):
        if ym[i] != prev:
            c, prev = 0, ym[i]
        c += 1
        out[i] = c
    return out


# ---------------------------------------------------------------------------
def build_formulas(S: Sweep):
    """Every entry: (name, description, weight matrix W[t] applied to return[t+1])."""
    P, T = S.P, S.T
    F = []

    def add(name, desc, W, group):
        F.append({"name": name, "desc": desc, "W": W, "group": group})

    # ===== GROUP A: explicit maturity-ladder term structure, single market ==
    def ladder(deferred, front):
        """log(deferred/front) drift = contango intensity. Positive = contango."""
        return P.lr(deferred, True) - P.lr(front, True)

    for tag, defr, frnt, trade in [("CRUDE", "USL", "USO", "USO"),
                                   ("NATGAS", "UNL", "UNG", "UNG"),
                                   ("BROAD", "DBC", "GSG", "GSG")]:
        d = ladder(defr, frnt)
        con63 = roll_mean(d, 63) * ANN
        z = zscore(con63, 504)
        add(f"A1_LADDER_{tag}", f"-z504(252*mean63(log {defr}/{frnt})); long {trade} when backwardated",
            S.put(S.blank(), trade, -np.clip(z, -2, 2) / 2.0), "A_ladder")

    # A2: carry MOMENTUM on the ladder (change in contango), not its level
    d = ladder("USL", "USO")
    con63 = roll_mean(d, 63) * ANN
    dcon = con63 - lag(con63, 63)
    add("A2_LADDER_CHANGE_CRUDE", "-sign(63d change in USL/USO contango); long USO when contango is FALLING",
        S.put(S.blank(), "USO", -np.sign(np.nan_to_num(dcon))), "A_ladder")

    # A3: ladder spread traded as a SPREAD (long deferred / short front) -- pure roll harvest
    W = S.blank()
    sig = np.sign(np.nan_to_num(zscore(roll_mean(ladder("USL", "USO"), 63) * ANN, 504)))
    W[:, S.ai["USL"]] = 0.5 * sig
    W[:, S.ai["USO"]] = -0.5 * sig
    add("A3_LADDER_SPREAD_CRUDE", "long USL / short USO when contango z>0 (harvest the ladder), flip otherwise",
        W, "A_ladder")

    # A4: gold futures-vs-spot basis (GC=F vs GLD) -> trade GLD
    gb = P.lr("GC=F", False) - P.lr("GLD", True)
    z = zscore(roll_mean(gb, 63) * ANN, 504)
    add("A4_GOLD_BASIS", "z504 of 63d (GC=F - GLD) drift; long GLD when gold basis rich",
        S.put(S.blank(), "GLD", np.clip(z, -2, 2) / 2.0), "A_ladder")

    # A5: broad optimised-roll vs front-roll as a pure spread (DBC vs GSG)
    W = S.blank()
    sig = np.sign(np.nan_to_num(zscore(roll_mean(ladder("DBC", "GSG"), 63) * ANN, 504)))
    W[:, S.ai["DBC"]] = 0.5
    W[:, S.ai["GSG"]] = -0.5
    add("A5_OPTROLL_STATIC", "static long DBC / short GSG (optimised roll minus front roll, always on)",
        W, "A_ladder")

    # ===== GROUP B: cross-sectional carry over the 12-name commodity panel ==
    c63, c252, c21 = S.carry(63), S.carry(252), S.carry(21)
    vol63 = S.cvol(63)

    add("B1_XS_CARRY_63", "rank 12 commodities by 63d realised roll yield; long top 4 / short bottom 4 ETFs",
        S.xs_weights(c63, 4), "B_xs_carry")
    add("B2_XS_CARRY_252", "same rank but carry measured over 252d",
        S.xs_weights(c252, 4), "B_xs_carry")
    add("B3_XS_CARRY_21", "same rank but carry measured over 21d (fast)",
        S.xs_weights(c21, 4), "B_xs_carry")
    add("B4_XS_CARRY_VOLSCALED", "63d carry rank, position sized 1/vol63",
        S.xs_weights(c63, 4, vol_scale=vol63), "B_xs_carry")
    add("B5_XS_CARRY_ZWEIGHT", "63d carry, continuous cross-sectional z-score weights (no tercile cut)",
        S.xs_weights(c63, 4, mode="zscore"), "B_xs_carry")
    add("B6_TS_CARRY_SIGN", "per-name TIME-SERIES: long if own carry z504>0, short if <0, equal gross",
        S.ts_weights(np.column_stack([zscore(c63[:, j], 504) for j in range(S.NC)])), "B_xs_carry")
    add("B7_XS_CARRY_CHANGE", "rank by 63d CHANGE in carry (basis momentum), long rising-carry names",
        S.xs_weights(c63 - np.vstack([np.full((63, S.NC), np.nan), c63[:-63]]), 4), "B_xs_carry")

    # B8: Boons-Prado style basis-momentum = 12m ETF return minus 12m futures-price return
    bm = np.column_stack([cum_lr(S.CE[:, j], 252) - cum_lr(S.CF[:, j], 252) for j in range(S.NC)])
    add("B8_BASIS_MOMENTUM_252", "rank by (12m ETF return - 12m futures price return) = cumulative realised roll",
        S.xs_weights(bm, 4), "B_xs_carry")

    # B9: CONTAMINATION TEST. The ETF and its futures print at different times and the
    # ETF carries a mean-reverting premium/discount, so a short-window carry estimate is
    # partly a recent PRICE move, not roll. Estimating carry over [t-84, t-21] and
    # skipping the last month removes that overlap. If the family survives the skip it is
    # carry; if it dies it was stale-price reversion wearing a carry costume.
    c84 = S.carry(84)
    carry_skip = np.column_stack([(c84[:, j] * 84 - c21[:, j] * 21) / 63.0 for j in range(S.NC)])
    carry_skip = np.vstack([np.full((21, S.NC), np.nan), carry_skip[:-21]])
    add("B9_XS_CARRY_SKIP21", "carry over [t-84,t-21] only -- skips the last month to kill ETF/futures price overlap",
        S.xs_weights(carry_skip, 4), "B_xs_carry")

    # B10/B11: low-turnover variants. The cost line, not the signal, decided the first
    # cut of this sweep; holding weights fixed inside the month is the structural fix.
    def monthly(W):
        out = np.array(W, copy=True)
        ym = S.dates // 100
        for t in range(1, S.T):
            if ym[t] == ym[t - 1]:
                out[t] = out[t - 1]
        return out

    add("B10_XS_CARRY_MONTHLY", "63d carry rank, weights REBALANCED ONLY ONCE A MONTH (turnover control)",
        monthly(S.xs_weights(c63, 4)), "B_xs_carry")
    add("B11_XS_CARRY_LIQUID_MONTHLY",
        "carry rank restricted to the 6 cheapest-to-trade ETFs, monthly rebalance",
        monthly(S.xs_weights(
            np.where(np.isin(np.arange(S.NC),
                             [S.cnames.index(x) for x in
                              ("crude", "natgas", "gold", "silver", "gasoline", "corn")]),
                     c63, np.nan), 2)), "B_xs_carry")

    # ===== GROUP C: momentum and carry x momentum ==========================
    m12 = S.cmom(252, skip=21)
    m1 = S.cmom(21)
    add("C1_XS_MOM_12_1", "classic cross-sectional 12-1 momentum on the commodity ETFs",
        S.xs_weights(m12, 4), "C_mom")
    add("C2_XS_REVERSAL_1M", "short past-1m winners / long past-1m losers",
        S.xs_weights(-m1, 4), "C_mom")
    zc = np.column_stack([zscore(c63[:, j], 504) for j in range(S.NC)])
    zm = np.column_stack([zscore(m12[:, j], 504) for j in range(S.NC)])
    add("C3_CARRY_PLUS_MOM", "rank by z(carry63)+z(mom12-1), long top 4 / short bottom 4",
        S.xs_weights(zc + zm, 4), "C_mom")
    agree = np.where(np.sign(np.nan_to_num(zc)) == np.sign(np.nan_to_num(zm)), zc + zm, np.nan)
    add("C4_CARRY_MOM_AGREE", "trade only names where carry and momentum AGREE in sign",
        S.xs_weights(agree, 3), "C_mom")
    add("C5_MOM_SIGNED_BY_CARRY", "score = sign(carry) * |mom12-1| (carry picks the side, momentum the size)",
        S.xs_weights(np.sign(np.nan_to_num(zc)) * np.abs(zm), 4), "C_mom")
    tsm = np.column_stack([np.sign(np.nan_to_num(m12[:, j])) for j in range(S.NC)])
    add("C6_TS_MOM", "per-name time-series 12-1 momentum sign (trend following, no cross-section)",
        S.ts_weights(tsm), "C_mom")

    # ===== GROUP D: seasonality ============================================
    mo = month_of(S.dates)
    yr = S.dates // 10000

    def expanding_month_stat(col, stat="mean", min_years=5):
        """For each t: the stat of this asset's returns in the CURRENT calendar month,
        computed over STRICTLY PRIOR years only. No look-ahead."""
        out = np.full(S.T, np.nan)
        x = S.CE[:, col]
        for m in range(1, 13):
            sel = np.nonzero(mo == m)[0]
            if len(sel) == 0:
                continue
            vals, yrs = x[sel], yr[sel]
            for i, t in enumerate(sel):
                prior = (yrs < yr[t]) & np.isfinite(vals)
                nyr = len(np.unique(yrs[prior])) if prior.any() else 0
                if nyr < min_years:
                    continue
                v = vals[prior]
                if stat == "mean":
                    out[t] = v.mean()
                else:
                    out[t] = v.mean() / (v.std() / math.sqrt(len(v)) + 1e-12)
        return out

    seas_mean = np.column_stack([expanding_month_stat(j, "mean") for j in range(S.NC)])
    seas_t = np.column_stack([expanding_month_stat(j, "t") for j in range(S.NC)])
    add("D1_XS_SEASONALITY_MEAN", "rank by expanding prior-years mean return in the CURRENT calendar month",
        S.xs_weights(seas_mean, 4), "D_seasonality")
    add("D2_XS_SEASONALITY_T", "same but ranked by the prior-years t-statistic, not the mean",
        S.xs_weights(seas_t, 4), "D_seasonality")
    add("D3_TS_SEASONALITY", "per-name: long if prior-years mean for this month > 0, else short",
        S.ts_weights(np.sign(np.nan_to_num(seas_mean))), "D_seasonality")

    # D4: fixed natgas inventory-cycle prior (no fitting at all)
    ngs = np.where((mo >= 2) & (mo <= 8), 1.0, -1.0)
    add("D4_NG_INVENTORY_CYCLE", "long UNG Feb-Aug (injection season), short Sep-Jan; fixed prior, nothing fitted",
        S.put(S.blank(), "UNG", ngs), "D_seasonality")

    # D5: the Goldman roll window -- optimised-roll long / front-roll short on bdays 5-9
    bd = bday_of_month(S.dates)
    inroll = ((bd >= 5) & (bd <= 9)).astype(float)
    W = S.blank()
    W[:, S.ai["DBC"]] = 0.5 * inroll
    W[:, S.ai["GSG"]] = -0.5 * inroll
    add("D5_GOLDMAN_ROLL_WINDOW", "long DBC / short GSG only on business days 5-9 (the index roll window), flat else",
        W, "D_seasonality")

    # D6: turn-of-month in the equity index
    bl = bdays_left(S.dates)
    tom = ((bd <= 3) | (bl <= 1)).astype(float)
    add("D6_TURN_OF_MONTH_EQ", "long SPY on the last trading day + first 3 of each month, flat otherwise",
        S.put(S.blank(), "SPY", tom), "D_seasonality")

    # D7: commodity-index seasonality, time-series on DBC
    dbc_lr = P.lr("DBC", True)
    dbc_seas = np.full(S.T, np.nan)
    for m in range(1, 13):
        sel = np.nonzero(mo == m)[0]
        for t in sel:
            prior = (yr[sel] < yr[t]) & np.isfinite(dbc_lr[sel])
            if len(np.unique(yr[sel][prior])) >= 5:
                dbc_seas[t] = dbc_lr[sel][prior].mean()
    add("D7_TS_SEASONALITY_DBC", "long/short the broad basket DBC by its own expanding month-of-year mean",
        S.put(S.blank(), "DBC", np.sign(np.nan_to_num(dbc_seas))), "D_seasonality")

    # ===== GROUP E: volatility term structure ==============================
    vix, v3m, v9d, v6m = (P.close.get(s) for s in ("^VIX", "^VIX3M", "^VIX9D", "^VIX6M"))
    with np.errstate(invalid="ignore", divide="ignore"):
        slope_1_3 = np.log(vix / v3m)
        slope_9d_1 = np.log(v9d / vix)
        slope_3_6 = np.log(v3m / v6m)
    add("E1_VIX_CONTANGO_SPY", "long SPY when log(VIX/VIX3M)<0 (vol curve in contango), short when >0",
        S.put(S.blank(), "SPY", -np.sign(np.nan_to_num(slope_1_3))), "E_volterm")
    add("E2_VIX_CONTANGO_SHORTVOL", "same vol-curve sign but expressed in SVXY (harvest the vol roll directly)",
        S.put(S.blank(), "SVXY", -np.sign(np.nan_to_num(slope_1_3))), "E_volterm")
    add("E3_VIX_CONTANGO_Z", "continuous: -z252(log VIX/VIX3M) sized into SPY",
        S.put(S.blank(), "SPY", -np.clip(zscore(slope_1_3, 252), -2, 2) / 2.0), "E_volterm")
    add("E4_VIX9D_SLOPE", "front of the vol curve: -sign(log VIX9D/VIX) into SPY",
        S.put(S.blank(), "SPY", -np.sign(np.nan_to_num(slope_9d_1))), "E_volterm")
    add("E5_VIX_FAR_SLOPE", "far end only: -sign(log VIX3M/VIX6M) into SPY",
        S.put(S.blank(), "SPY", -np.sign(np.nan_to_num(slope_3_6))), "E_volterm")
    curve = np.nan_to_num(slope_1_3) + np.nan_to_num(slope_3_6)
    add("E6_VIX_CURVE_SUM", "whole-curve slope (1M/3M + 3M/6M) into SVXY",
        S.put(S.blank(), "SVXY", -np.sign(curve)), "E_volterm")

    # ===== GROUP F: equity-index futures basis =============================
    es, spx = P.close.get("ES=F"), P.close.get("^GSPC")
    with np.errstate(invalid="ignore", divide="ignore"):
        basis = es / spx - 1.0
    zb = zscore(basis, 252)
    add("F1_ES_BASIS_Z", "z252 of the ES=F / S&P cash basis; long SPY when the basis is rich",
        S.put(S.blank(), "SPY", np.clip(zb, -2, 2) / 2.0), "F_eqbasis")
    add("F2_ES_BASIS_CHANGE", "sign of the 21d change in the ES basis (carry momentum) into SPY",
        S.put(S.blank(), "SPY", np.sign(np.nan_to_num(basis - lag(basis, 21)))), "F_eqbasis")

    # ===== GROUP G: rates curve carry / rolldown ===========================
    irx, fvx, tnx, tyx = (P.close.get(s) for s in ("^IRX", "^FVX", "^TNX", "^TYX"))
    sl_10_3m = tnx - irx
    sl_30_5 = tyx - fvx
    sl_10_5 = tnx - fvx
    add("G1_CURVE_CARRY_TLT", "long TLT when (10y - 3m) z252 is high (positive carry+rolldown), short when inverted",
        S.put(S.blank(), "TLT", np.clip(zscore(sl_10_3m, 252), -2, 2) / 2.0), "G_rates")
    add("G2_ROLLDOWN_IEF", "long IEF on (10y - 5y) rolldown slope z252",
        S.put(S.blank(), "IEF", np.clip(zscore(sl_10_5, 252), -2, 2) / 2.0), "G_rates")
    add("G3_CURVE_SIGN_TLT", "raw sign of (30y - 5y) slope into TLT (level, not z-score)",
        S.put(S.blank(), "TLT", np.sign(np.nan_to_num(sl_30_5))), "G_rates")
    tlt_m = cum_lr(P.lr("TLT", True), 252) - cum_lr(P.lr("TLT", True), 21)
    carry_x_mom = np.sign(np.nan_to_num(zscore(sl_10_3m, 252))) * np.sign(np.nan_to_num(tlt_m))
    add("G4_RATES_CARRY_X_MOM", "TLT only when curve carry and 12-1 price momentum agree, else flat",
        S.put(S.blank(), "TLT", np.where(carry_x_mom > 0, np.sign(np.nan_to_num(tlt_m)), 0.0)), "G_rates")

    # ===== GROUP H: carry across ASSET CLASSES (one basket) ================
    # crude carry -> USO, vol carry -> SVXY, curve carry -> TLT, commodity xs carry -> panel
    W = S.blank()
    w_c = -np.nan_to_num(np.clip(zscore(roll_mean(ladder("USL", "USO"), 63) * ANN, 504), -2, 2)) / 2.0
    w_v = -np.sign(np.nan_to_num(slope_1_3))
    w_r = np.nan_to_num(np.clip(zscore(sl_10_3m, 252), -2, 2)) / 2.0
    tot = np.abs(w_c) + np.abs(w_v) + np.abs(w_r)
    tot[tot < 1e-12] = np.nan
    W[:, S.ai["USO"]] = np.nan_to_num(w_c / tot)
    W[:, S.ai["SVXY"]] = np.nan_to_num(w_v / tot)
    W[:, S.ai["TLT"]] = np.nan_to_num(w_r / tot)
    add("H1_MULTI_ASSET_CARRY", "one gross-1 book: commodity ladder carry + vol-curve carry + rates curve carry",
        W, "H_multi")

    W2 = S.xs_weights(c63, 4) * 0.5 + S.put(S.blank(), "SVXY", -np.sign(np.nan_to_num(slope_1_3))) * 0.5
    add("H2_XSCARRY_PLUS_VOLCARRY", "half commodity cross-sectional carry, half vol-curve carry",
        W2, "H_multi")

    # ===== extra structurally-distinct entries ==============================
    # A6: natgas ladder traded as a pure calendar spread (UNL vs UNG)
    W = S.blank()
    sig = np.sign(np.nan_to_num(zscore(roll_mean(ladder("UNL", "UNG"), 63) * ANN, 504)))
    W[:, S.ai["UNL"]] = 0.5 * sig
    W[:, S.ai["UNG"]] = -0.5 * sig
    add("A6_LADDER_SPREAD_NATGAS", "long UNL / short UNG when natgas contango z>0, flip when backwardated",
        W, "A_ladder")

    # D8: fixed crude driving-season prior, nothing fitted
    add("D8_CRUDE_DRIVING_SEASON", "long USO Feb-Jun (refinery/driving build), short Jul-Jan; fixed prior",
        S.put(S.blank(), "USO", np.where((mo >= 2) & (mo <= 6), 1.0, -1.0)), "D_seasonality")

    # G5: curve STEEPENER expressed as a two-leg trade rather than a directional one
    W = S.blank()
    zs = np.clip(zscore(sl_10_3m, 252), -2, 2) / 2.0
    W[:, S.ai["SHY"]] = np.nan_to_num(zs) * 0.5
    W[:, S.ai["TLT"]] = -np.nan_to_num(zs) * 0.5
    add("G5_STEEPENER_SPREAD", "SHY vs TLT duration spread scaled by the 10y-3m slope z-score",
        W, "G_rates")

    # E7: vol-curve carry with a monthly rebalance (turnover control on the best family)
    ec = -np.sign(np.nan_to_num(slope_1_3))
    ecm = np.array(ec, copy=True)
    ymv = S.dates // 100
    for t in range(1, S.T):
        if ymv[t] == ymv[t - 1]:
            ecm[t] = ecm[t - 1]
    add("E7_VIX_CONTANGO_MONTHLY", "vol-curve sign into SVXY but only re-read once a month",
        S.put(S.blank(), "SVXY", ecm), "E_volterm")

    return F


# ---------------------------------------------------------------------------
def _legs(S: Sweep, W):
    """Return (gross_pnl_series, cost_series) aligned to dates[1:].

    THE SIGN TRAP THIS FUNCTION EXISTS TO AVOID
    -------------------------------------------
    Costs do NOT change sign when the signal does: -W trades exactly as much as +W.
    A first cut of this sweep ranked formulas by |t| of the NET series and crowned
    B3_XS_CARRY_21 at t=-3.80. Its GROSS Sharpe was only -0.78; the rest was a
    7.9%/yr cost line on an 8.1%-vol book. Flipping the sign does not buy +1.74 --
    it buys +0.78 gross MINUS the same 7.9%/yr, i.e. nothing. Ranking a sign-agnostic
    search by |net t| therefore promotes whichever formula trades the most, which is
    the opposite of what the search is for. Gross and cost are kept apart here so the
    caller can score BOTH orientations honestly.
    """
    Wf = np.where(np.isfinite(S.R), np.nan_to_num(W, nan=0.0), 0.0)
    R = np.nan_to_num(S.R, nan=0.0)
    gross = (Wf[:-1] * R[1:]).sum(axis=1)
    dW = np.abs(np.diff(np.vstack([np.zeros((1, S.K)), Wf]), axis=0))
    cost = (dW * S.cost).sum(axis=1)[:-1]
    return gross, cost, Wf


def _stats(r, yrs):
    mu, sd = r.mean(), r.std(ddof=1)
    if sd < 1e-14:
        return None
    sh = mu / sd * math.sqrt(ANN)
    se = math.sqrt((1 + 0.5 * sh ** 2) / yrs)
    eq = np.cumprod(1 + r)
    return {"sharpe": float(sh), "t_stat": float(sh / se),
            "ann_ret": float(mu * ANN), "ann_vol": float(sd * math.sqrt(ANN)),
            "max_dd": float((eq / np.maximum.accumulate(eq) - 1).min())}


def evaluate(S: Sweep, W, lo, hi):
    """Score BOTH sign orientations net of costs; report the better one.

    The search is sign-agnostic (a term-structure signal has no a-priori sign that
    this sweep is entitled to assume), so the honest statistic is
        max( Sharpe_net(+W), Sharpe_net(-W) )
    and the null distribution below is built from exactly the same statistic.
    """
    gross, cost, Wf = _legs(S, W)
    dts = S.dates[1:]
    m = (dts >= lo) & (dts <= hi)
    if m.sum() < 250:
        return None
    live = (np.abs(Wf[:-1]).sum(axis=1)[m] > 1e-9)
    if live.sum() < 250:
        return None
    yrs = float(m.sum()) / ANN
    g, c = gross[m], cost[m]
    plus, minus = _stats(g - c, yrs), _stats(-g - c, yrs)
    if plus is None or minus is None:
        return None
    best, orient = (plus, +1) if plus["sharpe"] >= minus["sharpe"] else (minus, -1)
    gs = _stats(g if orient > 0 else -g, yrs)
    return {
        **best,
        "orientation": orient,
        "sharpe_as_written": plus["sharpe"],
        "gross_sharpe": gs["sharpe"],
        "cost_drag_annual": float(c.sum() / max(yrs, 1e-9)),
        "n_days": int(m.sum()), "years": round(yrs, 2),
        "frac_days_live": float(live.mean()),
        "first": int(dts[m][0]), "last": int(dts[m][-1]),
    }


def null_max(S: Sweep, Ws, lo, hi, B=2000, seed=7):
    """Empirical distribution of the SEARCH STATISTIC under the null.

    Null construction: circularly shift the realised return matrix against the fixed
    weight matrices. That destroys signal/return alignment while preserving (a) each
    formula's turnover and cost line exactly, (b) return autocorrelation, (c) the
    cross-asset correlation structure, and (d) the correlation BETWEEN formulas --
    so the max is over 42 genuinely correlated tries, not 42 independent ones.

    The statistic drawn is identical to the one the sweep reports: for each formula
    the better of the two sign orientations net of its own costs, then the max over
    formulas.
    """
    rng = np.random.default_rng(seed)
    R = np.nan_to_num(S.R, nan=0.0)
    dts = S.dates[1:]
    m = (dts >= lo) & (dts <= hi)
    n = int(m.sum())
    if n < 250:
        return None
    yrs = n / ANN
    prepped = []
    for W in Ws:
        _, cost, Wf = _legs(S, W)
        prepped.append((Wf[:-1][m], cost[m]))
    Rn = R[1:][m]
    maxes = np.empty(B)
    for b in range(B):
        k = int(rng.integers(21, n - 21))
        Rs = np.roll(Rn, k, axis=0)
        best = -9.0
        for Wm, c in prepped:
            g = (Wm * Rs).sum(axis=1)
            for r in (g - c, -g - c):
                sd = r.std(ddof=1)
                if sd < 1e-14:
                    continue
                sh = r.mean() / sd * math.sqrt(ANN)
                if sh > best:
                    best = sh
        maxes[b] = best
    return {
        "B": B,
        "statistic": "max over formulas of max over sign of net-of-cost Sharpe",
        "expected_max_sharpe": float(maxes.mean()),
        "p95_max_sharpe": float(np.percentile(maxes, 95)),
        "p99_max_sharpe": float(np.percentile(maxes, 99)),
        "median_max_sharpe": float(np.median(maxes)),
        "_draws": maxes,
    }


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["design", "holdout"])
    ap.add_argument("--names", default="")
    ap.add_argument("--boot", type=int, default=2000)
    a = ap.parse_args()

    S = Sweep()
    F = build_formulas(S)
    print(f"panel {S.dates[0]}..{S.dates[-1]}  T={S.T}  assets={S.K}  formulas={len(F)}", flush=True)

    if a.cmd == "design":
        rows = []
        Ws = []
        for f in F:
            r = evaluate(S, f["W"], DESIGN_START, DESIGN_END)
            if r is None:
                print(f"  {f['name']:28s} SKIP (insufficient design coverage)", flush=True)
                continue
            rows.append({"name": f["name"], "group": f["group"], "desc": f["desc"], **r})
            Ws.append(f["W"])
            print(f"  {f['name']:28s} SR={r['sharpe']:+.2f} (sign {r['orientation']:+d}) "
                  f"gross={r['gross_sharpe']:+.2f} cost={r['cost_drag_annual']*100:5.2f}%/yr "
                  f"ret={r['ann_ret']*100:+.1f}% vol={r['ann_vol']*100:.1f}% dd={r['max_dd']*100:.0f}%",
                  flush=True)
        nm = null_max(S, Ws, DESIGN_START, DESIGN_END, B=a.boot)
        draws = nm.pop("_draws")
        N = len(rows)
        yrs = rows[0]["years"]
        # analytic bar: a sign-agnostic search over N formulas is 2N one-sided tries
        analytic_t = math.sqrt(2 * math.log(2 * N))
        analytic_sr = analytic_t / math.sqrt(yrs)
        emp_p = {r["name"]: float((draws >= r["sharpe"]).mean()) for r in rows}
        srs = sorted(r["sharpe"] for r in rows)
        out = {
            "theme": THEME,
            "design_window": f"{DESIGN_START}..{DESIGN_END}",
            "holdout_window_reserved": f"{HOLD_START}..{HOLD_END} (NOT evaluated by this command)",
            "n_formulas_tested": N,
            "search_is_sign_agnostic": True,
            "analytic_expected_max_t_sqrt2ln2N": analytic_t,
            "analytic_expected_max_sharpe": analytic_sr,
            "bootstrap_null": nm,
            "design_sharpe_distribution": {
                "min": srs[0], "p25": srs[len(srs) // 4], "median": srs[len(srs) // 2],
                "p75": srs[3 * len(srs) // 4], "max": srs[-1],
                "n_above_bootstrap_expected_max": sum(
                    1 for s in srs if s > nm["expected_max_sharpe"]),
                "n_above_bootstrap_p95": sum(1 for s in srs if s > nm["p95_max_sharpe"]),
                "all_sorted": srs,
            },
            "results": sorted(rows, key=lambda r: -r["sharpe"]),
            "bootstrap_p_values": emp_p,
        }
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / f"SWEEP_{THEME}_DESIGN.json").write_text(json.dumps(out, indent=2))
        print(f"\nN={N} formulas, sign-agnostic -> 2N={2*N} effective tries over {yrs:.1f}y")
        print(f"  analytic  E[max t] = sqrt(2 ln 2N) = {analytic_t:.2f}  "
              f"-> Sharpe {analytic_sr:.2f}")
        print(f"  bootstrap E[max SR] = {nm['expected_max_sharpe']:.2f}   "
              f"p95 = {nm['p95_max_sharpe']:.2f}   p99 = {nm['p99_max_sharpe']:.2f}")
        print(f"  design Sharpes: min {srs[0]:+.2f}  med {srs[len(srs)//2]:+.2f}  "
              f"max {srs[-1]:+.2f}")
        print("top by best-sign net Sharpe:")
        for r in out["results"][:8]:
            flag = "BEATS BAR" if emp_p[r["name"]] < 0.05 else ""
            print(f"  {r['name']:28s} SR={r['sharpe']:+.2f} sign={r['orientation']:+d} "
                  f"boot p={emp_p[r['name']]:.3f} {flag}")
        return 0

    # ---- holdout: only the explicitly named formulas -----------------------
    names = [x for x in a.names.split(",") if x]
    rows = []
    for f in F:
        if f["name"] not in names:
            continue
        d = evaluate(S, f["W"], DESIGN_START, DESIGN_END)
        h = evaluate(S, f["W"], HOLD_START, HOLD_END)
        rows.append({"name": f["name"], "desc": f["desc"], "design": d, "holdout": h})
        print(f"  {f['name']:28s} design SR={d['sharpe']:+.2f} t={d['t_stat']:+.2f} | "
              f"HELD-OUT SR={h['sharpe']:+.2f} t={h['t_stat']:+.2f} ret={h['ann_ret']*100:+.1f}% "
              f"dd={h['max_dd']*100:.0f}% yrs={h['years']}", flush=True)
    (OUT / f"SWEEP_{THEME}_HOLDOUT.json").write_text(json.dumps(rows, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
