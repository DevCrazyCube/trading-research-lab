#!/usr/bin/env python3
"""MEMEBOT_GRAD_V1 exact PumpSwap quote math and Arena arm identity."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import pathlib

from .. import scorer

from ..arm import Arm, closure_sha256

FEE_DEN = 10_000
LATENCY_SLOTS = 15
SIZE_USD = "10"
ENTRY_ROUTE_COST_LAMPORTS = 105_000
EXIT_ROUTE_COST_LAMPORTS = 105_000
ATA_RENT_LAMPORTS = 2_039_280
ATA_CLOSE_COST_LAMPORTS = 5_000
POOL_CONFIRM_TIMEOUT_S = 120
MIGRATION_CONFIRM_TIMEOUT_S = 60
# A migration's signal->fill latency is bounded by migration + pool confirmation. Beyond that the earliest
# observable reserves are far past the modeled +LATENCY_SLOTS entry, so a fill would be a backlog casualty
# (lookahead-adjacent). Such entries are VOIDed, never filled late. Measurement parameter -> frozen in SPEC.
MAX_ENTRY_LAG_S = MIGRATION_CONFIRM_TIMEOUT_S + POOL_CONFIRM_TIMEOUT_S
UNAVAILABLE_POLLS = 12
HORIZON_S = 90 * 60
PREREG = pathlib.Path(__file__).with_name("GRADUATION_PREREGISTRATION.md")
SPEC = {"LATENCY_SLOTS": LATENCY_SLOTS, "SIZE_USD": SIZE_USD,
        "ENTRY_ROUTE_COST_LAMPORTS": ENTRY_ROUTE_COST_LAMPORTS,
        "EXIT_ROUTE_COST_LAMPORTS": EXIT_ROUTE_COST_LAMPORTS,
        "ATA_RENT_LAMPORTS": ATA_RENT_LAMPORTS, "ATA_CLOSE_COST_LAMPORTS": ATA_CLOSE_COST_LAMPORTS,
        "POOL_CONFIRM_TIMEOUT_S": POOL_CONFIRM_TIMEOUT_S,
        "MIGRATION_CONFIRM_TIMEOUT_S": MIGRATION_CONFIRM_TIMEOUT_S,
        "MAX_ENTRY_LAG_S": MAX_ENTRY_LAG_S,
        "UNAVAILABLE_POLLS": UNAVAILABLE_POLLS, "HORIZON_S": HORIZON_S,
        "target_n": 100}


def _ceil(n: int, d: int) -> int:
    return -(-n // d)


def buy_quote(quote_in_lamports: int, reserves) -> dict:
    if type(quote_in_lamports) is not int or quote_in_lamports <= 0:
        raise ValueError("graduation buy requires positive exact quote input")
    fees = [_ceil(quote_in_lamports * bps, FEE_DEN) for bps in (
        reserves.lp_fee_bps, reserves.protocol_fee_bps, reserves.creator_fee_bps)]
    effective = quote_in_lamports - sum(fees)
    if effective <= 0:
        raise ValueError("graduation buy fees consume its input")
    base_out = reserves.base_reserve * effective // (reserves.quote_reserve + effective)
    if base_out <= 0 or base_out >= reserves.base_reserve:
        raise ValueError("graduation buy output is unavailable")
    return {"base_out_atoms": base_out, "effective_quote_lamports": effective,
            "lp_fee_lamports": fees[0], "protocol_fee_lamports": fees[1],
            "creator_fee_lamports": fees[2]}


class Graduation(Arm):
    instrument = "MEMEBOT_GRAD_V1"
    fill_basis = "pumpswap_exact_cp"
    service_kind = "graduation_rpc"
    requires_trade_data = True
    target_n = 100
    extended_cap = None

    def code_sha256(self):
        arena = pathlib.Path(__file__).resolve().parents[1]
        aftershock = arena.parents[1] / "aftershock"
        return closure_sha256([pathlib.Path(__file__)] + [arena / name for name in (
            "arm.py", "chainledger.py", "exit_engine.py", "graduation_runtime.py", "runtime.py",
            "manifest.py", "scorer.py")]
            + [arena.parent / "ws_data.py", aftershock / "pac_v2_pumpswap.py",
               aftershock / "solusd_recorder.py"])

    def prereg_sha256(self):
        return hashlib.sha256(PREREG.read_bytes()).hexdigest()

    def spec_sha256(self):
        return hashlib.sha256(repr(sorted(SPEC.items())).encode()).hexdigest()

    def candidates(self, feed):
        return []

    def entry_ok(self, candidate, history):
        return False

    def include_resolution(self, row):
        return row.get("cohort") == "PROXY_PASS"

    def final_verdict(self, decision, rows, all_rows):
        control = [float(r["net_return"]) for r in all_rows
                   if r.get("cohort") == "CONTROL_PROXY_FAIL"]
        result = {**decision, "control_n": len(control),
                  "control_mean": (sum(control) / len(control) if control else None)}
        if len(rows) >= 30:
            negative = sum(float(row["net_return"]) < 0 for row in rows)
            sign_p = sum(math.comb(len(rows), k) for k in range(negative, len(rows) + 1)) / 2 ** len(rows)
            result["negative_sign_p"] = sign_p
            if sign_p < 0.05:
                return {**result, "verdict": "KILL",
                        "reason": "predeclared one-sided sign test rejects median >= 0"}
        if len(rows) >= self.target_n:
            values = [float(row["net_return"]) for row in rows]
            clusters = [(row.get("mint"), row.get("entry_day")) for row in rows]
            adjusted = scorer.cluster_bootstrap_ci(values, clusters, alpha=0.05 / 27)
            result.update({"multiplicity_tests": 27, "adjusted_ci_lo": adjusted["ci_lo"],
                           "adjusted_ci_hi": adjusted["ci_hi"]})
            if adjusted["ci_hi"] < 0:
                return {**result, "verdict": "KILL",
                        "reason": "27-test adjusted bootstrap CI upper bound < 0"}
            if adjusted["ci_lo"] > 0:
                return {**result, "verdict": "PASS_TO_CONFIRMATION",
                        "reason": "27-test adjusted bootstrap CI lower bound > 0; paper confirmation only"}
            return {**result, "verdict": "KILL",
                    "reason": "adjusted CI straddles zero at frozen N=100"}
        return result


ARM = Graduation()
