#!/usr/bin/env python3
"""Render SWEEP_calendar_session.{json,holdout.json} into the markdown record."""
from __future__ import annotations

import json
import pathlib

OUT = pathlib.Path(__file__).resolve().parents[2] / "research" / "trading_bot"


def main():
    d = json.loads((OUT / "SWEEP_calendar_session.json").read_text())
    hp = OUT / "SWEEP_calendar_session_holdout.json"
    hold = json.loads(hp.read_text()) if hp.exists() else []
    nl = d["null"]
    bar = nl["max_abs_z_p95"]
    rows = d["results"]

    L = []
    a = L.append
    a("# SWEEP: calendar / session / structural-flow effects\n")
    a(f"Generated {d['generated']}. **{d['n_formulas']} structurally distinct formulas**, "
      "each scored on a design window only.\n")
    a("## Verdict\n")
    survivors = [r for r in rows if abs(r["z_vs_own_null"]) > bar]
    if not survivors:
        a("**The theme is noise.** Not one of the "
          f"{d['n_formulas']} formulas clears the family-wide multiple-testing bar.\n")
    else:
        a(f"{len(survivors)} of {d['n_formulas']} formulas clear the family bar on the design "
          "window. Their held-out numbers are below and are the only numbers that matter.\n")

    a("## Windows\n")
    a("| dataset | design | holdout |")
    a("|---|---|---|")
    for k in d["design_windows"]:
        a(f"| {k} | {d['design_windows'][k]} | {d['holdout_windows'][k]} |")
    a("")
    a("## Costs charged (per side, on |dw|)\n")
    for k, v in d["costs_bp_per_side"].items():
        a(f"- {k}: {v} bp")
    a("")

    a("## The multiple-testing bar\n")
    a(f"- formulas tried: **{d['n_formulas']}**")
    a(f"- analytic sqrt(2 ln N) for N independent tries: **{nl['analytic_sqrt_2lnN']}** "
      "SE units (upper bound -- these formulas are correlated)")
    a(f"- empirical null: {nl['replicates']} replicates, {nl['method']}")
    a(f"- **expected max |z| under the null: {nl['expected_max_abs_z']}** "
      f"(p90 {nl['max_abs_z_p90']}, p95 {nl['max_abs_z_p95']})")
    a(f"- **observed max |z| on the design window: {d['design_max_abs_z']}**")
    a("")
    a("`z` is the design Sharpe minus that same formula's own rotated-null mean, over the "
      "null sd. Studentising is not cosmetic: a formula that trades three times a day pays "
      "a deterministic cost drift that survives rotation, so raw Sharpe would rank the "
      "family by turnover rather than by luck.\n")

    a("## Full design distribution (all formulas, ranked by |z|)\n")
    a("| z | design Sharpe | null mean | p (2-sided) | dataset | formula | description |")
    a("|---:|---:|---:|---:|---|---|---|")
    for r in rows:
        a(f"| {r['z_vs_own_null']:+.2f} | {r['design_sharpe']:+.3f} | "
          f"{r['null_mean_sharpe']:+.3f} | {r['p_two_sided']:.4f} | {r['dataset']} | "
          f"`{r['name']}` | {r['desc']} |")
    a("")

    if hold:
        a("## Held-out results for the design leaders\n")
        a("| formula | design Sharpe | HELD-OUT Sharpe | held-out ann ret | held-out vol | maxDD |")
        a("|---|---:|---:|---:|---:|---:|")
        for h in hold:
            a(f"| `{h['name']}` | {h['design']['sharpe']:+.3f} | "
              f"**{h['holdout']['sharpe']:+.3f}** | {h['holdout']['ann_return_pct']:+.2f}% | "
              f"{h['holdout']['ann_vol_pct']:.2f}% | {h['holdout']['max_drawdown_pct']:.2f}% |")
        a("")
    (OUT / "SWEEP_calendar_session.md").write_text("\n".join(L))
    print("wrote", OUT / "SWEEP_calendar_session.md")


if __name__ == "__main__":
    main()
