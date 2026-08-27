#!/usr/bin/env python3
"""Momentum-surge SIGNAL detection for the sniper paper stack (agent B; owns ONLY this file).

Deterministic, NO LLM, read-only. Consumes `Bar` / `TradeTick` and emits `EntrySignal`, exactly as
defined in types.py. PAPER / DRY-RUN ONLY — this module never loads a wallet, reads a key, or sends an
order. It only *detects*; the strategy decides whether to act.

The entry structure (the one our research found had a positive GROSS edge on liquid coins): from a mint's
recent tick/bar stream at time t, qualify a surge when ALL of:
  1. price is up >= surge_bps over the last window_s seconds,
  2. rolling buy-volume fraction over that window >= min_buy_frac,
  3. >= min_trades trades in the window (attention / liquidity proxy),
  4. LIQUIDITY GATE: per-second USD throughput over the window >= min_liq_usd_per_s
     (only coins liquid enough to actually exit cheaply — this is what made the cheap subset net-positive).

Debounce: exactly one EntrySignal per mint per surge. A fired mint is DISARMED and only re-arms once the
window drops out of qualification (rising-edge), and a per-mint cooldown enforces a minimum time between
fires. An optional `position_open` hook lets the strategy suppress signals while it already holds the mint.

Runs incrementally on a stream: per-mint rolling window of recent events, old ones evicted, O(1)-amortized
per update (a bounded deque + running sums). `prune_idle` drops mints that have gone quiet.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, replace
from typing import Callable, Deque, Dict, Optional, Union

try:  # package import (normal) with a fallback so the file also runs as a plain script
    from .types import Bar, EntrySignal, TradeTick
except ImportError:  # pragma: no cover - exercised only when run outside the package
    from types import Bar, EntrySignal, TradeTick  # type: ignore


BarOrTick = Union[Bar, TradeTick]


# --------------------------------------------------------------------------- config
@dataclass(frozen=True)
class SurgeConfig:
    """Thresholds for the momentum-surge detector.

    Defaults are a deliberately middle-of-the-road ("BALANCED") set inside the research ranges. They are
    NOT tuned to any observed outcome — see PARAM_GRID for the pre-registered diverse sets to sweep later.
    """
    window_s: float = 30.0            # rolling lookback for the surge (seconds of real time)
    surge_bps: float = 400.0          # required price rise over the window (bps; +400 bps = +4%)
    min_buy_frac: float = 0.65        # buy USD / (buy+sell USD) over the window
    min_trades: int = 12              # trades in the window (attention / liquidity proxy)
    min_liq_usd_per_s: float = 15.0   # LIQUIDITY GATE: total window USD / window_s
    cooldown_s: float = 60.0          # min time between two fires on the same mint
    idle_evict_s: float = 300.0       # a mint silent this long is dropped by prune_idle
    # FOLLOW-THROUGH CONFIRMATION (default OFF = fire on the trigger, the original behavior). When
    # confirm_s > 0, a qualifying surge does NOT enter immediately; it must SUSTAIN for confirm_s more
    # seconds without the price fading more than confirm_max_drawdown_bps below the trigger. This filters
    # the "fader" surges (the ones that spike and immediately die -> the small trail losses) by TIME
    # persistence, not by a higher magnitude threshold (which was tested as core_tight and did worse).
    confirm_s: float = 0.0
    confirm_max_drawdown_bps: float = 200.0   # max fade below the trigger tolerated during confirm_s

    def __post_init__(self) -> None:
        if self.window_s <= 0:
            raise ValueError("window_s must be > 0")
        if self.confirm_s < 0:
            raise ValueError("confirm_s must be >= 0")
        if self.confirm_max_drawdown_bps < 0:
            raise ValueError("confirm_max_drawdown_bps must be >= 0")
        if self.surge_bps <= 0:
            raise ValueError("surge_bps must be > 0")
        if not (0.0 <= self.min_buy_frac <= 1.0):
            raise ValueError("min_buy_frac must be in [0, 1]")
        if self.min_trades < 1:
            raise ValueError("min_trades must be >= 1")
        if self.min_liq_usd_per_s < 0:
            raise ValueError("min_liq_usd_per_s must be >= 0")


# A few NAMED parameter sets to sweep for later forward-selection. These are DIVERSE priors, not fits:
# TIGHT wants a sharp, clearly buy-dominated, well-traded surge on a liquid coin; WIDE casts a broader net
# on quieter tape; FAST/SLOW vary only the horizon. Pre-registration discipline: do not edit these to
# chase any measured result.
PARAM_GRID: Dict[str, SurgeConfig] = {
    "BALANCED": SurgeConfig(),
    "TIGHT": SurgeConfig(
        window_s=20.0, surge_bps=800.0, min_buy_frac=0.75,
        min_trades=20, min_liq_usd_per_s=30.0, cooldown_s=90.0,
    ),
    "WIDE": SurgeConfig(
        window_s=45.0, surge_bps=200.0, min_buy_frac=0.58,
        min_trades=8, min_liq_usd_per_s=8.0, cooldown_s=45.0,
    ),
    "FAST": SurgeConfig(
        window_s=10.0, surge_bps=300.0, min_buy_frac=0.68,
        min_trades=8, min_liq_usd_per_s=20.0, cooldown_s=30.0,
    ),
    "SLOW": SurgeConfig(
        window_s=60.0, surge_bps=600.0, min_buy_frac=0.62,
        min_trades=25, min_liq_usd_per_s=12.0, cooldown_s=120.0,
    ),
    # CONFIRM: the BALANCED entry but with a 5s follow-through requirement -- a qualifying surge must
    # SUSTAIN (not fade > 1.5% below the trigger) for 5 more seconds before entering. Targets the fader
    # small-losses directly: a spike that instantly dies is skipped, a real run still enters (a few
    # seconds later). Same magnitude thresholds as BALANCED -- the ONLY new lever is time-persistence.
    "CONFIRM": SurgeConfig(
        confirm_s=5.0, confirm_max_drawdown_bps=150.0,
    ),
}


def params_grid() -> Dict[str, SurgeConfig]:
    """Return the named parameter sets to sweep (copy, so callers can't mutate the shared grid)."""
    return dict(PARAM_GRID)


# --------------------------------------------------------------------------- internals
@dataclass(frozen=True)
class _Ev:
    """One normalized event in a mint's rolling window (a Bar aggregates trades in its second)."""
    ts: float
    price0: float   # price at the start of the event (Bar open; tick price)
    price1: float   # price at the end of the event   (Bar close; tick price)
    usd: float      # total USD traded in the event
    buy_usd: float
    sell_usd: float
    trades: int
    venue: Optional[str]


def _normalize(x: BarOrTick) -> _Ev:
    if isinstance(x, Bar):
        return _Ev(
            ts=float(x.t), price0=float(x.o), price1=float(x.c), usd=float(x.v),
            buy_usd=float(x.buy_vol), sell_usd=float(x.sell_vol),
            trades=int(x.buys) + int(x.sells), venue=x.dex,
        )
    if isinstance(x, TradeTick):
        buy = x.side == "buy"
        return _Ev(
            ts=float(x.ts), price0=float(x.price_usd), price1=float(x.price_usd), usd=float(x.usd),
            buy_usd=float(x.usd) if buy else 0.0, sell_usd=0.0 if buy else float(x.usd),
            trades=1, venue=x.venue,
        )
    raise TypeError(f"update() expects a Bar or TradeTick, got {type(x).__name__}")


class _MintState:
    """Rolling window + running sums + debounce state for one mint."""

    __slots__ = ("events", "sum_usd", "sum_buy", "sum_sell", "sum_trades",
                 "armed", "last_fire_ts", "last_seen_ts", "venue",
                 "pending_since_ts", "pending_ref_price")

    def __init__(self) -> None:
        self.events: Deque[_Ev] = deque()
        self.sum_usd = 0.0
        self.sum_buy = 0.0
        self.sum_sell = 0.0
        self.sum_trades = 0
        self.armed = True                 # rising-edge latch: True => allowed to fire on next qualify
        self.last_fire_ts = float("-inf")
        self.last_seen_ts = float("-inf")
        self.venue: Optional[str] = None
        self.pending_since_ts: Optional[float] = None   # confirmation window start (None = none pending)
        self.pending_ref_price: float = 0.0             # price at the trigger, for the fade check

    def push(self, ev: _Ev) -> None:
        self.events.append(ev)
        self.sum_usd += ev.usd
        self.sum_buy += ev.buy_usd
        self.sum_sell += ev.sell_usd
        self.sum_trades += ev.trades
        self.last_seen_ts = ev.ts
        if ev.venue is not None:
            self.venue = ev.venue

    def evict_before(self, cutoff_ts: float) -> None:
        ev = self.events
        while ev and ev[0].ts < cutoff_ts:
            old = ev.popleft()
            self.sum_usd -= old.usd
            self.sum_buy -= old.buy_usd
            self.sum_sell -= old.sell_usd
            self.sum_trades -= old.trades
        # guard tiny negative drift from float subtraction
        if not ev:
            self.sum_usd = self.sum_buy = self.sum_sell = 0.0
            self.sum_trades = 0


# --------------------------------------------------------------------------- detector
@dataclass(frozen=True)
class _Metrics:
    surge_bps: float
    buy_frac: float
    liq_usd_per_s: float
    trades: int
    ref_price: float


class SurgeDetector:
    """Incremental momentum-surge detector.

    Usage:
        det = SurgeDetector(SurgeConfig())                 # or PARAM_GRID["TIGHT"]
        det.position_open = lambda mint: mint in my_open   # optional suppression hook
        for ev in stream:                                  # Bar or TradeTick, time-ordered per mint
            sig = det.update(ev)
            if sig is not None:
                strategy.on_signal(sig)
        det.prune_idle(now_ts)                             # drop quiet mints periodically
    """

    def __init__(
        self,
        config: Optional[SurgeConfig] = None,
        *,
        position_open: Optional[Callable[[str], bool]] = None,
    ) -> None:
        self.config = config or SurgeConfig()
        # Optional hook the strategy may set: return True to suppress signals while it holds `mint`.
        self.position_open: Optional[Callable[[str], bool]] = position_open
        self._mints: Dict[str, _MintState] = {}

    # -- core -----------------------------------------------------------------
    def update(self, bar_or_tick: BarOrTick, mint: Optional[str] = None) -> Optional[EntrySignal]:
        """Feed one Bar or TradeTick; return an EntrySignal if this update completes a fresh surge.

        A `TradeTick` carries its own `mint`. A `Bar` does NOT (the cache is one file per mint), so `mint`
        is REQUIRED when feeding a Bar. If both are present they must agree.
        """
        ev = _normalize(bar_or_tick)
        if isinstance(bar_or_tick, TradeTick):
            tick_mint = bar_or_tick.mint
            if mint is not None and mint != tick_mint:
                raise ValueError(f"mint mismatch: passed {mint!r} but tick is for {tick_mint!r}")
            mint = tick_mint
        elif mint is None:
            raise ValueError("update(Bar, mint=...) requires an explicit mint (a Bar has no mint field)")

        st = self._mints.get(mint)
        if st is None:
            st = self._mints[mint] = _MintState()

        st.push(ev)
        st.evict_before(ev.ts - self.config.window_s)

        m = self._metrics(st)
        qualifies = self._qualifies(m)
        cfg = self.config

        # --- FOLLOW-THROUGH CONFIRMATION: resolve any in-progress confirmation window FIRST, so a fade
        #     during it is caught regardless of whether the window still nominally qualifies. ---
        if st.pending_since_ts is not None:
            fade_floor = st.pending_ref_price * (1.0 - cfg.confirm_max_drawdown_bps / 10_000.0)
            if m.ref_price < fade_floor:
                # the surge faded below tolerance -> a "fader"; abandon the entry, re-arm for a fresh one
                st.pending_since_ts = None
                st.armed = True
                return None
            if ev.ts - st.pending_since_ts < cfg.confirm_s:
                return None   # still confirming and still holding up; keep waiting
            # confirmation window elapsed and price held; require buy-pressure to still be there to enter
            st.pending_since_ts = None
            if m.buy_frac < cfg.min_buy_frac:
                st.armed = True
                return None
            return self._fire(st, mint, m, ev, cfg, confirmed=True)

        # Rising-edge latch: re-arm as soon as the window is NOT qualifying, so the NEXT qualification
        # (a fresh surge) can fire again. This is what prevents re-firing every bar of one surge.
        if not qualifies:
            st.armed = True
            return None

        blocked_cd = (ev.ts - st.last_fire_ts) < cfg.cooldown_s
        blocked_pos = self.position_open is not None and bool(self.position_open(mint))
        if not st.armed or blocked_cd or blocked_pos:
            return None

        if cfg.confirm_s > 0:
            # Don't enter on the trigger; open a confirmation window and wait for follow-through.
            st.pending_since_ts = ev.ts
            st.pending_ref_price = m.ref_price
            st.armed = False
            return None

        return self._fire(st, mint, m, ev, cfg, confirmed=False)

    def _fire(self, st: "_MintState", mint: str, m: "_Metrics", ev: "_Ev",
              cfg: SurgeConfig, confirmed: bool) -> EntrySignal:
        """Emit the entry signal at the current (trigger or confirmed) price."""
        st.armed = False
        st.last_fire_ts = ev.ts
        venue = ev.venue if ev.venue is not None else st.venue
        tag = "confirmed " if confirmed else ""
        reason = (
            f"{tag}surge +{m.surge_bps:.0f}bps/{cfg.window_s:.0f}s "
            f"buy_frac {m.buy_frac:.2f} trades {m.trades} "
            f"liq ${m.liq_usd_per_s:.1f}/s"
        )
        return EntrySignal(
            mint=mint,
            ts=ev.ts,
            ref_price_usd=m.ref_price,
            surge_bps=m.surge_bps,
            buy_frac=m.buy_frac,
            liq_usd_per_s=m.liq_usd_per_s,
            venue=venue,
            reason=reason,
        )

    def _metrics(self, st: _MintState) -> _Metrics:
        events = st.events
        if not events:
            return _Metrics(0.0, 0.0, 0.0, 0, 0.0)
        first = events[0]
        last = events[-1]
        ref0 = first.price0
        cur = last.price1
        surge_bps = ((cur / ref0) - 1.0) * 10_000.0 if ref0 > 0 else 0.0
        flow = st.sum_buy + st.sum_sell
        buy_frac = (st.sum_buy / flow) if flow > 0 else 0.0
        liq = st.sum_usd / self.config.window_s   # per-second USD throughput normalized to the window
        return _Metrics(surge_bps, buy_frac, liq, st.sum_trades, cur)

    def _qualifies(self, m: _Metrics) -> bool:
        cfg = self.config
        return (
            m.surge_bps >= cfg.surge_bps
            and m.buy_frac >= cfg.min_buy_frac
            and m.trades >= cfg.min_trades
            and m.liq_usd_per_s >= cfg.min_liq_usd_per_s
        )

    # -- introspection (read-only; handy for sim/diagnostics, does not mutate state) --------
    def metrics(self, mint: str) -> Optional[dict]:
        """Current window metrics for a mint (or None if unseen). For diagnostics only."""
        st = self._mints.get(mint)
        if st is None:
            return None
        m = self._metrics(st)
        return {
            "surge_bps": m.surge_bps,
            "buy_frac": m.buy_frac,
            "liq_usd_per_s": m.liq_usd_per_s,
            "trades": m.trades,
            "ref_price_usd": m.ref_price,
            "qualifies": self._qualifies(m),
            "armed": st.armed,
        }

    def tracked_mints(self) -> int:
        return len(self._mints)

    # -- lifecycle ------------------------------------------------------------
    def prune_idle(self, now_ts: float) -> int:
        """Drop mints with no event for >= idle_evict_s. Returns how many were dropped."""
        cutoff = now_ts - self.config.idle_evict_s
        stale = [m for m, st in self._mints.items() if st.last_seen_ts < cutoff]
        for m in stale:
            del self._mints[m]
        return len(stale)

    def reset(self, mint: Optional[str] = None) -> None:
        """Reset one mint's window/debounce state, or ALL mints if mint is None."""
        if mint is None:
            self._mints.clear()
        else:
            self._mints.pop(mint, None)

    def with_config(self, config: SurgeConfig) -> "SurgeDetector":
        """A fresh detector with a different config, keeping the same position_open hook (empty state)."""
        return SurgeDetector(config, position_open=self.position_open)


__all__ = [
    "SurgeConfig",
    "SurgeDetector",
    "PARAM_GRID",
    "params_grid",
]

# `replace` is re-exported convenience for building tweaked configs without editing PARAM_GRID in place.
tweak = replace
