#!/usr/bin/env python3
"""Harness self-test for the INVENT_0823 intraday-microstructure sweep.

Three checks against the real cube, run before any design number is trusted:
  1. planted   -- a score that is the (unobservable) afternoon return plus noise must
                  score a large positive Sharpe.
  2. negated   -- the same score negated must score the mirror-image Sharpe.
  3. random    -- an i.i.d. score with nothing in it must score ~0.
  4. gap-decay -- a score built from the *bar s+1 return only* (a pure one-bar artefact)
                  must survive the primary fill and DIE under the gap fill, proving the
                  gap gate can actually detect a bounce/one-bar artefact.
"""
from __future__ import annotations

import json
import pathlib

import numpy as np

import im0823_sweep as S


def main() -> None:
    P = S.PanelA()
    F = S.Feat.__new__(S.Feat)   # only the panel is needed for these checks
    F.P = P
    da = (P.daykey >= S.DESIGN[0]) & (P.daykey <= S.DESIGN[1])
    cols = P.cols("MEGA")
    rng = np.random.default_rng(7)

    fwd = P.vw[:, 77, :] / P.vw[:, 24, :] - 1.0          # entry at 23+1, exit 77
    one_bar = P.vw[:, 25, :] / P.vw[:, 24, :] - 1.0      # the very next bar only

    out = {}
    for lab, sc in (("planted", fwd + rng.normal(0, 0.004, fwd.shape)),
                    ("negated", -(fwd + rng.normal(0, 0.004, fwd.shape))),
                    ("random", rng.normal(0, 0.01, fwd.shape)),
                    ("one_bar_artefact", one_bar)):
        cfg = dict(name=lab, universe="MEGA", score=sc.astype(np.float32), s=23,
                   family="selftest", panel="A", extra={})
        g0, e0 = S.run_panelA(cfg, F, da, 0)
        g1, e1 = S.run_panelA(cfg, F, da, 1)
        out[lab] = {"primary_gross_sharpe": S.sharpe(g0), "gap_gross_sharpe": S.sharpe(g1),
                    "primary_net_1bp": S.sharpe(S.net_series(g0, e0, 1.0, False)),
                    "gap_net_1bp": S.sharpe(S.net_series(g1, e1, 1.0, False))}
        print(f"{lab:18s} primary {out[lab]['primary_gross_sharpe']:+8.2f}  "
              f"gap {out[lab]['gap_gross_sharpe']:+8.2f}", flush=True)

    checks = {
        "planted_recovers": out["planted"]["primary_gross_sharpe"] > 5,
        "negation_mirrors": out["negated"]["primary_gross_sharpe"] < -5,
        "random_is_flat": abs(out["random"]["primary_gross_sharpe"]) < 1.0,
        "gap_gate_kills_one_bar_artefact":
            out["one_bar_artefact"]["primary_gross_sharpe"] > 2
            and out["one_bar_artefact"]["gap_gross_sharpe"]
            < 0.5 * out["one_bar_artefact"]["primary_gross_sharpe"],
    }
    out["checks"] = checks
    out["all_pass"] = bool(all(checks.values()))
    print(json.dumps(checks, indent=1))
    p = pathlib.Path(__file__).resolve().parents[2] / "research" / "trading_bot" / "INVENT_0823_intramicro_selftest.json"
    p.write_text(json.dumps(out, indent=1))
    print("wrote", p)


if __name__ == "__main__":
    main()
