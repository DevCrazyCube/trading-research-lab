#!/usr/bin/env python3
"""WIDE formula sweep: VOLATILITY-ETP TERM STRUCTURE, ROLL YIELD AND SHORT-VOL CARRY.

TERRITORY
---------
VXX/VIXY/UVXY/SVXY/VIXM/VXZ against the CBOE VIX term-structure indices
(^VIX9D / ^VIX / ^VIX3M / ^VIX6M / ^VVIX). Mechanism family: the variance risk
premium pushes the VIX futures curve into contango most of the time; every
constant-maturity VIX ETP is CONTRACTUALLY OBLIGED to roll a fixed fraction of its
book from the front to the second contract every single day, on a published
schedule, without regard to price. That forced, price-insensitive, calendar-driven
trade is the structural friction. The long-vol holder pays the roll; the short-vol
holder collects it; the tail is that the same crowd is on one side (Feb 2018).

THE THREE HARD GATES THIS FILE IMPLEMENTS
-----------------------------------------
G0 MECHANISM  -- every formula carries a one-sentence `why` and an A-PRIORI SIGN.
                 The sweep is NOT sign-agnostic: a formula is scored AS WRITTEN.
                 If the mechanism says "long SVXY when the curve is in contango",
                 then a great Sharpe on the FLIPPED sign is a failure, not a find.
G1 LAG-KILL   -- every formula is scored at three entry lags. lag1 (signal from
                 close t, MOC fill at close t+1, earns t+1 -> t+2) is the HEADLINE.
                 lag2 is the kill test. lag0 is reported only for reference and is
                 NOT used for selection, because a ^VIX-close signal filled MOC the
                 same day is a 15-minute lookahead.
G2 STATISTICS -- design window only; holdout walled behind a separate subcommand.
                 Pooled expected-max under the null is reported two ways: analytic
                 sqrt(2 ln N)/sqrt(years) and a circular-shift bootstrap that
                 preserves each formula's turnover, cost line, and the correlation
                 BETWEEN formulas (these formulas are massively correlated -- most
                 of them are "be long SVXY, sometimes" -- so an independent-tries
                 bar would be far too harsh and the bootstrap is the honest one).

THE BETA TRAP, AND WHY EVERY NUMBER HERE IS ALSO REPORTED AS ALPHA
------------------------------------------------------------------
Over 2011-2019 simply holding SVXY was one of the best Sharpes in any liquid asset.
Almost every formula below is a gated version of that single position, so a high raw
Sharpe means nothing on its own -- it is the benchmark leaking through the gate. Every
formula therefore also reports `alpha_*` from a regression on the static long-SVXY
book over the same window. A formula earns attention only if it beats the null bar on
RAW *and* carries a positive alpha t-stat against buy-and-hold short vol.

THE TAIL IS CHARGED, NOT DODGED
-------------------------------
SVXY's adjusted series carries -32% (2018-02-05) then -83% (2018-02-06); UVXY carries
+66% on 2018-02-05. None of it is winsorised away (the splice guard is at |r|>3.0, a
level no real vol-ETP day reaches, rather than the 0.75 used for equity ladders). A
close-to-close strategy CANNOT dodge 2018-02-06: the NAV collapse happened between
16:00 and 16:15 ET, after any MOC fill, so a VIX-level gate reading the 2018-02-05
close (VIX 37.3) exits at the 2018-02-06 close, i.e. after eating the whole -83%.
That is the honest result and the harness is built so it cannot be evaded.

COSTS
-----
Per-side spread on |dW| (so entry and exit are both charged -- the T6 correction),
plus a daily stock-borrow accrual on every NEGATIVE weight. Long-vol ETPs are the
crowded short in the market and are priced accordingly here (VIXY/VXX 5%/yr,
UVXY/UVIX 12%/yr). The primary short-vol expression in this sweep is a LONG SVXY
position precisely because it needs no borrow at all.

USAGE
    python3 scripts/trading_bot/volterm_sweep.py design
    python3 scripts/trading_bot/volterm_sweep.py holdout --names A,B,C
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
RAW = ROOT / "research" / "data" / "volterm_cache" / "raw"
OUT = ROOT / "research" / "trading_bot"
KEY = "volatility_etp_term_structure"

# SVXY and UVXY both list 2011-10-04; that is the first date on which the whole
# tradable universe exists, so the panel starts there and nothing is back-filled.
PANEL_START = 20111004
DESIGN_START, DESIGN_END = 20111004, 20191231
HOLD_START, HOLD_END = 20200101, 20261231
ANN = 252.0

# --- tradable legs: per-SIDE spread+impact, in bp of notional ---------------
COST_BP = {
    "SVXY": 5.0, "VIXY": 5.0, "UVXY": 5.0, "VIXM": 15.0,
    "VXX": 3.0, "VXZ": 12.0, "SVIX": 10.0, "UVIX": 8.0,
    "SVOL": 8.0, "XYLD": 8.0, "SPY": 1.0,
}

# --- annual stock-borrow charged on any NEGATIVE weight ---------------------
# Long-vol ETPs are the market's crowded short. These are deliberately at the
# expensive end of the observed range; a survivor gets a borrow sensitivity ladder.
BORROW_ANN = {
    "VIXY": 0.05, "VXX": 0.05, "UVXY": 0.12, "UVIX": 0.12,
    "VIXM": 0.02, "VXZ": 0.02,
    "SVXY": 0.01, "SVIX": 0.01, "SVOL": 0.01, "XYLD": 0.01, "SPY": 0.003,
}

ASSETS = sorted(COST_BP)


# ---------------------------------------------------------------------------
def _load_one(sym: str):
    p = RAW / (sym + ".json")
    if not p.exists():
        return None
    d = json.loads(p.read_text())["chart"]["result"][0]
    ts = d.get("timestamp")
    if not ts:
        return None
    q = d["indicators"]["quote"][0]
    adj = d["indicators"].get("adjclose")
    close = np.array([np.nan if x is None else float(x) for x in q["close"]])
    ac = (np.array([np.nan if x is None else float(x) for x in adj[0]["adjclose"]])
          if adj else close.copy())
    dates = np.array([int(datetime.datetime.fromtimestamp(t, datetime.UTC).strftime("%Y%m%d"))
                      for t in ts], dtype=np.int64)
    ok = np.isfinite(close)
    return dates[ok], close[ok], ac[ok]


class Panel:
    """Everything aligned to the SPY trading calendar. Forward-filled, never back-filled."""

    def __init__(self, start=PANEL_START):
        d, c, a = _load_one("SPY")
        m = d >= start
        self.dates = d[m]
        self.T = len(self.dates)
        self.close, self.adj, self._cache = {}, {}, {}
        for p in sorted(RAW.glob("*.json")):
            r = _load_one(p.stem)
            if r is None:
                continue
            sd, sc, sa = r
            idx = np.searchsorted(sd, self.dates, side="right") - 1
            valid = idx >= 0
            cc = np.full(self.T, np.nan)
            aa = np.full(self.T, np.nan)
            cc[valid] = sc[idx[valid]]
            aa[valid] = sa[idx[valid]]
            # mask any point whose source bar is more than 7 calendar days stale
            src = np.zeros(self.T, dtype=np.int64)
            src[valid] = sd[idx[valid]]
            stale = np.full(self.T, True)
            for i in np.nonzero(valid)[0]:
                s, t = int(src[i]), int(self.dates[i])
                d0 = datetime.date(s // 10000, s // 100 % 100, s % 100)
                d1 = datetime.date(t // 10000, t // 100 % 100, t % 100)
                stale[i] = (d1 - d0).days > 7
            cc[stale] = np.nan
            aa[stale] = np.nan
            self.close[p.stem] = cc
            self.adj[p.stem] = aa

    def ret(self, sym, adj=True):
        key = (sym, adj)
        if key in self._cache:
            return self._cache[key]
        p = (self.adj if adj else self.close).get(sym)
        r = np.full(self.T, np.nan)
        if p is not None:
            r[1:] = p[1:] / p[:-1] - 1.0
            r[~np.isfinite(r)] = np.nan
            # splice guard ONLY. 0.75 would delete SVXY 2018-02-06 (-83%) and
            # UVXY 2018-02-05 (+66%), which are the whole point of this territory.
            r[np.abs(r) > 3.0] = np.nan
        self._cache[key] = r
        return r

    def lr(self, sym, adj=True):
        r = self.ret(sym, adj)
        out = np.full(self.T, np.nan)
        ok = np.isfinite(r) & (r > -0.99)
        out[ok] = np.log1p(r[ok])
        return out

    def lvl(self, sym):
        return self.close.get(sym, np.full(self.T, np.nan))


# --- causal vector helpers --------------------------------------------------
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
    v = roll_mean(x * x, k) - m * m
    v[~np.isfinite(v)] = np.nan
    v[v < 0] = np.nan
    return np.sqrt(v)


def roll_med(x, k):
    """Trailing median, causal. Loop is fine at T~3.7k."""
    out = np.full(len(x), np.nan)
    for i in range(k - 1, len(x)):
        w = x[i - k + 1:i + 1]
        w = w[np.isfinite(w)]
        if len(w) >= max(3, int(k * 0.6)):
            out[i] = np.median(w)
    return out


def roll_max(x, k):
    out = np.full(len(x), np.nan)
    for i in range(k - 1, len(x)):
        w = x[i - k + 1:i + 1]
        w = w[np.isfinite(w)]
        if len(w):
            out[i] = w.max()
    return out


def zscore(x, k, clip=3.0):
    m, s = roll_mean(x, k), roll_std(x, k)
    out = np.full(len(x), np.nan)
    ok = np.isfinite(s) & (s > 1e-12) & np.isfinite(x) & np.isfinite(m)
    out[ok] = (x[ok] - m[ok]) / s[ok]
    return np.clip(out, -clip, clip)


def lagv(x, k=1):
    out = np.full(len(x), np.nan)
    if k > 0:
        out[k:] = x[:-k]
    else:
        out[:] = x
    return out


def sgn(x):
    return np.sign(np.nan_to_num(x, nan=0.0))


def gate(x):
    """Boolean-as-float, NaN -> 0 (flat). Never long on a missing signal."""
    return (np.nan_to_num(x, nan=0.0) > 0).astype(float)


# --- VIX futures expiry calendar (deterministic, no lookahead) --------------
def third_friday(y, m):
    d = datetime.date(y, m, 1)
    # weekday(): Mon=0 .. Fri=4
    offs = (4 - d.weekday()) % 7
    return d + datetime.timedelta(days=offs + 14)


def vix_expiries(y0, y1):
    """Final settlement = the Wednesday 30 days before the third Friday of the NEXT month."""
    out = []
    for y in range(y0, y1 + 1):
        for m in range(1, 13):
            ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
            e = third_friday(ny, nm) - datetime.timedelta(days=30)
            out.append(int(e.strftime("%Y%m%d")))
    return sorted(out)


def days_to_expiry(dates):
    """Trading days from each panel date to the next VIX expiry (0 on/after it)."""
    exp = np.array(vix_expiries(int(dates[0]) // 10000 - 1, int(dates[-1]) // 10000 + 1))
    out = np.zeros(len(dates), dtype=int)
    j = 0
    for i, d in enumerate(dates):
        while j < len(exp) - 1 and exp[j] < d:
            j += 1
        # count panel days strictly between d and the next expiry
        nxt = exp[j]
        out[i] = int(np.searchsorted(dates, nxt, side="right") - i - 1)
        if out[i] < 0:
            out[i] = 0
    return out


# ---------------------------------------------------------------------------
class Sweep:
    def __init__(self):
        self.P = Panel()
        self.T = self.P.T
        self.dates = self.P.dates
        self.assets = ASSETS
        self.ai = {a: i for i, a in enumerate(ASSETS)}
        self.K = len(ASSETS)
        self.R = np.column_stack([self.P.ret(a, adj=True) for a in ASSETS])
        self.cost = np.array([COST_BP[a] / 1e4 for a in ASSETS])
        self.borrow = np.array([BORROW_ANN[a] / ANN for a in ASSETS])
        self._signals()

    # -- the signal library, all causal, all readable at close t -------------
    def _signals(self):
        P = self.P
        self.vix = P.lvl("^VIX")
        self.vix9 = P.lvl("^VIX9D")
        self.vix3m = P.lvl("^VIX3M")
        self.vix6m = P.lvl("^VIX6M")
        self.vvix = P.lvl("^VVIX")

        def lg(a, b):
            out = np.full(self.T, np.nan)
            ok = np.isfinite(a) & np.isfinite(b) & (a > 0) & (b > 0)
            out[ok] = np.log(a[ok] / b[ok])
            return out

        # curve slopes: positive = upward sloping = contango
        self.s_near = lg(self.vix, self.vix9)      # 9d  -> 30d
        self.s_main = lg(self.vix3m, self.vix)     # 30d -> 93d
        self.s_back = lg(self.vix6m, self.vix3m)   # 93d -> 186d
        self.convex = self.s_main - self.s_near

        # tradable maturity ladder: mid-term minus short-term ETP log return.
        # Positive drift = the short end is decaying faster = the roll is being paid.
        self.ladder = P.lr("VIXM") - P.lr("VIXY")

        # realised decay of the front ETP itself
        self.lr_vixy = P.lr("VIXY")
        self.lr_uvxy = P.lr("UVXY")
        self.lr_svxy = P.lr("SVXY")
        self.lr_vixm = P.lr("VIXM")
        self.lr_spy = P.lr("SPY")

        # realised vol of SPY and of the front ETP
        self.rv21 = roll_std(self.lr_spy, 21) * math.sqrt(ANN)
        self.rv5 = roll_std(self.lr_spy, 5) * math.sqrt(ANN)
        self.rv_vixy21 = roll_std(self.lr_vixy, 21) * math.sqrt(ANN)

        # variance risk premium, in vol points
        self.vrp = self.vix / 100.0 - self.rv21
        self.vrp9 = self.vix9 / 100.0 - self.rv5
        self.vrp_ratio = np.where(self.rv21 > 1e-6, (self.vix / 100.0) / self.rv21, np.nan)

        # vol level / momentum / vol-of-vol
        self.vix_ma50 = roll_mean(self.vix, 50)
        self.vix_ma20 = roll_mean(self.vix, 20)
        self.vvix_ratio = np.where(self.vix > 1e-6, self.vvix / self.vix, np.nan)

        self.dte = days_to_expiry(self.dates).astype(float)

    # -- weight builders ----------------------------------------------------
    def blank(self):
        return np.zeros((self.T, self.K))

    def leg(self, sym, series, W=None):
        W = self.blank() if W is None else W
        W[:, self.ai[sym]] += np.nan_to_num(series, nan=0.0)
        return W


# ---------------------------------------------------------------------------
def _legs(S: Sweep, W, lag: int):
    """(gross, cost, effective weights) for return index 1..T-1, at the given entry lag.

    lag=0 : signal at close t, filled MOC at close t, earns t -> t+1.
    lag=1 : signal at close t, filled MOC at close t+1, earns t+1 -> t+2.  HEADLINE.
    lag=2 : one further day of delay.  THE KILL TEST.

    Costs never change sign with the signal and are kept apart from gross so that a
    formula cannot be flattered by its own turnover.
    """
    Wf = np.where(np.isfinite(S.R), np.nan_to_num(W, nan=0.0), 0.0)
    Weff = np.full_like(Wf, 0.0)
    if lag > 0:
        Weff[lag:] = Wf[:-lag]
    else:
        Weff = Wf
    R = np.nan_to_num(S.R, nan=0.0)
    gross = (Weff[:-1] * R[1:]).sum(axis=1)
    dW = np.abs(np.diff(np.vstack([np.zeros((1, S.K)), Weff]), axis=0))
    spread = (dW * S.cost).sum(axis=1)[:-1]
    borrow = (np.maximum(-Weff, 0.0) * S.borrow).sum(axis=1)[:-1]
    return gross, spread + borrow, Weff


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
    dd = float((eq / peak - 1.0).min())
    srt = np.sort(r)
    k = max(1, int(0.05 * n))
    return {
        "sharpe": float(sh),
        "t_stat": float(sh * math.sqrt(yrs)),
        "ann_ret": float(r.mean() * ANN),
        "ann_vol": float(sd * math.sqrt(ANN)),
        "max_dd": dd,
        "worst_day": float(srt[0]),
        "cvar5": float(srt[:k].mean()),
        "skew": float(((r - r.mean()) ** 3).mean() / sd ** 3),
        "hit": float((r > 0).mean()),
    }


def evaluate(S: Sweep, W, lo, hi, lag: int, bench=None):
    gross, cost, Weff = _legs(S, W, lag)
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
        b = bench[m]
        vb = b.var(ddof=1)
        beta = float(np.cov(net, b, ddof=1)[0, 1] / vb) if vb > 1e-18 else 0.0
        resid = net - beta * b
        rs = resid.std(ddof=1)
        a_ann = float(resid.mean() * ANN)
        out["beta_vs_static_svxy"] = beta
        out["alpha_annual"] = a_ann
        out["alpha_t"] = float(resid.mean() / rs * math.sqrt(len(resid))) if rs > 1e-14 else 0.0
    return out


def null_max(S: Sweep, Ws, lo, hi, lag, B=2000, seed=11):
    """Circular-shift null of the SEARCH STATISTIC actually used: max over formulas
    of the AS-WRITTEN net Sharpe. Preserves turnover, cost lines, return
    autocorrelation, cross-asset correlation and the correlation between formulas."""
    rng = np.random.default_rng(seed)
    dts = S.dates[1:]
    m = (dts >= lo) & (dts <= hi)
    n = int(m.sum())
    if n < 250:
        return None
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
            if sh > best:
                best = sh
        maxes[b] = best
    return {
        "B": B,
        "statistic": "max over formulas of AS-WRITTEN net-of-cost Sharpe (signs fixed a priori)",
        "expected_max_sharpe": float(maxes.mean()),
        "p95_max_sharpe": float(np.percentile(maxes, 95)),
        "p99_max_sharpe": float(np.percentile(maxes, 99)),
        "_draws": maxes,
    }


# ---------------------------------------------------------------------------
def build_formulas(S: Sweep):
    """(name, why, sign_is_a_priori, W). W[t] is the target book from close-t data."""
    F = []

    def add(name, why, W, group):
        F.append({"name": name, "why": why, "W": W, "group": group})

    T = S.T
    ones = np.ones(T)

    # ===== BENCHMARK ========================================================
    add("Z0_STATIC_LONG_SVXY",
        "BENCHMARK, not a formula: hold the inverse short-term VIX-futures ETP always. "
        "Every gated formula below is a subset of this position, so this is the bar.",
        S.leg("SVXY", ones), "Z_bench")

    add("Z1_STATIC_SHORT_VIXY",
        "BENCHMARK: the same short-vol exposure expressed by borrowing the long-vol ETP, "
        "so the 5%/yr borrow line is visible next to the borrow-free SVXY version.",
        S.leg("VIXY", -ones), "Z_bench")

    # ===== GROUP A: VIX-index curve slope gates =============================
    # WHY (whole group): the ETP must roll front->second daily on a published schedule.
    # When the curve slopes up, that forced roll sells cheap and buys dear every day and
    # the short-vol side collects it; when the curve inverts the sign of the forced trade
    # reverses. The slope measured at close t is the best free read on that.
    add("A1_CONTANGO_SIGN_3M",
        "Long SVXY only while log(VIX3M/VIX)>0: the forced daily front->second roll is a "
        "loss for the long-vol holder exactly when the 30d->93d curve slopes up.",
        S.leg("SVXY", gate(S.s_main)), "A_curve")

    add("A2_CONTANGO_Z",
        "Size the SVXY carry by z252 of the 30d->93d slope: the roll paid per day is "
        "proportional to how steep the curve is, not merely to its sign.",
        S.leg("SVXY", np.clip(np.nan_to_num(zscore(S.s_main, 252), nan=0.0), 0, 2) / 2.0),
        "A_curve")

    add("A3_CONTANGO_STEEP_ONLY",
        "Long SVXY only when the 30d->93d slope is above its own trailing 252d median: "
        "shallow contango does not pay enough roll to cover the crash tail.",
        S.leg("SVXY", gate(S.s_main - roll_med(S.s_main, 252))), "A_curve")

    add("A4_NEARSLOPE_SIGN",
        "Long SVXY only while log(VIX/VIX9D)>0: the 9d->30d segment inverts FIRST in a "
        "vol shock, so it is the earliest free read that the forced roll has flipped.",
        S.leg("SVXY", gate(S.s_near)), "A_curve")

    add("A5_CURVE_CONVEXITY",
        "Long SVXY when the far slope exceeds the near slope (convex curve): a curve that "
        "is steep out front but flat behind is a stressed curve, and the roll is not safe.",
        S.leg("SVXY", gate(S.convex)), "A_curve")

    add("A6_BACKSLOPE",
        "Long SVXY while the 93d->186d segment slopes up: the back end is where the pure "
        "term premium lives, unpolluted by short-dated event demand.",
        S.leg("SVXY", gate(S.s_back)), "A_curve")

    add("A7_SLOPE_MOMENTUM",
        "Long SVXY when the 30d->93d slope has STEEPENED over 5 days: the forced roll cost "
        "the long-vol ETP pays is re-set daily, so a steepening curve raises tomorrow's carry.",
        S.leg("SVXY", gate(S.s_main - lagv(S.s_main, 5))), "A_curve")

    add("A8_DUAL_GATE",
        "Long SVXY only when BOTH the 9d->30d and 30d->93d segments slope up: require the "
        "whole front of the curve to be paying the roll, not just one segment.",
        S.leg("SVXY", gate(S.s_near) * gate(S.s_main)), "A_curve")

    add("A9_TRIPLE_GATE",
        "Long SVXY only when all three measured segments (9->30, 30->93, 93->186) slope up: "
        "the strictest possible statement that the entire term structure is in contango.",
        S.leg("SVXY", gate(S.s_near) * gate(S.s_main) * gate(S.s_back)), "A_curve")

    # ===== GROUP B: the ETPs' OWN realised roll (no index proxy) ============
    # WHY: VIXY and VIXM hold the same futures curve at different maturities. Their return
    # difference IS the realised roll of the front bucket plus a constant fee offset, and it
    # is measured in tradable prices rather than inferred from a non-tradable index.
    lad63 = roll_mean(S.ladder, 63) * ANN
    lad21 = roll_mean(S.ladder, 21) * ANN
    add("B1_ETP_LADDER_CARRY_63",
        "Long SVXY when 63d mean of (VIXM - VIXY) log returns is positive: the short bucket "
        "decaying faster than the mid bucket IS the realised front roll, priced in tradables.",
        S.leg("SVXY", gate(lad63)), "B_ladder")

    add("B2_ETP_LADDER_CARRY_21",
        "Same tradable roll estimator over 21 days: a faster read of whether the front bucket "
        "is currently the one being bled by the roll.",
        S.leg("SVXY", gate(lad21)), "B_ladder")

    add("B3_ETP_LADDER_Z",
        "Size the SVXY carry by z504 of the tradable 63d roll estimator, long-only side.",
        S.leg("SVXY", np.clip(np.nan_to_num(zscore(lad63, 504), nan=0.0), 0, 2) / 2.0),
        "B_ladder")

    add("B4_CAL_SPREAD_STATIC",
        "Always long VIXM / short VIXY, gross 1: a pure maturity spread on one curve. The "
        "front bucket rolls a bigger fraction of its book per day than the mid bucket, so the "
        "spread harvests the roll differential with no outright vol direction.",
        S.leg("VIXY", -0.5 * ones, S.leg("VIXM", 0.5 * ones)), "B_ladder")

    add("B5_CAL_SPREAD_TIMED",
        "The same VIXM/VIXY maturity spread, on only while the 30d->93d curve slopes up: the "
        "roll differential reverses sign when the curve inverts.",
        S.leg("VIXY", -0.5 * gate(S.s_main), S.leg("VIXM", 0.5 * gate(S.s_main))), "B_ladder")

    dec21 = -roll_mean(S.lr_vixy, 21) * ANN
    add("B6_REALISED_DECAY",
        "Long SVXY when the front ETP has been decaying over the last 21 days: the ETP's own "
        "realised drift is the most direct evidence that the forced roll is currently a cost.",
        S.leg("SVXY", gate(dec21)), "B_ladder")

    add("B7_CALM_FRONT",
        "Long SVXY when the front ETP's own 21d realised vol is below its 252d median: the "
        "roll is collected smoothly only when the front contract is not being repriced.",
        S.leg("SVXY", gate(roll_med(S.rv_vixy21, 252) - S.rv_vixy21)), "B_ladder")

    lev = roll_mean(S.lr_uvxy - 2.0 * S.lr_vixy, 63) * ANN
    add("B8_LEVERAGE_DRAG_PAIR",
        "Long VIXY 2 / short UVXY 1 (gross 1): the levered ETP must rebalance to target every "
        "close, so it compounds at minus half its variance relative to twice the 1x. That drag "
        "is mechanical and is collected without taking a view on the curve.",
        S.leg("UVXY", -(1.0 / 3.0) * ones, S.leg("VIXY", (2.0 / 3.0) * ones)), "B_ladder")

    add("B9_LEVERAGE_DRAG_TIMED",
        "The same levered-pair drag, sized by the measured 63d drag itself, on only when the "
        "drag has actually been negative (i.e. the rebalance is currently costing UVXY).",
        S.leg("UVXY", -(1.0 / 3.0) * gate(-lev), S.leg("VIXY", (2.0 / 3.0) * gate(-lev))),
        "B_ladder")

    # ===== GROUP C: the variance risk premium itself =======================
    # WHY: the root cause of contango. Index option sellers charge more implied vol than the
    # market subsequently realises, because they warehouse a crash risk nobody wants.
    add("C1_VRP_SIGN",
        "Long SVXY when 30d implied vol exceeds SPY's trailing 21d realised vol: the option "
        "seller's premium is the source of the whole roll, so harvest it only when it exists.",
        S.leg("SVXY", gate(S.vrp)), "C_vrp")

    add("C2_VRP_Z",
        "Size the SVXY carry by z252 of the implied-minus-realised spread.",
        S.leg("SVXY", np.clip(np.nan_to_num(zscore(S.vrp, 252), nan=0.0), 0, 2) / 2.0),
        "C_vrp")

    add("C3_VRP_RATIO_110",
        "Long SVXY only when implied/realised exceeds 1.10: require the premium to be a clear "
        "margin, not a rounding difference between two noisy vol estimates.",
        S.leg("SVXY", gate(S.vrp_ratio - 1.10)), "C_vrp")

    add("C4_VRP_9D",
        "Long SVXY when 9-day implied exceeds SPY's 5-day realised: the near-dated premium is "
        "where event-hedging demand concentrates and where the roll bites hardest.",
        S.leg("SVXY", gate(S.vrp9)), "C_vrp")

    add("C5_VRP_AND_CONTANGO",
        "Long SVXY only when the premium exists AND the curve slopes up: the premium is the "
        "cause, the slope is the transmission; require both links of the chain.",
        S.leg("SVXY", gate(S.vrp) * gate(S.s_main)), "C_vrp")

    # ===== GROUP D: tail gates and structural hedges =======================
    # WHY: the crowd on the short-vol side is the same crowd, and it is levered. Feb 2018 is
    # the proof. These formulas do not claim extra carry; they claim the tail can be bounded.
    add("D1_VIX_LEVEL_GATE",
        "Long SVXY only while VIX closed under 20: above that, the crash convexity of a short "
        "vol-futures book dominates any roll it can collect.",
        S.leg("SVXY", gate(20.0 - S.vix)), "D_tail")

    add("D2_VIX_MA_GATE",
        "Long SVXY only while VIX is below its own 50d average: vol is a regime variable and "
        "the roll is only reliably paid inside the calm regime.",
        S.leg("SVXY", gate(S.vix_ma50 - S.vix)), "D_tail")

    add("D3_VVIX_GATE",
        "Long SVXY only when VVIX/VIX is below its 252d median: a high vol-of-vol says the "
        "market is paying up for VIX convexity, which is precisely the risk being sold here.",
        S.leg("SVXY", gate(roll_med(S.vvix_ratio, 252) - S.vvix_ratio)), "D_tail")

    add("D4_INVERSION_KILL",
        "Long SVXY unless the 9d->30d segment has inverted: the near segment inverts first, so "
        "it is the cheapest available kill switch on the forced roll flipping sign.",
        S.leg("SVXY", gate(S.s_near)), "D_tail")

    spike = (np.nan_to_num(roll_mean(S.lr_vixy, 5) * 5, nan=0.0) > 0.20).astype(float)
    cool = (roll_max(spike, 10) < 0.5).astype(float)
    add("D5_SPIKE_COOLDOWN",
        "Long SVXY, but flat for 10 sessions after any 5-day +20% move in the front ETP: vol "
        "shocks cluster, and the second leg down is what killed the 2018 short-vol complex.",
        S.leg("SVXY", np.nan_to_num(cool, nan=0.0)), "D_tail")

    add("D6_BARBELL",
        "Always 0.7 SVXY + 0.3 VIXM: pay part of the harvested roll back as permanent long "
        "convexity in the mid-term bucket, which does not gap the way the front does.",
        S.leg("VIXM", 0.3 * ones, S.leg("SVXY", 0.7 * ones)), "D_tail")

    add("D7_BARBELL_TIMED",
        "The barbell, with the SVXY sleeve gated on contango and the VIXM tail sleeve always "
        "on: the hedge must not be switched off by the same signal that sizes the risk.",
        S.leg("VIXM", 0.3 * ones, S.leg("SVXY", 0.7 * gate(S.s_main))), "D_tail")

    add("D8_EQUITY_HEDGED_CARRY",
        "Long SVXY, short 0.35 SPY: strip the equity beta so what is left is the roll and the "
        "variance premium rather than a leveraged bet that stocks go up.",
        S.leg("SPY", -0.35 * gate(S.s_main), S.leg("SVXY", gate(S.s_main))), "D_tail")

    # ===== GROUP E: the long-vol side and the two-sided switch =============
    # WHY: when the curve inverts, the forced daily roll works FOR the long-vol holder, and
    # dealers short gamma must chase, so backwardation is momentum-y rather than mean-reverting.
    add("E1_BACKWARDATION_LONG",
        "Long VIXY only while the 30d->93d curve is inverted: in backwardation the mandated "
        "roll buys cheap and sells dear for the long-vol holder.",
        S.leg("VIXY", gate(-S.s_main)), "E_longvol")

    add("E2_BACKWARDATION_MOMENTUM",
        "Long VIXY only when the curve is inverted AND VIX is above its 20d average: require "
        "the roll to have flipped and the regime to still be deteriorating.",
        S.leg("VIXY", gate(-S.s_main) * gate(S.vix - S.vix_ma20)), "E_longvol")

    add("E3_TWO_SIDED_SWITCH",
        "Long SVXY in contango, long VIXY in backwardation: trade the SIGN of the mandated "
        "roll rather than only its profitable side; always invested, never flat.",
        S.leg("VIXY", gate(-S.s_main), S.leg("SVXY", gate(S.s_main))), "E_longvol")

    add("E4_TWO_SIDED_LADDER",
        "The same switch driven by the tradable VIXM-minus-VIXY roll estimator instead of the "
        "non-tradable VIX index curve.",
        S.leg("VIXY", gate(-lad63), S.leg("SVXY", gate(lad63))), "E_longvol")

    # ===== GROUP F: the VIX settlement cycle ===============================
    # WHY: the front future converges to spot at (F1 - spot)/dte per day, so the per-day roll a
    # constant-maturity ETP pays MECHANICALLY accelerates as the settlement date approaches,
    # while the fraction rolled per day stays fixed. Carry should be back-loaded in the cycle.
    dte = S.dte
    add("F1_LAST_WEEK_OF_CYCLE",
        "Long SVXY only in the last 5 sessions before VIX settlement (and only in contango): "
        "front-contract convergence per day is (F1-spot)/dte, which is largest as dte shrinks.",
        S.leg("SVXY", gate(S.s_main) * ((dte <= 5) & (dte >= 0)).astype(float)), "F_cycle")

    add("F2_FIRST_HALF_OF_CYCLE",
        "The complement: long SVXY only when more than 10 sessions remain to settlement. If "
        "F1 beats it, the convergence-acceleration story is wrong.",
        S.leg("SVXY", gate(S.s_main) * (dte > 10).astype(float)), "F_cycle")

    inv_dte = 1.0 / np.sqrt(np.maximum(dte, 1.0))
    add("F3_DTE_SCALED",
        "Long SVXY in contango with size proportional to 1/sqrt(days to settlement): a smooth "
        "version of the convergence-acceleration claim rather than a hard calendar window.",
        S.leg("SVXY", gate(S.s_main) * inv_dte / inv_dte[np.isfinite(inv_dte)].max()), "F_cycle")

    # ===== GROUP G: vol-of-vol conditioning ================================
    add("G1_VVIX_SCALED_CARRY",
        "Long SVXY in contango, sized inversely to z252 of VVIX: the price of VIX convexity is "
        "the market's own quote for the risk this book is short.",
        S.leg("SVXY", gate(S.s_main) *
              np.clip(1.0 - np.nan_to_num(zscore(S.vvix, 252), nan=0.0) / 2.0, 0.0, 1.0)),
        "G_volofvol")

    add("G2_VIXY_REALVOL_SCALED",
        "Long SVXY in contango, sized inversely to the front ETP's own 21d realised vol: a "
        "plain risk-parity sizing of the same carry, using tradable prices only.",
        S.leg("SVXY", gate(S.s_main) *
              np.clip(np.nan_to_num(roll_med(S.rv_vixy21, 252) / S.rv_vixy21, nan=0.0), 0.0, 1.5)),
        "G_volofvol")

    add("G3_MID_BUCKET_CARRY",
        "Long VIXM-short-side via a short VIXM position in contango: the mid bucket also pays a "
        "roll, smaller but far less convex, so it is the low-tail version of the same trade.",
        S.leg("VIXM", -gate(S.s_main)), "G_volofvol")

    return F


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["design", "holdout"])
    ap.add_argument("--names", default="")
    ap.add_argument("--boot", type=int, default=2000)
    a = ap.parse_args()

    S = Sweep()
    F = build_formulas(S)
    print(f"panel {S.dates[0]}..{S.dates[-1]}  T={S.T}  assets={S.K}  formulas={len(F)}",
          flush=True)

    # the benchmark P&L series used for alpha, at the headline lag
    bg, bc, _ = _legs(S, F[0]["W"], 1)
    bench_net = bg - bc

    if a.cmd == "design":
        rows, Ws = [], []
        for f in F:
            r1 = evaluate(S, f["W"], DESIGN_START, DESIGN_END, 1, bench=bench_net)
            if r1 is None:
                print(f"  {f['name']:26s} SKIP (insufficient design coverage)", flush=True)
                continue
            r0 = evaluate(S, f["W"], DESIGN_START, DESIGN_END, 0)
            r2 = evaluate(S, f["W"], DESIGN_START, DESIGN_END, 2, bench=bench_net)
            keep = 1.0 if abs(r1["sharpe"]) < 1e-9 else r2["sharpe"] / r1["sharpe"]
            rows.append({"name": f["name"], "group": f["group"], "why": f["why"],
                         "lag1": r1, "lag0": r0, "lag2": r2,
                         "lagkill_retention": float(keep)})
            if f["group"] != "Z_bench":
                Ws.append(f["W"])
            print(f"  {f['name']:26s} SR1={r1['sharpe']:+.2f} SR2={r2['sharpe']:+.2f} "
                  f"keep={keep:+.2f} a={r1['alpha_annual']*100:+5.1f}%/yr at={r1['alpha_t']:+.2f} "
                  f"ret={r1['ann_ret']*100:+6.1f}% vol={r1['ann_vol']*100:5.1f}% "
                  f"dd={r1['max_dd']*100:5.0f}% wd={r1['worst_day']*100:+6.1f}% "
                  f"cost={r1['cost_drag_annual']*100:4.2f}%", flush=True)

        nm = null_max(S, Ws, DESIGN_START, DESIGN_END, 1, B=a.boot)
        draws = nm.pop("_draws")
        cand = [r for r in rows if r["group"] != "Z_bench"]
        N = len(cand)
        yrs = cand[0]["lag1"]["years"]
        analytic_t = math.sqrt(2 * math.log(N))
        analytic_sr = analytic_t / math.sqrt(yrs)
        emp_p = {r["name"]: float((draws >= r["lag1"]["sharpe"]).mean()) for r in rows}
        srs = sorted(r["lag1"]["sharpe"] for r in cand)
        out = {
            "key": KEY,
            "territory": "volatility-ETP term structure, roll yield and short-vol carry",
            "design_window": f"{DESIGN_START}..{DESIGN_END}",
            "holdout_window_reserved": f"{HOLD_START}..{HOLD_END} (NOT evaluated here)",
            "n_formulas_tested": N,
            "n_benchmarks": len(rows) - N,
            "search_is_sign_agnostic": False,
            "headline_lag": 1,
            "analytic_expected_max_t_sqrt2lnN": analytic_t,
            "analytic_expected_max_sharpe": analytic_sr,
            "bootstrap_null": nm,
            "design_sharpe_distribution": {
                "min": srs[0], "median": srs[len(srs) // 2], "max": srs[-1],
                "n_above_bootstrap_expected_max": sum(
                    1 for s in srs if s > nm["expected_max_sharpe"]),
                "n_above_bootstrap_p95": sum(1 for s in srs if s > nm["p95_max_sharpe"]),
                "all_sorted": srs,
            },
            "results": sorted(rows, key=lambda r: -r["lag1"]["sharpe"]),
            "bootstrap_p_values": emp_p,
        }
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / f"NEWTERR_{KEY}_DESIGN.json").write_text(json.dumps(out, indent=2))
        print(f"\nN={N} candidate formulas over {yrs:.1f}y")
        print(f"  analytic  E[max t]=sqrt(2 ln N)={analytic_t:.2f} -> Sharpe {analytic_sr:.2f}")
        print(f"  bootstrap E[max SR]={nm['expected_max_sharpe']:.2f}  "
              f"p95={nm['p95_max_sharpe']:.2f}  p99={nm['p99_max_sharpe']:.2f}")
        print(f"  benchmark Z0_STATIC_LONG_SVXY SR="
              f"{[r for r in rows if r['name']=='Z0_STATIC_LONG_SVXY'][0]['lag1']['sharpe']:+.2f}")
        return 0

    names = [x for x in a.names.split(",") if x]
    rows = []
    for f in F:
        if f["name"] not in names:
            continue
        d = evaluate(S, f["W"], DESIGN_START, DESIGN_END, 1, bench=bench_net)
        bgh, bch, _ = _legs(S, F[0]["W"], 1)
        h = evaluate(S, f["W"], HOLD_START, HOLD_END, 1, bench=bgh - bch)
        h2 = evaluate(S, f["W"], HOLD_START, HOLD_END, 2, bench=bgh - bch)
        rows.append({"name": f["name"], "why": f["why"], "design_lag1": d,
                     "holdout_lag1": h, "holdout_lag2": h2})
        print(f"  {f['name']:26s} design SR={d['sharpe']:+.2f} | HELD-OUT SR={h['sharpe']:+.2f} "
              f"t={h['t_stat']:+.2f} ret={h['ann_ret']*100:+.1f}% vol={h['ann_vol']*100:.1f}% "
              f"dd={h['max_dd']*100:.0f}% wd={h['worst_day']*100:+.1f}% "
              f"alpha={h['alpha_annual']*100:+.1f}%/yr at={h['alpha_t']:+.2f} "
              f"| lag2 SR={h2['sharpe']:+.2f}", flush=True)
    (OUT / f"NEWTERR_{KEY}_HOLDOUT.json").write_text(json.dumps(rows, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
