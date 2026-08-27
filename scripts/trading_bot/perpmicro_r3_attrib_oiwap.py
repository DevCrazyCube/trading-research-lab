#!/usr/bin/env python3
"""Attribution for the round-3 class-B liquidation-heatmap family.

R3B_OIWAP_GAP / R3B_LIQ_DIST_25X / R3B_LIQ_ASYM were the only class-B signals positive in
design AND both held-out windows. They share one construct: an exponentially-decayed
average price weighted by POSITIVE open-interest creation (the reconstructed cost basis),
compared to spot and scaled by daily vol.

The sceptical hypothesis: the OI weighting is decoration. A 7d-decay average price compared
to spot and divided by vol is a vol-normalised TREND signal; if equal weights or volume
weights give the same P&L, round 3 has invented nothing.

  GAP_EQ   : equal-weight 7d EWMA of price  -> (log px - log ewma)/vol   [no OI at all]
  GAP_QV   : quote-volume-weighted 7d EWMA                              [no OI at all]
  GAP_OI   : the round-3 OI-creation-weighted version                   [R3B_OIWAP_GAP]
  MOM_VOL  : r168 / daily vol                                           [plain vol-scaled 7d mom]
  OI_RESID : XS residual of GAP_OI on GAP_EQ  -> what OI weighting adds
"""
from __future__ import annotations

import json
import math
import pathlib

import numpy as np

from perpmicro_sweep import roll_sum, window_mask, run_window, _corr
import perpmicro_r3 as r3

OUT = pathlib.Path(__file__).resolve().parents[2] / "research" / "trading_bot"


def main():
    p = r3.build("B", 60, 20)
    U = p.univ
    g = p.g
    px = g["c"]
    lpx = np.log(np.where(px > 0, px, np.nan)).astype(np.float32)
    vol_d = np.maximum(p.rv24 * math.sqrt(24), 1e-4)
    lam = math.exp(-1.0 / (24 * 7))

    oi = g["oi"]
    dpos = np.clip((oi - r3.lag(oi, 1)).astype(np.float32), 0, None)
    ones = np.where(np.isfinite(px) & (px > 0), 1.0, 0.0).astype(np.float32)
    qvw = np.nan_to_num(g["qv"], nan=0.0)

    def gap(w):
        e = r3.ewma_ratio(w, px, lam)
        with np.errstate(invalid="ignore", divide="ignore"):
            return np.where(e > 0, (lpx - np.log(e)) / vol_d, np.nan).astype(np.float32)

    g_eq = gap(ones)
    g_qv = gap(qvw)
    g_oi = gap(dpos)
    with np.errstate(invalid="ignore", divide="ignore"):
        mom_vol = (p.r168 / vol_d).astype(np.float32)

    F = [
        ("GAP_EQ", g_eq, 24, "quintile", None, "equal-weight 7d EWMA price gap / vol"),
        ("GAP_QV", g_qv, 24, "quintile", None, "volume-weighted 7d EWMA price gap / vol"),
        ("GAP_OI", g_oi, 24, "quintile", None, "OI-creation-weighted (= R3B_OIWAP_GAP)"),
        ("MOM_VOL", mom_vol, 24, "quintile", None, "r168 / daily vol"),
        ("OI_RESID", r3.xs_resid(g_oi, g_eq, U), 24, "quintile", None,
         "XS residual of GAP_OI on GAP_EQ: the marginal content of the OI weighting"),
    ]
    out = {}
    signs = None
    for tag, w, thin in [("design", r3.DESIGN_B, False), ("hold_b1", r3.HOLD_B1, False)]:
        m = window_mask(p.t, *w)
        res, mat = run_window(F, p, m, signs=signs)
        if tag == "design":
            signs = {r["name"]: r["sign"] for r in res}
        store = {r["name"]: r["sign"] * row for r, row in zip(res, mat)}
        cm = {}
        ns = list(store)
        for i, a in enumerate(ns):
            for b in ns[i + 1:]:
                cm[f"{a}~{b}"] = _corr(store[a], store[b])
        out[tag] = {"range": list(w), "results": res, "corr": cm}
        print(f"--- {tag}")
        for r in res:
            print(f"  {r['name']:10s} net {r['sharpe_net']:+6.2f} gross {r['sharpe_gross']:+6.2f} "
                  f"be {r['breakeven_cost_bp_per_side']:6.1f} tpd {r['turnover_per_day']:.2f}")
        print("  corr GAP_OI~GAP_EQ", round(cm["GAP_EQ~GAP_OI"], 3),
              "GAP_OI~MOM_VOL", round(cm["GAP_OI~MOM_VOL"], 3),
              "GAP_EQ~MOM_VOL", round(cm["GAP_EQ~MOM_VOL"], 3))

    del p
    p2 = r3.build("B", 40, 8)
    U2 = p2.univ
    px2 = p2.g["c"]
    lpx2 = np.log(np.where(px2 > 0, px2, np.nan)).astype(np.float32)
    vd2 = np.maximum(p2.rv24 * math.sqrt(24), 1e-4)
    oi2 = p2.g["oi"]
    dpos2 = np.clip((oi2 - r3.lag(oi2, 1)).astype(np.float32), 0, None)
    ones2 = np.where(np.isfinite(px2) & (px2 > 0), 1.0, 0.0).astype(np.float32)
    qv2 = np.nan_to_num(p2.g["qv"], nan=0.0)

    def gap2(w):
        e = r3.ewma_ratio(w, px2, lam)
        with np.errstate(invalid="ignore", divide="ignore"):
            return np.where(e > 0, (lpx2 - np.log(e)) / vd2, np.nan).astype(np.float32)

    ge2, gq2, go2 = gap2(ones2), gap2(qv2), gap2(dpos2)
    F2 = [
        ("GAP_EQ", ge2, 24, "quintile", None, ""),
        ("GAP_QV", gq2, 24, "quintile", None, ""),
        ("GAP_OI", go2, 24, "quintile", None, ""),
        ("MOM_VOL", (p2.r168 / vd2).astype(np.float32), 24, "quintile", None, ""),
        ("OI_RESID", r3.xs_resid(go2, ge2, U2), 24, "quintile", None, ""),
    ]
    m = window_mask(p2.t, *r3.HOLD_B2)
    res, mat = run_window(F2, p2, m, signs=signs)
    out["hold_b2_thin"] = {"range": list(r3.HOLD_B2), "results": res}
    print("--- hold_b2_thin")
    for r in res:
        print(f"  {r['name']:10s} net {r['sharpe_net']:+6.2f} gross {r['sharpe_gross']:+6.2f}")

    (OUT / "INVENT_R3_perpstructure_ATTRIB_OIWAP.json").write_text(json.dumps(out, indent=1))
    print("wrote oiwap attrib")


if __name__ == "__main__":
    main()
