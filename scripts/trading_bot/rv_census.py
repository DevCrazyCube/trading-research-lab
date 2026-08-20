#!/usr/bin/env python3
"""Feasibility census for the intraday RV theme, computed BEFORE any strategy is scored.

The question a backtest cannot answer honestly on its own is whether the thing being traded
is bigger than the cost of trading it. For a same-claim ETF pair that question has a number:
how many basis points does the log price ratio actually move away from its own trailing mean,
and does that displacement persist for even one bar?

Round-trip cost of a two-leg pair trade is 2 legs x 2 sides x half_spread, so at the sweep's
headline 1.0 bp/side rung the pair must move ~4 bp before the trade breaks even. This census
prints the displacement distribution next to that number, per pair, on the DESIGN window only.

Output: research/trading_bot/SWEEP_intraday_rv_census.json
"""
from __future__ import annotations

import json
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from trading_bot.rv_sweep import (  # noqa: E402
    DESIGN, HEADLINE_BP, LEVERED_PAIRS, REG_BP_PER_TURNOVER, SECTOR_BASKETS, SIBLING_PAIRS,
    Panel, _nan_roll,
)

OUT = pathlib.Path(__file__).resolve().parents[2] / "research" / "trading_bot"


def census_spread(P, sp, mask, win=78):
    mu, _ = _nan_roll(sp[:, None], win)
    dev = (sp - mu[:, 0]) * 1e4
    dev = dev[mask & np.isfinite(dev)]
    if dev.size < 5000:
        return None
    d1 = dev[1:]
    ac = float(np.corrcoef(d1, dev[:-1])[0, 1]) if dev.size > 10 else float("nan")
    hl = float(np.log(0.5) / np.log(ac)) if 0 < ac < 1 else float("inf")
    return {
        "n": int(dev.size),
        "sd_bp": float(dev.std()),
        "p95_abs_bp": float(np.percentile(np.abs(dev), 95)),
        "p99_abs_bp": float(np.percentile(np.abs(dev), 99)),
        "ac1": ac,
        "implied_halflife_bars": hl,
    }


def main() -> None:
    P = Panel()
    mask = (P.daykey >= DESIGN[0]) & (P.daykey <= DESIGN[1])
    rt = 4 * HEADLINE_BP + 4 * REG_BP_PER_TURNOVER

    out = {
        "window": list(DESIGN),
        "detrend_window_bars": 78,
        "round_trip_cost_bp_two_leg": rt,
        "note": "a two-leg pair trade crosses four half-spreads (two legs, in and out). A "
                "dislocation whose 95th percentile is below that number cannot be traded by a "
                "taker at any threshold, and an ac(1) near zero means the displacement is "
                "non-synchronous-print noise rather than a dislocation that persists to be "
                "captured.",
        "sibling_pairs": {},
        "levered_pairs": {},
        "etf_vs_basket": {},
    }
    for a, b in SIBLING_PAIRS:
        ia, ib = P.col(a), P.col(b)
        if ia is None or ib is None:
            continue
        c = census_spread(P, P.logc[:, ia] - P.logc[:, ib], mask)
        if c:
            c["tradable_p95_over_cost"] = round(c["p95_abs_bp"] / rt, 3)
            out["sibling_pairs"][f"{a}/{b}"] = c
    for lev, base, mult in LEVERED_PAIRS:
        il, ib = P.col(lev), P.col(base)
        if il is None or ib is None:
            continue
        c = census_spread(P, P.logc[:, il] - mult * P.logc[:, ib], mask)
        if c:
            c["tradable_p95_over_cost"] = round(c["p95_abs_bp"] / rt, 3)
            out["levered_pairs"][f"{lev}~{mult}x{base}"] = c
    for etf, members in SECTOR_BASKETS.items():
        ie, cols = P.col(etf), P.cols(members)
        if ie is None or len(cols) < 2:
            continue
        c = census_spread(P, P.logc[:, ie] - np.nanmean(P.logc[:, cols], axis=1), mask)
        if c:
            c["tradable_p95_over_cost"] = round(c["p95_abs_bp"] / rt, 3)
            out["etf_vs_basket"][etf] = c

    sib = out["sibling_pairs"]
    if sib:
        ratios = [v["tradable_p95_over_cost"] for v in sib.values()]
        out["summary"] = {
            "n_sibling_pairs": len(sib),
            "n_with_p95_above_round_trip": int(sum(r > 1 for r in ratios)),
            "median_p95_over_cost": float(np.median(ratios)),
            "median_ac1": float(np.median([v["ac1"] for v in sib.values()])),
        }
    (OUT / "SWEEP_intraday_rv_census.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out.get("summary", {}), indent=1))
    print(f"wrote {OUT / 'SWEEP_intraday_rv_census.json'}")


if __name__ == "__main__":
    main()
