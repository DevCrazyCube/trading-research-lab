#!/usr/bin/env python3
"""INVENT R3 flow -- diagnostics on the only family that survived the design pass.

Three questions the sweep itself cannot answer:

  1. EXECUTABILITY.  C1/C2/C3/C4 form their signal from the CLOSING AUCTION PRINT
     and then enter at that same print.  You cannot observe an auction's clearing
     price and trade in that auction.  Two honest, strictly-executable variants
     are scored here (entry at the NEXT opening auction), plus a cost ladder for
     the post-close entry that the signal actually requires.
  2. NOVELTY.  How much of it is leg L1 (T3 overnight reversal of the last-30-min
     move) wearing a different hat?
  3. STABILITY.  Sub-period Sharpes.
"""
from __future__ import annotations

import json
import math
import sys

import numpy as np

sys.path.insert(0, "/home/anont/meme")
from scripts.invr3_flow_eval import (   # noqa: E402
    build_intraday_panel, half_spread_bp, zscore_ts, xs_rank_weights,
    book_pnl, sharpe, trailing_median_ratio, winsor, month_flags,
    DESIGN_END_I, HOLD_START_I, OUT,
)


def main():
    I = build_intraday_panel()
    ii = np.array(I.dates)
    mD = ii <= DESIGN_END_I
    mH = ii >= HOLD_START_I
    hs = half_spread_bp(I.DV)

    scaleC = trailing_median_ratio(I.AUC, I.C1555)
    scaleO = trailing_median_ratio(I.AUO, I.C0)
    AUCi, AUOi = I.AUC / scaleC, I.AUO / scaleO

    disl = winsor(AUCi / I.C1555 - 1.0, 0.05)
    r30 = winsor(I.C1555 / I.C1530 - 1.0, 0.15)
    T, K = disl.shape
    nan1 = np.full((1, K), np.nan)
    ON = winsor(np.vstack([AUOi[1:], nan1]) / AUCi - 1.0, 0.15)          # close t -> open t+1
    O2C = winsor(np.vstack([AUCi[1:], nan1]) / np.vstack([AUOi[1:], nan1]) - 1.0, 0.20)
    O2O = winsor(np.vstack([AUOi[2:], np.full((2, K), np.nan)])
                 / np.vstack([AUOi[1:], nan1]) - 1.0, 0.20)

    # cross-sectional residual of the auction dislocation on the last-30-min move
    resid = np.full_like(disl, np.nan)
    for t in range(T):
        y, x = disl[t], r30[t]
        ok = np.isfinite(y) & np.isfinite(x)
        if ok.sum() < 20:
            continue
        X = np.column_stack([np.ones(int(ok.sum())), x[ok]])
        b = np.linalg.lstsq(X, y[ok], rcond=None)[0]
        resid[t, ok] = y[ok] - X @ b
    zr = zscore_ts(resid, 60)
    z30 = zscore_ts(r30, 60)

    def score(W, R, mask, rt, hs_override=None, borrow=True):
        h = hs if hs_override is None else np.full(K, hs_override)
        Wm = W.copy()
        Wm[~mask] = 0.0
        net, gross, turn, live = book_pnl(Wm, R, h, borrow=borrow, roundtrip=rt)
        return net[mask], gross[mask], turn[mask]

    out = {}

    # ---- 1. the T3 control on the very same panel/window/cost ------------
    Wt3 = xs_rank_weights(-z30, min_names=20)
    Wc2 = xs_rank_weights(-zr, min_names=20)
    for tag, mask in (("design", mD), ("holdout", mH)):
        n3, g3, _ = score(Wt3, ON, mask, True)
        n2, g2, _ = score(Wc2, ON, mask, True)
        both = np.isfinite(n3) & np.isfinite(n2)
        corr = float(np.corrcoef(n3[both], n2[both])[0, 1])
        # C2 orthogonalised to the T3 control, day by day
        A = np.column_stack([np.ones(both.sum()), n3[both]])
        beta = np.linalg.lstsq(A, n2[both], rcond=None)[0]
        orth = n2[both] - A @ beta + beta[0]
        out[f"T3_control_{tag}"] = dict(
            t3_net_sharpe=round(sharpe(n3), 4), t3_gross_sharpe=round(sharpe(g3), 4),
            c2_net_sharpe=round(sharpe(n2), 4),
            corr_c2_t3=round(corr, 4),
            c2_net_sharpe_orthogonal_to_t3=round(sharpe(orth), 4),
            c2_mean_bp=round(float(np.nanmean(n2)) * 1e4, 3),
            c2_orth_mean_bp=round(float(np.nanmean(orth)) * 1e4, 3))

    # ---- 2. strictly executable variants (entry at the NEXT open print) --
    for name, R, rt in (("C5_AUCT_RESID_OPEN_TO_CLOSE", O2C, True),
                        ("C6_AUCT_RESID_OPEN_TO_OPEN", O2O, True)):
        row = {}
        for tag, mask in (("design", mD), ("holdout", mH)):
            n_, g_, t_ = score(Wc2, R, mask, rt)
            row[tag] = dict(net_sharpe=round(sharpe(n_), 4),
                            gross_sharpe=round(sharpe(g_), 4),
                            gross_bp=round(float(np.nanmean(g_)) * 1e4, 3),
                            turn=round(float(np.nanmean(t_)), 3))
        out[name] = row

    # ---- 3. cost ladder for the post-close entry the signal requires -----
    ladder = {}
    for bp in (0.0, 1.0, 1.38, 2.0, 3.0, 5.0, 8.0, 12.0):
        row = {}
        for tag, mask in (("design", mD), ("holdout", mH)):
            n_, g_, t_ = score(Wc2, ON, mask, True, hs_override=bp)
            row[tag] = round(sharpe(n_), 3)
        ladder[f"{bp:g}bp_per_side"] = row
    out["C2_cost_ladder_net_sharpe"] = ladder
    out["C2_note"] = ("entry price is the closing auction print that the signal is "
                      "measured FROM, so the only real entry is the post-close session; "
                      "the ladder above is what that entry has to beat")

    # ---- 4. stability by calendar year ----------------------------------
    yrs = {}
    n_, g_, t_ = score(Wc2, ON, np.ones(T, bool), True)
    for y in sorted({d[:4] for d in I.dates}):
        m = np.array([d[:4] == y for d in I.dates])
        v = n_[m]
        if np.isfinite(v).sum() > 60:
            yrs[y] = dict(net_sharpe=round(sharpe(v), 3),
                          mean_bp=round(float(np.nanmean(v)) * 1e4, 3))
    out["C2_by_year_net"] = yrs

    # ---- 5. is the dislocation itself the thing, or a stale 15:55 bar? ---
    #  If the 5-minute cache's last bar simply ends before the last continuous
    #  prints, `disl` is a staleness artefact and should shrink as the name gets
    #  more liquid.  Split the universe by median dollar volume.
    med = np.nanmedian(I.DV, axis=0)
    hi = med >= np.nanmedian(med)
    for tag, sel, lab in ((mD, hi, "design_liquid_half"), (mD, ~hi, "design_illiquid_half"),
                          (mH, hi, "holdout_liquid_half"), (mH, ~hi, "holdout_illiquid_half")):
        S = np.where(sel[None, :], zr, np.nan)
        W = xs_rank_weights(-S, min_names=10)
        n_, g_, t_ = score(W, ON, tag, True)
        out.setdefault("C2_liquidity_split", {})[lab] = dict(
            net_sharpe=round(sharpe(n_), 3), gross_sharpe=round(sharpe(g_), 3),
            gross_bp=round(float(np.nanmean(g_)) * 1e4, 3),
            median_abs_disloc_bp=round(float(np.nanmedian(np.abs(disl[:, sel]))) * 1e4, 2))

    (OUT / "INVENT_R3_flow_diagnostics.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
