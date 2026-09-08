#!/usr/bin/env python3
"""AFTERSHOCK V4 — PROFIT-LOCK resolver. PAPER, read-only.

Trails the executable full-position quote (like V2 arm C / V3 arm A) and adds a ONE-WAY profit floor: once
the quote has gone clearly green (peak >= lock_arm), a green trade may not exit below lock_floor. The
floor is a FIXED quote level, not a proportional trail, so a runner peaking well above the floor exits on
the 12% trail untouched; only a trade fading back toward break-even is caught at a small locked profit.
This targets the V2/V3 failure mode: 71% of losers went green then round-tripped to a loss.

  A trail          : quote <= (1 - trail_frac)*peak
  B/C trail+lock   : A, plus (armed AND quote <= lock_floor) -> PROFIT_LOCK
Base exits (all): capacity break, cluster resume, hard horizon. Single full exit; pricing identical to V1-V3.
"""
from __future__ import annotations

import time

from . import ecr
from .detector import SLOT_SECONDS
from .resolve import _price_usd
from .resolve_v2 import _exit_quote_value
from scripts.trading_bot.memebot import paper as _mpaper


def resolve_from_tape_v4(setup: dict, tape_lines: list, spec: dict, arm: dict,
                         now: float | None = None) -> dict | None:
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
    use_lock = bool((arm or {}).get("profit_lock"))
    lock_arm = arm.get("lock_arm") if use_lock else None
    lock_floor = arm.get("lock_floor") if use_lock else None

    peak = _exit_quote_value(entry_reserves, entry_reserves, q_sol)
    prev_R = ecr.real_quote_sol(entry_reserves)
    armed = False

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
        if quote > peak:
            peak = quote
        if use_lock and lock_arm is not None and peak >= lock_arm:
            armed = True

        # ---- exits, in the FROZEN prereg precedence (same exit line whichever fires; order sets only the
        #      resolution_reason label — an unsellable line is relabeled UNEXITABLE_TIMEOUT below regardless) ----
        # one-way profit floor: a green trade may not bleed below the locked level
        if armed and lock_floor is not None and quote <= lock_floor:
            exit_line, reason = ln, "PROFIT_LOCK"; break
        # trailing exit for the runner
        if peak > 0 and quote <= (1.0 - trail) * peak:
            exit_line, reason = ln, "QUOTE_TRAIL"; break
        if quote <= 0.0 or ecr.coverage_ratio(ln, q_sol) < cov_buffer:
            exit_line, reason = ln, "CAPACITY_BREAK"; break
        if side == "sell" and trader in cluster and prev_R > 0 and sol >= resume_frac * prev_R:
            exit_line, reason = ln, "CLUSTER_RESUME"; break
        if ts >= t_entry + max_hold_s:
            exit_line, reason = ln, "MAX_HOLD"; break

        prev_R = R_now

    if exit_line is None:
        if tape_lines and now >= t_entry + max_hold_s:
            exit_line, reason = tape_lines[-1], "MAX_HOLD"
        else:
            return None

    held_min = (float(exit_line["ts"]) - t_entry) / 60.0
    stressed = ecr.ecr_roundtrip(entry_reserves, exit_line, q_sol)
    if stressed["unexitable"]:
        reason = "UNEXITABLE_TIMEOUT"

    entry_price = _price_usd(entry_reserves) or setup.get("entry_price_usd") or 1.0
    exit_price = _price_usd(exit_line) or entry_price
    record = _mpaper._resolution_record(setup, exit_price, reason, held_min, "aftershock_v4_tape")
    record.update({
        "stressed_net_return": round(stressed["stressed_net_return"], 6),
        "stressed_ecr": round(stressed["stressed_ecr"], 6),
        "unexitable": bool(stressed["unexitable"]),
        "deployer": setup.get("deployer"),
        "exit_reserves": {"v_sol": exit_line.get("v_sol"), "v_tokens": exit_line.get("v_tokens"),
                          "pool": exit_line.get("pool")},
    })
    return record
