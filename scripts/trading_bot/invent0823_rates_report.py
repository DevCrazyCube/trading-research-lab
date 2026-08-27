#!/usr/bin/env python3
"""Render the INVENT_0823 rates sweep: gate ledger, design table, held-out table."""
import json
import pathlib
import sys

OUT = pathlib.Path(__file__).resolve().parents[2] / "research" / "trading_bot"


def load(stage):
    p = OUT / f"INVENT_0823_rates_{stage}.json"
    return json.loads(p.read_text()) if p.exists() else None


def gate_for(row, gates):
    """The rho1 bounce gate that applies to this formula's family."""
    fam = row["family"]
    vals = {k: v for k, v in gates.items() if k.startswith(fam + ":")}
    if not vals:
        return None, None
    worst = min(vals.values())
    return worst, ("BOUNCE" if worst < -0.35 else "pass")


def table(d, held=None):
    gates = d["rho1_delta_spread_design"]
    hd = {r["name"]: r for r in held["rows"]} if held else {}
    hdr = (f"| {'formula':34s} | {'family':12s} | rho1 | gate | gross SR | gross t | "
           f"net SR | net t | be_hs | tov | lag2 t |")
    if held:
        hdr += " HO gross t | HO net SR |"
    print(hdr)
    for r in sorted(d["rows"], key=lambda x: -(x["lag1"]["gross_t"] if x["lag1"] else 0)):
        g = r["lag1"]
        if not g:
            print(f"| {r['name']:34s} | insufficient data |")
            continue
        rho, fl = gate_for(r, gates)
        rs = f"{rho:+.2f}" if rho is not None else "  n/a"
        line = (f"| {r['name']:34s} | {r['family']:12s} | {rs} | {str(fl):6s} | "
                f"{g['gross_sharpe']:+8.2f} | {g['gross_t']:+7.2f} | {g['net_sharpe']:+6.2f} | "
                f"{g['net_t']:+6.2f} | {g['breakeven_hs_bp']:5.2f} | {g['turnover']:5.3f} | "
                f"{r['lag2']['gross_t']:+6.2f} |")
        if held:
            h = hd.get(r["name"], {}).get("lag1")
            line += (f" {h['gross_t']:+10.2f} | {h['net_sharpe']:+9.2f} |" if h
                     else "        n/a |       n/a |")
        print(line)


def main():
    d = load("design")
    h = load("holdout")
    pl = d["placebo_size_matched"]
    bar = max(d["analytic_bar_2sided_sqrt2ln2N"], pl["p95"])
    print(f"N = {d['n_formulas']}   window {d['window']}")
    print(f"analytic bar sqrt(2 ln N)   = {d['analytic_bar_1sided_sqrt2lnN']:.3f}")
    print(f"analytic bar sqrt(2 ln 2N)  = {d['analytic_bar_2sided_sqrt2ln2N']:.3f}")
    print(f"size-matched placebo ({pl['draws']} draws): mean max|t| {pl['mean']:.3f}  "
          f"p50 {pl['p50']:.3f}  p95 {pl['p95']:.3f}  max {pl['max']:.3f}")
    print(f"BAR USED (larger of the two)  = {bar:.3f}")
    print(f"placebo/analytic ratio        = {pl['p95'] / d['analytic_bar_2sided_sqrt2ln2N']:.2f}x")
    print()
    table(d, h)
    print()
    print("rho1(Delta spread) on the DESIGN window, per book:")
    for k, v in d["rho1_delta_spread_design"].items():
        print(f"   {k:34s} {v:+.3f}  {'BOUNCE' if v < -0.35 else ''}")
    print()
    survivors = [r for r in d["rows"] if r["lag1"] and r["lag1"]["gross_t"] > bar]
    print(f"Formulas clearing the gross bar ({bar:.2f}): {len(survivors)}")
    for r in survivors:
        rho, fl = gate_for(r, d["rho1_delta_spread_design"])
        print(f"   {r['name']:34s} gross t {r['lag1']['gross_t']:+.2f}  gate {fl}  "
              f"net t {r['lag1']['net_t']:+.2f}  be_hs {r['lag1']['breakeven_hs_bp']:.2f}bp")


if __name__ == "__main__":
    sys.exit(main())
