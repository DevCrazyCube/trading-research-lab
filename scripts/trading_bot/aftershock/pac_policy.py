#!/usr/bin/env python3
"""Frozen pure portfolio/exit policy for AFTERSHOCK PAC V1.

The policy consumes a curve-exact quote for selling the *entire* token position.  It never consumes a
chart price, never takes a fixed profit, never scales out, and never turns an unavailable quote into a
mark.  Execution/landing remains the responsibility of the causal execution engine.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum


TRAIL_NUM = 12
TRAIL_DEN = 100
COVERAGE_MULTIPLE = 6
MAX_HOLD_NANOS = 720_000_000_000
DISCOVERY_PROBE_USD = "10.00"
DISCOVERY_BANKROLL_USD = "100.00"


class ExitAction(str, Enum):
    HOLD = "HOLD"
    ATTEMPT_FULL_EXIT_TRAIL = "ATTEMPT_FULL_EXIT_TRAIL"
    ATTEMPT_FULL_EXIT_CAPACITY = "ATTEMPT_FULL_EXIT_CAPACITY"
    ATTEMPT_FULL_EXIT_HORIZON = "ATTEMPT_FULL_EXIT_HORIZON"
    UNEXITABLE_FULL_LOSS = "UNEXITABLE_FULL_LOSS"


@dataclass(frozen=True)
class PositionState:
    token_atoms: int
    quote_input_lamports: int
    entry_observation_unix_nanos: int
    peak_full_exit_quote_lamports: int

    def __post_init__(self) -> None:
        for label in ("token_atoms", "quote_input_lamports", "entry_observation_unix_nanos",
                      "peak_full_exit_quote_lamports"):
            value = getattr(self, label)
            if type(value) is not int or value < (0 if "nanos" in label or "peak" in label else 1):
                raise ValueError(f"{label} must be an exact non-negative/positive integer")


@dataclass(frozen=True)
class ExitDecision:
    action: ExitAction
    state: PositionState
    observed_full_exit_quote_lamports: int | None


def decide_exit(state: PositionState, *, full_exit_quote_lamports: int | None,
                external_reserve_lamports: int | None,
                observation_unix_nanos: int) -> ExitDecision:
    if not isinstance(state, PositionState):
        raise ValueError("PositionState required")
    if type(observation_unix_nanos) is not int or observation_unix_nanos < state.entry_observation_unix_nanos:
        raise ValueError("exit observation clock must be an exact integer at/after entry")
    if full_exit_quote_lamports is None or external_reserve_lamports is None:
        # There is no executable quote to sell against.  Calling this an exit would recreate the old
        # unavailable-mark bias; honest stress settles it as a full loss.
        return ExitDecision(ExitAction.UNEXITABLE_FULL_LOSS, state, None)
    if (type(full_exit_quote_lamports) is not int or full_exit_quote_lamports < 0
            or type(external_reserve_lamports) is not int or external_reserve_lamports < 0):
        raise ValueError("quotes/reserves must be exact non-negative integers or unavailable")

    peak = max(state.peak_full_exit_quote_lamports, full_exit_quote_lamports)
    next_state = replace(state, peak_full_exit_quote_lamports=peak)
    if external_reserve_lamports < COVERAGE_MULTIPLE * state.quote_input_lamports:
        return ExitDecision(ExitAction.ATTEMPT_FULL_EXIT_CAPACITY, next_state, full_exit_quote_lamports)
    if peak > 0 and full_exit_quote_lamports * TRAIL_DEN <= peak * (TRAIL_DEN - TRAIL_NUM):
        return ExitDecision(ExitAction.ATTEMPT_FULL_EXIT_TRAIL, next_state, full_exit_quote_lamports)
    if observation_unix_nanos - state.entry_observation_unix_nanos >= MAX_HOLD_NANOS:
        return ExitDecision(ExitAction.ATTEMPT_FULL_EXIT_HORIZON, next_state, full_exit_quote_lamports)
    return ExitDecision(ExitAction.HOLD, next_state, full_exit_quote_lamports)
