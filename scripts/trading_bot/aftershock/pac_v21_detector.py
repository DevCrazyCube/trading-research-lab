#!/usr/bin/env python3
"""PAC V2.1 single-shock payable-absorption detector.

The detector is pure and causal. It consumes only one same-mint, same-collector-epoch reserve chain and
returns the newest setup that satisfies the preregistered rule. It does not size USD, price an order,
read a clock, write state, or create a fill; callers must supply an exact point-in-time quote size and a
separately authenticated processed-inclusion p90.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import pac_detector
from . import pac_v2_detector
from .pac_v2_feed import ClockedEvent


BUYER_BREADTH_MIN = 3
RESERVE_SHOCK_COVER_MULTIPLE = 6


@dataclass(frozen=True)
class Qualification:
    evidence_indices: tuple[int, ...]
    evidence_event_ids: tuple[str, ...]
    shock_index: int
    recovery_index: int
    dwell_nanos: int
    buyer_breadth_ex_seller: int
    shock_seller: str
    shock_lamports: int
    pre_shock_reserve_lamports: int
    recovered_reserve_lamports: int
    reserve_cover_lamports: int


def qualify(events: tuple[ClockedEvent, ...], *, processed_p90_nanos: int,
            quote_input_lamports: int) -> Qualification | None:
    """Return the newest qualifying causal single-shock prefix, or ``None``.

    Observed addresses are counted literally. Distinct strings are not asserted to be independent
    owners, people, or funding clusters. The shock seller is excluded from the buyer breadth count.
    """
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
        recovery_index = None
        for index in range(shock_index + 1, len(events)):
            if events[index].post_state.real_quote >= pre_shock:
                recovery_index = index
                break
        if recovery_index is None:
            continue
        recovery = events[recovery_index]
        dwell = latest.source_received_unix_nanos - recovery.source_received_unix_nanos
        total_span = latest.source_received_unix_nanos - shock.source_received_unix_nanos
        if (dwell < processed_p90_nanos
                or total_span > pac_detector.MAX_PATTERN_SPAN_NANOS):
            continue
        # The economic floor is the reserve that existed immediately before the observed shock. A
        # recovery overshoot is allowed to fluctuate above this floor; falling below it fails.
        if any(event.post_state.real_quote < pre_shock
               for event in events[recovery_index:]):
            continue
        buyers = {
            event.trader for event in events[shock_index + 1:]
            if event.side == "buy" and event.trader != shock.trader
        }
        if len(buyers) < BUYER_BREADTH_MIN:
            continue
        cover = RESERVE_SHOCK_COVER_MULTIPLE * max(
            quote_input_lamports, shock_lamports)
        if latest.post_state.real_quote < cover:
            continue
        evidence_indices = tuple(range(shock_index, len(events)))
        return Qualification(
            evidence_indices=evidence_indices,
            evidence_event_ids=tuple(events[index].event_id for index in evidence_indices),
            shock_index=shock_index,
            recovery_index=recovery_index,
            dwell_nanos=dwell,
            buyer_breadth_ex_seller=len(buyers),
            shock_seller=shock.trader,
            shock_lamports=shock_lamports,
            pre_shock_reserve_lamports=pre_shock,
            recovered_reserve_lamports=recovery.post_state.real_quote,
            reserve_cover_lamports=cover,
        )
    return None
