#!/usr/bin/env python3
"""INVENT-0823 gamma sweep: post-design diagnostics for whatever survived.

Run AFTER the design table exists. For each named cell:
  * single-name-only vs sector-ETF-only split (the "is it just one sub-pool?" test)
  * realised net beta of the book (the "beta wearing a costume" test)
  * one-day-gap re-entry placebo
  * residualised-on-past-return twin
  * mechanism check: does |net gamma| predict the next session's realised range?
Usage: invent0823_gex_diag.py CELL [CELL ...]      e.g. S6_SKEW_TILT '|day'
"""
import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from invent0823_gex_eval import (COSTS, DESIGN, HELDOUT, book, build_signals,
                                 load, returns, stats, turnover_of, xs_rank_norm)

ROOT = "/home/anont/meme"
SECTOR = set("XLF XLE XLK XLV XLI XLP XLU XLB XLRE XLC SMH IWM QQQ DIA EEM".split())


def sub(F, sig, rets, lo, hi, cell, cols):
    name, h = cell.split("|")
    days = np.array(F["_days"])
    win = (days >= lo) & (days <= hi)
    x = np.where(win[:, None], sig[name], np.nan)
    mask = np.zeros(x.shape[1], dtype=bool)
    mask[cols] = True
    x = np.where(mask[None, :], x, np.nan)
    w, pnl, act = book(x, rets[h])
    return stats(pnl, act, turnover_of(w, h))


def main():
    cells = sys.argv[1:]
    F = load()
    sig, ctrl = build_signals(F)
    rets = returns(F)
    unds = F["_unds"]
    single = [i for i, u in enumerate(unds) if u not in SECTOR]
    sect = [i for i, u in enumerate(unds) if u in SECTOR]
    out = {"cells": {}}

    # market proxy for the beta test: equal-weight universe return
    for cell in cells:
        name, h = cell.split("|")
        rec = {}
        for wname, (lo, hi) in (("design", DESIGN), ("heldout", HELDOUT)):
            days = np.array(F["_days"])
            win = (days >= lo) & (days <= hi)
            x = np.where(win[:, None], sig[name], np.nan)
            w, pnl, act = book(x, rets[h])
            base = stats(pnl, act, turnover_of(w, h))
            mkt = np.nanmean(np.where(np.isfinite(rets[h]), rets[h], np.nan), axis=1)
            m = act & np.isfinite(mkt)
            beta = float(np.polyfit(mkt[m], pnl[m], 1)[0]) if m.sum() > 30 else None
            hedged = pnl.copy()
            if beta is not None:
                hedged[m] = pnl[m] - beta * mkt[m]
            hs = stats(hedged, act & np.isfinite(mkt), turnover_of(w, h))
            gap = None
            gh = "gap" if h == "intraday" else "gap_day"
            wg, pg, ag = book(x, rets[gh])
            gap = stats(pg, ag, turnover_of(wg, h))
            cn = "R_" + name
            cs = None
            if cn in ctrl:
                xc = np.where(win[:, None], ctrl[cn], np.nan)
                wc, pc, ac = book(xc, rets[h])
                cs = stats(pc, ac, turnover_of(wc, h))
            rec[wname] = {
                "all": base,
                "single_names_only": sub(F, sig, rets, lo, hi, cell, single),
                "sector_etfs_only": sub(F, sig, rets, lo, hi, cell, sect),
                "beta_to_universe": beta,
                "beta_hedged": hs,
                "gap_placebo": gap,
                "resid_on_past_returns": cs,
            }
        out["cells"][cell] = rec

    # mechanism: does |net gamma| predict next-session realised range?
    S, hi_, lo_, c = F["S"], F["adj_h"], F["adj_l"], F["adj_c"]
    rng = np.full_like(c, np.nan)
    rng[:-1] = (hi_[1:] - lo_[1:]) / c[1:]
    g6 = np.abs(F["net_gex"] / F["gross_gex"])
    days = np.array(F["_days"])
    for wname, (a, b) in (("design", DESIGN), ("heldout", HELDOUT)):
        win = (days >= a) & (days <= b)
        gz = xs_rank_norm(np.where(win[:, None], g6, np.nan))
        rz = xs_rank_norm(np.where(win[:, None], rng, np.nan))
        m = np.isfinite(gz) & np.isfinite(rz)
        if m.sum() > 500:
            cc = float(np.corrcoef(gz[m], rz[m])[0, 1])
            out.setdefault("gamma_vs_next_range_rankcorr", {})[wname] = {
                "corr": cc, "n": int(m.sum())}
    p = os.path.join(ROOT, "research/trading_bot/INVENT_0823_gamma_DIAG.json")
    json.dump(out, open(p, "w"), indent=1)
    print(json.dumps(out, indent=1)[:6000])
    print("WROTE", p)


if __name__ == "__main__":
    main()
