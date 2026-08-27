#!/usr/bin/env python3
"""INVENT_0825 -- theme: PERP FUNDING-SETTLEMENT-WINDOW micro-dynamics.

Harness rules (pre-committed):
  * every fill is at the OPEN of the bar AFTER the last bar used by the signal
    (never same-bar, never the close that produced the signal);
  * funding P&L is charged whenever a position is open across a stamp;
  * cost 5.5 bp/side (4.5 bp Binance USD-M VIP0 taker + 1.0 bp declared half
    spread), the repo convention; breakeven reported per formula;
  * rho1 bounce gate on the traded return series BEFORE any gross claim;
  * design window 2023-01-01..2024-12-31, held-out 2025-01-01..2026-08-16,
    frozen to disk before the held-out window is scored.
"""
import os, pickle, datetime as dt
import numpy as np

ROOT = "/home/anont/meme"
CACHE = f"{ROOT}/research/data/fund0825_cache"
T0 = int(dt.datetime(2023, 1, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
STEP = 300_000
COST_BP = 5.5          # per side
ANN_STAMP = np.sqrt(3 * 365.0)   # 3 funding stamps / day

# --------------------------------------------------------------------------- #


class Panel:
    def __init__(self):
        z = np.load(f"{CACHE}/panel5m.npz", allow_pickle=True)
        self.o = z["o"]; self.c = z["c"]; self.qv = z["qv"]
        self.tbq = z["tbq"]; self.oi = z["oi"]
        self.t = z["t"]; self.symbols = list(z["symbols"])
        self.S, self.NT = self.o.shape
        self.sidx = {s: i for i, s in enumerate(self.symbols)}
        self._events()

    def _events(self):
        rows = pickle.load(open(f"{CACHE}/funding.pkl", "rb"))
        # keep 8h-interval prints only: the calendar-known mechanical event
        by = {}
        for s, ts, iv, r in rows:
            if iv != 8.0 or s not in self.sidx:
                continue
            # funding prints carry a few ms of jitter -> snap to the nearest bar
            b = int(round((ts - T0) / STEP))
            if 0 <= b < self.NT and abs(ts - (T0 + b * STEP)) <= 60_000:
                by.setdefault(s, []).append((b, r))
        ev_s, ev_b, ev_r, ev_r1, ev_r2 = [], [], [], [], []
        for s, lst in by.items():
            lst.sort()
            for k in range(2, len(lst)):
                ev_s.append(self.sidx[s]); ev_b.append(lst[k][0])
                ev_r.append(lst[k][1]); ev_r1.append(lst[k - 1][1])
                ev_r2.append(lst[k - 2][1])
        o = np.argsort(np.array(ev_b, np.int64), kind="stable")
        self.ev_s = np.array(ev_s, np.int32)[o]
        self.ev_b = np.array(ev_b, np.int64)[o]
        self.ev_r = np.array(ev_r, np.float64)[o]      # rate settled AT this stamp
        self.ev_r1 = np.array(ev_r1, np.float64)[o]    # previous stamp's rate
        self.ev_r2 = np.array(ev_r2, np.float64)[o]
        # stamp-time grouping
        self.stamps = np.unique(self.ev_b)
        self.st_pos = {b: i for i, b in enumerate(self.stamps)}
        self.ev_g = np.array([self.st_pos[b] for b in self.ev_b], np.int32)
        # liquidity: trailing 7d quote volume ending at the bar BEFORE the stamp
        self.NS = len(self.stamps)


# ------------------------------- helpers ----------------------------------- #

def rho1(x):
    x = np.asarray(x, float); x = x[np.isfinite(x)]
    if x.size < 40:
        return np.nan
    x = x - x.mean(); d = float((x * x).sum())
    return float((x[1:] * x[:-1]).sum() / d) if d > 0 else np.nan


def sharpe(x, ann=ANN_STAMP):
    x = np.asarray(x, float); x = x[np.isfinite(x)]
    if x.size < 60 or x.std() == 0:
        return 0.0
    return float(x.mean() / x.std() * ann)


def tstat(x):
    x = np.asarray(x, float); x = x[np.isfinite(x)]
    if x.size < 60 or x.std() == 0:
        return 0.0
    return float(x.mean() / (x.std() / np.sqrt(x.size)))


def seg_ret(P, s, a, b):
    """open-to-open return, sym s, entry bar a, exit bar b (arrays)."""
    oa = P.o[s, a]; ob = P.o[s, b]
    with np.errstate(invalid="ignore", divide="ignore"):
        r = ob / oa - 1.0
    r[~np.isfinite(r)] = np.nan
    r[(oa <= 0) | (ob <= 0)] = np.nan
    return r.astype(np.float64)


def event_pnl(P, a, b, fund_cross):
    """per-event unit-long P&L (price + funding), independent of the weights."""
    r = seg_ret(P, P.ev_s, a, b)
    return r + np.where(fund_cross, -P.ev_r, 0.0)


def book_from(P, w, pv):
    """aggregate signed weights x per-event P&L into a per-stamp return series."""
    g = np.zeros(P.NS); tw = np.zeros(P.NS)
    ok = (w != 0) & np.isfinite(pv)
    if not ok.any():
        return g, tw
    gi = P.ev_g[ok]
    np.add.at(tw, gi, np.abs(w[ok]))
    np.add.at(g, gi, w[ok] * pv[ok])
    nz = tw > 0
    g[nz] /= tw[nz]
    tw[nz] = 1.0
    return g, tw


def book(P, mask, w, s, a, b, fund_cross):
    """Aggregate per-event weights into a per-stamp portfolio return series.

    mask  : bool, events used
    w     : signed weight per event (raw; normalised to sum|w|=1 per stamp)
    a, b  : entry / exit bar per event (already next-bar aligned)
    fund_cross : bool per event -- position open across the stamp
    returns gross_per_stamp, turnover_per_stamp (sum|w| ; round trip = 2x)
    """
    g = np.zeros(P.NS); tw = np.zeros(P.NS)
    idx = np.where(mask)[0]
    if idx.size == 0:
        return g, tw
    r = seg_ret(P, P.ev_s[idx], a[idx], b[idx])
    # funding P&L: a long pays the rate when rate > 0
    fp = np.where(fund_cross[idx], -P.ev_r[idx], 0.0)
    pnl = w[idx] * (r + fp)
    ok = np.isfinite(pnl)
    idx, wv, pnl = idx[ok], np.abs(w[idx][ok]), pnl[ok]
    gi = P.ev_g[idx]
    np.add.at(tw, gi, wv)
    np.add.at(g, gi, pnl)
    nz = tw > 0
    g[nz] /= tw[nz]
    tw[nz] = 1.0
    return g, tw


def evaluate(P, g, tw, cost_bp=COST_BP):
    cost = tw * 2.0 * cost_bp * 1e-4
    net = g - cost
    tot_g = float(np.nansum(g)); tot_c = float(np.nansum(cost))
    be = 1e4 * tot_g / (float(np.nansum(tw)) * 2.0) if np.nansum(tw) > 0 else 0.0
    return dict(sharpe_gross=sharpe(g), sharpe_net=sharpe(net),
                t_gross=tstat(g), t_net=tstat(net),
                mean_bp=float(np.nanmean(g[tw > 0]) * 1e4) if (tw > 0).any() else 0.0,
                n_stamps=int((tw > 0).sum()), breakeven_bp_side=float(be),
                rho1_pnl=rho1(g[tw > 0]),
                ann_gross_pct=float(np.nansum(g) / max(1, (tw > 0).sum()) * 1095 * 100),
                ann_net_pct=float(np.nansum(net) / max(1, (tw > 0).sum()) * 1095 * 100))


def window_mask(P, lo, hi):
    t0 = int(dt.datetime.fromisoformat(lo).replace(tzinfo=dt.timezone.utc).timestamp() * 1000)
    t1 = int(dt.datetime.fromisoformat(hi).replace(tzinfo=dt.timezone.utc).timestamp() * 1000)
    b0, b1 = (t0 - T0) // STEP, (t1 - T0) // STEP
    return (P.ev_b >= b0) & (P.ev_b < b1), (P.stamps >= b0) & (P.stamps < b1)
