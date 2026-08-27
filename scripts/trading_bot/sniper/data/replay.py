#!/usr/bin/env python3
"""ReplayProvider — the offline default for paper testing (ZERO network, READ-ONLY).

Replays the on-disk 1s candles in research/data/memebot_cache/bitquery_candles/{mint}.jsonl. It lets
the whole sniper stack — provider -> signals -> strategy -> executor -> sim — run and be tested with
no network at all. Nothing here signs, sends, or touches a wallet/key.

`stream_ticks()` synthesizes TradeTicks from every mint's bars in ONE global time order (so the
runner replays a whole session across all coins), advancing an internal replay clock as it goes.
`recent_bars()` returns the bars up to that clock, exactly as a live provider would only know the
past. `healthy()` is True when the cache directory holds candle files.

Tick synthesis is deterministic and approximate: each 1s bar is expanded into its `buys` buy-ticks
and `sells` sell-ticks, sized by buy_vol/sell_vol, priced by linear interpolation from the bar open
to its close, and spread across sub-second offsets so the whole stream is strictly time-ordered.
"""
from __future__ import annotations

import pathlib
from typing import Iterator, Optional

from ._common import CACHE_DIR, Bar, TradeTick, load_cached_bars


class ReplayProvider:
    """Deterministic offline replay of cached 1s candles as a time-ordered tick + bar feed."""

    name = "replay"

    def __init__(self, cache_dir: Optional[pathlib.Path] = None):
        self.cache_dir = pathlib.Path(cache_dir) if cache_dir else CACHE_DIR
        self._bars_by_mint: dict[str, list[Bar]] = {}
        self._loaded = False
        # Replay clock: epoch seconds of the last tick yielded. recent_bars() only sees bars <= this.
        self._clock: int = 0

    # -- health -------------------------------------------------------------------------------
    def healthy(self) -> bool:
        """True if the cache directory exists and holds at least one candle file."""
        d = self.cache_dir
        return d.is_dir() and any(d.glob("*.jsonl"))

    # -- loading ------------------------------------------------------------------------------
    def _load(self) -> None:
        if self._loaded:
            return
        for path in sorted(self.cache_dir.glob("*.jsonl")):
            mint = path.stem
            bars = load_cached_bars(mint, self.cache_dir)
            if bars:
                self._bars_by_mint[mint] = bars
        self._loaded = True

    def mints(self) -> list[str]:
        self._load()
        return sorted(self._bars_by_mint)

    # -- tick synthesis -----------------------------------------------------------------------
    @staticmethod
    def _bar_to_ticks(mint: str, bar: Bar) -> list[TradeTick]:
        """Expand one 1s bar into ordered synthetic ticks with sub-second timestamps in [t, t+1)."""
        n_buy = bar.buys if bar.buys > 0 else (1 if bar.buy_vol > 0 else 0)
        n_sell = bar.sells if bar.sells > 0 else (1 if bar.sell_vol > 0 else 0)
        total = n_buy + n_sell
        if total == 0:
            return []
        buy_each = (bar.buy_vol / n_buy) if n_buy else 0.0
        sell_each = (bar.sell_vol / n_sell) if n_sell else 0.0
        # Interleave buys and sells deterministically by their fractional position in the second.
        marks = ([("buy", (i + 0.5) / n_buy) for i in range(n_buy)] +
                 [("sell", (i + 0.5) / n_sell) for i in range(n_sell)])
        marks.sort(key=lambda m: m[1])
        ticks = []
        for idx, (side, _frac) in enumerate(marks):
            # Linear open->close price path across the ordered ticks in the bar.
            frac = idx / (total - 1) if total > 1 else 1.0
            price = bar.o + (bar.c - bar.o) * frac
            if price <= 0:
                price = bar.c or bar.o
            offset = (idx + 0.5) / total  # strictly inside [t, t+1), preserves ordering
            ticks.append(TradeTick(mint=mint, ts=bar.t + offset, price_usd=price,
                                   usd=buy_each if side == "buy" else sell_each, side=side,
                                   venue=bar.dex))
        return ticks

    def stream_ticks(self) -> Iterator[TradeTick]:
        """Yield synthetic ticks across ALL mints in strict global time order, advancing the clock."""
        self._load()
        all_ticks: list[TradeTick] = []
        for mint, bars in self._bars_by_mint.items():
            for bar in bars:
                all_ticks.extend(self._bar_to_ticks(mint, bar))
        all_ticks.sort(key=lambda t: t.ts)
        for tick in all_ticks:
            self._clock = int(tick.ts)
            yield tick

    # -- recent bars --------------------------------------------------------------------------
    def recent_bars(self, mint: str, lookback_s: int = 300) -> list[Bar]:
        """Bars for a mint up to the current replay clock (the replay only 'knows' the past)."""
        self._load()
        bars = self._bars_by_mint.get(mint)
        if not bars:
            return []
        clock = self._clock or (bars[-1].t)  # before streaming, expose the full history
        floor = clock - lookback_s
        return [b for b in bars if floor <= b.t <= clock]
