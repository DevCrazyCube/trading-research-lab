#!/usr/bin/env python3
"""ECR engine — the Exit-Capacity/round-trip math for AFTERSHOCK. Curve-EXACT, PAPER, read-only.

It does NOT reinvent the pump.fun bonding curve. It converts a PumpPortal tape line into the integer
reserve state the repo's audited kernel expects (scripts/b10a_simulator_kernel.py, itself over b9i), and
wraps that kernel's `simulate_round_trip` so every ECR is priced with the same integer arithmetic and
the same fee/execution model the repo already validated against on-chain trades.

TWO distinct quantities, deliberately named apart so they are never conflated:
  * coverage_ratio(line, q)  = R(t)/q  — how many times over the standing EXTERNAL real-SOL book alone
    could pay out a q-SOL position. Cheap, tape-only, used by the detector/resolver as a liquidity gate.
  * ecr_roundtrip(...)       = the curve-EXACT, fully-stressed round-trip return of a q-SOL position
    (buy q SOL of tokens at the frozen entry reserves, sell them back at the exit reserves), net of the
    125 bps/side curve fees + the execution/failed-landing stress. Feeds the pot-growth scorer.
    UNSELLABLE (the curve cannot pay the position, or the pool migrated) -> stressed_net_return = -1.0.

Pinned constants are VERIFIED against real pump.fun CreateEvents (research/b11a_creates.jsonl et al.:
virtual_quote 30_000_000_000, virtual_token 1_073_000_000_000_000, real_token 793_100_000_000_000,
real_quote 0 at launch) and the b17a execution model (fee 95 bps + creator 30 bps; base 5000, priority
100_000, ata_rent 2_039_280 lamports). Since real and virtual reserves move by the SAME delta on every
trade (b9d.curve_states_from_trade), `virtual - real` is a launch-fixed offset -> real_quote and
real_token are recovered exactly from the tape's virtual reserves.
"""
from __future__ import annotations

import importlib.util
import pathlib

_ROOT = pathlib.Path(__file__).resolve().parents[3]


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, _ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_B10A = _load("b10a_simulator_kernel", "b10a_simulator_kernel.py")
SimulationRefused = _B10A.SimulationRefused
STATUS_EXIT_UNAVAILABLE = _B10A.STATUS_EXIT_UNAVAILABLE
BUY = _B10A.BUY

# --------------------------------------------------------------------------------------------------
# Pinned constants (verified against real CreateEvents + b17a). Do curve arithmetic in raw integers.
# --------------------------------------------------------------------------------------------------
LAMPORTS_PER_SOL = 1_000_000_000
TOKEN_DECIMALS = 6
VIRTUAL_QUOTE_OFFSET = 30_000_000_000          # real_quote = virtual_quote(lamports) - 30 SOL
VIRTUAL_TOKEN_OFFSET = 279_900_000_000_000     # real_token = virtual_token(atoms) - (1073e12 - 793.1e12)
NATIVE_QUOTE_MINT = "11111111111111111111111111111111"
PUMP_POOLS = frozenset({"pump", "pumpfun"})    # the frozen regime: pump.fun bonding curve, SOL-paired only

FEE_SCHEDULE = {"fee_bps": 95, "creator_fee_bps": 30, "cashback_fee_bps": 0, "buyback_fee_bps": 5000}
# Base execution model (b17a). STRESS adds one failed landing per side (re-charges base+priority once) --
# the single a-priori stress lever; nothing here is tuned to an observed P&L.
BASE_POLICY = {"base_fee_lamports": 5000, "priority_fee_lamports": 100_000, "tip_lamports": 0,
               "ata_rent_lamports": 2_039_280, "failed_attempts": 0}
STRESS_POLICY = {**BASE_POLICY, "failed_attempts": 1}


def reserves_from_tape(line: dict, *, slot: int | None = None) -> dict:
    """One PumpPortal tape line -> the b10a-eligible integer curve state.

    Tape carries vSol/vTokens as floats in WHOLE SOL / WHOLE tokens; recover integers before any curve
    math. `slot` is synthesised from the wall-clock ts (ms) as a strictly-monotonic tick, used only to
    satisfy the kernel's exit-follows-entry ordering guard (the tape is not slot-stamped).
    """
    v_sol_lamports = round(float(line["v_sol"]) * LAMPORTS_PER_SOL)
    v_tok_atoms = round(float(line["v_tokens"]) * (10 ** TOKEN_DECIMALS))
    pool = (line.get("pool") or "pump")
    migrated = pool not in PUMP_POOLS
    if slot is None:
        slot = max(1, round(float(line.get("ts", 0.0)) * 1000.0))
    return {
        "virtual_quote": max(1, v_sol_lamports),
        "virtual_token": max(1, v_tok_atoms),
        "real_quote": v_sol_lamports - VIRTUAL_QUOTE_OFFSET,      # the exit-binding external SOL book
        "real_token": v_tok_atoms - VIRTUAL_TOKEN_OFFSET,
        "quote_mint": NATIVE_QUOTE_MINT,
        "mayhem_mode": False,
        "complete": migrated,                                    # migrated -> curve exit unavailable
        "slot": int(slot),
    }


def real_quote_sol(line: dict) -> float:
    """R(t): the real EXTERNAL SOL in the curve that can actually pay a seller (virtual_quote - 30 SOL),
    floored at 0. This is the standing book a position must exit into."""
    v_sol_lamports = round(float(line["v_sol"]) * LAMPORTS_PER_SOL)
    return max(0.0, (v_sol_lamports - VIRTUAL_QUOTE_OFFSET)) / LAMPORTS_PER_SOL


def coverage_ratio(line: dict, q_sol: float) -> float:
    """R(t)/q — size-invariant liquidity gate. >= entry floor to arm; < exit buffer to bail."""
    if q_sol <= 0:
        return float("inf")
    return real_quote_sol(line) / q_sol


def ecr_roundtrip(entry_reserves: dict, exit_line: dict, q_sol: float) -> dict:
    """Curve-EXACT, stressed round-trip of a q-SOL position from frozen entry reserves to exit reserves.

    Returns {stressed_net_return, stressed_ecr, unexitable, net_lamports}. UNSELLABLE (the exit curve
    cannot pay the tokens the entry bought, or the pool migrated) -> stressed_net_return = -1.0,
    unexitable=True: the honest full-loss mark. The loss is floored at -1.0 (a paper position cannot
    lose more than its all-in cost).
    """
    order = {"side": BUY, "quote_lamports": max(1, round(q_sol * LAMPORTS_PER_SOL))}
    entry_state = reserves_from_tape(entry_reserves)
    exit_state = reserves_from_tape(exit_line)
    if exit_state["slot"] <= entry_state["slot"]:
        exit_state["slot"] = entry_state["slot"] + 1              # strictly follow (synthetic ordering)
    try:
        rt = _B10A.simulate_round_trip(entry_state, exit_state, order, FEE_SCHEDULE, STRESS_POLICY)
    except SimulationRefused:
        # exit refused = the reserves cannot pay this position out = unsellable.
        return {"stressed_net_return": -1.0, "unexitable": True, "stressed_ecr": 0.0, "net_lamports": None}
    if rt["status"] == STATUS_EXIT_UNAVAILABLE or rt.get("net_lamports") is None:
        return {"stressed_net_return": -1.0, "unexitable": True, "stressed_ecr": 0.0, "net_lamports": None}
    cost = rt["entry"]["lamports_out_of_wallet"]
    into = rt["exit"]["lamports_into_wallet"]
    if cost <= 0:
        return {"stressed_net_return": -1.0, "unexitable": True, "stressed_ecr": 0.0, "net_lamports": None}
    net_return = rt["net_lamports"] / cost
    ecr = into / cost
    if net_return < -1.0:
        # Intentional modeling floor: max loss = the whole position (fractional-sizing convention, keeps
        # log-growth bounded). Exit-gas overshoot beyond -1 is negligible. Floor stressed_ecr CONSISTENTLY
        # (review #12) so it matches the unsellable branches where ecr 0.0 pairs with return -1.0.
        net_return, ecr = -1.0, 0.0
    return {"stressed_net_return": net_return, "unexitable": False,
            "stressed_ecr": ecr, "net_lamports": rt["net_lamports"]}
