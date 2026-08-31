#!/usr/bin/env python3
"""Causal PumpSwap sell + ATA-close state machine for PAC_SCALP_LL.

This is a paper-scenario measurement component, not a transaction sender.  Pool discovery never
counts as a fill.  A sell decision is made only after a typed PumpSwap observation; the modeled
full-token fill uses a *new* observation at/after its calibrated landing target.  ATA rent is not
reclaimed until a separate close attempt lands at/after its own target.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum

from .execution import PriceUnavailable, RefusedExecution
from . import pac_scalp_ll_accounting as accounting
from . import pac_scalp_ll_clock as clocking
from . import pac_scalp_ll_engine as engine
from .pac_v2_pumpswap import PumpSwapObservation, sell_quote


class VenueState(str, Enum):
    AWAITING_POOL = "AWAITING_POOL"
    SELL_DECIDED = "SELL_DECIDED"
    AWAITING_ATA_CLOSE = "AWAITING_ATA_CLOSE"
    TERMINAL = "TERMINAL"


@dataclass(frozen=True)
class CloseEvidence:
    mint: str
    entry_id: str
    full_sale_token_atoms: int
    decision_id: str
    attempt_id: str
    target_unix_nanos: int
    landed_clock: engine.ClockStamp
    succeeded: bool
    evidence_mode: str = "MODELED_PAPER_ATA_CLOSE_SCENARIO_NOT_EXECUTABLE"

    def __post_init__(self) -> None:
        if not all(isinstance(value, str) and value for value in (
                self.mint, self.entry_id, self.decision_id, self.attempt_id)):
            raise RefusedExecution("ATA-close evidence identity is incomplete")
        if (type(self.full_sale_token_atoms) is not int or self.full_sale_token_atoms <= 0
                or type(self.target_unix_nanos) is not int or self.target_unix_nanos < 0
                or not isinstance(self.landed_clock, engine.ClockStamp)
                or type(self.succeeded) is not bool
                or self.evidence_mode != "MODELED_PAPER_ATA_CLOSE_SCENARIO_NOT_EXECUTABLE"):
            raise RefusedExecution("ATA-close evidence is malformed")
        if self.landed_clock.wall_unix_nanos < self.target_unix_nanos:
            raise RefusedExecution("ATA-close evidence predates its landing target")


@dataclass(frozen=True)
class Transition:
    position: engine.Position
    state: VenueState
    opened_unix_nanos: int
    deadline_unix_nanos: int
    next_observation_not_before_unix_nanos: int
    failed_attempt_cost_lamports: int = 0
    sell_decision_id: str | None = None
    sell_target_unix_nanos: int | None = None
    sell_observation_sha256: str | None = None
    sell_decision_context_slot: int | None = None
    pumpswap_pool: str | None = None
    pumpswap_base_vault: str | None = None
    pumpswap_quote_vault: str | None = None
    wallet_proceeds_lamports: int | None = None
    close_decision_id: str | None = None
    close_target_unix_nanos: int | None = None
    terminal_equity_lamports: int | None = None
    terminal_reason: str | None = None
    ata_rent_reclaimed: bool = False
    modeled_close_equity_lamports: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.position, engine.Position) or not isinstance(self.state, VenueState):
            raise RefusedExecution("venue transition identity/state is invalid")
        for name in ("opened_unix_nanos", "deadline_unix_nanos",
                     "next_observation_not_before_unix_nanos", "failed_attempt_cost_lamports"):
            if type(getattr(self, name)) is not int or getattr(self, name) < 0:
                raise RefusedExecution(f"venue transition {name} is invalid")
        if self.deadline_unix_nanos <= self.opened_unix_nanos:
            raise RefusedExecution("venue transition deadline is not after open")
        if type(self.ata_rent_reclaimed) is not bool:
            raise RefusedExecution("venue transition rent state is invalid")
        if self.state is VenueState.SELL_DECIDED and (
                not self.sell_decision_id or self.sell_target_unix_nanos is None):
            raise RefusedExecution("sell-decided transition lacks decision/target")
        if self.state is VenueState.AWAITING_ATA_CLOSE and (
                self.wallet_proceeds_lamports is None or not self.close_decision_id
                or self.close_target_unix_nanos is None):
            raise RefusedExecution("sold transition lacks proceeds/close decision")
        if self.state is VenueState.TERMINAL and (
                self.terminal_equity_lamports is None or not self.terminal_reason):
            raise RefusedExecution("terminal transition lacks settlement")


def _sha64(value: object, label: str) -> str:
    if (not isinstance(value, str) or len(value) != 64
            or any(char not in "0123456789abcdef" for char in value)):
        raise RefusedExecution(f"{label} is not a lowercase sha256")
    return value


def _assert_runtime(position: engine.Position, runtime: engine.ArmRuntime) -> None:
    engine.assert_position_runtime(position, runtime)


def begin(position: engine.Position, runtime: engine.ArmRuntime,
          decision: engine.ServiceDecision) -> Transition:
    _assert_runtime(position, runtime)
    if (not isinstance(decision, engine.ServiceDecision)
            or decision.mint != position.mint
            or decision.action != "VENUE_TRANSITION_REQUIRED"
            or not engine.curve_failure_requires_cross_venue(decision.reason or "")
            or decision.arm != position.arm or decision.provider_id != position.provider_id
            or decision.calibration_sha256 != position.calibration_sha256
            or decision.campaign_sha256 != position.campaign_sha256
            or decision.target_unix_nanos is None):
        raise RefusedExecution("cross-venue transition lacks a bound typed curve decision")
    deadline = position.entry_unix_nanos + 720_000_000_000
    opened = decision.decision_clock.wall_unix_nanos
    if opened >= deadline:
        return Transition(position, VenueState.TERMINAL, opened, deadline, opened,
                          terminal_equity_lamports=0,
                          terminal_reason="CROSS_VENUE_DEADLINE_FULL_LOSS")
    return Transition(position, VenueState.AWAITING_POOL, opened, deadline,
                      decision.target_unix_nanos)


def pool_observed(transition: Transition, runtime: engine.ArmRuntime,
                  observation: PumpSwapObservation, *, request_clock: engine.ClockStamp,
                  evidence_clock: engine.ClockStamp,
                  decision_clock: engine.ClockStamp, decision_id: str) -> Transition:
    """Turn pool discovery into a sell decision; discovery itself is never the fill."""
    _assert_runtime(transition.position, runtime)
    _sha64(decision_id, "PumpSwap sell decision id")
    if transition.state is not VenueState.AWAITING_POOL:
        raise RefusedExecution("PumpSwap pool observation is out of transition order")
    _validate_observation(transition, runtime, observation, request_clock, evidence_clock,
                          transition.next_observation_not_before_unix_nanos)
    decision_ns = _validate_decision_clocks(request_clock, evidence_clock, decision_clock)
    if decision_ns >= transition.deadline_unix_nanos:
        return expire(transition, decision_unix_nanos=decision_ns)
    return replace(
        transition, state=VenueState.SELL_DECIDED, sell_decision_id=decision_id,
        sell_target_unix_nanos=clocking.landing_target(
            decision_unix_nanos=decision_ns,
            calibrated_p90_nanos=runtime.calibrated_p90_nanos),
        sell_observation_sha256=observation.raw_response_sha256,
        sell_decision_context_slot=observation.context_slot,
        pumpswap_pool=observation.pool, pumpswap_base_vault=observation.base_vault,
        pumpswap_quote_vault=observation.quote_vault)


def sell_landed(transition: Transition, runtime: engine.ArmRuntime,
                observation: PumpSwapObservation, *, request_clock: engine.ClockStamp,
                evidence_clock: engine.ClockStamp,
                decision_clock: engine.ClockStamp, close_decision_id: str) -> Transition:
    """Price the full-token sell on a new post-target observation, then decide ATA close."""
    _assert_runtime(transition.position, runtime)
    _sha64(close_decision_id, "ATA-close decision id")
    if transition.state is not VenueState.SELL_DECIDED or transition.sell_target_unix_nanos is None:
        raise RefusedExecution("PumpSwap sell landing is out of transition order")
    _validate_observation(transition, runtime, observation, request_clock, evidence_clock,
                          transition.sell_target_unix_nanos)
    if (observation.context_slot < (transition.sell_decision_context_slot or 0)
            or observation.pool != transition.pumpswap_pool
            or observation.base_vault != transition.pumpswap_base_vault
            or observation.quote_vault != transition.pumpswap_quote_vault):
        raise RefusedExecution("PumpSwap sell landing regresses/switches the discovered pool")
    decision_ns = _validate_decision_clocks(request_clock, evidence_clock, decision_clock)
    if decision_ns >= transition.deadline_unix_nanos:
        return expire(transition, decision_unix_nanos=decision_ns)
    quote = sell_quote(transition.position.token_atoms, observation.reserves)
    wallet_proceeds = quote["net_quote_lamports"] - runtime.exit_attempt_cost.attempt_cost_lamports
    if wallet_proceeds <= 0:
        raise PriceUnavailable("PumpSwap full-token sell is net-nonpositive after route costs")
    return replace(
        transition, state=VenueState.AWAITING_ATA_CLOSE,
        wallet_proceeds_lamports=wallet_proceeds,
        close_decision_id=close_decision_id,
        close_target_unix_nanos=clocking.landing_target(
            decision_unix_nanos=decision_ns,
            calibrated_p90_nanos=runtime.calibrated_p90_nanos))


def close_landed(transition: Transition, runtime: engine.ArmRuntime,
                 evidence: CloseEvidence) -> Transition:
    """Settle proceeds; rent returns only when independent close evidence says success."""
    _assert_runtime(transition.position, runtime)
    if transition.state is not VenueState.AWAITING_ATA_CLOSE:
        raise RefusedExecution("ATA-close landing is out of transition order")
    if (evidence.mint != transition.position.mint
            or evidence.entry_id != transition.position.entry_id
            or evidence.full_sale_token_atoms != transition.position.token_atoms
            or evidence.decision_id != transition.close_decision_id
            or evidence.target_unix_nanos != transition.close_target_unix_nanos):
        raise RefusedExecution("ATA-close evidence does not bind the full sale/decision")
    primary = accounting.settled_equity(
        wallet_proceeds_lamports=transition.wallet_proceeds_lamports or 0,
        ata_rent_lamports=transition.position.ata_rent_lamports,
        ata_close_cost_lamports=0,
        failed_attempt_cost_lamports=(transition.position.failed_exit_cost_lamports
                                      + transition.failed_attempt_cost_lamports),
        ata_close_succeeded=False)
    modeled = accounting.settled_equity(
        wallet_proceeds_lamports=transition.wallet_proceeds_lamports or 0,
        ata_rent_lamports=transition.position.ata_rent_lamports,
        ata_close_cost_lamports=runtime.ata_close_attempt_cost.attempt_cost_lamports,
        failed_attempt_cost_lamports=(transition.position.failed_exit_cost_lamports
                                      + transition.failed_attempt_cost_lamports),
        ata_close_succeeded=evidence.succeeded)
    return replace(
        transition, state=VenueState.TERMINAL,
        terminal_equity_lamports=primary.equity_lamports,
        terminal_reason="PUMPSWAP_FULL_SELL_PRIMARY_RENT_LOCKED",
        ata_rent_reclaimed=False,
        modeled_close_equity_lamports=modeled.equity_lamports)


def record_failed_sell_attempt(transition: Transition, runtime: engine.ArmRuntime, *,
                               landed_clock: engine.ClockStamp) -> Transition:
    """Charge a landed-but-unfilled sell once and return to bounded pool discovery."""
    _assert_runtime(transition.position, runtime)
    if transition.state is not VenueState.SELL_DECIDED or transition.sell_target_unix_nanos is None:
        raise RefusedExecution("failed PumpSwap sell is out of transition order")
    if landed_clock.wall_unix_nanos < transition.sell_target_unix_nanos:
        raise RefusedExecution("failed PumpSwap sell evidence predates target")
    if landed_clock.wall_unix_nanos >= transition.deadline_unix_nanos:
        return expire(transition, decision_unix_nanos=landed_clock.wall_unix_nanos)
    return replace(
        transition, state=VenueState.AWAITING_POOL,
        next_observation_not_before_unix_nanos=landed_clock.wall_unix_nanos + 1,
        failed_attempt_cost_lamports=(transition.failed_attempt_cost_lamports
                                      + runtime.exit_attempt_cost.attempt_cost_lamports),
        sell_decision_id=None, sell_target_unix_nanos=None, sell_observation_sha256=None)


def expire(transition: Transition, *, decision_unix_nanos: int) -> Transition:
    if transition.state is VenueState.TERMINAL:
        raise RefusedExecution("terminal venue transition cannot settle twice")
    if type(decision_unix_nanos) is not int or decision_unix_nanos < transition.deadline_unix_nanos:
        raise RefusedExecution("cross-venue full loss cannot precede the frozen deadline")
    if transition.state is VenueState.AWAITING_ATA_CLOSE:
        # The full-token sale already moved cash into the wallet. A close timeout can strand rent;
        # it cannot erase sale proceeds into an atomic-rug/full-loss label.
        equity = ((transition.wallet_proceeds_lamports or 0)
                  - transition.position.failed_exit_cost_lamports
                  - transition.failed_attempt_cost_lamports)
        if equity <= 0:
            raise RefusedExecution("sold PumpSwap proceeds are net-nonpositive after prior attempts")
        return replace(
            transition, state=VenueState.TERMINAL, terminal_equity_lamports=equity,
            terminal_reason="PUMPSWAP_SOLD_ATA_CLOSE_TIMEOUT_RENT_LOCKED",
            ata_rent_reclaimed=False)
    return replace(transition, state=VenueState.TERMINAL,
                   terminal_equity_lamports=0,
                   terminal_reason="CROSS_VENUE_DEADLINE_FULL_LOSS",
                   ata_rent_reclaimed=False)


def _validate_decision_clocks(request: engine.ClockStamp, evidence: engine.ClockStamp,
                              decision: engine.ClockStamp) -> int:
    if (len({request.boot_id, evidence.boot_id, decision.boot_id}) != 1
            or not request.monotonic_nanos <= evidence.monotonic_nanos <= decision.monotonic_nanos):
        raise RefusedExecution("venue decision clocks cross boot or go backwards")
    return clocking.decision_after_evidence(
        lambda: decision.wall_unix_nanos, [evidence.wall_unix_nanos])


def _validate_observation(transition: Transition, runtime: engine.ArmRuntime,
                          observation: PumpSwapObservation,
                          request_clock: engine.ClockStamp,
                          evidence_clock: engine.ClockStamp, not_before: int) -> None:
    if not isinstance(observation, PumpSwapObservation):
        raise RefusedExecution("venue observation is untyped")
    if (observation.mint != transition.position.mint
            or observation.endpoint_scheme_host != runtime.observe_endpoint_identity
            or observation.context_slot < transition.position.last_context_slot):
        raise RefusedExecution("PumpSwap observation differs from route/position")
    if (observation.response_received_unix_nanos > evidence_clock.wall_unix_nanos
            or observation.request_started_unix_nanos < not_before
            or observation.request_started_unix_nanos < request_clock.wall_unix_nanos
            or request_clock.wall_unix_nanos < not_before
            or observation.response_received_unix_nanos < not_before
            or evidence_clock.wall_unix_nanos < not_before
            or request_clock.boot_id != evidence_clock.boot_id
            or request_clock.monotonic_nanos > evidence_clock.monotonic_nanos):
        raise RefusedExecution("PumpSwap observation is not a causal post-target receipt")
