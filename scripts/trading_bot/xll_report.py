#!/usr/bin/env python3
"""Merge the XLL blocks into research/trading_bot/SWEEP_xll_leadlag.{md,json}."""
import json, os
import numpy as np

R = "/home/anont/meme/research/trading_bot"
BLOCKS = [("crypto", f"{R}/SWEEP_xll_crypto.json"),
          ("crypto_addendum", f"{R}/SWEEP_xll_crypto_addendum.json"),
          ("equity", f"{R}/SWEEP_xll_equity.json")]
FOCUS = f"{R}/SWEEP_xll_equity_P2_FOCUS.json"


def dist(v):
    v = np.array(sorted(v))
    return dict(n=len(v), min=float(v[0]), p10=float(np.percentile(v, 10)), p25=float(np.percentile(v, 25)),
                median=float(np.median(v)), p75=float(np.percentile(v, 75)), p90=float(np.percentile(v, 90)),
                max=float(v[-1]), mean=float(v.mean()), sd=float(v.std()))


def main():
    bl = [(t, json.load(open(p))) for t, p in BLOCKS if os.path.exists(p)]
    L = []
    A = L.append
    A("# SWEEP — cross-asset & cross-venue lead-lag")
    A("")
    A("**Verdict: the theme is noise.** 74 structurally different lead-lag formulas were built and")
    A("scored on a design window. Every formula whose signal is a *pure* cross-asset transmission —")
    A("one asset's past return predicting another's future return, with no term for the predicted")
    A("asset's own past return — sits at or below its noise bar, in both crypto and equities. The")
    A("formulas that post spectacular design numbers all share one component, the laggard's OWN")
    A("lagged return, and that component is the 5-minute bid-ask bounce, not a lead-lag: it decays")
    A("from Sharpe 20 at 5m to 0.1 at 1h, and it loses 100-400 Sharpe points to fees.")
    A("")
    A("One formula out of 74 clearly cleared its bar: `P2_ovn_gap_reversal`, design gross 2.12")
    A("against a bar of 0.84, held-out gross 1.43. The focused pass below kills it as an answer to")
    A("*this* theme and very nearly kills it outright:")
    A("")
    A("- **The cross-asset term does no work.** Delete the SPY-beta neutralisation entirely and the")
    A("  held-out number goes UP (1.43 -> 1.54). P2 is a single-name overnight-gap reversal that")
    A("  happened to be wearing a lead-lag hat; it is not evidence for cross-asset transmission.")
    A("- **It breaks even at 5.6 bp per side on the held-out window.** The sweep charged 5. That is")
    A("  not a margin, it is a rounding error, and the trade is a market-on-open entry across ~2,900")
    A("  names where the auction spread is the widest of the day.")
    A("- **On names liquid enough to justify a 5 bp fill it is gone.** Top half by dollar volume:")
    A("  held-out gross 0.83, breakeven 3.0 bp. Top quintile: 0.13, breakeven 0.5 bp. The effect")
    A("  lives exactly where the cost assumption stops being defensible.")
    A("")
    A("Nothing here should be promoted to a forward test.")
    A("")
    A("## Method, and what makes the noise bar honest")
    A("")
    A("- Every formula scored on a **design window only**. The held-out window was computed by the")
    A("  same harness but never used to choose anything; it is reported for the survivors as the")
    A("  real test, and for everything else only so the full table is visible.")
    A("- The noise bar is **empirical, not `sqrt(2 ln N)`**. Each null draw time-shifts the return")
    A("  matrix (by at least a day, both signs) and re-scores *every* formula against the shifted")
    A("  returns using the *same* shift. That destroys any lead-lag relation while preserving each")
    A("  formula's turnover and autocorrelation, and — crucially — preserving how correlated the")
    A("  formulas are with each other. Max-over-formulas of that is the expected max under the null.")
    A("  The naive `sqrt(2 ln N) x SD` is printed alongside; it assumes independent tries and is the")
    A("  wrong bar for a family this correlated.")
    A("- **Lookahead audit, automated.** Every context is rebuilt with everything past 65% of the")
    A("  sample replaced by reversed, rescaled prices; a formula whose weights on the surviving")
    A("  prefix change at all is reading the future. This caught a real bug (`N1_liqtier_lead` was")
    A("  using the leader basket's *same-day* return and scored 2.83; corrected it scores 0.43).")
    A("  Final state: 31/31 equity formulas and 32/32 crypto formulas at two frequencies, CLEAN.")
    A("- Costs are charged per side on `sum|w_t - w_{t-1}|`, and the provenance of each number is")
    A("  stated rather than assumed.")
    A("")
    summary = {"theme": "cross-asset & cross-venue lead-lag", "blocks": {}}
    total = 0
    for tag, d in bl:
        res = d["results"]
        total += len(res)
        nl = d["null"]
        bar = nl["expected_max_sharpe"]
        g = [r["gross_sharpe"] for r in res]
        dd = dist(g)
        A(f"## Block: `{d['block']}`")
        A("")
        A(f"- panel: `{d.get('panel','(shared with the parent crypto block)')}`")
        A(f"- design: {d['design_window'][0]} .. {d['design_window'][1]}   |   held out: {d['holdout_window'][0]} .. {d['holdout_window'][1]}")
        A(f"- formulas: **{len(res)}**")
        A(f"- cost: **{d['cost_bp_per_side']} bp per side** — {d['cost_provenance']}")
        if d.get("known_bias"):
            A(f"- known bias: {d['known_bias']}")
        A("")
        A("**Full design gross-Sharpe distribution (every formula, nothing dropped):**")
        A("")
        A("| n | min | p10 | p25 | median | p75 | p90 | max | mean | sd |")
        A("|---|---|---|---|---|---|---|---|---|---|")
        A("| " + " | ".join([str(dd["n"])] + [f"{dd[k]:.2f}" for k in
          ("min", "p10", "p25", "median", "p75", "p90", "max", "mean", "sd")]) + " |")
        A("")
        A("**Noise bar:**")
        A("")
        A(f"- {nl['n_draws']} null draws — {nl['method']}")
        A(f"- SD of one formula's Sharpe under the null: **{nl['sd_single_config_sharpe']:.2f}**")
        A(f"- **expected max over these {len(res)} formulas under the null: {bar:.2f}**   (p95: {nl['p95_max_sharpe']:.2f})")
        A(f"- naive `sqrt(2 ln N) x SD` for comparison: {nl['naive_sqrt2lnN']:.2f}")
        A("")
        A("| formula | design gross SR | x bar | design net SR | turnover/bar | held-out gross SR | held-out net SR | what it is |")
        A("|---|---|---|---|---|---|---|---|")
        for r in sorted(res, key=lambda x: -x["gross_sharpe"]):
            tn = r.get("turnover_per_bar", r.get("turnover_per_day"))
            A(f"| `{r['name']}` | {r['gross_sharpe']:+.2f} | {r['gross_sharpe']/bar:+.2f} | {r['net_sharpe']:+.2f} | "
              f"{tn:.2f} | {r['holdout_gross_sharpe']:+.2f} | {r['holdout_net_sharpe']:+.2f} | {r['formula_desc']} |")
        A("")
        summary["blocks"][tag] = dict(n_formulas=len(res), design_gross_distribution=dd, null=nl,
                                      design_window=d["design_window"], holdout_window=d["holdout_window"],
                                      cost_bp_per_side=d["cost_bp_per_side"], results=res)
    if os.path.exists(FOCUS):
        f = json.load(open(FOCUS))
        A("## Focused pass on the one survivor (`P2_ovn_gap_reversal`)")
        A("")
        A("P2 was the only formula in 74 to clearly clear its bar (design gross 2.12 against a bar of")
        A("0.84). It is a stock's own overnight gap, minus its beta-implied share of SPY's overnight")
        A("gap, faded from today's open to today's close. Three questions the sweep table cannot")
        A("answer: does the cross-asset term do anything, what cost turns it off, and does it survive")
        A("on names where a 5bp fill is defensible.")
        A("")
        A("| variant | design gross SR | held-out gross SR | turnover/day | breakeven cost/side (design) | breakeven (held-out) | net@5bp d/h | net@10bp d/h |")
        A("|---|---|---|---|---|---|---|---|")
        for r in f["rows"]:
            A(f"| {r['variant']} | {r['design_gross_sharpe']:+.2f} | {r['holdout_gross_sharpe']:+.2f} | "
              f"{r['turnover_per_day']:.2f} | {r['breakeven_cost_bp_per_side_design']:.1f} bp | "
              f"{r['breakeven_cost_bp_per_side_holdout']:.1f} bp | "
              f"{r['design_net_sharpe_5bp']:+.2f} / {r['holdout_net_sharpe_5bp']:+.2f} | "
              f"{r['design_net_sharpe_10bp']:+.2f} / {r['holdout_net_sharpe_10bp']:+.2f} |")
        A("")
        summary["p2_focus"] = f
    summary["n_formulas_total"] = total
    json.dump(summary, open(f"{R}/SWEEP_xll_leadlag.json", "w"), indent=1)
    open(f"{R}/SWEEP_xll_leadlag.md", "w").write("\n".join(L) + "\n")
    print(f"WROTE {R}/SWEEP_xll_leadlag.md and .json  ({total} formulas)")


if __name__ == "__main__":
    main()
