#!/usr/bin/env python3
"""Honest scoring -- EXPECTANCY is the metric, win-rate is not. Mirror of basket_eval / newsdesk.

Over the realised-R stream it computes win-rate, avg-win R, avg-loss R, and
EXPECTANCY = winrate*avgWinR - lossrate*avgLossR, then benchmarks the SCREEN=PASS trades against the
CONTROL trades (the same sizing/stop/target on coins the screen REJECTED -- the random/unscreened
null the task asks for) and against zero, and applies the frozen kill switch: HALT if, after
n>=N_min resolved PASS trades, the one-sided upper 95% bound on mean R is below zero.

Every number computed before N_min sits inside `inputs_that_are_not_results`, fenced so it cannot be
lifted out as an edge. Read-only over the logs.
"""

from __future__ import annotations

import math
import statistics


def _expectancy(rs: list) -> dict:
    n = len(rs)
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r <= 0]
    return {
        "n": n,
        "win_rate": len(wins) / n if n else 0.0,
        "loss_rate": len(losses) / n if n else 0.0,
        "avg_win_R": statistics.fmean(wins) if wins else 0.0,
        "avg_loss_R": statistics.fmean([abs(r) for r in losses]) if losses else 0.0,
        "expectancy_R": (len(wins) / n * statistics.fmean(wins) if wins else 0.0)
                        - (len(losses) / n * statistics.fmean([abs(r) for r in losses]) if losses else 0.0)
                        if n else 0.0,
        "mean_R": statistics.fmean(rs) if rs else None,
        "cum_R": sum(rs),
    }


def kill_check(rs: list, spec: dict) -> dict:
    """Frozen HALT rule on the realised-R stream of SCREEN=PASS trades."""
    ks = spec["kill_switch"]
    n = len(rs)
    out = {"n": n, "N_min": ks["N_min"], "rule": ks["rule"], "verdict": "ALIVE"}
    if n < 2:
        out["reason_not_evaluable"] = "need >=2 resolved trades for a standard error"
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
    """Full honest scorecard. `resolved` is the de-duplicated realised-R stream (PASS + control)."""
    from .frozen import FRAMING
    passed = [r["realized_r"] for r in resolved if not r.get("control")]
    control = [r["realized_r"] for r in resolved if r.get("control")]
    full_loss_r = (-1.0 - 2.0 * float(spec["toll_per_side"])) / float(spec["stop_frac"])
    stressed_pass = [
        full_loss_r if r.get("resolution_reason") == "UNEXITABLE_TIMEOUT" else r["realized_r"]
        for r in resolved if not r.get("control")
    ]
    stressed_control = [
        full_loss_r if r.get("resolution_reason") == "UNEXITABLE_TIMEOUT" else r["realized_r"]
        for r in resolved if r.get("control")
    ]
    n = len(passed)
    minimum = spec["kill_switch"]["N_min"]
    kill = kill_check(passed, spec)                 # frozen commitment on the generous -25% mark (kept)
    honest_kill = kill_check(stressed_pass, spec)   # the DECIDER: full-loss stress on the unexitable tail

    report = {
        "framing": FRAMING,
        "instrument_id": spec["instrument_id"],
        "freeze_utc": spec["frozen_utc"],
        "resolved_pass_trades": n,
        "resolved_control_trades": len(control),
        "minimum_before_verdict": minimum,
        "readable": n >= minimum,
        "verdict": ("NO VERDICT -- below the pre-registered minimum of "
                    f"{minimum} resolved PASS trades. Behaviour, not evidence."
                    if n < minimum else "MINIMUM MET -- read the expectancy gate vs the control null."),
        "kill_switch": kill,
        "benchmarks_definition": spec["benchmarks"],
        # The HONEST DECIDER. The frozen resolution convention marks an UNEXITABLE_TIMEOUT at the -25%
        # stop floor, but on-chain autopsy proved these coins drain to ~0 (real -64% to -100%), so that
        # mark FLATTERS every variant. This re-marks the unexitable tail at full loss (-100%) at SCORING
        # time (never touching the frozen forward log) and is the number the edge is adjudicated on.
        "decider": "full_loss_stress",
        "full_loss_stress": {
            "assumption": ("UNEXITABLE_TIMEOUT valued at -100% before pinned toll; conservative bound, "
                           "not a claim that every unavailable mark was literally zero"),
            "full_loss_R": full_loss_r,
            "screen_pass": _expectancy(stressed_pass),
            "control_null": _expectancy(stressed_control),
            "expectancy_edge_over_null_R": (_expectancy(stressed_pass)["expectancy_R"]
                                            - _expectancy(stressed_control)["expectancy_R"]),
            "honest_kill_switch": honest_kill,
            "changes_frozen_kill_rule": False,
        },
        "honest_verdict": (
            f"NO VERDICT -- below the {minimum}-trade minimum. Behaviour, not evidence." if n < minimum
            else ("HALTED (honest) -- full-loss-stress expectancy upper-95 < 0" if honest_kill["verdict"].startswith("HALTED")
                  else "HONEST-ALIVE -- stress expectancy not yet significantly negative; a positive "
                       "stress edge over the null is required to license the edge")),
    }
    if n >= 1 or control:
        scr = _expectancy(passed)
        null = _expectancy(control)
        edge = scr["expectancy_R"] - null["expectancy_R"]
        report["inputs_that_are_not_results"] = {
            "DISCLAIMER": ("NOT RESULTS. No expectancy verdict is licensed before the "
                           f"{minimum}-trade minimum; shown so the kill switch can be audited, the "
                           "power sized, and the screen-vs-null gap tracked -- fenced so it cannot be "
                           "lifted out as an edge. Honest prior: ~0 or negative."),
            "screen_pass": scr,
            "control_null_rejected_coins": null,
            "expectancy_edge_of_screen_over_null_R": edge,
            "screen_expectancy_beats_zero": scr["expectancy_R"] > 0,
            "screen_expectancy_beats_null": edge > 0,
            "resolution_reason_counts": _reasons(resolved),
        }
    report["status_line"] = status_line(report)
    return report


def honest_entry_gate(report: dict) -> dict:
    """Turn the displayed honest kill decision into an executable paper-entry gate.

    Tracking/resolution remains enabled so already-open paper positions finish normally. Only NEW
    PASS/control entries stop. Keeping this pure makes the safety decision hermetically testable and
    prevents the scanner from quietly treating a red dashboard badge as decoration.
    """
    verdict = str(
        report.get("full_loss_stress", {})
        .get("honest_kill_switch", {})
        .get("verdict", "")
    )
    halted = verdict.startswith("HALTED")
    return {
        "allow_new_entries": not halted,
        "reason": (
            "HONEST_KILL_HALTED_NO_NEW_ENTRIES" if halted
            else "HONEST_KILL_ALIVE_OR_NOT_YET_EVALUABLE"
        ),
        "verdict": verdict,
    }


def _reasons(resolved: list) -> dict:
    counts = {}
    for r in resolved:
        key = ("control:" if r.get("control") else "pass:") + r.get("resolution_reason", "?")
        counts[key] = counts.get(key, 0) + 1
    return counts


def status_line(report: dict) -> str:
    n = report["resolved_pass_trades"]
    honest = report.get("full_loss_stress", {})
    honest_kill = honest.get("honest_kill_switch", {}).get("verdict", "?").split("--")[0].strip()
    tail = ""
    inp = report.get("inputs_that_are_not_results")
    if inp:
        stress = honest.get("screen_pass", {}).get("expectancy_R")
        se = honest.get("expectancy_edge_over_null_R")
        gen = inp["screen_pass"]["expectancy_R"]                 # the generous -25% mark, now secondary
        tail = (f" | [not a result] stress {stress:+.3f}R (DECIDER), stress-edge vs null {se:+.3f}R"
                f" | generous {gen:+.3f}R (-25% mark)")
    return (f"{report['instrument_id']} PAPER (no orders/wallet/SOL) | resolved PASS {n}/"
            f"{report['minimum_before_verdict']} -> {report['verdict'].split('--')[0].strip()} "
            f"| honest-kill {honest_kill}{tail}")
