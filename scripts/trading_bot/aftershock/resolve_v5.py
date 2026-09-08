#!/usr/bin/env python3
"""AFTERSHOCK V5 — SCALE-OUT resolver. PAPER, read-only.

Two-leg partial exit. Leg 1 sells `scale_frac` of the position at the FIRST tick whose executable quote
reaches `tp_level` (banking a gap-proof gain); leg 2 rides the remaining (1 - scale_frac) on the 12%
quote-trail (plus the base capacity / cluster-resume / horizon exits), exactly like the plain trail. The
realised return is the fraction-weighted blend of the two legs:

    R = scale_frac * R(leg1) + (1 - scale_frac) * R(leg2)

Each leg's R is the curve-exact ECR round-trip value at its own tick (quote - 1; quote = _exit_quote_value
= 1 + stressed round-trip return, 0 if unsellable). Using the FULL-position quote for each leg is a
conservative approximation (a smaller partial sell would fill slightly BETTER). If `tp_level` is never
reached, leg 1 does not fire and the whole position rides the trail (V5 == plain trail on that trade).
Arm A (scale_out false) is the plain trail. At most two legs.
"""
from __future__ import annotations

import time

from . import ecr
from .detector import SLOT_SECONDS
from .resolve import _price_usd
from .resolve_v2 import _exit_quote_value
from scripts.trading_bot.memebot import paper as _mpaper


_LAMPORTS_PER_SOL = 1_000_000_000


def _second_leg_exit_gas_frac(spec: dict, q_sol: float) -> float:
    """A scale-out is TWO sell transactions; each _exit_quote_value round-trip already charges ONE exit-gas
    bundle, so the fraction-weighted blend nets out only one. Charge the SECOND sell's fixed exit gas (the
    frozen per-side stress model: (base+priority+tip)*(1+failed_attempts)) as a fraction of the entry cost,
    so the record honours the prereg's 'positive after ALL costs, BOTH legs'. The ATA opens once/closes
    once, so no second ata_rent is charged."""
    pol = spec.get("ecr_stress_policy", {})
    base = pol.get("base_fee_lamports", 5000)
    prio = pol.get("priority_fee_lamports", 100_000)
    tip = pol.get("tip_lamports", 0)
    fa = pol.get("failed_attempts", 1)
    exit_gas = (base + prio + tip) * (1 + fa)
    entry_cost = q_sol * _LAMPORTS_PER_SOL + exit_gas + pol.get("ata_rent_lamports", 2_039_280)
    return exit_gas / max(1.0, entry_cost)


def _trail_leg(entry_reserves, tape_lines, spec, q_sol, cluster, t_entry, start_i, now):
    """The runner leg: 12% quote-trail + capacity/cluster/horizon, over tape_lines[start_i:]. Returns
    (exit_line, reason, R). Mirrors the plain-trail resolver (V2 arm C / V4 arm A)."""
    ex = spec["exit"]
    max_hold_s = ex["max_hold_slots"] * SLOT_SECONDS
    trail = float(ex["trail_frac"]); cov_buffer = float(ex["coverage_exit_buffer"])
    resume_frac = float(ex["cluster_resume_frac_of_R"])
    peak = _exit_quote_value(entry_reserves, entry_reserves, q_sol)
    # seed the peak with everything up to the scale-out tick so the trail is measured from the true peak
    for ln in tape_lines[:start_i]:
        peak = max(peak, _exit_quote_value(entry_reserves, ln, q_sol))
    prev_R = ecr.real_quote_sol(entry_reserves)
    exit_line = None; reason = None
    for ln in tape_lines[start_i:]:
        ts = float(ln["ts"])
        if ts < t_entry:
            continue
        side = ln.get("side"); trader = ln.get("trader"); sol = float(ln.get("sol_amount") or 0.0)
        quote = _exit_quote_value(entry_reserves, ln, q_sol)
        if quote > peak:
            peak = quote
        if quote <= 0.0 or ecr.coverage_ratio(ln, q_sol) < cov_buffer:
            exit_line, reason = ln, "CAPACITY_BREAK"; break
        if side == "sell" and trader in cluster and prev_R > 0 and sol >= resume_frac * prev_R:
            exit_line, reason = ln, "CLUSTER_RESUME"; break
        if peak > 0 and quote <= (1.0 - trail) * peak:
            exit_line, reason = ln, "QUOTE_TRAIL"; break
        if ts >= t_entry + max_hold_s:
            exit_line, reason = ln, "MAX_HOLD"; break
        prev_R = ecr.real_quote_sol(ln)
    if exit_line is None:
        if tape_lines and now >= t_entry + max_hold_s:
            exit_line, reason = tape_lines[-1], "MAX_HOLD"
        else:
            return None, None, None
    return exit_line, reason, _exit_quote_value(entry_reserves, exit_line, q_sol) - 1.0


def resolve_from_tape_v5(setup: dict, tape_lines: list, spec: dict, arm: dict,
                         now: float | None = None) -> dict | None:
    if now is None:
        now = time.time()
    q_sol = float(setup.get("q_sol") or spec["detector"]["q_sol"])
    cluster = set(setup.get("cluster_wallets") or [])
    t_entry = float(setup.get("t_entry") or (tape_lines[0]["ts"] if tape_lines else 0.0))
    entry_reserves = setup["entry_reserves"]
    lines = [ln for ln in tape_lines if float(ln["ts"]) >= t_entry]

    scale_out = bool((arm or {}).get("scale_out"))
    tp_level = arm.get("tp_level")
    scale_frac = float(arm.get("scale_frac") or 0.0)

    leg1_line = None; leg1_R = None; start_i = 0
    if scale_out and tp_level is not None and scale_frac > 0:
        for i, ln in enumerate(lines):
            if _exit_quote_value(entry_reserves, ln, q_sol) >= float(tp_level):
                leg1_line = ln
                leg1_R = _exit_quote_value(entry_reserves, ln, q_sol) - 1.0
                start_i = i          # leg 2 rides from the scale-out tick onward
                break

    leg2 = _trail_leg(entry_reserves, lines, spec, q_sol, cluster, t_entry, start_i, now)
    exit_line, reason, leg2_R = leg2
    if exit_line is None:
        return None   # still open

    # leg-2 unsellable handling (its fraction booked at full loss); leg-1 gain, if banked, stands.
    stressed2 = ecr.ecr_roundtrip(entry_reserves, exit_line, q_sol)
    leg2_unexitable = bool(stressed2["unexitable"])
    if leg2_unexitable:
        leg2_R = -1.0

    second_leg_gas = 0.0
    if leg1_line is not None:
        second_leg_gas = _second_leg_exit_gas_frac(spec, q_sol)   # the extra sell pays exit gas (BOTH legs)
        blended = scale_frac * leg1_R + (1.0 - scale_frac) * leg2_R - second_leg_gas
        reason = f"SCALE_OUT+{reason}"
        unexitable = leg2_unexitable and scale_frac < 1.0 and leg1_R <= 0  # only if nothing was banked
    else:
        blended = leg2_R
        unexitable = leg2_unexitable

    held_min = (float(exit_line["ts"]) - t_entry) / 60.0
    entry_price = _price_usd(entry_reserves) or setup.get("entry_price_usd") or 1.0
    exit_price = _price_usd(exit_line) or entry_price
    record = _mpaper._resolution_record(setup, exit_price,
                                        "UNEXITABLE_TIMEOUT" if unexitable else reason,
                                        held_min, "aftershock_v5_tape")
    record.update({
        "stressed_net_return": round(blended, 6),
        "stressed_ecr": round(stressed2["stressed_ecr"], 6),
        "unexitable": bool(unexitable),
        "scale_out_leg1_R": (round(leg1_R, 6) if leg1_R is not None else None),
        "runner_leg2_R": round(leg2_R, 6),
        "second_leg_exit_gas": round(second_leg_gas, 6),
        "deployer": setup.get("deployer"),
        "exit_reserves": {"v_sol": exit_line.get("v_sol"), "v_tokens": exit_line.get("v_tokens"),
                          "pool": exit_line.get("pool")},
    })
    return record
