#!/usr/bin/env python3
"""CEFBOT -- the read-only evaluate-and-improve loop.

Scores the realised forward ledger against (1) a T-bill + 1pp/yr absolute hurdle and (2) the
buy-and-hold-the-CEF-basket null (to separate discount-reversion ALPHA from CEF BETA). It reports
cumulative return, Sharpe, per-rebalance hit rate and drawdown HONESTLY, and enforces the standard
"below N observations = NO VERDICT, behaviour not evidence" framing.

Per ITERATION_PROTOCOL.md §2 the evaluator READS; it does not edit a running rule or restart a
ledger. The only state it is allowed to influence is the pre-registered KILL switch (§6), and even
that it merely *detects and reports* -- `bot.run_cycle` is what flips the status, at run time,
before committing a new book. Improvement is a NEW pre-registration, never a tweak here.
"""

from __future__ import annotations

import json
import math

from scripts.trading_bot import stats as S
from scripts.trading_bot.cefbot import strategy as G


def weekly_hurdle() -> float:
    return (1.0 + G.BENCH_TBILL_ANNUAL + G.BENCH_ALPHA_ANNUAL) ** (1.0 / G.WEEKS_PER_YEAR) - 1.0


def read_settled() -> list:
    """Every settled weekly tranche with a numeric net, oldest first."""
    if not G.LOG.exists():
        return []
    out = []
    for line in G.LOG.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        s = row.get("settled")
        if s and isinstance(s.get("net"), (int, float)):
            out.append(s)
    return out


def _equity(series: list) -> list:
    eq, v = [1.0], 1.0
    for x in series:
        v *= (1.0 + x)
        eq.append(v)
    return eq


def kill_check(settled: list) -> dict:
    """The pre-registered kill rule (prereg §6). Detection only; bot.run_cycle acts on it."""
    nets = [s["net"] for s in settled]
    n = len(nets)
    if n < 2:
        return {"halt": False, "verdict": "NO VERDICT", "reason": "insufficient sample"}
    m = S.moments(nets)
    t_net = m["mean"] / m["sd"] * math.sqrt(n) if m["sd"] else 0.0
    cum = math.prod(1.0 + x for x in nets) - 1.0
    dd = S.max_drawdown(_equity(nets))["max_drawdown"]
    if dd <= -G.DRAWDOWN_HALT:
        return {"halt": True, "verdict": "DEAD - DRAWDOWN",
                "reason": f"realised drawdown {dd:.1%} <= -{G.DRAWDOWN_HALT:.0%}"}
    if n >= G.KILL_MIN_N and cum < 0 and t_net <= G.KILL_T:
        return {"halt": True, "verdict": "DEAD - FORWARD-NEGATIVE",
                "reason": f"n={n} >= {G.KILL_MIN_N}, cum net {cum:.2%} < 0, t {t_net:.2f} <= {G.KILL_T}"}
    return {"halt": False, "verdict": "RUNNING", "reason": "no kill condition met"}


def score(settled: list) -> dict:
    """The honest scorecard. Sharpe/t/annualised figures are RESULTS only at n >= the verdict
    minimum; below it they are quarantined in `inputs_that_are_not_results`."""
    n = len(settled)
    hurdle = weekly_hurdle()
    doc = {
        "preregistration_sha256": G.PREREG_SHA,
        "paper_forward_test": True,
        "n_settled_weekly_obs": n,
        "verdict_minimum": G.VERDICT_MIN_N,
        "kill_minimum": G.KILL_MIN_N,
        "benchmarks": {
            "absolute_hurdle": f"T-bill {G.BENCH_TBILL_ANNUAL:.2%} + {G.BENCH_ALPHA_ANNUAL:.2%}/yr "
                               f"= {G.BENCH_TBILL_ANNUAL + G.BENCH_ALPHA_ANNUAL:.2%}/yr "
                               f"({hurdle*1e4:.2f} bp/wk)",
            "beta_isolation_null": "equal-weight broad CEF universe (buy-and-hold the CEF basket)",
        },
    }
    if n == 0:
        doc["verdict"] = "NO VERDICT - no settled observations yet"
        doc["note"] = "The bot has entered its inaugural book but nothing has completed its hold."
        return doc

    nets = [s["net"] for s in settled]
    gross = [s["gross"] for s in settled]
    alpha = [s["cross_sectional_alpha"] for s in settled]
    long_r = [s["long_ret"] for s in settled]
    uni_r = [s["universe_ret"] for s in settled]
    excess = [x - hurdle for x in nets]

    cum_net = math.prod(1.0 + x for x in nets) - 1.0
    cum_null = math.prod(1.0 + x for x in uni_r) - 1.0
    hit = sum(1 for x in nets if x > 0) / n
    beat_hurdle = sum(1 for x in excess if x > 0) / n
    beat_null = sum(1 for a in alpha if a > 0) / n
    dd = S.max_drawdown(_equity(nets))["max_drawdown"]
    kill = kill_check(settled)

    scorecard = {
        "cumulative_net_return": cum_net,
        "cumulative_buy_hold_cef_null": cum_null,
        "edge_over_null": cum_net - cum_null,
        "mean_net_bp_per_wk": (sum(nets) / n) * 1e4,
        "mean_gross_bp_per_wk": (sum(gross) / n) * 1e4,
        "mean_cross_sectional_alpha_bp_per_wk": (sum(alpha) / n) * 1e4,
        "mean_long_leg_bp_per_wk": (sum(long_r) / n) * 1e4,
        "mean_null_bp_per_wk": (sum(uni_r) / n) * 1e4,
        "hit_rate_net_positive": hit,
        "hit_rate_beat_hurdle": beat_hurdle,
        "hit_rate_long_beat_null": beat_null,
        "max_drawdown": dd,
    }

    if n >= 2:
        m = S.moments(nets)
        t_net = m["mean"] / m["sd"] * math.sqrt(n) if m["sd"] else 0.0
        stat_block = {
            "t_net": t_net,
            "ann_sharpe": S.annualised_sharpe(nets, G.WEEKS_PER_YEAR),
            "ann_sharpe_excess_of_hurdle": S.annualised_sharpe(excess, G.WEEKS_PER_YEAR),
            "skew": m["skew"], "kurtosis_non_excess": m["kurtosis"],
        }
    else:
        stat_block = {"note": "need >= 2 observations for a second moment"}

    # ---- verdict + the mandatory NO-VERDICT framing ----
    if kill["halt"]:
        doc["verdict"] = kill["verdict"]
        doc["verdict_reason"] = kill["reason"]
        doc["scorecard"] = scorecard
        doc["stats"] = stat_block
    elif n < G.VERDICT_MIN_N:
        doc["verdict"] = (f"NO VERDICT - {n}/{G.VERDICT_MIN_N} settled obs. Behaviour is not "
                          "evidence below the power floor; the CEF weekly instrument cannot "
                          "certify an annualised Sharpe below ~1.1-1.3 with fewer "
                          "(T12_PREREGISTRATION.md §3a).")
        doc["scorecard"] = scorecard
        doc["inputs_that_are_not_results"] = {
            "WARNING": ("These are NOT results. Sharpe/t/annualised figures on a short forward "
                        "sample are forbidden as claims (ITERATION_PROTOCOL.md §8.5). Shown for "
                        "operation only; they support no conclusion, in either direction."),
            **stat_block,
            "kill_watch": kill,
        }
    else:
        m = S.moments(nets)
        t_net = m["mean"] / m["sd"] * math.sqrt(n) if m["sd"] else 0.0
        survives = (m["mean"] > 0 and t_net >= S.norm_ppf(0.95)
                    and scorecard["mean_cross_sectional_alpha_bp_per_wk"] > 0)
        doc["verdict"] = "SURVIVES" if survives else "RUNNING - NOT ESTABLISHED"
        doc["scorecard"] = scorecard
        doc["stats"] = stat_block

    return doc


def report(as_json: bool = False) -> str:
    settled = read_settled()
    doc = score(settled)
    if as_json:
        return json.dumps(doc, indent=2, default=str)

    L = []
    L.append("=" * 74)
    L.append("CEFBOT -- CEF discount-LEVEL tilt, long-vs-market-hedge (PAPER FORWARD TEST)")
    L.append("=" * 74)
    L.append(f"pre-registration sha256 : {G.PREREG_SHA[:16]}...  (verified frozen)")
    L.append(f"settled weekly obs      : {doc['n_settled_weekly_obs']}  "
             f"(kill-min {G.KILL_MIN_N}, verdict-min {G.VERDICT_MIN_N})")
    L.append(f"absolute hurdle         : {doc['benchmarks']['absolute_hurdle']}")
    L.append(f"beta-isolation null     : {doc['benchmarks']['beta_isolation_null']}")
    L.append("-" * 74)
    sc = doc.get("scorecard")
    if sc:
        L.append(f"cumulative net return   : {sc['cumulative_net_return']:+.3%}")
        L.append(f"  buy-hold CEF null     : {sc['cumulative_buy_hold_cef_null']:+.3%}")
        L.append(f"  edge over null        : {sc['edge_over_null']:+.3%}")
        L.append(f"mean net / gross        : {sc['mean_net_bp_per_wk']:+.2f} / "
                 f"{sc['mean_gross_bp_per_wk']:+.2f} bp/wk")
        L.append(f"cross-sectional alpha   : {sc['mean_cross_sectional_alpha_bp_per_wk']:+.2f} bp/wk "
                 f"(long {sc['mean_long_leg_bp_per_wk']:+.2f} vs null "
                 f"{sc['mean_null_bp_per_wk']:+.2f})")
        L.append(f"hit rate (net>0)        : {sc['hit_rate_net_positive']:.1%}   "
                 f"beat hurdle {sc['hit_rate_beat_hurdle']:.1%}   "
                 f"long>null {sc['hit_rate_long_beat_null']:.1%}")
        L.append(f"max drawdown            : {sc['max_drawdown']:+.2%}")
    L.append("-" * 74)
    L.append(f"VERDICT: {doc['verdict']}")
    if doc.get("verdict_reason"):
        L.append(f"  reason: {doc['verdict_reason']}")
    if "inputs_that_are_not_results" in doc:
        b = doc["inputs_that_are_not_results"]
        L.append("  [inputs_that_are_not_results -- NOT a claim, operation only]")
        if "t_net" in b:
            L.append(f"    t_net {b['t_net']:+.2f}  annSR {b['ann_sharpe']:+.3f}  "
                     f"kill_watch: {b['kill_watch']['verdict']}")
    L.append("=" * 74)
    return "\n".join(L)
