#!/usr/bin/env python3
"""D0821 evaluation: the multiple-testing bar, cluster-robust inference, and the
held-out window -- opened only after every design number above was fixed."""
from __future__ import annotations
import glob, json, os, sys
import numpy as np

sys.path.insert(0, "/home/anont/meme/scripts")
from d0821_season_lib import stats

CACHE = "/home/anont/meme/research/data/d0821_cache"
ETF_DESIGN = ("1900-01-01", "2014-01-01")
ETF_HELD = ("2014-01-01", "2099-01-01")
ST_DESIGN = ("2016-01-04", "2022-01-01")
ST_HELD = ("2022-01-01", "2099-01-01")

# formulas superseded by a corrected rebuild are NOT separate hypotheses
SUPERSEDED = {"X01_EXDIV_CAPTURE_PRERUN", "X02_EXDIV_CAPTURE_UNWIND", "X03_DRIP_PAYDATE"}


def cluster_t(series, dates, lo, hi, keyfun):
    x = np.array([r for r, d in zip(series, dates) if lo <= d < hi])
    dd = [d for d in dates if lo <= d < hi]
    agg = {}
    for r, d in zip(x, dd):
        if r != 0.0:
            agg.setdefault(keyfun(d), []).append(r)
    tot = np.array([sum(v) for v in agg.values()])
    if tot.size < 3:
        return float("nan"), int(tot.size), float("nan")
    sd = tot.std(ddof=1)
    t = tot.mean() / (sd / np.sqrt(tot.size)) if sd > 0 else float("nan")
    return float(t), int(tot.size), float((tot > 0).mean())


CLUSTER = {"L": lambda d: d[:4], "W": lambda d: d[:4] + "Q" + str((int(d[5:7]) - 1) // 3),
           "P": lambda d: d[:7], "T": lambda d: d[:7], "R": lambda d: d[:7],
           "D": lambda d: d[:7], "X": lambda d: d[:7], "C": lambda d: d[:7]}


def main():
    etf = json.load(open(os.path.join(CACHE, "etf_design.json")))
    st = json.load(open(os.path.join(CACHE, "stock_design.json")))
    fx = json.load(open(os.path.join(CACHE, "stock_fix_design.json")))
    edates, sdates = etf["dates"], st["dates"]
    meta = {}
    for k, v in etf["results"].items():
        meta[k] = dict(v, _dates="etf")
    for src in (st["results"], fx["results"]):
        for k, v in src.items():
            meta[k] = dict(v, _dates="stock")

    rows = []
    nets = {}
    for name, v in meta.items():
        arr = np.load(os.path.join(CACHE, name + ".npy"))
        gross, net, stress = arr[0], arr[1], arr[2]
        dates = edates if v["_dates"] == "etf" else sdates
        D = ETF_DESIGN if v["_dates"] == "etf" else ST_DESIGN
        H = ETF_HELD if v["_dates"] == "etf" else ST_HELD
        dn, hn = stats(net, dates, *D), stats(net, dates, *H)
        dg, hg = stats(gross, dates, *D), stats(gross, dates, *H)
        ds, hs = stats(stress, dates, *D), stats(stress, dates, *H)
        ct, nc, hitc = cluster_t(net, dates, *D, CLUSTER[v["family"]])
        cth, nch, _ = cluster_t(net, dates, *H, CLUSTER[v["family"]])
        rows.append(dict(name=name, family=v["family"], desc=v["desc"],
                         panel=v["_dates"], active=v["active_frac"],
                         design=dn, design_gross=dg, design_stress=ds,
                         held=hn, held_gross=hg, held_stress=hs,
                         design_cluster_t=ct, design_clusters=nc, design_cluster_hit=hitc,
                         held_cluster_t=cth, held_clusters=nch))
        if v["family"] != "C":
            nets[name] = (net, dates, D)

    # ------------------------------------------------- multiple-testing bar
    cand = [r for r in rows if r["family"] != "C" and r["name"] not in SUPERSEDED]
    N = len(cand)
    bar_t = float(np.sqrt(2 * np.log(2 * N)))          # sign-agnostic
    bar_t_1s = float(np.sqrt(2 * np.log(N)))
    yrs_etf = cand[0] and np.mean([r["design"]["years"] for r in cand if r["panel"] == "etf"])
    yrs_st = np.mean([r["design"]["years"] for r in cand if r["panel"] == "stock"])
    bar_sh_etf, bar_sh_st = bar_t / np.sqrt(yrs_etf), bar_t / np.sqrt(yrs_st)

    # ------------------------------------------------- empirical joint null
    # One sign per calendar SESSION, shared by every formula active that session, so
    # contemporaneous cross-formula correlation survives into the null.
    def joint_null(panel, nrep=20000, block=21, seed=7):
        sel = [r["name"] for r in cand if r["panel"] == panel]
        if not sel:
            return {}
        net0, dates0, D0 = nets[sel[0]]
        mask = np.array([(d >= D0[0]) and (d < D0[1]) for d in dates0])
        X = np.vstack([nets[s][0][mask] for s in sel])
        nb = X.shape[1] // block
        X = X[:, : nb * block].reshape(len(sel), nb, block)
        rng = np.random.default_rng(seed)
        mx = np.empty(nrep)
        for i in range(0, nrep, 500):
            k = min(500, nrep - i)
            s = rng.choice([-1.0, 1.0], size=(k, 1, nb, 1))
            sim = (X[None] * s).reshape(k, len(sel), -1)
            mu = sim.mean(2); sd = sim.std(2, ddof=1)
            t = np.abs(mu / (sd / np.sqrt(sim.shape[2]) + 1e-30))
            mx[i:i + k] = t.max(1)
        return dict(n_formulas=len(sel), E_max=float(mx.mean()),
                    p50=float(np.percentile(mx, 50)), p95=float(np.percentile(mx, 95)),
                    p99=float(np.percentile(mx, 99)),
                    E_max_sharpe=float(mx.mean() / np.sqrt(
                        np.mean([r["design"]["years"] for r in cand if r["panel"] == panel]))))

    jn = {"etf": joint_null("etf"), "stock": joint_null("stock")}

    obs_max = max(abs(r["design"]["t"]) for r in cand if np.isfinite(r["design"]["t"]))
    summary = dict(n_formulas=N, n_with_controls=len(rows),
                   analytic_bar_t_sign_agnostic=bar_t, analytic_bar_t_one_sided=bar_t_1s,
                   design_years_etf=float(yrs_etf), design_years_stock=float(yrs_st),
                   analytic_bar_sharpe_etf=float(bar_sh_etf),
                   analytic_bar_sharpe_stock=float(bar_sh_st),
                   joint_null=jn, observed_max_abs_design_t=float(obs_max))

    rows.sort(key=lambda r: -abs(r["design"]["t"] if np.isfinite(r["design"]["t"]) else 0))
    json.dump(dict(summary=summary, rows=rows),
              open(os.path.join(CACHE, "eval.json"), "w"), indent=1)

    print(json.dumps(summary, indent=1))
    print()
    hdr = (f"{'name':32s}{'fam':4s}{'dSh':>7s}{'dt':>7s}{'dclT':>7s}{'ncl':>5s}"
           f"{'dStrT':>7s}{'hSh':>7s}{'ht':>7s}{'hclT':>7s}{'hStrSh':>8s}")
    print(hdr); print("-" * len(hdr))
    for r in rows:
        d, h = r["design"], r["held"]
        print(f"{r['name']:32s}{r['family']:4s}{d['sharpe']:7.2f}{d['t']:7.2f}"
              f"{r['design_cluster_t']:7.2f}{r['design_clusters']:5d}"
              f"{r['design_stress']['t']:7.2f}{h['sharpe']:7.2f}{h['t']:7.2f}"
              f"{r['held_cluster_t']:7.2f}{r['held_stress']['sharpe']:8.2f}")


if __name__ == "__main__":
    main()
