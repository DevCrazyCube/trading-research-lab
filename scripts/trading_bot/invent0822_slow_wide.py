#!/usr/bin/env python3
"""
INVENT 0822 · LOW-TURNOVER · declared extension (frozen in INVENT_0822_slowturn_FREEZE.md).

The main sleeve inherits newterr_xseq's $20M+ ADV screen, which structurally excludes the
population in which an illiquidity / neglect premium could exist at all. This run repeats the
illiquidity and payout formulas on a $2M+ ADV universe -- the one and only universe extension
declared. Both windows are run in the same invocation because the extension was declared in
advance; the cells are counted into N.

Usage: python3 invent0822_slow_wide.py
"""
import json, os, sys, math, gc
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from trading_bot import newterr_xseq_sweep as X

X.MIN_ADV = 2e6            # <-- the extension

from trading_bot.newterr_xseq_sweep import (
    roll_mean, roll_std, roll_geomean, lag, xs_rank, decile_weights,
    run_book, stats, wmask, F32, FEE, STRESS_FLAT,
)
import trading_bot.invent0822_slow_xs as S

RES = "/home/anont/meme/research/trading_bot"
KEEP = {"ILLIQ_AMIHUD", "SPREAD_LEVEL", "ILLIQ_UNCERT", "ATTN_DECAY",
        "DIVY_TTM", "DIV_CUT_DEPTH"}


def main():
    P = X.Panel()
    print(f"wide universe: N={P.N}, median eligible/day="
          f"{np.median(P.elig.sum(axis=1)):.0f}", flush=True)
    sigs = [s for s in S.build_signals(P) if s[0] in KEEP]
    out = {}
    for tag, win in (("design", S.DESIGN), ("holdout", S.HOLDOUT)):
        out[tag] = S.sweep(P, win, sigs=sigs)
        for r in sorted(out[tag], key=lambda z: -z["gross_t"]):
            print(f"{tag:>8s} {r['name']:>16s} h{r['h']:>2d} gSR{r['gross_sharpe']:6.2f} "
                  f"t{r['gross_t']:6.2f} nSR{r['net_sharpe']:6.2f} t{r['net_t']:6.2f} "
                  f"turn{r['turnover_per_day']:7.4f} be{r['breakeven_cost_bps']:8.1f}bp", flush=True)
    out["universe"] = dict(min_adv=X.MIN_ADV, n_cols=int(P.N),
                           median_eligible=float(np.median(P.elig.sum(axis=1))),
                           mean_half_spread_bps=float(np.nanmean(np.where(P.elig, P.hs, np.nan)) * 1e4))
    json.dump(out, open(os.path.join(RES, "INVENT_0822_slowturn_WIDE.json"), "w"),
              indent=1, default=float)


if __name__ == "__main__":
    main()
