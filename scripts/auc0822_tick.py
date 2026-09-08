#!/usr/bin/env python3
"""INVENT_0822B -- POST-HOC characterisation of the one statistic that survived out of sample.

Found by the interval decomposition of the pre-registered grid, NOT pre-registered: the component
`1559_to_C` of the DAY_t1 outcome -- i.e. the NEXT day's own close-auction dislocation
d_{t+1} = ln(C_{t+1}/P59_{t+1}) -- is predicted by today's d_t with design t +14.3 and held-out
t +20.6. This script characterises that object honestly and prices it, because a t of 20 out of
sample deserves either a promotion or an explicit obituary and nothing in between.

The trade it implies: BUY at the 15:59 continuous print (must cross a real quoted spread) and
SELL into the closing auction print (free). So the capture is `d` and the cost is one half-spread.
T3 measured that half-spread first-party on this exact universe: 1.13 bp (2016-2021) and
1.43 bp (2022-2026) median, top-500 ADV, final second before the close.
"""
from __future__ import annotations

import json
import pathlib
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
CACHE = ROOT / "research" / "data" / "auc0822_cache"
OUT = ROOT / "research" / "trading_bot"
sys.path.insert(0, str(ROOT))
from scripts.auc0822_engine import (  # noqa: E402
    DESIGN_END, HELD_START, MIN_NAMES, MIN_PRICE, MAX_GAP, MAX_DAY,
    lag, roll_mean, stats, zscore_rows,
)

HALF_SPREAD_BP = {"design": 1.13, "held": 1.43}     # T3 first-party measurement, same universe


def main():
    z = np.load(CACHE / "panel.npz", allow_pickle=False)
    dates = np.array([str(d) for d in z["dates"]])
    p49, p59, po, pc = z["p49"], z["p59"], z["po"], z["pc"]
    ca, in_uni = z["ca"], z["in_uni"]
    with np.errstate(divide="ignore", invalid="ignore"):
        l49, l59, lo, lc = (np.log(v) for v in (p49, p59, po, pc))
    for a in (l49, l59, lo, lc):
        a[~np.isfinite(a)] = np.nan
    base = in_uni & (p59 >= MIN_PRICE) & (~ca) & np.isfinite(l59) & np.isfinite(lc) & np.isfinite(lo)
    d = lc - l59
    q = lo - lag(lc, 1)
    x = lc - lo
    base = base & (np.abs(np.nan_to_num(q, nan=0.0)) <= MAX_GAP) \
                & (np.abs(np.nan_to_num(x, nan=0.0)) <= MAX_DAY)
    dm = np.where(base, d, np.nan)
    d5 = roll_mean(dm, 5)
    d20 = roll_mean(dm, 20)
    d60 = roll_mean(dm, 60)

    des, hel = dates <= DESIGN_END, dates >= HELD_START
    rmask = base & lag(base, -1)
    R = np.where(rmask, lag(d, -1), np.nan)          # d_{t+1}: the capture, entry 15:59 -> exit print

    out = {"note": "POST-HOC. Not in the pre-registered N=54 grid. No promotion claim.",
           "half_spread_bp_charged": HALF_SPREAD_BP, "cells": {}}
    for nm, sig in (("d_t", d), ("mean5_d", d5), ("mean20_d", d20), ("mean60_d", d60),
                    ("sign_d_t", np.sign(d))):
        m = rmask & np.isfinite(sig) & np.isfinite(R)
        ok = m.sum(axis=1) >= MIN_NAMES
        W = zscore_rows(sig, m & ok[:, None])
        gross = np.where(ok, (W * np.nan_to_num(R, nan=0.0)).sum(axis=1), np.nan)
        turn = np.abs(W).sum(axis=1)                  # one crossed side (entry); exit is the print
        row = {}
        for tag, sel in (("design", des), ("held", hel)):
            g = stats(np.where(sel, gross, np.nan))
            c = HALF_SPREAD_BP[tag] * 1e-4
            n = stats(np.where(sel, gross - turn * c, np.nan))
            row[tag] = {"gross_bp": g["mean_bp"], "gross_t": g["t"], "gross_sharpe": g["sharpe"],
                        "n_days": g["n"],
                        "crossed_notional": float(np.nanmean(np.where(sel & ok, turn, np.nan))),
                        "cost_bp_per_day": float(np.nanmean(np.where(sel & ok, turn, np.nan))
                                                 * HALF_SPREAD_BP[tag]),
                        "net_bp": n["mean_bp"], "net_t": n["t"], "net_sharpe": n["sharpe"],
                        "breakeven_half_spread_bp": (g["mean_bp"] /
                                                     float(np.nanmean(np.where(sel & ok, turn, np.nan))))}
        out["cells"][nm] = row
        print(f"{nm:10s} des gross {row['design']['gross_bp']:+6.3f}bp t{row['design']['gross_t']:+7.2f}"
              f" net {row['design']['net_bp']:+7.3f}bp t{row['design']['net_t']:+6.2f}"
              f" | held gross {row['held']['gross_bp']:+6.3f}bp t{row['held']['gross_t']:+7.2f}"
              f" net {row['held']['net_bp']:+7.3f}bp t{row['held']['net_t']:+6.2f}"
              f" | breakeven half-spread {row['held']['breakeven_half_spread_bp']:.3f}bp")

    # per-name fixed effect: how much of d's cross-sectional persistence is a constant per symbol?
    sym_mean = np.nanmean(dm, axis=0)
    resid = dm - sym_mean[None, :]
    def ac1(a):
        p, q_ = a[1:], a[:-1]
        ok = np.isfinite(p) & np.isfinite(q_)
        pp, qq = p[ok] - p[ok].mean(), q_[ok] - q_[ok].mean()
        return float((pp * qq).sum() / np.sqrt((pp * pp).sum() * (qq * qq).sum()))
    out["rho1_level_raw"] = ac1(dm)
    out["rho1_level_after_symbol_demeaning"] = ac1(resid)
    out["sd_of_symbol_mean_d_bp"] = float(np.nanstd(sym_mean) * 1e4)
    out["median_abs_d_bp"] = float(np.nanmedian(np.abs(dm)) * 1e4)
    out["median_full_tick_bp"] = float(np.nanmedian(np.where(base, 0.01 / p59 * 1e4, np.nan)))
    print(json.dumps({k: v for k, v in out.items() if k != "cells"}, indent=1))
    (OUT / "INVENT_0822B_auction_TICK.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
