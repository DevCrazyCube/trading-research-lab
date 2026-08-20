#!/usr/bin/env python3
"""Harness self-test: does the evaluator find a KNOWN edge, and does it invent one when there
is none?

Five domains in this repo have died at the friction floor, and the way a backtest lies most
often is a sign error or a lookahead that manufactures alpha out of noise. So before any real
result is quoted, the evaluator is run against two synthetic panels whose answer is known in
advance:

  1. A planted OU dislocation (20 bp scale, 20-bar half-life) between two otherwise identical
     legs. A working harness MUST find a large positive gross Sharpe.
  2. A RANDOM-WALK spread -- nothing to revert to. A working harness MUST return ~0.

Plus a sign control: negating the weights must negate the Sharpe exactly. If it does not, the
sign convention is wrong somewhere and every number the sweep prints is suspect.

Writes research/trading_bot/SWEEP_intraday_rv_selftest.json.
"""
from __future__ import annotations

import json
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import trading_bot.rv_sweep as R  # noqa: E402

OUT = pathlib.Path(__file__).resolve().parents[2] / "research" / "trading_bot"


def synth(planted: bool, seed: int = 11, days: int = 400, bars: int = 78):
    rng = np.random.default_rng(seed)
    T = days * bars
    day = np.repeat(np.arange(days), bars)
    slot = np.tile(np.arange(bars), days)
    factor = np.cumsum(rng.normal(0, 3e-4, T))
    if planted:
        phi = 0.5 ** (1 / 20)
        s = np.zeros(T)
        for t in range(1, T):
            s[t] = phi * s[t - 1] + rng.normal(0, 20e-4 * np.sqrt(1 - phi ** 2))
    else:
        s = np.cumsum(rng.normal(0, 3e-5, T))
    close = np.exp(np.column_stack([5 + factor + s / 2, 5 + factor - s / 2]))
    P = R.Panel.__new__(R.Panel)
    P.day, P.slot = day, slot
    P.daykey = np.array([f"2022-{1 + d // 31:02d}-{1 + d % 31:02d}" for d in day])
    P.syms = ["SPY", "IVV"]
    P.idx = {"SPY": 0, "IVV": 1}
    P.close = P.open = P.vwap = close
    P.dvol = np.full((T, 2), 1e6)
    P.T, P.S = T, 2
    P.logc = np.log(close)
    P.tradable = np.ones((T, 2), bool)
    P.fwd_ret = np.full((T, 2), np.nan)
    P.fwd_ret[:-1] = close[1:] / close[:-1] - 1
    return P, np.ones(T, bool)


def main() -> None:
    saved = R.SIBLING_PAIRS
    R.SIBLING_PAIRS = [("SPY", "IVV")]
    cfg = {"kind": "pair_z_band", "win": 78, "entry": 2.0, "exit": 0.5}
    res = {}
    try:
        for label, planted in (("planted_ou_edge", True), ("null_random_walk", False)):
            P, mask = synth(planted)
            W = R.build(P, cfg)
            row = {}
            for sign, tag in ((1, "as_specified"), (-1, "negated_control")):
                g, turn = R.evaluate(P, sign * W, mask)
                d, _ = R.daily_series(P, g, turn, mask, 0.0, reg_bp=0.0)
                row[tag] = round(R.sharpe(d), 3)
            for bp in R.COST_RUNGS_BP:
                g, turn = R.evaluate(P, W, mask)
                d, _ = R.daily_series(P, g, turn, mask, bp)
                row[f"net_{bp}bp"] = round(R.sharpe(d), 3)
            row["turnover_per_day"] = round(float(np.bincount(P.day, weights=turn).mean()), 3)
            res[label] = row
    finally:
        R.SIBLING_PAIRS = saved

    checks = {
        "finds_planted_edge": res["planted_ou_edge"]["as_specified"] > 5.0,
        "sign_flips_exactly": abs(res["planted_ou_edge"]["as_specified"]
                                  + res["planted_ou_edge"]["negated_control"]) < 1e-6,
        "no_alpha_from_a_random_walk": abs(res["null_random_walk"]["as_specified"]) < 1.0,
    }
    payload = {"results": res, "checks": checks, "all_passed": all(checks.values())}
    (OUT / "SWEEP_intraday_rv_selftest.json").write_text(json.dumps(payload, indent=1))
    print(json.dumps(payload, indent=1))
    if not payload["all_passed"]:
        raise SystemExit("HARNESS SELF-TEST FAILED -- do not trust any sweep number")


if __name__ == "__main__":
    main()
