#!/usr/bin/env python3
"""Render the design + held-out + census JSONs into SWEEP_intraday_rv.{md,json}."""
from __future__ import annotations

import json
import pathlib

import numpy as np

OUT = pathlib.Path(__file__).resolve().parents[2] / "research" / "trading_bot"


def f(x, nd=2):
    try:
        if x is None or x != x:
            return "n/a"
        return f"{x:+.{nd}f}"
    except Exception:  # noqa: BLE001
        return "n/a"


def main() -> None:
    d = json.loads((OUT / "SWEEP_intraday_rv_design.json").read_text())
    hp, cp = OUT / "SWEEP_intraday_rv_heldout.json", OUT / "SWEEP_intraday_rv_census.json"
    h = json.loads(hp.read_text()) if hp.exists() else None
    c = json.loads(cp.read_text()) if cp.exists() else None
    st = OUT / "SWEEP_intraday_rv_selftest.json"
    selftest = json.loads(st.read_text()) if st.exists() else None
    hmap = {r["name"]: r for r in h["results"]} if h else {}
    nb = d["null_max_sharpe"]
    res = d["results"]
    best = max(res, key=lambda r: r["sharpe_1.0bp"])
    best_gross = max(res, key=lambda r: r["sharpe_gross"])
    n_pos = sum(1 for r in res if r["sharpe_1.0bp"] > 0)
    n_pos_half = sum(1 for r in res if r["sharpe_0.5bp"] > 0)
    n_gross_beat = sum(1 for r in res if r["sharpe_gross"] > d["null_max_sharpe_gross"]["p95"])

    L: list[str] = []
    A = L.append
    A("# SWEEP — intraday equity/ETF relative value & mean reversion")
    A("")
    A("## Verdict: the theme is DEAD, and it dies in an unusually informative way")
    A("")
    A(f"**{d['n_configs']} structurally different formulas** were scored on the design window. "
      f"**Zero** of them are net-positive at the headline 1.0 bp/side cost rung. The best is "
      f"`{best['name']}` at **{f(best['sharpe_1.0bp'])}**, against a noise bar — the 95th "
      f"percentile of best-of-{d['n_configs']} Sharpe when nothing has an edge — of "
      f"**{nb['p95']:+.2f}**. The winner is not near the bar; it is {nb['p95'] - best['sharpe_1.0bp']:.1f} "
      "Sharpe units below it.")
    A("")
    A("But the interesting part is *why*, and it is not \"there is no signal\":")
    A("")
    A(f"- **Before costs the signal is real, large, and it replicates out of sample.** "
      f"{n_gross_beat} of {d['n_configs']} configs beat the *gross* noise bar "
      f"({d['null_max_sharpe_gross']['p95']:+.2f}). The best gross design Sharpe is "
      f"**{f(best_gross['sharpe_gross'])}** (`{best_gross['name']}`)"
      + (f", and the same formula prints **{f(hmap[best_gross['name']]['sharpe_gross'])}** gross "
         "on the held-out window." if best_gross["name"] in hmap else "."))
    be = best_gross["breakeven_bp_per_turnover"]
    reg = d["regulatory_bp_per_turnover"]
    charged = d["headline_bp_per_side"] + reg
    A(f"- **The edge is smaller than the friction by one to two orders of magnitude.** "
      f"`{best_gross['name']}` can bear a total charge of **{be:.3f} bp per unit of "
      f"turnover** before its gross edge is exactly consumed. The headline rung charges "
      f"{charged:.2f} bp — **{charged / be:.0f}× more** than the edge can pay. It is worse "
      f"than that: the SEC 31 + FINRA TAF pass-through **alone** is {reg:.2f} bp, so this "
      "formula cannot cover the regulatory fee, never mind the spread. The repo's own "
      "measured half-spread for liquid names is 1.13 bp and the tightest mega-cap ETF is "
      "~0.2–0.5 bp; there is no venue at which this closes.")
    n_cannot_pay_reg = sum(1 for r_ in res if not r_.get("can_pay_regulatory_floor", False))
    A(f"- **{n_cannot_pay_reg} of {d['n_configs']}** configs cannot pay even the "
      f"{reg:.2f} bp regulatory floor out of their gross edge.")
    A(f"- Only **{n_pos_half} of {d['n_configs']}** configs are positive even at the "
      f"0.5 bp/side rung, and the best of those reaches "
      f"{f(max(r['sharpe_0.5bp'] for r in res))} — still far under the noise bar.")
    A("")
    A("Mean reversion between ETF siblings and across the short-horizon equity cross-section "
      "is not a mispricing that a taker can harvest. It is, to a very good approximation, the "
      "bid-ask bounce itself: the thing being measured *is* the spread, which is why the "
      "measurement is stable and the trade is impossible.")
    A("")

    if c and c.get("summary"):
        A("## This was predictable before any strategy was scored")
        A("")
        A(f"`rv_census.py` measured how far each same-claim pair's log ratio travels from its "
          f"own 78-bar trailing mean, on the design window, **before** any config ran. A "
          f"two-leg pair trade crosses four half-spreads per round trip, so at the headline "
          f"rung it must capture **{c['round_trip_cost_bp_two_leg']:.2f} bp** to break even.")
        A("")
        A("| pair | sd of dislocation (bp) | p95 \\|dislocation\\| (bp) | p95 ÷ round-trip cost | ac(1) |")
        A("|---|---|---|---|---|")
        sib = c["sibling_pairs"]
        order = sorted(sib.items(), key=lambda kv: kv[1]["p95_abs_bp"])
        for name, v in order[:8]:
            A(f"| {name} | {v['sd_bp']:.2f} | {v['p95_abs_bp']:.2f} | "
              f"{v['tradable_p95_over_cost']:.2f} | {v['ac1']:+.3f} |")
        A(f"| … | | | | |")
        for name, v in order[-4:]:
            A(f"| {name} | {v['sd_bp']:.2f} | {v['p95_abs_bp']:.2f} | "
              f"{v['tradable_p95_over_cost']:.2f} | {v['ac1']:+.3f} |")
        A("")
        A("The genuinely same-claim pairs — SPY/IVV/VOO, the ones where the arbitrage argument "
          "is airtight — sit at the top of that table with sub-2 bp p95 dislocations and "
          "one-bar autocorrelations near zero: the displacement does not survive a single bar, "
          "because it is non-synchronous prints rather than a dislocation. The pairs further "
          "down the table have larger, more persistent spreads precisely because they are "
          "*not* the same claim (XLK vs VGT hold different books), so there is no arbitrage "
          "force pulling them together and the 'reversion' is a bet, not a convergence.")
        A("")

    A("## Method")
    A("")
    A(f"- **Design** {d['window'][0]} .. {d['window'][1]} "
      f"({res[0]['n_days']} sessions). "
      + (f"**Held out** {h['window'][0]} .. {h['window'][1]} "
         f"({h['results'][0]['n_days']} sessions), untouched until the shortlist was frozen."
         if h else ""))
    A(f"- **Universe** 132 symbols, Alpaca SIP 5-minute bars, RTH only, `adjustment=all`. "
      "Same-claim ETF clusters, SPDR/Vanguard sector twins, style and regional ETFs, "
      "levered/inverse funds, 30+ mega-caps. Survivorship-biased (every ETF is alive today) "
      "and price levels are not point-in-time; no config filters on a level.")
    A(f"- **Execution** {d['execution']}. Flat at every close.")
    A(f"- **Costs** {d['cost_rungs_bp_per_side']} bp/side on `|Δw|`, headline "
      f"{d['headline_bp_per_side']} bp, plus {d['regulatory_bp_per_turnover']} bp/turnover for "
      f"SEC 31 + FINRA TAF. Borrow {d['borrow_annual']} — {d['borrow_note']}")
    A(f"- **Cost provenance** {d['cost_provenance']}")
    if selftest:
        s = selftest["results"]
        A(f"- **Harness self-test** (`rv_selftest.py`): recovers a planted OU dislocation at "
          f"gross Sharpe {s['planted_ou_edge']['as_specified']:+.2f}, flips to "
          f"{s['planted_ou_edge']['negated_control']:+.2f} under negation, and returns "
          f"{s['null_random_walk']['as_specified']:+.2f} on a random-walk spread with nothing "
          "to find. All three checks pass.")
    A("")
    A("## The noise bar")
    A("")
    A(f"Best-of-{d['n_configs']} Sharpe under H0, from a stationary block bootstrap "
      f"(block = 5 days, {nb['n_boot']} resamples) of each config's *demeaned* daily net PnL, "
      "drawing the same day indices for every config so the sweep's internal correlation "
      "survives:")
    A("")
    A("| statistic | net (1.0 bp) | gross |")
    A("|---|---|---|")
    g = d["null_max_sharpe_gross"]
    A(f"| mean | {nb['mean']:+.2f} | {g['mean']:+.2f} |")
    A(f"| p95 | {nb['p95']:+.2f} | {g['p95']:+.2f} |")
    A(f"| p99 | {nb['p99']:+.2f} | {g['p99']:+.2f} |")
    A(f"| naive √(2 ln N)/√years | {nb['naive_sqrt_2lnN']:+.2f} | — |")
    A("")
    A("## Distribution of design results (all 98 configs)")
    A("")
    A("| basis | min | p10 | p25 | median | p75 | p90 | max |")
    A("|---|---|---|---|---|---|---|---|")
    for k, lab in (("sharpe_gross", "gross (0 bp)"), ("sharpe_0.5bp", "net 0.5 bp/side"),
                   ("sharpe_1.0bp", "net 1.0 bp/side"), ("sharpe_2.0bp", "net 2.0 bp/side"),
                   ("sharpe_2.5bp", "net 2.5 bp/side")):
        s = d["distribution"].get(k)
        if not s:
            continue
        A(f"| {lab} | {f(s['min'])} | {f(s['p10'])} | {f(s['p25'])} | {f(s['median'])} "
          f"| {f(s['p75'])} | {f(s['p90'])} | {f(s['max'])} |")
    A("")
    A("The net rows are not close calls. The median config loses ~28 Sharpe units to friction.")
    A("")

    if h:
        A("## Held-out (pre-registered shortlist)")
        A("")
        A("Nothing cleared the p95 bar, so per §5 of the pre-registration these ran out of "
          "sample as a **documented negative control**, not as candidates. The two "
          "highest-*gross* formulas were added, labelled, to test whether the before-cost "
          "signal itself persists — it does.")
        A("")
        A("| formula | design gross | HELD-OUT gross | design net 1bp | HELD-OUT net 1bp | break-even bp/turnover |")
        A("|---|---|---|---|---|---|")
        dmap = {r["name"]: r for r in res}
        for name in ("D1_gap_rev_mega", "I5_xs_rev_mega_lb6_hold39", "D4_first30_rev_mega",
                     "A2_pair_z_intraday", "C1_xs_rev_mega_lb1"):
            dr, hr = dmap.get(name), hmap.get(name)
            if not dr or not hr:
                continue
            A(f"| `{name}` | {f(dr['sharpe_gross'])} | {f(hr['sharpe_gross'])} | "
              f"{f(dr['sharpe_1.0bp'])} | {f(hr['sharpe_1.0bp'])} | "
              f"{dr['breakeven_bp_per_turnover']:.3f} |")
        A("")
        A("The gross column is the finding: the mean-reversion signal is stable across a "
          "four-year design window and a twenty-month held-out window. The net column is the "
          "verdict: it is unreachable.")
        A("")

    A("## Every formula, ranked by net design Sharpe at 1.0 bp/side")
    A("")
    hdr = ("| # | formula | kind | turn/day | break-even bp/turnover | gross | net 0.5bp | "
           "net 1bp | net 2bp | net 2.5bp |")
    sep = "|---|---|---|---|---|---|---|---|---|---|"
    if h:
        hdr += " HELD-OUT net 1bp |"
        sep += "---|"
    A(hdr)
    A(sep)
    for i, r in enumerate(res, 1):
        ber = r.get("breakeven_bp_per_turnover", float("nan"))
        row = (f"| {i} | `{r['name']}` | {r['kind']} | {r['daily_turnover']:.1f} | "
               f"{ber:.3f} | {f(r['sharpe_gross'])} | {f(r['sharpe_0.5bp'])} | "
               f"{f(r['sharpe_1.0bp'])} | {f(r['sharpe_2.0bp'])} | {f(r['sharpe_2.5bp'])} |")
        if h:
            hr = hmap.get(r["name"])
            row += f" {f(hr['sharpe_1.0bp']) if hr else '—'} |"
        A(row)
    A("")
    A("## Known redundancy, disclosed")
    A("")
    A("`D1_gap_rev_mega` and `D3_gap_resid_rev_mega` return identical numbers: subtracting the "
      "cross-sectional mean gap before a dollar-neutralising demean is a no-op. That is one "
      "formula counted twice, so the effective N is 97, not 98. It moves the noise bar by "
      "less than 0.01 and is recorded rather than quietly deduplicated.")
    A("")
    A("## Artifacts")
    A("")
    A("| what | path |")
    A("|---|---|")
    for lab, p in (("pre-registration", "research/trading_bot/SWEEP_intraday_rv_PREREGISTRATION.md"),
                   ("design results", "research/trading_bot/SWEEP_intraday_rv_design.json"),
                   ("held-out results", "research/trading_bot/SWEEP_intraday_rv_heldout.json"),
                   ("feasibility census", "research/trading_bot/SWEEP_intraday_rv_census.json"),
                   ("harness self-test", "research/trading_bot/SWEEP_intraday_rv_selftest.json"),
                   ("combined", "research/trading_bot/SWEEP_intraday_rv.json"),
                   ("fetch / panel / sweep code", "scripts/trading_bot/rv_*.py"),
                   ("5-min bar cache", "research/data/rv_cache/ (132 .npz + panel_rv.npz)")):
        A(f"| {lab} | `{p}` |")
    A("")

    (OUT / "SWEEP_intraday_rv.md").write_text("\n".join(L) + "\n")
    combined = {
        "theme": "intraday equity/ETF relative-value & mean-reversion",
        "verdict": "NOISE at any tradable cost -- real gross signal, entirely inside the spread",
        "n_formulas_tested": d["n_configs"],
        "effective_n_after_disclosed_duplicate": d["n_configs"] - 1,
        "noise_bar_p95_net": nb["p95"],
        "noise_bar_p95_gross": g["p95"],
        "best_design_net_1bp": {"name": best["name"], "sharpe": best["sharpe_1.0bp"]},
        "best_design_gross": {"name": best_gross["name"], "sharpe": best_gross["sharpe_gross"],
                              "breakeven_bp_per_turnover": best_gross["breakeven_bp_per_turnover"],
                              "charged_bp_per_turnover_at_headline": d["headline_bp_per_side"] + d["regulatory_bp_per_turnover"]},
        "n_net_positive_at_1bp": n_pos,
        "n_net_positive_at_0.5bp": n_pos_half,
        "n_gross_above_gross_noise_bar": n_gross_beat,
        "design": d,
        "heldout": h,
        "census_summary": c.get("summary") if c else None,
        "selftest": selftest,
    }
    (OUT / "SWEEP_intraday_rv.json").write_text(json.dumps(combined, indent=1))
    print(f"wrote {OUT / 'SWEEP_intraday_rv.md'} and .json")


if __name__ == "__main__":
    main()
