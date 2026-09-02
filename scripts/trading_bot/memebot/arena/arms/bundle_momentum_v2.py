#!/usr/bin/env python3
"""BUNDLE_MOMENTUM_V2 — causal money-book bundle arm.

Same frozen first-six entry predicate as BUNDLE_MOMENTUM_V1, wired to the Phase-0 money-book framework:
  * $10 fixed clip sized in SOL at the fill (sizer.CLIP_USD via solusd_recorder + q_lamports_for_usd),
  * helius_coverage.coverage_ok completeness gate BEFORE any pending entry (a miss is a COVERAGE_VOID),
  * one of the ≤ 2 global PRIMARY slots claimed at the OPEN site (shared flock'd portfolio.json),
  * every would-be −100% RUG routed through helius_rug_arbiter (non-RUG_CONFIRMED ⇒ MEASUREMENT_FAILURE void).
The honest causal_cp fill / exit / ledger / scorer spine is unchanged and shared. New instrument, new ledger
dir — the frozen V1 ledger is untouched. No wallet, no orders, no spend.
"""
from __future__ import annotations

import hashlib
import pathlib

from ..arm import Arm, closure_sha256
from .bundle_momentum import (first_six_signal, K_BUYS, CLUMP_NS, CONCENTRATION_NUM,
                              CONCENTRATION_DEN)

CLIP_USD = "10"                  # fixed $10 money-book clip (== sizer.CLIP_USD), sized in SOL at the fill
LATENCY_S = 0.9
ENTRY_BOUNDARY_TIMEOUT_S = 60
EXIT_BOUNDARY_TIMEOUT_S = 60
DEAD_SILENCE_S = 600
COVERAGE_K = 6                   # first-K completeness the coverage gate must prove before a pending entry
PREREG = pathlib.Path(__file__).with_name("BUNDLE_MOMENTUM_V2_PREREGISTRATION.md")
SPEC = {"K_BUYS": K_BUYS, "CLUMP_NS": CLUMP_NS, "CONCENTRATION_NUM": CONCENTRATION_NUM,
        "CONCENTRATION_DEN": CONCENTRATION_DEN, "CLIP_USD": CLIP_USD, "LATENCY_S": LATENCY_S,
        "ENTRY_BOUNDARY_TIMEOUT_S": ENTRY_BOUNDARY_TIMEOUT_S,
        "EXIT_BOUNDARY_TIMEOUT_S": EXIT_BOUNDARY_TIMEOUT_S, "DEAD_SILENCE_S": DEAD_SILENCE_S,
        "COVERAGE_K": COVERAGE_K, "target_n": 120, "extended_cap": 240}


def _canonical_spec() -> str:
    return repr(sorted(SPEC.items()))


class BundleMomentumV2(Arm):
    instrument = "BUNDLE_MOMENTUM_V2"
    fill_basis = "causal_cp"
    service_kind = "trade_tape"
    requires_trade_data = True
    target_n = 120
    extended_cap = 240

    def code_sha256(self):
        arena = pathlib.Path(__file__).resolve().parents[1]
        aftershock = arena.parents[1] / "aftershock"
        repo = arena.parents[3]
        return closure_sha256([pathlib.Path(__file__)] + [arena / name for name in (
            "arm.py", "bundle_v2_runtime.py", "chainledger.py", "cohorts.py", "exit_engine.py",
            "fill.py", "helius_coverage.py", "helius_rug_arbiter.py", "manifest.py", "runtime.py",
            "scorer.py", "sizer.py")]
            + [arena / "arms" / "bundle_momentum.py", arena.parent / "__main__.py",
               arena.parent / "ws_data.py", arena.parent / "helius_tape.py",
               arena.parent / "helius_pump_decode.py", repo / "research" / "pump_idl_9c82f61.json",
               aftershock / "pac_v2_pumpswap.py", aftershock / "solusd_recorder.py",
               aftershock / "execution.py"])

    def prereg_sha256(self):
        return hashlib.sha256(PREREG.read_bytes()).hexdigest()

    def spec_sha256(self):
        return hashlib.sha256(_canonical_spec().encode()).hexdigest()

    def candidates(self, feed):
        return []

    def entry_ok(self, candidate, history):
        # The at-s6 concentration proxy. The coverage_ok completeness gate is enforced by the runtime at the
        # signal site (it needs the create coordinate + captured first-K buys, which are runtime state).
        return first_six_signal(history + [candidate]) is not None

    def final_verdict(self, decision, rows, all_rows):
        if decision.get("verdict") == "PASS":
            return {**decision, "verdict": "PASS_PENDING_SENSITIVITY",
                    "reason": "positive primary CI; preregistered latency/clump replay still required"}
        return decision


ARM = BundleMomentumV2()


def _selftest() -> None:
    rows = [{"received_unix_nanos": 1_000_000_000 + i * 100_000_000, "sequence": i + 1,
             "tx_type": "buy", "trader": "a" if i < 3 else "b", "token_amount": "10",
             "record_sha256": f"{i + 1:064x}"} for i in range(6)]
    assert ARM.entry_ok(rows[-1], rows[:-1])
    assert ARM.spec_sha256() and ARM.prereg_sha256()
    print("BUNDLE_MOMENTUM_V2 selftest: PASS")


if __name__ == "__main__":
    _selftest()
