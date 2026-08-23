#!/usr/bin/env python3
"""Where does the gross of the two best-gross intraday configs actually live?

Decomposes the hold into (i) the single leg immediately after the signal -- the leg the
gap test removes -- and (ii) the remainder of the hold.  If (i) carries the gross, the
"edge" is a one-bar continuation of the signal print, i.e. the bounce.
"""
from __future__ import annotations

import json
import pathlib

import numpy as np

import im0823_sweep as S


def book(sc, px_in, px_out, valid):
    valid = valid & (valid.sum(axis=1) >= 10)[:, None]
    w = S.weights_from_score(np.where(valid, sc, np.nan), valid)
    r = np.nan_to_num(np.where(valid, px_out / px_in - 1.0, 0.0))
    return (w * r).sum(axis=1)


def main() -> None:
    P = S.PanelA()
    F = S.Feat(P)
    B = S.PanelB()
    out = {}

    for lab, win in (("design", S.DESIGN), ("heldout", S.HELDOUT)):
        da = (P.daykey >= win[0]) & (P.daykey <= win[1])
        db = (B.dates >= win[0]) & (B.dates <= win[1])

        # --- F2_LD_REV on panel A: signal at bar 69, entry 70, exit 77
        cols = P.cols("MEGA")
        sc = (-F.r69)[:, cols][da]
        v70 = P.vw[:, 70, :][:, cols][da]
        v71 = P.vw[:, 71, :][:, cols][da]
        v77 = P.vw[:, 77, :][:, cols][da]
        ok = np.isfinite(sc) & np.isfinite(v70) & np.isfinite(v71) & np.isfinite(v77) & (v70 > 0) & (v71 > 0) & (v77 > 0)
        full = book(sc, v70, v77, ok)
        first = book(sc, v70, v71, ok)
        rest = book(sc, v71, v77, ok)
        out[f"F2_LD_REV_{lab}"] = {
            "gross_sharpe_full_70_to_77": S.sharpe(full),
            "gross_sharpe_first_bar_70_to_71": S.sharpe(first),
            "gross_sharpe_rest_71_to_77": S.sharpe(rest),
            "bps_day_full": float(full.mean() * 1e4),
            "bps_day_first_bar": float(first.mean() * 1e4),
            "bps_day_rest": float(rest.mean() * 1e4),
            "share_of_gross_in_first_bar": float(first.mean() / full.mean()) if full.mean() else float("nan"),
        }

        # --- G1_LD500_CONT on panel B: signal open->15:29, entry 15:49, exit close
        ok = (B.in_uni & np.isfinite(B.po) & np.isfinite(B.p29) & np.isfinite(B.p49)
              & np.isfinite(B.p59) & np.isfinite(B.pc) & (B.po > 0) & (B.p29 > 0)
              & (B.p49 > 0) & (B.p59 > 0) & (B.pc > 0))[db]
        scb = (B.p29 / B.po - 1.0)[db]
        okb = ok & (ok.sum(axis=1) >= 20)[:, None]
        fullb = book(scb, B.p49[db], B.pc[db], okb)
        firstb = book(scb, B.p49[db], B.p59[db], okb)
        restb = book(scb, B.p59[db], B.pc[db], okb)
        out[f"G1_LD500_CONT_{lab}"] = {
            "gross_sharpe_full_1549_to_close": S.sharpe(fullb),
            "gross_sharpe_first_leg_1549_to_1559": S.sharpe(firstb),
            "gross_sharpe_rest_1559_to_close": S.sharpe(restb),
            "bps_day_full": float(fullb.mean() * 1e4),
            "bps_day_first_leg": float(firstb.mean() * 1e4),
            "bps_day_rest": float(restb.mean() * 1e4),
            "share_of_gross_in_first_leg": float(firstb.mean() / fullb.mean()) if fullb.mean() else float("nan"),
        }

    print(json.dumps(out, indent=1))
    p = pathlib.Path(__file__).resolve().parents[2] / "research" / "trading_bot" / "INVENT_0823_intramicro_DIAG.json"
    p.write_text(json.dumps(out, indent=1))
    print("wrote", p)


if __name__ == "__main__":
    main()
