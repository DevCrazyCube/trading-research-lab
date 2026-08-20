#!/usr/bin/env python3
"""POST-HOC diagnostic for the ETF-structural deep mine. Declared post-hoc, and it selects
nothing: it is run AFTER the frozen shortlist and the held-out numbers are already on disk.

The design sweep answered "does this trade?" with a flat no -- 0 of 51 formulas has a positive
net Sharpe even in-sample. That answer is uninformative on its own, because it does not say
whether the family missed by a hair or by an order of magnitude. This computes, per formula:

  gross_bp_per_day   what the signal earned before any friction
  charged_half_bp    the average half-spread this formula actually paid, per unit of turnover
  breakeven_half_bp  the half-spread at which the formula would break exactly even
  tightness_needed   charged / breakeven -- how many times tighter spreads must be

A value of 2 means "wait for spreads to halve". A value of 40 means the family is not a costs
problem, it is a different-business problem.
"""
from __future__ import annotations

import json
import pathlib

OUT = pathlib.Path(__file__).resolve().parents[2] / "research" / "trading_bot"
KEY = "etf_structural_rv"
REG_BP = 0.15


def rows_for(stage):
    d = json.loads((OUT / f"DEEPMINE_{KEY}_{stage}.json").read_text())
    out = []
    for r in d["results"]:
        turn = r["daily_turnover"]
        net_bp = r["ann_ret"] / 252.0 * 1e4
        reg_bp = turn * REG_BP
        gross_bp = net_bp + r["daily_spread_bp"] + reg_bp + r["daily_borrow_bp"]
        charged = r["daily_spread_bp"] / turn if turn > 1e-9 else float("nan")
        be = (gross_bp - reg_bp - r["daily_borrow_bp"]) / turn if turn > 1e-9 else float("nan")
        cost_bp = r["daily_spread_bp"] + reg_bp + r["daily_borrow_bp"]
        out.append({
            "name": r["name"], "kind": r["kind"],
            "sharpe_gross": round(r["sharpe_gross"], 3),
            "sharpe_net": round(r["sharpe_net"], 3),
            "daily_turnover": round(turn, 2),
            "gross_bp_per_day": round(gross_bp, 3),
            "cost_bp_per_day": round(cost_bp, 3),
            "cost_multiple_of_gross": (round(cost_bp / gross_bp, 1) if gross_bp > 1e-9 else None),
            "reg_only_bp_per_day": round(reg_bp + r["daily_borrow_bp"], 3),
            "charged_half_spread_bp": round(charged, 3),
            "breakeven_half_spread_bp": round(be, 4),
            # A NEGATIVE break-even is not a rounding artefact and must not be printed as a
            # blank: it says the SEC/FINRA pass-throughs and borrow alone already exceed the
            # gross edge, so a zero-spread venue would not rescue this formula either.
            "zero_spread_still_loses": bool(be <= 0),
            "tightness_needed_x": (round(charged / be, 1) if be > 1e-9 else None),
        })
    return d, out


def main():
    design, rows = rows_for("design")
    rows.sort(key=lambda r: -r["sharpe_gross"])
    pos = [r for r in rows if r["breakeven_half_spread_bp"] > 0]
    payload = {
        "declared": "POST_HOC_DIAGNOSTIC",
        "why": "the frozen test returned 0/51 tradable; this measures HOW FAR the family is "
               "from tradable, which the pass/fail alone cannot say",
        "window": design["window"],
        "gross_noise_bar_p95": design["noise_bar"]["bootstrap_gross"]["p95"],
        "best_gross_sharpe": rows[0]["sharpe_gross"],
        "n_with_positive_gross_edge": len(pos),
        "median_tightness_needed_x": (
            sorted(r["tightness_needed_x"] for r in pos if r["tightness_needed_x"])[len(
                [r for r in pos if r["tightness_needed_x"]]) // 2] if pos else None),
        "per_formula": rows,
    }
    try:
        held = json.loads((OUT / f"DEEPMINE_{KEY}_heldout.json").read_text())
        _, hrows = rows_for("heldout")
        payload["heldout_window"] = held["window"]
        payload["heldout_per_formula"] = hrows
    except FileNotFoundError:
        pass
    payload["n_zero_spread_still_loses"] = sum(1 for r in rows if r["zero_spread_still_loses"])
    p = OUT / f"DEEPMINE_{KEY}_BREAKEVEN.json"
    p.write_text(json.dumps(payload, indent=1))
    for r in rows[:12]:
        tail = ("even a ZERO spread loses (fees alone > edge)" if r["zero_spread_still_loses"]
                else f"needs {r['tightness_needed_x']}x tighter spreads")
        print(f"{r['name']:34s} gross={r['sharpe_gross']:+.2f} grossbp/d={r['gross_bp_per_day']:6.3f} "
              f"costbp/d={r['cost_bp_per_day']:7.3f} (x{r['cost_multiple_of_gross']}) -> {tail}",
              flush=True)
    print("wrote", p, flush=True)


if __name__ == "__main__":
    main()
