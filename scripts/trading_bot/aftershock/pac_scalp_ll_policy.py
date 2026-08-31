#!/usr/bin/env python3
"""A-priori convex exit policy for the fresh low-latency measurement instrument.

The old -6% stop was inside entry toll plus ordinary landing noise.  This successor uses -12%
all-cost LIQUIDATION EQUITY for both the public control and low-latency intervention.  Changing the
route never changes this policy, which isolates the latency treatment instead of confounding it with
a second threshold experiment.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum


HARD_STOP_NUM = 12
HARD_STOP_DEN = 100
PROVEN_PEAK_NUM = 12
PROVEN_PEAK_DEN = 100
COVERAGE_MULTIPLE = 6
MAX_HOLD_NANOS = 720_000_000_000
TRAIL_TIERS = ((150, 35), (50, 25), (12, 18))


class ExitAction(str, Enum):
    HOLD = "HOLD"
    EXIT_HORIZON = "EXIT_HORIZON"
    EXIT_HARD_STOP = "EXIT_HARD_STOP"
    EXIT_CAPACITY = "EXIT_CAPACITY"
    EXIT_TRAIL = "EXIT_TRAIL"


@dataclass(frozen=True)
class Position:
    entry_all_in_lamports: int
    entry_unix_nanos: int
    quote_input_lamports: int
    peak_liquidation_equity_lamports: int = 0

    def __post_init__(self) -> None:
        if (type(self.entry_all_in_lamports) is not int or self.entry_all_in_lamports <= 0
                or type(self.entry_unix_nanos) is not int or self.entry_unix_nanos < 0
                or type(self.quote_input_lamports) is not int or self.quote_input_lamports <= 0
                or type(self.peak_liquidation_equity_lamports) is not int
                or self.peak_liquidation_equity_lamports < 0):
            raise ValueError("low-latency scalp position is invalid")


@dataclass(frozen=True)
class Decision:
    action: ExitAction
    position: Position
    observed_liquidation_equity_lamports: int | None


def _trail_pct(peak_gain_pct: int) -> int | None:
    for lower, pct in TRAIL_TIERS:
        if peak_gain_pct >= lower:
            return pct
    return None


def decide(position: Position, *, decision_unix_nanos: int,
           liquidation_equity_lamports: int | None,
           real_quote_lamports: int | None) -> Decision:
    if type(decision_unix_nanos) is not int or decision_unix_nanos < position.entry_unix_nanos:
        raise ValueError("low-latency scalp decision clock is invalid")
    if liquidation_equity_lamports is not None and (
            type(liquidation_equity_lamports) is not int or liquidation_equity_lamports <= 0):
        raise ValueError("low-latency scalp equity is invalid")
    if real_quote_lamports is not None and (
            type(real_quote_lamports) is not int or real_quote_lamports < 0):
        raise ValueError("low-latency scalp reserve is invalid")

    # Unavailable is never called an atomic rug here.  The runner must first attempt the frozen
    # cross-venue state machine; only that terminal path may score a full loss.
    if liquidation_equity_lamports is None or real_quote_lamports is None:
        return Decision(ExitAction.HOLD, position, None)
    peak = max(position.peak_liquidation_equity_lamports, liquidation_equity_lamports)
    updated = replace(position, peak_liquidation_equity_lamports=peak)
    if decision_unix_nanos - position.entry_unix_nanos >= MAX_HOLD_NANOS:
        return Decision(ExitAction.EXIT_HORIZON, updated, liquidation_equity_lamports)
    if (liquidation_equity_lamports * HARD_STOP_DEN
            <= position.entry_all_in_lamports * (HARD_STOP_DEN - HARD_STOP_NUM)):
        return Decision(ExitAction.EXIT_HARD_STOP, updated, liquidation_equity_lamports)
    if real_quote_lamports < COVERAGE_MULTIPLE * position.quote_input_lamports:
        return Decision(ExitAction.EXIT_CAPACITY, updated, liquidation_equity_lamports)
    peak_gain_pct = ((peak - position.entry_all_in_lamports) * 100
                     // position.entry_all_in_lamports)
    trail_pct = _trail_pct(peak_gain_pct)
    if (trail_pct is not None
            and liquidation_equity_lamports * 100 <= peak * (100 - trail_pct)):
        return Decision(ExitAction.EXIT_TRAIL, updated, liquidation_equity_lamports)
    return Decision(ExitAction.HOLD, updated, liquidation_equity_lamports)
