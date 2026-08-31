#!/usr/bin/env python3
"""Provider-isolated causal position-service kernel for PAC_SCALP_LL (paper scenario only)."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, replace
import hashlib
import json
import pathlib
import time
from typing import Callable, Mapping

from .execution import IntentKind, OrderIntent, PriceUnavailable, RefusedExecution, ReserveState
from .feasibility import kernel_accounting
from .pac_v2_snapshot import LandingSnapshot, SnapshotUnavailable
from . import pac_scalp_ll_accounting as accounting
from . import pac_scalp_ll_clock as clocking
from . import pac_scalp_ll_policy as policy
from . import pac_scalp_ll_route as routes


CURVE_FAILURES_REQUIRING_CROSS_VENUE = frozenset({
    "OBSERVED_STATE_UNPRICEABLE", "EXIT_SNAPSHOT_PERMANENT_REFUSAL",
    "UNAVAILABLE_OR_NET_NEGATIVE_DUST", "HORIZON_SNAPSHOT_DEADLINE_ELAPSED",
    "HORIZON_SLIPPAGE_FAILURE", "CURVE_COMPLETE_OR_ZEROED",
    "CURVE_OBSERVATION_UNAVAILABLE",
})
MAX_WRAPPER_RECEIPT_LAG_NANOS = 1_000_000_000
try:
    BOOT_ID = pathlib.Path("/proc/sys/kernel/random/boot_id").read_text().strip()
except OSError:
    BOOT_ID = "BOOT_ID_UNAVAILABLE"


@dataclass(frozen=True)
class ClockStamp:
    wall_unix_nanos: int
    monotonic_nanos: int
    boot_id: str

    def __post_init__(self) -> None:
        if (type(self.wall_unix_nanos) is not int or self.wall_unix_nanos < 0
                or type(self.monotonic_nanos) is not int or self.monotonic_nanos < 0
                or not isinstance(self.boot_id, str) or not self.boot_id):
            raise RefusedExecution("clock stamp is invalid")


def clock_stamp() -> ClockStamp:
    return ClockStamp(time.time_ns(), time.monotonic_ns(), BOOT_ID)


@dataclass(frozen=True)
class ArmRuntime:
    arm: str
    provider_id: str
    calibrated_p90_nanos: int
    calibration_sha256: str
    campaign_sha256: str
    submit_endpoint_identity: str
    observe_endpoint_identity: str
    config_fingerprint_sha256: str
    entry_attempt_cost: routes.AttemptCost
    exit_attempt_cost: routes.AttemptCost
    ata_close_attempt_cost: routes.AttemptCost

    def __post_init__(self) -> None:
        if self.arm not in routes.ARMS or not isinstance(self.provider_id, str) or not self.provider_id:
            raise RefusedExecution("arm runtime identity is invalid")
        if type(self.calibrated_p90_nanos) is not int or self.calibrated_p90_nanos <= 0:
            raise RefusedExecution("arm runtime lacks a positive measured p90")
        for value in (self.calibration_sha256, self.campaign_sha256,
                      self.config_fingerprint_sha256):
            if (not isinstance(value, str) or len(value) != 64
                    or any(c not in "0123456789abcdef" for c in value)):
                raise RefusedExecution("arm runtime evidence hash is invalid")
        if not all(isinstance(value, str) and value.startswith("https://") for value in (
                self.submit_endpoint_identity, self.observe_endpoint_identity)):
            raise RefusedExecution("arm runtime endpoint identity is invalid")
        if not isinstance(self.entry_attempt_cost, routes.AttemptCost) \
                or not isinstance(self.exit_attempt_cost, routes.AttemptCost) \
                or not isinstance(self.ata_close_attempt_cost, routes.AttemptCost):
            raise RefusedExecution("arm runtime lacks typed all-cost attempts")


@dataclass(frozen=True)
class Position:
    mint: str
    token_atoms: int
    quote_input_lamports: int
    entry_curve_fee_lamports: int
    entry_attempt_cost_lamports: int
    ata_rent_lamports: int
    entry_all_in_lamports: int
    entry_unix_nanos: int
    peak_liquidation_equity_lamports: int
    failed_exit_cost_lamports: int
    entry_id: str
    last_context_slot: int
    last_state: dict
    arm: str
    provider_id: str
    calibration_sha256: str
    campaign_sha256: str
    submit_endpoint_identity: str
    observe_endpoint_identity: str
    config_fingerprint_sha256: str
    entry_cost_profile_sha256: str
    exit_cost_profile_sha256: str
    ata_close_cost_profile_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.mint, str) or not self.mint or self.arm not in routes.ARMS:
            raise RefusedExecution("position identity/arm is invalid")
        if not isinstance(self.provider_id, str) or not self.provider_id:
            raise RefusedExecution("position provider is invalid")
        for value in (self.calibration_sha256, self.campaign_sha256, self.entry_id,
                      self.config_fingerprint_sha256, self.entry_cost_profile_sha256,
                      self.exit_cost_profile_sha256, self.ata_close_cost_profile_sha256):
            if (not isinstance(value, str) or len(value) != 64
                    or any(c not in "0123456789abcdef" for c in value)):
                raise RefusedExecution("position evidence id/hash is invalid")
        if not all(isinstance(value, str) and value.startswith("https://") for value in (
                self.submit_endpoint_identity, self.observe_endpoint_identity)):
            raise RefusedExecution("position endpoint identity is invalid")
        for name in ("token_atoms", "quote_input_lamports", "entry_all_in_lamports"):
            if type(getattr(self, name)) is not int or getattr(self, name) <= 0:
                raise RefusedExecution(f"position {name} is invalid")
        for name in ("entry_curve_fee_lamports", "entry_attempt_cost_lamports",
                     "ata_rent_lamports", "entry_unix_nanos",
                     "peak_liquidation_equity_lamports", "failed_exit_cost_lamports",
                     "last_context_slot"):
            if type(getattr(self, name)) is not int or getattr(self, name) < 0:
                raise RefusedExecution(f"position {name} is invalid")
        if self.entry_all_in_lamports != (self.quote_input_lamports
                                         + self.entry_curve_fee_lamports
                                         + self.entry_attempt_cost_lamports
                                         + self.ata_rent_lamports):
            raise RefusedExecution("position entry all-cost does not reconcile")
        try:
            ReserveState(**self.last_state)
        except (TypeError, ValueError, RefusedExecution) as exc:
            raise RefusedExecution("position reserve state is invalid") from exc


@dataclass(frozen=True)
class ProviderBinding:
    route: routes.Route
    calibration_sha256: str
    campaign_sha256: str
    provider: object

    def __post_init__(self) -> None:
        if not hasattr(self.provider, "capture"):
            raise RefusedExecution("provider binding has no capture method")
        for value in (self.calibration_sha256, self.campaign_sha256):
            if not isinstance(value, str) or len(value) != 64:
                raise RefusedExecution("provider binding hash is invalid")

    def assert_runtime(self, runtime: ArmRuntime) -> None:
        if (runtime.arm != self.route.arm or runtime.provider_id != self.route.provider_id
                or runtime.submit_endpoint_identity != self.route.submit_endpoint_identity
                or runtime.observe_endpoint_identity != self.route.observe_endpoint_identity
                or runtime.config_fingerprint_sha256 != self.route.config_fingerprint_sha256
                or runtime.calibration_sha256 != self.calibration_sha256
                or runtime.campaign_sha256 != self.campaign_sha256):
            raise RefusedExecution("provider binding does not match assigned arm runtime")


@dataclass(frozen=True)
class ServiceDecision:
    mint: str
    action: str
    decision_clock: ClockStamp
    target_unix_nanos: int | None
    request_clock: ClockStamp
    evidence_clock: ClockStamp
    provider_response_unix_nanos: int | None
    context_slot: int | None
    raw_evidence_sha256: str | None
    reserve_state: dict | None
    gross_quote_lamports: int | None
    wallet_proceeds_lamports: int | None
    liquidation_equity_lamports: int | None
    peak_liquidation_equity_lamports: int
    reason: str | None
    arm: str
    provider_id: str
    calibration_sha256: str
    campaign_sha256: str
    observe_endpoint_identity: str
    exit_attempt_all_cost_lamports: int
    ata_close_all_cost_lamports: int


@dataclass(frozen=True)
class EntryOrder:
    mint: str
    quote_input_lamports: int
    min_tokens_out: int
    decision_id: str
    decision_clock: ClockStamp
    evidence_clock: ClockStamp
    target_unix_nanos: int
    minimum_context_slot: int
    evidence_sha256: str
    arm: str
    provider_id: str
    calibration_sha256: str
    campaign_sha256: str
    calibrated_p90_nanos: int
    observe_endpoint_identity: str
    config_fingerprint_sha256: str
    decision_state: dict
    decision_tokens_out: int
    slippage_bps: int

    def __post_init__(self) -> None:
        if (self.arm not in routes.ARMS or type(self.quote_input_lamports) is not int
                or self.quote_input_lamports <= 0 or type(self.min_tokens_out) is not int
                or self.min_tokens_out <= 0 or type(self.calibrated_p90_nanos) is not int
                or self.calibrated_p90_nanos <= 0 or type(self.decision_tokens_out) is not int
                or self.decision_tokens_out <= 0 or type(self.slippage_bps) is not int
                or not 0 <= self.slippage_bps < 10_000
                or self.target_unix_nanos != (self.decision_clock.wall_unix_nanos
                                              + self.calibrated_p90_nanos)
                or self.min_tokens_out != max(
                    1, self.decision_tokens_out * (10_000 - self.slippage_bps) // 10_000)):
            raise RefusedExecution("entry order economics/target are invalid")
        if (self.evidence_clock.boot_id != self.decision_clock.boot_id
                or self.decision_clock.monotonic_nanos < self.evidence_clock.monotonic_nanos
                or self.decision_clock.wall_unix_nanos < self.evidence_clock.wall_unix_nanos):
            raise RefusedExecution("entry order decision/evidence clocks are invalid")
        try:
            state = ReserveState(**self.decision_state)
            quote = kernel_accounting(
                state, OrderIntent(IntentKind.EXACT_QUOTE_BUY, self.quote_input_lamports, 1))
        except (TypeError, PriceUnavailable) as exc:
            raise RefusedExecution("entry order decision state is invalid") from exc
        if quote["out_amount"] != self.decision_tokens_out:
            raise RefusedExecution("entry order quote differs from its decision state")
        expected_id = _hash({
            "kind": "PAC_SCALP_LL_ENTRY", "mint": self.mint,
            "quote": self.quote_input_lamports, "evidence": self.evidence_sha256,
            "decision": self.decision_clock.wall_unix_nanos, "arm": self.arm,
            "provider": self.provider_id, "calibration": self.calibration_sha256,
            "campaign": self.campaign_sha256, "minimum_context_slot": self.minimum_context_slot,
            "min_tokens_out": self.min_tokens_out, "target": self.target_unix_nanos,
            "config": self.config_fingerprint_sha256})
        if self.decision_id != expected_id:
            raise RefusedExecution("entry order decision id does not bind all fields")


@dataclass(frozen=True)
class CurveExitOrder:
    position: Position
    action: str
    min_gross_quote_lamports: int
    decision_id: str
    decision_clock: ClockStamp
    target_unix_nanos: int
    evidence_clock: ClockStamp
    decision_gross_quote_lamports: int
    calibrated_p90_nanos: int
    minimum_context_slot: int

    def __post_init__(self) -> None:
        if (self.action not in {action.value for action in policy.ExitAction
                               if action is not policy.ExitAction.HOLD}
                or type(self.min_gross_quote_lamports) is not int
                or self.min_gross_quote_lamports <= 0
                or type(self.minimum_context_slot) is not int
                or self.minimum_context_slot < 0
                or self.target_unix_nanos != (self.decision_clock.wall_unix_nanos
                                              + self.calibrated_p90_nanos)
                or self.evidence_clock.boot_id != self.decision_clock.boot_id
                or self.decision_clock.monotonic_nanos < self.evidence_clock.monotonic_nanos):
            raise RefusedExecution("curve exit order fields/clocks are invalid")
        expected = _hash({"entry": self.position.entry_id, "action": self.action,
                          "decision": self.decision_clock.wall_unix_nanos,
                          "gross": self.decision_gross_quote_lamports,
                          "target": self.target_unix_nanos,
                          "min_slot": self.minimum_context_slot})
        if self.decision_id != expected:
            raise RefusedExecution("curve exit order id does not bind its target/economics")


@dataclass(frozen=True)
class CurveSale:
    position: Position
    action: str
    decision_id: str
    attempt_id: str
    target_unix_nanos: int
    landing_clock: ClockStamp
    wallet_proceeds_lamports: int
    gross_quote_lamports: int
    curve_fee_lamports: int
    close_decision_id: str
    close_target_unix_nanos: int


@dataclass(frozen=True)
class CurveCloseEvidence:
    mint: str
    entry_id: str
    full_sale_token_atoms: int
    close_decision_id: str
    close_attempt_id: str
    target_unix_nanos: int
    landed_clock: ClockStamp
    succeeded: bool
    evidence_mode: str = "MODELED_PAPER_ATA_CLOSE_SCENARIO_NOT_EXECUTABLE"


@dataclass(frozen=True)
class AttemptFailure:
    stage: str
    mint: str
    decision_id: str
    attempt_id: str
    arm: str
    provider_id: str
    landed_clock: ClockStamp
    charged_lamports: int
    reason: str

    def __post_init__(self) -> None:
        if self.stage not in {"ENTRY", "CURVE_EXIT", "PUMPSWAP_EXIT", "ATA_CLOSE"}:
            raise RefusedExecution("failed-attempt stage is invalid")
        if (not all(isinstance(value, str) and value for value in (
                self.mint, self.arm, self.provider_id, self.reason))
                or not all(isinstance(value, str) and len(value) == 64
                           and all(c in "0123456789abcdef" for c in value)
                           for value in (self.decision_id, self.attempt_id))
                or type(self.charged_lamports) is not int or self.charged_lamports < 0):
            raise RefusedExecution("failed-attempt evidence is invalid")


def failed_entry_attempt(order: EntryOrder, runtime: ArmRuntime, *, attempt_id: str,
                         landed_clock: ClockStamp, reason: str) -> AttemptFailure:
    if (not isinstance(order, EntryOrder) or order.arm != runtime.arm
            or order.provider_id != runtime.provider_id
            or landed_clock.boot_id != order.decision_clock.boot_id
            or landed_clock.monotonic_nanos <= order.decision_clock.monotonic_nanos
            or landed_clock.wall_unix_nanos < order.target_unix_nanos):
        raise RefusedExecution("failed entry attempt is non-causal/route-mismatched")
    return AttemptFailure("ENTRY", order.mint, order.decision_id, attempt_id,
                          runtime.arm, runtime.provider_id, landed_clock,
                          runtime.entry_attempt_cost.all_cost_lamports, reason)


def failed_curve_exit_attempt(order: CurveExitOrder, runtime: ArmRuntime, *, attempt_id: str,
                              landed_clock: ClockStamp, reason: str) -> tuple[Position, AttemptFailure]:
    assert_position_runtime(order.position, runtime)
    if (landed_clock.boot_id != order.decision_clock.boot_id
            or landed_clock.monotonic_nanos <= order.decision_clock.monotonic_nanos
            or landed_clock.wall_unix_nanos < order.target_unix_nanos):
        raise RefusedExecution("failed curve exit attempt is non-causal")
    failure = AttemptFailure(
        "CURVE_EXIT", order.position.mint, order.decision_id, attempt_id,
        runtime.arm, runtime.provider_id, landed_clock,
        runtime.exit_attempt_cost.attempt_cost_lamports, reason)
    return (replace(
        order.position,
        failed_exit_cost_lamports=(order.position.failed_exit_cost_lamports
                                   + failure.charged_lamports)), failure)


def _hash(value: object) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


def cost_profile_sha256(value: routes.AttemptCost) -> str:
    if not isinstance(value, routes.AttemptCost):
        raise RefusedExecution("cost profile is untyped")
    return _hash(asdict(value))


def assert_position_runtime(position: Position, runtime: ArmRuntime) -> None:
    if (position.arm != runtime.arm or position.provider_id != runtime.provider_id
            or position.calibration_sha256 != runtime.calibration_sha256
            or position.campaign_sha256 != runtime.campaign_sha256
            or position.submit_endpoint_identity != runtime.submit_endpoint_identity
            or position.observe_endpoint_identity != runtime.observe_endpoint_identity
            or position.config_fingerprint_sha256 != runtime.config_fingerprint_sha256
            or position.entry_cost_profile_sha256 != cost_profile_sha256(runtime.entry_attempt_cost)
            or position.exit_cost_profile_sha256 != cost_profile_sha256(runtime.exit_attempt_cost)
            or position.ata_close_cost_profile_sha256
            != cost_profile_sha256(runtime.ata_close_attempt_cost)):
        raise RefusedExecution("position is bound to a different route/calibration/cost profile")


def make_entry_order(*, mint: str, quote_input_lamports: int, decision_state: ReserveState,
                     minimum_context_slot: int, evidence_sha256: str,
                     evidence_clock: ClockStamp, decision_clock: ClockStamp,
                     runtime: ArmRuntime, slippage_bps: int = 500) -> EntryOrder:
    """Create an entry intent from decision-time evidence; it is not a fill."""
    if (not isinstance(mint, str) or not mint or type(quote_input_lamports) is not int
            or quote_input_lamports <= 0 or not isinstance(decision_state, ReserveState)
            or type(minimum_context_slot) is not int or minimum_context_slot < 0
            or not isinstance(evidence_sha256, str) or len(evidence_sha256) != 64
            or any(c not in "0123456789abcdef" for c in evidence_sha256)
            or type(slippage_bps) is not int or not 0 <= slippage_bps < 10_000):
        raise RefusedExecution("entry decision inputs are invalid")
    decision_ns = clocking.decision_after_evidence(
        lambda: decision_clock.wall_unix_nanos, [evidence_clock.wall_unix_nanos])
    if (evidence_clock.boot_id != decision_clock.boot_id
            or decision_clock.monotonic_nanos < evidence_clock.monotonic_nanos):
        raise RefusedExecution("entry decision clocks cross boot or go backwards")
    quote = kernel_accounting(
        decision_state, OrderIntent(IntentKind.EXACT_QUOTE_BUY, quote_input_lamports, 1))
    minimum = max(1, quote["out_amount"] * (10_000 - slippage_bps) // 10_000)
    target = clocking.landing_target(decision_unix_nanos=decision_ns,
                                     calibrated_p90_nanos=runtime.calibrated_p90_nanos)
    decision_id = _hash({
        "kind": "PAC_SCALP_LL_ENTRY", "mint": mint, "quote": quote_input_lamports,
        "evidence": evidence_sha256, "decision": decision_ns, "arm": runtime.arm,
        "provider": runtime.provider_id, "calibration": runtime.calibration_sha256,
        "campaign": runtime.campaign_sha256, "minimum_context_slot": minimum_context_slot,
        "min_tokens_out": minimum, "target": target,
        "config": runtime.config_fingerprint_sha256})
    return EntryOrder(
        mint=mint, quote_input_lamports=quote_input_lamports, min_tokens_out=minimum,
        decision_id=decision_id, decision_clock=decision_clock, evidence_clock=evidence_clock,
        target_unix_nanos=target, minimum_context_slot=minimum_context_slot,
        evidence_sha256=evidence_sha256, arm=runtime.arm, provider_id=runtime.provider_id,
        calibration_sha256=runtime.calibration_sha256, campaign_sha256=runtime.campaign_sha256,
        calibrated_p90_nanos=runtime.calibrated_p90_nanos,
        observe_endpoint_identity=runtime.observe_endpoint_identity,
        config_fingerprint_sha256=runtime.config_fingerprint_sha256,
        decision_state=asdict(decision_state), decision_tokens_out=quote["out_amount"],
        slippage_bps=slippage_bps)


def land_entry(order: EntryOrder, runtime: ArmRuntime, snapshot: LandingSnapshot, *,
               request_clock: ClockStamp, evidence_clock: ClockStamp,
               landing_clock: ClockStamp) -> Position:
    """Fill an entry only from a fresh assigned-provider snapshot at/after its target."""
    if not isinstance(order, EntryOrder) or not isinstance(snapshot, LandingSnapshot):
        raise RefusedExecution("entry landing requires typed order/snapshot")
    if (order.arm != runtime.arm or order.provider_id != runtime.provider_id
            or order.calibration_sha256 != runtime.calibration_sha256
            or order.campaign_sha256 != runtime.campaign_sha256
            or order.observe_endpoint_identity != runtime.observe_endpoint_identity
            or order.config_fingerprint_sha256 != runtime.config_fingerprint_sha256
            or snapshot.mint != order.mint
            or snapshot.endpoint_scheme_host != runtime.observe_endpoint_identity
            or snapshot.context_slot < order.minimum_context_slot
            or snapshot.modeled_target_unix_nanos != order.target_unix_nanos
            or snapshot.request_started_unix_nanos < order.target_unix_nanos
            or snapshot.response_received_unix_nanos < order.target_unix_nanos
            or snapshot.response_received_unix_nanos > evidence_clock.wall_unix_nanos
            or snapshot.request_started_unix_nanos < request_clock.wall_unix_nanos
            or request_clock.wall_unix_nanos < order.target_unix_nanos
            or landing_clock.wall_unix_nanos < evidence_clock.wall_unix_nanos
            or len({order.decision_clock.boot_id, request_clock.boot_id,
                    evidence_clock.boot_id, landing_clock.boot_id}) != 1
            or not (order.decision_clock.monotonic_nanos < request_clock.monotonic_nanos
                    <= evidence_clock.monotonic_nanos <= landing_clock.monotonic_nanos)):
        raise RefusedExecution("entry landing is non-causal or route-mismatched")
    quote = kernel_accounting(
        snapshot.state, OrderIntent(IntentKind.EXACT_QUOTE_BUY, order.quote_input_lamports,
                                    order.min_tokens_out))
    if quote["out_amount"] < order.min_tokens_out:
        raise PriceUnavailable("entry landing violates frozen min_tokens_out")
    all_in = (order.quote_input_lamports + quote["curve_fee_lamports"]
              + runtime.entry_attempt_cost.all_cost_lamports + quote["ata_rent_lamports"])
    entry_id = _hash({"decision_id": order.decision_id,
                      "landing_evidence": snapshot.raw_response_sha256,
                      "landing": landing_clock.wall_unix_nanos,
                      "tokens": quote["out_amount"]})
    return Position(
        mint=order.mint, token_atoms=quote["out_amount"],
        quote_input_lamports=order.quote_input_lamports,
        entry_curve_fee_lamports=quote["curve_fee_lamports"],
        entry_attempt_cost_lamports=runtime.entry_attempt_cost.all_cost_lamports,
        ata_rent_lamports=quote["ata_rent_lamports"], entry_all_in_lamports=all_in,
        entry_unix_nanos=landing_clock.wall_unix_nanos,
        peak_liquidation_equity_lamports=0, failed_exit_cost_lamports=0,
        entry_id=entry_id, last_context_slot=snapshot.context_slot,
        last_state=asdict(snapshot.state), arm=runtime.arm, provider_id=runtime.provider_id,
        calibration_sha256=runtime.calibration_sha256,
        campaign_sha256=runtime.campaign_sha256,
        submit_endpoint_identity=runtime.submit_endpoint_identity,
        observe_endpoint_identity=runtime.observe_endpoint_identity,
        config_fingerprint_sha256=runtime.config_fingerprint_sha256,
        entry_cost_profile_sha256=cost_profile_sha256(runtime.entry_attempt_cost),
        exit_cost_profile_sha256=cost_profile_sha256(runtime.exit_attempt_cost),
        ata_close_cost_profile_sha256=cost_profile_sha256(runtime.ata_close_attempt_cost))


def make_curve_exit_order(position: Position, decision: ServiceDecision, *,
                          slippage_bps: int = 500) -> CurveExitOrder:
    if (not isinstance(position, Position) or not isinstance(decision, ServiceDecision)
            or decision.action not in {action.value for action in policy.ExitAction if action is not policy.ExitAction.HOLD}
            or decision.target_unix_nanos is None or decision.gross_quote_lamports is None
            or decision.context_slot is None
            or type(slippage_bps) is not int or not 0 <= slippage_bps < 10_000):
        raise RefusedExecution("curve exit decision is not executable")
    if (decision.mint != position.mint or decision.arm != position.arm
            or decision.provider_id != position.provider_id):
        raise RefusedExecution("curve exit decision differs from position")
    minimum = max(1, decision.gross_quote_lamports * (10_000 - slippage_bps) // 10_000)
    decision_id = _hash({"entry": position.entry_id, "action": decision.action,
                         "decision": decision.decision_clock.wall_unix_nanos,
                         "gross": decision.gross_quote_lamports,
                         "target": decision.target_unix_nanos,
                         "min_slot": decision.context_slot})
    return CurveExitOrder(position, decision.action, minimum, decision_id,
                          decision.decision_clock, decision.target_unix_nanos,
                          decision.evidence_clock, decision.gross_quote_lamports,
                          decision.target_unix_nanos - decision.decision_clock.wall_unix_nanos,
                          decision.context_slot)


def land_curve_exit(order: CurveExitOrder, runtime: ArmRuntime, snapshot: LandingSnapshot, *,
                    request_clock: ClockStamp, evidence_clock: ClockStamp,
                    landing_clock: ClockStamp,
                    attempt_id: str, close_decision_id: str) -> CurveSale:
    """Fill the curve exit from a distinct post-target snapshot, then open ATA-close intent."""
    if not isinstance(order, CurveExitOrder):
        raise RefusedExecution("curve exit landing requires typed order")
    for value in (attempt_id, close_decision_id):
        if (not isinstance(value, str) or len(value) != 64
                or any(c not in "0123456789abcdef" for c in value)):
            raise RefusedExecution("curve exit attempt/close id is invalid")
    position = order.position
    assert_position_runtime(position, runtime)
    if (snapshot.mint != position.mint
            or snapshot.endpoint_scheme_host != runtime.observe_endpoint_identity
            or snapshot.context_slot < position.last_context_slot
            or snapshot.context_slot < order.minimum_context_slot
            or snapshot.modeled_target_unix_nanos != order.target_unix_nanos
            or snapshot.request_started_unix_nanos < order.target_unix_nanos
            or snapshot.response_received_unix_nanos < order.target_unix_nanos
            or snapshot.response_received_unix_nanos > evidence_clock.wall_unix_nanos
            or snapshot.request_started_unix_nanos < request_clock.wall_unix_nanos
            or request_clock.wall_unix_nanos < order.target_unix_nanos
            or landing_clock.wall_unix_nanos < evidence_clock.wall_unix_nanos
            or len({order.decision_clock.boot_id, request_clock.boot_id,
                    evidence_clock.boot_id, landing_clock.boot_id}) != 1
            or not (order.decision_clock.monotonic_nanos < request_clock.monotonic_nanos
                    <= evidence_clock.monotonic_nanos <= landing_clock.monotonic_nanos)):
        raise RefusedExecution("curve exit landing is non-causal or route-mismatched")
    quote = kernel_accounting(
        snapshot.state, OrderIntent(IntentKind.EXACT_TOKEN_SELL, position.token_atoms,
                                    order.min_gross_quote_lamports))
    if quote["gross_quote_lamports"] < order.min_gross_quote_lamports:
        raise PriceUnavailable("curve exit landing violates frozen min_quote_out")
    wallet = (quote["gross_quote_lamports"] - quote["curve_fee_lamports"]
              - runtime.exit_attempt_cost.attempt_cost_lamports)
    if wallet <= 0:
        raise PriceUnavailable("curve exit is net-nonpositive after assigned-route costs")
    close_target = clocking.landing_target(
        decision_unix_nanos=landing_clock.wall_unix_nanos,
        calibrated_p90_nanos=runtime.calibrated_p90_nanos)
    return CurveSale(position, order.action, order.decision_id, attempt_id,
                     order.target_unix_nanos, landing_clock, wallet,
                     quote["gross_quote_lamports"], quote["curve_fee_lamports"],
                     close_decision_id, close_target)


def settle_curve_sale(sale: CurveSale, runtime: ArmRuntime,
                      evidence: CurveCloseEvidence) -> accounting.LiquidationEquity:
    """Settle a curve sale from a separate full-sale ATA-close landing."""
    if not isinstance(sale, CurveSale) or not isinstance(evidence, CurveCloseEvidence):
        raise RefusedExecution("curve sale settlement requires typed sale/close evidence")
    position = sale.position
    assert_position_runtime(position, runtime)
    if (evidence.mint != position.mint or evidence.entry_id != position.entry_id
            or evidence.full_sale_token_atoms != position.token_atoms
            or evidence.close_decision_id != sale.close_decision_id
            or evidence.target_unix_nanos != sale.close_target_unix_nanos
            or evidence.landed_clock.wall_unix_nanos < sale.close_target_unix_nanos
            or type(evidence.succeeded) is not bool):
        raise RefusedExecution("curve ATA-close evidence does not bind the full sale")
    for value in (evidence.close_decision_id, evidence.close_attempt_id):
        if (not isinstance(value, str) or len(value) != 64
                or any(c not in "0123456789abcdef" for c in value)):
            raise RefusedExecution("curve ATA-close evidence id is invalid")
    if evidence.evidence_mode != "MODELED_PAPER_ATA_CLOSE_SCENARIO_NOT_EXECUTABLE":
        raise RefusedExecution("paper ATA close cannot be relabelled executable evidence")
    # Primary P&L keeps rent locked. The in-memory boolean is a labeled scenario only and cannot
    # improve the performance series.
    return accounting.settled_equity(
        wallet_proceeds_lamports=sale.wallet_proceeds_lamports,
        ata_rent_lamports=position.ata_rent_lamports,
        ata_close_cost_lamports=0,
        failed_attempt_cost_lamports=position.failed_exit_cost_lamports,
        ata_close_succeeded=False)


def curve_failure_requires_cross_venue(reason: str) -> bool:
    if not isinstance(reason, str):
        raise RefusedExecution("curve failure reason is invalid")
    return reason in CURVE_FAILURES_REQUIRING_CROSS_VENUE


def _decision(position: Position, runtime: ArmRuntime, *, action: str,
              request_clock: ClockStamp, evidence_clock: ClockStamp, decision_clock: ClockStamp,
              snapshot: LandingSnapshot | None, gross_quote: int | None,
              wallet_proceeds: int | None,
              equity: int | None, peak: int, reason: str | None) -> ServiceDecision:
    if evidence_clock.boot_id != decision_clock.boot_id \
            or decision_clock.monotonic_nanos < evidence_clock.monotonic_nanos:
        raise RefusedExecution("decision/evidence monotonic clocks cross boot or go backwards")
    decision_ns = clocking.decision_after_evidence(
        lambda: decision_clock.wall_unix_nanos, [evidence_clock.wall_unix_nanos])
    target = None if action == policy.ExitAction.HOLD.value else clocking.landing_target(
        decision_unix_nanos=decision_ns, calibrated_p90_nanos=runtime.calibrated_p90_nanos)
    return ServiceDecision(
        position.mint, action, decision_clock, target, request_clock, evidence_clock,
        snapshot.response_received_unix_nanos if snapshot else None,
        snapshot.context_slot if snapshot else None,
        snapshot.raw_response_sha256 if snapshot else None,
        asdict(snapshot.state) if snapshot else None, gross_quote,
        wallet_proceeds, equity, peak, reason,
        runtime.arm, runtime.provider_id, runtime.calibration_sha256, runtime.campaign_sha256,
        runtime.observe_endpoint_identity, runtime.exit_attempt_cost.attempt_cost_lamports,
        runtime.ata_close_attempt_cost.attempt_cost_lamports)


def evaluate_snapshot(position: Position, runtime: ArmRuntime, snapshot: LandingSnapshot, *,
                      request_clock: ClockStamp, evidence_clock: ClockStamp,
                      decision_clock: ClockStamp) -> ServiceDecision:
    if not isinstance(position, Position) or not isinstance(snapshot, LandingSnapshot):
        raise RefusedExecution("service evaluation requires typed position and snapshot")
    assert_position_runtime(position, runtime)
    if (snapshot.endpoint_scheme_host != runtime.observe_endpoint_identity
            or snapshot.mint != position.mint
            or snapshot.context_slot < position.last_context_slot):
        raise RefusedExecution("service snapshot does not match route/position evidence")
    if (snapshot.response_received_unix_nanos > evidence_clock.wall_unix_nanos
            or evidence_clock.wall_unix_nanos - snapshot.response_received_unix_nanos
            > MAX_WRAPPER_RECEIPT_LAG_NANOS
            or snapshot.request_started_unix_nanos < request_clock.wall_unix_nanos
            or len({request_clock.boot_id, evidence_clock.boot_id,
                    decision_clock.boot_id}) != 1
            or not (request_clock.monotonic_nanos <= evidence_clock.monotonic_nanos
                    <= decision_clock.monotonic_nanos)):
        raise RefusedExecution("provider-supplied receive clock exceeds trusted wrapper receipt")
    if snapshot.state.complete or snapshot.state.real_token <= 0:
        return _decision(position, runtime, action="VENUE_TRANSITION_REQUIRED",
                         request_clock=request_clock, evidence_clock=evidence_clock,
                         decision_clock=decision_clock,
                         snapshot=snapshot, gross_quote=None, wallet_proceeds=None, equity=None,
                         peak=position.peak_liquidation_equity_lamports,
                         reason="CURVE_COMPLETE_OR_ZEROED")
    intent = OrderIntent(IntentKind.EXACT_TOKEN_SELL, position.token_atoms, 1)
    try:
        quote = kernel_accounting(snapshot.state, intent)
    except PriceUnavailable:
        return _decision(position, runtime, action="VENUE_TRANSITION_REQUIRED",
                         request_clock=request_clock, evidence_clock=evidence_clock,
                         decision_clock=decision_clock,
                         snapshot=snapshot, gross_quote=None, wallet_proceeds=None, equity=None,
                         peak=position.peak_liquidation_equity_lamports,
                         reason="UNAVAILABLE_OR_NET_NEGATIVE_DUST")
    wallet_proceeds = (quote["gross_quote_lamports"] - quote["curve_fee_lamports"]
                       - runtime.exit_attempt_cost.attempt_cost_lamports)
    if wallet_proceeds <= position.failed_exit_cost_lamports:
        return _decision(position, runtime, action="VENUE_TRANSITION_REQUIRED",
                         request_clock=request_clock, evidence_clock=evidence_clock,
                         decision_clock=decision_clock,
                         snapshot=snapshot, gross_quote=quote["gross_quote_lamports"],
                         wallet_proceeds=None, equity=None,
                         peak=position.peak_liquidation_equity_lamports,
                         reason="UNAVAILABLE_OR_NET_NEGATIVE_DUST")
    # Primary paper metric: rent remains locked because a paper ATA cannot produce real close-account
    # evidence. This conservative equity drives stop, trail, marks, and terminal P&L alike.
    equity = accounting.settled_equity(
        wallet_proceeds_lamports=wallet_proceeds,
        ata_rent_lamports=position.ata_rent_lamports,
        ata_close_cost_lamports=0,
        failed_attempt_cost_lamports=position.failed_exit_cost_lamports,
        ata_close_succeeded=False)
    pure = policy.Position(position.entry_all_in_lamports, position.entry_unix_nanos,
                           position.quote_input_lamports,
                           position.peak_liquidation_equity_lamports)
    outcome = policy.decide(pure, decision_unix_nanos=decision_clock.wall_unix_nanos,
                            liquidation_equity_lamports=equity.equity_lamports,
                            real_quote_lamports=snapshot.state.real_quote)
    return _decision(position, runtime, action=outcome.action.value,
                     request_clock=request_clock, evidence_clock=evidence_clock,
                     decision_clock=decision_clock,
                     snapshot=snapshot, gross_quote=quote["gross_quote_lamports"],
                     wallet_proceeds=wallet_proceeds,
                     equity=equity.equity_lamports,
                     peak=outcome.position.peak_liquidation_equity_lamports, reason=None)


def unavailable_decision(position: Position, runtime: ArmRuntime, *,
                         request_clock: ClockStamp, evidence_clock: ClockStamp,
                         decision_clock: ClockStamp) -> ServiceDecision:
    return _decision(position, runtime, action="VENUE_TRANSITION_REQUIRED",
                     request_clock=request_clock, evidence_clock=evidence_clock,
                     decision_clock=decision_clock,
                     snapshot=None, gross_quote=None, wallet_proceeds=None, equity=None,
                     peak=position.peak_liquidation_equity_lamports,
                     reason="CURVE_OBSERVATION_UNAVAILABLE")


def iter_service_concurrently(positions: Mapping[str, tuple[Position, ArmRuntime]],
                              providers: Mapping[str, ProviderBinding], *,
                              stamp: Callable[[], ClockStamp] = clock_stamp,
                              max_workers: int = 4):
    if not positions:
        return
    if type(max_workers) is not int or not 1 <= max_workers <= 16:
        raise RefusedExecution("position-service worker count is invalid")

    def capture(item):
        mint, (position, runtime) = item
        binding = providers.get(runtime.arm)
        if not isinstance(binding, ProviderBinding):
            raise RefusedExecution(f"no typed provider binding for arm {runtime.arm}")
        binding.assert_runtime(runtime)
        requested = stamp()
        try:
            snapshot = binding.provider.capture(mint, requested.wall_unix_nanos,
                                                position.last_context_slot)
            received = stamp()
            return mint, position, runtime, snapshot, None, requested, received
        except SnapshotUnavailable as exc:
            received = stamp()
            return mint, position, runtime, None, exc, requested, received

    with ThreadPoolExecutor(max_workers=min(max_workers, len(positions))) as pool:
        futures = [pool.submit(capture, item) for item in positions.items()]
        for future in as_completed(futures):
            mint, position, runtime, snapshot, error, requested, received = future.result()
            decided = stamp()
            if (requested.boot_id != received.boot_id or received.boot_id != decided.boot_id
                    or not requested.monotonic_nanos <= received.monotonic_nanos <= decided.monotonic_nanos):
                raise RefusedExecution("provider request/receipt/decision clock sequence is invalid")
            if error is None:
                decision = evaluate_snapshot(
                    position, runtime, snapshot, request_clock=requested,
                    evidence_clock=received, decision_clock=decided)
            else:
                decision = unavailable_decision(
                    position, runtime, request_clock=requested,
                    evidence_clock=received, decision_clock=decided)
            # Yield before waiting on any slower arm.  A runner must persist/dispatch this decision
            # before requesting the next item from the iterator.
            yield mint, decision


def service_concurrently(positions: Mapping[str, tuple[Position, ArmRuntime]],
                         providers: Mapping[str, ProviderBinding], *,
                         stamp: Callable[[], ClockStamp] = clock_stamp,
                         max_workers: int = 4) -> dict[str, ServiceDecision]:
    """Compatibility collector. Production runners must consume iter_service_concurrently directly."""
    return dict(iter_service_concurrently(
        positions, providers, stamp=stamp, max_workers=max_workers))
