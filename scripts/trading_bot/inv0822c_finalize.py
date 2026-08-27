#!/usr/bin/env python3
"""INVENT_0822C -- verdict layer.

Adds three things the raw sweep does not have:
  1. GROSS robustness   -- rerun every overlay on the legs' GROSS series.
  2. OVERLAY REBALANCE COST -- an overlay that re-weights the book has to TRADE.
     Legs that fully unwind every session (T3, T7D1, ORB, ETFRV) can be re-sized for
     free -- you just send a different notional tomorrow.  Legs that hold a position
     across sessions (DUALCLASS, CEF) must actually trade the delta.  Charged at the
     leg's own measured one-way cost.
  3. The pooled bar + the size-matched placebo, stated together.
"""
from __future__ import annotations
import json, math, pathlib, sys
import numpy as np
import importlib.util

ROOT = pathlib.Path("/home/anont/meme")
CACHE = ROOT / "research/data/inv0822c_cache"
OUT = ROOT / "research/trading_bot"

spec = importlib.util.spec_from_file_location("ov", ROOT / "scripts/trading_bot/inv0822c_overlay.py")
ov = importlib.util.module_from_spec(spec); spec.loader.exec_module(ov)

# one-way execution cost (bp of leg notional) and whether the leg holds overnight
LEG_COST_BP = {"T3": 0.87, "T7D1": 0.60, "ORB": 4.65, "ETFRV": 0.60,
               "DUALCLASS": 5.00, "CEF": 5.77}
LEG_HOLDS = {"T3": False, "T7D1": False, "ORB": False, "ETFRV": False,
             "DUALCLASS": True, "CEF": True}


def build_gross_panel(cfg):
    names = cfg["legs"]; weekly = cfg.get("weekly", False)
    per = {}
    for nm in names:
        L = ov.LEGS[nm]
        g = L.get("gross", L["net"])
        if weekly:
            agg = {}
            for d, v in zip(L["dates"], g):
                k = d if L.get("weekly") else ov.week_key(d)
                agg[k] = agg.get(k, 0.0) + v
            per[nm] = agg
        else:
            per[nm] = dict(zip(L["dates"], g))
    lo = max(min(per[n]) for n in names); hi = min(max(per[n]) for n in names)
    allk = sorted({k for n in names for k in per[n] if lo <= k <= hi})
    R = np.zeros((len(names), len(allk)))
    for i, nm in enumerate(names):
        for j, k in enumerate(allk):
            R[i, j] = per[nm].get(k, 0.0)
    return names, np.array(allk), R


def weight_paths(S, W0, LIVE, dates, ppy, names, ctx):
    """re-derive the WEIGHT matrix for the weight-changing overlays so the rebalance
    cost can be charged.  Book-level scalers get a scalar path instead."""
    N, T = S.shape
    base = ov.apply_w(S, W0)

    def norm_w(W):
        t = np.abs(W).sum(axis=0); t[t == 0] = 1.0
        return W / t

    W = {}
    for lb in (60, 120):
        SD = np.vstack([ov.trail_sd(S[i], lb) for i in range(N)])
        Wi = np.where(np.isfinite(SD) & (SD > 1e-12), 1.0 / np.maximum(SD, 1e-12), np.nan)
        Wi = np.where(np.isfinite(Wi), Wi, 1.0)
        W[f"OV_RP{lb}"] = norm_w(Wi)
        if lb == 60:
            W["OV_RP60_CAP40"] = norm_w(np.minimum(norm_w(Wi), 0.40))
            W["OV_SQRTVOL60"] = norm_w(np.sqrt(Wi))
            W["OV_RP60_INV"] = norm_w(np.where(np.isfinite(SD), SD, 1.0))
    SDx = np.vstack([ov.expand_sd(S[i]) for i in range(N)])
    Wi = np.where(np.isfinite(SDx) & (SDx > 1e-12), 1.0 / np.maximum(SDx, 1e-12), 1.0)
    W["OV_RP_EXPAND"] = norm_w(Wi)
    return W, base


def rebalance_cost(Wpath, W0, names, sd_design):
    """bp per period the overlay pays JUST to move weights, on the holding legs."""
    dW = np.abs(np.diff(Wpath, axis=1))
    dW0 = np.abs(np.diff(W0, axis=1))
    extra = np.zeros(Wpath.shape[1])
    for i, nm in enumerate(names):
        if not LEG_HOLDS.get(nm, False):
            continue
        extra[1:] += (dW[i] - dW0[i]) * LEG_COST_BP[nm] * 1e-4
    return np.clip(extra, 0, None)


def main():
    raw = json.load(open(CACHE / "overlay_raw.json"))
    report = {"theme": raw["theme"], "n_formulas_tested": raw["n_formulas_tested"],
              "expected_max_sigma_analytic_sqrt2lnN": raw["expected_max_sigma_analytic"],
              "panels": {}}

    for pn, cfg in ov.PANELS.items():
        pr = raw["panels"][pn]
        ppy = cfg["ppy"]
        # ---- gross rerun
        names, dates, Rg = build_gross_panel(cfg)
        Sg, W0g, _ = ov.base_book(Rg, dates, cfg["design_end"])
        ctx = {"spy_ex": ov.spy_exposure(dates)}
        bg, baseg = ov.overlays(Sg, W0g, np.ones(Rg.shape, bool), dates, ppy, names, ctx)
        dmg = dates <= cfg["design_end"]; hmg = dates >= cfg["hold_start"]
        gross = {}
        sb_h = ov.sharpe(baseg[hmg], ppy); sb_f = ov.sharpe(baseg, ppy)
        for nm, b in bg.items():
            gross[nm] = {"d_holdout_gross": ov.sharpe(b[hmg], ppy) - sb_h,
                         "d_full_gross": ov.sharpe(b, ppy) - sb_f}
        gross_base = {"holdout": sb_h, "full": sb_f}

        # ---- rebalance cost on the weight-changing overlays
        namesn, datesn, Rn, LIVE = ov.build_panel(cfg)
        Sn, W0n, sdn = ov.base_book(Rn, datesn, cfg["design_end"])
        ctxn = {"spy_ex": ov.spy_exposure(datesn)}
        Wp, basen = weight_paths(Sn, W0n, LIVE, datesn, ppy, namesn, ctxn)
        booksn, _ = ov.overlays(Sn, W0n, LIVE, datesn, ppy, namesn, ctxn)
        dmn = datesn <= cfg["design_end"]; hmn = datesn >= cfg["hold_start"]
        sbn_h = ov.sharpe(basen[hmn], ppy)
        netcost = {}
        for nm, Wpath in Wp.items():
            c = rebalance_cost(Wpath, W0n, namesn, sdn)
            # cost is in bp of LEG notional -> convert to the risk-scaled book units
            scale = float(np.mean([1.0 / max(sdn[i], 1e-12) for i in range(len(namesn))]))
            b = booksn[nm] - c * scale
            netcost[nm] = {
                "mean_rebal_cost_bp": float(c.mean() * 1e4),
                "d_holdout_after_rebal_cost": ov.sharpe(b[hmn], ppy) - sbn_h,
            }

        for r in pr["results"]:
            r["gross"] = gross.get(r["overlay"])
            r["rebal"] = netcost.get(r["overlay"])
        pr["gross_base"] = gross_base
        report["panels"][pn] = pr

    # ---------------- pooled verdict
    best = None
    for pn, pr in report["panels"].items():
        p95 = pr["placebo_null"]["max_dSharpe_holdout_p95"]
        for r in pr["results"]:
            r["beats_placebo_p95"] = bool(np.isfinite(r["d_holdout"]) and r["d_holdout"] > p95)
            r["panel"] = pn
            if best is None or (np.isfinite(r["d_holdout"]) and r["d_holdout"] > best["d_holdout"]):
                best = r
    report["best_overall"] = best
    report["survivors"] = [r for pn, pr in report["panels"].items()
                           for r in pr["results"] if r.get("beats_placebo_p95")]
    (OUT / "INVENT_0822C_overlay.json").write_text(json.dumps(report, indent=1))

    for pn, pr in report["panels"].items():
        n = pr["placebo_null"]
        print(f"\n=== {pn}  n={pr['n_obs']} {pr['span'][0]}..{pr['span'][1]}  "
              f"K={pr['n_overlays']}  ppy={pr['ppy']}")
        print(f"  BASE equal-risk: design {pr['base']['design']:.2f}  "
              f"holdout {pr['base']['holdout']:.2f}  full {pr['base']['full']:.2f}"
              f"   (gross holdout {pr['gross_base']['holdout']:.2f})")
        print(f"  placebo max-dSR(holdout): mean {n['max_dSharpe_holdout_mean']:+.3f}  "
              f"p95 {n['max_dSharpe_holdout_p95']:+.3f}   [{n['n_draws']} draws]")
        print("  %-28s %8s %8s %8s %9s %9s" %
              ("overlay", "dDesign", "dHold", "dFull", "dHoldGrs", "afterCost"))
        for r in pr["results"]:
            g = r.get("gross") or {}
            rb = r.get("rebal") or {}
            print("  %-28s %+8.3f %+8.3f %+8.3f %+9s %+9s %s" % (
                r["overlay"], r["d_design"], r["d_holdout"], r["d_full"],
                ("%.3f" % g["d_holdout_gross"]) if g else "  --",
                ("%.3f" % rb["d_holdout_after_rebal_cost"]) if rb else "  --",
                "<-- beats placebo p95" if r["beats_placebo_p95"] else ""))
    print("\nN =", report["n_formulas_tested"],
          " sqrt(2lnN) =", round(report["expected_max_sigma_analytic_sqrt2lnN"], 3))
    print("survivors:", [ (r['panel'], r['overlay']) for r in report["survivors"]])


if __name__ == "__main__":
    main()
