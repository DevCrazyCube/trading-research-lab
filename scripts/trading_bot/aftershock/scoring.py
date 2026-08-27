#!/usr/bin/env python3
"""AFTERSHOCK scoring — POT GROWTH is the score; the unexitable-dump rate is a hard KILL-GATE, not the
score. PAPER, read-only.

The owner's frame: a bot with a 0% dump rate that loses a little every trade still drains the pot, so
the score must be pot growth, with an unsellable exit booked as a full economic loss. Fractional sizing
makes log-growth well-defined even for a full loss:

    g_i = ln(1 + f · r_i),   f = position_fraction (frozen), r_i = stressed_net_return in [-1, ∞)
    -> with f < 1, 1 + f·r_i >= 1 - f > 0, so a full loss is ln(1-f), bounded, never -∞.
    G = Σ g_i ;  pot_multiple = exp(G) ;  per_trade_growth = G / n.

Reuses memebot.scoring.kill_check on the g_i stream for the expectancy HALT (it operates on any numeric
list). Adds the dump-rate HALT: if AFTERSHOCK cannot even beat the raw B20B screen on unexitability
itself, its whole added machinery is worthless.
"""
from __future__ import annotations

import math

from scripts.trading_bot.memebot import scoring as _mscore


def _log_growths(resolved: list, f: float) -> list:
    """g_i = ln(1 + f·r_i) for each resolved PASS trade, r_i = stressed_net_return (unsellable -> -1)."""
    out = []
    for r in resolved:
        if r.get("control"):
            continue
        sr = r.get("stressed_net_return")
        if sr is None:
            continue
        sr = max(-1.0, float(sr))
        out.append(math.log(max(1e-12, 1.0 + f * sr)))
    return out


def _max_drawdown(gs: list) -> float:
    """Max fractional drawdown of the equity curve E_k = exp(Σ_{i<=k} g_i), starting at 1.0."""
    if not gs:
        return 0.0
    peak = 1.0
    equity = 1.0
    mdd = 0.0
    for g in gs:
        equity *= math.exp(g)
        peak = max(peak, equity)
        mdd = max(mdd, 1.0 - equity / peak)
    return mdd


def _cluster_concentration(resolved: list, f: float) -> dict:
    """HHI + top-1 share of |g_i| grouped by deployer (fallback mint): a G driven by one cluster is
    fragile. Reported as a robustness annotation only — never subtracted by a magic weight."""
    by = {}
    for r in resolved:
        if r.get("control") or r.get("stressed_net_return") is None:
            continue
        g = abs(math.log(max(1e-12, 1.0 + f * max(-1.0, float(r["stressed_net_return"])))))
        key = r.get("deployer") or r.get("pool_address") or r.get("name") or "?"
        by[key] = by.get(key, 0.0) + g
    total = sum(by.values())
    if total <= 0:
        return {"HHI": None, "top1_share": None, "n_clusters": len(by)}
    shares = [v / total for v in by.values()]
    return {"HHI": round(sum(s * s for s in shares), 4),
            "top1_share": round(max(shares), 4), "n_clusters": len(by)}


def score(spec: dict, resolved: list) -> dict:
    """Full pot-growth report. Everything below N_min is fenced under inputs_that_are_not_results."""
    f = float(spec.get("position_fraction", 0.02))
    ks = spec["kill_switch"]
    n_min = ks["N_min"]
    dump_max = float(spec.get("dump_rate_max", 0.13))

    gs = _log_growths(resolved, f)
    gs_ctrl = _log_growths([{**r, "control": False} for r in resolved if r.get("control")], f)
    n = len(gs)

    pass_records = [r for r in resolved if not r.get("control") and r.get("stressed_net_return") is not None]
    dumps = sum(1 for r in pass_records if r.get("unexitable") or float(r["stressed_net_return"]) <= -1.0 + 1e-9)
    dump_rate = (dumps / n) if n else None

    G = sum(gs)
    G_ctrl = sum(gs_ctrl)
    expectancy_gate = _mscore.kill_check(gs, spec)          # HALT on log-growth stream
    dump_gate = {"dump_rate": dump_rate, "dump_rate_max": dump_max, "verdict": "ALIVE"}
    if n >= n_min and dump_rate is not None and dump_rate >= dump_max:
        dump_gate["verdict"] = f"HALTED -- dump rate {dump_rate:.3f} >= {dump_max} (no better than raw B20B)"

    readable = n >= n_min
    verdict = ("NO VERDICT -- below the pre-registered minimum of "
               f"{n_min} resolved PASS trades. Behaviour, not evidence." if not readable
               else ("HALTED" if "HALTED" in expectancy_gate["verdict"] or "HALTED" in dump_gate["verdict"]
                     else "READABLE -- pot growth is a result at n>=N_min"))

    result = {
        "instrument_id": spec["instrument_id"],
        "freeze_utc": spec.get("frozen_utc"),
        "resolved_pass_trades": n,
        "minimum_before_verdict": n_min,
        "readable": readable,
        "verdict": verdict,
        "kill_switch": {"expectancy_gate": expectancy_gate, "dump_gate": dump_gate},
        "status_line": None,
    }
    body = {
        "log_growth_G": round(G, 5),
        "pot_multiple": round(math.exp(G), 5),
        "per_trade_growth": round(G / n, 6) if n else None,
        "max_drawdown": round(_max_drawdown(gs), 4),
        "cluster_concentration": _cluster_concentration(resolved, f),
        "dump": {"dump_rate": dump_rate, "unexitable_dumps": dumps, "pass_resolved": n},
        "control_null": {
            "G_control": round(G_ctrl, 5), "n_control": len(gs_ctrl),
            # Per-TRADE edge (review #7): differencing raw sums over different n confounds edge with
            # sample size. The comparable quantity is per-trade log-growth PASS minus CONTROL.
            "per_trade_growth_pass": round(G / n, 6) if n else None,
            "per_trade_growth_control": round(G_ctrl / len(gs_ctrl), 6) if gs_ctrl else None,
            "edge_per_trade": (round(G / n - G_ctrl / len(gs_ctrl), 6)
                               if (n and gs_ctrl) else None),
        },
        "position_fraction": f,
    }
    if readable:
        result.update(body)
    else:
        result["inputs_that_are_not_results"] = body
    growth_seg = (f"potG {round(G,4)} x{round(math.exp(G),3)}" if readable
                  else f"[not a result] potG {round(G,4)} x{round(math.exp(G),3)}")  # review #16
    result["status_line"] = (
        f"AFTERSHOCK PAPER (no orders/wallet/SOL) | resolved PASS {n}/{n_min} -> "
        f"{'READABLE' if readable else 'NO VERDICT'} | {growth_seg} | "
        f"dump {dump_rate if dump_rate is None else round(dump_rate,3)} ({dump_gate['verdict'].split(' ')[0]}) | "
        f"kill {expectancy_gate['verdict'].split(' ')[0]}")
    return result
