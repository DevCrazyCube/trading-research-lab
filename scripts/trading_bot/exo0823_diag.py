#!/usr/bin/env python3
"""Post-reveal diagnostics for INVENT_0823: is the surviving carry a disguised beta?"""
from __future__ import annotations

import json
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from trading_bot import exo0823_sweep as S  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]

TARGETS = ["L7_lev_decay_carry", "L8_bullbear_shortboth", "C7_feecarry_btc",
           "C8_feecarry_eth", "C9_feecarry_pooled", "F5_fof_fee_carry"]


def reg(y, x):
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    m = np.isfinite(x) & np.isfinite(y)
    x, y = x[m], y[m]
    if len(x) < 30:
        return None
    A = np.column_stack([np.ones_like(x), x])
    coef, *_ = np.linalg.lstsq(A, y, rcond=None)
    resid = y - A @ coef
    se = np.sqrt(np.sum(resid ** 2) / (len(x) - 2) / np.sum((x - x.mean()) ** 2))
    return {"beta": float(coef[1]), "t_beta": float(coef[1] / se) if se > 0 else 0.0,
            "corr": float(np.corrcoef(x, y)[0, 1]),
            "alpha_bp_day": float(coef[0] * 1e4),
            "alpha_t": float(coef[0] / (resid.std(ddof=2) / np.sqrt(len(x))))}


def main():
    panel = S.build_panel()
    master, px = panel["dates"], panel["px"]
    idx = {k: S.date_index(master, v) for k, v in
           {"d0": S.D0, "d1": S.D1, "h0": S.H0, "h1": S.H1,
            "cd0": S.CD0, "cd1": S.CD1, "ch0": S.CH0, "ch1": S.CH1}.items()}
    hs = {}
    for s in px:
        v = S.corwin_schultz_halfspread(px[s]["h"], px[s]["l"], idx["d0"], idx["h1"])
        hs[s] = max(S.SPREAD_FLOOR_BP, v) if np.isfinite(v) else 25.0
    specs, placebos, ctrls, prims = S.build_all(panel)

    def openret(sym):
        O = px[sym]["o"]
        r = np.full(len(O), np.nan)
        r[:-1] = O[1:] / O[:-1] - 1
        return r

    spy, ibit, eth = openret("SPY"), openret("IBIT"), openret("ETHA")
    out = {}
    for name, fam, syms, raw, H in specs:
        if name not in TARGETS:
            continue
        W = S.normalise_and_stagger(raw, H)
        rec = {}
        for wl, (a, b) in (("design", ("cd0", "cd1") if fam == "C" else ("d0", "d1")),
                           ("heldout", ("ch0", "ch1") if fam == "C" else ("h0", "h1"))):
            st = S.evaluate(W, syms, px, hs, idx[a], idx[b])
            pnl = st["_net"]
            sl = slice(idx[a], idx[b])
            rec[wl] = {"net_sharpe": st["net_sharpe"],
                       "vs_SPY": reg(pnl, spy[sl]),
                       "vs_IBIT": reg(pnl, ibit[sl]) if np.isfinite(ibit[sl]).sum() > 50 else None,
                       "vs_ETHA": reg(pnl, eth[sl]) if np.isfinite(eth[sl]).sum() > 50 else None,
                       "worst_day_bp": float(pnl.min() * 1e4),
                       "best_day_bp": float(pnl.max() * 1e4),
                       "pct_days_positive": float((pnl > 0).mean()),
                       "max_drawdown_bp": float((np.maximum.accumulate(np.cumsum(pnl))
                                                 - np.cumsum(pnl)).max() * 1e4)}
        out[name] = rec
    p = ROOT / "research" / "trading_bot" / "INVENT_0823_exotic_DIAG.json"
    p.write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
