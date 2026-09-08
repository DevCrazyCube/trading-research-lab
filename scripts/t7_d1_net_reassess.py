#!/usr/bin/env python3
"""RE-ASSESS T7 D1 (close -> ex-open) NET of the T7 primary cost rung + stress ladder + DSR.

Not a new search: identical rule to T7_DIAGNOSTICS D1, only the cost model and the deflation
that the exploratory diagnostic never applied are added.
"""
from __future__ import annotations
import datetime, json, math, pathlib, sys

ROOT = pathlib.Path("/home/anont/meme")
sys.path.insert(0, str(ROOT))

import numpy as np
import scripts.t3_pressure_reversal as t3
import scripts.t7_evaluate as ev
from scripts.trading_bot.stats import (annualised_sharpe, moments, deflated_sharpe,
                                       expected_max_sharpe)
from scripts.t7_evaluate import SEC31_FRACTION, TAF_MICROS_PER_SHARE

CFG = json.loads((ROOT / "research/trading_bot/T7_FROZEN_CONFIG.json").read_text())
cfg = CFG["frozen_config"] if "frozen_config" in CFG else CFG
print("cfg keys:", list(CFG)[:10], file=sys.stderr)
cfg = {"yield_min": 0.0, "top_n": 500, "include_special": True}

H_TEST_BP = 1.43   # T3 first-party measured median closing half-spread, 2022-2026
BORROW = 0.0033    # B22G measured ETB general collateral median


def gap_days(cum, ex):
    return max(1, (datetime.date.fromisoformat(ex) - datetime.date.fromisoformat(cum)).days)


_AU = {}


def run(panel, day_filter, half_spread_bp):
    if not _AU:
        _AU["a"] = t3.auctions(sorted({s for v in t3.build_universe(500).values() for s in v}))
    auct = _AU["a"]
    uni = ev.universe_sets(cfg["top_n"])
    dates, gross, net, control, pools = [], [], [], [], []
    hs = half_spread_bp / 1e4
    for day in sorted(panel):
        if not day_filter(day):
            continue
        rec = panel[day]
        cum = rec["cum"]
        allowed = uni.get(cum[:7], set()) & uni.get(day[:7], set())
        spy_c, spy_o = auct.get(f"SPY|{cum}"), auct.get(f"SPY|{day}")
        if not spy_c or not spy_o or "c" not in spy_c or "o" not in spy_o:
            continue
        r_spy = spy_o["o"] / spy_c["c"] - 1.0
        rows, ex_names = [], {e[0] for e in rec["events"]}
        prices = []
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
            prices.append((p_cum, a["o"]))
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
        k = len(rows)
        g = 0.5 * sum(rows) / k - 0.5 * r_spy
        # --- costs, identical accounting to t7_evaluate.run_config ---
        cost = hs * 1.0 + hs * 1.0                      # 1.0 notional opened, 1.0 closed
        cost += float(SEC31_FRACTION) * 1.0             # both sale legs, 0.5 notional each
        inv_buy = sum(1.0 / p[0] for p in prices) / k
        inv_sell = sum(1.0 / p[1] for p in prices) / k
        taf = TAF_MICROS_PER_SHARE / 1e6
        cost += taf * 0.5 * (inv_buy + inv_sell)
        cost += taf * 1.0 / rec["spy_price"]
        cost += 0.5 * BORROW * gap_days(cum, day) / 365.25
        dates.append(day)
        gross.append(g)
        net.append(g - cost)
        control.append(0.5 * sum(pool) / len(pool) - 0.5 * r_spy)
        pools.append((np.asarray(pool), k))
    return dates, gross, net, control, pools


def rep(x, label):
    m = moments(x)
    return {"label": label, "n": m["n"], "mean_bp": m["mean"] * 1e4,
            "t": m["mean"] / m["sd"] * math.sqrt(m["n"]),
            "sharpe_per_obs": m["mean"] / m["sd"],
            "ann_sharpe_221": annualised_sharpe(x, 221),
            "skew": m["skew"], "kurtosis_non_excess": m["kurtosis"]}


def main():
    panel, _ = ev.load_panel()
    test = lambda d: d >= "2022-01-03"
    design = lambda d: d <= "2021-12-31"

    out = {}
    for name, filt in (("heldout_2022_2026", test), ("design_2016_2021", design)):
        d, g, n, c, pools = run(panel, filt, 0.0)
        diff = [a - b for a, b in zip(n, c)]
        out[name] = {"gross": rep(g, "gross"), "net_auction_rail": rep(n, "net primary rung"),
                     "control": rep(c, "control"),
                     "net_minus_control": rep(diff, "net - control")}
        # stress ladder
        ladder = {}
        for mult, tag in ((0.5, "0.5h per leg"), (1.0, "h per leg"), (2.0, "2h per leg")):
            _, _, ns, _, _ = run(panel, filt, mult * H_TEST_BP)
            ladder[tag] = rep(ns, tag)
        out[name]["stress_ladder"] = ladder
        if name == "heldout_2022_2026":
            # DSR on the NET series at the pre-registered trial variance
            sv = 1.657e-3
            mn = moments(n)
            sr = mn["mean"] / mn["sd"]
            for tr in (8, 9, 24):
                out[name][f"DSR_net_trials_{tr}"] = deflated_sharpe(
                    n, trials=tr, sharpe_variance=sv)
                out[name][f"expected_max_sharpe_{tr}"] = expected_max_sharpe(tr, sv)
            out[name]["observed_sharpe_per_obs_net"] = sr
            # bootstrap fraction positive
            rng = np.random.default_rng(20260820)
            a = np.asarray(n)
            bs = rng.choice(a, size=(10000, a.size), replace=True).mean(axis=1)
            out[name]["bootstrap_frac_positive_net"] = float((bs > 0).mean())
    print(json.dumps(out, indent=1, default=float))


main()
