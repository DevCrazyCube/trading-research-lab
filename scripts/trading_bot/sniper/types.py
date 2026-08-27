#!/usr/bin/env python3
"""Shared contracts for the sniper paper stack. Every module imports from HERE and nowhere else for
these types, so components built independently fit together. PAPER / DRY-RUN ONLY — see ARCHITECTURE.md.

Nothing in this file (or any consumer) may sign or send a transaction, load a wallet, or read a private
key. `ALLOW_REAL_ORDERS` is hard-False and exists only so the Executor can mark where a future,
human-gated, operator-wallet live path would attach. Code must never flip it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, Iterator, Optional, runtime_checkable

# The single global kill-flag for real trading. HARD-CODED False. Never set True in code.
ALLOW_REAL_ORDERS: bool = False


# ---------------- market data ----------------
@dataclass(frozen=True)
class TokenEvent:
    """A newly-observed token / pool."""
    mint: str
    symbol: Optional[str]
    venue: Optional[str]          # "Pumpfun" (bonding-curve) | "Pumpswap" (migrated AMM) | ...
    created_utc: Optional[str]
    seen_utc: str


@dataclass(frozen=True)
class TradeTick:
    """One executed trade on a mint."""
    mint: str
    ts: float                     # epoch seconds
    price_usd: float
    usd: float                    # trade size in USD
    side: str                     # "buy" | "sell" (taker direction vs the token)
    venue: Optional[str] = None
    user: Optional[str] = None    # taker wallet, when the source decodes it (Chainstack pump.fun feed).
    #                               Optional so non-decoding providers stay unaffected; consumers that
    #                               don't need it (signals/strategy) simply ignore it. Read-only, never
    #                               used to sign/send. Powers rug-risk early-buyer + deployer signals.


@dataclass(frozen=True)
class Bar:
    """A 1-second OHLCV+flow candle (matches research/data/memebot_cache/bitquery_candles schema)."""
    t: int
    o: float; h: float; l: float; c: float
    v: float
    buys: int; sells: int
    buy_vol: float; sell_vol: float
    dex: Optional[str] = None


# ---------------- signals / orders / fills ----------------
@dataclass(frozen=True)
class EntrySignal:
    mint: str
    ts: float
    ref_price_usd: float          # price at the moment the surge qualified
    surge_bps: float
    buy_frac: float
    liq_usd_per_s: float
    venue: Optional[str]
    reason: str                   # human-readable why it fired


@dataclass(frozen=True)
class OrderIntent:
    mint: str
    side: str                     # "buy" | "sell"
    ts: float
    ref_price_usd: float
    usd_size: float               # paper notional
    venue: Optional[str]
    tag: str = ""                 # "entry" | "exit:<reason>"


@dataclass(frozen=True)
class Fill:
    mint: str
    side: str
    ts: float
    price_usd: float              # realistic paper fill price (after slippage)
    usd_size: float
    toll_bps: float               # round-trip-equivalent venue toll charged on this side
    slip_bps: float
    tip_usd: float = 0.0          # estimated Jito tip / priority fee (paper)
    dry_run: bool = True


@dataclass
class Position:
    mint: str
    entry: Fill
    venue: Optional[str]
    peak_price: float
    opened_ts: float
    frozen_sha256: str = ""
    exit: Optional[Fill] = None
    exit_reason: str = ""
    realized_r: Optional[float] = None
    meta: dict = field(default_factory=dict)

    @property
    def is_open(self) -> bool:
        return self.exit is None


# ---------------- provider / strategy / executor interfaces ----------------
@runtime_checkable
class DataProvider(Protocol):
    """Read-only market data. Implementations: Chainstack, PublicRpc, Bitquery, Replay."""

    name: str

    def healthy(self) -> bool:
        """True if this provider can currently serve data (e.g. Chainstack returns False on 403)."""
        ...

    def stream_ticks(self) -> Iterator[TradeTick]:
        """Yield trade ticks in time order (live: as they arrive; replay: from cache)."""
        ...

    def recent_bars(self, mint: str, lookback_s: int = 300) -> list[Bar]:
        """Recent 1s bars for a mint (for signal + exit walks)."""
        ...


@runtime_checkable
class Strategy(Protocol):
    def on_signal(self, sig: EntrySignal) -> Optional[OrderIntent]:
        """Decide whether/how to enter given an entry signal + current book/bankroll."""
        ...

    def on_bar(self, mint: str, bar: Bar) -> list[OrderIntent]:
        """Per-bar update of open positions -> zero or more exit intents (let-winners-run/flow-exit)."""
        ...


@runtime_checkable
class Executor(Protocol):
    def execute(self, intent: OrderIntent) -> Fill:
        """Return a PAPER fill (realistic price/cost). Live sign+send is stubbed behind ALLOW_REAL_ORDERS."""
        ...
