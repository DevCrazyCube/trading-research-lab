#!/usr/bin/env python3
"""Honest scoring -- mirror of basket_eval. EXPECTANCY is the metric, win-rate is not.

Over the stream of realised R-multiples it computes win-rate, avg-win R, avg-loss R and
EXPECTANCY = winrate*avgWinR - lossrate*avgLossR, benchmarks that against zero and against the
same-instrument RANDOM-DIRECTION null, and applies the frozen kill switch (HALT if, after n>=N_min
resolved setups, the one-sided upper 95% bound on mean R is below zero).

Every number computed before the N_min minimum travels inside `inputs_that_are_not_results` with the
reason it is not evidence -- the same fence BASKET1 uses. This module is READ-ONLY over the logs.
"""

from __future__ import annotations

import math
import statistics


def _expectancy(rs: list) -> dict:
    n = len(rs)
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r <= 0]
    win_rate = len(wins) / n if n else 0.0
    loss_rate = len(losses) / n if n else 0.0
    avg_win = statistics.fmean(wins) if wins else 0.0
    avg_loss = statistics.fmean([abs(r) for r in losses]) if losses else 0.0
    expectancy = win_rate * avg_win - loss_rate * avg_loss
    return {"n": n, "win_rate": win_rate, "loss_rate": loss_rate,
            "avg_win_R": avg_win, "avg_loss_R": avg_loss, "expectancy_R": expectancy,
            "mean_R": statistics.fmean(rs) if rs else None}


def kill_check(rs: list, spec: dict) -> dict:
    """Frozen HALT rule on the realised-R stream (mirror of basket_forward.kill_check)."""
    ks = spec["kill_switch"]
    n = len(rs)
    out = {"n": n, "N_min": ks["N_min"], "rule": ks["rule"], "verdict": "ALIVE"}
    if n < 2:
        out["reason_not_evaluable"] = "need >=2 resolved setups for a standard error"
        return out
    mean = statistics.fmean(rs)
    sd = statistics.stdev(rs)
    se = sd / math.sqrt(n)
    upper95 = mean + 1.645 * se
    out.update({"mean_R": mean, "se": se, "one_sided_upper_95_bound": upper95,
                "t_stat": (mean / se) if se > 0 else None})
    if n >= ks["N_min"] and upper95 < 0:
        out["verdict"] = "HALTED -- significantly negative forward expectancy"
    elif n < ks["N_min"]:
        out["verdict"] = f"ALIVE -- kill not evaluable below N_min={ks['N_min']} (n={n})"
    return out


def score(spec: dict, resolved: list) -> dict:
    """Full honest scorecard over the resolved-R stream. Returns a read-only report dict."""
    from .frozen import FRAMING
    real = [r["realized_r"] for r in resolved if r.get("realized_r") is not None]
    null = [r["null_realized_r"] for r in resolved if r.get("null_realized_r") is not None]
    n = len(real)
    minimum = spec["kill_switch"]["N_min"]
    kill = kill_check(real, spec)

    report = {
        "framing": FRAMING,
        "instrument_id": spec["instrument_id"],
        "freeze_utc": spec["frozen_utc"],
        "resolved_setups": n,
        "minimum_before_verdict": minimum,
        "readable": n >= minimum,
        "verdict": ("NO VERDICT -- below the pre-registered minimum of "
                    f"{minimum} resolved setups. Behaviour, not evidence."
                    if n < minimum else "MINIMUM MET -- read the expectancy gate vs the null."),
        "kill_switch": kill,
        "benchmarks_definition": spec["benchmarks"],
    }
    if n >= 1:
        agent = _expectancy(real)
        rand = _expectancy(null)
        edge_vs_null = (agent["expectancy_R"] - rand["expectancy_R"])
        report["inputs_that_are_not_results"] = {
            "DISCLAIMER": ("NOT RESULTS. No expectancy verdict is licensed before the "
                           f"{minimum}-setup minimum; shown so the kill switch can be audited and the "
                           "power sized, fenced so it cannot be lifted out as an edge."),
            "agent_read": agent,
            "random_direction_null": rand,
            "expectancy_edge_over_null_R": edge_vs_null,
            "expectancy_beats_zero": agent["expectancy_R"] > 0,
            "expectancy_beats_null": edge_vs_null > 0,
            "cum_R_agent": sum(real), "cum_R_null": sum(null),
            "per_reason_counts": _reasons(resolved),
        }
    report["status_line"] = status_line(report)
    return report


def _reasons(resolved: list) -> dict:
    counts = {}
    for r in resolved:
        counts[r.get("resolution_reason", "?")] = counts.get(r.get("resolution_reason", "?"), 0) + 1
    return counts


def status_line(report: dict) -> str:
    n = report["resolved_setups"]
    k = report["kill_switch"]["verdict"].split("--")[0].strip()
    tail = ""
    inp = report.get("inputs_that_are_not_results")
    if inp:
        a = inp["agent_read"]["expectancy_R"]
        e = inp["expectancy_edge_over_null_R"]
        tail = f" | [not a result] expectancy {a:+.3f}R, edge vs null {e:+.3f}R"
    return (f"NEWSDESK1 PAPER-LOGGER (no orders) | resolved {n}/{report['minimum_before_verdict']} "
            f"-> {report['verdict'].split('--')[0].strip()} | kill {k}{tail}")
