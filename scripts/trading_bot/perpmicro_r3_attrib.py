#!/usr/bin/env python3
"""Attribution for the round-3 class-A survivors.

The only class-A formula that clearly beat its design bar is R3A_NETCARRY_MOM
(7d return minus 7d funding paid). The obvious sceptical hypothesis is that it is
round 1's XS_MOM168 (7d momentum) wearing a hat: funding is O(10 bp/week) while a 7d
crypto return is O(1000 bp/week), so the funding term may contribute nothing.

This script decomposes it, on the SAME panel and the SAME two windows:
  M_ONLY      = r168                          (pure 7d momentum, = round 1's XS_MOM168)
  F_ONLY      = -sum(funding paid, 168h)      (pure realised carry, sign as it enters netcarry)
  NETCARRY    = r168 - sum(funding, 168h)     (the round-3 formula)
  NETCARRY_K3 = r168 - 3*sum(funding, 168h)   (funding term tripled: does weighting matter?)
  NC_RESID_M  = cross-sectional residual of NETCARRY on r168   (the part momentum cannot explain)
  M_RESID_F   = cross-sectional residual of r168 on the carry term

If NC_RESID_M is flat, round 3 has re-derived a round-1 formula and must say so.
"""
from __future__ import annotations

import json
import pathlib

import numpy as np

import perpmicro_sweep as ps
from perpmicro_sweep import roll_sum, noise_bar, window_mask, run_window, _corr
import perpmicro_r3 as r3

OUT = pathlib.Path(__file__).resolve().parents[2] / "research" / "trading_bot"


def main():
    p = r3.build("A", 60, 20)
    U = p.univ
    f168 = roll_sum(p.fpaid, 168)
    net = (p.r168 - f168).astype(np.float32)
    F = [
        ("M_ONLY", p.r168, 24, "quintile", None, "7d log return (= round 1 XS_MOM168)"),
        ("F_ONLY", (-f168).astype(np.float32), 24, "quintile", None,
         "minus 7d realised funding paid"),
        ("NETCARRY", net, 24, "quintile", None, "r168 - funding paid (round-3 formula)"),
        ("NETCARRY_K3", (p.r168 - 3.0 * f168).astype(np.float32), 24, "quintile", None,
         "r168 - 3x funding paid"),
        ("NC_RESID_M", r3.xs_resid(net, p.r168, U), 24, "quintile", None,
         "XS residual of netcarry on r168"),
        ("M_RESID_F", r3.xs_resid(p.r168, (-f168).astype(np.float32), U), 24, "quintile", None,
         "XS residual of r168 on the carry term"),
    ]
    out = {}
    signs = None
    store = {}
    for tag, w in [("design", r3.DESIGN_A), ("holdout", r3.HOLD_A)]:
        m = window_mask(p.t, *w)
        res, mat = run_window(F, p, m, signs=signs)
        if tag == "design":
            signs = {r["name"]: r["sign"] for r in res}
        for r, row in zip(res, mat):
            store.setdefault(tag, {})[r["name"]] = r["sign"] * row
        out[tag] = {"range": list(w), "results": res}
        print(f"--- {tag}")
        for r in res:
            print(f"  {r['name']:14s} net {r['sharpe_net']:+6.2f} gross {r['sharpe_gross']:+6.2f} "
                  f"be {r['breakeven_cost_bp_per_side']:6.1f} tpd {r['turnover_per_day']:.2f} "
                  f"sign {r['sign']:+.0f}")
        c = {}
        names = list(store[tag])
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                c[f"{a}|{b}"] = _corr(store[tag][a], store[tag][b])
        out[tag]["corr"] = c
        get = lambda a, b: c.get(f"{a}|{b}", c.get(f"{b}|{a}", float("nan")))
        print("  corr NETCARRY-M_ONLY", round(get("NETCARRY", "M_ONLY"), 4),
              " NETCARRY-F_ONLY", round(get("NETCARRY", "F_ONLY"), 3),
              " NC_RESID_M-M_ONLY", round(get("NC_RESID_M", "M_ONLY"), 3))
    (OUT / "INVENT_R3_perpstructure_ATTRIB.json").write_text(json.dumps(out, indent=1))
    print("wrote attrib")


if __name__ == "__main__":
    main()
