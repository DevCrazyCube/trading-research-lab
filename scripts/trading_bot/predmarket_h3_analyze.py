#!/usr/bin/env python3
"""Analyze the corrected, SIMULTANEOUS H3 ladders. Prints a JSON blob.

NESTED (KXMLBTOTAL, 'Over N'): YES(strike) must be monotone decreasing. Adjacent riskless locked
arb exists iff you can buy the lower strike YES cheaper than you can sell the higher strike YES:
ask_low < bid_high. Guaranteed profit >= (bid_high - ask_low) - fees (min payoff of +YES_low/-YES_high
is 1). Report violation rate and net-of-fee locked-arb rate + size, over adjacent pairs.

PARTITION (KXHIGH*, exclusive+exhaustive buckets): exactly one bucket resolves YES.
  - buy one YES in every bucket: cost sum(ask)+fees, pays 1  -> arb if sum(ask)+fees < 1.
  - sell one YES in every bucket: take sum(bid)-fees, pays 1 -> arb if sum(bid)-fees > 1.
Report how often, and mean net size, across events (simultaneous books only).
"""
from __future__ import annotations
import json, math, sys

LAD = sys.argv[1] if len(sys.argv) > 1 else "/home/anont/meme/research/data/predmarket_structural/h3_ladders.jsonl"

def fee(p):
    p = min(max(p, 0.0), 1.0)
    return math.ceil(0.07 * p * (1 - p) * 100) / 100

def mean_se(xs):
    n = len(xs)
    if n == 0: return 0.0, 0.0, 0
    m = sum(xs) / n
    if n < 2: return m, 0.0, n
    v = sum((x - m) ** 2 for x in xs) / (n - 1)
    return m, math.sqrt(v / n), n

def main():
    lads = [json.loads(l) for l in open(LAD) if l.strip()]
    nested = [L for L in lads if L["kind"] == "nested"]
    part = [L for L in lads if L["kind"] == "partition"]

    # --- NESTED ---
    pairs = 0; viol = 0; locked = 0; locked_edges = []; viol_sizes = []
    liq_pairs = 0; liq_locked = 0; liq_edges = []
    for L in nested:
        legs = [g for g in L["legs"] if g.get("strike") is not None]
        legs.sort(key=lambda g: g["strike"])
        for i in range(len(legs) - 1):
            lo, hi = legs[i], legs[i + 1]        # strike_lo < strike_hi ; YES_lo should be >= YES_hi
            if lo["strike"] == hi["strike"]: continue
            pairs += 1
            if hi["mid"] > lo["mid"]:
                viol += 1; viol_sizes.append(hi["mid"] - lo["mid"])
            edge = (hi["bid"] - lo["ask"]) - (fee(lo["ask"]) + fee(hi["bid"]))
            if edge > 0:
                locked += 1; locked_edges.append(edge)
            tight = lo["spread"] <= 0.03 and hi["spread"] <= 0.03 and lo["vol"] >= 200 and hi["vol"] >= 200
            if tight:
                liq_pairs += 1
                if edge > 0: liq_locked += 1; liq_edges.append(edge)
    me, _, _ = mean_se(locked_edges)
    lme, _, _ = mean_se(liq_edges)
    nested_res = {
        "events": len(nested), "adjacent_pairs": pairs,
        "mid_monotonicity_violations": viol,
        "mid_violation_rate": round(viol / pairs, 4) if pairs else None,
        "mean_violation_size": round(sum(viol_sizes) / len(viol_sizes), 4) if viol_sizes else None,
        "locked_arbs_net_of_fees": locked,
        "locked_arb_rate": round(locked / pairs, 5) if pairs else None,
        "mean_locked_edge": round(me, 5) if locked_edges else None,
        "max_locked_edge": round(max(locked_edges), 4) if locked_edges else None,
        "liquid_pairs_spread_le3c_vol_ge200": liq_pairs,
        "liquid_locked_arbs": liq_locked,
        "liquid_locked_rate": round(liq_locked / liq_pairs, 5) if liq_pairs else None,
        "liquid_mean_edge": round(lme, 5) if liq_edges else None,
    }

    # --- PARTITION ---
    n_ev = 0; exactly_one = 0
    buy_arbs = []; sell_arbs = []
    buy_liq = []; sell_liq = []
    sum_mid = []
    for L in part:
        legs = L["legs"]
        # exclusivity/exhaustiveness sanity: exactly one YES?
        n_ev += 1
        yes_ct = sum(g["result"] for g in legs)
        if yes_ct == 1: exactly_one += 1
        sum_mid.append(sum(g["mid"] for g in legs))
        cost_buy = sum(g["ask"] for g in legs) + sum(fee(g["ask"]) for g in legs)
        take_sell = sum(g["bid"] for g in legs) - sum(fee(g["bid"]) for g in legs)
        buy_edge = 1.0 - cost_buy       # >0 => arb (pay < guaranteed 1)
        sell_edge = take_sell - 1.0     # >0 => arb (take > guaranteed 1 liability)
        if buy_edge > 0: buy_arbs.append(buy_edge)
        if sell_edge > 0: sell_arbs.append(sell_edge)
        tight = all(g["spread"] <= 0.03 for g in legs) and all(g["vol"] >= 100 for g in legs)
        if tight:
            if buy_edge > 0: buy_liq.append(buy_edge)
            if sell_edge > 0: sell_liq.append(sell_edge)
    part_res = {
        "events": n_ev,
        "exactly_one_yes_frac": round(exactly_one / n_ev, 4) if n_ev else None,
        "mean_sum_of_yes_mids": round(sum(sum_mid) / len(sum_mid), 4) if sum_mid else None,
        "buy_all_yes_arbs": len(buy_arbs), "buy_arb_rate": round(len(buy_arbs) / n_ev, 4) if n_ev else None,
        "mean_buy_edge": round(sum(buy_arbs) / len(buy_arbs), 5) if buy_arbs else None,
        "sell_all_yes_arbs": len(sell_arbs), "sell_arb_rate": round(len(sell_arbs) / n_ev, 4) if n_ev else None,
        "mean_sell_edge": round(sum(sell_arbs) / len(sell_arbs), 5) if sell_arbs else None,
        "liquid_buy_arbs_spread_le3c": len(buy_liq),
        "mean_liquid_buy_edge": round(sum(buy_liq) / len(buy_liq), 5) if buy_liq else None,
        "liquid_sell_arbs_spread_le3c": len(sell_liq),
        "mean_liquid_sell_edge": round(sum(sell_liq) / len(sell_liq), 5) if sell_liq else None,
    }
    print(json.dumps({"nested": nested_res, "partition": part_res}, indent=1))

if __name__ == "__main__":
    main()
