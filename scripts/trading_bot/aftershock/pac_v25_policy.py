#!/usr/bin/env python3
"""PAC V2.5 exit vocabulary; inherited V2 policy plus a premise-break action."""
from __future__ import annotations

from enum import Enum

from . import pac_v2_policy as base


TRAIL_NUM = base.TRAIL_NUM
TRAIL_DEN = base.TRAIL_DEN
COVERAGE_MULTIPLE = base.COVERAGE_MULTIPLE
MAX_HOLD_NANOS = base.MAX_HOLD_NANOS
Position = base.Position
Decision = base.Decision


class ExitAction(str, Enum):
    HOLD = "HOLD"
    EXIT_HORIZON = "EXIT_HORIZON"
    EXIT_CAPACITY = "EXIT_CAPACITY"
    EXIT_TRAIL = "EXIT_TRAIL"
    EXIT_PREMISE_BREAK = "EXIT_PREMISE_BREAK"
    UNEXITABLE_FULL_LOSS = "UNEXITABLE_FULL_LOSS"


def decide(position: Position, *, now_unix_nanos: int,
           net_exit_lamports: int | None, real_quote_lamports: int | None):
    result = base.decide(position, now_unix_nanos=now_unix_nanos,
                         net_exit_lamports=net_exit_lamports,
                         real_quote_lamports=real_quote_lamports)
    return type(result)(ExitAction(result.action.value), result.position,
                        result.observed_net_exit_lamports)
