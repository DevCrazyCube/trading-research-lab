#!/usr/bin/env python3
"""Convex exit policy for the PAC portfolio scalper: cut losers small+fast, let winners run.

The asymmetry is the whole engine.  Losers (and gradual rugs) are floored by a tight entry-relative
HARD STOP so a would-be -100% bleed is booked as a small capped loss.  A position that PROVES itself
(peak >= +12% net) switches to a WIDE, widening peak-trail so the fat runner tail (+300%+ observed) is
ridden, not clipped.  Absolute ordering (a later condition never shadows an earlier one):
    HORIZON  >  HARD_STOP  >  CAPACITY  >  LET_RUN_TRAIL  >  HOLD.
Honesty: this policy is pure and path-triggered on OBSERVED quotes only; the runner fills every exit
at the modeled landing snapshot (decision + calibrated latency), never at a fabricated peak.  The
irreducible atomic-rug tail (dev drains all reserve inside the landing window -> no bid) cannot be
escaped by any stop and resolves as an honest unexitable full loss elsewhere.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum


HARD_STOP_NUM = 6            # entry-relative hard stop at -6%
HARD_STOP_DEN = 100
PROVEN_PEAK_NUM = 12         # a position is a "runner" once peak net >= +12% of entry
PROVEN_PEAK_DEN = 100
COVERAGE_MULTIPLE = 6
MAX_HOLD_NANOS = 720_000_000_000
# Widening peak-trail once proven: (peak_gain_lower_bound_pct, trail_pct). First match from the top.
TRAIL_TIERS = ((150, 35), (50, 25), (12, 18))


class ExitAction(str, Enum):
    HOLD = "HOLD"
    EXIT_HORIZON = "EXIT_HORIZON"
    EXIT_HARD_STOP = "EXIT_HARD_STOP"
    EXIT_CAPACITY = "EXIT_CAPACITY"
    EXIT_TRAIL = "EXIT_TRAIL"
    UNEXITABLE_FULL_LOSS = "UNEXITABLE_FULL_LOSS"


@dataclass(frozen=True)
class Position:
    token_atoms: int
    quote_input_lamports: int
    entry_all_in_lamports: int
    entry_unix_nanos: int
    peak_net_exit_lamports: int = 0

    def __post_init__(self):
        if (type(self.token_atoms) is not int or self.token_atoms <= 0
                or type(self.quote_input_lamports) is not int or self.quote_input_lamports <= 0
                or type(self.entry_all_in_lamports) is not int or self.entry_all_in_lamports <= 0
                or type(self.entry_unix_nanos) is not int or self.entry_unix_nanos < 0
                or type(self.peak_net_exit_lamports) is not int or self.peak_net_exit_lamports < 0):
            raise ValueError("PAC scalp position fields are invalid")


@dataclass(frozen=True)
class Decision:
    action: ExitAction
    position: Position
    observed_net_exit_lamports: int | None


def _trail_pct(peak_gain_pct: int) -> int | None:
    for lower, pct in TRAIL_TIERS:
        if peak_gain_pct >= lower:
            return pct
    return None


def decide(position: Position, *, now_unix_nanos: int,
           net_exit_lamports: int | None, real_quote_lamports: int | None) -> Decision:
    if type(now_unix_nanos) is not int or now_unix_nanos < position.entry_unix_nanos:
        raise ValueError("PAC scalp exit clock is invalid")
    unavailable = net_exit_lamports is None or real_quote_lamports is None
    if not unavailable and (type(net_exit_lamports) is not int or net_exit_lamports < 0
                            or type(real_quote_lamports) is not int or real_quote_lamports < 0):
        raise ValueError("PAC scalp quote/reserve is invalid")

    # HORIZON is absolute and first: a prior stop/trail/capacity can never shadow it.
    if now_unix_nanos - position.entry_unix_nanos >= MAX_HOLD_NANOS:
        return Decision(ExitAction.UNEXITABLE_FULL_LOSS if unavailable else ExitAction.EXIT_HORIZON,
                        position, net_exit_lamports)
    if unavailable:
        return Decision(ExitAction.UNEXITABLE_FULL_LOSS, position, None)

    peak = max(position.peak_net_exit_lamports, net_exit_lamports)
    updated = replace(position, peak_net_exit_lamports=peak)

    # HARD STOP (entry-relative, tight): floor every loser small and fast; survives gradual rugs.
    if net_exit_lamports * HARD_STOP_DEN <= position.entry_all_in_lamports * (HARD_STOP_DEN - HARD_STOP_NUM):
        return Decision(ExitAction.EXIT_HARD_STOP, updated, net_exit_lamports)

    # CAPACITY: the curve can no longer absorb our exit at bounded impact.
    if real_quote_lamports < COVERAGE_MULTIPLE * position.quote_input_lamports:
        return Decision(ExitAction.EXIT_CAPACITY, updated, net_exit_lamports)

    # LET WINNERS RUN: below the proven threshold there is NO trail (only the -6% hard stop floors
    # it); once proven, a widening peak-trail rides the fat tail instead of clipping it.
    peak_gain_pct = (peak - position.entry_all_in_lamports) * 100 // position.entry_all_in_lamports
    if peak_gain_pct >= PROVEN_PEAK_NUM:
        trail_pct = _trail_pct(peak_gain_pct)
        if trail_pct is not None and net_exit_lamports * 100 <= peak * (100 - trail_pct):
            return Decision(ExitAction.EXIT_TRAIL, updated, net_exit_lamports)
    return Decision(ExitAction.HOLD, updated, net_exit_lamports)
