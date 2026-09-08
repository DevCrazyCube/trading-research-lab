#!/usr/bin/env python3
"""Design -> held-out bridge.  Selection is made on the DESIGN file only; the held-out
number reported is that same formula's number, never the held-out maximum."""
import json, math, pathlib, sys

C = pathlib.Path("/home/anont/meme/research/data/holdco_cache")
D = json.load(open(C / "sweep_design_etb.json"))
H = json.load(open(C / "sweep_holdout_etb.json"))
DH = json.load(open(C / "sweep_design_htb.json"))
HH = json.load(open(C / "sweep_holdout_htb.json"))
N = D["n_formulas"]
BAR = math.sqrt(2 * math.log(N))

print(f"N formulas evaluated on the design window = {N}")
print(f"expected-max |t| under the null           = {BAR:.2f} SE\n")

out = {"n_formulas": N, "noise_bar_SE": round(BAR, 3), "groups": {}}
allrows = []
for g in ("P", "H", "S", "M"):
    fs = D["groups"][g]["formulas"]
    ranked = sorted(((v["agg"].get("t", -9) if v["agg"].get("n", 0) > 5 else -9, k)
                     for k, v in fs.items()), reverse=True)
    best_t, best = ranked[0]
    ds = fs[best]["agg"]
    hs = H["groups"][g]["formulas"].get(best, {}).get("agg", {"n": 0})
    dsh = DH["groups"][g]["formulas"].get(best, {}).get("agg", {"n": 0})
    hsh = HH["groups"][g]["formulas"].get(best, {}).get("agg", {"n": 0})
    print(f"=== group {g}   design-selected formula: {best}")
    print(f"    DESIGN  n={ds['n']:>4} gross={ds['gross_bp']:>8.1f} cost={ds['cost_bp']:>6.1f} "
          f"net={ds['net_bp']:>8.1f}bp  t={ds['t']:>5.2f}  SR={ds['sharpe']:>5.2f}  "
          f"hit={ds['hit']}  hold={ds['mean_hold']}")
    if hs.get("n", 0):
        print(f"    HELDOUT n={hs['n']:>4} gross={hs['gross_bp']:>8.1f} cost={hs['cost_bp']:>6.1f} "
              f"net={hs['net_bp']:>8.1f}bp  t={hs['t']:>5.2f}  SR={hs['sharpe']:>5.2f}  "
              f"hit={hs['hit']}  hold={hs['mean_hold']}")
    else:
        print("    HELDOUT no trades")
    print(f"    borrow@HTB(10.28%/yr): design net={dsh.get('net_bp')}bp t={dsh.get('t')} | "
          f"heldout net={hsh.get('net_bp')}bp t={hsh.get('t')}")
    print(f"    clears noise bar on design? {'YES' if ds['t'] > BAR else 'NO'} "
          f"({ds['t']:.2f} vs {BAR:.2f})")
    # top-5 per-pair contribution and leave-one-out on the design window
    pp = fs[best]["per_pair"]
    tot = sum(v["n"] * v["net_bp"] for v in pp.values())
    contrib = sorted(((v["n"] * v["net_bp"] / tot if tot else 0, k, v["n"], v["net_bp"])
                      for k, v in pp.items()), reverse=True)
    print("    design P&L share by pair: " + ", ".join(
        f"{k} {s:+.0%}(n={n})" for s, k, n, _ in contrib[:4]))
    out["groups"][g] = {"formula": best,
                        "design": ds, "heldout": hs,
                        "design_htb": dsh, "heldout_htb": hsh,
                        "pnl_share_top": [[k, round(s, 3), n] for s, k, n, _ in contrib[:5]]}
    allrows.append((ds["t"], g, best, ds, hs))
    print()

bt, bg, bn, bds, bhs = max(allrows)
print(f"### family-best on design: group {bg} / {bn}  t={bt:.2f}  (bar {BAR:.2f})")
print(f"### its held-out number: "
      + (f"net={bhs['net_bp']}bp t={bhs['t']} SR={bhs['sharpe']} n={bhs['n']}"
         if bhs.get("n") else "no trades"))
out["family_best"] = {"group": bg, "formula": bn, "design": bds, "heldout": bhs}
(C / "bridge.json").write_text(json.dumps(out, indent=1))
print("\nwrote", C / "bridge.json")
