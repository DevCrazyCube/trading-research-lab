#!/usr/bin/env python3
"""Consolidate the INVENT_0822 forced-flow design + held-out passes and the four decisive
diagnostics into one master JSON.  Re-runnable; reads only the cached npz panel."""
from __future__ import annotations

import json
import math
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from trading_bot.inv0822_flow_engine import (BENCH, FLOW, Panel,  # noqa: E402
                                             clustered_t, dstr_to_int)
from trading_bot.inv0822_flow_run import load_corp_events, load_events  # noqa: E402

OUT = pathlib.Path(__file__).resolve().parents[2] / "research" / "trading_bot"
DESIGN = ("2016-01-04", "2021-12-31")
HELDOUT = ("2022-01-01", "2026-08-14")


def _daily(panel, e, lo_off, hi_off, bench):
    g = panel.get(e["ticker"])
    if g is None:
        return None
    c, dv = g
    t0 = panel.day_index_on_or_after(dstr_to_int(e["date"]))
    if t0 <= 0:
        return None
    return c, dv, t0


def flow_magnitude(panel, ev):
    out = {}
    for idx in ("SP500", "SP400", "SP600"):
        for side in ("add", "delete"):
            rel, usd = [], []
            for e in ev:
                if e["index"] != idx or e["side"] != side:
                    continue
                g = panel.get(e["ticker"])
                if g is None:
                    continue
                c, dv = g
                t0 = panel.day_index_on_or_after(dstr_to_int(e["date"]))
                if t0 <= 0:
                    continue
                R = t0 - 1
                base = dv[max(0, R - 40):max(0, R - 8)]
                base = base[np.isfinite(base)]
                if base.size < 15 or np.median(base) <= 0 or R >= dv.size:
                    continue
                if not np.isfinite(dv[R]):
                    continue
                rel.append(float(dv[R] / np.median(base)))
                usd.append(float(dv[R]))
            if rel:
                out[f"{idx}_{side}"] = {
                    "n": len(rel),
                    "median_rel_dollar_volume_at_R": round(float(np.median(rel)), 1),
                    "median_dollar_traded_at_R_musd": round(float(np.median(usd)) / 1e6, 0),
                }
    return out


def index_decomposition(panel, ev, lo, hi):
    sets = {"SP500add": ("SP500", "add"), "SP400add": ("SP400", "add"),
            "SP600add": ("SP600", "add"), "SP600del": ("SP600", "delete")}
    out = {}
    for name, (idx, side) in sets.items():
        pre, post, onR, postR, ds = [], [], [], [], []
        for e in ev:
            if e["index"] != idx or e["side"] != side or not (lo <= e["date"] <= hi):
                continue
            g = panel.get(e["ticker"])
            if g is None:
                continue
            c, dv = g
            t0 = panel.day_index_on_or_after(dstr_to_int(e["date"]))
            if t0 <= 0:
                continue
            R = t0 - 1
            if R - 6 < 5 or R + 5 >= len(panel.cal):
                continue
            b = panel.get(BENCH[idx])[0]
            seg, segb = c[R - 6:R + 6], b[R - 6:R + 6]
            if not np.all(np.isfinite(seg)) or not np.all(np.isfinite(segb)):
                continue
            dr = (seg[1:] / seg[:-1] - 1) - (segb[1:] / segb[:-1] - 1)
            if abs(float(np.sum(dr[:6]))) > 3:
                continue
            j = int(np.argmax(np.abs(dr[:5])))          # the presumed announcement day
            pre.append(float(np.sum(dr[:6])))
            post.append(float(np.sum(dr[j + 1:6])))
            onR.append(float(dr[5]))
            postR.append(float(np.sum(dr[6:11])))
            ds.append(int(panel.cal[R]))
        if len(pre) < 10:
            continue
        ds = np.array(ds)
        def cell(x):
            x = np.array(x)
            return {"mean_pct": round(100 * float(x.mean()), 2),
                    "t": round(clustered_t(x, ds)[0], 2)}
        out[name] = {"n": len(pre), "R_minus5_to_R": cell(pre),
                     "announcement_close_to_R": cell(post),
                     "on_the_R_flow_day": cell(onR), "R_to_R_plus5": cell(postR)}
    return out


def b5_day_profile(panel, sec, lo, hi, advmin, advmax=None):
    iwm = panel.get("IWM")[0]
    prof = {k: [] for k in range(-3, 7)}
    dts = []
    for e in sec:
        if not (lo <= e["date"] <= hi):
            continue
        g = panel.get(e["ticker"])
        if g is None:
            continue
        c, dv = g
        F = panel.day_index_on_or_after(dstr_to_int(e["date"]))
        if F < 30 or F + 7 >= len(panel.cal):
            continue
        w = dv[F - 21:F - 1]
        w = w[np.isfinite(w)]
        if w.size < 10:
            continue
        m = float(np.median(w))
        if m < advmin or (advmax and m >= advmax):
            continue
        seg, segb = c[F - 4:F + 7], iwm[F - 4:F + 7]
        if not np.all(np.isfinite(seg)):
            continue
        dr = (seg[1:] / seg[:-1] - 1) - (segb[1:] / segb[:-1] - 1)
        if float(np.max(np.abs(dr))) > 2:
            continue
        for i, k in enumerate(range(-3, 7)):
            prof[k].append(float(dr[i]))
        dts.append(int(panel.cal[F]))
    if len(dts) < 20:
        return None
    ds = np.array(dts)
    return {"n": len(dts),
            "per_day": {f"F{k:+d}": {"mean_pct": round(100 * float(np.mean(prof[k])), 2),
                                     "t": round(clustered_t(np.array(prof[k]), ds)[0], 2)}
                        for k in range(-3, 7)}}


def b5_windows(panel, sec, lo, hi):
    iwm = panel.get("IWM")[0]
    res = {}
    cases = {"entry_at_filing_close_F_to_F5": (0, 5, 2e6, None),
             "entry_one_day_later_F1_to_F6": (1, 6, 2e6, None),
             "entry_one_day_later_F1_to_F21": (1, 21, 2e6, None),
             "placebo_shift_plus60d": (0, 5, 2e6, None),
             "liquid_20M_F1_to_F6": (1, 6, 2e7, None),
             "liquid_100M_F1_to_F6": (1, 6, 1e8, None),
             "micro_2_to_20M_F1_to_F6": (1, 6, 2e6, 2e7)}
    for name, (a, b, amin, amax) in cases.items():
        shift = 60 if "placebo" in name else 0
        rs, ds = [], []
        for e in sec:
            if not (lo <= e["date"] <= hi):
                continue
            g = panel.get(e["ticker"])
            if g is None:
                continue
            c, dv = g
            t0 = panel.day_index_on_or_after(dstr_to_int(e["date"]))
            if t0 <= 0:
                continue
            F = t0 + shift
            i0, i1 = F + a, F + b
            if i0 < 25 or i1 >= len(panel.cal) or i1 <= i0:
                continue
            if not (np.isfinite(c[i0]) and np.isfinite(c[i1])):
                continue
            w = dv[max(0, i0 - 20):i0]
            w = w[np.isfinite(w)]
            if w.size < 10:
                continue
            m = float(np.median(w))
            if m < amin or (amax and m >= amax):
                continue
            r = (c[i1] / c[i0] - 1) - (iwm[i1] / iwm[i0] - 1)
            if not np.isfinite(r) or abs(r) > 3:
                continue
            rs.append(float(r))
            ds.append(int(panel.cal[F]))
        if len(rs) < 20:
            continue
        rs = np.array(rs)
        res[name] = {"n": rs.size, "mean_pct": round(100 * float(rs.mean()), 2),
                     "t": round(clustered_t(rs, np.array(ds))[0], 2)}
    return res


def main():
    panel = Panel()
    ev, promo, demote = load_events()
    lock, sec = load_corp_events()
    design = json.loads((OUT / "INVENT_0822_forcedflow_design.json").read_text())
    heldout = json.loads((OUT / "INVENT_0822_forcedflow_heldout.json").read_text())
    n = design["meta"]["n_formulas"]
    master = {
        "theme": "LARGE-GROSS forced / mechanical flow (index reconstitution, index migration, "
                 "IPO lockup expiry, secondary-offering pressure)",
        "date": "2026-08-22",
        "data": {
            "index_change_events_scraped": len(ev),
            "index_events_in_bar_window": sum(1 for e in ev if e["date"] >= "2016-01-05"),
            "edgar_424_filings": len(json.loads((FLOW / "raw" / "edgar_424.json").read_text())),
            "ipo_lockup_events": len(lock), "secondary_offering_events": len(sec),
            "migrations_up": len(promo), "migrations_down": len(demote),
            "symbols_with_bars": len(list((FLOW / "bars").glob("*.npz"))),
            "sources": ["Wikipedia: Historical components of the S&P 500 / List of S&P 400 / "
                        "List of S&P 600 constituent-change tables",
                        "SEC EDGAR full-index form.idx (424B4, 424B5) + company_tickers.json",
                        "Alpaca SIP daily bars, adjustment=all, delisted symbols included"],
        },
        "bars": {
            "n_formulas": n,
            "expected_max_t_null_one_sided": round(math.sqrt(2 * math.log(n)), 2),
            "expected_max_t_null_two_sided": round(math.sqrt(2 * math.log(2 * n)), 2),
            "pooled_cross_round_bar": 3.28,
        },
        "convention_check_volume_spike_at_R": flow_magnitude(panel, ev),
        "index_decomposition_design": index_decomposition(panel, ev, *DESIGN),
        "index_decomposition_heldout": index_decomposition(panel, ev, *HELDOUT),
        "b5_windows_design": b5_windows(panel, sec, "2015-01-01", "2021-12-31"),
        "b5_windows_heldout": b5_windows(panel, sec, *HELDOUT),
        "b5_day_profile_heldout_all": b5_day_profile(panel, sec, *HELDOUT, 2e6),
        "b5_day_profile_heldout_liquid20M": b5_day_profile(panel, sec, *HELDOUT, 2e7),
        "b5_day_profile_heldout_micro": b5_day_profile(panel, sec, *HELDOUT, 2e6, 2e7),
        "design": design["formulas"],
        "heldout": heldout["formulas"],
    }
    (OUT / "INVENT_0822_forcedflow.json").write_text(json.dumps(master, indent=1))
    print("wrote", OUT / "INVENT_0822_forcedflow.json")


if __name__ == "__main__":
    main()
