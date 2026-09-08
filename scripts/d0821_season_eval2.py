#!/usr/bin/env python3
"""D0821 evaluation, corrected sign accounting.

A formula whose NET design t is large and NEGATIVE is usually not a reversed edge --
it is cost drag.  Reversing a book flips the GROSS series but NOT the cost, so the
best net any trader can have is  sign*gross - cost.  The hypothesis test is therefore
run on GROSS (sign-agnostic), and tradability on the correctly-signed net.
"""
from __future__ import annotations
import json, os, sys
import numpy as np

sys.path.insert(0, "/home/anont/meme/scripts")
from d0821_season_lib import stats

CACHE = "/home/anont/meme/research/data/d0821_cache"
SPLIT = {"etf": (("1900-01-01", "2014-01-01"), ("2014-01-01", "2099-01-01")),
         "stock": (("2016-01-04", "2022-01-01"), ("2022-01-01", "2099-01-01"))}
SUPERSEDED = {"X01_EXDIV_CAPTURE_PRERUN", "X02_EXDIV_CAPTURE_UNWIND", "X03_DRIP_PAYDATE"}
CLUSTER = {"L": lambda d: d[:4], "W": lambda d: d[:4] + "Q" + str((int(d[5:7]) - 1) // 3)}


def cluster_t(series, dates, lo, hi, keyfun):
    agg = {}
    for r, d in zip(series, dates):
        if lo <= d < hi and r != 0.0:
            agg.setdefault(keyfun(d), []).append(r)
    tot = np.array([sum(v) for v in agg.values()])
    if tot.size < 3 or tot.std(ddof=1) == 0:
        return float("nan"), int(tot.size)
    return float(tot.mean() / (tot.std(ddof=1) / np.sqrt(tot.size))), int(tot.size)


def main():
    meta = {}
    etf = json.load(open(os.path.join(CACHE, "etf_design.json")))
    st = json.load(open(os.path.join(CACHE, "stock_design.json")))
    fx = json.load(open(os.path.join(CACHE, "stock_fix_design.json")))
    for k, v in etf["results"].items():
        meta[k] = dict(v, panel="etf")
    for src in (st["results"], fx["results"]):
        for k, v in src.items():
            meta[k] = dict(v, panel="stock")
    DATES = {"etf": etf["dates"], "stock": st["dates"]}

    rows, gross_store = [], {}
    for name, v in meta.items():
        arr = np.load(os.path.join(CACHE, name + ".npy"))
        gross, net, stress = arr[0], arr[1], arr[2]
        cost = gross - net                       # >= 0 by construction
        dates = DATES[v["panel"]]
        D, H = SPLIT[v["panel"]]
        dg = stats(gross, dates, *D)
        sgn = 1.0 if dg["t"] >= 0 else -1.0      # sign CHOSEN ON DESIGN GROSS ONLY
        net_s = sgn * gross - cost
        net_stress_s = sgn * gross - 2.0 * cost
        r = dict(name=name, family=v["family"], desc=v["desc"], panel=v["panel"],
                 active=v["active_frac"], sign=sgn,
                 design_gross=dg, held_gross=stats(gross, dates, *H),
                 design_net=stats(net_s, dates, *D), held_net=stats(net_s, dates, *H),
                 design_net_stress=stats(net_stress_s, dates, *D),
                 held_net_stress=stats(net_stress_s, dates, *H),
                 cost_bp_per_active_day=float(
                     np.mean(cost[cost > 0]) * 1e4) if np.any(cost > 0) else 0.0)
        if v["family"] in CLUSTER:
            r["design_cluster_t"], r["design_clusters"] = cluster_t(
                sgn * gross, dates, *D, CLUSTER[v["family"]])
            r["held_cluster_t"], r["held_clusters"] = cluster_t(
                sgn * gross, dates, *H, CLUSTER[v["family"]])
        rows.append(r)
        if v["family"] != "C":
            gross_store[name] = (gross, dates, D, v["panel"])

    cand = [r for r in rows if r["family"] != "C" and r["name"] not in SUPERSEDED]
    N = len(cand)
    bar_t = float(np.sqrt(2 * np.log(2 * N)))

    def joint_null(panel, nrep=20000, block=21, seed=11):
        sel = [r["name"] for r in cand if r["panel"] == panel]
        g0, d0, D0, _ = gross_store[sel[0]]
        mask = np.array([(d >= D0[0]) and (d < D0[1]) for d in d0])
        X = np.vstack([gross_store[s][0][mask] for s in sel])
        nb = X.shape[1] // block
        X = X[:, : nb * block].reshape(len(sel), nb, block)
        rng = np.random.default_rng(seed)
        mx = np.empty(nrep)
        for i in range(0, nrep, 500):
            k = min(500, nrep - i)
            s = rng.choice([-1.0, 1.0], size=(k, 1, nb, 1))
            sim = (X[None] * s).reshape(k, len(sel), -1)
            t = np.abs(sim.mean(2) / (sim.std(2, ddof=1) / np.sqrt(sim.shape[2]) + 1e-30))
            mx[i:i + k] = t.max(1)
        yrs = float(np.mean([r["design_gross"]["years"] for r in cand if r["panel"] == panel]))
        obs = max(abs(r["design_gross"]["t"]) for r in cand if r["panel"] == panel)
        return dict(n=len(sel), design_years=yrs, E_max_t=float(mx.mean()),
                    p95_t=float(np.percentile(mx, 95)), p99_t=float(np.percentile(mx, 99)),
                    E_max_sharpe=float(mx.mean() / np.sqrt(yrs)),
                    p95_sharpe=float(np.percentile(mx, 95) / np.sqrt(yrs)),
                    observed_max_t=float(obs), joint_p=float((mx >= obs).mean()))

    jn = {p: joint_null(p) for p in ("etf", "stock")}
    summary = dict(n_formulas=N, analytic_bar_t_sign_agnostic=bar_t,
                   analytic_bar_sharpe={p: bar_t / np.sqrt(jn[p]["design_years"]) for p in jn},
                   joint_null=jn)
    rows.sort(key=lambda r: -abs(r["design_gross"]["t"]))
    json.dump(dict(summary=summary, rows=rows),
              open(os.path.join(CACHE, "eval2.json"), "w"), indent=1)
    print(json.dumps(summary, indent=1)); print()
    hdr = (f"{'name':32s}{'fam':4s}{'sgn':>4s}{'dGrSh':>7s}{'dGrT':>7s}{'dNetSh':>8s}"
           f"{'dStrSh':>8s}{'hGrSh':>7s}{'hNetSh':>8s}{'hStrSh':>8s}{'cst_bp':>8s}")
    print(hdr); print("-" * len(hdr))
    for r in rows:
        print(f"{r['name']:32s}{r['family']:4s}{r['sign']:4.0f}"
              f"{r['design_gross']['sharpe']:7.2f}{r['design_gross']['t']:7.2f}"
              f"{r['design_net']['sharpe']:8.2f}{r['design_net_stress']['sharpe']:8.2f}"
              f"{r['held_gross']['sharpe']:7.2f}{r['held_net']['sharpe']:8.2f}"
              f"{r['held_net_stress']['sharpe']:8.2f}{r['cost_bp_per_active_day']:8.2f}")


if __name__ == "__main__":
    main()
