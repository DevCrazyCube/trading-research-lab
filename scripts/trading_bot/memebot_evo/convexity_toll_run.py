#!/usr/bin/env python3
"""Driver: re-score the convexity probe's policy B under a REALISTIC per-venue toll + slippage.

PAPER ONLY. No orders/wallet/money. No git-commit. Frozen memebot + dashboard untouched.
IN-SAMPLE MECHANISM/PLAUSIBILITY CHECK, forward-unconfirmed. Reuses convexity_probe's momentum entries
and policy-B walker UNCHANGED (walked with cost pinned to zero to extract the raw price path), then
applies convexity_toll's venue-aware cost. See convexity_toll.py for the honest proxy + cost rationale.
"""
from __future__ import annotations
import json
import statistics
import convexity_probe as cp
import convexity_toll as ct

BASE_ENTRY = dict(entry_surge_bps=300.0, entry_window_s=20, entry_min_buyfrac=0.60, entry_min_trades=5)
LIQ_GATE = 5.0   # the frozen probe's part-1 entry liquidity gate -> the SAME 784 entries / 232 coins
DEFAULT_SPLIT = 50.0


def fpct(x):
    return "n/a" if x is None else f"{x*100:+.1f}%"


def raw_paths():
    """Reproduce the exact 784 entries and walk policy B with ZERO cost to get the raw gross path."""
    mints = cp.all_mints()
    ecfg = cp.Config(min_liq_usd_per_s=LIQ_GATE, **BASE_ENTRY)
    entries = cp.generate_entries(ecfg, mints)
    b_costless = cp.Config(policy="B", flip_window_s=20, flip_buy_frac=0.45, flip_K=2,
                           max_hold_s=3600, min_liq_usd_per_s=LIQ_GATE,
                           toll_per_side=0.0, exit_slip_bps=0.0, **BASE_ENTRY)
    rows = []
    for e in entries:
        bars = cp.load_tick_bars(e["mint"])
        fwd = bars[e["fwd_from"]:]
        r = cp.walk_exit(fwd, e["entry_epoch"], b_costless)
        if r is None:
            continue
        rows.append({
            "mint": e["mint"],
            "liq": e["diag"]["liq_usd_per_s"],
            "gross_mult": r["gross_mult"],       # raw exit/entry, cost-free path
            "reason": r["reason"],
            "held_s": r["held_s"],
        })
    return rows


def score(rows, split):
    """Attach venue + realistic net return to each row for a given liquidity split."""
    out = []
    for r in rows:
        c = ct.cost_for(r["liq"], split)
        nr = ct.net_return(r["gross_mult"], c)
        out.append({**r, "venue": c.venue, "net": nr,
                    "slip_bps_side": c.slip_bps_side, "toll_rt": c.round_trip_toll})
    return out


def summarize(scored, total_n):
    if not scored:
        return {"n": 0, "frac": 0.0}
    gross = [s["gross_mult"] - 1.0 for s in scored]     # gross return per trade
    nets = [s["net"] for s in scored]
    wins = [x for x in nets if x > 0]
    best = max(scored, key=lambda s: s["net"])
    return {
        "n": len(scored),
        "frac": len(scored) / total_n if total_n else 0.0,
        "gross_mean": statistics.mean(gross),
        "net_mean": statistics.mean(nets),
        "net_median": statistics.median(nets),
        "win_rate": len(wins) / len(nets),
        "best_net": max(nets),
        "best_gross_mult": best["gross_mult"],
        "best_liq": best["liq"],
        "sum_net": sum(nets),
    }


def row_str(label, s):
    if s.get("n", 0) == 0:
        return f"{label:<22} n=0"
    return (f"{label:<22} n={s['n']:<4} frac={s['frac']*100:4.0f}%  "
            f"gross={fpct(s['gross_mean']):>7}  net_mean={fpct(s['net_mean']):>7}  "
            f"net_med={fpct(s['net_median']):>7}  win%={s['win_rate']*100:4.1f}  "
            f"best={s['best_gross_mult']:5.2f}x({fpct(s['best_net'])})")


def main():
    rows = raw_paths()
    n = len(rows)
    print(f"policy-B raw paths reproduced: {n} entries / {len(set(r['mint'] for r in rows))} coins "
          f"(entry liq gate {LIQ_GATE} USD/s)\n")

    # Sanity: the raw (cost-free) gross edge that the frozen probe reported
    gross_all = [r["gross_mult"] - 1.0 for r in rows]
    print(f"RAW GROSS EDGE (cost-free) : mean={fpct(statistics.mean(gross_all))}  "
          f"median={fpct(statistics.median(gross_all))}  "
          f"best={max(r['gross_mult'] for r in rows):.2f}x  "
          f"win%(gross>0)={sum(1 for g in gross_all if g>0)/n*100:.1f}\n")

    # ============================================================================================
    # THREE-WAY TABLE at the default split
    # ============================================================================================
    print(f"{'='*118}")
    print(f"THREE-WAY NET RE-SCORING  (realistic per-venue toll + liquidity-scaled slippage;  "
          f"CHEAP/EXPENSIVE split = {DEFAULT_SPLIT:.0f} USD/s)")
    print(f"{'='*118}")
    scored = score(rows, DEFAULT_SPLIT)
    cheap = [s for s in scored if s["venue"] == "CHEAP"]
    exp = [s for s in scored if s["venue"] == "EXPENSIVE"]
    s_all = summarize(scored, n)
    s_cheap = summarize(cheap, n)
    s_exp = summarize(exp, n)
    print(row_str("(a) ALL entries", s_all))
    print(row_str("(b) CHEAP/liquid", s_cheap))
    print(row_str("(c) EXPENSIVE b-curve", s_exp))
    print()
    print(f"  CHEAP subset NET-POSITIVE? {'YES' if s_cheap['net_mean'] > 0 else 'NO'}  "
          f"(net_mean {fpct(s_cheap['net_mean'])}, n={s_cheap['n']})")

    # ============================================================================================
    # WINNER LOCATION -- do the fat runners live on CHEAP or EXPENSIVE coins?
    # ============================================================================================
    print(f"\n{'='*118}")
    print("WINNER LOCATION -- where do the fat gross runners live? (top 15 by gross multiple)")
    print(f"{'='*118}")
    top = sorted(scored, key=lambda s: s["gross_mult"], reverse=True)[:15]
    print(f"  {'gross':>7} {'liq USD/s':>11} {'venue':>10} {'slip/side':>10} {'net@split50':>12}  reason")
    for s in top:
        print(f"  {s['gross_mult']:>6.2f}x {s['liq']:>11.1f} {s['venue']:>10} "
              f"{s['slip_bps_side']:>8.0f}bp {fpct(s['net']):>12}  {s['reason']}")
    winners = [s for s in scored if s["gross_mult"] > 1.0]
    losers = [s for s in scored if s["gross_mult"] <= 1.0]
    big = [s for s in scored if s["gross_mult"] >= 2.0]   # >=2x runners
    print(f"\n  mean liq  winners(gross>0): {statistics.mean([s['liq'] for s in winners]):.0f} USD/s "
          f"| losers: {statistics.mean([s['liq'] for s in losers]):.0f} USD/s")
    if big:
        n_big_cheap = sum(1 for s in big if s["venue"] == "CHEAP")
        print(f"  >=2x runners: {len(big)} total, {n_big_cheap} CHEAP / {len(big)-n_big_cheap} EXPENSIVE "
              f"(at split {DEFAULT_SPLIT:.0f})  median liq of runners = "
              f"{statistics.median([s['liq'] for s in big]):.0f} USD/s")

    # ============================================================================================
    # SPLIT SWEEP -- cleanest cheap cut; is ANY cheap cell net-positive with meaningful n?
    # ============================================================================================
    print(f"\n{'='*118}")
    print("SPLIT SWEEP -- CHEAP subset (liq >= split) re-scored with realistic toll+slippage")
    print(f"{'='*118}")
    print(f"  {'split':>6} | {'n_cheap':>7} {'frac':>5} | {'gross':>7} {'net_mean':>9} {'net_med':>8} "
          f"{'win%':>5} {'best':>8} {'sum_net':>8}")
    sweep = []
    best_pos = None
    for split in [5, 10, 20, 30, 50, 75, 100, 150, 200, 300, 500, 1000]:
        sc = score(rows, split)
        ch = [s for s in sc if s["venue"] == "CHEAP"]
        st = summarize(ch, n)
        if st["n"] == 0:
            continue
        sweep.append({"split": split, **st})
        flag = "  <== net-positive" if st["net_mean"] > 0 else ""
        print(f"  {split:>6} | {st['n']:>7} {st['frac']*100:>4.0f}% | {fpct(st['gross_mean']):>7} "
              f"{fpct(st['net_mean']):>9} {fpct(st['net_median']):>8} {st['win_rate']*100:>4.1f} "
              f"{st['best_gross_mult']:>6.2f}x {fpct(st['sum_net']):>8}{flag}")
        if st["net_mean"] > 0 and (best_pos is None or st["net_mean"] > best_pos["net_mean"]):
            best_pos = {"split": split, **st}

    print()
    if best_pos:
        print(f"BEST net-positive CHEAP cell: split>={best_pos['split']} USD/s  "
              f"net_mean={fpct(best_pos['net_mean'])} net_med={fpct(best_pos['net_median'])} "
              f"win%={best_pos['win_rate']*100:.1f}  n={best_pos['n']} ({best_pos['frac']*100:.0f}% of entries)")
    else:
        # report how far off the best (least-negative) cheap cell is
        least_neg = max(sweep, key=lambda r: r["net_mean"])
        print(f"NO net-positive cheap cell. Least-negative: split>={least_neg['split']} USD/s "
              f"net_mean={fpct(least_neg['net_mean'])} (n={least_neg['n']}); "
              f"its gross={fpct(least_neg['gross_mean'])} so cost overhang = "
              f"{fpct(least_neg['gross_mean']-least_neg['net_mean'])}.")

    # ---- tradeable volume: the cache is a SINGLE short firehose snapshot -- report honestly --------
    span_min = _cache_span_minutes(rows)
    print(f"\nTRADEABLE VOLUME: the whole cache is ONE ~{span_min:.0f}-minute Pumpfun+Pumpswap firehose "
          f"snapshot (not a multi-day series), so a per-DAY rate is not estimable. Reporting arrival "
          f"rate within the snapshot instead:")
    for split in [50, 100, 200]:
        sc = score(rows, split)
        ncheap = sum(1 for s in sc if s["venue"] == "CHEAP")
        print(f"  split>={split:>3}: {ncheap} cheap entries in ~{span_min:.0f} min -> "
              f"~{ncheap/max(span_min,1e-9):.1f} entries/min across the market (firehose, one snapshot)")
    print("  => raw arrival rate is high (many/min market-wide); tradeable VOLUME is NOT the binding "
          "constraint. Edge QUALITY is (see medians below).")

    out = {
        "note": "IN-SAMPLE plausibility re-scoring; forward-unconfirmed. PAPER ONLY.",
        "n_entries": n, "n_coins": len(set(r['mint'] for r in rows)),
        "entry_liq_gate": LIQ_GATE, "default_split": DEFAULT_SPLIT,
        "cost_model": {
            "toll_cheap_side": ct.TOLL_CHEAP_SIDE, "toll_expensive_side": ct.TOLL_EXPENSIVE_SIDE,
            "slip_floor_bps": ct.SLIP_FLOOR_BPS, "slip_cap_bps": ct.SLIP_CAP_BPS,
            "slip_coef": ct.SLIP_COEF,
        },
        "raw_gross_mean": statistics.mean(gross_all),
        "three_way": {"all": s_all, "cheap": s_cheap, "expensive": s_exp},
        "split_sweep": sweep,
        "best_positive_cheap_cell": best_pos,
        "cache_span_minutes": span_min,
    }
    with open("convexity_toll_result.json", "w") as fh:
        json.dump(out, fh, indent=2, default=str)
    print("\nwrote convexity_toll_result.json")


def _cache_span_minutes(rows):
    """Wall-clock span of the tick cache in MINUTES (max-min bar epoch over the entry coins)."""
    lo = hi = None
    for mint in set(r["mint"] for r in rows):
        bars = cp.load_tick_bars(mint)
        if not bars:
            continue
        t0, t1 = bars[0]["t"], bars[-1]["t"]
        lo = t0 if lo is None else min(lo, t0)
        hi = t1 if hi is None else max(hi, t1)
    return (hi - lo) / 60.0 if (lo is not None and hi is not None) else 0.0


if __name__ == "__main__":
    main()
