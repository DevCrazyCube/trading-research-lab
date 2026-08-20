#!/usr/bin/env python3
"""Verdict layer for the intraday equity/ETF relative-value sweep.

Reads the design, held-out and census JSONs and writes:
  research/trading_bot/SWEEP_intraday_rv.json   -- machine-readable verdict + full distribution
  research/trading_bot/SWEEP_intraday_rv.md     -- appends the verdict sections to rv_report.py's table

The one number that decides this theme is bp CAPTURED PER UNIT OF TURNOVER. Costs here are
charged as (cost_bp + reg_bp) x |dw|, so at the 1.0 bp/side headline rung a config must earn
more than 1.15 bp for every unit of turnover it generates or it loses money by construction,
independently of how good its gross Sharpe looks.
"""
from __future__ import annotations

import json
import pathlib

import numpy as np

OUT = pathlib.Path(__file__).resolve().parents[2] / "research" / "trading_bot"
HEADLINE_BP = 1.0
REG_BP = 0.15


def bp_per_turnover(r: dict) -> float:
    """Gross bp earned per unit of |dw|. ann_ret in the JSON is NET at the headline rung."""
    turn = r["daily_turnover"]
    if not turn or not np.isfinite(turn) or turn <= 0:
        return float("nan")
    gross_ann = r["ann_ret"] + turn * 252 * (HEADLINE_BP + REG_BP) * 1e-4
    return gross_ann / (turn * 252) * 1e4


def main() -> None:
    d = json.loads((OUT / "SWEEP_intraday_rv_design.json").read_text())
    hp = OUT / "SWEEP_intraday_rv_heldout.json"
    h = json.loads(hp.read_text()) if hp.exists() else None
    cp = OUT / "SWEEP_intraday_rv_census.json"
    c = json.loads(cp.read_text()) if cp.exists() else None

    nb = d["null_max_sharpe"]
    bar = nb["p95"]
    res = d["results"]
    for r in res:
        r["bp_per_turnover"] = bp_per_turnover(r)

    breakeven = HEADLINE_BP + REG_BP
    bpt = np.array([r["bp_per_turnover"] for r in res if np.isfinite(r["bp_per_turnover"])])
    clearing = [r["name"] for r in res if r["sharpe_1.0bp"] > bar]
    positive = [r["name"] for r in res if r["sharpe_1.0bp"] > 0]

    verdict = {
        "theme": "intraday equity/ETF relative value & mean reversion",
        "verdict": "NOISE_AND_WORSE -- dead on costs, not merely unproven",
        "n_formulas_tested": len(res),
        "design_window": d["window"],
        "heldout_window": h["window"] if h else None,
        "noise_bar_p95_block_bootstrap": bar,
        "noise_bar_naive_sqrt2lnN": nb["naive_sqrt_2lnN"],
        "n_clearing_noise_bar": len(clearing),
        "n_with_positive_net_sharpe_at_headline": len(positive),
        "best_design_net_sharpe_1bp": max(r["sharpe_1.0bp"] for r in res),
        "best_design_gross_sharpe": max(r["sharpe_gross"] for r in res),
        "gross_noise_bar_p95": d["null_max_sharpe_gross"]["p95"],
        "mechanism": {
            "break_even_bp_per_unit_turnover": breakeven,
            "best_bp_per_unit_turnover": float(bpt.max()),
            "median_bp_per_unit_turnover": float(np.median(bpt)),
            "n_above_break_even": int((bpt > breakeven).sum()),
            "note": "not one of the formulas captures enough per unit of turnover to pay the "
                    "headline spread. The best gross Sharpes in the sweep (up to "
                    f"{max(r['sharpe_gross'] for r in res):+.2f}) come from configs that "
                    "capture ~0.18 bp per unit of turnover at 60-110x daily turnover: the "
                    "signal is real and it is smaller than any plausible spread.",
        },
        "distribution": d["distribution"],
        "held_out_negative_control": (
            [{"name": r["name"], "sharpe_gross": r["sharpe_gross"],
              "sharpe_1.0bp": r["sharpe_1.0bp"], "sharpe_2.5bp": r["sharpe_2.5bp"],
              "ann_ret": r["ann_ret"], "n_days": r["n_days"]} for r in h["results"]]
            if h else None),
        "held_out_note": (
            "Run under pre-registration rule 4: NOTHING cleared the design noise bar, so the "
            "top 3 went out of sample explicitly as a documented negative control, not as "
            "candidate edges. D1 and D3 are numerically identical -- cross-sectional "
            "demeaning makes gap_resid_reversal the same portfolio as gap_reversal."),
        "known_reporting_bug": (
            "rv_sweep.daily_turnover uses np.bincount(day[mask]).mean() with GLOBAL day "
            "indices, so in the held-out stage (whose days start at index ~1005) the printed "
            "turnover is scaled by n_days_in_window/(max_day+1) = 405/1410. The held-out "
            "turnover figures are understated by ~3.5x. Sharpe, ann_ret and n_days are "
            "unaffected -- daily_series() masks days correctly. Design-stage turnover is "
            "correct because the design window starts at day 0."),
        "ranked": [{"name": r["name"], "kind": r["kind"], "turn": r["daily_turnover"],
                    "gross": r["sharpe_gross"], "net_0.5bp": r["sharpe_0.5bp"],
                    "net_1.0bp": r["sharpe_1.0bp"], "net_2.5bp": r["sharpe_2.5bp"],
                    "bp_per_turnover": r["bp_per_turnover"]} for r in res],
    }
    if c and "summary" in c:
        sib = c["sibling_pairs"]
        true_same_claim = {k: v for k, v in sib.items()
                           if k in ("SPY/IVV", "SPY/VOO", "IVV/VOO", "SPY/SPLG", "VTI/ITOT",
                                    "QQQ/QQQM", "GLD/IAU", "GLD/GLDM", "IAU/GLDM", "IWM/VTWO",
                                    "IJH/MDY", "EFA/IEFA", "EEM/IEMG", "AGG/BND")}
        verdict["census"] = {
            "round_trip_cost_bp_two_leg": c["round_trip_cost_bp_two_leg"],
            "summary": c["summary"],
            "true_same_claim_pairs": {
                k: {"p95_abs_bp": v["p95_abs_bp"], "ac1": v["ac1"],
                    "implied_halflife_bars": v["implied_halflife_bars"],
                    "p95_over_round_trip": v["tradable_p95_over_cost"]}
                for k, v in true_same_claim.items()},
            "reading": "The census 'median p95 = 2.2x round trip' headline is misleading and "
                       "the sweep is what exposes it. The pairs that clear the cost line are "
                       "the ones that are NOT the same claim (SPY/VTI, levered-vs-base, "
                       "sector-SPDR-vs-Vanguard): their spread is wide because it genuinely "
                       "drifts, which is why an ac(1) of 0.96 buys nothing. The genuinely "
                       "same-claim pairs -- SPY/IVV/VOO, IVV/VOO -- have a p95 displacement "
                       "of ~1.5 bp against a 4.6 bp round trip and an ac(1) near 0.1, i.e. a "
                       "half-life under half a bar. That is non-synchronous printing, not a "
                       "dislocation, and it cannot be taken by a taker at any threshold.",
        }

    (OUT / "SWEEP_intraday_rv.json").write_text(json.dumps(verdict, indent=1))

    md = OUT / "SWEEP_intraday_rv.md"
    body = md.read_text() if md.exists() else ""
    L = []
    L.append("\n## VERDICT — the theme is dead, and it is dead on mechanism\n")
    L.append(f"- **{len(res)} formulas** tested on design, **{len(clearing)}** cleared the "
             f"block-bootstrap noise bar (p95 = {bar:+.2f}).")
    L.append(f"- **{len(positive)} of {len(res)}** are even *positive* at the 1.0 bp/side "
             f"headline rung. The best is {max(r['sharpe_1.0bp'] for r in res):+.2f}.")
    L.append(f"- Gross, the signal is real: best gross Sharpe {max(r['sharpe_gross'] for r in res):+.2f} "
             f"against a gross noise bar of {d['null_max_sharpe_gross']['p95']:+.2f}. Intraday "
             "ETF/mega-cap mean reversion exists. It is simply smaller than the spread.")
    L.append("")
    L.append(f"### The decisive number: bp captured per unit of turnover\n")
    L.append(f"Costs are charged as `(spread + reg) x |dw|`, so break-even at the headline rung "
             f"is **{breakeven:.2f} bp per unit of turnover**.\n")
    L.append("| | bp per unit turnover |")
    L.append("|---|---|")
    L.append(f"| break-even needed (1.0 bp/side + 0.15 bp reg) | {breakeven:.2f} |")
    L.append(f"| best of all {len(res)} formulas | {bpt.max():.3f} |")
    L.append(f"| median formula | {np.median(bpt):.3f} |")
    L.append(f"| formulas above break-even | **{int((bpt > breakeven).sum())} of {len(res)}** |")
    L.append("")
    L.append("The high-gross-Sharpe end of the sweep is the clearest statement of the problem: "
             "`C1_xs_rev_mega_lb1` earns a +6.1 gross Sharpe while capturing 0.18 bp per unit "
             "of turnover at 109x daily turnover. There is no cost rung, no threshold and no "
             "holding period that turns 0.18 bp into a trade.")
    L.append("")
    if h:
        L.append("### Held-out (pre-registered negative control)\n")
        L.append("Nothing cleared the design bar, so rule 4 of the pre-registration applies: the "
                 "top 3 were still run out of sample, explicitly as a negative control.\n")
        L.append("| formula | gross | net 0.5bp | net 1bp | net 2.5bp | ann ret | days |")
        L.append("|---|---|---|---|---|---|---|")
        for r in h["results"]:
            L.append(f"| `{r['name']}` | {r['sharpe_gross']:+.2f} | {r['sharpe_0.5bp']:+.2f} | "
                     f"{r['sharpe_1.0bp']:+.2f} | {r['sharpe_2.5bp']:+.2f} | "
                     f"{r['ann_ret']*100:+.2f}% | {r['n_days']} |")
        L.append("")
        L.append("+0.06 out of sample at the headline rung on a 405-day window is zero. It is "
                 "reported as zero, not as a survivor.")
        L.append("")
        L.append(f"> **Reporting bug, disclosed:** {verdict['known_reporting_bug']}")
        L.append("")
    if "census" in verdict:
        L.append("### Why the census summary line is not the good news it looks like\n")
        L.append(verdict["census"]["reading"])
        L.append("")
        L.append("| same-claim pair | p95 displacement | round trip | ac(1) | half-life (bars) |")
        L.append("|---|---|---|---|---|")
        for k, v in verdict["census"]["true_same_claim_pairs"].items():
            hl = v["implied_halflife_bars"]
            L.append(f"| {k} | {v['p95_abs_bp']:.1f} bp | "
                     f"{verdict['census']['round_trip_cost_bp_two_leg']:.1f} bp | "
                     f"{v['ac1']:.2f} | {hl:.1f} |")
        L.append("")
    md.write_text(body + "\n".join(L) + "\n")
    print(f"wrote {OUT / 'SWEEP_intraday_rv.json'} and appended verdict to {md}")


if __name__ == "__main__":
    main()
