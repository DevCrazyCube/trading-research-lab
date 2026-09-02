#!/usr/bin/env python3
"""MIGRATION_ACCEPTANCE_V1 — exit-capacity-gated PumpSwap graduation arm.

Models MEMEBOT_GRAD_V1 (PumpSwap exact-CP quotes, PROXY_PASS vs CONTROL_PROXY_FAIL cohorts) but enters ONLY
after a CONFIRMED migration whose live pool passes an EXECUTABLE EXIT-CAPACITY STRESS TEST — a failed stress
test is a STRATEGY VOID, never a trade and never a loss. Every real total-loss routes through the Helius
arbiter (in the runtime). New instrument, new ledger dir. No wallet, no orders, no spend.

This module supplies the arm identity, the frozen spec, the exact-integer PumpSwap buy quote, and the pure
`stress_test_exit_capacity` simulation the runtime (`migration_acceptance_runtime.py`) calls before entry.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import hashlib
import math
import pathlib

from .. import scorer
from .. import sizer as SZ
from ..arm import Arm, closure_sha256
from ....aftershock.execution import PriceUnavailable, RefusedExecution
from ....aftershock.pac_v2_pumpswap import PumpSwapReserves, sell_quote

FEE_DEN = 10_000
LATENCY_SLOTS = 15
SIZE_USD = "10"                  # fixed $10 money-book clip (== sizer.CLIP_USD)
ENTRY_ROUTE_COST_LAMPORTS = 105_000
EXIT_ROUTE_COST_LAMPORTS = 105_000
ATA_RENT_LAMPORTS = 2_039_280
ATA_CLOSE_COST_LAMPORTS = 5_000
POOL_CONFIRM_TIMEOUT_S = 120
MIGRATION_CONFIRM_TIMEOUT_S = 60
MAX_ENTRY_LAG_S = MIGRATION_CONFIRM_TIMEOUT_S + POOL_CONFIRM_TIMEOUT_S
STRESS_SELLS = 2                 # independent position-size sells that must be executably absorbed
MAX_STRESS_SLIPPAGE = 0.35       # each simulated exit must net >= (1 - this) of the SOL deployed
UNAVAILABLE_POLLS = 12
HORIZON_S = 90 * 60
PREREG = pathlib.Path(__file__).with_name("MIGRATION_ACCEPTANCE_PREREGISTRATION.md")
SPEC = {"LATENCY_SLOTS": LATENCY_SLOTS, "SIZE_USD": SIZE_USD,
        "ENTRY_ROUTE_COST_LAMPORTS": ENTRY_ROUTE_COST_LAMPORTS,
        "EXIT_ROUTE_COST_LAMPORTS": EXIT_ROUTE_COST_LAMPORTS,
        "ATA_RENT_LAMPORTS": ATA_RENT_LAMPORTS, "ATA_CLOSE_COST_LAMPORTS": ATA_CLOSE_COST_LAMPORTS,
        "POOL_CONFIRM_TIMEOUT_S": POOL_CONFIRM_TIMEOUT_S,
        "MIGRATION_CONFIRM_TIMEOUT_S": MIGRATION_CONFIRM_TIMEOUT_S, "MAX_ENTRY_LAG_S": MAX_ENTRY_LAG_S,
        "STRESS_SELLS": STRESS_SELLS, "MAX_STRESS_SLIPPAGE": MAX_STRESS_SLIPPAGE,
        "UNAVAILABLE_POLLS": UNAVAILABLE_POLLS, "HORIZON_S": HORIZON_S, "target_n": 100}

LAMPORTS_PER_SOL = 1_000_000_000


def _ceil(n: int, d: int) -> int:
    return -(-n // d)


def buy_quote(quote_in_lamports: int, reserves) -> dict:
    """Exact-integer PumpSwap buy, fee-on-input. Duplicated (not imported from graduation) so this arm's
    executable closure is self-contained."""
    if type(quote_in_lamports) is not int or quote_in_lamports <= 0:
        raise ValueError("migration buy requires positive exact quote input")
    fees = [_ceil(quote_in_lamports * bps, FEE_DEN) for bps in (
        reserves.lp_fee_bps, reserves.protocol_fee_bps, reserves.creator_fee_bps)]
    effective = quote_in_lamports - sum(fees)
    if effective <= 0:
        raise ValueError("migration buy fees consume its input")
    base_out = reserves.base_reserve * effective // (reserves.quote_reserve + effective)
    if base_out <= 0 or base_out >= reserves.base_reserve:
        raise ValueError("migration buy output is unavailable")
    return {"base_out_atoms": base_out, "effective_quote_lamports": effective,
            "lp_fee_lamports": fees[0], "protocol_fee_lamports": fees[1],
            "creator_fee_lamports": fees[2]}


def _depress(reserves: PumpSwapReserves, base_in_atoms: int, gross_out_lamports: int) -> PumpSwapReserves:
    """The pool AFTER an exact-CP sell of `base_in_atoms`: base grows by the tokens sold, quote shrinks by the
    gross SOL paid out. gross < quote_reserve always (constant product), so the quote stays positive."""
    return PumpSwapReserves(
        base_reserve=reserves.base_reserve + base_in_atoms,
        quote_reserve=reserves.quote_reserve - gross_out_lamports,
        lp_fee_bps=reserves.lp_fee_bps, protocol_fee_bps=reserves.protocol_fee_bps,
        creator_fee_bps=reserves.creator_fee_bps)


def stress_test_exit_capacity(reserves: PumpSwapReserves, base_in_atoms: int,
                              quote_in_lamports: int, sol_usd_value_str: str) -> dict:
    """The EXECUTABLE exit-capacity acceptance gate, run on the LIVE confirmed pool BEFORE any entry.

    A pool is accepted only if ALL of:
      1. the clip is <= 5% of the pool's exit capacity (`sizer.exit_capacity_ok`, capacity = the quote/WSOL
         reserve valued at the causal SOL/USD mark) — never trade blind/thin liquidity;
      2. `STRESS_SELLS` INDEPENDENT position-size sells are each executably absorbed — each sell is priced by
         the audited exact-CP `sell_quote` against the reserves the PRIOR sell left (so we model our own exit
         plus concurrent dumps depressing the pool), and each must net >= (1 - MAX_STRESS_SLIPPAGE) of the SOL
         deployed;
      3. after that depression, the FULL $10 position still sells absorbed (the exit recovers into the
         depressed pool) at the same slippage floor.

    A failure at (1) is an EXIT_CAPACITY_VOID; a failure at (2)/(3) is a STRESS_TEST_FAILED. Both are STRATEGY
    VOIDS (the caller never enters, never books a loss). Returns {ok, reason, detail, capacity_usd, absorbed}.
    Pure math (no I/O) — the reserve deltas are simulated, never sent."""
    try:
        rate = Decimal(str(sol_usd_value_str))
    except (InvalidOperation, TypeError, ValueError) as exc:
        return {"ok": False, "reason": "STRESS_TEST_FAILED", "detail": f"bad SOL/USD rate: {exc}"}
    if not rate.is_finite() or rate <= 0:
        return {"ok": False, "reason": "STRESS_TEST_FAILED", "detail": "non-positive SOL/USD rate"}
    if type(base_in_atoms) is not int or base_in_atoms <= 0 or type(quote_in_lamports) is not int \
            or quote_in_lamports <= 0:
        return {"ok": False, "reason": "STRESS_TEST_FAILED", "detail": "invalid position size/input"}

    capacity_usd = float(Decimal(reserves.quote_reserve) / Decimal(LAMPORTS_PER_SOL) * rate)
    ok_cap, cap_reason = SZ.exit_capacity_ok(float(Decimal(SIZE_USD)), capacity_usd)
    if not ok_cap:
        return {"ok": False, "reason": "EXIT_CAPACITY_VOID", "detail": cap_reason,
                "capacity_usd": capacity_usd}

    floor = (1.0 - MAX_STRESS_SLIPPAGE) * quote_in_lamports
    current = reserves
    absorbed: list[int] = []
    for i in range(STRESS_SELLS):
        try:
            q = sell_quote(base_in_atoms, current)
        except (PriceUnavailable, RefusedExecution) as exc:
            return {"ok": False, "reason": "STRESS_TEST_FAILED",
                    "detail": f"sell {i + 1} unpriceable: {str(exc)[:80]}", "capacity_usd": capacity_usd}
        if q["net_quote_lamports"] < floor:
            return {"ok": False, "reason": "STRESS_TEST_FAILED",
                    "detail": (f"sell {i + 1} netted {q['net_quote_lamports']} < floor {int(floor)} "
                               f"({MAX_STRESS_SLIPPAGE:.0%} slippage bound)"), "capacity_usd": capacity_usd}
        absorbed.append(q["net_quote_lamports"])
        current = _depress(current, base_in_atoms, q["gross_quote_lamports"])
    try:
        recovery = sell_quote(base_in_atoms, current)
    except (PriceUnavailable, RefusedExecution) as exc:
        return {"ok": False, "reason": "STRESS_TEST_FAILED",
                "detail": f"post-stress full exit unpriceable: {str(exc)[:80]}", "capacity_usd": capacity_usd}
    if recovery["net_quote_lamports"] < floor:
        return {"ok": False, "reason": "STRESS_TEST_FAILED",
                "detail": (f"post-stress full exit netted {recovery['net_quote_lamports']} < floor "
                           f"{int(floor)}"), "capacity_usd": capacity_usd}
    absorbed.append(recovery["net_quote_lamports"])
    return {"ok": True, "reason": "STRESS_PASS", "capacity_usd": capacity_usd, "absorbed": absorbed}


class MigrationAcceptance(Arm):
    instrument = "MIGRATION_ACCEPTANCE_V1"
    fill_basis = "pumpswap_exact_cp"
    service_kind = "graduation_rpc"
    requires_trade_data = True
    target_n = 100
    extended_cap = None

    def code_sha256(self):
        arena = pathlib.Path(__file__).resolve().parents[1]
        aftershock = arena.parents[1] / "aftershock"
        return closure_sha256([pathlib.Path(__file__)] + [arena / name for name in (
            "arm.py", "chainledger.py", "cohorts.py", "exit_engine.py", "fill.py",
            "helius_rug_arbiter.py", "manifest.py", "migration_acceptance_runtime.py", "runtime.py",
            "scorer.py", "sizer.py")]
            + [arena / "arms" / "bundle_momentum.py", arena.parent / "ws_data.py",
               aftershock / "pac_v2_pumpswap.py", aftershock / "solusd_recorder.py",
               aftershock / "execution.py"])

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


ARM = MigrationAcceptance()


def _selftest() -> None:
    deep = PumpSwapReserves(10 ** 15, 2_000 * LAMPORTS_PER_SOL, 20, 5, 5)   # deep pool
    q = 50_000_000                                                          # ~0.05 SOL clip input
    atoms = buy_quote(q, deep)["base_out_atoms"]
    ok = stress_test_exit_capacity(deep, atoms, q, "150")
    assert ok["ok"] and len(ok["absorbed"]) == STRESS_SELLS + 1, ok
    thin = PumpSwapReserves(10 ** 12, 1 * LAMPORTS_PER_SOL, 20, 5, 5)       # ~$150 pool, $10 clip = 6.7% > 5%
    atoms2 = buy_quote(q, thin)["base_out_atoms"]
    bad = stress_test_exit_capacity(thin, atoms2, q, "150")
    assert not bad["ok"] and bad["reason"] in {"EXIT_CAPACITY_VOID", "STRESS_TEST_FAILED"}, bad
    assert not ARM.include_resolution({"cohort": "CONTROL_PROXY_FAIL"})
    assert ARM.include_resolution({"cohort": "PROXY_PASS"})
    print("MIGRATION_ACCEPTANCE_V1 selftest: PASS")


if __name__ == "__main__":
    _selftest()
