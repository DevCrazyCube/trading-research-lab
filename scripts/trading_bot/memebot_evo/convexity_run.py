#!/usr/bin/env python3
"""Driver: run the convexity probe on the REAL Bitquery tick cache and print the honest verdict.
PAPER ONLY. No orders/wallet/money. No git-commit. Frozen memebot + dashboard untouched.

In-sample MECHANISM CHECK (not a forward result): entries are decided by the momentum-surge + liquidity
gate over the whole on-disk cache; the SAME entry set is resolved under three exit policies (A/B/C).
"""
from __future__ import annotations
import json
import statistics
import convexity_probe as cp


def fmt_pct(x):
    return "n/a" if x is None else f"{x*100:+.1f}%"


def fmt_summary_row(label, s):
    if s.get("n", 0) == 0:
        return f"{label:<26} n=0"
    return (f"{label:<26} n={s['n']:<4} "
            f"meanNet={fmt_pct(s['mean_net_return']):>8} medNet={fmt_pct(s['median_net_return']):>8} "
            f"meanR={s['mean_R']:+6.2f} medR={s['median_R']:+6.2f} win%={s['win_rate']*100:4.1f} "
            f"bestR={s['best_R']:+7.1f} worstR={s['worst_R']:+6.1f}")


def loss_distribution(res):
    losses = [r["net_return"] for r in res if r["net_return"] <= 0]
    if not losses:
        return {"n_losses": 0}
    ls = sorted(losses)
    n = len(ls)
    def pct(p): return ls[min(n-1, int(round(p*(n-1))))]
    return {
        "n_losses": n,
        "mean_loss": statistics.mean(ls),
        "median_loss": statistics.median(ls),
        "worst_loss": ls[0],
        "p10_loss": pct(0.10), "p25_loss": pct(0.25),
        "frac_worse_than_-30%": sum(1 for x in ls if x < -0.30) / n,
        "frac_worse_than_-50%": sum(1 for x in ls if x < -0.50) / n,
    }


def winners_distribution(res):
    wins = sorted((r["net_return"] for r in res if r["net_return"] > 0), reverse=True)
    if not wins:
        return {"n_wins": 0}
    return {
        "n_wins": len(wins),
        "best_win": wins[0],
        "top3_wins": [round(w, 3) for w in wins[:3]],
        "mean_win": statistics.mean(wins),
    }


def main():
    mints = cp.all_mints()
    print(f"tick cache: {len(mints)} coins\n")

    # ---- Fixed representative ENTRY gate (mid-bounds momentum surge) --------------------------------
    # Held constant across all exit policies so the 3-way comparison is on the SAME entries.
    base_entry = dict(entry_surge_bps=300.0, entry_window_s=20, entry_min_buyfrac=0.60,
                      entry_min_trades=5)

    # ================================================================================================
    # PART 1: three-way exit comparison on the SAME entries, at a moderate liquidity gate
    # ================================================================================================
    LIQ = 5.0   # USD/sec throughput floor over the entry window
    entry_cfg = cp.Config(min_liq_usd_per_s=LIQ, **base_entry)
    entries = cp.generate_entries(entry_cfg, mints)
    print(f"PART 1 -- three-way exit comparison (liquidity gate = {LIQ} USD/s over the entry window)")
    print(f"entries qualifying the momentum+liquidity gate: {len(entries)}\n")

    policies = {
        "A capped tp300/sl200": cp.Config(policy="A", tp_bps=300, sl_bps=200, max_hold_s=180,
                                          min_liq_usd_per_s=LIQ, **base_entry),
        "B flow-only uncapped": cp.Config(policy="B", flip_window_s=20, flip_buy_frac=0.45, flip_K=2,
                                          max_hold_s=3600, min_liq_usd_per_s=LIQ, **base_entry),
        "C flow+backstop -60%": cp.Config(policy="C", flip_window_s=20, flip_buy_frac=0.45, flip_K=2,
                                          backstop_frac=0.60, max_hold_s=3600, min_liq_usd_per_s=LIQ,
                                          **base_entry),
    }
    part1 = {}
    for label, cfg in policies.items():
        res = cp.resolve_all(cfg, entries)
        s = cp.summarize(res)
        part1[label] = (res, s)
        print(fmt_summary_row(label, s))
    print()
    print("LOSS DISTRIBUTION (does flow-exit keep losers SMALLER than the price-stop?)")
    for label, (res, s) in part1.items():
        ld = loss_distribution(res)
        if ld.get("n_losses", 0) == 0:
            print(f"  {label:<26} no losses"); continue
        print(f"  {label:<26} nLoss={ld['n_losses']:<3} meanLoss={fmt_pct(ld['mean_loss']):>8} "
              f"medLoss={fmt_pct(ld['median_loss']):>8} worst={fmt_pct(ld['worst_loss']):>8} "
              f">-30%:{ld['frac_worse_than_-30%']*100:4.0f}% >-50%:{ld['frac_worse_than_-50%']*100:4.0f}%")
    print()
    print("WINNERS (is the right tail fat enough to pay for the losers + toll?)")
    for label, (res, s) in part1.items():
        wd = winners_distribution(res)
        if wd.get("n_wins", 0) == 0:
            print(f"  {label:<26} no winners"); continue
        print(f"  {label:<26} nWin={wd['n_wins']:<3} best={fmt_pct(wd['best_win']):>9} "
              f"top3={wd['top3_wins']} meanWin={fmt_pct(wd['mean_win']):>8}")
    print()

    # Exit-reason breakdown (why did losers exit -- flow-flip in time, or gap-through backstop?)
    print("EXIT-REASON MIX")
    for label, (res, s) in part1.items():
        print(f"  {label:<26} {s['reasons']}")
    print()

    # ---- WORKED EXAMPLE: one real coin walked under all three policies ------------------------------
    print("WORKED EXAMPLE -- one real coin, same entry, three exit policies")
    ex_entry = _pick_example(entries, policies["C flow+backstop -60%"])
    if ex_entry:
        for label, cfg in policies.items():
            bars = cp.load_tick_bars(ex_entry["mint"])
            fwd = bars[ex_entry["fwd_from"]:]
            r = cp.walk_exit(fwd, ex_entry["entry_epoch"], cfg)
            print(f"  {ex_entry['mint'][:10]}.. entry@{r['entry_px']:.3e}  [{label}]  "
                  f"walked {r['bars_walked']} bars -> {r['reason']} @ {r['exit_px']:.3e}  "
                  f"({r['gross_mult']:.2f}x)  netR={r['R']:+.2f}  net={fmt_pct(r['net_return'])}")
    print()

    # ================================================================================================
    # PART 2: sweep flow-flip sensitivity x liquidity gate for policy C -- is ANY cell net-positive?
    # ================================================================================================
    print("PART 2 -- sweep (policy C: flow-flip + -60% backstop, UNCAPPED winner)")
    print("looking for ANY cell with mean net return > 0 after the pinned 3% toll + pessimistic slip\n")
    print(f"{'liqUSD/s':>8} {'flipFrac':>8} {'K':>2} {'win_s':>6} | {'n':>4} {'meanNet':>9} "
          f"{'medNet':>8} {'win%':>5} {'bestR':>7} {'sumNet':>8}")
    best_cell = None
    cells = []
    for liq in [0.0, 5.0, 20.0, 50.0]:
        ecfg = cp.Config(min_liq_usd_per_s=liq, **base_entry)
        ents = cp.generate_entries(ecfg, mints)
        for frac in [0.35, 0.45, 0.55]:
            for K in [1, 2, 3]:
                for win_s in [10, 30]:
                    cfg = cp.Config(policy="C", flip_window_s=win_s, flip_buy_frac=frac, flip_K=K,
                                    backstop_frac=0.60, max_hold_s=3600, min_liq_usd_per_s=liq,
                                    **base_entry)
                    res = cp.resolve_all(cfg, ents)
                    s = cp.summarize(res)
                    if s["n"] < 10:
                        continue
                    row = dict(liq=liq, frac=frac, K=K, win_s=win_s, n=s["n"],
                               mean_net=s["mean_net_return"], med_net=s["median_net_return"],
                               win_rate=s["win_rate"], best_R=s["best_R"], sum_net=s["sum_net_return"])
                    cells.append(row)
                    if best_cell is None or row["mean_net"] > best_cell["mean_net"]:
                        best_cell = row
    for row in sorted(cells, key=lambda r: r["mean_net"], reverse=True)[:12]:
        print(f"{row['liq']:>8.0f} {row['frac']:>8.2f} {row['K']:>2} {row['win_s']:>6} | "
              f"{row['n']:>4} {fmt_pct(row['mean_net']):>9} {fmt_pct(row['med_net']):>8} "
              f"{row['win_rate']*100:>4.1f} {row['best_R']:>7.1f} {fmt_pct(row['sum_net']):>8}")
    print(f"\n... {len(cells)} cells with n>=10 evaluated.")
    n_pos = sum(1 for r in cells if r["mean_net"] > 0)
    print(f"cells net-positive (mean net return > 0 after toll+slip): {n_pos} / {len(cells)}")
    if best_cell:
        print(f"BEST cell: liq={best_cell['liq']} flipFrac={best_cell['frac']} K={best_cell['K']} "
              f"win_s={best_cell['win_s']}  meanNet={fmt_pct(best_cell['mean_net'])} "
              f"medNet={fmt_pct(best_cell['med_net'])} n={best_cell['n']}")

    # Save machine-readable summary alongside (NOT committed).
    out = {
        "n_coins": len(mints), "R_UNIT": cp.R_UNIT, "toll_per_side": cp.TOLL_PER_SIDE,
        "part1_liq": LIQ,
        "part1": {k: v[1] for k, v in part1.items()},
        "part2_best_cell": best_cell,
        "part2_n_positive_cells": n_pos, "part2_n_cells": len(cells),
        "part2_top_cells": sorted(cells, key=lambda r: r["mean_net"], reverse=True)[:12],
    }
    outp = "convexity_probe_result.json"
    with open(outp, "w") as fh:
        json.dump(out, fh, indent=2, default=str)
    print(f"\nwrote {outp}")


def _pick_example(entries, cfg_c):
    """Pick a real entry that shows a non-trivial path (walks several bars) for the worked example."""
    best = None
    for e in entries:
        bars = cp.load_tick_bars(e["mint"])
        fwd = bars[e["fwd_from"]:]
        if len(fwd) < 6:
            continue
        r = cp.walk_exit(fwd, e["entry_epoch"], cfg_c)
        if r and r["bars_walked"] >= 4:
            if best is None or r["bars_walked"] > best[1]["bars_walked"]:
                best = (e, r)
    return best[0] if best else (entries[0] if entries else None)


if __name__ == "__main__":
    main()
