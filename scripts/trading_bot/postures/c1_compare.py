#!/usr/bin/env python3
"""POSTURE C1 -- assemble the crypto-vs-equity side-by-side and apply the
pre-registered kill lines from PREREG_C1.json. No new estimation here."""
import json
OUT = "/home/anont/meme/research/postures/c1_equity_skew"
pre = json.load(open(f"{OUT}/PREREG_C1.json"))
cry = json.load(open(f"{OUT}/crypto_baseline.json"))
eq  = json.load(open(f"{OUT}/c1_result.json"))
bias = json.load(open(f"{OUT}/survivorship_biased_contrast.json"))
cost = json.load(open(f"{OUT}/cost_measured.json"))

rows = []
c = cry
rows.append({
    "market": "CRYPTO perps (Binance USD-M, incl. delisted)",
    "screen": "quote vol >= $1M/day",
    "days": c["panel"]["days_used"], "avg_names": c["panel"]["avg_liquid_names_per_day"],
    "EW_bp_day": round(c["pp_per_day"]["EW_mean_simple_liquid"] * 100, 2),
    "MEDIAN_bp_day": round(c["pp_per_day"]["MEDIAN_simple_liquid"] * 100, 2),
    "GAP_bp_day": round(c["gap_pp_per_day"]["like_for_like_both_SIMPLE"] * 100, 2),
    "GAP_ci95_bp": [round(x * 100, 2) for x in c["gap_pp_per_day"]["ci95_like_for_like"]],
    "compound_EW_pct": c["compounded_over_sample_pct"]["EW_liquid_basket"],
    "compound_median_pct": c["compounded_over_sample_pct"]["daily_cross_sectional_MEDIAN_simple"],
    "per_name_buyhold_median_pct": c["per_name_buyhold_while_liquid"]["median_pct"],
    "share_names_negative": c["per_name_buyhold_while_liquid"]["share_negative"],
    "top1pct_share_of_total": c["top_share_of_total_EW_return"]["top_1pct"]["share"],
    "top5pct_share_of_total": c["top_share_of_total_EW_return"]["top_5pct"]["share"],
    "round_trip_bp": 24.1,
})
for tag, d in eq["GATE3_effect"].items():
    e = eq["ECONOMICS"][tag]
    rows.append({
        "market": "US EQUITY (point-in-time NMS, incl. delisted)",
        "screen": tag,
        "days": d["days"], "avg_names": eq["GATE2_power"][tag]["avg_names_per_date"],
        "EW_bp_day": round(d["EW_mean_pp_per_day"] * 100, 2),
        "MEDIAN_bp_day": round(d["MEDIAN_pp_per_day"] * 100, 2),
        "GAP_bp_day": round(d["GAP_pp_per_day"] * 100, 2),
        "GAP_ci95_bp": [round(x * 100, 2) for x in d["GAP_ci95_pp"]],
        "compound_EW_pct": d["compound_EW_basket_pct"],
        "compound_median_pct": d["compound_daily_median_pct"],
        "per_name_buyhold_median_pct": d["per_name_buyhold_while_eligible"]["median_pct"],
        "per_name_buyhold_median_pct_delist_shock":
            d["per_name_buyhold_with_-30pct_delisting_shock"]["median_pct"],
        "share_names_negative": d["per_name_buyhold_while_eligible"]["share_negative"],
        "top1pct_share_of_total": d["top_share_of_total_EW_return"]["top_1pct"]["share"],
        "top5pct_share_of_total": d["top_share_of_total_EW_return"]["top_5pct"]["share"],
        "round_trip_bp": cost["round_trip_bp_median"],
        "gap_over_roundtrip_per_day": e.get("gap_over_roundtrip_per_day"),
        "MDE_bp_day": round(eq["GATE2_power"][tag]["MDE_governing_pp_per_day"] * 100, 3),
        "h21": d["h21_indep"], "h252": d["h252_indep"], "h252_overlap": d["h252_overlap"],
    })

crypto_gap = rows[0]["GAP_bp_day"]
kl = pre["kill_lines_declared_in_advance"]
verdicts = {}
for r in rows[1:]:
    lo, hi = r["GAP_ci95_bp"]
    if r["GAP_bp_day"] < 0.25 * crypto_gap and hi < 0.4375 * crypto_gap:
        v = "VIABLE_less_tail_dominated"
    elif lo >= 0.50 * crypto_gap:
        v = "DEAD_universal_skew"
    else:
        v = "MARGINAL"
    verdicts[r["screen"]] = {
        "verdict_vs_prereg": v,
        "gap_bp_day": r["GAP_bp_day"],
        "crypto_gap_bp_day": crypto_gap,
        "ratio_equity_over_crypto": round(r["GAP_bp_day"] / crypto_gap, 4),
        "prereg_viable_threshold_bp_day": round(0.25 * crypto_gap, 3),
        "prereg_dead_threshold_bp_day": round(0.50 * crypto_gap, 3),
        "also_required_252d_median_name_positive":
            r["h252"]["median_NAME_window_ret_mean_pct"] > 0,
    }
out = {"side_by_side": rows, "verdicts": verdicts,
       "survivorship_bias_contrast": bias, "cost": cost,
       "gate1": eq["GATE1_coverage"], "gate2": eq["GATE2_power"]}
print(json.dumps(out, indent=2))
json.dump(out, open(f"{OUT}/c1_comparison.json", "w"), indent=2)
