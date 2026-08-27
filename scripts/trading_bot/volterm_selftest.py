#!/usr/bin/env python3
"""Self-test for the vol-ETP term-structure harness.

A sweep that returns "noise" is only believable if the same code can find an edge that
is definitely there, lose it when the sign is wrong, and report nothing on a random walk.
Three planted cases, run through the SAME _legs/_stats/evaluate path the sweep uses:

  1. PLANTED   -- a synthetic asset whose next-day return really is driven by a lagged
                  signal. The harness must report a large positive Sharpe at lag1.
  2. SIGN FLIP -- the identical setup with the weight sign reversed. Because the sweep
                  is deliberately NOT sign-agnostic, the harness must report a large
                  NEGATIVE Sharpe, not the absolute value.
  3. RANDOM    -- signal and returns independent. |Sharpe| must sit inside the noise band.
                  Run at ZERO cost: a +-1 signal that flips daily pays ~12%/yr in spread on
                  a 16%-vol book, so a costed random walk sits at Sharpe ~ -0.8 by
                  construction and would fail a noise test that the harness passes fine.
  4. STALENESS -- the signal IS the return it claims to predict (a quote read after the
                  bar it is timestamped to). lag0 must look spectacular and lag1 must
                  collapse to nothing. This is the artefact the lag-kill gate exists to
                  catch, so the gate is verified to fire rather than assumed to.

Usage: python3 scripts/trading_bot/volterm_selftest.py
"""
from __future__ import annotations

import json
import math
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from scripts.trading_bot.volterm_sweep import ANN, _legs, _stats  # noqa: E402

OUT = pathlib.Path(__file__).resolve().parents[2] / "research" / "trading_bot"


class FakeSweep:
    """Minimal stand-in exposing exactly what _legs touches: R, K, cost, borrow, dates."""

    def __init__(self, R, cost_bp=5.0, borrow_ann=0.0):
        self.R = R
        self.T, self.K = R.shape
        self.cost = np.full(self.K, cost_bp / 1e4)
        self.borrow = np.full(self.K, borrow_ann / ANN)
        self.dates = np.arange(20000101, 20000101 + self.T)


def score(R, W, lag, cost_bp=5.0):
    S = FakeSweep(R, cost_bp=cost_bp)
    g, c, _ = _legs(S, W, lag)
    return _stats(g - c, len(g) / ANN)


def main() -> int:
    rng = np.random.default_rng(20260820)
    T = 2000
    sig = rng.standard_normal(T)          # the "signal" observable at close t
    noise = rng.standard_normal(T) * 0.01
    res = {}

    # --- 1/2: a real, lag-1-tradable edge -----------------------------------
    r = np.zeros(T)
    r[2:] = 0.004 * sig[:-2] + noise[2:]   # return over t+1->t+2 driven by signal at t
    R = r.reshape(-1, 1)
    W = np.sign(sig).reshape(-1, 1)
    st = score(R, W, 1)
    res["planted_lag1"] = st["sharpe"]
    res["planted_sign_flipped_lag1"] = score(R, -W, 1)["sharpe"]

    # --- 3: pure noise, zero cost so the spread line cannot masquerade as signal
    rn = (rng.standard_normal(T) * 0.01).reshape(-1, 1)
    res["random_walk_lag1"] = score(rn, W, 1, cost_bp=0.0)["sharpe"]
    band = 2.0 / math.sqrt(T / ANN)
    res["noise_band_2se_sharpe"] = band
    res["random_walk_lag1_with_5bp_costs"] = score(rn, W, 1)["sharpe"]

    # --- 4: a same-bar staleness artefact -----------------------------------
    # _legs pairs W[i-lag] with R[i+1]. A perfectly stale signal is one whose value at
    # index i already contains R[i+1] -- i.e. a quote timestamped to a bar that had in
    # fact already printed. At lag0 that is free money; one extra lag must erase it.
    rs = (rng.standard_normal(T) * 0.01)
    stale_sig = np.zeros(T)
    stale_sig[:-1] = rs[1:]                       # signal at i IS the return at i+1
    RS = rs.reshape(-1, 1)
    WS = np.sign(stale_sig).reshape(-1, 1)
    res["staleness_lag0"] = score(RS, WS, 0, cost_bp=0.0)["sharpe"]
    res["staleness_lag1"] = score(RS, WS, 1, cost_bp=0.0)["sharpe"]
    res["staleness_retention_lag1_over_lag0"] = (
        res["staleness_lag1"] / res["staleness_lag0"])

    ok = {
        "planted_edge_detected": res["planted_lag1"] > 3.0,
        "sign_flip_is_negative": res["planted_sign_flipped_lag1"] < -3.0,
        "random_walk_inside_noise_band": abs(res["random_walk_lag1"]) < band,
        "staleness_is_spectacular_at_lag0": res["staleness_lag0"] > 5.0,
        "lagkill_gate_fires_on_staleness": abs(
            res["staleness_retention_lag1_over_lag0"]) < 0.25,
    }
    res["assertions"] = ok
    res["all_passed"] = all(ok.values())
    (OUT / "NEWTERR_volatility_etp_term_structure_SELFTEST.json").write_text(
        json.dumps(res, indent=2))
    for k, v in res.items():
        if k not in ("assertions",):
            print(f"  {k:38s} {v}")
    for k, v in ok.items():
        print(f"  [{'PASS' if v else 'FAIL'}] {k}")
    return 0 if res["all_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
