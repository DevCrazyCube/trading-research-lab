#!/usr/bin/env python3
"""INVENT_0822B -- futures/FX MECHANICAL-ROLL & SEASONAL structure.

Shared data + scoring library.

P&L RULE (inherited, non-negotiable, from SWEEP_futures_term_structure):
  Yahoo `X=F` continuous series are the front contract's SPLICED price -- the roll
  yield is deleted from them -- so they are SIGNAL INPUTS ONLY.  Every P&L leg here
  is either an ETF adjusted close or an FX SPOT rate (the tradable leg of an FX
  future over a <=5 day hold, where the carry term is ~0.3bp/day and is charged
  nowhere, i.e. conservatively ignored).
"""
from __future__ import annotations

import json
import pathlib
import numpy as np
import pandas as pd

ROOT = pathlib.Path("/home/anont/meme")
TS_RAW = ROOT / "research" / "data" / "ts_cache" / "raw"
B_RAW = ROOT / "research" / "data" / "inv0822b_cache" / "raw"

DESIGN = ("2007-01-01", "2018-12-31")
HOLDOUT = ("2019-01-01", "2026-08-21")

# ---- cost model: bp per side of notional traded --------------------------
COST_BP = {
    # FX futures legs (CME): 6E/6J tick 0.5bp + ~0.2bp commission -> conservative
    "EUR": 1.5, "JPY": 1.5, "GBP": 2.0, "AUD": 2.5, "CAD": 2.5, "CHF": 3.0,
    # bond ETFs
    "TLT": 1.5, "IEF": 2.0, "SHY": 2.0, "TLH": 4.0, "AGG": 2.0, "GOVT": 2.0,
    # commodity ETFs (inherited from round 1)
    "USO": 3.0, "UNG": 4.0, "UGA": 12.0, "GLD": 1.5, "SLV": 2.0, "CPER": 15.0,
    "CORN": 12.0, "WEAT": 12.0, "SOYB": 12.0, "CANE": 15.0, "DBC": 4.0,
    "DBE": 12.0, "DBA": 8.0, "GSG": 8.0, "USL": 10.0, "UNL": 15.0, "SPY": 1.0,
}


def _load_raw(path: pathlib.Path) -> pd.Series | None:
    try:
        d = json.loads(path.read_text())
        res = d["chart"]["result"][0]
        ts = res["timestamp"]
        q = res["indicators"]["quote"][0]
        close = q["close"]
        adj = None
        ind = res["indicators"]
        if "adjclose" in ind and ind["adjclose"]:
            adj = ind["adjclose"][0]["adjclose"]
        vals = adj if adj is not None else close
        idx = pd.to_datetime(pd.Series(ts), unit="s").dt.normalize()
        s = pd.Series(vals, index=idx, dtype="float64")
        s = s[~s.index.duplicated(keep="last")].sort_index().dropna()
        return s
    except Exception:
        return None


def load(sym: str) -> pd.Series:
    for base in (TS_RAW, B_RAW):
        p = base / (sym.replace("/", "_") + ".json")
        if p.exists():
            s = _load_raw(p)
            if s is not None and len(s) > 100:
                return s
    raise FileNotFoundError(sym)


# ---- FX: USD-per-foreign spot --------------------------------------------
FX_SPOT_SRC = {"EUR": ("EURUSD=X", False), "GBP": ("GBPUSD=X", False),
               "AUD": ("AUDUSD=X", False), "JPY": ("JPY=X", True),
               "CAD": ("CAD=X", True), "CHF": ("CHF=X", True)}
FX_EQ = {"EUR": "^GDAXI", "GBP": "^FTSE", "AUD": "^AXJO",
         "JPY": "^N225", "CAD": "^GSPTSE", "CHF": "^SSMI"}
CCYS = ["EUR", "JPY", "GBP", "AUD", "CAD", "CHF"]


def build_panel() -> dict:
    """One US-trading-day calendar; every series reindexed + ffilled onto it."""
    spy = load("SPY")
    cal = spy.index[(spy.index >= pd.Timestamp("2003-01-01"))]

    px = {}
    for c, (sym, inv) in FX_SPOT_SRC.items():
        s = load(sym).reindex(cal).ffill()
        px[c] = (1.0 / s) if inv else s
    for c, sym in FX_EQ.items():
        px["EQ_" + c] = load(sym).reindex(cal).ffill()
    px["EQ_US"] = spy.reindex(cal).ffill()
    px["EQ_USidx"] = load("^GSPC").reindex(cal).ffill()
    for sym in ["TLT", "IEF", "SHY", "TLH", "AGG", "GOVT", "USO", "UNG", "UGA",
                "GLD", "SLV", "CPER", "CORN", "WEAT", "SOYB", "CANE", "DBC",
                "DBE", "DBA", "GSG", "USL", "UNL", "SPY"]:
        try:
            px[sym] = load(sym).reindex(cal).ffill()
        except FileNotFoundError:
            pass
    P = pd.DataFrame(px).sort_index()

    cal_df = pd.DataFrame(index=P.index)
    ym = P.index.to_period("M")
    cal_df["ym"] = ym
    g = pd.Series(np.arange(len(P.index)), index=P.index).groupby(ym)
    cal_df["bd_start"] = g.cumcount() + 1
    cal_df["bd_end"] = g.transform(lambda x: len(x)) - g.cumcount()
    cal_df["month"] = P.index.month
    cal_df["day"] = P.index.day
    cal_df["year"] = P.index.year
    return {"P": P, "cal": cal_df}


def logret(P: pd.DataFrame, cols) -> pd.DataFrame:
    return np.log(P[cols]).diff()


# ---- scoring --------------------------------------------------------------
def score(W: pd.DataFrame, R: pd.DataFrame, costs: np.ndarray,
          lo: str, hi: str) -> dict:
    """W[t] = weight HELD over day t (set from info through t-1). Sign-agnostic."""
    idx = W.index
    m = (idx >= pd.Timestamp(lo)) & (idx <= pd.Timestamp(hi))
    Wm = W.loc[m].fillna(0.0)
    Rm = R.loc[m, W.columns].fillna(0.0)
    gross = (Wm.values * Rm.values).sum(axis=1)
    dW = np.abs(np.diff(np.vstack([np.zeros(Wm.shape[1]), Wm.values]), axis=0))
    cost = (dW * (costs / 1e4)).sum(axis=1)
    net = gross - cost
    n = len(net)
    if n < 250 or net.std() == 0:
        return {"n": n, "sr_net": 0.0, "sr_gross": 0.0, "bad": True}
    sr_g = gross.mean() / gross.std() * np.sqrt(252) if gross.std() > 0 else 0.0
    sr_n = net.mean() / net.std() * np.sqrt(252)
    # sign-agnostic: costs are identical under W -> -W
    net_neg = -gross - cost
    sr_n_neg = net_neg.mean() / net_neg.std() * np.sqrt(252) if net_neg.std() > 0 else 0.0
    sgn = 1 if sr_n >= sr_n_neg else -1
    best = max(sr_n, sr_n_neg)
    ser = net if sgn == 1 else net_neg
    eq = np.cumsum(ser)
    dd = float((eq - np.maximum.accumulate(eq)).min())
    return {
        "n": int(n), "yrs": round(n / 252.0, 2), "sign": sgn,
        "sr_net": round(float(best), 4),
        "sr_gross": round(float(sgn * sr_g), 4),
        "ann_ret": round(float(ser.mean() * 252), 5),
        "vol": round(float(ser.std() * np.sqrt(252)), 5),
        "cost_yr": round(float(cost.mean() * 252), 5),
        "maxdd": round(dd, 4),
        "t": round(float(best * np.sqrt(n / 252.0)), 3),
        "turn_yr": round(float(dW.sum(axis=1).mean() * 252), 3),
        "days_on": int((np.abs(Wm.values).sum(axis=1) > 1e-12).sum()),
        "bad": False,
    }


def net_series(W, R, costs, lo, hi):
    idx = W.index
    m = (idx >= pd.Timestamp(lo)) & (idx <= pd.Timestamp(hi))
    Wm = W.loc[m].fillna(0.0)
    Rm = R.loc[m, W.columns].fillna(0.0)
    gross = (Wm.values * Rm.values).sum(axis=1)
    dW = np.abs(np.diff(np.vstack([np.zeros(Wm.shape[1]), Wm.values]), axis=0))
    cost = (dW * (costs / 1e4)).sum(axis=1)
    return gross, cost
