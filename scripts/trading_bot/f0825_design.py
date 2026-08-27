#!/usr/bin/env python3
"""INVENT_0825 stage 1 -- DESIGN window scoring + both nulls + freeze.

Design   2023-01-01 .. 2024-12-31
Held-out 2025-01-01 .. 2026-08-16   (NOT touched here)
"""
import os, sys, json, hashlib
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from f0825_lib import (Panel, event_pnl, book_from, evaluate, sharpe, rho1,
                       window_mask, COST_BP)
import f0825_formulas as FF

OUT = "/home/anont/meme/research/trading_bot"
RNG = np.random.default_rng(20260825)
DESIGN = ("2023-01-01", "2025-01-01")


def perm_within_stamp(P, w, rng):
    """ADV-slot analogue: reassign the weights across the symbols trading at the
    same stamp.  Preserves per-stamp net exposure and gross size exactly."""
    wp = np.zeros_like(w)
    nz = np.where(w != 0)[0]
    if nz.size == 0:
        return wp
    g = P.ev_g[nz]
    tgt = nz[np.argsort(g, kind="stable")]
    src = nz[np.lexsort((rng.random(nz.size), g))]
    wp[tgt] = w[src]
    return wp


def main():
    P = Panel()
    print("events", len(P.ev_b), "stamps", P.NS, "symbols", P.S, flush=True)
    F = FF.build(P)
    names = list(F)
    N = len(names)
    print("N formulas", N, flush=True)
    ev_m, st_m = window_mask(P, *DESIGN)

    # ------------- rho1 bounce gate, reported BEFORE any gross claim -------
    rr = []
    for i in range(P.S):
        o = P.o[i].astype(np.float64)
        r = np.diff(o) / o[:-1]
        r = r[np.isfinite(r)]
        if r.size > 5000:
            rr.append(rho1(r))
    gate = dict(rho1_5m_open_ret_mean=float(np.nanmean(rr)),
                rho1_5m_open_ret_median=float(np.nanmedian(rr)),
                rho1_5m_open_ret_min=float(np.nanmin(rr)),
                rho1_5m_open_ret_max=float(np.nanmax(rr)),
                n_symbols=len(rr),
                gate_threshold=-0.35,
                passes=bool(np.nanmean(rr) > -0.35))
    print("GATE", json.dumps(gate), flush=True)

    # ------------- design scores -------------------------------------------
    PV, PVP, W = {}, {}, {}
    res, curves = {}, {}
    for n in names:
        w, e, x, fc, kind = F[n]
        pv = event_pnl(P, e, x, fc)
        pvp = event_pnl(P, e, x, np.zeros(len(P.ev_b), bool))   # price-only
        wm = np.where(ev_m, w, 0.0)
        PV[n], PVP[n], W[n] = pv, pvp, wm
        g, tw = book_from(P, wm, pv)
        r = evaluate(P, g[st_m], tw[st_m])
        gp, twp = book_from(P, wm, pvp)
        r["sharpe_gross_priceonly"] = sharpe(gp[st_m])
        r["kind"] = kind
        res[n] = r
        curves[n] = g[st_m]
        print(f"{n:24s} gross {r['sharpe_gross']:+6.2f}  net {r['sharpe_net']:+6.2f} "
              f"px-only {r['sharpe_gross_priceonly']:+6.2f} "
              f"mean {r['mean_bp']:+7.2f}bp  be {r['breakeven_bp_side']:+6.2f}  "
              f"rho1 {r['rho1_pnl']:+.3f}  n {r['n_stamps']}", flush=True)

    # ------------- null 1: size-matched signal-permutation placebo ---------
    R = 300
    pm = np.zeros((N, R))
    for j, n in enumerate(names):
        for k in range(R):
            wp = perm_within_stamp(P, W[n], RNG)
            g, _ = book_from(P, wp, PV[n])
            pm[j, k] = sharpe(g[st_m])
        print("perm", n, "p95|SR|", round(float(np.percentile(np.abs(pm[j]), 95)), 2),
              flush=True)
    maxdraw = np.max(np.abs(pm), axis=0)
    null1 = dict(draws=R,
                 family_max_abs_mean=float(maxdraw.mean()),
                 family_max_abs_p95=float(np.percentile(maxdraw, 95)),
                 per_formula_p95={n: float(np.percentile(np.abs(pm[j]), 95))
                                  for j, n in enumerate(names)})
    print("NULL1 permutation family max|SR|: mean %.2f p95 %.2f"
          % (null1["family_max_abs_mean"], null1["family_max_abs_p95"]), flush=True)

    # ------------- null 2: calendar placebo (non-funding anchors) ----------
    # the same 27 formulas anchored 1h..7h after the stamp; none of those is a
    # funding time.  Price-only on both sides so the comparison is like-for-like.
    shifts = [12, 24, 36, 48, 60, 72, 84]
    pl = np.zeros((N, len(shifts)))
    old_b = P.ev_b.copy()
    for k, sh in enumerate(shifts):
        P.ev_b = old_b + sh
        FF._CS.clear()
        FS = FF.build(P)
        zero = np.zeros(len(P.ev_b), bool)
        for j, n in enumerate(names):
            w, e, x, fc, kind = FS[n]
            pv = event_pnl(P, e, x, zero)
            g, _ = book_from(P, np.where(ev_m, w, 0.0), pv)
            pl[j, k] = sharpe(g[st_m])
        print("calendar shift +%dm  family max|SR| %.2f"
              % (sh * 5, float(np.max(np.abs(pl[:, k])))), flush=True)
    P.ev_b = old_b
    FF._CS.clear()
    null2 = dict(shifts_minutes=[s * 5 for s in shifts],
                 family_max_abs=[float(np.max(np.abs(pl[:, k]))) for k in range(len(shifts))],
                 family_max_abs_mean=float(np.mean(np.max(np.abs(pl), axis=0))),
                 per_formula={n: [float(v) for v in pl[j]] for j, n in enumerate(names)})
    print("NULL2 calendar-placebo family max|SR| mean %.2f"
          % null2["family_max_abs_mean"], flush=True)

    analytic = float(np.sqrt(2 * np.log(N)))
    bar = max(null1["family_max_abs_p95"], null2["family_max_abs_mean"], analytic)

    sel = [n for n in names if abs(res[n]["sharpe_gross"]) > bar]
    sel.sort(key=lambda n: -abs(res[n]["sharpe_gross"]))
    out = dict(theme="perp funding-settlement-window micro-dynamics",
               design_window=DESIGN, holdout_window=["2025-01-01", "2026-08-16"],
               n_formulas=N, cost_bp_side=COST_BP, universe=P.symbols,
               n_events=int(len(P.ev_b)), n_stamps=int(P.NS),
               rho1_gate=gate, analytic_expected_max=analytic,
               null_permutation=null1, null_calendar=null2, gross_bar=bar,
               design=res,
               selection_rule=("|design gross Sharpe| > max(permutation-null family "
                               "max|SR| p95, calendar-placebo family max|SR| mean, "
                               "sqrt(2 ln N)); survivors ranked by |gross SR|; top 3 "
                               "carried to the untouched held-out window."),
               selected=sel[:3], selected_all_over_bar=sel)
    js = json.dumps(out, indent=1, sort_keys=True, default=float)
    open(f"{OUT}/INVENT_0825_fundwindow_DESIGN.json", "w").write(js)
    open(f"{OUT}/INVENT_0825_fundwindow_DESIGN.sha256", "w").write(
        hashlib.sha256(js.encode()).hexdigest())
    np.savez_compressed("/home/anont/meme/research/data/fund0825_cache/design_curves.npz",
                        **curves)
    print("BAR %.2f  OVER-BAR %s" % (bar, sel), flush=True)


if __name__ == "__main__":
    main()
