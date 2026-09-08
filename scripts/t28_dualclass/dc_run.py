#!/usr/bin/env python3
import json, math, statistics as st, sys, pathlib
sys.path.insert(0, "/home/anont/meme/scripts/t28_dualclass")
import dc_test as m

Q = json.load(open("/home/anont/meme/research/data/t28_dualclass_cache/quotes.json"))


def spread_map(window, min_obs=3):
    lo, hi = window
    out = {}
    for sym in {s for d in Q for s in Q[d]}:
        vals = [Q[d][sym] for d in Q if lo <= d <= hi and sym in Q[d]]
        if len(vals) >= min_obs:
            out[sym] = st.median(vals) * 1e-4      # full spread as a fraction
    return out


def design_adv(sym, lo, hi):
    v = [x["c"] * x["v"] for x in m.RAW.get(sym, []) if lo <= x["t"][:10] <= hi]
    return st.median(v) if v else 0.0


def run(window, label, pairs=None, hs_mult=1.0, borrow=m.BORROW_ANNUAL,
        L=250, K=2.0, EXIT=0.5, MAXHOLD=20, min_dv=1e6):
    sp = spread_map(window)
    pairs = pairs or m.PAIRS
    allt, per = [], {}
    for p in pairs:
        a, b = p
        if a not in sp or b not in sp:
            continue
        t = m.run_pair(p, window[0], window[1], L, K, EXIT, MAXHOLD, min_dv, 2.0,
                       sp[a] / 2 * hs_mult, sp[b] / 2 * hs_mult, borrow)
        if t:
            per[f"{a}/{b}"] = m.stats(t, "", 1)
            allt.extend(t)
    days = sorted({d["d"] for p in pairs for d in m.build(p, window[0], window[1])})
    s = m.stats(allt, label, len(days) or 1)
    s["p_boot_mean_le_0"] = m.bootstrap_p(allt)
    s["pairs_traded"] = len(per)
    s["pairs_positive"] = sum(1 for v in per.values() if v["net_bp"] > 0)
    return s, per, allt


def show(s):
    print(json.dumps(s, indent=None))


if __name__ == "__main__":
    D, H = m.DESIGN, m.HELDOUT
    liquid = [p for p in m.PAIRS
              if min(design_adv(p[0], *D), design_adv(p[1], *D)) >= 3e6]
    print("design-selected liquid pairs:", [f"{a}/{b}" for a, b in liquid])
    print()
    for name, win in (("DESIGN", D), ("HELDOUT", H)):
        s, per, _ = run(win, f"{name} all-pairs NET")
        show(s)
        s2, per2, _ = run(win, f"{name} liquid-subset NET", pairs=liquid)
        show(s2)
    print()
    print("--- held-out cost sensitivity, liquid subset ---")
    for mult in (1.0, 1.5, 2.0, 3.0):
        s, _, _ = run(H, f"heldout liquid hs x{mult}", pairs=liquid, hs_mult=mult)
        show(s)
    s, _, _ = run(H, "heldout liquid HTB borrow 10.28%/yr", pairs=liquid,
                  borrow=m.BORROW_HTB)
    show(s)
    print()
    print("--- held-out per-pair, liquid subset ---")
    s, per, _ = run(H, "x", pairs=liquid)
    for k, v in sorted(per.items(), key=lambda x: -x[1]["n"]):
        print(f"{k:14s} n={v['n']:3d} gross={v['gross_bp']:8.1f} cost={v['cost_bp']:6.1f} "
              f"net={v['net_bp']:8.1f} hit={v['hit']:.2f}")
    print()
    print("--- parameter grid, HELD-OUT, liquid subset, NET (sign stability) ---")
    for L in (120, 250):
        for K in (1.5, 2.0, 2.5):
            for MH in (10, 20, 40):
                s, _, _ = run(H, f"L{L} K{K} MH{MH}", pairs=liquid, L=L, K=K, MAXHOLD=MH)
                print(f"L={L} K={K} MH={MH:2d}  n={s.get('n',0):4d} "
                      f"net={s.get('net_bp',float('nan')):7.2f} t={s.get('t',float('nan')):5.2f} "
                      f"bookSharpe={s.get('book_sharpe',float('nan'))}")
