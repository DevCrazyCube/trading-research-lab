#!/usr/bin/env python3
"""T7 -- EXPLORATORY diagnostics. NOT pre-registered. NO VERDICT FOLLOWS FROM ANY OF THIS.

Run only after the frozen verdict was written, to explain it. Every number here is labelled
exploratory in T7_RESULT.md for the same reason T3's D1/D2 were: a number that was not frozen
is not evidence.

D1  the close-to-OPEN variant (cum closing auction -> ex-date OPENING auction). Both legs are
    still auction prints. Deliberately excluded from the trial grid (pre-registration 7).
D2  the drop-off ratio with a confidence interval, and by dividend-yield bucket.
D3  the tax arithmetic, computed from the held-out numbers rather than asserted.
"""

from __future__ import annotations

import json
import math
import pathlib
import statistics as st
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.t3_pressure_reversal as t3                                       # noqa: E402
import scripts.t7_evaluate as ev                                                # noqa: E402
from scripts.trading_bot.stats import annualised_sharpe, moments                # noqa: E402

OUT = ROOT / "research" / "trading_bot"
ORDINARY_RATES = (0.24, 0.32, 0.35, 0.37, 0.408)     # 0.408 = 37% + 3.8% NIIT


def d1_close_to_open(panel, cfg, day_filter, label):
    """Exit at the ex-date OPENING auction instead of its closing auction. Both legs auctions.

    Reported WITH the same-day non-ex-dividend control and the same label permutation the frozen
    rule faced, because without them this is just "a long-stock/short-SPY book held overnight",
    and B22F measured the overnight session as carrying a large common drift. The control is the
    instrument that separates a dividend effect from an overnight-beta tilt.
    """
    import numpy as np

    auct = t3.auctions(sorted({s for v in t3.build_universe(500).values() for s in v}))
    uni = ev.universe_sets(cfg["top_n"])
    gross, control, pools, dropped = [], [], [], 0
    for day in sorted(panel):
        if not day_filter(day):
            continue
        rec = panel[day]
        cum = rec["cum"]
        allowed = uni.get(cum[:7], set()) & uni.get(day[:7], set())
        spy_c, spy_o = auct.get(f"SPY|{cum}"), auct.get(f"SPY|{day}")
        if not spy_c or not spy_o or "c" not in spy_c or "o" not in spy_o:
            dropped += 1
            continue
        r_spy = spy_o["o"] / spy_c["c"] - 1.0
        rows, ex_names = [], {e[0] for e in rec["events"]}
        for e in rec["events"]:
            sym, p_cum, _p_ex, rate, special = e
            if sym not in allowed or rate / p_cum < cfg["yield_min"]:
                continue
            if not cfg["include_special"] and special:
                continue
            a = auct.get(f"{sym}|{day}")
            if not a or "o" not in a or a["o"] <= 0:
                continue
            rows.append((a["o"] - p_cum + rate) / p_cum)
        pool = []
        for sym in allowed:
            if sym in ex_names or sym == "SPY":
                continue
            a, b = auct.get(f"{sym}|{cum}"), auct.get(f"{sym}|{day}")
            if not a or not b or "c" not in a or "o" not in b:
                continue
            if a["c"] <= 0 or b["o"] <= 0:
                continue
            pool.append(b["o"] / a["c"] - 1.0)
        if not rows or len(pool) < len(rows):
            continue
        gross.append(0.5 * sum(rows) / len(rows) - 0.5 * r_spy)
        control.append(0.5 * sum(pool) / len(pool) - 0.5 * r_spy)
        pools.append((np.asarray(pool), len(rows)))

    m, mc = moments(gross), moments(control)
    diff = [a - b for a, b in zip(gross, control)]
    md = moments(diff)

    rng = np.random.default_rng(20260817)
    trials = 10_000
    null = np.zeros(trials)
    for pool, k in pools:
        pick = np.argpartition(rng.random((trials, pool.size)), k - 1, axis=1)[:, :k]
        null += 0.5 * pool[pick].mean(axis=1)
    null /= len(pools)
    # the -0.5*r_spy hedge term is identical in observed and permuted and is added back here so
    # the two statistics are on the same scale.
    null += mc["mean"] - 0.5 * float(np.mean([p.mean() for p, _ in pools]))
    ge = int((null >= m["mean"]).sum())

    return {"label": label, "n_event_days": m["n"], "days_dropped_missing_spy_open": dropped,
            "gross_mean_per_day_bp": m["mean"] * 1e4,
            "t_stat": m["mean"] / m["sd"] * math.sqrt(m["n"]),
            "annualised_sharpe": annualised_sharpe(gross, 221),
            "control_mean_per_day_bp": mc["mean"] * 1e4,
            "control_t_stat": mc["mean"] / mc["sd"] * math.sqrt(mc["n"]),
            "basket_minus_control_bp": md["mean"] * 1e4,
            "basket_minus_control_t": md["mean"] / md["sd"] * math.sqrt(md["n"]),
            "label_permutation_p_right": (ge + 1) / (trials + 1),
            "label_permutation_null_mean_bp": float(null.mean()) * 1e4,
            "label_permutation_null_sd_bp": float(null.std(ddof=1)) * 1e4,
            "note": "EXPLORATORY. Not in the declared grid; no verdict follows."}


def d2_dropoff(panel, cfg, day_filter, label):
    """Drop-off ratio with an interval, and by dividend-yield bucket.

    The interval comes from the DAY-level portfolio series, not from the per-event scatter: the
    events on one day share a market move, so an event-level standard error would over-state the
    information by roughly sqrt(events per day).
    """
    uni = ev.universe_sets(cfg["top_n"])
    day_excess, yields_all, buckets = [], [], {}
    for day in sorted(panel):
        if not day_filter(day):
            continue
        rec = panel[day]
        cum = rec["cum"]
        allowed = uni.get(cum[:7], set()) & uni.get(day[:7], set())
        r_spy = rec["spy"]
        rows = []
        for e in rec["events"]:
            sym, p_cum, p_ex, rate, special = e
            if sym not in allowed or rate / p_cum < cfg["yield_min"]:
                continue
            if not cfg["include_special"] and special:
                continue
            y = rate / p_cum
            excess = (p_ex - p_cum + rate) / p_cum - r_spy
            rows.append(excess)
            yields_all.append(y)
            key = ("<0.25%" if y < 0.0025 else "0.25-0.5%" if y < 0.005
                   else "0.5-1.0%" if y < 0.01 else ">=1.0%")
            b = buckets.setdefault(key, {"drop": 0.0, "div": 0.0, "n": 0, "excess": []})
            b["drop"] += p_cum * (1 + r_spy) - p_ex
            b["div"] += rate
            b["n"] += 1
            b["excess"].append(excess)
        if rows:
            day_excess.append(sum(rows) / len(rows))
    m = moments(day_excess)
    mean_y = st.mean(yields_all)
    se = m["sd"] / math.sqrt(m["n"])
    lo, hi = m["mean"] - 1.96 * se, m["mean"] + 1.96 * se
    return {
        "label": label,
        "n_event_days": m["n"], "n_events": len(yields_all),
        "mean_yield_pct": mean_y * 100,
        "mean_excess_per_event_bp": m["mean"] * 1e4,
        "t_stat_day_clustered": m["mean"] / se,
        "implied_dropoff_ratio": 1 - m["mean"] / mean_y,
        "dropoff_ratio_95ci": [1 - hi / mean_y, 1 - lo / mean_y],
        "by_yield_bucket": {
            k: {"n_events": v["n"],
                "dollar_weighted_dropoff_ratio": v["drop"] / v["div"],
                "mean_excess_per_event_bp": st.mean(v["excess"]) * 1e4}
            for k, v in sorted(buckets.items())},
        "note": "EXPLORATORY. The buckets are descriptive; none of them is a declared trial.",
    }


def d3_tax(heldout):
    """The after-tax arithmetic, from the held-out numbers. See T7_RESULT.md for the argument."""
    ppy = heldout["periods_per_year_used"]
    yield_per_event = heldout["dropoff_heldout"]["mean_yield_pct"] / 100
    dr = heldout["dropoff_heldout"]["dollar_weighted_dropoff_ratio"]
    net_bp_day = heldout["net"]["mean_per_day_bp"]

    # The book is 50% long the basket, so the dividend received per event-day is 0.5 * yield.
    div_income_per_year = 0.5 * yield_per_event * ppy
    profit_per_year = net_bp_day / 1e4 * ppy
    cap_loss_per_year = div_income_per_year - profit_per_year

    rows = {}
    for t in ORDINARY_RATES:
        rows[f"{t:.3f}"] = {
            "case_A_losses_fully_usable_after_tax_return_pct": profit_per_year * (1 - t) * 100,
            "case_B_losses_unusable_tax_on_dividend_pct_of_equity": div_income_per_year * t * 100,
            "case_B_after_tax_return_pct": (profit_per_year - div_income_per_year * t) * 100,
            "dropoff_ratio_needed_to_break_even_case_B": 1 - t,
        }
    return {
        "held_out_inputs": {
            "mean_dividend_yield_per_event_pct": yield_per_event * 100,
            "dollar_weighted_dropoff_ratio": dr,
            "event_days_per_year": ppy,
            "net_pre_tax_return_pct_per_year": profit_per_year * 100,
        },
        "ordinary_dividend_income_pct_of_equity_per_year": div_income_per_year * 100,
        "short_term_capital_LOSS_pct_of_equity_per_year": cap_loss_per_year * 100,
        "by_marginal_ordinary_rate": rows,
        "note": ("EXPLORATORY arithmetic, but the INPUTS are the frozen held-out result. A "
                 "one-day hold can never satisfy the 61-day qualified-dividend holding period "
                 "of IRC 1(h)(11)(B)(iii), so every dollar of dividend here is ORDINARY income. "
                 "Case A assumes the short-term capital losses are fully absorbed by other "
                 "realised capital gains; case B assumes they are not, in which case IRC 1211(b) "
                 "caps the deduction against ordinary income at $3,000/yr and the rest carries "
                 "forward."),
    }


if __name__ == "__main__":
    heldout = json.loads((OUT / "T7_HELDOUT_RESULT.json").read_text())
    cfg = heldout["frozen_config"]
    panel, _ = ev.load_panel()
    design = lambda d: d <= t3.DESIGN_END                                       # noqa: E731
    test = lambda d: d >= t3.TEST_START                                         # noqa: E731

    out = {
        "NOT_PREREGISTERED": ("Every number in this file is exploratory and was computed AFTER "
                              "the frozen verdict. No verdict follows from any of it."),
        "frozen_config": cfg,
        "D1_close_to_open_design": d1_close_to_open(panel, cfg, design, "D1 design 2016-2021"),
        "D1_close_to_open_heldout": d1_close_to_open(panel, cfg, test, "D1 held-out 2022-2026"),
        "D2_dropoff_design": d2_dropoff(panel, cfg, design, "D2 design 2016-2021"),
        "D2_dropoff_heldout": d2_dropoff(panel, cfg, test, "D2 held-out 2022-2026"),
        "D3_tax": d3_tax(heldout),
    }
    (OUT / "T7_DIAGNOSTICS.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))
