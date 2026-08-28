#!/usr/bin/env python3
"""AFTERSHOCK execution-realism feasibility adapter (handoff 424). PAPER-ONLY, UNFROZEN.

Plumbing only — NO strategy, NO frozen instrument, NO secondary-sell thresholds. Wires the pure execution
engine to the real b10a integer kernel: the price_fn returns a structured PriceResult or raises the NAMED
PriceUnavailable for a known venue refusal (curve complete / below-min / ineligible). Unknown errors are
NOT swallowed into a fill. The single wallet-cost path is the kernel's own execution cost (no hardcode).

Every result is PUMPPORTAL_RECEIVE_TIME_SCENARIO + SIMULATED_OBSERVED_PATH + CALIBRATION_UNCALIBRATED — a
scenario, never executable evidence.
"""
from __future__ import annotations

import hashlib
import json

from . import ecr
from .execution import (
    ObservedEvent, ReserveState, Source, CanonicalCoord,
    OrderIntent, IntentKind, PriceResult, PriceUnavailable, Unit,
    LatencyModel, ExecutionContext, RefusedExecution, build_decision_record, attempt_order,
)

_B10A = ecr._B10A
_FEE = ecr.FEE_SCHEDULE
# One AttemptRecord represents exactly one attempt. Hidden failed attempts inside the kernel policy would
# charge retries without records, so the adapter is structurally fixed to zero embedded failures.
_POLICY = {**ecr.BASE_POLICY, "failed_attempts": 0}
_NATIVE = ecr.NATIVE_QUOTE_MINT
_STATUS_PRICED = getattr(_B10A, "STATUS_PRICED", "PRICED")


def _reserve_state(kernel_state: dict) -> ReserveState:
    return ReserveState(
        virtual_quote=int(kernel_state["virtual_quote"]), virtual_token=int(kernel_state["virtual_token"]),
        real_quote=int(kernel_state["real_quote"]), real_token=int(kernel_state["real_token"]),
        complete=bool(kernel_state["complete"]))


def tape_to_events(tape_lines: list) -> list:
    """PumpPortal observations -> a receive-time stream.

    ``received_unix_nanos`` is mandatory. Provider event time is not a local receive clock and is never
    silently relabelled as one. Optional canonical coordinates must be present as a complete four-field set.
    """
    events, prev_state = [], None
    for ln in tape_lines:
        if not isinstance(ln, dict) or not isinstance(ln.get("mint"), str) or not ln["mint"].strip():
            raise RefusedExecution("every PumpPortal observation requires an exact mint")
        obs_ns = ln.get("received_unix_nanos")
        if type(obs_ns) is not int or obs_ns < 0:
            raise RefusedExecution("PumpPortal observation requires exact non-negative received_unix_nanos")
        ks = ecr.reserves_from_tape({"v_sol": ln["v_sol"], "v_tokens": ln["v_tokens"], "pool": ln.get("pool", "pump")})
        post = _reserve_state(ks)
        pre = prev_state if prev_state is not None else post
        coordinate_fields = ("slot", "transaction_index", "outer_index", "inner_index")
        present = [field in ln for field in coordinate_fields]
        if any(present) and not all(present):
            raise RefusedExecution("PumpPortal reconciliation coordinate is partial")
        coord = (CanonicalCoord(*(ln[field] for field in coordinate_fields)) if all(present) else None)
        evidence_body = {key: ln.get(key) for key in (
            "mint", "provider_event_time", "received_unix_nanos", "observation_source", "sig",
            "v_sol", "v_tokens", "pool",
            *coordinate_fields)}
        sha = hashlib.sha256(json.dumps(evidence_body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        raw_source = ln.get("observation_source", "pumpportal")
        try:
            source = Source(raw_source)
        except ValueError as exc:
            raise RefusedExecution(f"unknown observation_source {raw_source!r}") from exc
        events.append(ObservedEvent(
            mint=ln["mint"],
            observation_unix_nanos=obs_ns, pre_state=pre, post_state=post,
            source=source, evidence_sha=sha, coord=coord))
        prev_state = post
    return events


def _kernel_state(rs: ReserveState) -> dict:
    return {"virtual_quote": rs.virtual_quote, "virtual_token": rs.virtual_token,
            "real_quote": rs.real_quote, "real_token": rs.real_token, "complete": rs.complete,
            "quote_mint": _NATIVE, "mayhem_mode": False, "slot": 1}


def _gas_cost(exec_costs: dict) -> int:
    """The single, exact wallet-cost path: the kernel's own `total` MINUS ata_rent (ata_rent is settled by
    the typed rent ledger, not double-counted here). Reconciles to one number — no summing of components +
    total, no `failed_attempts` count, no hardcode (handoff 423 P0-4)."""
    if not isinstance(exec_costs, dict):
        raise RefusedExecution("kernel execution_costs must be a mapping")
    if exec_costs.get("failed_attempts") != 0 or exec_costs.get("failed_attempt_cost") != 0:
        raise RefusedExecution("kernel embedded a hidden retry; every failed attempt needs its own record")
    total = exec_costs.get("total")
    ata = exec_costs.get("ata_rent_charged_never_refunded")
    if type(total) is not int or type(ata) is not int or total < ata or ata < 0:
        raise RefusedExecution("kernel execution cost/rent did not reconcile as non-negative exact integers")
    return total - ata


def _exit_gas_cost(exec_costs: dict) -> int:
    """Exit wallet cost. Unlike entry, `price_exit` carries NO `ata_rent_charged_never_refunded` — ATA rent
    is charged once on entry and never refunded on exit (b10a kernel contract), so it is a sunk entry cost,
    not part of the exit gas. The exit `total` IS the wallet gas; this validates that shape strictly and
    refuses if an ata field ever appears here (that would mean the exit double-counted entry rent)."""
    if not isinstance(exec_costs, dict):
        raise RefusedExecution("kernel execution_costs must be a mapping")
    if exec_costs.get("failed_attempts") != 0 or exec_costs.get("failed_attempt_cost") != 0:
        raise RefusedExecution("kernel embedded a hidden retry; every failed attempt needs its own record")
    if "ata_rent_charged_never_refunded" in exec_costs:
        raise RefusedExecution("exit cost carries an ata_rent field; entry rent must not be charged on exit")
    total = exec_costs.get("total")
    if type(total) is not int or total < 0:
        raise RefusedExecution("kernel exit cost did not reconcile as a non-negative exact integer")
    return total


def kernel_accounting(fill_state: ReserveState, intent: OrderIntent) -> dict:
    """One exact B10a price plus the wallet components the generic AttemptRecord intentionally omits.

    ``AttemptRecord.cost_lamports`` remains the current attempt's gas/tip cost.  This companion record
    additionally exposes curve fees, ATA rent, and the final wallet delta so a portfolio runner cannot
    accidentally call a gross quote an all-cost return.  It is deterministic and contains no defaults.
    """
    if not isinstance(fill_state, ReserveState) or not isinstance(intent, OrderIntent):
        raise RefusedExecution("kernel_accounting requires typed fill state and intent")
    state = _kernel_state(fill_state)
    try:
        if intent.kind == IntentKind.EXACT_QUOTE_BUY:
            r = _B10A.price_entry(
                state, {"side": _B10A.BUY, "quote_lamports": intent.amount}, _FEE, _POLICY)
            tokens = int(r.get("tokens_out") or 0)
            if tokens <= 0:
                raise PriceUnavailable("entry priced zero tokens")
            fees = r.get("curve_fees") or {}
            execution = r.get("execution_costs") or {}
            attempt_cost = _gas_cost(execution)
            curve_fee = fees.get("charged_total")
            ata_rent = execution.get("ata_rent_charged_never_refunded")
            wallet_out = r.get("lamports_out_of_wallet")
            for label, value in (("curve fee", curve_fee), ("ATA rent", ata_rent),
                                 ("entry wallet out", wallet_out)):
                if type(value) is not int or value < 0:
                    raise RefusedExecution(f"kernel {label} is not an exact non-negative integer")
            if wallet_out != intent.amount + curve_fee + attempt_cost + ata_rent:
                raise RefusedExecution("kernel entry wallet delta does not reconcile")
            return {
                "side": "ENTRY", "out_amount": tokens, "out_unit": Unit.ATOMS,
                "gross_quote_lamports": intent.amount,
                "curve_fee_lamports": curve_fee,
                "attempt_cost_lamports": attempt_cost,
                "ata_rent_lamports": ata_rent,
                "wallet_delta_lamports": -wallet_out,
            }

        r = _B10A.price_exit(state, intent.amount, _FEE, _POLICY)
        if r.get("status") != _STATUS_PRICED or r.get("quote_lamports") is None:
            raise PriceUnavailable(f"exit not priced: {r.get('status')}")
        fees = r.get("curve_fees") or {}
        execution = r.get("execution_costs") or {}
        gross = r.get("quote_lamports")
        curve_fee = fees.get("charged_total")
        attempt_cost = _exit_gas_cost(execution)
        wallet_in = r.get("lamports_into_wallet")
        for label, value in (("exit gross quote", gross), ("curve fee", curve_fee),
                             ("exit wallet in", wallet_in)):
            if type(value) is not int:
                raise RefusedExecution(f"kernel {label} is not an exact integer")
        if gross < 0 or curve_fee < 0 or wallet_in != gross - curve_fee - attempt_cost:
            raise RefusedExecution("kernel exit wallet delta does not reconcile")
        return {
            "side": "EXIT", "out_amount": gross, "out_unit": Unit.LAMPORTS,
            "gross_quote_lamports": gross,
            "curve_fee_lamports": curve_fee,
            "attempt_cost_lamports": attempt_cost,
            "ata_rent_lamports": 0,
            "wallet_delta_lamports": wallet_in,
        }
    except PriceUnavailable:
        raise
    except _B10A.SimulationRefused as exc:
        # This is the kernel's one named evidence/venue refusal. Programming errors propagate.
        raise PriceUnavailable(f"kernel refused: {type(exc).__name__}") from exc


def kernel_price_fn():
    def _price(fill_state: ReserveState, intent: OrderIntent) -> PriceResult:
        accounting = kernel_accounting(fill_state, intent)
        return PriceResult(
            out_amount=accounting["out_amount"], unit=accounting["out_unit"],
            wallet_cost_lamports=accounting["attempt_cost_lamports"])
    return _price


def demo_attempt(tape_lines: list, intent: OrderIntent, reaction_nanos: int, *,
                 ctx: ExecutionContext, detector_module_path: str,
                 detector_callable_name: str, detector_sha256: str,
                 spec_sha256: str, attempt_index: int = 0,
                 retry_of: str | None = None) -> dict:
    """Exercise the public anchored path; this harness never manufactures a verified context."""
    events = tape_to_events(tape_lines)
    decision = build_decision_record(
        events, ctx, detector_module_path=detector_module_path,
        detector_callable_name=detector_callable_name,
        detector_sha256=detector_sha256, spec_sha256=spec_sha256)
    rec = attempt_order(events, decision, intent, LatencyModel(reaction_nanos=reaction_nanos),
                        ctx, kernel_price_fn(), attempt_index=attempt_index, retry_of=retry_of)
    return {
        "outcome": rec.outcome.value, "boundary_index": rec.boundary_index,
        "out_amount": rec.out_amount, "out_unit": rec.out_unit.value if rec.out_unit else None,
        "cost_lamports": rec.cost_lamports, "cost_reason": rec.cost_reason,
        "labels": list(rec.labels), "attempt_id": rec.attempt_id,
        "clocks": {
            "observation": rec.clocks.observation_unix_nanos,
            "decision": rec.clocks.decision_unix_nanos,
            "build": rec.clocks.build_unix_nanos,
            "send": rec.clocks.send_unix_nanos,
            "land": rec.clocks.land_unix_nanos,
            "modeled_land_target": rec.clocks.modeled_land_target_unix_nanos,
            "scenario_boundary_observation": rec.clocks.scenario_boundary_observation_unix_nanos,
        },
        "boundary": "SCENARIO ONLY — PumpPortal receive-time, uncalibrated latency; not executable evidence.",
    }
