#!/usr/bin/env python3
"""EXO_0822C size-matched placebo null + rho1 gate + design freeze.

Placebo construction (pre-registered): each event's returns are replaced by the SAME
symbol's hedged returns on a nearby NON-event date (offset drawn from +/-3..15
sessions). Cohort membership, cohort size, calendar, universe, weights and turnover
are all preserved; only "is this date an event" is destroyed. All 28 formulas are
re-scored every replicate and the maximum |t| is taken.
"""
from __future__ import annotations

import json
import pathlib

import numpy as np

from exo0822c_sweep import (CE_HEAD, FORMULAS, OUTDIR, Panel, eval_formula,
                            expanding_tercile, placebo_returns, real_returns,
                            shuffle_rate)

NREP = 400
CAND = [f for f in FORMULAS if f[1] != "E"]


def main():
    P = Panel()
    rng = np.random.default_rng(20260822)
    q33, q67 = expanding_tercile(P.y, P.evd, P.nd)
    ctx = {"q33": q33, "q67": q67, "yshuf": shuffle_rate(P.y, P.evd, rng)}
    r = real_returns(P, ctx["yshuf"])
    lo, hi = 0, P.cut

    # ---- rho1 gate, reported BEFORE any gross claim -------------------------
    ordinary = P.typ == 0
    des = ordinary & (P.evd < P.cut)
    eps = r["eps_h"][des]
    oc = r["oc"][des]
    f1 = r["f1"][des]
    ok = np.isfinite(eps) & np.isfinite(oc) & np.isfinite(f1)
    rho = {
        "rho_gap_vs_exday_session": float(np.corrcoef(eps[ok], oc[ok])[0, 1]),
        "rho_gap_vs_next_oo": float(np.corrcoef(eps[ok], f1[ok])[0, 1]),
        "n": int(ok.sum()),
    }
    # per-symbol AR(1) of the residual series (is eps itself a bouncing spread?)
    ar = []
    for s in np.unique(P.evs[des]):
        m = des & (P.evs == s)
        v = r["eps_h"][m]
        v = v[np.isfinite(v)]
        if v.size >= 12:
            ar.append(np.corrcoef(v[:-1], v[1:])[0, 1])
    ar = np.array(ar)
    rho["rho1_eps_per_symbol_mean"] = float(np.nanmean(ar))
    rho["rho1_eps_per_symbol_median"] = float(np.nanmedian(ar))
    rho["frac_symbols_below_-0.35"] = float(np.nanmean(ar < -0.35))
    rho["n_symbols"] = int(ar.size)
    print("rho1 gate:", json.dumps(rho, indent=1))

    # ---- design statistics + frozen signs ----------------------------------
    design = {}
    for name, fam, rkey, H, ap in FORMULAS:
        base, _, _ = eval_formula(name, fam, rkey, H, P, r, ctx, lo, hi, CE_HEAD, 1.0, rng)
        sign = float(ap) if ap is not None else (1.0 if base["gross_bpd"] >= 0 else -1.0)
        o, _, _ = eval_formula(name, fam, rkey, H, P, r, ctx, lo, hi, CE_HEAD, sign, rng)
        design[name] = {"sign": sign, "family": fam, "H": H, "apriori": ap is not None,
                        "gross_t": o["gross_t"], "gross_sr": o["gross_sr"],
                        "net_sr": o["net_sr"], "breakeven_bp": o["breakeven_bp"]}

    # ---- placebo replicates -------------------------------------------------
    mx_all = np.zeros(NREP)
    mx_cand = np.zeros(NREP)
    per = {f[0]: np.zeros(NREP) for f in FORMULAS}
    for rep in range(NREP):
        rp = placebo_returns(P, rng)
        ts = {}
        for name, fam, rkey, H, ap in FORMULAS:
            o, _, _ = eval_formula(name, fam, rkey, H, P, rp, ctx, lo, hi, CE_HEAD, 1.0, rng)
            ts[name] = abs(o["gross_t"])
            per[name][rep] = o["gross_t"]
        mx_all[rep] = max(ts.values())
        mx_cand[rep] = max(ts[f[0]] for f in CAND)
        if (rep + 1) % 50 == 0:
            print(f"  rep {rep+1}/{NREP}  max|t| all={mx_all[rep]:.2f} cand={mx_cand[rep]:.2f}")

    q = lambda a, p: float(np.percentile(a, p))
    nulls = {
        "n_formulas": len(FORMULAS),
        "n_candidates": len(CAND),
        "analytic_bar_2lnN": float(np.sqrt(2 * np.log(2 * len(FORMULAS)))),
        "analytic_bar_candidates": float(np.sqrt(2 * np.log(2 * len(CAND)))),
        "placebo_max_all": {"mean": float(mx_all.mean()), "p50": q(mx_all, 50),
                            "p95": q(mx_all, 95), "p99": q(mx_all, 99)},
        "placebo_max_candidates": {"mean": float(mx_cand.mean()), "p50": q(mx_cand, 50),
                                   "p95": q(mx_cand, 95), "p99": q(mx_cand, 99)},
        "placebo_per_formula_mean_t": {k: float(v.mean()) for k, v in per.items()},
        "placebo_per_formula_sd_t": {k: float(v.std(ddof=1)) for k, v in per.items()},
        "placebo_exceed_frac": {
            k: float(np.mean(np.abs(per[k]) >= abs(design[k]["gross_t"]))) for k in per},
        "rho1": rho,
    }
    json.dump(nulls, open(OUTDIR / "INVENT_0822C_gaptether_NULLS.json", "w"), indent=1)
    json.dump(design, open(OUTDIR / "INVENT_0822C_gaptether_DESIGN.json", "w"), indent=1)
    print(json.dumps({k: v for k, v in nulls.items()
                      if k not in ("placebo_per_formula_mean_t", "placebo_per_formula_sd_t",
                                   "placebo_exceed_frac", "rho1")}, indent=1))
    print("\nper-formula placebo mean t / sd / P(|null t| >= |design t|):")
    for k in sorted(design, key=lambda k: -abs(design[k]["gross_t"])):
        print(f"  {k:18s} design t {design[k]['gross_t']:+7.2f}   null mean "
              f"{per[k].mean():+6.2f} sd {per[k].std(ddof=1):5.2f}   "
              f"p={nulls['placebo_exceed_frac'][k]:.4f}")


if __name__ == "__main__":
    main()
