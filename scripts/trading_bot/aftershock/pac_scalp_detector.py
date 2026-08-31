#!/usr/bin/env python3
"""Momentum entry gate for the PAC portfolio convexity scalper (PAPER-SCENARIO).

This is NOT a predictive edge (no decision-time feature separates winners from losers; every AUC is
~0.5).  It is a permissive OBSERVABLE gate whose only job is to put a slot on a mint that is pumping
RIGHT NOW with a live curve bid, so the convex exit (small fast stop, let winners run) and the
multi-position book can harvest the fat runner tail across many shots.  It makes no directional claim.

A mint qualifies over a rolling window W (W > the calibrated landing latency so the signal is not
stale-raced) iff ALL hold, read only from causally-received bonding-curve trade events:
  1. the curve SOL reserve (real_quote) is strictly higher at the end of the window than the start
     (net SOL inflow / net buy pressure);
  2. gross buy quote volume strictly exceeds gross sell quote volume across the window;
  3. at least MIN_BUYERS distinct buyer addresses arrive in the window (observed addresses only);
  4. the current curve SOL reserve is at least COVERAGE_MULTIPLE x our own position notional (bounds
     our exit impact and guarantees a live bid for the stop to fill against) -- sizing/impact only.
"""
from __future__ import annotations

from dataclasses import dataclass

from .execution import RefusedExecution


WINDOW_NANOS = 4_000_000_000
MIN_BUYERS = 3
COVERAGE_MULTIPLE = 6


@dataclass(frozen=True)
class MomentumSignal:
    mint: str
    window_start_unix_nanos: int
    window_end_unix_nanos: int
    entry_real_quote: int
    buyer_breadth: int
    net_quote_inflow: int
    evidence_event_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in ("window_start_unix_nanos", "window_end_unix_nanos", "entry_real_quote",
                     "buyer_breadth", "net_quote_inflow"):
            if type(getattr(self, name)) is not int:
                raise RefusedExecution(f"momentum signal {name} is not an exact integer")
        if self.window_end_unix_nanos <= self.window_start_unix_nanos:
            raise RefusedExecution("momentum window is degenerate")
        if self.buyer_breadth < MIN_BUYERS or self.entry_real_quote <= 0:
            raise RefusedExecution("momentum signal fails its own gate")


def qualify(events, *, now_unix_nanos: int, quote_input_lamports: int,
            window_nanos: int = WINDOW_NANOS):
    """Return a MomentumSignal if the mint is pumping now with a live bid, else None.

    ``events`` is the mint's causally-ordered ClockedEvent buffer (each carries pre_state/post_state
    ReserveState, trader, side, source_received_unix_nanos).  Pure; no I/O; no lookahead -- it reads
    only events already received by ``now``.
    """
    if type(now_unix_nanos) is not int or type(quote_input_lamports) is not int \
            or quote_input_lamports <= 0:
        raise RefusedExecution("momentum qualify inputs are invalid")
    window = [e for e in events
              if e.source_received_unix_nanos <= now_unix_nanos
              and e.source_received_unix_nanos > now_unix_nanos - window_nanos]
    if len(window) < MIN_BUYERS:
        return None
    first, last = window[0], window[-1]
    entry_real_quote = last.post_state.real_quote
    # (1) net SOL inflow across the window
    if entry_real_quote <= first.pre_state.real_quote:
        return None
    # (2) gross buy quote volume strictly exceeds gross sell quote volume
    buy_vol = sum(max(0, e.post_state.real_quote - e.pre_state.real_quote) for e in window)
    sell_vol = sum(max(0, e.pre_state.real_quote - e.post_state.real_quote) for e in window)
    if buy_vol <= sell_vol:
        return None
    # (3) >= MIN_BUYERS distinct buyer addresses arriving in the window
    buyers = {e.trader for e in window
              if e.side == "buy" and isinstance(e.trader, str) and e.trader}
    if len(buyers) < MIN_BUYERS:
        return None
    # (4) live-bid / exit-impact floor: current curve SOL reserve >= COVERAGE_MULTIPLE x our notional
    if entry_real_quote < COVERAGE_MULTIPLE * quote_input_lamports:
        return None
    evidence = tuple(e.event_id for e in window if isinstance(getattr(e, "event_id", None), str))
    return MomentumSignal(
        mint=last.mint, window_start_unix_nanos=first.source_received_unix_nanos,
        window_end_unix_nanos=last.source_received_unix_nanos,
        entry_real_quote=entry_real_quote, buyer_breadth=len(buyers),
        net_quote_inflow=buy_vol - sell_vol, evidence_event_ids=evidence)
