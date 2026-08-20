#!/usr/bin/env python3
"""T27 diagnostics -- distribution, deflated Sharpe, and the diversification test
against T3 (pressure reversal) and T7 (ex-dividend open).

  python3 t27_diag.py dist                 # design distribution + analytic noise bar
  python3 t27_diag.py corr NAME [NAME...]  # correlation of a config's daily net P&L
                                           # with the T3 book, design AND held out
  python3 t27_diag.py census               # event census (counts, not returns)
"""

from __future__ import annotations

import json
import math
import pathlib
import sys

import numpy as np


import t27_event_overnight as T27

WORK = T27.WORK


def _t3_series(F, RET_A, valid, ctx, rows, hs):
    W = T27.weights_decile(F["p10"], valid, 0.10)
    allday = np.ones(len(ctx["days"]), dtype=bool)
    r = T27.evaluate(W, allday, "A", 0.5, RET_A, RET_A, ctx, rows, hs)
    return r


def mirror(v):
    """A config whose design result is NEGATIVE is traded the other way round --
    but the mirror pays the SAME costs, it does not earn them.  So

        net_mirror = -gross - cost,   not  -(gross - cost).

    Reported here so that the "best tradeable formula" is chosen on a number that
    could actually be earned in either direction."""
    n = v["net"]["n"]
    gm = v["gross"]["mean_bp"]
    gs = v["gross"].get("sd_bp")
    c = v["mean_cost_bp"]
    if gs in (None, 0):
        return None
    m = -gm - c
    return {"n": n, "mean_bp": m, "sharpe": m / gs * math.sqrt(252.0),
            "t": m / (gs / math.sqrt(n))}


def dist():
    res = json.load(open(WORK / "design_results.json"))
    for name, v in res.items():
        v["mirror"] = mirror(v)
        best = v["net"]
        if v["mirror"] and v["mirror"]["sharpe"] > best["sharpe"]:
            v["tradeable"] = dict(v["mirror"], direction="mirror")
        else:
            v["tradeable"] = dict(best, direction="as-specified")
    json.dump(res, open(WORK / "design_results_tradeable.json", "w"), indent=1)
    tr = sorted(res.items(), key=lambda kv: -kv[1]["tradeable"]["sharpe"])
    print(f"{'config':26s} {'dir':13s} {'n':>5s} {'net bp':>9s} {'SR':>7s} {'t':>7s}")
    for k, v in tr:
        t = v["tradeable"]
        print(f"{k:26s} {t['direction']:13s} {t['n']:5d} {t['mean_bp']:+9.2f} "
              f"{t['sharpe']:+7.2f} {t['t']:+7.2f}")
    sr = np.array([v["net"]["sharpe"] for v in res.values()])
    tt = np.array([v["net"]["t"] for v in res.values()])
    trs = np.array([v["tradeable"]["sharpe"] for v in res.values()])
    trt = np.array([v["tradeable"]["t"] for v in res.values()])
    N = len(res)
    out = {
        "n_formulas": N,
        "analytic_expected_max_z": math.sqrt(2 * math.log(N)),
        "design_net_sharpe": {
            "min": float(sr.min()), "p10": float(np.quantile(sr, .10)),
            "p25": float(np.quantile(sr, .25)), "p50": float(np.quantile(sr, .50)),
            "p75": float(np.quantile(sr, .75)), "p90": float(np.quantile(sr, .90)),
            "max": float(sr.max()), "mean": float(sr.mean()), "sd": float(sr.std(ddof=1)),
            "n_positive": int((sr > 0).sum()),
        },
        "design_net_t": {
            "min": float(tt.min()), "p50": float(np.quantile(tt, .50)),
            "max": float(tt.max()),
        },
        "design_tradeable_sharpe": {
            "min": float(trs.min()), "p10": float(np.quantile(trs, .10)),
            "p25": float(np.quantile(trs, .25)), "p50": float(np.quantile(trs, .50)),
            "p75": float(np.quantile(trs, .75)), "p90": float(np.quantile(trs, .90)),
            "max": float(trs.max()), "mean": float(trs.mean()),
            "sd": float(trs.std(ddof=1)), "n_positive": int((trs > 0).sum()),
        },
        "design_tradeable_t": {
            "min": float(trt.min()), "p50": float(np.quantile(trt, .50)),
            "p90": float(np.quantile(trt, .90)), "max": float(trt.max()),
        },
    }
    print(json.dumps(out, indent=1))
    json.dump(out, open(WORK / "dist.json", "w"), indent=1)


def corr(names):
    F, RET_A, RET_B, valid, ctx = T27.load_features()
    days = np.array(ctx["days"])
    out = {}
    for tag, lo, hi, hs in (("design", T27.DESIGN_START, T27.DESIGN_END, T27.HALF_SPREAD_DESIGN_BP),
                            ("test", T27.TEST_START, T27.TEST_END, T27.HALF_SPREAD_TEST_BP)):
        rows = T27.window_rows(ctx["days"], lo, hi)
        t3 = _t3_series(F, RET_A, valid, ctx, rows, hs)
        t3map = dict(zip(t3["dates"], t3["net"]))
        cfg = T27.build_configs(F, valid, ctx)
        for name in names:
            rail, W, dmask, sn, note = cfg[name]
            r = T27.evaluate(W, dmask, rail, sn, RET_A, RET_B, ctx, rows, hs)
            if r is None:
                continue
            common = [d for d in r["dates"] if d in t3map]
            a = np.array([v for d, v in zip(r["dates"], r["net"]) if d in t3map])
            b = np.array([t3map[d] for d in common])
            rho = float(np.corrcoef(a, b)[0, 1]) if a.size > 5 else float("nan")
            # residual alpha of the config on T3
            beta = float(np.cov(a, b)[0, 1] / np.var(b, ddof=1))
            resid = a - beta * b
            tr = float(resid.mean() / (resid.std(ddof=1) / math.sqrt(resid.size)))
            out.setdefault(name, {})[tag] = {
                "n_common": int(a.size), "rho_with_T3": rho, "beta_on_T3": beta,
                "resid_mean_bp": float(resid.mean() * 1e4), "resid_t": tr,
                "T3_sharpe_same_window": float(np.mean(t3["net"]) / np.std(t3["net"], ddof=1)
                                               * math.sqrt(252)),
            }
            print(f"{name:24s} {tag:6s} rho_T3={rho:+.3f} beta={beta:+.3f} "
                  f"resid {resid.mean()*1e4:+.2f}bp t={tr:+.2f}", flush=True)
    json.dump(out, open(WORK / "corr.json", "w"), indent=1)


def census():
    F, RET_A, RET_B, valid, ctx = T27.load_features()
    ANN = F["ann"]
    V = valid
    n_ann_valid = int((ANN & V).sum())
    per_day = (ANN & V).sum(axis=1)
    rows_d = T27.window_rows(ctx["days"], T27.DESIGN_START, T27.DESIGN_END)
    rows_t = T27.window_rows(ctx["days"], T27.TEST_START, T27.TEST_END)
    out = {
        "valid_symbol_nights": int(V.sum()),
        "announcement_nights_in_universe": n_ann_valid,
        "design": {"nights": int(rows_d.sum()),
                   "ann_symbol_nights": int(per_day[rows_d].sum()),
                   "median_announcers_per_night": float(np.median(per_day[rows_d])),
                   "p90_announcers_per_night": float(np.quantile(per_day[rows_d], .9)),
                   "nights_with_ge5": int((per_day[rows_d] >= 5).sum())},
        "test": {"nights": int(rows_t.sum()),
                 "ann_symbol_nights": int(per_day[rows_t].sum()),
                 "median_announcers_per_night": float(np.median(per_day[rows_t])),
                 "nights_with_ge5": int((per_day[rows_t] >= 5).sum())},
    }
    for k in ("k_since", "k_until_pred"):
        v = F[k][V]
        out[k + "_dist"] = {str(int(q)): int((v == q).sum()) for q in range(0, 11)}
    print(json.dumps(out, indent=1))
    json.dump(out, open(WORK / "census.json", "w"), indent=1)


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "dist":
        dist()
    elif cmd == "corr":
        corr(sys.argv[2:])
    elif cmd == "census":
        census()
    else:
        raise SystemExit(cmd)
