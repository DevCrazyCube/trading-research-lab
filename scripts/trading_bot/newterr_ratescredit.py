#!/usr/bin/env python3
"""NEW TERRITORY -- rates / credit / bond relative value.  Wide, mechanism-gated sweep.

TERRITORY (not previously swept by this programme): Treasury-duration ETFs, IG/HY credit,
TIPS breakevens, munis, preferreds, converts, MBS.  Structures: curve steepener/flattener,
duration-neutral credit RV, bullet-vs-barbell convexity, breakeven, muni ratio, preferred and
convert residuals, month-end index-extension flow.

THE THREE GATES, IN ORDER
=========================
G0 MECHANISM.  Every formula below carries a one-sentence causal WHY naming who is forced to
   trade or what friction pays.  A formula with no mechanism is not in the list at all.  The
   mechanism also fixes the SIGN ex ante: every formula is written so that a POSITIVE t-stat
   is the mechanism working.  A negative t-stat is therefore a failure, not a sign flip to be
   harvested -- the sign is pre-registered, not fitted.

G1 LAG-KILL.  Positions are indexed so that W[t] (held over day t, earning close(t-1)->close(t))
   depends only on data through close(t-L).  L=1 is the scored BASE (see close t-1, be in the
   position for day t).  L=2 is the LAG-KILL.  L=0 is computed too, purely as a diagnostic:
   a formula that is large at L=0 and gone at L=1 was reading the same bar it trades.

G2 STATISTICS.  Every scoring decision uses the DESIGN window only.  The HELDOUT window is
   unreachable from --stage design (the loader refuses to return it).  N formulas is reported,
   the naive pooled bar sqrt(2 ln N) in SE units is reported, and because these formulas share
   legs and are heavily cross-correlated a stationary block bootstrap of the demeaned daily
   net PnL -- same day indices across all configs, so the correlation survives -- gives the
   empirical max-|t| null as well.  The bar is the LARGER of the two.

COSTS.  Every formula is market-neutral RV and pays BOTH legs.  Per-symbol half-spread comes
   from a liquidity tier on measured median dollar volume (PROXY, not a quote measurement --
   said out loud, and every survivor gets a break-even half-spread reported next to it).
   Plus 0.15 bp/turnover SEC 31 + FINRA TAF.  Plus borrow on the SHORT notional every calendar
   day: 0.33 %/yr for names the traded account's own /v2/assets screen calls easy-to-borrow,
   1.00 %/yr flagged UNSCREENED for the rest, and the unscreened short share is reported next
   to the Sharpe rather than netted into it.

DATA.  Yahoo daily ADJUSTED close = total return (for a bond ETF most of the return IS the
   coupon; a price series would fabricate a short-side edge in every high-yielding leg).
   FRED for yield/spread/breakeven/CPI levels.  ICE BofA OAS is licence-capped to 3 years on
   the free endpoint, so the credit-spread LEVEL signal uses Moody's BAA10Y / AAA10Y, which
   are public-domain and daily back to 1986.  That substitution is stated, not hidden.
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
KEY = "ratescredit"

DESIGN = ("2010-01-04", "2019-12-31")
HELDOUT = ("2020-01-02", "2026-08-15")

REG_BP_PER_TURNOVER = 0.15
BORROW_ETB = 0.0033          # B22G easy-to-borrow general-collateral median
BORROW_UNSCREENED = 0.0100   # flagged, not a measurement
BETA_WIN = 250
BETA_MIN = 180


# ------------------------------------------------------------------ panel

def _to_date(ts: int) -> str:
    return dt.datetime.utcfromtimestamp(ts + 43200).strftime("%Y-%m-%d")


class Panel:
    def __init__(self, end: str):
        px = json.loads((CACHE / "etf_daily.json").read_text())
        fred = json.loads((CACHE / "fred_daily.json").read_text())

        base = px["SPY"]
        dates = [_to_date(t) for t in base["t"]]
        dates = [d for d in dates if "2003-01-01" <= d <= end]
        self.dates = np.array(dates)
        pos = {d: i for i, d in enumerate(self.dates)}
        T = len(dates)

        self.syms = sorted(px)
        S = len(self.syms)
        self.sidx = {s: i for i, s in enumerate(self.syms)}
        self.R = np.full((T, S), np.nan)
        self.ADV = np.zeros(S)
        for s in self.syms:
            j = self.sidx[s]
            d = px[s]
            ac = np.array([np.nan if v is None else v for v in d["adjclose"]], float)
            vol = np.array([0.0 if v is None else v for v in (d["volume"] or [])], float)
            cl = np.array([np.nan if v is None else v for v in (d["close"] or [])], float)
            col = np.full(T, np.nan)
            prev = np.nan
            dv = []
            for k, ts in enumerate(d["t"]):
                dd = _to_date(ts)
                i = pos.get(dd)
                if i is None:
                    continue
                v = ac[k]
                if np.isfinite(v) and np.isfinite(prev) and prev > 0:
                    col[i] = v / prev - 1.0
                if np.isfinite(v):
                    prev = v
                if k < len(vol) and k < len(cl) and np.isfinite(cl[k]):
                    dv.append(vol[k] * cl[k])
            self.R[:, j] = col
            self.ADV[j] = float(np.median(dv)) if dv else 0.0

        # calendar day gaps, for borrow accrual
        dd = [dt.date.fromisoformat(x) for x in self.dates]
        self.caldays = np.array([1.0] + [(dd[i] - dd[i - 1]).days for i in range(1, T)])
        self.month = np.array([int(x[5:7]) for x in self.dates])
        self.year = np.array([int(x[:4]) for x in self.dates])
        ym = self.year * 100 + self.month
        self.bdom = np.zeros(T, int)      # 1-based business day of month
        self.bdom_r = np.zeros(T, int)    # 1-based from the END of the month
        for m in np.unique(ym):
            ix = np.where(ym == m)[0]
            self.bdom[ix] = np.arange(1, len(ix) + 1)
            self.bdom_r[ix] = np.arange(len(ix), 0, -1)

        # FRED, forward-filled onto trading days with a 7-calendar-day staleness cap
        self.F = {}
        for sid, series in fred.items():
            arr = np.full(T, np.nan)
            keys = sorted(series)
            kv = [(k, series[k]) for k in keys]
            p = 0
            last_d, last_v = None, np.nan
            for i, d in enumerate(self.dates):
                while p < len(kv) and kv[p][0] <= d:
                    last_d, last_v = kv[p]
                    p += 1
                if last_d is not None and (dt.date.fromisoformat(d)
                                           - dt.date.fromisoformat(last_d)).days <= 7:
                    arr[i] = last_v
            self.F[sid] = arr
        self.cpi = {k: v for k, v in fred["CPIAUCNS"].items()}

        # half-spread proxy by liquidity tier on median dollar volume
        self.hs_bp = np.zeros(S)
        for s in self.syms:
            a = self.ADV[self.sidx[s]]
            self.hs_bp[self.sidx[s]] = (1.0 if a > 500e6 else 1.5 if a > 100e6 else
                                        3.0 if a > 20e6 else 5.0 if a > 5e6 else 10.0)
        # borrow screen from the traded account's own /v2/assets answer
        scr = {}
        p = ROOT / "research" / "data" / "rv_cache" / "borrow_screen.json"
        if p.exists():
            scr = json.loads(p.read_text())
        self.borrow = np.zeros(S)
        self.unscreened = np.zeros(S, bool)
        for s in self.syms:
            j = self.sidx[s]
            rec = scr.get(s)
            if rec and rec.get("easy_to_borrow") and rec.get("shortable"):
                self.borrow[j] = BORROW_ETB
            else:
                self.borrow[j] = BORROW_UNSCREENED
                self.unscreened[j] = True

    def r(self, s: str) -> np.ndarray:
        return self.R[:, self.sidx[s]]

    def mask(self, lo: str, hi: str) -> np.ndarray:
        return (self.dates >= lo) & (self.dates <= hi)


# ------------------------------------------------------------------ rolling primitives

def _pref(a: np.ndarray) -> np.ndarray:
    return np.concatenate([[0.0], np.cumsum(a)])


def _win(p: np.ndarray, w: int) -> np.ndarray:
    """sum over the window (t-w, t] inclusive of t, indexed by t."""
    T = len(p) - 1
    idx = np.arange(1, T + 1)
    lo = np.maximum(idx - w, 0)
    return p[idx] - p[lo]


def roll_beta1(y: np.ndarray, x: np.ndarray, w: int = BETA_WIN) -> np.ndarray:
    """beta[t] from OLS of y on x over (t-w, t], inclusive of t."""
    m = np.isfinite(y) & np.isfinite(x)
    ys, xs = np.where(m, y, 0.0), np.where(m, x, 0.0)
    n = _win(_pref(m.astype(float)), w)
    sx, sy = _win(_pref(xs), w), _win(_pref(ys), w)
    sxx, sxy = _win(_pref(xs * xs), w), _win(_pref(xs * ys), w)
    nn = np.maximum(n, 1.0)
    cov, var = sxy - sx * sy / nn, sxx - sx * sx / nn
    out = np.where((n >= BETA_MIN) & (var > 0), cov / np.where(var > 0, var, 1.0), np.nan)
    return out


def roll_beta2(y, x1, x2, w: int = BETA_WIN):
    m = np.isfinite(y) & np.isfinite(x1) & np.isfinite(x2)
    ys = np.where(m, y, 0.0)
    a, b = np.where(m, x1, 0.0), np.where(m, x2, 0.0)
    n = _win(_pref(m.astype(float)), w)
    sa, sb, sy = _win(_pref(a), w), _win(_pref(b), w), _win(_pref(ys), w)
    saa, sbb, sab = _win(_pref(a * a), w), _win(_pref(b * b), w), _win(_pref(a * b), w)
    say, sby = _win(_pref(a * ys), w), _win(_pref(b * ys), w)
    nn = np.maximum(n, 1.0)
    Caa, Cbb, Cab = saa - sa * sa / nn, sbb - sb * sb / nn, sab - sa * sb / nn
    Cay, Cby = say - sa * sy / nn, sby - sb * sy / nn
    det = Caa * Cbb - Cab * Cab
    ok = (n >= BETA_MIN) & (np.abs(det) > 1e-18)
    d = np.where(ok, det, 1.0)
    b1 = np.where(ok, (Cbb * Cay - Cab * Cby) / d, np.nan)
    b2 = np.where(ok, (Caa * Cby - Cab * Cay) / d, np.nan)
    return b1, b2


def roll_z(x: np.ndarray, w: int) -> np.ndarray:
    m = np.isfinite(x)
    xs = np.where(m, x, 0.0)
    n = _win(_pref(m.astype(float)), w)
    s1, s2 = _win(_pref(xs), w), _win(_pref(xs * xs), w)
    nn = np.maximum(n, 1.0)
    mu = s1 / nn
    var = np.maximum(s2 / nn - mu * mu, 0.0)
    sd = np.sqrt(var)
    return np.where((n >= w * 0.6) & (sd > 0), (x - mu) / np.where(sd > 0, sd, 1.0), np.nan)


def roll_sum(x: np.ndarray, w: int) -> np.ndarray:
    xs = np.where(np.isfinite(x), x, 0.0)
    m = _win(_pref(np.isfinite(x).astype(float)), w)
    s = _win(_pref(xs), w)
    return np.where(m >= w * 0.6, s, np.nan)


def roll_std(x: np.ndarray, w: int) -> np.ndarray:
    m = np.isfinite(x)
    xs = np.where(m, x, 0.0)
    n = _win(_pref(m.astype(float)), w)
    s1, s2 = _win(_pref(xs), w), _win(_pref(xs * xs), w)
    nn = np.maximum(n, 1.0)
    return np.where(n >= w * 0.6, np.sqrt(np.maximum(s2 / nn - (s1 / nn) ** 2, 0.0)), np.nan)


def lag(x: np.ndarray, L: int) -> np.ndarray:
    if L == 0:
        return x
    out = np.full_like(x, np.nan, dtype=float)
    out[L:] = x[:-L]
    return out


# ------------------------------------------------------------------ leg builders

class Legs:
    """A daily basket: symbol -> weight array.  Normalised to gross 1 at use time."""

    def __init__(self, P: Panel):
        self.P = P
        self._cache: dict = {}

    def dn(self, a: str, b: str):
        """Long a, short trailing-beta units of b.  beta[t] known at close t."""
        k = ("dn", a, b)
        if k not in self._cache:
            beta = roll_beta1(self.P.r(a), self.P.r(b))
            self._cache[k] = ({a: np.ones(len(beta)), b: -beta}, beta)
        return self._cache[k][0]

    def resid2(self, a: str, b: str, c: str):
        k = ("r2", a, b, c)
        if k not in self._cache:
            b1, b2 = roll_beta2(self.P.r(a), self.P.r(b), self.P.r(c))
            self._cache[k] = {a: np.ones(len(b1)), b: -b1, c: -b2}
        return self._cache[k]

    def fly(self, belly: str, short_leg: str, long_leg: str):
        """Bullet vs barbell, duration-neutral by regression: long the belly, short the
        trailing-OLS combination of the two wings that reproduces its rate exposure."""
        return self.resid2(belly, short_leg, long_leg)

    def spread_ret(self, legs: dict) -> np.ndarray:
        """Realised return of the basket using weights known at close t-1 -- the series a
        signal at close t is allowed to have seen."""
        T = len(self.P.dates)
        out = np.zeros(T)
        ok = np.ones(T, bool)
        gross = np.zeros(T)
        for s, w in legs.items():
            wl = lag(w, 1)
            gross += np.abs(wl)
            ok &= np.isfinite(wl)
        gross = np.where(gross > 0, gross, np.nan)
        for s, w in legs.items():
            wl = lag(w, 1) / gross
            r = self.P.r(s)
            out += np.where(np.isfinite(wl) & np.isfinite(r), wl * r, 0.0)
            ok &= np.isfinite(r)
        return np.where(ok, out, np.nan)


# ------------------------------------------------------------------ formula table

def build_formulas(P: Panel, L: "Legs") -> list[dict]:
    r = P.r
    F = P.F
    T = len(P.dates)
    ones = np.ones(T)
    zero = np.zeros(T)

    def sgn(x):
        return np.where(np.isfinite(x), np.sign(x), np.nan)

    def clipz(x, w=504):
        z = roll_z(x, w)
        return np.clip(z, -1.5, 1.5) / 1.5

    def mom(sr, n, skip=0):
        s = roll_sum(sr, n + skip) - (roll_sum(sr, skip) if skip else 0.0)
        return sgn(s)

    def cum_z(sr, n):
        """z-score of the n-day cumulative spread return against its own longer history."""
        c = roll_sum(sr, n)
        return roll_z(c, 504)

    # ---- month-of-year expanding seasonal (causal: prior COMPLETE months only) ----
    def expanding_month_seasonal(sr: np.ndarray, min_years: int = 4) -> np.ndarray:
        ym = P.year * 100 + P.month
        buckets = []                                   # (calendar month, last index, total)
        for k in np.unique(ym):
            ix = np.where(ym == k)[0]
            v = sr[ix]
            buckets.append((int(k % 100), int(ix[-1]), float(np.nansum(v))))
        buckets.sort(key=lambda b: b[1])
        out = np.full(T, np.nan)
        hist: dict[int, list[float]] = {m: [] for m in range(1, 13)}
        b = 0
        for i in range(T):
            while b < len(buckets) and buckets[b][1] < i:
                hist[buckets[b][0]].append(buckets[b][2])
                b += 1
            h = hist[int(P.month[i])]
            if len(h) >= min_years:
                s = float(np.mean(h))
                out[i] = np.sign(s) if s != 0 else 0.0
        return out

    # ---- mechanical NSA-CPI seasonal, 3-month accrual lag, expanding estimation ----
    def cpi_seasonal_signal(min_years: int = 5) -> np.ndarray:
        keys = sorted(P.cpi)
        rec = []                                       # (available_from, month, log change)
        for i in range(1, len(keys)):
            a, b = keys[i - 1], keys[i]
            avail = (dt.date.fromisoformat(b[:8] + "01")
                     + dt.timedelta(days=50)).isoformat()
            rec.append((avail, int(b[5:7]), float(np.log(P.cpi[b] / P.cpi[a]))))
        rec.sort()
        out = np.full(T, np.nan)
        by_m: dict[int, list[float]] = {m: [] for m in range(1, 13)}
        tot, cnt, p = 0.0, 0, 0
        for i in range(T):
            d = P.dates[i]
            while p < len(rec) and rec[p][0] <= d:
                _, mm, v = rec[p]
                by_m[mm].append(v)
                tot += v
                cnt += 1
                p += 1
            if cnt < min_years * 12:
                continue
            tgt = ((int(d[5:7]) - 3 - 1) % 12) + 1     # accrual lags CPI by ~3 months
            sel = by_m[tgt]
            if len(sel) < min_years:
                continue
            out[i] = np.sign(float(np.mean(sel)) - tot / cnt)
        return out

    fs: list[dict] = []

    def add(name, fam, mech, legs, g, need=()):
        fs.append({"name": name, "family": fam, "mechanism": mech,
                   "legs": legs, "g": g, "need": tuple(need)})

    # =============== A. CURVE / DURATION ===============
    A_MECH = ("The FOMC moves policy in deliberately gradual, pre-announced sequences and "
              "index-tracking bond funds cannot front-run their own benchmark, so the price of "
              "duration adjusts over quarters rather than instantly.")
    dn_dur = L.dn("TLT", "SHY")
    sr_dur = L.spread_ret(dn_dur)
    add("A1_curve_mom_21", "curve", A_MECH, dn_dur, mom(sr_dur, 21))
    add("A2_curve_mom_63", "curve", A_MECH, dn_dur, mom(sr_dur, 63))
    add("A3_curve_mom_126", "curve", A_MECH, dn_dur, mom(sr_dur, 126))
    add("A4_curve_mom_252s21", "curve", A_MECH, dn_dur, mom(sr_dur, 231, skip=21))
    add("A5_curve_rev_5", "curve",
        "Duration is a crowded macro trade held by leveraged accounts; a 5-day move that is "
        "large relative to its own history is disproportionately liquidation, not information, "
        "and liquidation reverses when the forced seller is done.",
        dn_dur, -sgn(cum_z(sr_dur, 5)))
    add("A6_curve_carry_slope", "curve",
        "A steep curve IS the term premium: it is the price the market is paying long-duration "
        "holders to absorb duration risk, so expected excess return on duration rises with it.",
        dn_dur, clipz(F["T10Y2Y"], 504))
    add("A7_curve_carry_3m10y", "curve",
        "Same term-premium mechanism measured against the actual financing rate (3m bill) "
        "rather than the 2y, so it is carry net of funding rather than a curve shape.",
        dn_dur, clipz(F["T10Y3M"], 504))
    fly = L.fly("IEF", "SHY", "TLT")
    sr_fly = L.spread_ret(fly)
    FLY_MECH = ("Mortgage servicers and GSEs are structurally SHORT convexity and must buy "
                "duration at the wings when rates move, so they pay a premium for convexity; "
                "a bullet-versus-barbell position is the other side of that forced hedge.")
    add("A8_fly_static", "curve", FLY_MECH, fly, ones)
    add("A9_fly_rev_21", "curve",
        "The belly of the curve is where both index demand and the 5y/7y auction supply "
        "concentrate; a temporary supply/demand imbalance there is arbitraged by dealers "
        "within weeks, so the fly mean-reverts.",
        fly, -sgn(cum_z(sr_fly, 21)))
    add("A10_fly_volcond", "curve",
        FLY_MECH + " The premium paid for convexity scales with realised rate volatility, so "
        "the short-convexity side is only worth holding when vol is not already elevated.",
        fly, -clipz(roll_std(r("TLT"), 21), 504))

    # =============== B. CREDIT ===============
    B_MECH = ("Corporate bonds trade by dealer appointment against a balance sheet that is "
              "regulatorily capped, so a credit shock is absorbed over days of inventory "
              "unwind rather than in one print, and the ETF that fronts that market inherits "
              "the underreaction.")
    hy = L.dn("HYG", "IEF")
    sr_hy = L.spread_ret(hy)
    ig = L.dn("LQD", "IEF")
    sr_ig = L.spread_ret(ig)
    add("B1_hy_mom_21", "credit", B_MECH, hy, mom(sr_hy, 21))
    add("B2_hy_mom_63", "credit", B_MECH, hy, mom(sr_hy, 63))
    add("B3_hy_rev_5", "credit",
        "High-yield mutual funds are open-ended against an illiquid asset; a redemption spike "
        "forces indiscriminate selling that overshoots and is bought back by dealers and "
        "crossover buyers within a fortnight.",
        hy, -sgn(cum_z(sr_hy, 5)))
    add("B4_hy_rev_10", "credit", "Same forced-redemption overshoot, two-week horizon.",
        hy, -sgn(cum_z(sr_hy, 10)))
    add("B5_hy_carry_baa", "credit",
        "The credit spread is compensation for default AND for the dealer balance sheet that "
        "must warehouse the bond; when spread is wide relative to its own history the second "
        "component -- which is not a default forecast -- is what is wide, and it is earned.",
        hy, clipz(F["BAA10Y"], 504))
    add("B6_ig_carry_baa", "credit", "Same balance-sheet-scarcity premium, investment grade.",
        ig, clipz(F["BAA10Y"], 504))
    add("B7_ig_mom_63", "credit", B_MECH, ig, mom(sr_ig, 63))
    add("B8_ig_rev_5", "credit",
        "IG funds face the same open-ended redemption mismatch as HY with a thinner buyer "
        "base per unit of notional; short-horizon moves overshoot and revert.",
        ig, -sgn(cum_z(sr_ig, 5)))
    hyig = {}
    for s, w in hy.items():
        hyig[s] = hyig.get(s, zero) + w
    for s, w in ig.items():
        hyig[s] = hyig.get(s, zero) - w
    add("B9_hyig_rel_carry", "credit",
        "When the Baa-Aaa gap is wide, the market is charging more per unit of credit risk in "
        "the risky tranche than the safe one; that differential is the balance-sheet premium "
        "and it is harvested by owning the risky leg against the safe one.",
        hyig, clipz(F["BAA10Y"] - F["AAA10Y"], 504))
    hyjnk = L.dn("HYG", "JNK")
    sr_hyjnk = L.spread_ret(hyjnk)
    add("B10_hygjnk_rev_20", "credit",
        "HYG and JNK track different high-yield indices with different authorised-participant "
        "sets, so an idiosyncratic flow into one pushes it off its own basket; creation and "
        "redemption arbitrage restores it but only at T+1 with a real basket to source.",
        hyjnk, -sgn(cum_z(sr_hyjnk, 20)), need=("HYG", "JNK"))
    lqdvcit = L.dn("LQD", "VCIT")
    add("B11_lqdvcit_rev_20", "credit",
        "Same authorised-participant friction between two IG ETFs whose baskets overlap but "
        "whose flows do not.",
        lqdvcit, -sgn(cum_z(L.spread_ret(lqdvcit), 20)), need=("LQD", "VCIT"))
    angl = L.resid2("ANGL", "HYG", "LQD")
    add("B12_angl_rev_20", "credit",
        "An investment-grade mandate is a hard constraint: when a bond is downgraded, IG funds "
        "MUST sell it regardless of price, and the fallen-angel buyer base is small, so the "
        "cheapening is forced rather than informational and it reverses.",
        angl, -sgn(cum_z(L.spread_ret(angl), 20)), need=("ANGL",))
    bkln = L.dn("BKLN", "HYG")
    add("B13_bkln_mom_5", "credit",
        "Leveraged loans settle T+20 and are marked off a weekly dealer poll, so the loan ETF's "
        "own basket is genuinely stale relative to high yield -- DECOY: this is exactly the "
        "shape the lag-kill test exists to destroy, and it is in the list to prove the test "
        "bites.",
        bkln, mom(L.spread_ret(bkln), 5), need=("BKLN",))
    emb = L.resid2("EMB", "IEF", "HYG")
    add("B14_emb_rev_20", "credit",
        "Dedicated EM-debt funds are a small, flow-driven holder base with no natural domestic "
        "buyer; a redemption wave moves price against a residual that duration and US credit "
        "cannot explain, and it reverts.",
        emb, -sgn(cum_z(L.spread_ret(emb), 20)), need=("EMB",))
    add("B15_hy_vixcond", "credit",
        "Credit risk premium is paid to whoever supplies balance sheet when balance sheet is "
        "scarce; equity-implied vol is the cheapest free observable of that scarcity, so the "
        "premium on the credit leg is highest right after vol has spiked.",
        hy, clipz(F["VIXCLS"], 504))

    # =============== C. TIPS / BREAKEVEN ===============
    be = L.dn("TIP", "IEF")
    sr_be = L.spread_ret(be)
    add("C1_be_seasonal_cpi", "tips",
        "TIPS principal accrues with NON-seasonally-adjusted CPI on a fixed ~3-month lag; the "
        "seasonal component of NSA CPI is large, mechanical and published, so the carry of a "
        "breakeven position is KNOWN in advance and the marginal TIPS holder (a real-money "
        "index fund) is not permitted to trade it away.",
        be, cpi_seasonal_signal(), need=("TIP",))
    add("C2_be_seasonal_emp", "tips",
        "Same mechanical NSA-CPI accrual seasonality, measured from the realised breakeven "
        "return by calendar month on prior complete years only, instead of from CPI itself.",
        be, expanding_month_seasonal(sr_be), need=("TIP",))
    add("C3_be_mom_63", "tips",
        "Inflation expectations are revised by committees on quarterly cycles and TIPS index "
        "funds rebalance monthly, so repricing of the breakeven is spread over months.",
        be, mom(sr_be, 63), need=("TIP",))
    add("C4_be_rev_10", "tips",
        "TIPS are the first thing a levered relative-value book liquidates because they are "
        "the least liquid Treasury instrument; a sharp breakeven move is disproportionately "
        "that liquidation and it retraces.",
        be, -sgn(cum_z(sr_be, 10)), need=("TIP",))
    add("C5_be_carry_z", "tips",
        "The breakeven is depressed below fair inflation by a TIPS illiquidity premium that is "
        "widest when balance sheet is scarce; buying the breakeven when it is low against its "
        "own history is being paid that premium.",
        be, -clipz(F["T10YIE"], 504), need=("TIP",))
    stlt = L.dn("STIP", "LTPZ")
    add("C6_be_front_seasonal", "tips",
        "The NSA-CPI accrual seasonality is the SAME dollar amount on a short TIPS as on a long "
        "one but a far larger fraction of its total return, so the front of the TIPS curve is "
        "where the mechanical seasonal actually shows up.",
        stlt, cpi_seasonal_signal(), need=("STIP", "LTPZ"))
    add("C7_be_liqcond", "tips",
        "The TIPS illiquidity premium WIDENS in stress -- the 2008 and 2020 breakeven "
        "collapses were funding events, not inflation forecasts -- so the breakeven is the "
        "wrong side to own while balance sheet is being withdrawn.",
        be, -clipz(F["VIXCLS"], 504), need=("TIP",))

    # =============== D. MUNI ===============
    muni = L.dn("MUB", "IEF")
    sr_muni = L.spread_ret(muni)
    add("D1_muni_seasonal_emp", "muni",
        "The municipal market is retail-dominated and its coupon, call and maturity dates are "
        "contractually clustered in January, June and July, so those months force a wall of "
        "reinvestment cash into a market whose new-issue supply is calendar-driven and does "
        "not move to meet it.",
        muni, expanding_month_seasonal(sr_muni), need=("MUB",))
    add("D2_muni_janjul", "muni",
        "The same contractual reinvestment cluster, stated as the raw calendar rule rather "
        "than estimated: long municipal risk in January and July, short it in the heavy "
        "September-October new-issue window.",
        muni, np.where(np.isin(P.month, [1, 7]), 1.0,
                       np.where(np.isin(P.month, [9, 10]), -1.0, 0.0)), need=("MUB",))
    add("D3_muni_rev_60", "muni",
        "The muni/Treasury ratio has a hard economic anchor -- the top marginal tax rate -- and "
        "when it moves far from it, taxable crossover buyers (insurers, foreign banks) step in, "
        "which is why the ratio reverts rather than drifts.",
        muni, -sgn(cum_z(sr_muni, 60)), need=("MUB",))
    add("D4_muni_mom_21", "muni",
        "Municipal fund flows are reported weekly and are the most autocorrelated flows in "
        "fixed income; a retail fund receiving money must buy into a market with no dealer "
        "inventory, and next week it receives more.",
        muni, mom(sr_muni, 21), need=("MUB",))
    add("D5_muni_mom_63", "muni", "Same flow-persistence mechanism, quarter horizon.",
        muni, mom(sr_muni, 63), need=("MUB",))
    hydmub = L.dn("HYD", "MUB")
    add("D6_hymuni_rev_20", "muni",
        "High-yield munis are held by a handful of funds against an essentially non-existent "
        "secondary market, so a single fund's flow moves the whole sector away from investment-"
        "grade munis and back.",
        hydmub, -sgn(cum_z(L.spread_ret(hydmub), 20)), need=("HYD",))

    # =============== E. PREFERRED / CONVERT ===============
    pff = L.resid2("PFF", "TLT", "HYG")
    sr_pff = L.spread_ret(pff)
    P_MECH = ("Preferred shares are retail instruments trading in small size on an exchange "
              "with no institutional market-maker of last resort; a retail flow shock moves "
              "the whole sector away from the duration and credit factors that price it.")
    add("E1_pff_rev_5", "pref", P_MECH, pff, -sgn(cum_z(sr_pff, 5)), need=("PFF",))
    add("E2_pff_rev_10", "pref", P_MECH, pff, -sgn(cum_z(sr_pff, 10)), need=("PFF",))
    add("E3_pff_mom_63", "pref",
        "Preferred issuance is a bank-capital decision made on quarterly cycles, so supply "
        "arrives in persistent waves that the retail buyer base absorbs slowly.",
        pff, mom(sr_pff, 63), need=("PFF",))
    pgxpff = L.dn("PGX", "PFF")
    add("E4_pgxpff_rev_10", "pref",
        "Two preferred ETFs over near-identical universes with different flows and different "
        "authorised participants; divergence is flow, not value.",
        pgxpff, -sgn(cum_z(L.spread_ret(pgxpff), 10)), need=("PGX", "PFF"))
    cwb = L.resid2("CWB", "SPY", "LQD")
    sr_cwb = L.spread_ret(cwb)
    C_MECH = ("Convertibles are warehoused by levered convertible-arbitrage funds; a margin "
              "call forces them to sell the bond and unwind the hedge at once, cheapening the "
              "convert against its own replicating portfolio until fresh capital arrives.")
    add("E5_cwb_rev_21", "convert", C_MECH, cwb, -sgn(cum_z(sr_cwb, 21)), need=("CWB",))
    add("E6_cwb_rev_63", "convert", C_MECH, cwb, -sgn(cum_z(sr_cwb, 63)), need=("CWB",))

    # =============== F. FORCED-DURATION CALENDAR ===============
    ME_MECH = ("Bond indices reconstitute on the last business day of the month: newly issued "
               "long-dated paper enters and the index duration EXTENDS, so every fund tracking "
               "it must buy duration on that date or take tracking error. The date is known, "
               "the direction is known, and the buyer has no discretion.")
    add("F1_me_extend_1", "flow", ME_MECH, dn_dur, (P.bdom_r <= 1).astype(float))
    add("F2_me_extend_2", "flow", ME_MECH, dn_dur, (P.bdom_r <= 2).astype(float))
    add("F3_me_extend_3", "flow", ME_MECH, dn_dur, (P.bdom_r <= 3).astype(float))
    add("F4_qe_extend_2", "flow",
        ME_MECH + " At quarter end corporate defined-benefit plans, which are structurally "
        "short duration against their liabilities, rebalance on top of it.",
        dn_dur, ((P.bdom_r <= 2) & np.isin(P.month, [3, 6, 9, 12])).astype(float))
    add("F5_me_unwind_first3", "flow",
        "The mirror of the extension: the forced buying is over, the liquidity providers who "
        "supplied duration into it need to get flat, and the first days of the month are when "
        "they do.",
        dn_dur, -(P.bdom <= 3).astype(float))
    add("F6_auction_concession", "flow",
        "Primary dealers are contractually obliged to bid at Treasury auctions and hedge what "
        "they are allotted, so the long end cheapens into the mid-month refunding and richens "
        "once the paper is placed.",
        dn_dur, np.where((P.bdom >= 10) & (P.bdom <= 13), 1.0,
                         np.where((P.bdom >= 5) & (P.bdom <= 8), -1.0, 0.0)))
    lqdshy = L.dn("LQD", "SHY")
    add("F7_me_extend_credit", "flow",
        ME_MECH + " The investment-grade corporate index extends on the same date and by more, "
        "because corporate issuance is skewed long.",
        lqdshy, (P.bdom_r <= 2).astype(float))

    # =============== G. MBS ===============
    mbs = L.resid2("MBB", "IEF", "SHY")
    sr_mbs = L.spread_ret(mbs)
    G_MECH = ("A mortgage pool is a bond with a short call the homeowner owns for free; the "
              "holder is paid a spread for that negative convexity, and since the Fed stopped "
              "buying, the private sector must be paid enough to absorb the whole coupon "
              "stack.")
    add("G1_mbs_carry", "mbs", G_MECH, mbs, ones, need=("MBB",))
    add("G2_mbs_volcond", "mbs",
        G_MECH + " The cost of the embedded short option scales with rate volatility, so the "
        "spread is only worth owning when realised rate vol is not already high.",
        mbs, -clipz(roll_std(r("IEF"), 21), 504), need=("MBB",))
    add("G3_mbs_rev_21", "mbs",
        "Mortgage originators hedge their pipeline mechanically and in size; that hedging "
        "pushes the basis around on a horizon set by lock periods, not by information.",
        mbs, -sgn(cum_z(sr_mbs, 21)), need=("MBB",))

    # =============== H. STALENESS DECOYS (expected to die at lag-kill) ===============
    def decoy(name, a, b, lead):
        add(name, "decoy",
            f"DECOY: {a} is priced off an illiquid basket and is expected to lag {lead}. If "
            "this scores, it is quote staleness, not an edge -- it is in the list so the "
            "lag-kill test has a known positive control.",
            L.dn(a, b), sgn(r(lead)), need=(a, b))

    decoy("H1_mub_follows_ief", "MUB", "IEF", "IEF")
    decoy("H2_pff_follows_hyg", "PFF", "HYG", "HYG")
    decoy("H3_bkln_follows_hyg", "BKLN", "HYG", "HYG")
    decoy("H4_hyd_follows_mub", "HYD", "MUB", "MUB")

    return fs


# ------------------------------------------------------------------ evaluation

def evaluate(P: Panel, f: dict, lo: str, hi: str, Lag: int) -> dict:
    T = len(P.dates)
    S = len(P.syms)
    legs = f["legs"]
    g = np.asarray(f["g"], float)
    gl = lag(g, Lag)

    W = np.zeros((T, S))
    gross = np.zeros(T)
    ok = np.isfinite(gl)
    for s, w in legs.items():
        wl = lag(np.asarray(w, float), Lag)
        gross += np.abs(np.nan_to_num(wl, nan=0.0))
        ok &= np.isfinite(wl)
    gross = np.where(gross > 1e-12, gross, np.nan)
    for s, w in legs.items():
        wl = lag(np.asarray(w, float), Lag) / gross
        W[:, P.sidx[s]] = np.where(np.isfinite(wl), wl, 0.0) * np.nan_to_num(gl, nan=0.0)
    for s in legs:
        ok &= np.isfinite(P.R[:, P.sidx[s]])
    W[~ok] = 0.0

    gross_pnl = np.nansum(W * np.nan_to_num(P.R, nan=0.0), axis=1)
    dW = np.abs(np.diff(W, axis=0, prepend=np.zeros((1, S))))
    cost_sp = dW @ ((P.hs_bp + REG_BP_PER_TURNOVER) / 1e4)
    shortn = np.maximum(-W, 0.0)
    cost_bw = (shortn @ P.borrow) * P.caldays / 365.0
    net = gross_pnl - cost_sp - cost_bw

    m = P.mask(lo, hi) & ok
    n = int(m.sum())
    if n < 250:
        return {"n": n, "insufficient": True}
    x = net[m]
    xg = gross_pnl[m]
    sd = float(x.std(ddof=1))
    t = float(x.mean() / sd * np.sqrt(n)) if sd > 0 else 0.0
    tg = float(xg.mean() / xg.std(ddof=1) * np.sqrt(n)) if xg.std(ddof=1) > 0 else 0.0
    ann = t / np.sqrt(n) * np.sqrt(252)
    turn = float(dW[m].sum(axis=1).mean())
    cost_total = float((cost_sp + cost_bw)[m].mean())
    # break-even half-spread multiplier: how much wider could every quote be before net=0
    be_mult = float(xg.mean() / max(cost_sp[m].mean(), 1e-15)) if cost_sp[m].mean() > 0 else np.inf
    un = float(np.nansum(shortn[m][:, P.unscreened]) / max(np.nansum(shortn[m]), 1e-12))
    return {"n": n, "t": t, "t_gross": tg, "ann_sharpe": float(ann),
            "mean_bp_day": float(x.mean() * 1e4), "gross_bp_day": float(xg.mean() * 1e4),
            "cost_bp_day": float(cost_total * 1e4), "turnover": turn,
            "breakeven_spread_mult": be_mult, "unscreened_short_share": un,
            "exposure_frac": float((np.abs(W[m]).sum(axis=1) > 1e-9).mean()),
            "pnl": net, "mask": m}


def bootstrap_maxt(pnls: list[np.ndarray], masks: list[np.ndarray], T: int,
                   n_boot: int = 2000, block: int = 21, seed: int = 20260820) -> float:
    """Stationary block bootstrap of demeaned daily net PnL with the SAME day indices across
    every config, so the (large) cross-config correlation is preserved in the null."""
    rng = np.random.default_rng(seed)
    X = np.zeros((T, len(pnls)))
    M = np.zeros((T, len(pnls)))
    for j, (p, m) in enumerate(zip(pnls, masks)):
        v = np.where(m, p, 0.0)
        mu = v[m].mean() if m.sum() else 0.0
        X[:, j] = np.where(m, v - mu, 0.0)
        M[:, j] = m.astype(float)
    idx_all = np.arange(T)
    nb = int(np.ceil(T / block))
    out = np.empty(n_boot)
    for b in range(n_boot):
        starts = rng.integers(0, T, size=nb)
        take = (starts[:, None] + np.arange(block)[None, :]).ravel()[:T] % T
        xb, mb = X[take], M[take]
        n = mb.sum(axis=0)
        mu = xb.sum(axis=0) / np.maximum(n, 1)
        var = (xb ** 2).sum(axis=0) / np.maximum(n, 1) - mu ** 2
        sd = np.sqrt(np.maximum(var, 1e-30))
        tt = np.where(n >= 250, mu / sd * np.sqrt(np.maximum(n, 1)), 0.0)
        out[b] = np.abs(tt).max()
    del idx_all
    return float(np.quantile(out, 0.95))


# ------------------------------------------------------------------ stages

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["inventory", "design", "holdout"], required=True)
    ap.add_argument("--boot", type=int, default=2000)
    a = ap.parse_args()

    if a.stage == "inventory":
        P = Panel(DESIGN[1])
        fs = build_formulas(P, Legs(P))
        inv = [{"name": f["name"], "family": f["family"], "mechanism": f["mechanism"],
                "legs": sorted(f["legs"])} for f in fs]
        (OUT / f"NEWTERR_{KEY}_INVENTORY.json").write_text(
            json.dumps({"n_formulas": len(inv),
                        "naive_bar_sqrt_2lnN": float(np.sqrt(2 * np.log(len(inv)))),
                        "formulas": inv}, indent=1))
        for f in inv:
            print(f"{f['name']:26s} {f['family']:8s} {'+'.join(f['legs'])}")
        print(f"N={len(inv)}  sqrt(2 ln N)={np.sqrt(2*np.log(len(inv))):.3f}")
        return

    end = DESIGN[1] if a.stage == "design" else HELDOUT[1]
    P = Panel(end)                      # design stage cannot even LOAD the holdout window
    Lg = Legs(P)
    fs = build_formulas(P, Lg)
    N = len(fs)
    lo, hi = DESIGN if a.stage == "design" else HELDOUT

    rows = []
    pnls, masks = [], []
    for f in fs:
        row = {"name": f["name"], "family": f["family"], "mechanism": f["mechanism"]}
        for Lag, tag in ((0, "L0_diag"), (1, "L1_base"), (2, "L2_lagkill")):
            e = evaluate(P, f, lo, hi, Lag)
            if e.get("insufficient"):
                row[tag] = {"insufficient": True, "n": e["n"]}
                continue
            if Lag == 1:
                pnls.append(e["pnl"])
                masks.append(e["mask"])
            row[tag] = {k: v for k, v in e.items() if k not in ("pnl", "mask")}
        rows.append(row)

    res = {"stage": a.stage, "window": [lo, hi], "n_formulas": N,
           "naive_bar_sqrt_2lnN": float(np.sqrt(2 * np.log(N))), "rows": rows}
    if pnls:
        res["bootstrap_max_abs_t_95"] = bootstrap_maxt(pnls, masks, len(P.dates), a.boot)
    p = OUT / f"NEWTERR_{KEY}_{a.stage}.json"
    p.write_text(json.dumps(res, indent=1, default=float))
    print(f"wrote {p}  N={N}  naive_bar={res['naive_bar_sqrt_2lnN']:.2f} "
          f"boot95={res.get('bootstrap_max_abs_t_95')}")

    order = sorted([r for r in rows if "t" in r.get("L1_base", {})],
                   key=lambda r: -r["L1_base"]["t"])
    print(f"{'name':26s} {'L0':>6s} {'L1':>6s} {'L2':>6s} {'annS':>6s} "
          f"{'gbp':>6s} {'cbp':>6s} {'tovr':>5s} {'n':>5s}")
    for r in order:
        b, l0, l2 = r["L1_base"], r.get("L0_diag", {}), r.get("L2_lagkill", {})
        print(f"{r['name']:26s} {l0.get('t', float('nan')):6.2f} {b['t']:6.2f} "
              f"{l2.get('t', float('nan')):6.2f} {b['ann_sharpe']:6.2f} "
              f"{b['gross_bp_day']:6.2f} {b['cost_bp_day']:6.2f} "
              f"{b['turnover']:5.2f} {b['n']:5d}")


if __name__ == "__main__":
    main()
