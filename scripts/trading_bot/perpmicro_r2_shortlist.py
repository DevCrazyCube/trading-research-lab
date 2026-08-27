#!/usr/bin/env python3
"""Is the round-2 shortlist several findings or one bet?

Recomputes the DAILY net P&L of the shortlist on the virgin held-out window and reports the
correlation matrix, plus each one's correlation to (a) the equal-weight perp basket and
(b) a long-majors/short-alts proxy (the cross-sectional low-idiosyncratic-vol book), which is
what a 2025-26 BTC-dominance regime would look like if it leaked into everything.
"""
from __future__ import annotations

import json
import pathlib

import numpy as np

import perpmicro_sweep as ps
import perpmicro_sweep2 as s2
from perpmicro_sweep import evaluate, to_daily, sharpe, window_mask

SHORT = ["X2_FLOWSTREAK", "X2_TOD_FLOW_EU", "X2_IDIOVOL", "X2_FLOW_VA", "X2_UPWICK",
         "X2_WICKASYM", "X2_RESID_MOM", "X2_KYLE", "X2_FUNDPATH_REV", "X2_RESID_REV",
         "X2_KYLE_RES"]
OUT = (pathlib.Path(__file__).resolve().parents[2] / "research" / "trading_bot"
       / "SWEEP_crypto_perp_microstructure_R2_SHORTLIST.json")


def daily(F, p, name, wmask, sign, cost):
    ndays = p.NH // 24
    dm = wmask[:ndays * 24].reshape(-1, 24).any(axis=1)
    for n, x, H, sc, tm, cl, desc in F:
        if n != name:
            continue
        if x.ndim == 1:
            x = np.broadcast_to(x[None, :], (p.S, p.NH))
        x = np.ascontiguousarray(x.astype(np.float32))
        t = np.asarray(tm) if (tm is not None and np.ndim(tm) == 1) else None
        pnl, pf, dh = evaluate(x, p, H, sc, t)
        g = sign * (to_daily(pnl, p.NH)[dm] + to_daily(pf, p.NH)[dm])
        return g - to_daily(dh, p.NH)[dm] * cost * 1e-4
    raise KeyError(name)


def main():
    des = json.loads((pathlib.Path(__file__).resolve().parents[2] / "research" / "trading_bot"
                      / "SWEEP_crypto_perp_microstructure_R2_ext_top50_holdout.json").read_text())
    signs = {r["name"]: r["sign"] for r in des["design"]}
    pan = np.load(s2.PANEL_X, allow_pickle=True)
    p = s2.build2(pan, False, 50, 25)
    F = s2.catalogue2(p)
    wm = window_mask(p.t, *s2.HOLD2)
    ndays = p.NH // 24
    dm = wm[:ndays * 24].reshape(-1, 24).any(axis=1)
    nlive = np.maximum(p.univ.sum(0), 1)
    mkt = to_daily((np.where(p.univ, p.ret, 0.0).sum(0) / nlive).astype(np.float64), p.NH)[dm]

    ser = {n: daily(F, p, n, wm, signs[n], 5.5) for n in SHORT}
    names = list(ser)
    M = np.array([ser[n] for n in names])
    C = np.corrcoef(M)
    out = {"window": list(s2.HOLD2), "names": names,
           "net_sharpe_5p5bp": {n: sharpe(ser[n]) for n in names},
           "corr_to_equalweight_basket": {n: float(np.corrcoef(ser[n], mkt)[0, 1]) for n in names},
           "corr_to_X2_IDIOVOL": {n: float(C[names.index(n), names.index("X2_IDIOVOL")])
                                  for n in names},
           "corr_matrix": C.round(3).tolist(),
           "mean_abs_offdiag_corr": float(np.abs(C[~np.eye(len(names), dtype=bool)]).mean())}
    # equal-weight composite of the three that cleared the bar AND stayed positive at 15 bp
    core = ["X2_FLOWSTREAK", "X2_TOD_FLOW_EU", "X2_IDIOVOL"]
    comp = np.mean([ser[n] for n in core], axis=0)
    out["composite_core"] = {"members": core, "net_sharpe_5p5bp": sharpe(comp),
                             "ann_net": float(np.mean(comp) * 365),
                             "corr_to_basket": float(np.corrcoef(comp, mkt)[0, 1])}
    OUT.write_text(json.dumps(out, indent=1))
    print(json.dumps({k: v for k, v in out.items() if k != "corr_matrix"}, indent=1))
    print("\ncorr matrix (order:", names, ")")
    for i, n in enumerate(names):
        print(f"{n:18s} " + " ".join(f"{C[i, j]:+.2f}" for j in range(len(names))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
