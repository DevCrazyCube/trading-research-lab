#!/usr/bin/env python3
"""Wiring smoke tests. NOTHING HERE IS AN EDGE CANDIDATE, and nothing here is fitted.

T2's acceptance asks for a trivial known strategy to prove the rig is wired correctly. The
temptation at this point is to also drop in "just one" real candidate and look at the number.
That is how a rig becomes a search, and a search that happened before it was declared is
exactly what the deflated Sharpe exists to punish. So this module contains only strategies
whose answer is known in advance:

  BuyAndHold      -- position +1 always. Must reproduce the asset's own return net of one
                     entry cost. Its paired excess against itself is identically zero, which
                     must make the DSR REFUSE (FINDINGS 5c, the "wrong object" failure mode).
  AlwaysFlat      -- position 0 always. Must produce exactly zero return and zero cost.
  AlwaysShort     -- position -1 always. Must pay borrow every calendar day, including
                     weekends, and must lose roughly what BuyAndHold makes.
  Oscillator      -- alternates +1/-1 on a fixed bar parity. Known turnover of 2.0 per bar,
                     so it prices the cost model against hand arithmetic.
  CheatingOracle  -- DELIBERATELY LEAKY. It reads the future through a closure, not through
                     the view, so it is invisible to the interface guard and can only be
                     caught by the future-scramble audit. It exists to prove the audit works;
                     an audit never shown to fail is not evidence.
"""

from __future__ import annotations

from fractions import Fraction

from .engine import PointInTimeView, Strategy
from .frozen import Refused


class BuyAndHold(Strategy):
    """Long the asset, always. The wiring smoke test."""

    name = "buy_and_hold"
    warmup_bars = 0

    def on_bar(self, view: PointInTimeView, state: dict) -> Fraction:
        return Fraction(1)


class AlwaysFlat(Strategy):
    """Never in the market. Zero return, zero cost, zero turnover -- exactly."""

    name = "always_flat"
    warmup_bars = 0

    def on_bar(self, view: PointInTimeView, state: dict) -> Fraction:
        return Fraction(0)


class AlwaysShort(Strategy):
    """Short the asset, always. Exists to exercise the borrow leg of the cost model."""

    name = "always_short"
    warmup_bars = 0

    def on_bar(self, view: PointInTimeView, state: dict) -> Fraction:
        return Fraction(-1)


class Oscillator(Strategy):
    """+1 on even bars, -1 on odd. Turnover is exactly 2.0 per bar, so costs are hand-checkable.

    Uses only `view.index`, which is the bar number, and no price at all -- so it is
    trivially leakage-free and the audit must pass it.
    """

    name = "oscillator"
    warmup_bars = 0

    def on_bar(self, view: PointInTimeView, state: dict) -> Fraction:
        return Fraction(1) if view.index % 2 == 0 else Fraction(-1)


class TrailingSmaCross(Strategy):
    """Long when the close is above its own trailing SMA, else flat. A *shape*, not a candidate.

    Present because a strategy with a real warm-up is needed to test that the engine and the
    walk-forward splitter honour it. FINDINGS 5b already killed the return claim of this
    family (DSR 0.224-0.341, nine of ten lengths lose to buy-and-hold); what survived was a
    drawdown reduction, which is not a return statistic. It is here as plumbing, and no number
    it produces in this rig is a finding.
    """

    name = "sma_cross"

    def __init__(self, length: int = 100):
        if length < 2:
            raise Refused(f"an SMA of length {length} is not a moving average")
        self.length = length
        self.warmup_bars = length - 1
        self.name = f"sma_cross_{length}"

    def on_bar(self, view: PointInTimeView, state: dict) -> Fraction:
        closes = view.closes(self.length)          # refuses if the window has not printed
        sma = Fraction(sum(closes), len(closes))
        return Fraction(1) if Fraction(view.now.close_micros) > sma else Fraction(0)

    def describe(self) -> dict:
        return dict(super().describe(), length=self.length)


class CheatingOracle(Strategy):
    """DELIBERATELY LEAKY. Reads tomorrow's bar from its own copy, bypassing the view entirely.

    The negative control for the future-scramble audit. It is invisible to layer 1: it never
    asks the view for a future bar, it holds its own reference to the series. Only re-running
    against an altered future catches it, and `run_backtest` must REFUSE on it. A test asserts
    that, because an audit never demonstrated to fail is not evidence of anything.

    Pass the CLASS, not `lambda: CheatingOracle(bars)`. `build_strategy` hands a
    series-taking factory the series the audit is currently probing with; a zero-argument
    lambda closing over the real bars keeps the real future in both runs and the audit
    correctly reports nothing -- which is exactly how the audit's first version was found to
    be toothless.
    """

    name = "cheating_oracle_NEGATIVE_CONTROL"
    warmup_bars = 0

    def __init__(self, raw_series):
        self._smuggled = tuple(raw_series)

    def on_bar(self, view: PointInTimeView, state: dict) -> Fraction:
        nxt = view.index + 1
        if nxt >= len(self._smuggled):
            return Fraction(0)
        future = self._smuggled[nxt]
        return Fraction(1) if future.close_micros > future.open_micros else Fraction(-1)


__all__ = [
    "BuyAndHold", "AlwaysFlat", "AlwaysShort", "Oscillator", "TrailingSmaCross",
    "CheatingOracle",
]
