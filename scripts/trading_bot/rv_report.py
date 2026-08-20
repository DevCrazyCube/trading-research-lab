#!/usr/bin/env python3
"""Render SWEEP_intraday_rv_{design,heldout}.json into SWEEP_intraday_rv.md."""
from __future__ import annotations

import json
import pathlib

OUT = pathlib.Path(__file__).resolve().parents[2] / "research" / "trading_bot"


def fmt(x, nd=2):
    try:
        if x is None or x != x:
            return "n/a"
        return f"{x:+.{nd}f}"
    except Exception:  # noqa: BLE001
        return "n/a"


def main() -> None:
    d = json.loads((OUT / "SWEEP_intraday_rv_design.json").read_text())
    hp = OUT / "SWEEP_intraday_rv_heldout.json"
    h = json.loads(hp.read_text()) if hp.exists() else None
    hmap = {r["name"]: r for r in h["results"]} if h else {}

    nb = d["null_max_sharpe"]
    lines = []
    L = lines.append
    L("# SWEEP — intraday equity/ETF relative value & mean reversion")
    L("")
    L(f"- **Design window** {d['window'][0]} .. {d['window'][1]} "
      f"(held out: {h['window'][0]} .. {h['window'][1]})" if h else
      f"- **Design window** {d['window'][0]} .. {d['window'][1]}")
    L(f"- **Formulas tested on design:** {d['n_configs']}")
    L(f"- **Execution:** {d['execution']}")
    L(f"- **Costs:** {d['cost_rungs_bp_per_side']} bp per side; headline "
      f"{d['headline_bp_per_side']} bp. Provenance: {d['cost_provenance']}")
    L("")
    L("## The noise bar")
    L("")
    L(f"Best-of-{d['n_configs']} Sharpe when **nothing has an edge**, from a stationary block "
      f"bootstrap of the demeaned daily PnL (block = 5 days, {nb['n_boot']} resamples, the same "
      "day indices drawn for every config so the sweep's internal correlation is preserved):")
    L("")
    L("| statistic of max-Sharpe under H0 | value |")
    L("|---|---|")
    for k in ("mean", "p50", "p90", "p95", "p99"):
        L(f"| {k} | {nb[k]:+.2f} |")
    L(f"| naive sqrt(2 ln N) / sqrt(years) | {nb['naive_sqrt_2lnN']:+.2f} |")
    L("")
    if "null_max_sharpe_gross" in d:
        g = d["null_max_sharpe_gross"]
        L(f"Before costs the same bar is mean {g['mean']:+.2f}, p95 {g['p95']:+.2f}.")
        L("")
    L("**A design result is only interesting if it clears the p95 line.**")
    L("")
    L("## Distribution of design results (all configs)")
    L("")
    L("| basis | min | p10 | p25 | median | p75 | p90 | max |")
    L("|---|---|---|---|---|---|---|---|")
    for k, lab in (("sharpe_gross", "gross (0 bp)"), ("sharpe_0.5bp", "net 0.5 bp/side"),
                   ("sharpe_1.0bp", "net 1.0 bp/side"), ("sharpe_2.0bp", "net 2.0 bp/side"),
                   ("sharpe_2.5bp", "net 2.5 bp/side (repo retail-taker default)")):
        s = d["distribution"].get(k)
        if not s:
            continue
        L(f"| {lab} | {fmt(s['min'])} | {fmt(s['p10'])} | {fmt(s['p25'])} | {fmt(s['median'])} "
          f"| {fmt(s['p75'])} | {fmt(s['p90'])} | {fmt(s['max'])} |")
    L("")
    L("## Every formula, ranked by net design Sharpe at 1.0 bp/side")
    L("")
    hdr = "| # | formula | kind | turn/day | gross | net 0.5bp | net 1bp | net 2bp | net 2.5bp |"
    if h:
        hdr += " HELD-OUT net 1bp |"
    L(hdr)
    L("|---|---|---|---|---|---|---|---|---|" + ("---|" if h else ""))
    for i, r in enumerate(d["results"], 1):
        row = (f"| {i} | `{r['name']}` | {r['kind']} | {r['daily_turnover']:.1f} | "
               f"{fmt(r['sharpe_gross'])} | {fmt(r['sharpe_0.5bp'])} | {fmt(r['sharpe_1.0bp'])} | "
               f"{fmt(r['sharpe_2.0bp'])} | {fmt(r['sharpe_2.5bp'])} |")
        if h:
            hr = hmap.get(r["name"])
            row += f" {fmt(hr['sharpe_1.0bp']) if hr else '—'} |"
        L(row)
    L("")
    (OUT / "SWEEP_intraday_rv.md").write_text("\n".join(lines) + "\n")
    print(f"wrote {OUT / 'SWEEP_intraday_rv.md'}")


if __name__ == "__main__":
    main()
