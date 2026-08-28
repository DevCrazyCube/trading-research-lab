#!/usr/bin/env python3
"""Pure PAC V2 full-position exit policy with an actually absolute horizon."""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum


TRAIL_NUM = 12
TRAIL_DEN = 100
COVERAGE_MULTIPLE = 6
MAX_HOLD_NANOS = 720_000_000_000


class ExitAction(str, Enum):
    HOLD = "HOLD"
    EXIT_HORIZON = "EXIT_HORIZON"
    EXIT_CAPACITY = "EXIT_CAPACITY"
    EXIT_TRAIL = "EXIT_TRAIL"
    UNEXITABLE_FULL_LOSS = "UNEXITABLE_FULL_LOSS"


@dataclass(frozen=True)
class Position:
    token_atoms: int
    quote_input_lamports: int
    entry_unix_nanos: int
    peak_net_exit_lamports: int = 0

    def __post_init__(self):
        if (type(self.token_atoms) is not int or self.token_atoms <= 0
                or type(self.quote_input_lamports) is not int or self.quote_input_lamports <= 0
                or type(self.entry_unix_nanos) is not int or self.entry_unix_nanos < 0
                or type(self.peak_net_exit_lamports) is not int
                or self.peak_net_exit_lamports < 0):
            raise ValueError("PAC V2 position fields are invalid")


@dataclass(frozen=True)
class Decision:
    action: ExitAction
    position: Position
    observed_net_exit_lamports: int | None


def decide(position: Position, *, now_unix_nanos: int,
           net_exit_lamports: int | None, real_quote_lamports: int | None) -> Decision:
    if type(now_unix_nanos) is not int or now_unix_nanos < position.entry_unix_nanos:
        raise ValueError("PAC V2 exit clock is invalid")
    unavailable = net_exit_lamports is None or real_quote_lamports is None
    if not unavailable and (type(net_exit_lamports) is not int or net_exit_lamports < 0
                            or type(real_quote_lamports) is not int or real_quote_lamports < 0):
        raise ValueError("PAC V2 quote/reserve is invalid")

    # ABSOLUTE means first.  A prior trail/capacity condition can never shadow the horizon.
    if now_unix_nanos - position.entry_unix_nanos >= MAX_HOLD_NANOS:
        return Decision(ExitAction.UNEXITABLE_FULL_LOSS if unavailable else ExitAction.EXIT_HORIZON,
                        position, net_exit_lamports)
    if unavailable:
        return Decision(ExitAction.UNEXITABLE_FULL_LOSS, position, None)
    peak = max(position.peak_net_exit_lamports, net_exit_lamports)
    updated = replace(position, peak_net_exit_lamports=peak)
    if real_quote_lamports < COVERAGE_MULTIPLE * position.quote_input_lamports:
        return Decision(ExitAction.EXIT_CAPACITY, updated, net_exit_lamports)
    if peak > 0 and net_exit_lamports * TRAIL_DEN <= peak * (TRAIL_DEN - TRAIL_NUM):
        return Decision(ExitAction.EXIT_TRAIL, updated, net_exit_lamports)
    return Decision(ExitAction.HOLD, updated, net_exit_lamports)
