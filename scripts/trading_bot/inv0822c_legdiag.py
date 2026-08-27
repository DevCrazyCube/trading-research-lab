#!/usr/bin/env python3
"""INVENT_0822C -- leg-level bounce diagnostics for the two RV legs feeding the book.

ETFRV: the frozen leg computes z from the 15:45 log-spread AND fills at 15:45.
       Signal and fill share a price -> the R3 'shared-price measurement error'
       failure mode.  PLACEBO: keep the 15:45 signal, move the FILL to 15:50.
DUALCLASS: signal = today's raw close, fill = today's close.  Same shape.
       PLACEBO: one-day-gap re-entry (fill at t+1's close).
"""
from __future__ import annotations
import json, math, pathlib, statistics as st, sys, datetime as dt
from zoneinfo import ZoneInfo
import numpy as np

ROOT = pathlib.Path("/home/anont/meme")
ET = ZoneInfo("America/New_York")
sys.path.insert(0, str(ROOT))
from scripts.trading_bot.inv0822c_panel import (ETFRV_PAIRS, ETFRV_HS, SEC31,
                                                DC_PAIRS, DC_HS, DC_BORROW)


def prices(sym, minutes):
    z = np.load(ROOT / "research/data/rv_cache" / f"{sym}.npz")
    t = z["t"].astype("int64"); o = z["o"].astype(float); c = z["c"].astype(float)
    out = {m: {} for m in minutes}; close = {}
    for i in range(len(t)):
        d = dt.datetime.fromtimestamp(int(t[i]), ET)
        k = d.strftime("%Y-%m-%d"); hm = d.hour * 60 + d.minute
        if hm in out:
            out[hm][k] = o[i]
        if 15 * 60 + 30 <= hm <= 16 * 60:
            close[k] = c[i]
    return out, close


def etfrv(entry_min):
    M = [15 * 60 + 45, entry_min]
    P = {s: prices(s, M) for s in sorted({x for p in ETFRV_PAIRS for x in p})}
    per = {}
    for a, b in ETFRV_PAIRS:
        oa, ca = P[a]; ob, cb = P[b]
        sa, sb = oa[15 * 60 + 45], ob[15 * 60 + 45]
        ea, eb = oa[entry_min], ob[entry_min]
        days = sorted(set(sa) & set(sb) & set(ca) & set(cb) & set(ea) & set(eb))
        s = [math.log(sa[d] / sb[d]) for d in days]
        cost = (ETFRV_HS[a] + ETFRV_HS[b] + 2 * SEC31) * 1e-4
        for i in range(60, len(days)):
            w = s[i - 60:i]; mu = st.fmean(w); sd = st.pstdev(w)
            if sd <= 0:
                continue
            z = (s[i] - mu) / sd
            if abs(z) < 1.5:
                continue
            sgn = -1.0 if z > 0 else 1.0
            d = days[i]
            g = sgn * ((ca[d] / ea[d] - 1) - (cb[d] / eb[d] - 1))
            per.setdefault(d, []).append(g - cost)
    ds = sorted(per)
    x = np.array([st.fmean(per[d]) for d in ds])
    return x


def dualclass(gap):
    from scripts.t28_dualclass import dc_test as dc
    tr = []
    for a, b in DC_PAIRS:
        rows = dc.build((a, b), "2016-01-04", "2026-08-18")
        if len(rows) < 300:
            continue
        hs = (DC_HS.get(a, 5.0) + DC_HS.get(b, 5.0)) * 1e-4
        rt = 2 * hs + 2 * SEC31 * 1e-4
        pos = None; hist = []
        for i, r in enumerate(rows):
            if i > 0 and abs(r["s"] - rows[i - 1]["s"]) > 0.15:
                hist = []; pos = None
            if pos is not None:
                z = None
                if len(hist) >= 250:
                    mu = st.fmean(hist[-250:]); sd = st.pstdev(hist[-250:])
                    z = (r["s"] - mu) / sd if sd > 0 else 0.0
                held = i - pos["i"]
                if (z is not None and abs(z) <= 0.5) or held >= 20 or i == len(rows) - 1:
                    g = pos["sgn"] * ((r["pa"] / pos["pa"] - 1) - (r["pb"] / pos["pb"] - 1))
                    tr.append(g - rt - DC_BORROW * held / 252.0)
                    pos = None
            if pos is None and len(hist) >= 250:
                mu = st.fmean(hist[-250:]); sd = st.pstdev(hist[-250:])
                if sd > 0:
                    z = (r["s"] - mu) / sd
                    if abs(z) >= 2.0 and r["dv"] >= 1e6 and min(r["px_a"], r["px_b"]) >= 2.0:
                        j = i + gap
                        if j < len(rows):
                            pos = {"i": j, "sgn": -1 if z > 0 else 1,
                                   "pa": rows[j]["pa"], "pb": rows[j]["pb"]}
            hist.append(r["s"])
    return np.array(tr)


def rep(x, ppy, label):
    if len(x) < 10:
        return {"label": label, "n": len(x)}
    return {"label": label, "n": int(len(x)), "mean_bp": float(x.mean() * 1e4),
            "t": float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))),
            "ann_sharpe": float(x.mean() / x.std(ddof=1) * math.sqrt(ppy))}


def main():
    out = {}
    out["etfrv_fill_1545_FROZEN"] = rep(etfrv(15 * 60 + 45), 252, "signal & fill both 15:45")
    out["etfrv_fill_1550_PLACEBO"] = rep(etfrv(15 * 60 + 50), 252, "signal 15:45, fill 15:50")
    out["etfrv_fill_1555_PLACEBO"] = rep(etfrv(15 * 60 + 55), 252, "signal 15:45, fill 15:55")
    out["dualclass_gap0_FROZEN"] = rep(dualclass(0), 16, "fill at the signal close")
    out["dualclass_gap1_PLACEBO"] = rep(dualclass(1), 16, "one-day-gap re-entry")
    out["dualclass_gap2_PLACEBO"] = rep(dualclass(2), 16, "two-day-gap re-entry")
    (ROOT / "research/data/inv0822c_cache/legdiag.json").write_text(json.dumps(out, indent=1))
    for k, v in out.items():
        print("%-30s n=%5s mean_bp=%8s t=%6s SR=%6s" % (
            k, v.get("n"), round(v.get("mean_bp", 0), 3),
            round(v.get("t", 0), 2), round(v.get("ann_sharpe", 0), 2)))


if __name__ == "__main__":
    main()
