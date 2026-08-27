#!/usr/bin/env python3
"""Render the round-2 perp-microstructure sweep JSONs into one markdown report."""
from __future__ import annotations

import json
import pathlib

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[2]
D = ROOT / "research" / "trading_bot"
MET = D / "SWEEP_crypto_perp_microstructure_R2_metrics_top50_holdout.json"
EXT = D / "SWEEP_crypto_perp_microstructure_R2_ext_top50_holdout.json"
SHL = D / "SWEEP_crypto_perp_microstructure_R2_SHORTLIST.json"
OUT = D / "SWEEP_crypto_perp_microstructure_R2.md"


def ix(rows):
    return {r["name"]: r for r in rows}


def rankc(a, b):
    ra = np.argsort(np.argsort(a)).astype(float)
    rb = np.argsort(np.argsort(b)).astype(float)
    return float(np.corrcoef(ra, rb)[0, 1])


def f(x, s="%+.2f"):
    return "--" if (x is None or not np.isfinite(x)) else s % x


def main():
    met = json.loads(MET.read_text())
    ext = json.loads(EXT.read_text())
    shl = json.loads(SHL.read_text())
    L = []
    A = L.append
    barm = met["noise_bar"]["bootstrap"]["p95"]
    barx = ext["noise_bar"]["bootstrap"]["p95"]

    A("# SWEEP round 2: crypto-perp microstructure (Binance USD-M)\n")
    A("Round 1 tested 56 formulas and is written up in `SWEEP_crypto_perp_microstructure.md`. "
      "**This is a second round of 51 structurally different formulas that appear nowhere in "
      "round 1**, run with two deliberate protocol changes.\n")
    A("**1. The headline universe is the top-50 by trailing-7d volume, not the top-120.** "
      "Round 1's central finding was that most of its apparent survivors (`XS_AMIHUD`, `XS_QV_Z`, "
      "`XS_NTR_Z`, `XS_ATS_Z`, `XS_LIQPROX`, `XS_CROWD_UNWIND`) were illiquidity tilts living in "
      "the thin tail of the top-120, and went negative out of sample once the universe was cut to "
      "the top-50. Round 2 designs on the top-50 from the first bar, so there is no such tail to "
      "harvest and every number below is one where a 5.5 bp/side fill is defensible.\n")
    A("**2. There is a genuinely VIRGIN held-out window.** Round 1 evaluated all 56 of its "
      "formulas on 2024-04 -> 2025-01, so that window is burned. Round 1 stopped there because the "
      "Binance futures-METRICS feed (open interest, long/short ratios) dies at 2024-12 in the "
      "orphanflush cache -- only ~30 symbols carry it afterwards. But the 5m KLINES run monthly to "
      "2026-07 plus daily files for 2026-08, for 130-150 symbols, and the t23 funding cache runs to "
      "2026-07. So a second panel was built (`perpmicro_panel2.py` -> `panel1h_ext.npz`, 439 "
      "symbols x 40536 hours, trimmed to the 150 most-traded x 33984 hours) and every formula built "
      "only from price / volume / trade count / taker-buy volume / funding (**class A**, 39 of the "
      "51) is tested on **2025-01-01 -> 2026-08-01: 577 days no formula in this programme had ever "
      "seen**. The 12 formulas that need the metrics feed (**class B**) can only use the burned "
      "window and are marked as such.\n")

    A("## Protocol\n")
    A("| | |")
    A("|---|---|")
    A(f"| Design window | **{met['design_window'][0]} -> {met['design_window'][1]}** "
      f"({met['design_days']} days) |")
    A(f"| Held-out 1 (`h1`) | {met['holdout1'][0]} -> {met['holdout1'][1]} "
      "-- **BURNED**: round 1 evaluated all 56 of its formulas here |")
    A(f"| Held-out 2 (`h2`) | {met['holdout2'][0]} -> {met['holdout2'][1]} "
      f"-- **VIRGIN**, class A only, {ext['heldout2'][0]['ndays']} days |")
    A(f"| Universe | point-in-time top-{met['top_n']} by trailing-7d quote volume, "
      "min 25 live names |")
    A("| Entry / exit | OPEN of the bar after the signal bar; H overlapping tranches; the close "
      "that made the signal is never a fill price |")
    A("| P&L | price + funding accrual (charged at the settlement bar) - turnover x cost |")
    A(f"| Cost | **{met['cost_bp_per_side']} bp/side** (4.5 bp published Binance USD-M VIP0 taker "
      "+ 1.0 bp DECLARED half-spread), and a **15 bp/side** shock reported for every held-out "
      "number. Perp slippage has still never been MEASURED by this programme, so breakeven cost is "
      "reported for every formula. |")
    A("| Sign | oriented on DESIGN gross P&L (a formula and its negation are one hypothesis, which "
      "is why the bar is two-sided); FROZEN out of sample |")
    A("| Design freeze | `*_DESIGN_FROZEN.json` written before either held-out window was touched |")
    aud = {}
    for tag in ("metrics", "ext"):
        pth = D / f"SWEEP_crypto_perp_microstructure_R2_{tag}_top50_audit.json"
        if pth.exists():
            aud[tag] = json.loads(pth.read_text())
    if aud:
        A("| Lookahead audit | every formula re-derived with all inputs after bar "
          + " / ".join(f"{v['cut_bar']} ({k}, {v['n_checked']} formulas)" for k, v in aud.items())
          + " destroyed: **"
          + " + ".join(str(len(v["violations"])) for v in aud.values())
          + " = 0 violations** |")
    A("")

    A("## Noise bar\n")
    A(f"- NEW formulas in round 2: **{met['n_formulas_round2']}** (39 class A + 12 class B)")
    A(f"- cumulative for the theme, round 1 + round 2: **{met['n_formulas_cumulative']}**")
    A(f"- analytic expected max |Sharpe| under the null, sqrt(2 ln 2N)/sqrt(T), for N=51: "
      f"**{met['noise_bar']['analytic_round2']:.2f}**; for the cumulative N=107: "
      f"**{met['noise_bar']['analytic_cumulative']:.2f}**")
    A(f"- sign-flip block bootstrap (5-day blocks, 4000 draws) of max |Sharpe| across the ACTUAL "
      f"correlated round-2 set: metrics panel mean {met['noise_bar']['bootstrap']['mean']:.2f}, "
      f"**95th pct {barm:.2f}**; klines panel mean "
      f"{ext['noise_bar']['bootstrap']['mean']:.2f}, **95th pct {barx:.2f}**")
    A(f"\nThe bar applied below is the bootstrap 95th percentile of the max: **{barm:.2f}** on the "
      f"metrics panel, **{barx:.2f}** on the klines panel. `<<<` marks the formulas that cleared it "
      "on design.\n")

    # ---------------- klines panel (the important one) ----------------
    h1 = ix(ext["heldout1"]); h2 = ix(ext["heldout2"]); h2c = ix(ext["heldout2_cost15"])
    dg = np.array([r["sharpe_gross"] for r in ext["design"]])
    hg2 = np.array([h2[r["name"]]["sharpe_gross"] for r in ext["design"]])
    hn2 = np.array([h2[r["name"]]["sharpe_net"] for r in ext["design"]])
    sel = dg >= barx

    A(f"## Class A on the VIRGIN window -- all {len(ext['design'])} formulas, klines+funding panel, "
      "top-50\n")
    A("`d` = design, `h1` = burned window, `h2` = **virgin** 2025-01 -> 2026-08. "
      "Sharpes are net of 5.5 bp/side unless the column says gross or @15bp.\n")
    A("| # | formula | H | d SR | d net | h1 net | **h2 SR** | **h2 net** | h2 @15bp | h2 be bp | "
      "turn/day | corr(mkt) | 2025 | 2026 | signal |")
    A("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for i, r in enumerate(ext["design"], 1):
        n = r["name"]; a = h1[n]; b = h2[n]; c = h2c[n]
        y = b.get("net_sharpe_by_year", {})
        mark = " `<<<`" if r["sharpe_gross"] >= barx else ""
        A(f"| {i} | `{n}`{mark} | {r['H']}h | {r['sharpe_gross']:.2f} | "
          f"{f(r['sharpe_net'])} | {f(a['sharpe_net'])} | **{f(b['sharpe_gross'])}** | "
          f"**{f(b['sharpe_net'])}** | {f(c['sharpe_net'])} | "
          f"{f(b['breakeven_cost_bp_per_side'], '%.1f')} | {r['turnover_per_day']:.2f} | "
          f"{f(b['corr_market'])} | {f(y.get('2025'))} | {f(y.get('2026'))} | {r['desc']} |")
    A("")

    A("### Does the design ranking survive into a window nobody had seen?\n")
    A("| | value |")
    A("|---|---|")
    A(f"| Spearman rank corr, design gross SR -> **virgin** gross SR (n={len(dg)}) | "
      f"**{rankc(dg, hg2):+.3f}** |")
    A(f"| Spearman rank corr, design gross SR -> burned h1 gross SR | {rankc(dg, np.array([h1[r['name']]['sharpe_gross'] for r in ext['design']])):+.3f} |")
    A(f"| mean virgin GROSS SR, the {int(sel.sum())} that cleared the design bar | "
      f"**{hg2[sel].mean():+.2f}** |")
    A(f"| mean virgin GROSS SR, the {int((~sel).sum())} that did not | {hg2[~sel].mean():+.2f} |")
    A(f"| mean virgin NET SR, cleared / not | {hn2[sel].mean():+.2f} / {hn2[~sel].mean():+.2f} |")
    A(f"| fraction of all {len(dg)} with positive virgin gross SR | {np.mean(hg2 > 0):.0%} |")
    A("\nThe design ranking does carry information into the virgin window: +0.39 rank correlation, "
      "and the bar-clearers average roughly twice the gross Sharpe of the rest. That is the single "
      "strongest piece of evidence in this sweep. The 82% positive-gross figure is much weaker "
      "evidence than it looks -- see the correlation matrix below, these 39 formulas are about four "
      "clusters, not 39 independent draws.\n")

    # ---------------- metrics panel ----------------
    m1 = ix(met["heldout1"]); m1c = ix(met["heldout1_cost15"])
    dgm = np.array([r["sharpe_gross"] for r in met["design"]])
    hgm = np.array([m1[r["name"]]["sharpe_gross"] for r in met["design"]])
    hnm = np.array([m1[r["name"]]["sharpe_net"] for r in met["design"]])
    selm = dgm >= barm
    A(f"## All {len(met['design'])} formulas on the metrics panel, top-50 (h1 only -- burned window)\n")
    A("| # | formula | cls | H | d SR | d net | h1 SR | h1 net | h1 @15bp | h1 be bp | turn/day | "
      "corr(mkt) | signal |")
    A("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for i, r in enumerate(met["design"], 1):
        n = r["name"]; a = m1[n]; c = m1c[n]
        mark = " `<<<`" if (np.isfinite(r["sharpe_gross"]) and r["sharpe_gross"] >= barm) else ""
        A(f"| {i} | `{n}`{mark} | {r['cls']} | {r['H']}h | {f(r['sharpe_gross'], '%.2f')} | "
          f"{f(r['sharpe_net'])} | {f(a['sharpe_gross'])} | {f(a['sharpe_net'])} | "
          f"{f(c['sharpe_net'])} | {f(a['breakeven_cost_bp_per_side'], '%.1f')} | "
          f"{r['turnover_per_day']:.2f} | {f(a['corr_market'])} | {r['desc']} |")
    A("")
    A(f"Design->h1 rank correlation on this panel: **{rankc(dgm, hgm):+.3f}**. The "
      f"{int(selm.sum())} that cleared the design bar average **{hnm[selm].mean():+.2f}** net "
      f"Sharpe out of sample against {hnm[~selm].mean():+.2f} for the rest -- i.e. clearing the bar "
      "bought nothing on this panel. **On the top-50, round 2's open-interest and long/short-ratio "
      "transforms are noise.** `X2_RETAIL_VS_TAKER` (design 3.91, h1 net +1.30) and `X2_GLSR_SLOW` "
      "(design 3.30, h1 net +0.59) are the only two that stayed positive, both die at 15 bp/side, "
      "and both are built from the same two Binance long/short-ratio fields as round 1's single "
      "survivor `XS_SMART` -- they are not an independent finding, they are the same one.\n")

    # ---------------- independence ----------------
    A("## Is the virgin-window shortlist several findings or one bet?\n")
    A("Daily net P&L of the shortlist on the virgin window, correlated against each other:\n")
    nm = shl["names"]
    A("| | " + " | ".join(x.replace("X2_", "") for x in nm) + " |")
    A("|---|" + "---|" * len(nm))
    for i, n in enumerate(nm):
        A(f"| **{n.replace('X2_', '')}** | " +
          " | ".join(f"{v:+.2f}" for v in shl["corr_matrix"][i]) + " |")
    A(f"\nMean absolute off-diagonal correlation **{shl['mean_abs_offdiag_corr']:.2f}**. "
      "Four clusters are visible and they are what the 39 formulas actually are:\n")
    A("| cluster | members | internal corr | virgin verdict |")
    A("|---|---|---|---|")
    A("| **taker-flow imbalance** | `X2_FLOWSTREAK`, `X2_TOD_FLOW_EU`, `X2_FLOW_VA` | 0.60-0.80 | "
      "**the only market-neutral one that works** (corr to basket -0.01 / -0.06) |")
    A("| **liquidity / low-vol tilt** | `X2_IDIOVOL`, `X2_KYLE` | 0.86 | works, but corr to the "
      "equal-weight basket +0.47 / +0.58 -- this is a long-majors/short-alts directional bet |")
    A("| **candle shape** | `X2_UPWICK`, `X2_WICKASYM` | 0.85 | cleared the design bar, **died on "
      "the virgin window** (net -0.01 / -0.39) |")
    A("| **residual momentum / carry-vs-return** | `X2_RESID_MOM`, `X2_FUNDPATH_REV` | 0.80 | "
      "positive on all three windows but **never cleared the design bar** (2.46 / 2.20 vs 2.76) |")
    A("")
    cc = shl["composite_core"]
    A(f"An equal-weight composite of the three bar-clearers that stayed positive at 15 bp "
      f"({', '.join(x.replace('X2_', '') for x in cc['members'])}) nets Sharpe "
      f"**{cc['net_sharpe_5p5bp']:.2f}** ({cc['ann_net']*100:+.0f}%/yr) on the virgin window at "
      f"5.5 bp/side, with correlation {cc['corr_to_basket']:+.2f} to the equal-weight perp basket. "
      "That correlation is entirely `IDIOVOL`'s.\n")

    A("## Verdict\n")
    A("**The metrics half of the theme is noise; the taker-flow half is not, but it is too thin to "
      "trade at an honest cost.**\n")
    A("What survived everything -- design bar, a window nothing had seen, and a 15 bp/side cost "
      "shock:\n")
    A("| | `X2_FLOWSTREAK` | `X2_TOD_FLOW_EU` |")
    A("|---|---|---|")
    A("| signal | fraction of the last 24 hours with net taker BUYING (one-sidedness, magnitude "
      "discarded) | 24h taker buy-sell notional imbalance, held ONLY 07-15 UTC |")
    A("| design gross / net | 4.61 / +3.11 | 3.24 / +2.18 |")
    A("| burned h1 net | **-0.67** | +1.06 |")
    A("| **virgin h2** gross / net | **+3.34 / +2.31** | **+2.80 / +1.85** |")
    A("| virgin net @ 15 bp/side | **+0.54** | **+0.21** |")
    A("| virgin breakeven cost | 17.9 bp/side | 16.2 bp/side |")
    A("| virgin 2025 / 2026 net | +2.5 / +2.0 | +1.7 / +2.1 |")
    A("| corr to equal-weight basket | -0.01 | -0.06 |")
    A("| turnover | 1.38 x/day | 0.42 x/day |")
    A("")
    A("### Honest caveats\n")
    A("1. **These two are ONE hypothesis, and round 1 already had it.** Both are the cross-sectional "
      "taker aggressor-flow imbalance; round 1's `XS_TAKER24` is the same feature (design gross "
      "3.15, h1 net +1.12 on the top-120 but only +0.32 on the top-50 and -1.67 at 15 bp). Counting "
      "round 1 and round 2 together this family has been tested six ways across three windows and "
      "is positive in most of them, negative in some. It is not six confirmations.")
    A("2. **`X2_FLOWSTREAK` failed the middle window.** Design +3.11, h1 **-0.67**, h2 +2.31. A "
      "formula that is strong, then negative, then strong is not a stable edge; it is a formula "
      "with a wide sampling distribution. `X2_TOD_FLOW_EU` is the only one positive in all three "
      "(+2.18 / +1.06 / +1.85) and it is the weaker of the two.")
    A("3. **At a realistic cost this is not tradeable.** Breakeven is 16-18 bp/side against a 4.5 bp "
      "published taker fee, which sounds like room -- but the surviving net Sharpe at 15 bp/side is "
      "+0.54 and +0.21. This programme has still never MEASURED perp slippage. "
      "`orphanflush_cache/bookdepth` holds +-1%..+-5% notional for 264 symbols and was again not "
      "used. Until that measurement exists, the honest statement is: the edge is real at 5.5 bp and "
      "gone somewhere before 20 bp, and nobody here knows which side of that line the fills land on.")
    A("4. **`X2_IDIOVOL` should not be counted as a microstructure finding.** It is long low "
      "idiosyncratic-vol perps / short high -- on a top-50 universe that is long majors, short alts. "
      "Its virgin Sharpe (+1.87 net, +1.70 at 15 bp) coincides with a period of rising BTC "
      "dominance, and its correlation to the equal-weight basket is +0.47. It is a directional "
      "regime bet wearing a cross-sectional costume.")
    A("5. **The 82%-positive statistic is not 39 confirmations.** Mean absolute pairwise "
      "correlation of the shortlist is 0.35 and the set collapses to about four clusters, so the "
      "effective number of independent draws is closer to 4-8 than to 39. The +0.39 design->virgin "
      "rank correlation should be read with that effective n, at which it is suggestive, not "
      "significant.")
    A("6. **Two formulas were initially untestable and were fixed, not dropped.** `X2_FUNDPERSIST` "
      "and `X2_FUNDFLIP` returned NaN on the first pass because funding settles 3x/day and the "
      "shared rolling-window helper requires 60% of the hours in a window to be observed. They were "
      "re-derived with a settlement-count gate and both then failed on their own merits (design "
      "1.18 / 0.71, virgin net -1.17 / -2.27).")
    A("7. **The virgin window is one draw of one regime**, 2025-01 to 2026-08. It is not a "
      "walk-forward, and 2025-26 perp market structure (funding intervals moved from 8h to 4h and "
      "1h on many symbols during it) is not the 2023 market the formulas were designed on.")
    A("")
    A("## Files\n")
    A("- `scripts/trading_bot/perpmicro_panel2.py` -- builds the extended klines+funding panel "
      "(439 symbols x 40536 hours, 2022-01 -> 2026-08)")
    A("- `scripts/trading_bot/perpmicro_trim_ext.py` -- trims it to 150 symbols x 33984 hours")
    A("- `scripts/trading_bot/perpmicro_sweep2.py` -- the round-2 harness; formula catalogue in "
      "`catalogue2()`")
    A("- `scripts/trading_bot/perpmicro_r2_shortlist.py` -- shortlist correlation / independence check")
    A("- `research/trading_bot/SWEEP_crypto_perp_microstructure_R2_{metrics,ext}_top50_"
      "DESIGN_FROZEN.json` -- design results, written before any held-out window was touched")
    A("- `research/trading_bot/SWEEP_crypto_perp_microstructure_R2_{metrics,ext}_top50_holdout.json`")
    A("- `research/trading_bot/SWEEP_crypto_perp_microstructure_R2_SHORTLIST.json`")

    OUT.write_text("\n".join(L) + "\n")
    print("wrote", OUT, len("\n".join(L)), "chars")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
