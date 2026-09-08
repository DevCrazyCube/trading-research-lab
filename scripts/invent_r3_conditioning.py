#!/usr/bin/env python3
"""INVENT R3 -- CONDITION & COMBINE the surviving edges.

Theme: do regime gates / cross-leg filters / ensembles lift the HELD-OUT Sharpe of the
alive basket legs beyond the raw standalone legs?

Legs (reconstructed from cache, frozen specs, no re-fit of the leg itself):
  T3    : end-of-day pressure reversal, top-300, w=10, cut=0.10, net of 1.43+0.31 bp + borrow
  T7D1  : ex-dividend cum-close -> ex-OPEN residual, frozen cfg, auction rail (M0 outstanding)
  CEF   : T12 S2 discount-LEVEL decile tilt, H=4 weeks, net @11.53 bp half-spread

Conditioners are strictly LAGGED (value as of close(t-1)) and every threshold is estimated on
the DESIGN window only, then frozen and applied to the untouched HOLDOUT.

Windows
  daily legs  : DESIGN 2016-02-01..2022-12-30   HOLDOUT 2023-01-03..2026-08-14
  weekly CEF  : DESIGN ..2024-02-29             HOLDOUT 2024-03-01..
"""
from __future__ import annotations
import json, math, pathlib, datetime, itertools
import numpy as np

ROOT = pathlib.Path("/home/anont/meme")
D = ROOT / "research/data/invent_r3"
OUT = ROOT / "research/trading_bot"

DESIGN_END = "2022-12-30"
HOLD_START = "2023-01-03"
CEF_DESIGN_END = "2024-02-29"

# ---------------------------------------------------------------- load


def load(name):
    return json.loads((D / name).read_text())


def _dates(ds):
    return np.array(ds)


cond_raw = load("cond.json")


def cseries(key):
    d = cond_raw[key]
    ks = sorted(d)
    return ks, np.array([d[k] for k in ks], dtype=float)


# ------------------------------------------------- conditioner construction
CD, CV = {}, {}
for k in cond_raw:
    ks, vs = cseries(k)
    CD[k] = ks
    CV[k] = vs

_spy_dates = CD["spy"]
_spy_idx = {d: i for i, d in enumerate(_spy_dates)}
spy = CV["spy"]
spy_hi, spy_lo, spy_op, spy_vol = CV["spy_high"], CV["spy_low"], CV["spy_open"], CV["spy_vol"]
spy_r = np.concatenate([[np.nan], np.diff(np.log(spy))])


def rolling(a, n, fn):
    out = np.full(len(a), np.nan)
    for i in range(n - 1, len(a)):
        w = a[i - n + 1:i + 1]
        if np.all(np.isfinite(w)):
            out[i] = fn(w)
    return out


spy_rv20 = rolling(spy_r, 20, lambda w: w.std(ddof=1) * math.sqrt(252) * 100)
spy_rv5 = rolling(spy_r, 5, lambda w: w.std(ddof=1) * math.sqrt(252) * 100)
spy_ma200 = rolling(spy, 200, np.mean)
spy_ma20 = rolling(spy, 20, np.mean)
spy_r20 = np.concatenate([np.full(20, np.nan), spy[20:] / spy[:-20] - 1.0])
spy_range = (spy_hi - spy_lo) / spy
spy_range20 = rolling(spy_range, 20, np.mean)
spy_volma = rolling(spy_vol.astype(float), 20, np.mean)


def align(target_dates, src_dates, src_vals, lag=1):
    """value of src as of the last src date STRICTLY BEFORE target date, extra `lag` back."""
    out = np.full(len(target_dates), np.nan)
    j = 0
    n = len(src_dates)
    for i, d in enumerate(target_dates):
        while j < n and src_dates[j] < d:
            j += 1
        k = j - lag                      # lag=1 -> last obs strictly before d
        if 0 <= k < n and np.isfinite(src_vals[k]):
            out[i] = src_vals[k]
    return out


def build_conditioners(dates):
    """dict name -> lagged value array aligned to `dates` (all strictly as-of t-1)."""
    C = {}
    vix = align(dates, CD["vix"], CV["vix"])
    vix_p = align(dates, CD["vix"], CV["vix"], lag=2)
    v3 = align(dates, CD["vix3m"], CV["vix3m"])
    v9 = align(dates, CD["vix9d"], CV["vix9d"])
    vv = align(dates, CD["vvix"], CV["vvix"])
    irx = align(dates, CD["irx"], CV["irx"])
    irx_p = align(dates, CD["irx"], CV["irx"], lag=22)
    C["VIX_LEVEL"] = vix
    C["VIX_TERM"] = vix / v3                      # >1 = backwardation = stress
    C["VIX_9D_RATIO"] = v9 / vix
    C["VVIX_RATIO"] = vv / vix
    C["VIX_DCHG"] = np.log(vix / vix_p)
    C["SPY_TREND200"] = align(dates, _spy_dates, spy / spy_ma200)
    C["SPY_TREND20"] = align(dates, _spy_dates, spy / spy_ma20)
    C["SPY_MOM20"] = align(dates, _spy_dates, spy_r20)
    C["RV20"] = align(dates, _spy_dates, spy_rv20)
    C["RV5_OVER_RV20"] = align(dates, _spy_dates, spy_rv5 / spy_rv20)
    C["VRP"] = vix - align(dates, _spy_dates, spy_rv20)      # VIX minus realised
    C["RANGE20"] = align(dates, _spy_dates, spy_range20)
    C["VOLUME_REL"] = align(dates, _spy_dates, spy_vol.astype(float) / spy_volma)
    C["RATE_LEVEL"] = irx
    C["RATE_CHG"] = irx - irx_p
    C["SPY_RET_PREV"] = align(dates, _spy_dates, spy_r)
    return C


def daytype(dates):
    """calendar gates -- no threshold fitting, the split is definitional."""
    out = {}
    dts = [datetime.date.fromisoformat(d) for d in dates]
    wd = np.array([d.weekday() for d in dts])
    out["DT_MON"] = (wd == 0).astype(float)
    out["DT_FRI"] = (wd == 4).astype(float)
    out["DT_MIDWEEK"] = ((wd >= 1) & (wd <= 3)).astype(float)
    # turn of month: last 2 or first 3 trading days of the month
    mon = np.array([d.year * 12 + d.month for d in dts])
    tom = np.zeros(len(dts))
    for m in set(mon.tolist()):
        idx = np.where(mon == m)[0]
        tom[idx[:3]] = 1.0
        tom[idx[-2:]] = 1.0
    out["DT_TURNMONTH"] = tom
    # opex week: the week containing the 3rd Friday
    ox = np.zeros(len(dts))
    for i, d in enumerate(dts):
        if d.weekday() == 4 and 15 <= d.day <= 21:
            ox[i] = 1.0
    for i in range(len(dts)):
        if ox[i] == 1.0:
            for j in range(max(0, i - 4), i + 1):
                ox[j] = 1.0
    out["DT_OPEXWEEK"] = ox
    return out


# ---------------------------------------------------------------- stats
def ann_sharpe(x, ppy):
    x = np.asarray(x, dtype=float)
    if len(x) < 5 or x.std() == 0:
        return 0.0
    return float(x.mean() / x.std(ddof=1) * math.sqrt(ppy))


def tstat(x):
    x = np.asarray(x, dtype=float)
    if len(x) < 5 or x.std() == 0:
        return 0.0
    return float(x.mean() / x.std(ddof=1) * math.sqrt(len(x)))


def report(x, ppy):
    x = np.asarray(x, dtype=float)
    return {"n": int(len(x)), "mean_bp": float(x.mean() * 1e4),
            "ann_sharpe": ann_sharpe(x, ppy), "t": tstat(x),
            "ann_ret_pct": float(x.mean() * ppy * 100)}


# ---------------------------------------------------------------- legs
def load_legs():
    t3 = load("t3_daily.json")
    t7 = load("t7d1_daily.json")
    cef = load("t12_all.json")["S2_LNone_H4"]
    legs = {
        "T3": {"dates": t3["dates"], "net": np.array(t3["net"]),
               "ctrl": np.array(t3["control"]),
               "long": np.array(t3["long"]), "short": np.array(t3["short"]), "ppy": 252},
        "T7D1": {"dates": t7["dates"], "net": np.array(t7["net"]),
                 "ctrl": np.array(t7["control"]), "ppy": 221},
        "CEF": {"dates": cef["dates"], "net": np.array(cef["net"]), "ppy": 52},
    }
    return legs


def trail_mean(x, n):
    out = np.full(len(x), np.nan)
    cs = np.concatenate([[0.0], np.cumsum(x)])
    for i in range(n, len(x)):
        out[i] = (cs[i] - cs[i - n]) / n          # uses x[i-n..i-1]: strictly lagged
    return out


def leg_conditioners(leg, other=None, other_dates=None):
    """conditioners derived from the legs themselves. ALL strictly lagged."""
    C = {}
    net, dates = leg["net"], leg["dates"]
    C["OWN_MOM20"] = trail_mean(net, 20)
    C["OWN_MOM60"] = trail_mean(net, 60)
    C["OWN_VOL20"] = np.concatenate([[np.nan]] + [[np.nan]] * 0 + [
        [np.nan] * 0]) if False else _trail_sd(net, 20)
    if "ctrl" in leg:
        c = leg["ctrl"]
        C["CTRL_PREV"] = np.concatenate([[np.nan], c[:-1]])
        C["CTRL_ABS20"] = trail_mean(np.abs(c), 20)
    if "long" in leg:
        C["LEG_ASYM20"] = trail_mean(leg["long"] + leg["short"], 20)
    if other is not None:
        om = trail_mean(other["net"], 20)
        C["CROSS_MOM20"] = align(dates, other["dates"], om, lag=1)
    return C


def _trail_sd(x, n):
    out = np.full(len(x), np.nan)
    for i in range(n, len(x)):
        out[i] = x[i - n:i].std(ddof=1)
    return out


# ---------------------------------------------------------------- the test
def gate_test(r, dates, gate_val, design_end, hold_start, ppy, binary=False):
    """Split at the DESIGN median of the conditioner; sign chosen on DESIGN.

    Returns design/holdout stats for the ON-vs-OFF differential AND for the
    'stand down when OFF' book (zeros on OFF days, same calendar).
    """
    d = np.array(dates)
    fin = np.isfinite(gate_val)
    dmask = (d <= design_end) & fin
    hmask = (d >= hold_start) & fin
    if dmask.sum() < 100 or hmask.sum() < 50:
        return None
    if binary:
        thr = 0.5
    else:
        thr = float(np.median(gate_val[dmask]))
    hi = gate_val > thr
    # sign: which side has the higher DESIGN mean return
    m_hi = r[dmask & hi].mean() if (dmask & hi).sum() > 10 else -1e9
    m_lo = r[dmask & ~hi].mean() if (dmask & ~hi).sum() > 10 else -1e9
    if m_hi == -1e9 or m_lo == -1e9:
        return None
    side_hi = m_hi > m_lo
    on = hi if side_hi else ~hi

    def block(mask):
        a = r[mask & on]
        b = r[mask & ~on]
        if len(a) < 10 or len(b) < 10:
            return None
        se = math.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
        tdiff = float((a.mean() - b.mean()) / se) if se > 0 else 0.0
        # stand-down book on the same calendar
        book = np.where(on[mask], r[mask], 0.0)
        raw = r[mask]
        return {"n_on": int(len(a)), "n_off": int(len(b)),
                "mean_on_bp": float(a.mean() * 1e4), "mean_off_bp": float(b.mean() * 1e4),
                "t_diff": tdiff,
                "sharpe_book": ann_sharpe(book, ppy),
                "sharpe_raw": ann_sharpe(raw, ppy),
                "d_sharpe": ann_sharpe(book, ppy) - ann_sharpe(raw, ppy),
                "sharpe_on_only": ann_sharpe(a, ppy)}

    return {"threshold": thr, "side_hi": bool(side_hi),
            "design": block(dmask), "holdout": block(hmask)}


# ---------------------------------------------------------------- ensembles
def to_weekly(dates, r):
    """sum a daily series into ISO weeks -> {week_end_date: sum}."""
    out = {}
    for d, x in zip(dates, r):
        dt = datetime.date.fromisoformat(d)
        key = (dt - datetime.timedelta(days=dt.weekday())).isoformat()
        out[key] = out.get(key, 0.0) + float(x)
    return out


def ensemble_block(legs, design_end, hold_start):
    """Weekly common calendar; every leg self-financing, scaled to unit design vol."""
    wk = {}
    for name, leg in legs.items():
        if leg["ppy"] == 52:
            w = {}
            for d, x in zip(leg["dates"], leg["net"]):
                dt = datetime.date.fromisoformat(d)
                w[(dt - datetime.timedelta(days=dt.weekday())).isoformat()] = float(x)
            wk[name] = w
        else:
            wk[name] = to_weekly(leg["dates"], leg["net"])
    keys = sorted(set().union(*[set(v) for v in wk.values()]))
    return keys, wk


# ---------------------------------------------------------------- driver
def main():
    legs = load_legs()
    results = []
    trials = 0

    for legname in ("T3", "T7D1"):
        leg = legs[legname]
        other = legs["T7D1"] if legname == "T3" else legs["T3"]
        dates, r, ppy = leg["dates"], leg["net"], leg["ppy"]
        C = build_conditioners(dates)
        C.update(leg_conditioners(leg, other=other))
        DT = daytype(dates)
        for cname, cval in C.items():
            res = gate_test(r, dates, cval, DESIGN_END, HOLD_START, ppy)
            trials += 2                       # both sign choices are reachable
            if res and res["design"] and res["holdout"]:
                results.append({"family": "GATE", "leg": legname, "cond": cname, **res})
        for cname, cval in DT.items():
            res = gate_test(r, dates, cval, DESIGN_END, HOLD_START, ppy, binary=True)
            trials += 2
            if res and res["design"] and res["holdout"]:
                results.append({"family": "DAYTYPE", "leg": legname, "cond": cname, **res})

    # ---- CEF weekly gates (own split, fewer conditioners: weekly power is thin)
    cef = legs["CEF"]
    Cc = build_conditioners(cef["dates"])
    Cc.update(leg_conditioners(cef))
    for cname, cval in Cc.items():
        res = gate_test(cef["net"], cef["dates"], cval, CEF_DESIGN_END, "2024-03-01", 52)
        trials += 2
        if res and res["design"] and res["holdout"]:
            results.append({"family": "GATE", "leg": "CEF", "cond": cname, **res})

    # ---- ensembles ------------------------------------------------------
    keys, wk = ensemble_block(legs, DESIGN_END, HOLD_START)
    dk = [k for k in keys if k <= DESIGN_END]
    hk = [k for k in keys if k >= HOLD_START]
    cef_start = min(wk["CEF"])
    dk_c = [k for k in dk if k >= cef_start]

    def vec(name, ks):
        return np.array([wk[name].get(k, 0.0) for k in ks])

    ens = []
    names3 = ["T3", "T7D1", "CEF"]
    sd_design = {}
    for nm in names3:
        base = dk_c if nm == "CEF" else dk
        v = vec(nm, base)
        sd_design[nm] = float(v.std(ddof=1)) or 1.0

    def build(ws, ks):
        out = np.zeros(len(ks))
        for nm, w in ws.items():
            out += w * vec(nm, ks) / sd_design[nm]
        return out

    weight_sets = {
        "ENS_EQRISK_T3_T7": {"T3": 0.5, "T7D1": 0.5},
        "ENS_EQRISK_ALL3": {"T3": 1 / 3, "T7D1": 1 / 3, "CEF": 1 / 3},
        "ENS_T3_HEAVY": {"T3": 0.6, "T7D1": 0.2, "CEF": 0.2},
        "ENS_CEF_HEAVY": {"T3": 0.25, "T7D1": 0.15, "CEF": 0.60},
        "ENS_BASKET_V5": {"T3": 0.268, "T7D1": 0.075, "CEF": 0.17},
        "ENS_T3_ONLY": {"T3": 1.0},
        "ENS_CEF_ONLY": {"CEF": 1.0},
        "ENS_T7_ONLY": {"T7D1": 1.0},
    }
    # design-Sharpe-proportional weights (a FIT -> counts as trials)
    srs = {}
    for nm in names3:
        base = dk_c if nm == "CEF" else dk
        srs[nm] = max(0.0, ann_sharpe(vec(nm, base), 52))
    tot = sum(srs.values()) or 1.0
    weight_sets["ENS_SHARPE_WEIGHTED"] = {k: v / tot for k, v in srs.items()}
    # design inverse-correlation (min-variance on design corr, long-only clipped)
    M = np.vstack([vec(nm, dk_c) / sd_design[nm] for nm in names3])
    cov = np.cov(M)
    try:
        iv = np.linalg.solve(cov, np.ones(3))
        iv = np.clip(iv, 0, None)
        iv = iv / (iv.sum() or 1.0)
        weight_sets["ENS_MINVAR"] = dict(zip(names3, iv.tolist()))
    except Exception:
        pass

    for nm, ws in weight_sets.items():
        trials += 1
        dser = build(ws, dk_c)
        hser = build(ws, hk)
        ens.append({"family": "ENSEMBLE", "name": nm, "weights": ws,
                    "design": report(dser, 52), "holdout": report(hser, 52)})

    # ---- vol-targeted ensemble (overlay on the equal-risk 3-leg book)
    for nm, ws in (("ENS_EQRISK_ALL3", weight_sets["ENS_EQRISK_ALL3"]),
                   ("ENS_BASKET_V5", weight_sets["ENS_BASKET_V5"])):
        for lb in (8, 13, 26):
            trials += 1
            full = [k for k in keys if k >= cef_start]
            s = build(ws, full)
            sd = _trail_sd(s, lb)
            tgt = np.nanmedian(sd[np.isfinite(sd)]) if np.isfinite(sd).any() else 1.0
            scale = np.clip(tgt / sd, 0.25, 2.0)
            scaled = np.where(np.isfinite(scale), scale, 1.0) * s
            fk = np.array(full)
            dm, hm = fk <= DESIGN_END, fk >= HOLD_START
            ens.append({"family": "VOLTARGET", "name": f"VT{lb}_{nm}",
                        "design": report(scaled[dm], 52), "holdout": report(scaled[hm], 52),
                        "raw_design": report(s[dm], 52), "raw_holdout": report(s[hm], 52)})

    # ---- one edge as a FILTER for another: gate the whole weekly book on VIX regime
    full = [k for k in keys if k >= cef_start]
    base = build(weight_sets["ENS_EQRISK_ALL3"], full)
    Cw = build_conditioners(full)
    for cname in ("VIX_LEVEL", "VIX_TERM", "SPY_TREND200", "RV20", "VRP"):
        trials += 2
        res = gate_test(base, full, Cw[cname], DESIGN_END, HOLD_START, 52)
        if res and res["design"] and res["holdout"]:
            ens.append({"family": "ENS_GATE", "name": f"ENSGATE_{cname}", **res})

    payload = {
        "theme": "condition_and_combine_surviving_edges",
        "windows": {"daily_design": ["2016-02-01", DESIGN_END],
                    "daily_holdout": [HOLD_START, "2026-08-14"],
                    "cef_design_end": CEF_DESIGN_END},
        "n_trials_declared": trials,
        "expected_max_sharpe_under_null_sigma": math.sqrt(2 * math.log(max(trials, 2))),
        "gates": results,
        "ensembles": ens,
    }
    (OUT / "INVENT_R3_condition_combine.json").write_text(json.dumps(payload, indent=1))
    print(json.dumps({"trials": trials,
                      "bar_sigma": payload["expected_max_sharpe_under_null_sigma"],
                      "n_gates": len(results), "n_ens": len(ens)}, indent=1))

    print("\n=== GATES ranked by |design t_diff| ===")
    for g in sorted(results, key=lambda x: -abs(x["design"]["t_diff"]))[:20]:
        d, h = g["design"], g["holdout"]
        print(f"{g['leg']:5s} {g['cond']:16s} design t={d['t_diff']:+.2f} "
              f"dSR={d['d_sharpe']:+.2f} (raw {d['sharpe_raw']:+.2f}) | "
              f"HOLD t={h['t_diff']:+.2f} dSR={h['d_sharpe']:+.2f} "
              f"(book {h['sharpe_book']:+.2f} vs raw {h['sharpe_raw']:+.2f})")

    print("\n=== ENSEMBLES ===")
    for e in ens:
        if e["family"] in ("ENSEMBLE", "VOLTARGET"):
            print(f"{e['name']:26s} design SR {e['design']['ann_sharpe']:+.2f} "
                  f"| HOLD SR {e['holdout']['ann_sharpe']:+.2f} "
                  f"(mean {e['holdout']['mean_bp']:+.1f} bp/wk, n={e['holdout']['n']})")
        else:
            d, h = e["design"], e["holdout"]
            print(f"{e['name']:26s} design t={d['t_diff']:+.2f} dSR={d['d_sharpe']:+.2f} "
                  f"| HOLD dSR={h['d_sharpe']:+.2f} book {h['sharpe_book']:+.2f}")


if __name__ == "__main__":
    main()
