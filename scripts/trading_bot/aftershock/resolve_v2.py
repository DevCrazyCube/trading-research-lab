#!/usr/bin/env python3
"""AFTERSHOCK V2 resolver — arm-aware. PAPER, read-only.

Arms A and B use V1's exit unchanged (delegates to resolve.resolve_from_tape). Arm C uses the
executable-full-position QUOTE trail: the trail is applied to ExitQuote(q,t) — the curve-exact net SOL
proceeds of selling the WHOLE position right now (via the ECR kernel from the frozen entry reserves) —
instead of chart price, and the churny routine FLOW_FLIP exit is dropped in favour of capacity/emergency
exits only. Pricing of the realised exit is identical to V1 (ecr_roundtrip at the exit tick), so the
ledger/scoring read it unchanged.
"""
from __future__ import annotations

import time

from . import ecr
from .detector import SLOT_SECONDS
from .resolve import resolve_from_tape, _price_usd
from scripts.trading_bot.memebot import paper as _mpaper


def _exit_quote_value(entry_reserves: dict, line: dict, q_sol: float) -> float:
    """ExitQuote as a VALUE proportional to net proceeds of selling the full position now: (1 + stressed
    round-trip return). Unsellable curve -> 0.0 (capacity collapse). Cost is fixed, so this is a faithful
    monotone proxy for the executable sell proceeds and the right thing to trail on."""
    rt = ecr.ecr_roundtrip(entry_reserves, line, q_sol)
    if rt.get("unexitable"):
        return 0.0
    return 1.0 + float(rt["stressed_net_return"])


def resolve_from_tape_c(setup: dict, tape_lines: list, spec: dict, now: float | None = None) -> dict | None:
    """Arm C: capacity/emergency exits + 12% trail on the executable full-position quote. Returns a
    resolution record, or None if still open."""
    if now is None:
        now = time.time()
    ex = spec["exit"]
    q_sol = float(setup.get("q_sol") or spec["detector"]["q_sol"])
    cluster = set(setup.get("cluster_wallets") or [])
    t_entry = float(setup.get("t_entry") or (tape_lines[0]["ts"] if tape_lines else 0.0))
    entry_reserves = setup["entry_reserves"]

    max_hold_s = ex["max_hold_slots"] * SLOT_SECONDS
    trail = float(ex["trail_frac"])
    cov_buffer = float(ex["coverage_exit_buffer"])
    resume_frac = float(ex["cluster_resume_frac_of_R"])

    peak_quote = _exit_quote_value(entry_reserves, entry_reserves, q_sol)  # value at entry (~1.0 minus toll)
    prev_R = ecr.real_quote_sol(entry_reserves)

    exit_line = None
    reason = None
    for ln in tape_lines:
        ts = float(ln["ts"])
        if ts < t_entry:
            continue
        side = ln.get("side")
        trader = ln.get("trader")
        sol = float(ln.get("sol_amount") or 0.0)
        R_now = ecr.real_quote_sol(ln)

        quote = _exit_quote_value(entry_reserves, ln, q_sol)
        if quote > peak_quote:
            peak_quote = quote

        # ---- capacity/emergency exits + quote trail (NO routine FLOW_FLIP) ----
        # 1) EMERGENCY / capacity collapse: the curve can no longer pay the position out.
        if quote <= 0.0 or ecr.coverage_ratio(ln, q_sol) < cov_buffer:
            exit_line, reason = ln, "CAPACITY_BREAK"; break
        # 2) CLUSTER RESUME: a cluster wallet resumes distributing materially.
        if side == "sell" and trader in cluster and prev_R > 0 and sol >= resume_frac * prev_R:
            exit_line, reason = ln, "CLUSTER_RESUME"; break
        # 3) QUOTE TRAIL: the executable full-position sell value gave back trail_frac from its peak.
        if peak_quote > 0 and quote <= (1.0 - trail) * peak_quote:
            exit_line, reason = ln, "QUOTE_TRAIL"; break
        # 4) MAX HOLD: liveness backstop.
        if ts >= t_entry + max_hold_s:
            exit_line, reason = ln, "MAX_HOLD"; break

        prev_R = R_now

    if exit_line is None:
        if tape_lines and now >= t_entry + max_hold_s:
            exit_line, reason = tape_lines[-1], "MAX_HOLD"
        else:
            return None   # still open

    held_min = (float(exit_line["ts"]) - t_entry) / 60.0
    stressed = ecr.ecr_roundtrip(entry_reserves, exit_line, q_sol)
    if stressed["unexitable"]:
        reason = "UNEXITABLE_TIMEOUT"

    entry_price = _price_usd(entry_reserves) or setup.get("entry_price_usd") or 1.0
    exit_price = _price_usd(exit_line) or entry_price
    record = _mpaper._resolution_record(setup, exit_price, reason, held_min, "aftershock_v2_tape")
    record.update({
        "stressed_net_return": round(stressed["stressed_net_return"], 6),
        "stressed_ecr": round(stressed["stressed_ecr"], 6),
        "unexitable": bool(stressed["unexitable"]),
        "deployer": setup.get("deployer"),
        "exit_reserves": {"v_sol": exit_line.get("v_sol"), "v_tokens": exit_line.get("v_tokens"),
                          "pool": exit_line.get("pool")},
    })
    return record


def resolve_from_tape_v2(setup: dict, tape_lines: list, spec: dict, arm: dict,
                         now: float | None = None) -> dict | None:
    """Arm-aware resolve. Arms A/B -> V1 exit; arm C -> executable-quote trail."""
    exit_kind = (arm or {}).get("exit", "v1_existing")
    if exit_kind == "v2_capacity_and_quote_trail":
        return resolve_from_tape_c(setup, tape_lines, spec, now=now)
    return resolve_from_tape(setup, tape_lines, spec, now=now)
