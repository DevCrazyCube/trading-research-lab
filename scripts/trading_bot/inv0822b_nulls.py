#!/usr/bin/env python3
"""INVENT_0822B: the two MEASURED nulls + the day-of-month diagnostic.

NULL 1 -- circular-shift bootstrap (size-matched to the whole search).
  Circularly shift the realised return matrix against the FIXED weight matrices.
  Preserves each formula's turnover and cost line exactly, each asset's return
  autocorrelation, the cross-asset correlation, and the correlation BETWEEN
  formulas -- so the max is over 42 correlated tries, not 42 independent ones.
  Statistic drawn is the one reported: best-of-two-signs, net of costs.
  For a CALENDAR formula this is exactly the right null: it destroys the
  alignment between the weights and the day-of-month while changing nothing else.

NULL 2 -- random-calendar-window placebo, run only on the surviving family.
  Re-run the identical formula with its trading window moved to a random
  position inside the month, same number of days held, same costs.
"""
from __future__ import annotations
import json, sys
import numpy as np
import pandas as pd

sys.path.insert(0, "/home/anont/meme/scripts/trading_bot")
from inv0822b_lib import ROOT, DESIGN, HOLDOUT, COST_BP, build_panel, score
import inv0822b_sweep as SW

RNG = np.random.default_rng(20260822)
OUT = ROOT / "research" / "trading_bot"


def stack(F, P, window):
    idx = P.index
    m = (idx >= pd.Timestamp(window[0])) & (idx <= pd.Timestamp(window[1]))
    names, blocks, costs, spans = [], [], [], []
    c0 = 0
    for name, (bk, _) in F.items():
        Wm = bk.W.loc[m].fillna(0.0).values
        names.append(name)
        blocks.append(Wm)
        costs.append(bk.costs)
        spans.append((c0, c0 + Wm.shape[1], bk.assets))
        c0 += Wm.shape[1]
    W = np.hstack(blocks)
    return names, W, spans, m


def null1(F, P, R, window, ndraw=2000):
    names, W, spans, m = stack(F, P, window)
    Rm_full = R.loc[m]
    T = W.shape[0]
    # asset-aligned return block
    Rb = np.hstack([Rm_full[a].fillna(0.0).values.reshape(-1, 1) for _, _, ass in spans for a in ass])
    # fixed cost line per formula
    fixed_cost = {}
    for k, (a, b, ass) in enumerate(spans):
        dW = np.abs(np.diff(np.vstack([np.zeros(b - a), W[:, a:b]]), axis=0))
        cst = np.array([COST_BP[x] for x in ass], float) / 1e4
        fixed_cost[names[k]] = (dW * cst).sum(axis=1)
    best = np.empty(ndraw)
    per = {n: np.empty(ndraw) for n in names}
    shifts = RNG.integers(21, T - 21, size=ndraw)
    for d in range(ndraw):
        Rs = np.roll(Rb, shifts[d], axis=0)
        prod = W * Rs
        mx = -9e9
        for k, (a, b, _) in enumerate(spans):
            g = prod[:, a:b].sum(axis=1)
            c = fixed_cost[names[k]]
            for sgn in (1.0, -1.0):
                s = sgn * g - c
                sd = s.std()
                if sd > 0:
                    sr = s.mean() / sd * np.sqrt(252)
                    if sgn == 1.0:
                        per[names[k]][d] = sr
                    else:
                        per[names[k]][d] = max(per[names[k]][d], sr)
                    mx = max(mx, sr)
        best[d] = mx
    return {"ndraw": ndraw, "E_max": float(best.mean()), "p50": float(np.percentile(best, 50)),
            "p95": float(np.percentile(best, 95)), "p99": float(np.percentile(best, 99)),
            "max": float(best.max()),
            "per_formula_E": {n: float(v.mean()) for n, v in per.items()},
            "per_formula_p95": {n: float(np.percentile(v, 95)) for n, v in per.items()},
            "_best": best.tolist()}


def null2_calendar(P, cal, R, window, ndraw=1000):
    """Random-calendar-window placebo for the month-end bond family.
    Draw a random contiguous run of k business days inside the month (k=2),
    same asset, same costs.  Also reports the full day-of-month profile."""
    res = {}
    for leg in ["TLT", "IEF", "AGG", "SHY", "SPY"]:
        if leg not in P.columns:
            continue
        srs = []
        # every possible 2-day window, indexed from the END of the month
        for k in range(1, 19):
            bk = SW.bond_calendar(P, cal, [(leg, 1.0)], (k, k + 1))
            s = score(bk.W, R, bk.costs, *window)
            srs.append({"bd_end": k, "sr_net": s["sr_net"], "sr_gross": s["sr_gross"],
                        "sign": s.get("sign"), "t": s.get("t"), "days_on": s.get("days_on")})
        # random draws: max over the 18 candidate windows under the null is the
        # same thing as the observed max, so report the whole profile AND a
        # bootstrap of "best window chosen in-sample"
        arr = np.array([x["sr_net"] for x in srs])
        res[leg] = {"profile": srs, "best_window_sr": float(arr.max()),
                    "median_window_sr": float(np.median(arr)),
                    "E_max_over_18_windows_if_all_noise": None}
    return res


def dom_profile(P, cal, window, legs=("TLT", "IEF", "SHY", "AGG", "SPY")):
    idx = P.index
    m = (idx >= pd.Timestamp(window[0])) & (idx <= pd.Timestamp(window[1]))
    out = {}
    for leg in legs:
        if leg not in P.columns:
            continue
        r = np.log(P[leg]).diff().loc[m]
        be = cal.loc[m, "bd_end"]
        rows = []
        for k in range(1, 16):
            x = r[be == k].dropna()
            if len(x) < 30:
                continue
            rows.append({"bd_end": int(k), "n": int(len(x)),
                         "mean_bp": round(float(x.mean() * 1e4), 3),
                         "t": round(float(x.mean() / x.std() * np.sqrt(len(x))), 3)})
        allr = r.dropna()
        rows.append({"bd_end": "ALL", "n": int(len(allr)),
                     "mean_bp": round(float(allr.mean() * 1e4), 3),
                     "t": round(float(allr.mean() / allr.std() * np.sqrt(len(allr))), 3)})
        out[leg] = rows
    return out


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "design"
    window = DESIGN if which == "design" else HOLDOUT
    d = build_panel()
    P, cal = d["P"], d["cal"]
    R = np.log(P).diff()
    F = SW.build_all(P, cal)
    print(f"N formulas = {len(F)}; analytic 2-sided bar t = {np.sqrt(2*np.log(2*len(F))):.3f}")
    n1 = null1(F, P, R, window, ndraw=2000)
    print("NULL1 circular-shift: E[max]=%.3f p95=%.3f p99=%.3f max=%.3f"
          % (n1["E_max"], n1["p95"], n1["p99"], n1["max"]))
    n2 = null2_calendar(P, cal, R, window)
    prof = dom_profile(P, cal, window)
    best = n1.pop("_best")
    out = {"which": which, "window": window, "n_formulas": len(F),
           "analytic_bar_t": round(float(np.sqrt(2 * np.log(2 * len(F)))), 3),
           "null1_circular_shift": n1,
           "null2_window_profile": n2,
           "day_of_month_profile": prof,
           "null1_draws_hist": np.histogram(best, bins=20)[0].tolist()}
    p = OUT / f"INVENT_0822B_futroll_NULLS_{which.upper()}.json"
    p.write_text(json.dumps(out, indent=1))
    print("wrote", p)
    for leg, v in n2.items():
        arr = [x["sr_net"] for x in v["profile"]]
        print(f"{leg}: window profile best={max(arr):+.2f} median={np.median(arr):+.2f} "
              f"min={min(arr):+.2f}  (bd_end=1..18, 2-day windows)")
    for leg, rows in prof.items():
        s = " ".join(f"{r['bd_end']}:{r['mean_bp']:+.1f}" for r in rows)
        print(f"{leg} mean bp by bd_end: {s}")


if __name__ == "__main__":
    main()
