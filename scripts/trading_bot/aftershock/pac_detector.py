#!/usr/bin/env python3
"""AFTERSHOCK PAC V1 entry detector — pure, causal, and sealable.

PAC means Payable Absorption Compression.  It does not infer wallets or fresh capital.  It observes
only exact external-quote reserves and fires after two sequential withdrawal/recovery cycles when the
second cycle is at least as stressful, recovers no slower, and preserves the reserve baseline.

``detector(events, warmup_count)`` returns the exact four evidence indices
``(withdraw_1, recover_1, withdraw_2, recover_2)``.  An empty tuple means no setup.
"""
from __future__ import annotations

from dataclasses import dataclass


MIN_CYCLE_WITHDRAWAL_LAMPORTS = 50_000_000
MAX_PATTERN_SPAN_NANOS = 180_000_000_000
REQUIRED_CYCLES = 2


@dataclass(frozen=True)
class Cycle:
    withdrawal_index: int
    recovery_index: int
    withdrawal_lamports: int
    pre_withdrawal_reserve: int
    recovered_reserve: int
    recovery_nanos: int


def _cycles(events: tuple, warmup_count: int) -> tuple[Cycle, ...]:
    out: list[Cycle] = []
    for i in range(warmup_count, len(events) - 1):
        pre = events[i].pre_state.real_quote
        post = events[i].post_state.real_quote
        withdrawn = pre - post
        if withdrawn < MIN_CYCLE_WITHDRAWAL_LAMPORTS:
            continue
        for j in range(i + 1, len(events)):
            if events[j].post_state.real_quote >= pre:
                elapsed = events[j].observation_unix_nanos - events[i].observation_unix_nanos
                if elapsed > 0:
                    out.append(Cycle(i, j, withdrawn, pre,
                                     events[j].post_state.real_quote, elapsed))
                break
    return tuple(out)


def _pac_pair(first: Cycle, second: Cycle, events: tuple) -> bool:
    if first.recovery_index >= second.withdrawal_index:
        return False
    if second.recovery_index != len(events) - 1:
        return False
    if (events[second.recovery_index].observation_unix_nanos
            - events[first.withdrawal_index].observation_unix_nanos) > MAX_PATTERN_SPAN_NANOS:
        return False
    # PAC = min(W2/W1, D1/D2, Rpre2/Rpre1, Rrec2/Rrec1).  PAC >= 1 is evaluated
    # component-wise with exact integers; there are no floats or fitted score weights.
    return (second.withdrawal_lamports >= first.withdrawal_lamports
            and second.recovery_nanos <= first.recovery_nanos
            and second.pre_withdrawal_reserve >= first.pre_withdrawal_reserve
            and second.recovered_reserve >= first.recovered_reserve)


def detector(events: tuple, warmup_count: int) -> tuple[int, ...]:
    if type(warmup_count) is not int or warmup_count < 0 or warmup_count >= len(events):
        return ()
    candidates = _cycles(events, warmup_count)
    pairs: list[tuple[Cycle, Cycle]] = []
    for first in candidates:
        for second in candidates:
            if _pac_pair(first, second, events):
                pairs.append((first, second))
    if not pairs:
        return ()
    # Prefer the most recent qualifying evidence.  This is causal recency, not an outcome score.
    first, second = max(pairs, key=lambda pair: (
        pair[1].withdrawal_index, pair[0].withdrawal_index,
        pair[0].recovery_index, pair[1].recovery_index))
    result = (first.withdrawal_index, first.recovery_index,
              second.withdrawal_index, second.recovery_index)
    if (result[0] < warmup_count or result[-1] != len(events) - 1
            or any(a >= b for a, b in zip(result, result[1:]))):
        return ()
    return result


def pac_metrics(events: tuple, evidence_indices: tuple[int, ...]) -> dict[str, int]:
    """Return auditable integer PAC components for an already detected setup."""
    if (not isinstance(evidence_indices, tuple) or len(evidence_indices) != 4
            or any(type(i) is not int for i in evidence_indices)
            or any(a >= b for a, b in zip(evidence_indices, evidence_indices[1:]))):
        raise ValueError("PAC evidence must contain four increasing exact indices")
    w1, r1, w2, r2 = evidence_indices
    if w1 < 0 or r2 >= len(events):
        raise ValueError("PAC evidence is outside the event stream")
    c1 = Cycle(w1, r1,
               events[w1].pre_state.real_quote - events[w1].post_state.real_quote,
               events[w1].pre_state.real_quote, events[r1].post_state.real_quote,
               events[r1].observation_unix_nanos - events[w1].observation_unix_nanos)
    c2 = Cycle(w2, r2,
               events[w2].pre_state.real_quote - events[w2].post_state.real_quote,
               events[w2].pre_state.real_quote, events[r2].post_state.real_quote,
               events[r2].observation_unix_nanos - events[w2].observation_unix_nanos)
    if (c1.withdrawal_lamports < MIN_CYCLE_WITHDRAWAL_LAMPORTS
            or c2.withdrawal_lamports < MIN_CYCLE_WITHDRAWAL_LAMPORTS
            or events[r1].post_state.real_quote < c1.pre_withdrawal_reserve
            or events[r2].post_state.real_quote < c2.pre_withdrawal_reserve
            or not _pac_pair(c1, c2, events)):
        raise ValueError("evidence does not satisfy the complete PAC rule")
    return {
        "withdrawal_1_lamports": c1.withdrawal_lamports,
        "withdrawal_2_lamports": c2.withdrawal_lamports,
        "recovery_1_nanos": c1.recovery_nanos,
        "recovery_2_nanos": c2.recovery_nanos,
        "pre_reserve_1_lamports": c1.pre_withdrawal_reserve,
        "pre_reserve_2_lamports": c2.pre_withdrawal_reserve,
        "recovered_reserve_1_lamports": c1.recovered_reserve,
        "recovered_reserve_2_lamports": c2.recovered_reserve,
    }


def position_size_is_covered(events: tuple, evidence_indices: tuple[int, ...],
                             q_lamports: int) -> bool:
    """The planned exact-quote buy must fit inside both demonstrated withdrawals."""
    if type(q_lamports) is not int or q_lamports <= 0:
        return False
    try:
        metrics = pac_metrics(events, evidence_indices)
    except (ValueError, IndexError, AttributeError, TypeError):
        return False
    return q_lamports <= min(metrics["withdrawal_1_lamports"],
                             metrics["withdrawal_2_lamports"])
