#!/usr/bin/env python3
"""Render SWEEP_futures_term_structure.md from the design + holdout JSON artifacts."""
from __future__ import annotations

import json
import pathlib

OUT = pathlib.Path(__file__).resolve().parents[2] / "research" / "trading_bot"
THEME = "futures_term_structure"

GROUPS = {
    "A_ladder": "A. Maturity-ladder term structure (ETF pair spreads: USL/USO, UNL/UNG, DBC/GSG, GC=F/GLD)",
    "B_xs_carry": "B. Cross-sectional carry over a 12-commodity panel",
    "C_mom": "C. Momentum and carry x momentum combinations",
    "D_seasonality": "D. Seasonality (expanding-window and fixed-prior)",
    "E_volterm": "E. Volatility term structure (VIX curve)",
    "F_eqbasis": "F. Equity-index futures basis",
    "G_rates": "G. Rates curve carry / rolldown",
    "H_multi": "H. Multi-asset carry composites",
}


def main() -> int:
    d = json.loads((OUT / f"SWEEP_{THEME}_DESIGN.json").read_text())
    hp = OUT / f"SWEEP_{THEME}_HOLDOUT.json"
    hold = json.loads(hp.read_text()) if hp.exists() else []
    nm = d["bootstrap_null"]
    dist = d["design_sharpe_distribution"]
    res = d["results"]
    p = d["bootstrap_p_values"]
    bar = nm["expected_max_sharpe"]
    best = res[0]

    L = []
    A = L.append
    A(f"# Sweep: futures/commodities term structure, roll, seasonality, carry-momentum\n")
    A(f"**Verdict: the theme is noise.** {d['n_formulas_tested']} structurally different formulas, "
      f"best design Sharpe **{best['sharpe']:+.2f}** against a bootstrap expected-max-under-null of "
      f"**{bar:+.2f}**. The winner does not clear the bar it has to clear "
      f"(bootstrap p = {p[best['name']]:.3f}); nothing in the sweep does.\n")

    A("## How this was scored\n")
    A(f"- **Design window:** {d['design_window']} (~{res[0]['years']:.0f}y). "
      f"**Held out:** {d['holdout_window_reserved']}\n")
    A(f"- **Formulas tested:** {d['n_formulas_tested']}. The search is sign-agnostic "
      f"(a curve signal has no sign this sweep is entitled to assume), so it is "
      f"**{2*d['n_formulas_tested']} effective one-sided tries**.\n")
    A(f"- **Analytic bar:** sqrt(2 ln 2N) = {d['analytic_expected_max_t_sqrt2ln2N']:.2f} in Sharpe-SE "
      f"units = Sharpe **{d['analytic_expected_max_sharpe']:.2f}**.\n")
    A(f"- **Bootstrap bar ({nm['B']} draws):** circularly shift the realised return matrix against "
      f"the fixed weight matrices. This preserves each formula's turnover and cost line exactly, "
      f"the return autocorrelation, the cross-asset correlation, and the correlation *between "
      f"formulas* -- so the max is over {d['n_formulas_tested']} correlated tries, not "
      f"{d['n_formulas_tested']} independent ones. Statistic drawn is identical to the one reported: "
      f"best-of-two-signs, net of costs.\n")
    A(f"  - E[max Sharpe] = **{nm['expected_max_sharpe']:.2f}**, "
      f"p95 = {nm['p95_max_sharpe']:.2f}, p99 = {nm['p99_max_sharpe']:.2f}\n")
    A(f"- **Costs charged** per side of turnover, in bp of notional: SPY 1, GLD/TLT 1.5, "
      f"SLV/IEF/SHY/IAU 2, USO 3, UNG/DBC/PDBC 4, GSG/DBA/SVXY/VIXY 8, USL/BNO/PPLT 10, "
      f"CORN/WEAT/SOYB/UGA/DJP/DBB/DBE 12, UNL/CANE/CPER 15. "
      f"Provenance is ASSUMED (spread-scale for these ETFs), not measured -- so gross Sharpe and the "
      f"annual cost drag are reported per formula and you can re-charge any row yourself.\n")

    A("\n## The data fact that shaped the whole design\n")
    A("Yahoo's `X=F` continuous series is the **front contract's price, spliced** -- each contract "
      "drifts down toward spot inside its life and the splice gaps back up at every roll, so the "
      "roll yield is silently deleted. Measured over 2007-01-03..2018-12-31: the CL=F price series "
      "fell **~25%** while USO -- an actual front-month WTI position -- fell **80.4%**. That 55pp gap "
      "*is* the contango drag. Any backtest that takes P&L from `=F` returns books it as profit.\n")
    A("So `=F` series are used **only as signal inputs** (they are a fine spot proxy) and every P&L "
      "leg is an ETF adjusted-close return, which is real, holdable, and roll-and-fee-inclusive.\n")
    A("The carry estimator is `carry_i(t) = 252 * mean_k[ logret(ETF_i) - logret(FUT_i) ]`, consumed "
      "only as a z-score against its own history or a cross-sectional rank -- both invariant to the "
      "constant per-name offset (expense ratio, collateral yield). Sanity check on the levels, which "
      "come out economically right: crude -10.1%/yr, natgas -29.1%/yr, wheat -10.7%/yr (all deep "
      "contango over the window), gold -0.4%/yr (GLD is spot-backed, so this is just its fee).\n")

    A("\n## Full design distribution (every formula, not just the winner)\n")
    A(f"| min | p25 | median | p75 | max |\n|---|---|---|---|---|\n"
      f"| {dist['min']:+.2f} | {dist['p25']:+.2f} | {dist['median']:+.2f} | "
      f"{dist['p75']:+.2f} | {dist['max']:+.2f} |\n")
    A(f"\nFormulas above the bootstrap E[max] ({bar:+.2f}): **{dist['n_above_bootstrap_expected_max']}** "
      f"of {d['n_formulas_tested']}. Above bootstrap p95 ({nm['p95_max_sharpe']:+.2f}): "
      f"**{dist['n_above_bootstrap_p95']}**.\n")
    A("\nA null search over this many correlated tries is *expected* to hand back a best of about "
      f"{bar:+.2f}. It handed back {best['sharpe']:+.2f}. That is the finding.\n")

    A("\n## Every formula, by group\n")
    by_g = {}
    for r in res:
        by_g.setdefault(r["group"], []).append(r)
    for g, title in GROUPS.items():
        rows = sorted(by_g.get(g, []), key=lambda r: -r["sharpe"])
        if not rows:
            continue
        A(f"\n### {title}\n")
        A("| formula | net SR | sign | gross SR | cost %/yr | ann ret | vol | maxDD | boot p |\n")
        A("|---|---|---|---|---|---|---|---|---|\n")
        for r in rows:
            A(f"| `{r['name']}` | **{r['sharpe']:+.2f}** | {r['orientation']:+d} | "
              f"{r['gross_sharpe']:+.2f} | {r['cost_drag_annual']*100:.2f} | "
              f"{r['ann_ret']*100:+.1f}% | {r['ann_vol']*100:.1f}% | {r['max_dd']*100:.0f}% | "
              f"{p[r['name']]:.3f} |\n")
        A("\n")
        for r in rows:
            A(f"- `{r['name']}` -- {r['desc']}\n")

    A("\n## What the sweep caught in itself\n")
    A("Two methodology traps fired during this run and both would have manufactured an 'edge'.\n")
    A("\n**1. Ranking a sign-agnostic search by |t| of the net series promotes turnover, not signal.** "
      "The first cut crowned `B3_XS_CARRY_21` at t = -3.80. Its *gross* Sharpe was only -0.78; the "
      "rest was a 7.9%/yr cost line on an 8.1%-vol book. Costs do not flip when the signal does, so "
      "-W does not earn +1.74 -- it earns +0.78 gross minus the same 7.9%/yr, i.e. nothing. Scoring "
      "now takes `max(SR_net(+W), SR_net(-W))` and the null draws the identical statistic.\n")
    A("\n**2. A short-window ETF-minus-futures 'carry' is mostly stale-price reversion.** The ETF "
      "and its futures print at different times and the ETF carries a mean-reverting premium/discount, "
      "so a 21-day carry estimate is partly a recent *price* move. The tell was that the family got "
      "monotonically stronger as the estimation window got *shorter* (21d > 63d > 252d) -- the opposite "
      "of what a real roll-yield signal does. `B9_XS_CARRY_SKIP21` measures carry over [t-84, t-21] "
      "instead, skipping the last month: gross Sharpe collapses from +0.78 to "
      f"{next((r['gross_sharpe'] for r in res if r['name']=='B9_XS_CARRY_SKIP21'), float('nan')):+.2f}. "
      "It was price overlap wearing a carry costume.\n")

    if hold:
        A("\n## Held-out numbers\n")
        A("No formula earned a held-out look -- none cleared the noise bar on design. The top 3 are "
          "shown anyway as further evidence for the noise verdict; nothing was selected on these.\n\n")
        A("| formula | design SR | HELD-OUT SR | held-out ret | held-out vol | maxDD | yrs |\n")
        A("|---|---|---|---|---|---|---|\n")
        for r in hold:
            h, dd = r["holdout"], r["design"]
            A(f"| `{r['name']}` | {dd['sharpe']:+.2f} | **{h['sharpe']:+.2f}** | "
              f"{h['ann_ret']*100:+.1f}% | {h['ann_vol']*100:.1f}% | {h['max_dd']*100:.0f}% | "
              f"{h['years']} |\n")

    if hold:
        hd = {r["name"]: r for r in hold}
        w = hd.get(best["name"])
        if w:
            A(f"\nThe design winner behaved exactly as a noise winner behaves: "
              f"`{best['name']}` went **{w['design']['sharpe']:+.2f} -> "
              f"{w['holdout']['sharpe']:+.2f}** with an "
              f"{w['holdout']['max_dd']*100:.0f}% held-out drawdown.\n")
        A("\nTwo composites (`H1_MULTI_ASSET_CARRY`, `E2_VIX_CONTANGO_SHORTVOL`) held their level "
          "across both windows (~+0.6 on each). That is worth writing down, but it is **not** an "
          "edge claim: +0.6 sits below the +0.78 bar this search has to clear, their held-out "
          "t-stats are ~1.5, and both run 24-37% vol with 33-44% drawdowns. They are consistent "
          "with a real but small risk premium (short vol, term-structure carry) that this sweep "
          "has no power to separate from luck -- and that a levered book would not survive.\n")

    A("\n## Conclusion\n")
    A("Across maturity-ladder term structure, cross-sectional and time-series carry, basis momentum, "
      "carry x momentum, expanding-window and fixed-prior seasonality, the VIX curve, the equity-index "
      "futures basis, and rates curve carry -- on free daily data, charged realistic ETF spreads -- "
      f"the best of {d['n_formulas_tested']} formulas reached Sharpe {best['sharpe']:+.2f} against an "
      f"expected-max-under-null of {bar:+.2f}.\n")
    A("\n**No formula in this theme is promotable.** The design winner is indistinguishable from the "
      "best draw of a null search of the same size and shape.\n")
    A("\nArtifacts: `research/trading_bot/SWEEP_futures_term_structure.json` (design + holdout, "
      "combined), `..._DESIGN.json`"
      + (", `..._HOLDOUT.json`" if hold else "")
      + ". Harness: `scripts/trading_bot/ts_sweep.py`, data cache: `scripts/trading_bot/ts_fetch.py` "
        "-> `research/data/ts_cache/`.\n")

    (OUT / f"SWEEP_{THEME}.md").write_text("".join(L))
    combined = {
        "theme": THEME,
        "verdict": "NOISE -- no formula clears the expected-max-under-null bar",
        "design": d,
        "holdout_top3_for_completeness": hold,
    }
    (OUT / f"SWEEP_{THEME}.json").write_text(json.dumps(combined, indent=2))
    print("wrote", OUT / f"SWEEP_{THEME}.md", "and", OUT / f"SWEEP_{THEME}.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
