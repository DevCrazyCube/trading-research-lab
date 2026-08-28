#!/usr/bin/env python3
"""PAC V2 entry qualification: original PAC plus latency dwell, address breadth and shock cover."""
from __future__ import annotations

from dataclasses import dataclass

from . import pac_detector
from .pac_v2_feed import ClockedEvent


BUYER_BREADTH_MIN = 3
RESERVE_SHOCK_COVER_MULTIPLE = 6


@dataclass(frozen=True)
class Qualification:
    evidence_indices: tuple[int, ...]
    evidence_event_ids: tuple[str, ...]
    pac_indices: tuple[int, int, int, int]
    dwell_nanos: int
    buyer_breadth: int
    largest_observed_sell_lamports: int
    reserve_cover_lamports: int


def _valid_stream(events: tuple[ClockedEvent, ...]) -> bool:
    if not events or any(not isinstance(event, ClockedEvent) for event in events):
        return False
    mint, epoch = events[0].mint, events[0].collector_epoch
    if any(event.mint != mint or event.collector_epoch != epoch for event in events):
        return False
    if any(right.source_received_unix_nanos <= left.source_received_unix_nanos
           for left, right in zip(events, events[1:])):
        return False
    if any(right.pre_state != left.post_state for left, right in zip(events, events[1:])):
        return False
    return True


def qualify(events: tuple[ClockedEvent, ...], *, reaction_p90_nanos: int,
            quote_input_lamports: int) -> Qualification | None:
    """Return the newest qualifying causal prefix, or None.

    Wallet strings are exact observed addresses only.  `buyer_breadth` never means independent owner or
    funding cluster.  The reserve rule protects against the largest sell already observed in this setup;
    it makes no claim about a larger future seller.
    """
    if (type(reaction_p90_nanos) is not int or reaction_p90_nanos <= 0
            or type(quote_input_lamports) is not int or quote_input_lamports <= 0
            or not _valid_stream(events)):
        return None
    for recovery2 in range(len(events) - 1, 2, -1):
        prefix = events[:recovery2 + 1]
        pac_indices = pac_detector.detector(prefix, 0)
        if not pac_indices:
            continue
        w1, r1, w2, r2 = pac_indices
        if r2 != recovery2:
            continue
        dwell = events[-1].source_received_unix_nanos - events[r2].source_received_unix_nanos
        total_span = events[-1].source_received_unix_nanos - events[w1].source_received_unix_nanos
        if dwell < reaction_p90_nanos or total_span > pac_detector.MAX_PATTERN_SPAN_NANOS:
            continue
        if not pac_detector.position_size_is_covered(prefix, pac_indices, quote_input_lamports):
            continue
        recovered = events[r2].post_state.real_quote
        dwell_events = events[r2:]
        # Dwell means the recovered reserve survives throughout the measured execution window.
        if any(event.post_state.real_quote < recovered for event in dwell_events):
            continue
        buyers = {event.trader for event in dwell_events if event.side == "buy"}
        if len(buyers) < BUYER_BREADTH_MIN:
            continue
        setup = events[w1:]
        withdrawals = [max(0, event.pre_state.real_quote - event.post_state.real_quote)
                       for event in setup]
        largest = max(withdrawals, default=0)
        cover = RESERVE_SHOCK_COVER_MULTIPLE * max(quote_input_lamports, largest)
        if events[-1].post_state.real_quote < cover:
            continue
        # Commit every PAC event plus all post-recovery events that establish dwell/breadth/survival.
        indices = tuple(dict.fromkeys((*pac_indices, *range(r2 + 1, len(events)))))
        return Qualification(
            evidence_indices=indices,
            evidence_event_ids=tuple(events[index].event_id for index in indices),
            pac_indices=tuple(pac_indices), dwell_nanos=dwell, buyer_breadth=len(buyers),
            largest_observed_sell_lamports=largest, reserve_cover_lamports=cover)
    return None
