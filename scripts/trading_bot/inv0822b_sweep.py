#!/usr/bin/env python3
"""INVENT_0822B sweep: MECHANICAL, CALENDAR-KNOWN FLOW in futures/FX.

Four families, none of which the two earlier futures term-structure sweeps
(98 formulas, both noise) touched:

  P  FX month-end hedge-rebalancing flow, signed by the month's relative
     equity performance.  Mechanism: a USD investor holding FX-hedged foreign
     equities must resize the hedge at month end; if the foreign market rose,
     the hedge notional rises and the foreign currency is SOLD into the fix.
     Calendar-known (last business day / WMR 4pm), cross-sectional, mechanical.

  Q  Month-end bond-index duration extension.  Mechanism: the Bloomberg US
     Agg/Treasury indices rebalance on the last calendar day; new issuance
     enters and index duration EXTENDS, so index trackers must buy duration on
     that day.  Larger in quarterly-refunding months (Feb/May/Aug/Nov).

  R  Commodity-index roll window, cross-sectionally weighted by published
     index weight.  Mechanism: S&P GSCI rolls on business days 5-9 and BCOM on
     6-10; the mandated flow into commodity i is proportional to its INDEX
     WEIGHT, which differs sharply between the two indices.  Earlier sweeps
     traded the roll window only in aggregate (DBC/GSG, USL/USO).

  S  Physical/regulatory calendar seasonals not already burned: the RVP
     gasoline spec transition, the EIA storage-cycle turn dates, the distillate
     build, the grain planting/harvest window pair.

Usage:
  python3 inv0822b_sweep.py design   -> design window only, writes _DESIGN.json
  python3 inv0822b_sweep.py nulls    -> both null distributions
  python3 inv0822b_sweep.py holdout  -> held-out window (run ONLY after freeze)
"""
from __future__ import annotations

import json
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "/home/anont/meme/scripts/trading_bot")
from inv0822b_lib import (ROOT, DESIGN, HOLDOUT, COST_BP, CCYS, build_panel,
                          score, net_series)

OUTDIR = ROOT / "research" / "trading_bot"

# published-ish index weights (S&P GSCI RPDW vs BCOM target), coarse but real
GSCI_W = {"USO": .24, "UGA": .06, "UNG": .03, "GLD": .04, "SLV": .005,
          "CPER": .04, "CORN": .04, "WEAT": .03, "SOYB": .03, "CANE": .015}
BCOM_W = {"USO": .08, "UGA": .03, "UNG": .08, "GLD": .15, "SLV": .05,
          "CPER": .06, "CORN": .06, "WEAT": .03, "SOYB": .06, "CANE": .03}
COMMOD = list(GSCI_W)


# ---------------------------------------------------------------- helpers
def zx(v: np.ndarray) -> np.ndarray:
    v = np.asarray(v, dtype=float)
    ok = np.isfinite(v)
    if ok.sum() < 3:
        return np.zeros_like(v)
    out = np.zeros_like(v)
    x = v[ok]
    s = x.std()
    out[ok] = (x - x.mean()) / s if s > 0 else 0.0
    return out


def norm_gross(w: np.ndarray, target: float = 1.0) -> np.ndarray:
    g = np.abs(w).sum()
    return w * (target / g) if g > 1e-12 else w


def tercile(v: np.ndarray, k: int = 2) -> np.ndarray:
    v = np.asarray(v, float)
    ok = np.isfinite(v)
    out = np.zeros_like(v)
    idx = np.argsort(np.where(ok, v, -np.inf))
    lo = idx[:k]
    hi = idx[-k:]
    out[hi] = 1.0 / (2 * k)
    out[lo] = -1.0 / (2 * k)
    return out


class Book:
    """Weight matrix builder over a fixed asset list."""

    def __init__(self, index, assets):
        self.assets = list(assets)
        self.W = pd.DataFrame(0.0, index=index, columns=self.assets)
        self.costs = np.array([COST_BP[a] for a in self.assets], float)


# --------------------------------------------------- family P: FX month-end
def fx_monthend(P, cal, hold_end, sig_lookback_extra=0, mode="rel_z",
                months=None, unwind=False, placebo_bd=None):
    """hold_end: tuple of bd_from_end values held (e.g. (1,2,3)).
    placebo_bd: if given, hold on these bd_from_START values instead.
    sig_lookback_extra: extra business days of gap between signal and entry."""
    bk = Book(P.index, CCYS)
    idx = P.index
    eq = {c: np.log(P["EQ_" + c]) for c in CCYS}
    eq_us = np.log(P["EQ_USidx"])
    pos = {d: i for i, d in enumerate(idx)}
    for ym, blk in cal.groupby("ym", sort=True):
        days = blk.index
        if len(days) < 12:
            continue
        if months is not None and days[0].month not in months:
            continue
        if placebo_bd is not None:
            held = [d for d in days if blk.loc[d, "bd_start"] in placebo_bd]
        elif unwind:
            nxt = cal[cal["ym"] == ym + 1]
            if len(nxt) < 6:
                continue
            held = [d for d in nxt.index if nxt.loc[d, "bd_start"] in hold_end]
        else:
            held = [d for d in days if blk.loc[d, "bd_end"] in hold_end]
        if not held:
            continue
        entry = min(held)
        i0 = pos[entry] - 1 - sig_lookback_extra
        if i0 < 1:
            continue
        sig_day = idx[i0]
        m0 = pos[days[0]] - 1           # last day of previous month
        if m0 < 1:
            continue
        base = idx[m0]
        rel = []
        for c in CCYS:
            r_for = eq[c].get(sig_day, np.nan) - eq[c].get(base, np.nan)
            r_us = eq_us.get(sig_day, np.nan) - eq_us.get(base, np.nan)
            if mode == "abs":
                rel.append(r_for)   # NOTE: with XS z-scoring this is identical to
                                    # "rel"; mode "ts_sign" below is the non-degenerate
                                    # per-currency time-series version
            elif mode == "usd_terms":
                fx = np.log(P[c])
                rel.append((r_for + fx.get(sig_day, np.nan) - fx.get(base, np.nan)) - r_us)
            else:
                rel.append(r_for - r_us)
        rel = np.array(rel, float)
        if not np.isfinite(rel).all():
            continue
        if mode == "tercile":
            w = -tercile(zx(rel))
        elif mode == "sign":
            w = -np.sign(zx(rel)) / len(CCYS)
        elif mode == "ts_sign":
            w = -np.sign(rel) / len(CCYS)   # per-currency time-series, NOT cross-sectional
        elif mode == "dollar":
            w = -np.sign(np.nanmean(rel)) * np.ones(len(CCYS)) / len(CCYS)
        elif mode == "flat":
            w = np.ones(len(CCYS)) / len(CCYS)
        else:
            w = norm_gross(-zx(rel))
        if unwind:
            w = -w
        for d in held:
            bk.W.loc[d, CCYS] = w
    return bk


# ---------------------------------------------- family Q: bond month-end
def bond_calendar(P, cal, legs, hold, from_end=True, months=None,
                  sign_by=None, flip=False):
    bk = Book(P.index, [l[0] for l in legs])
    col = "bd_end" if from_end else "bd_start"
    mask = cal[col].isin(hold)
    if months is not None:
        mask &= cal["month"].isin(months)
    lr = np.log(P["TLT"]).diff()
    idx = P.index
    pos = {d: i for i, d in enumerate(idx)}
    for d in idx[mask.values]:
        s = 1.0
        if sign_by == "month_bond_ret":
            blk = cal[cal["ym"] == cal.loc[d, "ym"]]
            i0 = pos[blk.index[0]] - 1
            if i0 < 1:
                continue
            r = np.log(P["TLT"]).iloc[pos[d] - 1] - np.log(P["TLT"]).iloc[i0]
            if not np.isfinite(r):
                continue
            s = -np.sign(r)
        if flip:
            s = -s
        for name, wt in legs:
            bk.W.loc[d, name] = s * wt
    return bk


# ---------------------------------------- family R: index roll window (XS)
def roll_window(P, cal, bd_range, weight_map, universe=None, months=None,
                from_end=False):
    uni = universe or COMMOD
    uni = [u for u in uni if u in P.columns]
    bk = Book(P.index, uni)
    col = "bd_end" if from_end else "bd_start"
    mask = cal[col].isin(bd_range)
    if months is not None:
        mask &= cal["month"].isin(months)
    w = norm_gross(zx(np.array([weight_map[u] for u in uni], float)))
    for d in P.index[mask.values]:
        bk.W.loc[d, uni] = w
    return bk


# -------------------------------------------------- family S: seasonals
def date_window(P, cal, spec):
    """spec: list of (leg_weights dict, (m1,d1), (m2,d2))."""
    assets = sorted({a for lw, _, _ in spec for a in lw})
    assets = [a for a in assets if a in P.columns]
    bk = Book(P.index, assets)
    md = cal["month"].values * 100 + cal["day"].values
    for lw, (m1, d1), (m2, d2) in spec:
        a, b = m1 * 100 + d1, m2 * 100 + d2
        m = (md >= a) & (md <= b) if a <= b else ((md >= a) | (md <= b))
        for k, v in lw.items():
            if k in bk.W.columns:
                bk.W.loc[P.index[m], k] += v
    return bk


# ================================================================= formulas
def build_all(P, cal):
    F = {}
    # --- P: FX month-end hedge rebalancing ------------------------------
    F["P01_FXME_REL_Z_3D"] = (fx_monthend(P, cal, (1, 2, 3)),
        "XS z of -(foreign eq - US eq) month return, held last 3 bdays, 6 CME FX")
    F["P02_FXME_REL_Z_1D"] = (fx_monthend(P, cal, (1,)),
        "same, held last 1 bday only")
    F["P03_FXME_REL_Z_5D"] = (fx_monthend(P, cal, (1, 2, 3, 4, 5)),
        "same, held last 5 bdays")
    F["P04_FXME_TERCILE"] = (fx_monthend(P, cal, (1, 2, 3), mode="tercile"),
        "long bottom-2 / short top-2 relative equity performers, last 3 bdays")
    F["P05_FXME_SIGN"] = (fx_monthend(P, cal, (1, 2, 3), mode="sign"),
        "sign-only weights (equal risk), last 3 bdays")
    F["P06_FXME_TS_SIGN"] = (fx_monthend(P, cal, (1, 2, 3), mode="ts_sign"),
        "per-currency TIME-SERIES: short currency i if its own market rose this month "
        "(non-cross-sectional; the XS z-score version is identical to P01 by construction)")
    F["P07_FXME_USD_TERMS"] = (fx_monthend(P, cal, (1, 2, 3), mode="usd_terms"),
        "signed by foreign equity return in USD terms minus US (unhedged investor)")
    F["P08_FXME_DOLLAR"] = (fx_monthend(P, cal, (1, 2, 3), mode="dollar"),
        "aggregate dollar leg: all 6 currencies by the sign of average rel perf")
    F["P09_FXME_FLAT_CAL"] = (fx_monthend(P, cal, (1, 2, 3), mode="flat"),
        "unsigned month-end calendar dummy: long the 6-currency basket")
    F["P10_FXME_QTREND"] = (fx_monthend(P, cal, (1, 2, 3), months=(3, 6, 9, 12)),
        "P01 restricted to quarter-end months (larger rebalances)")
    F["P11_FXME_UNWIND"] = (fx_monthend(P, cal, (1, 2, 3), unwind=True),
        "flow unwind: opposite sign, held the first 3 bdays of the NEXT month")
    F["P12_FXME_GAP5"] = (fx_monthend(P, cal, (1, 2, 3), sig_lookback_extra=5),
        "MECHANISM CONTROL: identical, signal measured 5 extra bdays earlier")
    F["P13_FXME_PLACEBO_MID"] = (fx_monthend(P, cal, (1, 2, 3), placebo_bd=(10, 11, 12)),
        "WINDOW PLACEBO: identical signal, held mid-month instead of month-end")

    # --- Q: month-end bond index duration extension ----------------------
    F["Q01_BONDME_TLT_2D"] = (bond_calendar(P, cal, [("TLT", 1.0)], (1, 2)),
        "long TLT the last 2 bdays of the month (index duration extension)")
    F["Q02_BONDME_TLT_1D"] = (bond_calendar(P, cal, [("TLT", 1.0)], (1,)),
        "long TLT the last bday only")
    F["Q03_BONDME_TLT_3D"] = (bond_calendar(P, cal, [("TLT", 1.0)], (1, 2, 3)),
        "long TLT the last 3 bdays")
    F["Q04_BONDME_DURSPREAD"] = (bond_calendar(P, cal, [("TLT", 0.5), ("SHY", -0.5)], (1, 2)),
        "long TLT / short SHY (duration spread) the last 2 bdays")
    F["Q05_BONDME_REFUND"] = (bond_calendar(P, cal, [("TLT", 1.0)], (1, 2), months=(2, 5, 8, 11)),
        "Q01 restricted to quarterly-refunding months Feb/May/Aug/Nov")
    F["Q06_BONDME_QTR"] = (bond_calendar(P, cal, [("TLT", 1.0)], (1, 2), months=(3, 6, 9, 12)),
        "Q01 restricted to quarter-end months")
    F["Q07_BONDME_FADE"] = (bond_calendar(P, cal, [("TLT", 1.0)], (1, 2), from_end=False, flip=True),
        "fade: short TLT the first 2 bdays of the month")
    F["Q08_BONDME_IEF"] = (bond_calendar(P, cal, [("IEF", 1.0)], (1, 2)),
        "belly version: long IEF the last 2 bdays")
    F["Q09_BONDME_REBAL_SIGN"] = (bond_calendar(P, cal, [("TLT", 1.0)], (1, 2), sign_by="month_bond_ret"),
        "month-end rebalancing sign: -sign(month TLT return), last 2 bdays")
    F["Q10_BONDME_PLACEBO"] = (bond_calendar(P, cal, [("TLT", 1.0)], (12, 13), from_end=False),
        "WINDOW PLACEBO: long TLT on bdays 12-13 of the month")

    F["Q11_BONDME_TLH"] = (bond_calendar(P, cal, [("TLH", 1.0)], (1, 2)),
        "duration gradient: long TLH (10-20y) the last 2 bdays")
    F["Q12_BONDME_AGG"] = (bond_calendar(P, cal, [("AGG", 1.0)], (1, 2)),
        "duration gradient: long AGG (the actual index being rebalanced) last 2 bdays")
    F["Q13_BONDME_GOVT"] = (bond_calendar(P, cal, [("GOVT", 1.0)], (1, 2)),
        "duration gradient: long GOVT (broad Treasury) last 2 bdays")
    F["Q14_BONDME_SHY"] = (bond_calendar(P, cal, [("SHY", 1.0)], (1, 2)),
        "duration gradient FLOOR: long SHY (1-3y) last 2 bdays -- effect should be tiny")
    F["Q15_BONDME_SPY_CTRL"] = (bond_calendar(P, cal, [("SPY", 1.0)], (1, 2)),
        "ASSET CONTROL: long SPY the last 2 bdays (a different, equity, mechanism)")
    F["Q16_BONDME_TLT_4D"] = (bond_calendar(P, cal, [("TLT", 1.0)], (1, 2, 3, 4)),
        "long TLT the last 4 bdays")

    # --- R: index roll window, cross-sectional by index weight -----------
    diff_w = {k: GSCI_W[k] - BCOM_W[k] for k in COMMOD}
    F["R01_GSCIROLL_WZ"] = (roll_window(P, cal, (5, 6, 7, 8, 9), GSCI_W),
        "bd 5-9 (S&P GSCI roll): XS z of GSCI weight, long heavy / short light")
    F["R02_GSCIROLL_PRE"] = (roll_window(P, cal, (1, 2, 3, 4), GSCI_W),
        "same weights, bd 1-4 (front-run the roll)")
    F["R03_GSCIROLL_POST"] = (roll_window(P, cal, (10, 11, 12, 13, 14), GSCI_W),
        "same weights, bd 10-14 (fade after the roll clears)")
    F["R04_ROLL_WDIFF"] = (roll_window(P, cal, (5, 6, 7, 8, 9), diff_w),
        "bd 5-9: XS z of (GSCI weight - BCOM weight), the NET index pressure")
    F["R05_JANREWEIGHT"] = (roll_window(P, cal, (5, 6, 7, 8, 9), GSCI_W, months=(1,)),
        "January roll window only (annual reweight amplifies the mandated flow)")
    F["R06_ROLL_LIQUID"] = (roll_window(P, cal, (5, 6, 7, 8, 9), GSCI_W,
                                        universe=["USO", "UNG", "GLD", "SLV", "CORN", "WEAT"]),
        "bd 5-9 GSCI-weight XS restricted to the 6 cheapest-to-trade legs")
    F["R07_ROLL_PLACEBO"] = (roll_window(P, cal, (16, 17, 18, 19, 20), GSCI_W),
        "WINDOW PLACEBO: same weights on bd 16-20 (no index roll)")

    # --- S: physical / regulatory calendar seasonals ---------------------
    F["S01_RVP_SPEC"] = (date_window(P, cal, [
        ({"UGA": 0.5, "USO": -0.5}, (3, 15), (4, 30)),
        ({"UGA": -0.5, "USO": 0.5}, (9, 15), (10, 31))]),
        "RVP gasoline spec switch: long UGA/short USO 15Mar-30Apr, flipped 15Sep-31Oct")
    F["S02_NG_STORAGE_TURN"] = (date_window(P, cal, [
        ({"UNG": 1.0}, (10, 1), (11, 15)),
        ({"UNG": -1.0}, (2, 15), (3, 31))]),
        "EIA storage-cycle turns: long UNG 1Oct-15Nov, short UNG 15Feb-31Mar")
    F["S03_DISTILLATE_BUILD"] = (date_window(P, cal, [
        ({"DBE": 1.0}, (9, 15), (12, 15))]),
        "distillate/heating build: long DBE 15Sep-15Dec")
    F["S04_GRAIN_PLANT_HARVEST"] = (date_window(P, cal, [
        ({"CORN": 0.5, "SOYB": 0.5}, (2, 1), (6, 15)),
        ({"CORN": -0.5, "SOYB": -0.5}, (8, 15), (10, 15))]),
        "planting weather premium long 1Feb-15Jun; harvest pressure short 15Aug-15Oct")
    F["S05_GOLD_FESTIVAL_LEAD"] = (date_window(P, cal, [
        ({"GLD": 1.0}, (8, 15), (10, 15))]),
        "long GLD 15Aug-15Oct (physical restock lead into the Indian festival season)")
    F["S06_TURNOFYEAR_COMMOD"] = (date_window(P, cal, [
        ({"DBC": 1.0}, (12, 15), (1, 15))]),
        "long DBC 15Dec-15Jan (annual index reweight + tax-loss reversal)")
    return F


# =================================================================== driver
def run(window, tag):
    d = build_panel()
    P, cal = d["P"], d["cal"]
    R = np.log(P).diff()
    F = build_all(P, cal)
    rows = []
    for name, (bk, desc) in F.items():
        s = score(bk.W, R, bk.costs, *window)
        s["formula"] = name
        s["desc"] = desc
        s["group"] = name[0]
        rows.append(s)
    rows.sort(key=lambda r: -r["sr_net"])
    out = {"window": window, "n_formulas": len(rows),
           "analytic_bar_t": round(float(np.sqrt(2 * np.log(2 * len(rows)))), 3),
           "rows": rows}
    p = OUTDIR / f"INVENT_0822B_futroll_{tag}.json"
    p.write_text(json.dumps(out, indent=1))
    print(f"wrote {p}")
    hdr = f"{'formula':26s} {'grp':3s} {'sr_net':>7s} {'sr_gr':>7s} {'sgn':>3s} {'t':>6s} {'vol':>6s} {'cost/y':>7s} {'don':>5s}"
    print(hdr)
    for r in rows:
        print(f"{r['formula']:26s} {r['group']:3s} {r['sr_net']:7.3f} {r['sr_gross']:7.3f} "
              f"{r.get('sign',0):3d} {r.get('t',0):6.2f} {r.get('vol',0):6.3f} "
              f"{r.get('cost_yr',0):7.4f} {r.get('days_on',0):5d}")
    return out


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "design"
    if cmd == "design":
        run(DESIGN, "DESIGN")
    elif cmd == "holdout":
        run(HOLDOUT, "HOLDOUT")
    else:
        print("unknown", cmd)
