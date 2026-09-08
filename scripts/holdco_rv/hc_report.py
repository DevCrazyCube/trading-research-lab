#!/usr/bin/env python3
"""Report the full result distribution of a holdco RV sweep."""
import json, math, sys, argparse

ap = argparse.ArgumentParser()
ap.add_argument("path")
ap.add_argument("--top", type=int, default=12)
ap.add_argument("--all", action="store_true")
a = ap.parse_args()
R = json.load(open(a.path))
N = R["n_formulas"]
bar = math.sqrt(2 * math.log(N))
print(f"window={R['window']} {R['span']} borrow={R['borrow']} hs_mult={R['hs_mult']}")
print(f"N formulas = {N}   expected-max |t| under the null = sqrt(2 ln N) = {bar:.2f}")
rows = []
for g, gd in R["groups"].items():
    print(f"\n=== group {g}  pairs/deals used = {len(gd['pairs'])}")
    print("   ", ", ".join(gd["pairs"]))
    for name, v in gd["formulas"].items():
        s = v["agg"]
        if s.get("n", 0) == 0:
            rows.append((g, name, 0, 0, 0, 0, 0))
            continue
        rows.append((g, name, s["n"], s["net_bp"], s["t"], s["sharpe"], s["gross_bp"]))
ts = [r[4] for r in rows if r[2] > 0]
print(f"\n--- distribution of t-stats across all {len(rows)} formulas "
      f"({len(ts)} with trades)")
if ts:
    ts_s = sorted(ts)
    q = lambda p: ts_s[min(len(ts_s) - 1, int(p * len(ts_s)))]
    print(f"  min {ts_s[0]:.2f}  p10 {q(.10):.2f}  p25 {q(.25):.2f}  med {q(.50):.2f} "
          f" p75 {q(.75):.2f}  p90 {q(.90):.2f}  max {ts_s[-1]:.2f}")
    print(f"  n with t>0: {sum(1 for x in ts if x > 0)}   t>2: {sum(1 for x in ts if x > 2)}"
          f"   t>{bar:.2f}: {sum(1 for x in ts if x > bar)}")
print(f"\n--- top {a.top} by t-stat")
hdr = f"{'grp':>3} {'formula':<42} {'n':>5} {'gross':>8} {'net_bp':>8} {'t':>6} {'SR':>6}"
print(hdr)
for r in sorted(rows, key=lambda x: -x[4])[:a.top]:
    print(f"{r[0]:>3} {r[1]:<42} {r[2]:>5} {r[6]:>8.1f} {r[3]:>8.1f} {r[4]:>6.2f} {r[5]:>6.2f}")
print(f"\n--- worst 5 by t-stat")
for r in sorted(rows, key=lambda x: x[4])[:5]:
    print(f"{r[0]:>3} {r[1]:<42} {r[2]:>5} {r[6]:>8.1f} {r[3]:>8.1f} {r[4]:>6.2f} {r[5]:>6.2f}")
if a.all:
    print("\n--- all")
    for r in sorted(rows, key=lambda x: (x[0], -x[4])):
        print(f"{r[0]:>3} {r[1]:<42} {r[2]:>5} {r[6]:>8.1f} {r[3]:>8.1f} {r[4]:>6.2f} {r[5]:>6.2f}")
print("\n--- hygiene", json.dumps(R.get("hygiene", {}))[:600])
