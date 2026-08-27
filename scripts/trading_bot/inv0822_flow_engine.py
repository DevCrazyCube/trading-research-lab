#!/usr/bin/env python3
"""INVENT_0822 forced/mechanical-flow event engine.

One event = (kind, ticker, effective_date).  For an S&P index change the change is effective
BEFORE THE OPEN of the effective date ED, so every index tracker must execute in the CLOSING
AUCTION of the previous trading day.  That day is called R (the "rebalance close") and every
offset below is measured in trading days relative to R.

A formula is (event set, entry offset a, exit offset b, sign, hedge).  Return is the
close-to-close simple return of the stock minus the same-window return of a size-matched ETF
(SPY / MDY / IJR), signed.

Two headline numbers per formula:
  * mean abnormal return per event in bp, with a t-stat CLUSTERED BY EVENT DATE (index
    changes arrive in batches on the same date, so the naive cross-event t is inflated);
  * the annualised Sharpe of the daily equal-weight portfolio that actually holds the trades,
    counting idle days as zero return -- the fundable standalone number.
"""
from __future__ import annotations

import json
import math
import pathlib

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[2]
FLOW = ROOT / "research" / "data" / "inv0822_flow"
BARS = FLOW / "bars"

BENCH = {"SP500": "SPY", "SP400": "MDY", "SP600": "IJR", "IPO": "IWM", "SEC": "IWM"}


# ------------------------------------------------------------------ panel
class Panel:
    def __init__(self):
        self.px: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
        spy = np.load(BARS / "SPY.npz")
        self.cal = spy["d"].astype(np.int64)
        self.pos = {int(d): i for i, d in enumerate(self.cal)}

    def get(self, sym: str):
        """(close, dollar-volume) aligned onto the master calendar; NaN where absent."""
        if sym in self.px:
            return self.px[sym]
        p = BARS / f"{sym.replace('/', '_')}.npz"
        if not p.exists():
            self.px[sym] = None
            return None
        z = np.load(p)
        d = z["d"].astype(np.int64)
        if d.size < 30:
            self.px[sym] = None
            return None
        c = np.full(self.cal.size, np.nan, np.float64)
        dv = np.full(self.cal.size, np.nan, np.float64)
        idx = np.array([self.pos.get(int(x), -1) for x in d])
        keep = idx >= 0
        c[idx[keep]] = z["c"][keep]
        dv[idx[keep]] = z["c"][keep].astype(np.float64) * z["v"][keep].astype(np.float64)
        self.px[sym] = (c, dv)
        return self.px[sym]

    def day_index_on_or_after(self, yyyymmdd: int) -> int:
        i = int(np.searchsorted(self.cal, yyyymmdd, "left"))
        return i if i < self.cal.size else -1


def dstr_to_int(s: str) -> int:
    return int(s[:4] + s[5:7] + s[8:10])


# ------------------------------------------------------------------ evaluation
def event_returns(panel: Panel, events, a: int, b: int, sign: int,
                  hedged: bool = True, min_dv: float = 2e6):
    """Return (per-event abnormal returns, event R-dates, daily leg contributions).

    `a`,`b` are trading-day offsets from R (the rebalance close).  Position is opened at the
    close of R+a and closed at the close of R+b.
    """
    rets, rdays, legs = [], [], []
    for ev in events:
        sym, idx = ev["ticker"], ev["index"]
        sgn = int(ev.get("_sign", sign))
        got = panel.get(sym)
        if got is None:
            continue
        c, dv = got
        ted = panel.day_index_on_or_after(dstr_to_int(ev["date"]))
        if ted <= 0:
            continue
        R = ted - 1
        i0, i1 = R + a, R + b
        if i0 < 5 or i1 >= panel.cal.size or i1 <= i0:
            continue
        if not (np.isfinite(c[i0]) and np.isfinite(c[i1])):
            continue
        # liquidity screen on the 20 sessions BEFORE the entry (no lookahead)
        w = dv[max(0, i0 - 20):i0]
        w = w[np.isfinite(w)]
        if w.size < 10 or float(np.median(w)) < min_dv:
            continue
        r = c[i1] / c[i0] - 1.0
        if hedged:
            bc = panel.get(BENCH.get(idx, "SPY"))
            if bc is None:
                continue
            bcc = bc[0]
            if not (np.isfinite(bcc[i0]) and np.isfinite(bcc[i1])):
                continue
            r -= bcc[i1] / bcc[i0] - 1.0
        if not np.isfinite(r) or abs(r) > 3.0:
            continue
        rets.append(sgn * r)
        rdays.append(int(panel.cal[R]))
        # daily contributions for the portfolio series
        seg_s = c[i0:i1 + 1]
        seg_b = (panel.get(BENCH.get(idx, "SPY"))[0][i0:i1 + 1] if hedged else None)
        dr = seg_s[1:] / seg_s[:-1] - 1.0
        if hedged:
            dr = dr - (seg_b[1:] / seg_b[:-1] - 1.0)
        dr = np.where(np.isfinite(dr), dr, 0.0)
        legs.append((i0 + 1, sgn * dr))
    return np.array(rets), np.array(rdays), legs


def clustered_t(rets: np.ndarray, rdays: np.ndarray):
    """t-stat of the mean, clustering by event date (one observation per R-date)."""
    if rets.size < 8:
        return float("nan"), 0
    grp: dict[int, list] = {}
    for r, d in zip(rets, rdays):
        grp.setdefault(int(d), []).append(float(r))
    means = np.array([np.mean(v) for v in grp.values()])
    n = means.size
    if n < 5 or means.std(ddof=1) == 0:
        return float("nan"), n
    return float(means.mean() / (means.std(ddof=1) / math.sqrt(n))), n


def portfolio_series(legs, n_days: int):
    num = np.zeros(n_days)
    cnt = np.zeros(n_days)
    for start, dr in legs:
        k = min(dr.size, n_days - start)
        if k <= 0:
            continue
        num[start:start + k] += dr[:k]
        cnt[start:start + k] += 1.0
    out = np.zeros(n_days)
    m = cnt > 0
    out[m] = num[m] / cnt[m]
    return out, cnt


def sharpe(x: np.ndarray):
    x = x[np.isfinite(x)]
    if x.size < 50 or x.std(ddof=1) == 0:
        return float("nan")
    return float(x.mean() / x.std(ddof=1) * math.sqrt(252))


def evaluate(panel: Panel, events, a, b, sign, hedged=True, costs=(0.5, 3.0, 5.5)):
    rets, rdays, legs = event_returns(panel, events, a, b, sign, hedged)
    if rets.size == 0:
        return None
    t, nclust = clustered_t(rets, rdays)
    lo, hi = min(0, len(panel.cal)), len(panel.cal)
    ser, cnt = portfolio_series(legs, len(panel.cal))
    # trim to the span actually traded
    active = np.flatnonzero(cnt > 0)
    if active.size == 0:
        return None
    ser_tr = ser[active[0]:active[-1] + 1]
    mean_bp = float(rets.mean() * 1e4)
    # cost: 2 stock legs + 2 hedge legs (hedge charged 1 bp/side)
    net = {f"c{c}": mean_bp - 2 * c - (2 * 1.0 if hedged else 0.0) for c in costs}
    return {
        "n_events": int(rets.size), "n_dates": nclust,
        "mean_bp": round(mean_bp, 2),
        "median_bp": round(float(np.median(rets)) * 1e4, 2),
        "t_clustered": round(t, 3) if t == t else None,
        "hit_rate": round(float((rets > 0).mean()), 3),
        "sd_bp": round(float(rets.std(ddof=1)) * 1e4, 1) if rets.size > 2 else None,
        "sharpe_portfolio": round(sharpe(ser_tr), 3) if sharpe(ser_tr) == sharpe(ser_tr) else None,
        "pct_days_invested": round(float((cnt[active[0]:active[-1] + 1] > 0).mean()), 3),
        "net_bp": {k: round(v, 2) for k, v in net.items()},
        "first": min(rdays.tolist()), "last": max(rdays.tolist()),
    }
