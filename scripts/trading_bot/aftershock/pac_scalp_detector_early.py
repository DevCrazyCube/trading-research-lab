#!/usr/bin/env python3
"""Early-curve accumulation entry gate for the PAC portfolio convexity scalper (PAPER-SCENARIO).

Second anti-exhaustion sibling of :mod:`pac_scalp_detector`.  Where the momentum gate buys a curve
whose reserve is already high (median entry real_quote ~20 SOL on the losing forward run -- i.e. late,
after the crowd), this gate buys EARLY: a low-reserve curve just starting to accumulate, before the
vertical spike is visible on lagged data, so there is runway left to run into the convex exit.

A mint qualifies over a rolling window W iff ALL hold, read only from causally-received events:
  1. current curve SOL reserve is inside the EARLY band [COVERAGE_MULTIPLE x notional , EARLY_MAX] --
     high enough to fill our exit against, low enough to still be early on the curve;
  2. net SOL inflow across the window (accumulation), and gross buy volume strictly exceeds sell;
  3. at least MIN_BUYERS distinct buyer addresses arrive in the window;
  4. RUG-GUARD: no single sell event in the window drained more than GUARD_NUM/GUARD_DEN of the
     current reserve (refuse curves already showing a whale-dump signature).

Makes no directional claim; shares the identical convex exit and multi-position book with the other
arms.  Pure; no I/O; no lookahead.
"""
from __future__ import annotations

from dataclasses import dataclass

from .execution import RefusedExecution


WINDOW_NANOS = 4_000_000_000
MIN_BUYERS = 3
COVERAGE_MULTIPLE = 6                       # exit-impact floor / lower edge of the early band
EARLY_MAX_QUOTE_LAMPORTS = 8_000_000_000    # upper edge: 8 SOL reserve -- below the ~20 SOL late median
GUARD_NUM = 1                               # rug-guard: reject if any single sell drained
GUARD_DEN = 4                               #   > 1/4 of the current reserve in one event


@dataclass(frozen=True)
class EarlyCurveSignal:
    mint: str
    window_start_unix_nanos: int
    window_end_unix_nanos: int
    entry_real_quote: int
    max_single_sell: int
    buyer_breadth: int
    net_quote_inflow: int
    evidence_event_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in ("window_start_unix_nanos", "window_end_unix_nanos", "entry_real_quote",
                     "max_single_sell", "buyer_breadth", "net_quote_inflow"):
            if type(getattr(self, name)) is not int:
                raise RefusedExecution(f"early-curve signal {name} is not an exact integer")
        if self.window_end_unix_nanos <= self.window_start_unix_nanos:
            raise RefusedExecution("early-curve window is degenerate")
        if self.buyer_breadth < MIN_BUYERS or self.entry_real_quote <= 0:
            raise RefusedExecution("early-curve signal fails its own gate")
        if self.entry_real_quote > EARLY_MAX_QUOTE_LAMPORTS:
            raise RefusedExecution("early-curve entry reserve above the early band")


def qualify(events, *, now_unix_nanos: int, quote_input_lamports: int,
            window_nanos: int = WINDOW_NANOS):
    """Return an EarlyCurveSignal if the mint is early and accumulating cleanly, else None.

    ``events`` is the mint's causally-ordered ClockedEvent buffer.  Pure; no lookahead.
    """
    if type(now_unix_nanos) is not int or type(quote_input_lamports) is not int \
            or quote_input_lamports <= 0:
        raise RefusedExecution("early-curve qualify inputs are invalid")
    window = [e for e in events
              if e.source_received_unix_nanos <= now_unix_nanos
              and e.source_received_unix_nanos > now_unix_nanos - window_nanos]
    if len(window) < MIN_BUYERS:
        return None
    first, last = window[0], window[-1]
    current = last.post_state.real_quote
    # (1) EARLY band: high enough to fill our exit, low enough to still be early on the curve
    if current < COVERAGE_MULTIPLE * quote_input_lamports:
        return None
    if current > EARLY_MAX_QUOTE_LAMPORTS:
        return None
    # (2) net inflow + gross buy > gross sell
    if current <= first.pre_state.real_quote:
        return None
    buy_vol = sum(max(0, e.post_state.real_quote - e.pre_state.real_quote) for e in window)
    sell_vol = sum(max(0, e.pre_state.real_quote - e.post_state.real_quote) for e in window)
    if buy_vol <= sell_vol:
        return None
    # (3) buyer breadth
    buyers = {e.trader for e in window
              if e.side == "buy" and isinstance(e.trader, str) and e.trader}
    if len(buyers) < MIN_BUYERS:
        return None
    # (4) rug-guard: reject a whale-dump signature already present in the window
    max_single_sell = max((e.pre_state.real_quote - e.post_state.real_quote
                           for e in window if e.post_state.real_quote < e.pre_state.real_quote),
                          default=0)
    if max_single_sell * GUARD_DEN > current * GUARD_NUM:
        return None
    evidence = tuple(e.event_id for e in window if isinstance(getattr(e, "event_id", None), str))
    return EarlyCurveSignal(
        mint=last.mint, window_start_unix_nanos=first.source_received_unix_nanos,
        window_end_unix_nanos=last.source_received_unix_nanos, entry_real_quote=current,
        max_single_sell=int(max_single_sell), buyer_breadth=len(buyers),
        net_quote_inflow=buy_vol - sell_vol, evidence_event_ids=evidence)
