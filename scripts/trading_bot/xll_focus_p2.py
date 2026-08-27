#!/usr/bin/env python3
"""Focused pass on P2 -- the only equity formula that clearly beat its noise bar.

Three questions the sweep table cannot answer:
  1. What per-side cost turns it off? (the sweep charged one rung; the open auction is worse)
  2. Is the SPY-beta neutralisation -- the cross-asset part, which is what this THEME claims --
     doing any work at all, or is it a plain single-name overnight reversal wearing a lead-lag hat?
  3. Does it hold on liquid names only, where a 5bp/side fill is defensible?
"""
import json, sys
import numpy as np
sys.path.insert(0, "/home/anont/meme/scripts/trading_bot")
import xll_sweep_equity as X

OUT = "/home/anont/meme/research/trading_bot/SWEEP_xll_equity_P2_FOCUS.json"
c = X.build_ctx()
I = c.idx
ann = np.sqrt(252.0)


def evaluate(W, tr, tag):
    W = X.gross1(np.where(tr, W, 0.0))
    pr = np.einsum("it,it->t", W, c.roc).astype(np.float64)
    dW = np.abs(W - X.lag(W, 1)).sum(0)
    d = c.design
    row = {"variant": tag, "turnover_per_day": float(dW[d].mean()),
           "design_gross_bp_per_day": float(pr[d].mean() * 1e4),
           "holdout_gross_bp_per_day": float(pr[~d].mean() * 1e4)}

    def sh(x, m):
        x = x[m]
        return 0.0 if x.std() == 0 else float(x.mean() / x.std() * ann)
    row["design_gross_sharpe"] = sh(pr, d)
    row["holdout_gross_sharpe"] = sh(pr, ~d)
    for cbp in (0, 2, 5, 7, 10, 15, 20):
        net = pr - dW * (cbp * 1e-4)
        row[f"design_net_sharpe_{cbp}bp"] = sh(net, d)
        row[f"holdout_net_sharpe_{cbp}bp"] = sh(net, ~d)
    tot = dW[d].mean()
    row["breakeven_cost_bp_per_side_design"] = float(pr[d].mean() / tot * 1e4) if tot > 0 else None
    tot_h = dW[~d].mean()
    row["breakeven_cost_bp_per_side_holdout"] = float(pr[~d].mean() / tot_h * 1e4) if tot_h > 0 else None
    return row


rows = []
tr = c.tradable_oc
resid = c.rovn - c.beta["SPY_OVN"] * c.rovn[I["SPY"]][None, :]
rows.append(evaluate(-X.xs_demean(resid, tr), tr, "P2 as swept: SPY-beta-neutralised overnight gap, faded open->close"))
rows.append(evaluate(-X.xs_demean(c.rovn, tr), tr,
                     "NO cross-asset term at all: fade the raw overnight gap, XS-demeaned"))
rows.append(evaluate(-X.xs_demean(c.rovn - c.rovn[I["SPY"]][None, :], tr), tr,
                     "beta forced to 1 instead of estimated"))
rows.append(evaluate(-X.rank_xs(resid, tr), tr, "rank of the residual gap instead of its size"))

liq = X.rank_xs(c.adv, tr)
for cut, lbl in ((0.0, "top HALF by dollar volume"), (0.6, "top QUINTILE by dollar volume")):
    m = tr & (liq > cut)
    rows.append(evaluate(-X.xs_demean(resid, m), m, f"P2 restricted to the {lbl}"))

json.dump({"formula": "P2_ovn_gap_reversal", "design_window": ["2016-01-05", "2021-12-31"],
           "holdout_window": ["2022-01-03", "2026-08-14"], "rows": rows}, open(OUT, "w"), indent=1)
for r in rows:
    print(f"{r['variant'][:58]:60s} dsgnSR={r['design_gross_sharpe']:+5.2f} HO_SR={r['holdout_gross_sharpe']:+5.2f} "
          f"tno={r['turnover_per_day']:.2f} BE_cost_design={r['breakeven_cost_bp_per_side_design']:.2f}bp "
          f"BE_holdout={r['breakeven_cost_bp_per_side_holdout']:.2f}bp "
          f"net@5bp d/h={r['design_net_sharpe_5bp']:+.2f}/{r['holdout_net_sharpe_5bp']:+.2f} "
          f"net@10bp d/h={r['design_net_sharpe_10bp']:+.2f}/{r['holdout_net_sharpe_10bp']:+.2f}")
print("WROTE", OUT)
