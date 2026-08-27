#!/usr/bin/env python3
"""AFTERSHOCK resolver — tape-driven exit. PAPER, read-only.

AFTERSHOCK exits are CAPACITY/FLOW-first, not price-first (a fixed take-profit would clip the rare
right-tail runner the whole thesis needs). It walks the mint's trade tape forward from the frozen entry
and resolves on the FIRST of five triggers. The realised outcome is priced CURVE-EXACTLY by the ECR
engine against the frozen entry reserves and the exit-tick reserves, and an unsellable exit is booked
as a full economic loss (stressed_net_return = -1.0) — the honest mark.

It reuses memebot.paper._resolution_record for the append-only record schema (so the ledger/dashboard
read it unchanged), then augments with stressed_net_return / stressed_ecr / unexitable.
"""
from __future__ import annotations

import time
from collections import deque

from . import ecr
from .detector import SLOT_SECONDS
from scripts.trading_bot.memebot import paper as _mpaper

SOL_USD = 200.0   # display-only; every use here is a price RATIO, so the constant cancels


def _price_usd(line: dict) -> float:
    v_tok = float(line.get("v_tokens") or 0.0)
    if v_tok <= 0:
        return 0.0
    return (float(line["v_sol"]) / v_tok) * SOL_USD


def resolve_from_tape(setup: dict, tape_lines: list, spec: dict, now: float | None = None) -> dict | None:
    """Resolve ONE open AFTERSHOCK position against the tape lines AT/AFTER its entry. Returns a
    resolution record, or None if no exit trigger has fired yet (still open — call again with more tape).

    `tape_lines` are the mint's tape entries with ts >= the entry tick, in time order. `now` (wall-clock
    epoch seconds; defaults to time.time()) drives the MAX-HOLD backstop and is injectable for tests.
    """
    if now is None:
        now = time.time()
    ex = spec["exit"]
    q_sol = float(setup.get("q_sol") or spec["detector"]["q_sol"])
    cluster = set(setup.get("cluster_wallets") or [])
    t_entry = float(setup.get("t_entry") or (tape_lines[0]["ts"] if tape_lines else 0.0))
    entry_reserves = setup["entry_reserves"]

    max_hold_s = ex["max_hold_slots"] * SLOT_SECONDS
    flow_window_s = ex["flow_window_slots"] * SLOT_SECONDS

    entry_price = _price_usd(entry_reserves) or setup.get("entry_price_usd") or 1.0
    peak = entry_price
    flow = deque()   # trailing (ts, side, sol) over the flow window, non-cluster only
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
        price = _price_usd(ln) or peak
        peak = max(peak, price)

        # trailing non-cluster flow window
        if trader is not None and trader not in cluster and sol > 0:
            flow.append((ts, side, sol))
        while flow and flow[0][0] < ts - flow_window_s:
            flow.popleft()

        # ---- exit triggers, in priority order ----
        # 1) COVERAGE BREAK (primary): the standing external book can no longer cover the position.
        if ecr.coverage_ratio(ln, q_sol) < ex["coverage_exit_buffer"]:
            exit_line, reason = ln, "COVERAGE_BREAK"; break
        # 2) CLUSTER RESUME: a cluster wallet resumes distributing materially.
        if side == "sell" and trader in cluster and prev_R > 0 and sol >= ex["cluster_resume_frac_of_R"] * prev_R:
            exit_line, reason = ln, "CLUSTER_RESUME"; break
        # 3) FLOW FLIP: independent (non-cluster) selling dominates over the trailing window. Gated by a
        #    magnitude + trade-count floor (review #4) so a lone trivial sell (sell_frac==1.0 on ~0 volume)
        #    cannot trip the exit.
        sell_sol = sum(s for (_t, sd, s) in flow if sd == "sell")
        tot_sol = sum(s for (_t, _sd, s) in flow)
        flow_min_sol = ex.get("flow_min_window_sol", q_sol)
        flow_min_trades = ex.get("flow_min_trades", 3)
        if (tot_sol >= flow_min_sol and len(flow) >= flow_min_trades
                and (sell_sol / tot_sol) >= ex["flow_flip_sell_frac"]):
            exit_line, reason = ln, "FLOW_FLIP"; break
        # 4) TRAIL STOP: price gave back trail_frac from the peak (lets the runner run; no fixed TP).
        if price <= (1.0 - ex["trail_frac"]) * peak:
            exit_line, reason = ln, "TRAIL_STOP"; break
        # 5) MAX HOLD: liveness backstop.
        if ts >= t_entry + max_hold_s:
            exit_line, reason = ln, "MAX_HOLD"; break

        prev_R = R_now

    if exit_line is None:
        # WALL-CLOCK MAX-HOLD backstop (review #3/#5): the tape-driven MAX_HOLD only fires if a line
        # actually arrives past the horizon. A coin that goes silent after entry would otherwise never
        # resolve. If the horizon has objectively elapsed in wall-clock time, force-close at the last
        # observed line (its reserves price the stressed exit; an unsellable one books UNEXITABLE).
        if tape_lines and now >= t_entry + max_hold_s:
            exit_line, reason = tape_lines[-1], "MAX_HOLD"
        else:
            return None   # still open

    held_min = (float(exit_line["ts"]) - t_entry) / 60.0
    stressed = ecr.ecr_roundtrip(entry_reserves, exit_line, q_sol)
    # If the curve-exact exit says the position is unsellable, the honest reason is an unexitable dump,
    # regardless of which trigger nominally fired.
    if stressed["unexitable"]:
        reason = "UNEXITABLE_TIMEOUT"

    exit_price = _price_usd(exit_line) or entry_price
    record = _mpaper._resolution_record(setup, exit_price, reason, held_min, "aftershock_tape")
    record.update({
        "stressed_net_return": round(stressed["stressed_net_return"], 6),
        "stressed_ecr": round(stressed["stressed_ecr"], 6),
        "unexitable": bool(stressed["unexitable"]),
        "deployer": setup.get("deployer"),
        "exit_reserves": {"v_sol": exit_line.get("v_sol"), "v_tokens": exit_line.get("v_tokens"),
                          "pool": exit_line.get("pool")},
    })
    return record
