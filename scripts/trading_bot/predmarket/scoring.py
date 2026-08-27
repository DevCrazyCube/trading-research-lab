#!/usr/bin/env python3
"""Honest scoring -- CALIBRATION (agent Brier vs market Brier) is the metric; P&L is secondary.

PRIMARY: over the resolved stream, compute mean Brier for the agent and for the market, and the PAIRED
difference d_i = brier_market_i - brier_agent_i (d>0 means the agent beat the market on market i). The
agent has a demonstrated calibration edge iff, after n>=N_min resolved markets, the one-sided lower 95%
bound on mean(d) is ABOVE zero: mean(d) - 1.645*se(d) > 0.

KILL SWITCH (frozen): HALT if, after n>=N_min, the agent's mean Brier is NOT below the market's at
one-sided 95% -- i.e. mean(d) - 1.645*se(d) <= 0. The agent must PROVE it beats the crowd or it halts.

SECONDARY (noisy, confirming only): mean hypothetical P&L net of fees on the bet-eligible subset, and a
bucketed calibration curve. Every number before N_min travels inside `inputs_that_are_not_results`.
READ-ONLY over the logs.
"""

from __future__ import annotations

import math
import statistics


def _mean_se(xs: list):
    n = len(xs)
    if n == 0:
        return None, None, 0
    mean = statistics.fmean(xs)
    se = (statistics.stdev(xs) / math.sqrt(n)) if n >= 2 else None
    return mean, se, n


def kill_check(resolved: list, spec: dict) -> dict:
    """Frozen HALT rule on the paired Brier-difference stream."""
    ks = spec["kill_switch"]
    d = [r["brier_market"] - r["brier_agent"] for r in resolved]
    n = len(d)
    out = {"n": n, "N_min": ks["N_min"], "rule": ks["rule"], "verdict": "ALIVE"}
    if n < 2:
        out["reason_not_evaluable"] = "need >=2 resolved markets for a standard error"
        return out
    mean, se, _ = _mean_se(d)
    lower95 = mean - 1.645 * se
    out.update({"mean_brier_edge": round(mean, 6), "se": round(se, 6),
                "one_sided_lower_95_bound": round(lower95, 6),
                "t_stat": (round(mean / se, 4) if se and se > 0 else None)})
    if n >= ks["N_min"] and lower95 <= 0:
        out["verdict"] = "HALTED -- agent Brier not significantly below market Brier at N_min"
    elif n < ks["N_min"]:
        out["verdict"] = f"ALIVE -- kill not evaluable below N_min={ks['N_min']} (n={n})"
    else:
        out["verdict"] = "ALIVE -- agent Brier significantly below market Brier"
    return out


def _calibration_buckets(resolved: list) -> list:
    edges = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0001]
    buckets = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        rows = [r for r in resolved if lo <= r["q_agent"] < hi]
        if not rows:
            continue
        buckets.append({"bucket": f"[{lo:.1f},{min(hi,1.0):.1f})", "n": len(rows),
                        "mean_q_agent": round(statistics.fmean(r["q_agent"] for r in rows), 4),
                        "realized_yes_freq": round(statistics.fmean(r["yes_outcome"] for r in rows), 4)})
    return buckets


def score(spec: dict, resolved: list) -> dict:
    from .frozen import FRAMING
    n = len(resolved)
    minimum = spec["kill_switch"]["N_min"]
    kill = kill_check(resolved, spec)

    report = {
        "framing": FRAMING,
        "instrument_id": spec["instrument_id"],
        "freeze_utc": spec["frozen_utc"],
        "resolved_markets": n,
        "minimum_before_verdict": minimum,
        "readable": n >= minimum,
        "primary_metric": "calibration: agent Brier vs market Brier (lower is better)",
        "verdict": ("NO VERDICT -- below the pre-registered minimum of "
                    f"{minimum} resolved markets. Behaviour, not evidence."
                    if n < minimum else
                    "MINIMUM MET -- read the paired Brier gate."),
        "kill_switch": kill,
        "benchmarks_definition": spec["benchmarks"],
    }
    if n >= 1:
        ba, _, _ = _mean_se([r["brier_agent"] for r in resolved])
        bm, _, _ = _mean_se([r["brier_market"] for r in resolved])
        bets = [r["hypothetical_pnl_net_fee"] for r in resolved
                if r.get("hypothetical_pnl_net_fee") is not None]
        pnl_mean, pnl_se, n_bets = _mean_se(bets)
        report["inputs_that_are_not_results"] = {
            "DISCLAIMER": ("NOT RESULTS. No calibration verdict is licensed before the "
                           f"{minimum}-market minimum; shown so the kill switch can be audited and the "
                           "power sized, fenced so it cannot be lifted out as an edge."),
            "mean_brier_agent": round(ba, 6),
            "mean_brier_market": round(bm, 6),
            "agent_beats_market_brier": (ba is not None and bm is not None and ba < bm),
            "brier_edge_mean": (round(bm - ba, 6) if ba is not None else None),
            "n_hypothetical_bets": n_bets,
            "n_abstentions_among_resolved": n - n_bets,
            "hypothetical_pnl_net_fee_mean": (round(pnl_mean, 4) if pnl_mean is not None else None),
            "hypothetical_pnl_positive": (pnl_mean is not None and pnl_mean > 0),
            "calibration_curve": _calibration_buckets(resolved),
        }
    report["status_line"] = status_line(report)
    return report


def status_line(report: dict) -> str:
    n = report["resolved_markets"]
    k = report["kill_switch"]["verdict"].split("--")[0].strip()
    tail = ""
    inp = report.get("inputs_that_are_not_results")
    if inp:
        ba, bm = inp["mean_brier_agent"], inp["mean_brier_market"]
        tail = (f" | [not a result] Brier agent {ba:.4f} vs market {bm:.4f}"
                f" (edge {inp['brier_edge_mean']:+.4f})")
    return (f"PREDMARKET1 CALIBRATION TRACKER (no bets) | resolved {n}/{report['minimum_before_verdict']} "
            f"-> {report['verdict'].split('--')[0].strip()} | kill {k}{tail}")
