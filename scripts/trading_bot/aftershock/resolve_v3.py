#!/usr/bin/env python3
"""AFTERSHOCK V3 — QUOTE-HARVEST resolver. PAPER, read-only.

All arms trail the executable full-position quote `ExitQuote(q,t)` = curve-exact net proceeds of selling
the WHOLE position now (ECR, stressed; 0 if unsellable). quote=1.0 is cost-recovered break-even, >1 is
net profit. `peak` = highest quote since entry. Arms differ only by the exit rule:

  A trail    : exit when quote <= (1 - trail_frac) * peak                                 (12%, = V2 arm C)
  B ratchet  : A, but once peak has reached (1 + ratchet_arm_profit) the trail TIGHTENS to
               ratchet_trail_frac to lock the gain                                        (5% after +10%)
  C rollover : B, plus once armed and past the peak, exit on rollover_confirm_ticks consecutive lower
               quotes (a confirmed lower-high) -- harvest at the roll-over, not the full give-back

Base exits (all arms): capacity break (quote<=0 or coverage<buffer), cluster resume, hard horizon. Single
full exit. Pricing of the realised exit is identical to V1/V2 (ecr_roundtrip at the exit tick).
"""
from __future__ import annotations

import time

from . import ecr
from .detector import SLOT_SECONDS
from .resolve import _price_usd
from .resolve_v2 import _exit_quote_value
from scripts.trading_bot.memebot import paper as _mpaper


def resolve_from_tape_v3(setup: dict, tape_lines: list, spec: dict, arm: dict,
                         now: float | None = None) -> dict | None:
    """Resolve ONE open V3 position under the arm's exit mode. None if still open."""
    if now is None:
        now = time.time()
    ex = spec["exit"]
    mode = (arm or {}).get("exit_mode", "trail")
    q_sol = float(setup.get("q_sol") or spec["detector"]["q_sol"])
    cluster = set(setup.get("cluster_wallets") or [])
    t_entry = float(setup.get("t_entry") or (tape_lines[0]["ts"] if tape_lines else 0.0))
    entry_reserves = setup["entry_reserves"]

    max_hold_s = ex["max_hold_slots"] * SLOT_SECONDS
    base_trail = float(ex["trail_frac"])
    tight_trail = float(ex["ratchet_trail_frac"])
    arm_profit = float(ex["ratchet_arm_profit"])
    rollover_ticks = int(ex["rollover_confirm_ticks"])
    cov_buffer = float(ex["coverage_exit_buffer"])
    resume_frac = float(ex["cluster_resume_frac_of_R"])

    entry_quote = _exit_quote_value(entry_reserves, entry_reserves, q_sol)
    peak = entry_quote
    prev_quote = entry_quote
    prev_R = ecr.real_quote_sol(entry_reserves)
    armed = False        # ratchet/rollover: peak has reached the profit threshold
    down_ticks = 0

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
        # Arm per the FROZEN prereg: ExitQuote peak >= (1 + arm_profit) * entry_quote, i.e. the position
        # is arm_profit ABOVE its entry value. (entry_quote < 1.0 always — the round-trip fee drag — so an
        # absolute 1.10 would arm strictly later than the spec and defeat arms B/C on modest-peak trades.)
        if mode in ("ratchet", "rollover") and peak >= (1.0 + arm_profit) * entry_quote:
            armed = True
        # rollover momentum bookkeeping
        if quote < prev_quote:
            down_ticks += 1
        elif quote > prev_quote:
            down_ticks = 0

        # ---- exits ----
        # 1) capacity / emergency
        if quote <= 0.0 or ecr.coverage_ratio(ln, q_sol) < cov_buffer:
            exit_line, reason = ln, "CAPACITY_BREAK"; break
        # 2) cluster resume
        if side == "sell" and trader in cluster and prev_R > 0 and sol >= resume_frac * prev_R:
            exit_line, reason = ln, "CLUSTER_RESUME"; break
        # 3) rollover harvest (arm C only): confirmed lower-high once armed
        if mode == "rollover" and armed and down_ticks >= rollover_ticks and quote < peak:
            exit_line, reason = ln, "ROLLOVER"; break
        # 4) quote trail (tightened once armed for ratchet/rollover)
        eff_trail = tight_trail if (armed and mode in ("ratchet", "rollover")) else base_trail
        if peak > 0 and quote <= (1.0 - eff_trail) * peak:
            exit_line, reason = ln, ("RATCHET_TRAIL" if (armed and mode != "trail") else "QUOTE_TRAIL"); break
        # 5) hard horizon
        if ts >= t_entry + max_hold_s:
            exit_line, reason = ln, "MAX_HOLD"; break

        prev_quote = quote
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
    record = _mpaper._resolution_record(setup, exit_price, reason, held_min, "aftershock_v3_tape")
    record.update({
        "stressed_net_return": round(stressed["stressed_net_return"], 6),
        "stressed_ecr": round(stressed["stressed_ecr"], 6),
        "unexitable": bool(stressed["unexitable"]),
        "deployer": setup.get("deployer"),
        "exit_reserves": {"v_sol": exit_line.get("v_sol"), "v_tokens": exit_line.get("v_tokens"),
                          "pool": exit_line.get("pool")},
    })
    return record
