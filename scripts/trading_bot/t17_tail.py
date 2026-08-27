#!/usr/bin/env python3
"""T17 FAT-TAIL DRAWDOWN. POST-HOC, and never a gate.

The primary held-out run draws each trade's slippage once, from a single fixed seed. That
gives ONE realisation of the friction, and a single realisation cannot show what B22B's tail
does to a drawdown -- which is the whole reason the empirical mode exists. This script
re-runs the held-out window under `SEEDS` independent draw sequences from the SAME measured
distribution, changing nothing else, and reports the distribution of the outcome.

It is deliberately separate from the frozen driver and is labelled POST_HOC in the artifact
it writes. It cannot change the verdict; it says how wide the verdict's error bar is.
"""

from __future__ import annotations

import json
import math
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from trading_bot import costs as COSTS  # noqa: E402
from trading_bot import frozen as PINNED  # noqa: E402
from trading_bot import stats as STATS  # noqa: E402
from trading_bot import t17_orb as ORB  # noqa: E402
from trading_bot import t17_run as RUN  # noqa: E402

CACHE = ROOT / "research" / "data" / "t17_cache"
OUT = ROOT / "research" / "trading_bot"
SEEDS = 50


def main(window="heldout"):
    lo, hi = ((ORB.HELDOUT_START, ORB.HELDOUT_END) if window == "heldout"
              else (ORB.POSTPAPER_START, ORB.POSTPAPER_END))
    selection = json.loads((CACHE / "selection.json").read_text())
    days = [d for d in sorted(selection) if lo <= d <= hi]
    cost = COSTS.b22b_measured_costs()
    exit_frac = cost.exit_half_spread.value * COSTS.BP

    slips = [RUN.KeyedSlippage(RUN.SLIP_SEED + 1_000_003 * s) for s in range(SEEDS)]
    equity = [RUN.START_EQUITY_MICROS] * SEEDS
    daily = [[] for _ in range(SEEDS)]

    for di, day in enumerate(days):
        picks = selection.get(day) or []
        p = CACHE / "paths" / f"{day}.json"
        if not picks or not p.exists():
            continue
        raw = json.loads(p.read_text())
        prepared = []
        for rank, (relvol, sym, direction, or_high, or_low, atr) in enumerate(picks):
            path = raw.get(sym)
            if not path:
                continue
            bars = [{"o": PINNED.to_micros(b[1]), "h": PINNED.to_micros(b[2]),
                     "l": PINNED.to_micros(b[3]), "c": PINNED.to_micros(b[4])} for b in path]
            prepared.append((rank, sym, direction,
                             or_high if direction == "long" else or_low,
                             PINNED.r_unit_micros(atr), bars))
        for s in range(SEEDS):
            eq = equity[s]
            sized = []
            for rank, sym, direction, level, r_micros, bars in prepared:
                key = di * 1_000_003 + rank * 97 + (1 if direction == "long" else 2)
                e = slips[s].draw_keyed(r_micros, key)
                x = slips[s].draw_keyed(r_micros, key + 500_000_003)
                res = ORB.simulate_stock_day(direction, level, r_micros, bars, e, x)
                res["entry_level"] = level
                sized.append({"symbol": sym, "res": res, "entry_level": level,
                              "r_micros": r_micros,
                              "shares": ORB.position_shares(eq, r_micros)})
            pnl = 0
            for item in ORB.apply_gross_cap(sized, eq):
                res = item["res"]
                if res["outcome"] == "NO_TRIGGER":
                    continue
                pnl += (res["pnl_per_share"] * item["shares"]
                        - int(res["exit"] * item["shares"] * exit_frac))
            daily[s].append(pnl / eq)
            equity[s] = eq + pnl
        if di % 100 == 0:
            print(f"{day} ({di}/{len(days)})", flush=True)

    rows = []
    for s in range(SEEDS):
        d = daily[s]
        eq, peak, mdd = 1.0, 1.0, 0.0
        for r in d:
            eq *= 1 + r
            peak = max(peak, eq)
            mdd = max(mdd, 1 - eq / peak)
        m = STATS.moments(d)
        rows.append({"seed_index": s, "annualised_sharpe": STATS.annualised_sharpe(d, 252),
                     "max_drawdown": mdd, "final_multiple": eq,
                     "annualised_return": eq ** (252 / len(d)) - 1 if eq > 0 else -1.0,
                     "t_stat": m["mean"] / m["sd"] * math.sqrt(m["n"])})

    def dist(field):
        v = sorted(r[field] for r in rows)
        n = len(v)
        return {"min": v[0], "p10": v[n // 10], "p50": v[n // 2], "p90": v[9 * n // 10],
                "max": v[-1], "mean": sum(v) / n}

    report = {
        "document": "T17_FAT_TAIL_POST_HOC",
        "status": ("POST HOC. Not a gate, not a declared trial. The held-out verdict is in "
                   "T17_HELDOUT_RESULT.json and this does not amend it."),
        "window": [lo, hi], "sessions": len(days), "seeds": SEEDS,
        "what_varies": ("ONLY the sequence of draws from B22B's 425 decontaminated measured "
                        "entry-slippage observations. Same rule, same selection, same paths, "
                        "same sizing, same cost model."),
        "annualised_sharpe": dist("annualised_sharpe"),
        "max_drawdown": dist("max_drawdown"),
        "annualised_return": dist("annualised_return"),
        "t_stat": dist("t_stat"),
        "share_of_seeds_with_sharpe_below_1": sum(
            1 for r in rows if r["annualised_sharpe"] < 1.0) / SEEDS,
        "share_of_seeds_with_t_below_1p96": sum(
            1 for r in rows if r["t_stat"] < 1.96) / SEEDS,
        "per_seed": rows,
    }
    (OUT / f"T17_FAT_TAIL_{window.upper()}.json").write_text(json.dumps(report, indent=1))
    print(json.dumps({k: v for k, v in report.items() if k != "per_seed"}, indent=1))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "heldout")
