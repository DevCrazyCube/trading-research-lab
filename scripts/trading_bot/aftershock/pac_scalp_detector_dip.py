#!/usr/bin/env python3
"""Dip-reclaim entry gate for the PAC portfolio convexity scalper (PAPER-SCENARIO).

Anti-exhaustion sibling of :mod:`pac_scalp_detector`.  The forensic on 322 real forward paper trades
(2026-08-31) showed the momentum gate systematically buys EXHAUSTION: 82% of entries went straight
down from fill and the median LOSER's peak intra-trade gain was -494 bps (never green).  We were the
exit liquidity of a vertical spike that was only visible on lagged free data AFTER the move.

This gate refuses the vertical spike and instead waits for a shakeout-then-reclaim:
  * a local PEAK forms in the curve SOL reserve (real_quote) earlier in the window,
  * a PULLBACK of at least PULLBACK_MIN_BPS drains the reserve off that peak (weak hands flushed),
  * a RECLAIM: the current reserve has recovered at least RECLAIM_MIN_FRAC_BPS of the peak->trough
    range on RENEWED buying (buy>sell + breadth) in the leg after the trough, while STILL BELOW the
    peak (buying the reclaim, never a fresh all-time high -- a new high is momentum/exhaustion again).

It makes no directional claim and shares the identical convex exit (small fast stop, let winners run)
and multi-position book with the momentum arm; only the ENTRY trigger differs, so the two arms form a
matched forward comparison of "buy the spike" vs "buy the reclaim".  Pure; no I/O; no lookahead --
reads only bonding-curve events already causally received by ``now``.
"""
from __future__ import annotations

from dataclasses import dataclass

from .execution import RefusedExecution


WINDOW_NANOS = 12_000_000_000          # longer than momentum: must contain peak + pullback + reclaim
MIN_EVENTS = 5
MIN_BUYERS = 3
PULLBACK_MIN_BPS = 800                  # >= 8% drain off the local peak to count as a real shakeout
RECLAIM_MIN_FRAC_BPS = 3000            # current recovered >= 30% of the peak->trough range
COVERAGE_MULTIPLE = 6                   # live-bid / exit-impact floor (sizing only, same as momentum)


@dataclass(frozen=True)
class DipReclaimSignal:
    mint: str
    window_start_unix_nanos: int
    window_end_unix_nanos: int
    entry_real_quote: int
    peak_real_quote: int
    trough_real_quote: int
    pullback_bps: int
    reclaim_frac_bps: int
    buyer_breadth: int
    net_quote_inflow: int
    evidence_event_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in ("window_start_unix_nanos", "window_end_unix_nanos", "entry_real_quote",
                     "peak_real_quote", "trough_real_quote", "pullback_bps", "reclaim_frac_bps",
                     "buyer_breadth", "net_quote_inflow"):
            if type(getattr(self, name)) is not int:
                raise RefusedExecution(f"dip-reclaim signal {name} is not an exact integer")
        if self.window_end_unix_nanos <= self.window_start_unix_nanos:
            raise RefusedExecution("dip-reclaim window is degenerate")
        if self.buyer_breadth < MIN_BUYERS or self.entry_real_quote <= 0:
            raise RefusedExecution("dip-reclaim signal fails its own gate")
        if not (self.trough_real_quote < self.entry_real_quote < self.peak_real_quote):
            raise RefusedExecution("dip-reclaim ordering trough<entry<peak violated")


def qualify(events, *, now_unix_nanos: int, quote_input_lamports: int,
            window_nanos: int = WINDOW_NANOS):
    """Return a DipReclaimSignal if the mint just reclaimed a dip on renewed buying, else None.

    ``events`` is the mint's causally-ordered ClockedEvent buffer (each carries pre_state/post_state
    ReserveState, trader, side, event_id, slot, source_received_unix_nanos).  Pure; no lookahead.
    """
    if type(now_unix_nanos) is not int or type(quote_input_lamports) is not int \
            or quote_input_lamports <= 0:
        raise RefusedExecution("dip-reclaim qualify inputs are invalid")
    window = [e for e in events
              if e.source_received_unix_nanos <= now_unix_nanos
              and e.source_received_unix_nanos > now_unix_nanos - window_nanos]
    if len(window) < MIN_EVENTS:
        return None
    quotes = [e.post_state.real_quote for e in window]
    current = quotes[-1]
    # (1) local peak strictly before the last point (we need room for a pullback + reclaim after it)
    peak_idx = max(range(len(quotes) - 1), key=lambda i: quotes[i])
    peak = quotes[peak_idx]
    if peak <= 0:
        return None
    # (2) trough after the peak
    after = quotes[peak_idx:]
    trough_off = min(range(len(after)), key=lambda i: after[i])
    trough_idx = peak_idx + trough_off
    trough = quotes[trough_idx]
    if trough_idx >= len(window) - 1:
        return None  # trough is the last point -> no reclaim leg yet
    pullback_bps = (peak - trough) * 10000 // peak
    if pullback_bps < PULLBACK_MIN_BPS:
        return None
    # (3) reclaim: recovered a real fraction of the dip, on renewed buying, but still below the peak
    if current <= trough or current >= peak:
        return None
    reclaim_frac_bps = (current - trough) * 10000 // max(1, peak - trough)
    if reclaim_frac_bps < RECLAIM_MIN_FRAC_BPS:
        return None
    # the reclaim leg is strictly AFTER the trough event -- including the trough's own sell would net
    # its drain against the renewed buying and mask a real reclaim.
    reclaim_leg = window[trough_idx + 1:]
    buy_vol = sum(max(0, e.post_state.real_quote - e.pre_state.real_quote) for e in reclaim_leg)
    sell_vol = sum(max(0, e.pre_state.real_quote - e.post_state.real_quote) for e in reclaim_leg)
    if buy_vol <= sell_vol:
        return None
    buyers = {e.trader for e in reclaim_leg
              if e.side == "buy" and isinstance(e.trader, str) and e.trader}
    if len(buyers) < MIN_BUYERS:
        return None
    # (4) live-bid / exit-impact floor
    if current < COVERAGE_MULTIPLE * quote_input_lamports:
        return None
    evidence = tuple(e.event_id for e in reclaim_leg if isinstance(getattr(e, "event_id", None), str))
    last = window[-1]
    return DipReclaimSignal(
        mint=last.mint, window_start_unix_nanos=window[0].source_received_unix_nanos,
        window_end_unix_nanos=last.source_received_unix_nanos, entry_real_quote=current,
        peak_real_quote=peak, trough_real_quote=trough, pullback_bps=pullback_bps,
        reclaim_frac_bps=reclaim_frac_bps, buyer_breadth=len(buyers),
        net_quote_inflow=buy_vol - sell_vol, evidence_event_ids=evidence)
