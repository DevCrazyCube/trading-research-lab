#!/usr/bin/env python3
"""INVENT R3 phase 3 -- the two survivors of phases 1-2, stress-tested.

A. SIDE conditioning of T3, BETA-CONTROLLED. Phase 2's `SIDE_LONGONLY_HI` beat the raw leg
   both in design and out of sample -- but an un-hedged long half in a bull tape earns the
   overnight equity risk premium, which is on the DEAD ledger (overnight-harvest). The honest
   version subtracts the realised net exposure times the equal-weight universe overnight
   return (`control`), which is exactly that premium. If the lift survives, it is alpha.

B. The 3-leg ensemble, against the DIVERSIFICATION-ONLY null: the Sharpe you would predict
   from the legs' own held-out Sharpes and their DESIGN correlation matrix. If realised ~=
   predicted, combining added nothing a spreadsheet could not have told you in advance.
"""
from __future__ import annotations
import json, math, pathlib, datetime, sys
import numpy as np

ROOT = pathlib.Path("/home/anont/meme"); sys.path.insert(0, str(ROOT))
from scripts.invent_r3_conditioning import (   # noqa: E402
    load_legs, build_conditioners, ann_sharpe, to_weekly, DESIGN_END, HOLD_START, OUT)

COST = (1.43 + 0.31) / 1e4


def main():
    legs = load_legs()
    t3 = legs["T3"]
    dates = t3["dates"]
    d = np.array(dates)
    dm, hm = d <= DESIGN_END, d >= HOLD_START
    L, S, ctrl = t3["long"], t3["short"], t3["ctrl"]
    C = build_conditioners(dates)
    out = {"side_beta_controlled": [], "diversification_null": {}, "correlations": {}}

    base = 0.5 * L - 0.5 * S - COST
    for cname in ("SPY_TREND200", "VIX_TERM", "SPY_MOM20", "VIX_LEVEL"):
        v = C[cname]
        fin = np.isfinite(v)
        thr = float(np.median(v[dm & fin]))
        hi = (v > thr) & fin
        for label, (wl_hi, ws_hi), (wl_lo, ws_lo) in (
                ("LONGONLY_HI", (1.0, 0.0), (0.5, 0.5)),
                ("SIDE_TILT", (0.75, 0.25), (0.25, 0.75))):
            wl = np.where(hi, wl_hi, wl_lo)
            ws = np.where(hi, ws_hi, ws_lo)
            raw_book = wl * L - ws * S - COST
            beta = wl - ws                                  # net long exposure
            hedged = raw_book - beta * ctrl                 # subtract the overnight premium
            rec = {"cond": cname, "variant": label}
            for lbl, msk in (("design", dm & fin), ("holdout", hm & fin)):
                rec[lbl] = {
                    "sharpe_unhedged": ann_sharpe(raw_book[msk], 252),
                    "sharpe_BETA_HEDGED": ann_sharpe(hedged[msk], 252),
                    "sharpe_raw_neutral_leg": ann_sharpe(base[msk], 252),
                    "d_sharpe_hedged_vs_raw": ann_sharpe(hedged[msk], 252) - ann_sharpe(base[msk], 252),
                    "mean_hedged_bp": float(hedged[msk].mean() * 1e4),
                    "mean_beta_contrib_bp": float((beta * ctrl)[msk].mean() * 1e4),
                    "avg_net_exposure": float(beta[msk].mean()),
                }
            out["side_beta_controlled"].append(rec)

    # ---- half-by-half: is the T3 LONG half or SHORT half carrying the edge? ---------
    halves = {}
    for lbl, msk in (("design", dm), ("holdout", hm)):
        halves[lbl] = {
            "long_half_vs_ctrl_bp": float((L - ctrl)[msk].mean() * 1e4),
            "short_half_vs_ctrl_bp": float((ctrl - S)[msk].mean() * 1e4),
            "long_half_t": float((L - ctrl)[msk].mean() / (L - ctrl)[msk].std(ddof=1) * math.sqrt(msk.sum())),
            "short_half_t": float((ctrl - S)[msk].mean() / (ctrl - S)[msk].std(ddof=1) * math.sqrt(msk.sum())),
            "ctrl_mean_bp": float(ctrl[msk].mean() * 1e4),
        }
    out["t3_halves"] = halves

    # ---- B. diversification-only null -----------------------------------
    wk = {}
    for name, leg in legs.items():
        if leg["ppy"] == 52:
            w = {}
            for dd, x in zip(leg["dates"], leg["net"]):
                dt = datetime.date.fromisoformat(dd)
                w[(dt - datetime.timedelta(days=dt.weekday())).isoformat()] = float(x)
            wk[name] = w
        else:
            wk[name] = to_weekly(leg["dates"], leg["net"])
    cef_start = min(wk["CEF"])
    keys = sorted(k for k in set().union(*[set(v) for v in wk.values()]) if k >= cef_start)
    kd = np.array(keys)
    dmw, hmw = kd <= DESIGN_END, kd >= HOLD_START
    names = ["T3", "T7D1", "CEF"]
    V = {n: np.array([wk[n].get(k, 0.0) for k in keys]) for n in names}
    sd_d = {n: (V[n][dmw].std(ddof=1) or 1.0) for n in names}
    Z = {n: V[n] / sd_d[n] for n in names}
    Cd = np.corrcoef(np.vstack([Z[n][dmw] for n in names]))
    Ch = np.corrcoef(np.vstack([Z[n][hmw] for n in names]))
    out["correlations"] = {"design": Cd.tolist(), "holdout": Ch.tolist(), "order": names}

    sr_h = {n: ann_sharpe(Z[n][hmw], 52) for n in names}
    w = np.array([1 / 3, 1 / 3, 1 / 3])
    # predicted combined Sharpe using each leg's OWN holdout Sharpe but the DESIGN corr matrix
    num = sum(w[i] * sr_h[names[i]] for i in range(3))
    den = math.sqrt(float(w @ Cd @ w))
    pred_design_corr = num / den
    den_h = math.sqrt(float(w @ Ch @ w))
    pred_hold_corr = num / den_h
    eq = sum(w[i] * Z[names[i]] for i in range(3))
    out["diversification_null"] = {
        "leg_holdout_sharpes": sr_h,
        "realised_equal_risk_holdout_sharpe": ann_sharpe(eq[hmw], 52),
        "predicted_from_DESIGN_corr": pred_design_corr,
        "predicted_from_HOLDOUT_corr": pred_hold_corr,
        "lift_over_best_single_leg": ann_sharpe(eq[hmw], 52) - max(sr_h.values()),
        "excess_over_diversification_prediction": ann_sharpe(eq[hmw], 52) - pred_design_corr,
        "n_weeks_holdout": int(hmw.sum()), "n_weeks_design": int(dmw.sum()),
    }
    # equal-risk on the two long-history daily legs only, on the FULL daily calendar
    keys2 = sorted(set(wk["T3"]) | set(wk["T7D1"]))
    k2 = np.array(keys2)
    V2 = {n: np.array([wk[n].get(k, 0.0) for k in keys2]) for n in ("T3", "T7D1")}
    d2, h2 = k2 <= DESIGN_END, k2 >= HOLD_START
    sd2 = {n: (V2[n][d2].std(ddof=1) or 1.0) for n in V2}
    e2 = 0.5 * V2["T3"] / sd2["T3"] + 0.5 * V2["T7D1"] / sd2["T7D1"]
    out["two_leg_full_history"] = {
        "design_sharpe": ann_sharpe(e2[d2], 52), "holdout_sharpe": ann_sharpe(e2[h2], 52),
        "T3_design": ann_sharpe(V2["T3"][d2], 52), "T3_holdout": ann_sharpe(V2["T3"][h2], 52),
        "T7_design": ann_sharpe(V2["T7D1"][d2], 52), "T7_holdout": ann_sharpe(V2["T7D1"][h2], 52),
        "design_corr": float(np.corrcoef(V2["T3"][d2], V2["T7D1"][d2])[0, 1]),
        "holdout_corr": float(np.corrcoef(V2["T3"][h2], V2["T7D1"][h2])[0, 1]),
        "n_weeks_design": int(d2.sum()), "n_weeks_holdout": int(h2.sum()),
    }

    (OUT / "INVENT_R3_condition_combine_phase3.json").write_text(json.dumps(out, indent=1))
    print("=== SIDE, BETA-CONTROLLED ===")
    for r in out["side_beta_controlled"]:
        dd, hh = r["design"], r["holdout"]
        print(f"{r['cond']:14s} {r['variant']:12s} | design unhedged {dd['sharpe_unhedged']:+.2f} "
              f"HEDGED {dd['sharpe_BETA_HEDGED']:+.2f} (raw {dd['sharpe_raw_neutral_leg']:+.2f}) "
              f"|| HOLD unhedged {hh['sharpe_unhedged']:+.2f} HEDGED {hh['sharpe_BETA_HEDGED']:+.2f} "
              f"(raw {hh['sharpe_raw_neutral_leg']:+.2f}, d {hh['d_sharpe_hedged_vs_raw']:+.2f}) "
              f"beta gave {hh['mean_beta_contrib_bp']:+.2f} bp")
    print("\n=== T3 HALVES vs the equal-weight universe ===")
    print(json.dumps(halves, indent=1))
    print("\n=== DIVERSIFICATION NULL ===")
    print(json.dumps(out["diversification_null"], indent=1))
    print("\ncorr design:", np.round(Cd, 3).tolist(), "\ncorr hold  :", np.round(Ch, 3).tolist())
    print("\n=== TWO-LEG, FULL HISTORY ===")
    print(json.dumps(out["two_leg_full_history"], indent=1))


if __name__ == "__main__":
    main()
