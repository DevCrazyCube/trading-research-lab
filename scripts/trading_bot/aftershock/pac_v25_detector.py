#!/usr/bin/env python3
"""PAC V2.5 paid-overshoot and graduation-runway entry qualification.

Pure, causal and intentionally narrow: the prior single-sell PAC setup is retained, but the
recovered reserve must subsequently absorb one additional probe of net paid quote for a full
processed-p90 window.  The remaining token reserve must also cover the modeled entry plus two of
the largest token-depletion windows observed over that same latency horizon.
"""
from __future__ import annotations

from dataclasses import dataclass

from .execution import IntentKind, OrderIntent, PriceUnavailable
from .feasibility import kernel_accounting
from . import pac_detector
from . import pac_v2_detector
from .pac_v2_feed import ClockedEvent


BUYER_BREADTH_MIN = 3
RESERVE_SHOCK_COVER_MULTIPLE = 6
RUNWAY_WINDOWS = 2


@dataclass(frozen=True)
class Qualification:
    evidence_indices: tuple[int, ...]
    evidence_event_ids: tuple[str, ...]
    shock_index: int
    paid_recovery_index: int
    dwell_nanos: int
    buyer_breadth_ex_seller: int
    shock_seller: str
    shock_lamports: int
    pre_shock_reserve_lamports: int
    paid_floor_lamports: int
    reserve_cover_lamports: int
    decision_tokens_out: int
    max_latency_token_depletion: int
    runway_required_token_atoms: int


def _max_token_depletion(events: tuple[ClockedEvent, ...], horizon_nanos: int) -> int:
    """Largest causal real-token depletion inside any observed horizon-length window."""
    largest = 0
    for left, start in enumerate(events):
        floor = start.pre_state.real_token
        for event in events[left:]:
            if event.source_received_unix_nanos - start.source_received_unix_nanos > horizon_nanos:
                break
            largest = max(largest, floor - event.post_state.real_token)
    return max(0, largest)


def qualify(events: tuple[ClockedEvent, ...], *, processed_p90_nanos: int,
            quote_input_lamports: int) -> Qualification | None:
    if (type(processed_p90_nanos) is not int or processed_p90_nanos <= 0
            or type(quote_input_lamports) is not int or quote_input_lamports <= 0
            or not pac_v2_detector._valid_stream(events)):
        return None
    latest = events[-1]
    for shock_index in range(len(events) - 2, -1, -1):
        shock = events[shock_index]
        shock_lamports = shock.pre_state.real_quote - shock.post_state.real_quote
        if shock.side != "sell" or shock_lamports < quote_input_lamports:
            continue
        pre_shock = shock.pre_state.real_quote
        paid_floor = pre_shock + quote_input_lamports
        paid_recovery = next((index for index in range(shock_index + 1, len(events))
                              if events[index].post_state.real_quote >= paid_floor), None)
        if paid_recovery is None:
            continue
        dwell = latest.source_received_unix_nanos - events[paid_recovery].source_received_unix_nanos
        span = latest.source_received_unix_nanos - shock.source_received_unix_nanos
        if dwell < processed_p90_nanos or span > pac_detector.MAX_PATTERN_SPAN_NANOS:
            continue
        if any(event.post_state.real_quote < paid_floor for event in events[paid_recovery:]):
            continue
        buyers = {event.trader for event in events[shock_index + 1:]
                  if event.side == "buy" and event.trader != shock.trader}
        if len(buyers) < BUYER_BREADTH_MIN:
            continue
        cover = RESERVE_SHOCK_COVER_MULTIPLE * max(quote_input_lamports, shock_lamports)
        premise_floor = max(paid_floor, cover)
        if latest.post_state.real_quote < premise_floor:
            continue
        try:
            decision_quote = kernel_accounting(
                latest.post_state,
                OrderIntent(IntentKind.EXACT_QUOTE_BUY, quote_input_lamports, 1))
        except PriceUnavailable:
            continue
        depletion = _max_token_depletion(events[shock_index:], processed_p90_nanos)
        runway = decision_quote["out_amount"] + RUNWAY_WINDOWS * depletion
        if latest.post_state.real_token < runway:
            continue
        evidence = tuple(range(shock_index, len(events)))
        return Qualification(
            evidence_indices=evidence,
            evidence_event_ids=tuple(events[index].event_id for index in evidence),
            shock_index=shock_index, paid_recovery_index=paid_recovery, dwell_nanos=dwell,
            buyer_breadth_ex_seller=len(buyers), shock_seller=shock.trader,
            shock_lamports=shock_lamports, pre_shock_reserve_lamports=pre_shock,
            paid_floor_lamports=paid_floor, reserve_cover_lamports=premise_floor,
            decision_tokens_out=decision_quote["out_amount"],
            max_latency_token_depletion=depletion, runway_required_token_atoms=runway)
    return None
