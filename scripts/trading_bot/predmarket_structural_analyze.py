#!/usr/bin/env python3
"""Analyze the Kalshi structural-edge sample. Emits a JSON result blob to stdout.

Three structural hypotheses, all Kalshi-only, all net of a realistic cost model:
  H1  favorite-longshot bias / calibration curve + a pre-registered fade-longshot/back-favorite rule
  H2  near-certain (high-YES) settlement yield, annualized, with the blow-up tail
  H3  nested-threshold internal consistency -> locked (riskless) intra-event arbs, net of fees

Cost model (Kalshi taker, buy-and-hold-to-settlement): entry fee per contract =
ceil(0.07 * p*(1-p) * 100)/100 dollars; you cross the spread on entry (buy at ask); settlement is
free (no exit trade). Design vs held-out split is by close-time median.
"""
from __future__ import annotations
import json, math, sys
from collections import defaultdict

ROWS = sys.argv[1] if len(sys.argv) > 1 else "/home/anont/meme/research/data/predmarket_structural/rows.jsonl"
FEE_COEFF = 0.07
SNAP = "0.5"

def fee(p):
    p = min(max(p, 0.0), 1.0)
    return math.ceil(FEE_COEFF * p * (1.0 - p) * 100.0) / 100.0

def load():
    out = []
    for line in open(ROWS):
        line = line.strip()
        if not line: continue
        r = json.loads(line)
        s = r.get("snaps", {}).get(SNAP)
        if not s: continue
        mid = s["mid"]; sp = max(0.0, s["spread"])
        if not (0.0 < mid < 1.0): continue
        r["mid"] = mid; r["spread"] = sp
        r["ask"] = min(1.0, mid + sp / 2.0)   # buy YES here
        r["bid"] = max(0.0, mid - sp / 2.0)   # sell YES here
        r["lead_sec"] = s.get("lead_sec", 0)
        out.append(r)
    return out

def wilson_se(k, n):
    if n == 0: return 0.0
    p = k / n
    return math.sqrt(max(p * (1 - p), 1e-9) / n)

def mean_se(xs):
    n = len(xs)
    if n == 0: return 0.0, 0.0, 0
    m = sum(xs) / n
    if n < 2: return m, 0.0, n
    var = sum((x - m) ** 2 for x in xs) / (n - 1)
    return m, math.sqrt(var / n), n

# ----------------------------------------------------------------- H1 calibration
BINS = [0.0, 0.02, 0.05, 0.10, 0.20, 0.30, 0.40, 0.50,
        0.60, 0.70, 0.80, 0.90, 0.95, 0.98, 1.0]

def calibration(rows):
    curve = []
    for i in range(len(BINS) - 1):
        lo, hi = BINS[i], BINS[i + 1]
        sub = [r for r in rows if lo <= r["mid"] < hi]
        n = len(sub)
        if n == 0:
            curve.append({"lo": lo, "hi": hi, "n": 0}); continue
        impl = sum(r["mid"] for r in sub) / n
        realized = sum(r["result"] for r in sub) / n
        curve.append({
            "lo": lo, "hi": hi, "n": n,
            "mean_implied": round(impl, 4),
            "realized_yes": round(realized, 4),
            "resid_realized_minus_implied": round(realized - impl, 4),
            "se": round(wilson_se(sum(r["result"] for r in sub), n), 4),
            "mean_spread": round(sum(r["spread"] for r in sub) / n, 4),
        })
    return curve

def rule_edge(rows, lo_thr=0.10, hi_thr=0.90):
    """Pre-registered structural rule, per-contract net PnL, buy-and-hold-to-settlement:
       mid <= lo_thr -> BUY NO (fade the longshot);  mid >= hi_thr -> BUY YES (back the favorite)."""
    yes_pnl, no_pnl = [], []
    for r in rows:
        if r["mid"] >= hi_thr:
            entry = r["ask"]                       # buy YES at ask
            f = fee(entry)
            yes_pnl.append(r["result"] - entry - f)
        elif r["mid"] <= lo_thr:
            no_price = 1.0 - r["bid"]              # buy NO = sell YES at bid
            f = fee(r["bid"])
            no_pnl.append((1 - r["result"]) - no_price - f)
    allp = yes_pnl + no_pnl
    m, se, n = mean_se(allp)
    my, sey, ny = mean_se(yes_pnl)
    mn, sen, nn = mean_se(no_pnl)
    # gross (mid, no fee, no spread) for comparison
    gross = []
    for r in rows:
        if r["mid"] >= hi_thr: gross.append(r["result"] - r["mid"])
        elif r["mid"] <= lo_thr: gross.append((1 - r["result"]) - (1 - r["mid"]))
    gm, gse, gn = mean_se(gross)
    return {
        "lo_thr": lo_thr, "hi_thr": hi_thr,
        "combined": {"mean_net_per_contract": round(m, 5), "se": round(se, 5), "n": n,
                     "t": round(m / se, 2) if se else None},
        "back_favorites_yes": {"mean_net": round(my, 5), "se": round(sey, 5), "n": ny},
        "fade_longshots_no": {"mean_net": round(mn, 5), "se": round(sen, 5), "n": nn},
        "gross_mid_no_cost": {"mean": round(gm, 5), "se": round(gse, 5), "n": gn},
    }

# ----------------------------------------------------------------- H2 near-certain yield
def high_yield(rows, lo=0.95, hi=0.995):
    sub = [r for r in rows if lo <= r["mid"] <= hi and r["ask"] < 1.0]
    pnl, rets, days, blow = [], [], [], 0
    for r in sub:
        entry = r["ask"]; f = fee(entry)
        net = r["result"] - entry - f
        pnl.append(net)
        rets.append(net / entry if entry > 0 else 0.0)
        d = max(r["lead_sec"], 60) / 86400.0
        days.append(d)
        if r["result"] == 0: blow += 1
    m, se, n = mean_se(pnl)
    mret, seret, _ = mean_se(rets)
    md = (sum(days) / len(days)) if days else 0.0
    ann = (mret * 365.0 / md) if md > 0 else None
    return {
        "band": [lo, hi], "n": n,
        "mean_net_pnl_per_contract": round(m, 5), "se": round(se, 5),
        "t": round(m / se, 2) if se else None,
        "blowups_resolved_no": blow, "blowup_rate": round(blow / n, 4) if n else None,
        "mean_return_on_capital": round(mret, 5),
        "mean_holding_days": round(md, 3),
        "naive_annualized_return": round(ann, 3) if ann is not None else None,
        "mean_entry_ask": round(sum(r["ask"] for r in sub) / n, 4) if n else None,
    }

# ----------------------------------------------------------------- H3 nested-threshold arb
def nested_arb(rows):
    ev = defaultdict(list)
    for r in rows:
        if r.get("floor_strike") is not None:
            ev[r["event"]].append(r)
    pairs = 0; mid_viol = 0; locked = 0
    locked_edges = []; mid_viol_sizes = []
    events_used = 0
    for e, ms in ev.items():
        ms = [m for m in ms if m.get("floor_strike") is not None]
        if len(ms) < 2: continue
        ms.sort(key=lambda m: m["floor_strike"])
        events_used += 1
        for i in range(len(ms) - 1):
            L, H = ms[i], ms[i + 1]           # L strike < H strike ; YES_L should be >= YES_H
            if L["floor_strike"] == H["floor_strike"]: continue
            pairs += 1
            # naive mid monotonicity violation
            if H["mid"] > L["mid"]:
                mid_viol += 1
                mid_viol_sizes.append(H["mid"] - L["mid"])
            # locked riskless arb: buy YES_L at ask_L, sell YES_H at bid_H; needs ask_L < bid_H
            ask_L = L["ask"]; bid_H = H["bid"]
            fpair = fee(ask_L) + fee(bid_H)
            edge = (bid_H - ask_L) - fpair     # guaranteed >= this (min payoff structure)
            if edge > 0:
                locked += 1; locked_edges.append(edge)
    me, see, _ = mean_se(locked_edges)
    return {
        "events_with_ladder": events_used,
        "adjacent_pairs": pairs,
        "naive_mid_monotonicity_violations": mid_viol,
        "naive_mid_violation_rate": round(mid_viol / pairs, 4) if pairs else None,
        "mean_naive_violation_size": round(sum(mid_viol_sizes) / len(mid_viol_sizes), 4) if mid_viol_sizes else None,
        "locked_riskless_arbs_net_of_fees": locked,
        "locked_arb_rate": round(locked / pairs, 5) if pairs else None,
        "mean_locked_edge_per_pair": round(me, 5) if locked_edges else None,
        "max_locked_edge": round(max(locked_edges), 4) if locked_edges else None,
    }

def series_breakdown(rows):
    by = defaultdict(lambda: [0, 0])
    for r in rows:
        by[r["series"]][0] += 1
        by[r["series"]][1] += r["result"]
    return {s: {"n": v[0], "yes_rate": round(v[1] / v[0], 3)} for s, v in sorted(by.items())}

def main():
    rows = load()
    rows.sort(key=lambda r: r["close_ts"])
    n = len(rows)
    mid_ix = n // 2
    design = rows[:mid_ix]; held = rows[mid_ix:]
    out = {
        "n_total": n,
        "n_design": len(design), "n_held": len(held),
        "split_close_ts": rows[mid_ix]["close_ts"] if n else None,
        "series_breakdown": series_breakdown(rows),
        "spread_stats": {
            "median_spread": round(sorted(r["spread"] for r in rows)[n // 2], 4) if n else None,
            "frac_spread_le_2c": round(sum(1 for r in rows if r["spread"] <= 0.02) / n, 3) if n else None,
            "frac_spread_le_5c": round(sum(1 for r in rows if r["spread"] <= 0.05) / n, 3) if n else None,
        },
        "H1_calibration": {
            "curve_all": calibration(rows),
            "curve_design": calibration(design),
            "curve_held": calibration(held),
            "rule_all": rule_edge(rows),
            "rule_design": rule_edge(design),
            "rule_held": rule_edge(held),
            "rule_liquid_only_all": rule_edge([r for r in rows if r["spread"] <= 0.03]),
        },
        "H2_high_yield": {
            "all": high_yield(rows),
            "design": high_yield(design),
            "held": high_yield(held),
            "band_98_995": high_yield(rows, 0.98, 0.995),
            "band_96_99": high_yield(rows, 0.96, 0.99),
        },
        "H3_nested_arb": {
            "all": nested_arb(rows),
            "design": nested_arb(design),
            "held": nested_arb(held),
            "liquid_only": nested_arb([r for r in rows if r["spread"] <= 0.05]),
        },
    }
    print(json.dumps(out, indent=1))

if __name__ == "__main__":
    main()
