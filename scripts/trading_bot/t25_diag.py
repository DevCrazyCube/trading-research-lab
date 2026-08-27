#!/usr/bin/env python3
"""T25 — DESIGN-WINDOW-ONLY diagnostics, written AFTER the census returned POWER-BLOCKED.

The gate (§7) says the held-out window is not spent when G1 fails, and §8 forbids reading
anything here as evidence for the candidate.  This file exists only so the two facts that
outlive the block are on the record, exactly as T23 recorded its two.

NOTHING in here touches 2023-06 .. 2024-09.  Every number is from the window T21 already
burned (2024-10 .. 2026-07).

Usage: python3 scripts/trading_bot/t25_diag.py
"""
from __future__ import annotations

import json
import math
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from trading_bot import t25_census as C  # noqa: E402

OUT = os.path.join(C.REPO, "research", "trading_bot", "T25_DESIGN_DIAGNOSTIC.json")


def main() -> int:
    C.assert_gate()
    uni = json.load(open(os.path.join(C.CACHE, "universe.json")))
    coin2sym = {r["coin"]: r["binance"] for r in uni["download_universe"]}
    hl = C.load_hl()
    syms = {coin2sym[c] for c in hl}
    bn = C.load_binance(syms)
    adv = C.load_adv(syms)
    tb = C.tbill_by_month()

    months = C.months_between(*C.WINDOWS["DESIGN"])
    eligible = {}
    for m in months:
        pm = C.prev_month(m)
        asof = C.month_end_ms(pm)
        eligible[m] = [
            c
            for c, s in coin2sym.items()
            if c in hl
            and pm in hl[c]
            and pm in bn.get(s, {})
            and m in hl[c]
            and m in bn.get(s, {})
            and C.trailing_adv(adv.get(s, []), asof) >= C.ADV_MIN
        ]

    out = {
        "WARNING": "DESIGN WINDOW ONLY (2024-10..2026-07), the months T21 already searched. "
        "Gate §8 forbids reading any of this as evidence for the candidate. "
        "The held-out window 2023-06..2024-09 was NOT touched by this file.",
        "gate_sha256": C.assert_gate(),
        "books": {},
    }
    for n in C.TOPN_GRID:
        rows = []
        for m in months:
            names = eligible.get(m, [])
            if len(names) < n:
                continue
            pm = C.prev_month(m)
            scored = sorted(
                (
                    (
                        abs(hl[c][pm] - bn[coin2sym[c]][pm]),
                        math.copysign(1.0, hl[c][pm] - bn[coin2sym[c]][pm]),
                        hl[c][m] - bn[coin2sym[c]][m],
                        c,
                    )
                    for c in names
                ),
                reverse=True,
            )[:n]
            gross = sum(s * d for _, s, d, _ in scored) / len(scored)
            net = (gross - C.FRICTION_PP) / C.CAPITAL_MULT
            rows.append(
                {
                    "month": m,
                    "gross_pp_yr": gross,
                    "excess_pp_yr": net - tb.get(m, 3.84),
                    "hit": sum(1 for _, s, d, _ in scored if s * d > 0) / len(scored),
                }
            )
        ex = [r["excess_pp_yr"] for r in rows]
        mo = [r["excess_pp_yr"] * C.month_days(r["month"]) / 365.25 for r in rows]
        mean_ann = statistics.mean(ex)
        sd_ann = statistics.stdev(mo) * math.sqrt(12)
        out["books"][str(n)] = {
            "n_months": len(rows),
            "mean_gross_differential_pp_yr": round(statistics.mean(r["gross_pp_yr"] for r in rows), 3),
            "mean_net_excess_over_tbill_pp_yr": round(mean_ann, 3),
            "sd_annual_pct": round(sd_ann, 3),
            "t_stat": round(mean_ann / (sd_ann / math.sqrt(len(rows) / 12.0)), 3) if sd_ann else None,
            "share_of_months_positive": round(
                sum(1 for v in ex if v > 0) / len(ex), 3
            ),
            "sign_hit_rate_of_selected_names": round(
                statistics.mean(r["hit"] for r in rows), 3
            ),
            "worst_month_excess_pp_yr": round(min(ex), 3),
            "bar_pp": C.BAR,
            "clears_bar": mean_ann > C.BAR,
        }
    with open(OUT, "w") as fh:
        json.dump(out, fh, indent=1)
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
