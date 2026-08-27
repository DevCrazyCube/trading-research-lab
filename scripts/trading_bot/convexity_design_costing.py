#!/usr/bin/env python3
"""CONVEXITY design-window costing on the FREE DoltHub weekly options panel (T35 support).

Purpose: put NUMBERS on the entry cost, unconditional carry and trigger frequency of the three
pre-named bought-convexity designs in CONVEXITY_PREREGISTRATION.md, using ONLY the cached
DoltHub panel (research/data/doltopts_cache/, weekly EOD chains, ~50 liquid US names, 2020-01 ->
2026-08).  The forward panels (T31 Deribit, T33 Alpaca) are NOT touched: this script never opens
research/data/deribit_forward or research/data/us_options_forward.

What is measured (all on the weekly grid, so every figure is a DESIGN PRIOR, not a test):
  * the ~15-delta strangle nearest 7-14 DTE: premium / spot, relative half-spread (ask-mid)/mid,
    fee as % of premium under the T33 fee model ($0.05/contract on a 100-multiplier, i.e. 5 c);
  * C0 unconditional: buy at ASK, mark at BID one snapshot (~7 calendar days) later
    (if the contracts expired in between, mark at intrinsic on the later snapshot's close);
    net return per unit premium, cluster-robust t (cluster = snapshot date);
  * trigger frequency and the same C0-style hold P&L conditional on D1 / D2 / D3, using the
    WEEKLY analogues of the daily rules (stated in the pre-registration).  Weekly analogues are
    coarser than the daily forward rules; their only role is to bound N and expected carry.

Design-window discipline: thresholds are the pre-registered ones; nothing here is tuned.  The
output is one JSON (research/trading_bot/CONVEXITY_DESIGN_COSTING.json) plus a printed summary.
Research only.  No network.  No orders.
"""
import glob
import json
import math
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CACHE = os.path.join(ROOT, "research", "data", "doltopts_cache")
OUT = os.path.join(ROOT, "research", "trading_bot", "CONVEXITY_DESIGN_COSTING.json")

TARGET_DELTA = 0.15
DTE_NEAR = (7, 20, 14)     # entry-cost stats only: nearest listed expiry (~2w bucket)
DTE_HOLD = (21, 35, 28)    # carry/trigger stats: ~4w expiry, marked at bid TWO snapshots later (~14 DTE)
HOLD_SNAPS = 2
FEE_PER_CONTRACT = 0.05          # $ per contract, T33 fee model (regulatory-only, commission-free venue)
MULT = 100.0
# pre-registered triggers (weekly analogues)
D1_IV_RV_MAX = 0.90              # front ATM IV / trailing realised vol <= 0.90
D1_RV_WEEKS = 8
D2_SHOCK_SD = 2.5                # |last return| >= 2.5 x sd of prior 20 returns
D2_SD_WEEKS = 20
D3_PCTL = 0.20                   # ATM IV at/below 20th pctile of trailing 40 snapshots
D3_WEEKS = 40
D3_MIN_HIST = 20


def f(x):
    try:
        v = float(x)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def dte(exp, date):
    from datetime import date as D
    y, m, d = map(int, exp.split("-"))
    y2, m2, d2 = map(int, date.split("-"))
    return (D(y, m, d) - D(y2, m2, d2)).days


def pick_strangle(chain, date, spot, win):
    """Return dict(call, put, atm_iv, exp, dte) for the expiry nearest DTE in [7,14], else None."""
    by_exp = {}
    for r in chain:
        b, a, dl = f(r.get("bid")), f(r.get("ask")), f(r.get("delta"))
        if b is None or a is None or dl is None or a <= 0 or b <= 0 or a < b:
            continue
        by_exp.setdefault(r["expiration"], []).append((r, b, a, dl))
    best = None
    for exp, rows in by_exp.items():
        t = dte(exp, date)
        if t < win[0] or t > win[1]:
            continue
        if best is None or abs(t - win[2]) < abs(best[1] - win[2]):
            best = (exp, t, rows)
    if best is None:
        return None
    exp, t, rows = best
    calls = [x for x in rows if x[0]["call_put"] == "Call" and x[3] > 0]
    puts = [x for x in rows if x[0]["call_put"] == "Put" and x[3] < 0]
    if not calls or not puts:
        return None
    c = min(calls, key=lambda x: abs(x[3] - TARGET_DELTA))
    p = min(puts, key=lambda x: abs(-x[3] - TARGET_DELTA))
    if abs(c[3] - TARGET_DELTA) > 0.07 or abs(-p[3] - TARGET_DELTA) > 0.07:
        return None
    atm = min(calls, key=lambda x: abs(x[3] - 0.5))
    atm_iv = f(atm[0].get("vol"))
    return dict(exp=exp, dte=t, call=c, put=p, atm_iv=atm_iv)


def mark_exit(chain_next, exp, kc, kp, spot_next, date_next):
    """Bid-side value of the strangle at the next snapshot; intrinsic if expired."""
    if dte(exp, date_next) < 0:
        return max(spot_next - kc, 0.0) + max(kp - spot_next, 0.0), "intrinsic"
    bc = bp = None
    for r in chain_next:
        if r["expiration"] != exp:
            continue
        k = f(r.get("strike"))
        if r["call_put"] == "Call" and k == kc:
            bc = f(r.get("bid"))
        elif r["call_put"] == "Put" and k == kp:
            bp = f(r.get("bid"))
    if bc is None or bp is None:
        return None, "missing"
    return bc + bp, "bid"


def cluster_t(x, cl):
    """Mean and cluster-robust t of x clustered by cl (list of hashables)."""
    x = np.asarray(x, float)
    if len(x) < 2:
        return float("nan"), float("nan"), 0
    m = x.mean()
    groups = {}
    for v, c in zip(x - m, cl):
        groups.setdefault(c, []).append(v)
    G = len(groups)
    if G < 2:
        return m, float("nan"), G
    s = sum(sum(g) ** 2 for g in groups.values())
    se = math.sqrt(s) / len(x) * math.sqrt(G / (G - 1))
    return m, (m / se if se > 0 else float("nan")), G


def main():
    files = sorted(p for p in glob.glob(os.path.join(CACHE, "*.json"))
                   if os.path.basename(p)[:4] >= "2020")
    panel = []
    for p in files:
        with open(p) as fh:
            panel.append(json.load(fh))
    print("snapshots %d (%s .. %s)" % (len(panel), panel[0]["date"], panel[-1]["date"]))
    closes = {}      # sym -> list of (date, close) in grid order
    atm_hist = {}    # sym -> list of atm_iv
    trades = []
    cost_rows = []
    cost_near = []
    for i in range(len(panel) - HOLD_SNAPS):
        cur, nxt = panel[i], panel[i + HOLD_SNAPS]
        date, date_next = cur["date"], nxt["date"]
        for sym, chain in cur["options"].items():
            st = cur["stocks"].get(sym)
            st2 = nxt["stocks"].get(sym)
            spot = f(st["close"]) if st else None
            spot2 = f(st2["close"]) if st2 else None
            if spot:
                closes.setdefault(sym, []).append(spot)
            near = pick_strangle(chain, date, spot, DTE_NEAR) if spot else None
            if near is not None:
                (rc_, bc_, ac_, _), (rp_, bp_, ap_, _) = near['call'], near['put']
                pn, mn = ac_ + ap_, (bc_ + ac_) / 2 + (bp_ + ap_) / 2
                if pn > 0 and mn > 0:
                    cost_near.append(dict(prem_pct_spot=pn / spot, rel_half_spread=(pn - mn) / mn,
                                          fee_frac=2 * FEE_PER_CONTRACT / MULT / pn, dte=near['dte']))
            sel = pick_strangle(chain, date, spot, DTE_HOLD) if spot else None
            if sel is not None:
                atm_hist.setdefault(sym, []).append(sel["atm_iv"])
            if sel is None or spot2 is None:
                continue
            (rc, bc, ac, dc), (rp, bpv, ap, dp) = sel["call"], sel["put"]
            kc, kp = f(rc["strike"]), f(rp["strike"])
            prem = ac + ap
            mid = (bc + ac) / 2 + (bpv + ap) / 2
            fee = 2 * FEE_PER_CONTRACT / MULT
            if prem <= 0 or mid <= 0:
                continue
            exit_val, how = mark_exit(nxt["options"].get(sym, []), sel["exp"], kc, kp, spot2, date_next)
            cost_rows.append(dict(prem_pct_spot=prem / spot, rel_half_spread=(prem - mid) / mid,
                                  fee_frac=fee / prem, dte=sel["dte"]))
            if exit_val is None:
                continue
            r = (exit_val - prem - fee) / prem
            # triggers, computed from history strictly BEFORE this snapshot's entry
            hist = closes.get(sym, [])
            rets = np.diff(np.log(hist)) if len(hist) > 2 else np.array([])
            iv_h = atm_hist.get(sym, [])[:-1]
            d1 = d2 = d3 = None
            if sel["atm_iv"] and len(rets) >= D1_RV_WEEKS:
                rv = float(np.std(rets[-D1_RV_WEEKS:], ddof=1) * math.sqrt(52))
                d1 = (rv > 0) and (sel["atm_iv"] / rv <= D1_IV_RV_MAX)
            if len(rets) >= D2_SD_WEEKS + 1:
                sd = float(np.std(rets[-D2_SD_WEEKS - 1:-1], ddof=1))
                d2 = sd > 0 and abs(rets[-1]) >= D2_SHOCK_SD * sd
            if sel["atm_iv"] and len(iv_h) >= D3_MIN_HIST:
                h = [v for v in iv_h[-D3_WEEKS:] if v]
                d3 = bool(h) and sel["atm_iv"] <= float(np.quantile(h, D3_PCTL))
            trades.append(dict(date=date, sym=sym, exp=sel["exp"], r=r, how=how, d1=d1, d2=d2, d3=d3))
    print("strangles priced %d, hold-marked %d" % (len(cost_rows), len(trades)))
    def coststats(rows):
        c = {k: float(np.median([x[k] for x in rows])) for k in ("prem_pct_spot", "rel_half_spread", "fee_frac", "dte")}
        c["rel_half_spread_p75"] = float(np.percentile([x["rel_half_spread"] for x in rows], 75))
        c["n"] = len(rows)
        return c
    c = coststats(cost_rows)
    cn = coststats(cost_near)
    for lab, cc in (("~14-DTE strangle (entry cost only)", cn), ("~28-DTE strangle (held 2 snapshots)", c)):
        print("%s: n=%d premium %.2f%% of spot, rel half-spread %.1f%% (p75 %.1f%%), fee %.2f%% of premium, dte %.0f" % (
            lab, cc["n"], cc["prem_pct_spot"] * 100, cc["rel_half_spread"] * 100, cc["rel_half_spread_p75"] * 100, cc["fee_frac"] * 100, cc["dte"]))
    res = {}
    for name, key in (("C0_unconditional", None), ("D1_iv_under_realised", "d1"),
                      ("D2_aftershock", "d2"), ("D3_iv_compression", "d3")):
        sub = [t for t in trades if key is None or t[key]]
        elig = [t for t in trades if key is None or t[key] is not None]
        x = [t["r"] for t in sub]
        m, tt, G = cluster_t(x, [t["date"] for t in sub])
        res[name] = dict(n_trades=len(sub), n_clusters=G, frac_of_eligible=(len(sub) / len(elig) if elig else None),
                         mean_net_return_on_premium=m, cluster_t=tt,
                         win_rate=float(np.mean(np.asarray(x) > 0)) if x else None,
                         p95_return=float(np.percentile(x, 95)) if x else None,
                         max_return=float(max(x)) if x else None,
                         share_of_pnl_top_cluster=(None if not x else float(
                             max(sum(t["r"] for t in sub if t["date"] == d) for d in set(t["date"] for t in sub))
                             / sum(x))) if x and sum(x) != 0 else None)
        r_ = res[name]
        print("%-22s n=%5d clusters=%4d freq=%s mean=%+.3f t=%+.2f win=%s p95=%s" % (
            name, r_["n_trades"], G, ("%.3f" % r_["frac_of_eligible"]) if r_["frac_of_eligible"] is not None else "-",
            m, tt, ("%.2f" % r_["win_rate"]) if r_["win_rate"] is not None else "-",
            ("%+.2f" % r_["p95_return"]) if r_["p95_return"] is not None else "-"))
    out = dict(built="2026-08-26", panel="research/data/doltopts_cache (weekly, 2020-01 -> 2026-08)",
               n_snapshots=len(panel), n_strangles=len(cost_rows), n_marked=len(trades),
               instrument="~15-delta strangle, expiry nearest 28 DTE (21-35), buy at ask, mark at bid two snapshots (~14d) later; entry-cost stats also for the nearest ~14-DTE strangle",
               cost_hold_28dte=c, cost_near_14dte=cn, designs=res,
               caveat="weekly EOD panel with uncertain stamp; hold = two snapshots (~14d) of a ~28-DTE strangle, not to expiry; "
                      "figures are design priors for N_min and carry, never a test result")
    with open(OUT, "w") as fh:
        json.dump(out, fh, indent=1, sort_keys=True)
    print("wrote", OUT)


if __name__ == "__main__":
    sys.exit(main())
