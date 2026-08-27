#!/usr/bin/env python3
"""INVENT_0825 stage 2 -- HELD-OUT window.  Runs only after the design freeze
file exists; signs and selection are read from it, never re-fit here.

Held-out 2025-01-01 .. 2026-08-16.
"""
import os, sys, json, hashlib
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from f0825_lib import (Panel, event_pnl, book_from, evaluate, sharpe, rho1,
                       window_mask, COST_BP)
import f0825_formulas as FF

OUT = "/home/anont/meme/research/trading_bot"
DES = f"{OUT}/INVENT_0825_fundwindow_DESIGN.json"
HOLD = ("2025-01-01", "2026-08-16")
RNG = np.random.default_rng(825825)


def perm_within_stamp(P, w, rng):
    wp = np.zeros_like(w)
    nz = np.where(w != 0)[0]
    if nz.size == 0:
        return wp
    g = P.ev_g[nz]
    wp[nz[np.argsort(g, kind="stable")]] = w[nz[np.lexsort((rng.random(nz.size), g))]]
    return wp


def main():
    d = json.load(open(DES))
    sha = hashlib.sha256(json.dumps(d, indent=1, sort_keys=True, default=float)
                         .encode()).hexdigest()
    frozen = open(DES.replace(".json", ".sha256")).read().strip()
    P = Panel()
    F = FF.build(P)
    names = list(F)
    ev_m, st_m = window_mask(P, *HOLD)
    res = {}
    for n in names:
        w, e, x, fc, kind = F[n]
        sgn = np.sign(d["design"][n]["sharpe_gross"]) or 1.0
        wm = np.where(ev_m, w, 0.0) * sgn   # sign frozen from design
        pv = event_pnl(P, e, x, fc)
        g, tw = book_from(P, wm, pv)
        r = evaluate(P, g[st_m], tw[st_m])
        r["design_sign"] = float(sgn)
        r["kind"] = kind
        # held-out permutation null, same size
        pm = np.empty(300)
        for k in range(300):
            gp, _ = book_from(P, perm_within_stamp(P, wm, RNG), pv)
            pm[k] = sharpe(gp[st_m])
        r["holdout_perm_p95_absSR"] = float(np.percentile(np.abs(pm), 95))
        res[n] = r
        star = "*" if n in d["selected"] else " "
        print(f"{star}{n:24s} gross {r['sharpe_gross']:+6.2f} net {r['sharpe_net']:+6.2f} "
              f"mean {r['mean_bp']:+7.2f}bp be {r['breakeven_bp_side']:+6.2f} "
              f"rho1 {r['rho1_pnl']:+.3f} permp95 {r['holdout_perm_p95_absSR']:.2f}",
              flush=True)

    # design -> holdout rank correlation across the whole family (theme test)
    ds = np.array([d["design"][n]["sharpe_gross"] for n in names])
    hs = np.array([res[n]["sharpe_gross"] for n in names])
    def _sp(a, b):
        ra = np.argsort(np.argsort(a)).astype(float)
        rb = np.argsort(np.argsort(b)).astype(float)
        ra -= ra.mean(); rb -= rb.mean()
        r = float((ra * rb).sum() / np.sqrt((ra * ra).sum() * (rb * rb).sum()))
        n = len(a)
        t = r * np.sqrt(max(n - 2, 1) / max(1e-12, 1 - r * r))
        return r, t
    rho, pval = _sp(ds, hs)

    # ---- held-out CALENDAR placebo: same formulas anchored at non-funding times
    shifts = [12, 24, 36, 48, 60, 72, 84]
    old_b = P.ev_b.copy()
    cal = {n: [] for n in names}
    for sh in shifts:
        P.ev_b = old_b + sh
        FF._CS.clear()
        FS = FF.build(P)
        zero = np.zeros(len(P.ev_b), bool)
        for n in names:
            w, e, x, fc, kind = FS[n]
            sgn = np.sign(d["design"][n]["sharpe_gross"]) or 1.0
            pv = event_pnl(P, e, x, zero)
            g, _ = book_from(P, np.where(ev_m, w, 0.0) * sgn, pv)
            cal[n].append(float(sharpe(g[st_m])))
    P.ev_b = old_b
    FF._CS.clear()
    for n in names:
        res[n]["holdout_calendar_placebo"] = cal[n]
        res[n]["holdout_calendar_placebo_mean"] = float(np.mean(cal[n]))
        res[n]["holdout_calendar_placebo_maxabs"] = float(np.max(np.abs(cal[n])))
    print("\nheld-out calendar placebo (stamp vs non-funding anchors):", flush=True)
    for n in sorted(names, key=lambda k: -res[k]["sharpe_gross"])[:8]:
        print(f"  {n:24s} stamp {res[n]['sharpe_gross']:+6.2f}  placebo mean "
              f"{res[n]['holdout_calendar_placebo_mean']:+6.2f}  max|.| "
              f"{res[n]['holdout_calendar_placebo_maxabs']:5.2f}", flush=True)
    out = dict(holdout_window=HOLD, design_sha256_expected=frozen,
               design_sha256_recomputed=sha, freeze_ok=(sha == frozen),
               selected=d["selected"], gross_bar=d["gross_bar"],
               holdout=res,
               theme_rank_corr_design_vs_holdout=float(rho),
               theme_rank_corr_p=float(pval),
               verdict_rule=("REAL only if held-out gross beats BOTH nulls with the "
                             "design sign AND held-out NET is positive at 5.5 bp/side"))
    js = json.dumps(out, indent=1, sort_keys=True, default=float)
    open(f"{OUT}/INVENT_0825_fundwindow_HOLDOUT.json", "w").write(js)
    print("freeze_ok", sha == frozen, "rank corr %.3f (p=%.3f)" % (rho, pval), flush=True)


if __name__ == "__main__":
    main()
