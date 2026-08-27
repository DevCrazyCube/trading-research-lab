#!/usr/bin/env python3
"""The execution seam. One strategy interface, two destinations, and a gate between them.

WHY BACKTEST AND PAPER SHARE ONE PATH
=====================================
The commonest way a validated strategy loses its edge is that the live code is not the code
that was tested. So a live run consumes the SAME `Strategy.on_bar` and the SAME
`PointInTimeView` -- in a live session the view's cursor is simply the last bar that printed,
and "the future does not exist yet" is enforced by physics rather than by the clamp. The
clamp still holds, so a strategy that reaches forward fails identically in both modes.

WHAT IS AND IS NOT IMPLEMENTED HERE
===================================
Implemented: the order schema, the endpoint guard, and the pre-trade checks.

**Not implemented: order submission.** `submit()` refuses. This mirrors B22B's pinned
collection stage -- the part that touches the outside world is written when it is authorised,
not before. Two separate gates stand in front of it:

  1. **Endpoint.** Only `paper-api.alpaca.markets` is constructible. The live host refuses at
     construction time, not at submission time.
  2. **Owner authorisation.** PLAN.md's promotion gates and explicit owner sign-off. This rig
     cannot grant itself either, and there is no flag here that pretends to.

An agent reading this file should not implement `submit()`. Propose it as a diff.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from fractions import Fraction

from .data import FORBIDDEN_HOSTNAMES, PAPER_HOSTNAME, PAPER_TRADING_HOST, hostname_of
from .frozen import Refused


class Side(enum.Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(enum.Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"


@dataclass(frozen=True)
class Order:
    """One intent. Prices are integer micro-dollars; quantity is whole shares.

    Fractional shares are refused: they change the commission arithmetic, they are not
    shortable at most brokers, and a rig whose mandate includes shorting should not silently
    produce an order that cannot be shorted.
    """

    symbol: str
    side: Side
    order_type: OrderType
    quantity_shares: int
    limit_micros: int | None = None
    stop_micros: int | None = None
    decided_at_bar_ts_ns: int = 0

    def __post_init__(self) -> None:
        if self.quantity_shares <= 0:
            raise Refused(f"order quantity must be positive whole shares; got {self.quantity_shares}")
        if self.order_type is OrderType.LIMIT and self.limit_micros is None:
            raise Refused("a limit order without a limit price is not an order")
        if self.order_type is OrderType.STOP and self.stop_micros is None:
            raise Refused("a stop order without a stop price is not an order")
        if self.order_type is OrderType.MARKET and (self.limit_micros or self.stop_micros):
            raise Refused("a market order carrying a limit or stop price is a caller confusion")


def orders_for_target(
    symbol: str,
    target_position: Fraction,
    current_position: Fraction,
    equity_micros: int,
    price_micros: int,
    ts_ns: int,
) -> list:
    """Translate a target exposure into whole-share market orders. The same maths the engine prices.

    Rounds the share count DOWN in absolute value. Under-filling is the conservative error:
    it takes less risk than intended, whereas rounding up takes more than the position sizing
    authorised.
    """
    if price_micros <= 0:
        raise Refused("cannot size an order at a non-positive price")
    if equity_micros <= 0:
        raise Refused("cannot size an order against non-positive equity")
    delta = Fraction(target_position) - Fraction(current_position)
    if delta == 0:
        return []
    shares = int(abs(delta) * Fraction(equity_micros) / Fraction(price_micros))
    if shares == 0:
        return []
    return [Order(
        symbol=symbol,
        side=Side.BUY if delta > 0 else Side.SELL,
        order_type=OrderType.MARKET,
        quantity_shares=shares,
        decided_at_bar_ts_ns=ts_ns,
    )]


class PaperBroker:
    """Paper endpoint only. Constructing it against the live host refuses."""

    def __init__(self, host: str = PAPER_TRADING_HOST):
        # Matched on the parsed HOSTNAME. A substring test would be wrong in both directions:
        # "api.alpaca.markets" is contained in "paper-api.alpaca.markets", so a naive
        # blocklist refuses the paper host, and a naive allowlist on the paper prefix would
        # wave through "https://paper-api.alpaca.markets.evil.test".
        name = hostname_of(host)
        if name in FORBIDDEN_HOSTNAMES:
            raise Refused(
                f"{host!r} is the LIVE trading endpoint. Real-money execution is owner-gated "
                "by PLAN.md's promotion gates and cannot be reached from this rig. Refusing "
                "at construction time, not at submission time."
            )
        if name != PAPER_HOSTNAME:
            raise Refused(f"{host!r} is not the Alpaca paper endpoint ({PAPER_TRADING_HOST})")
        self.host = host

    def submit(self, order: Order):
        raise Refused(
            "Order submission is deliberately unimplemented, exactly as B22B's collection "
            "stage is.\n"
            "  Gate 1 (endpoint): satisfied -- this broker is paper-only by construction.\n"
            "  Gate 2 (authorisation): NOT satisfied -- PLAN.md's promotion gates plus "
            "explicit owner sign-off are required before any order leaves this process, "
            "paper or otherwise.\n"
            "Do not implement this in place. Propose it as a diff for owner review."
        )

    def positions(self):
        raise Refused("account reads are part of the same owner-gated seam as submit()")


__all__ = ["Side", "OrderType", "Order", "orders_for_target", "PaperBroker"]
