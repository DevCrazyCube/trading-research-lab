#!/usr/bin/env python3
"""Exact bankroll and profit-lock policy for PAC_SCALP_LL (paper-only until promoted).

Trade exits preserve convexity; portfolio settlement compounds 75% of each realised gain and locks
25% in a non-trading reserve.  Sizing never reads an unrealised mark and never changes an open order.
All values are integer USD cents so a $100 book starts with a meaningful $10 probe.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
import time

from .execution import RefusedExecution


START_TRADING_CENTS = 10_000
MIN_POSITION_CENTS = 1_000
MAX_POSITION_CENTS = 5_000
POSITION_FRACTION_NUM = 1
POSITION_FRACTION_DEN = 10
MAX_GROSS_FRACTION_NUM = 2
MAX_GROSS_FRACTION_DEN = 5
PROFIT_LOCK_NUM = 1
PROFIT_LOCK_DEN = 4
DAILY_LOSS_NUM = 1
DAILY_LOSS_DEN = 5
CAPACITY_MULTIPLE = 6
UTC_DAY_NANOS = 86_400_000_000_000
AUTHORIZATION_TTL_NANOS = 5_000_000_000


def _exact_nonnegative(name: str, value: object) -> int:
    if type(value) is not int or value < 0:
        raise RefusedExecution(f"portfolio {name} is not an exact non-negative integer")
    return value


def _identifier(name: str, value: object) -> str:
    if (not isinstance(value, str) or not value or len(value) > 160
            or any(ord(char) < 33 or ord(char) > 126 for char in value)):
        raise RefusedExecution(f"portfolio {name} is invalid")
    return value


@dataclass(frozen=True)
class Allocation:
    position_id: str
    notional_cents: int
    authorization_id: str

    def __post_init__(self) -> None:
        _identifier("position id", self.position_id)
        _identifier("authorization id", self.authorization_id)
        notional = _exact_nonnegative("allocation notional", self.notional_cents)
        if notional < MIN_POSITION_CENTS:
            raise RefusedExecution("portfolio allocation is below the frozen minimum")


@dataclass(frozen=True)
class Portfolio:
    trading_equity_cents: int = START_TRADING_CENTS
    locked_profit_cents: int = 0
    allocations: tuple[Allocation, ...] = ()
    revision: int = 0
    day_id: int = 0
    day_start_trading_cents: int = START_TRADING_CENTS
    day_realized_pnl_cents: int = 0
    halted_for_day: bool = False
    profit_lock_remainder: int = 0
    settled_resolution_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("trading_equity_cents", "locked_profit_cents",
                     "day_start_trading_cents", "revision", "profit_lock_remainder"):
            _exact_nonnegative(name, getattr(self, name))
        if (type(self.day_id) is not int or self.day_id < 0
                or type(self.day_realized_pnl_cents) is not int
                or type(self.halted_for_day) is not bool):
            raise RefusedExecution("portfolio day state is invalid")
        if (not isinstance(self.allocations, tuple)
                or any(not isinstance(item, Allocation) for item in self.allocations)
                or len({item.position_id for item in self.allocations}) != len(self.allocations)
                or len({item.authorization_id for item in self.allocations})
                != len(self.allocations)):
            raise RefusedExecution("portfolio allocation book is invalid")
        if (not isinstance(self.settled_resolution_ids, tuple)
                or len(set(self.settled_resolution_ids)) != len(self.settled_resolution_ids)):
            raise RefusedExecution("portfolio resolution book is invalid")
        for resolution_id in self.settled_resolution_ids:
            _identifier("resolution id", resolution_id)
        if self.profit_lock_remainder >= PROFIT_LOCK_DEN:
            raise RefusedExecution("portfolio profit-lock carry is invalid")
        if self.open_gross_cents > self.trading_equity_cents:
            raise RefusedExecution("portfolio open gross exceeds trading equity")

    @property
    def total_capital_cents(self) -> int:
        return self.trading_equity_cents + self.locked_profit_cents

    @property
    def open_gross_cents(self) -> int:
        return sum(item.notional_cents for item in self.allocations)


def _utc_day(now_unix_nanos: int) -> int:
    if type(now_unix_nanos) is not int or now_unix_nanos <= 0:
        raise RefusedExecution("portfolio trusted clock is invalid")
    return now_unix_nanos // UTC_DAY_NANOS


def _roll_to_now(book: Portfolio, now_unix_nanos: int) -> Portfolio:
    if not isinstance(book, Portfolio):
        raise RefusedExecution("portfolio day roll requires typed state")
    day_id = _utc_day(now_unix_nanos)
    if book.day_id > day_id:
        raise RefusedExecution("portfolio state is from a future UTC day")
    if day_id == book.day_id:
        return book
    return replace(book, revision=book.revision + 1, day_id=day_id,
                   day_start_trading_cents=book.trading_equity_cents,
                   day_realized_pnl_cents=0, halted_for_day=False)


def next_position_cents(book: Portfolio, *, curve_exit_capacity_cents: int) -> int | None:
    """Return the next frozen notional, or None when risk/capacity refuses a new position."""
    if not isinstance(book, Portfolio):
        raise RefusedExecution("portfolio sizing requires typed state")
    capacity = _exact_nonnegative("curve exit capacity", curve_exit_capacity_cents)
    if book.halted_for_day:
        return None
    target = book.trading_equity_cents * POSITION_FRACTION_NUM // POSITION_FRACTION_DEN
    target = min(MAX_POSITION_CENTS, max(MIN_POSITION_CENTS, target))
    gross_cap = book.trading_equity_cents * MAX_GROSS_FRACTION_NUM // MAX_GROSS_FRACTION_DEN
    remaining_gross = max(0, gross_cap - book.open_gross_cents)
    sized = min(target, remaining_gross, capacity // CAPACITY_MULTIPLE)
    return sized if sized >= MIN_POSITION_CENTS else None


@dataclass(frozen=True)
class SizeAuthorization:
    position_id: str
    book_revision: int
    issued_unix_nanos: int
    day_id: int
    curve_exit_capacity_cents: int
    notional_cents: int
    authorization_id: str


def _authorization_id(*, position_id: str, book_revision: int, issued_unix_nanos: int,
                      day_id: int, capacity: int, notional: int) -> str:
    body = {"position_id": position_id, "book_revision": book_revision,
            "issued_unix_nanos": issued_unix_nanos, "day_id": day_id,
            "curve_exit_capacity_cents": capacity, "notional_cents": notional}
    return hashlib.sha256(json.dumps(
        body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def authorize_next(book: Portfolio, *, position_id: str,
                   curve_exit_capacity_cents: int) -> tuple[Portfolio, SizeAuthorization] | None:
    """Issue a short-lived, one-shot size bound to the exact current book revision."""
    position = _identifier("position id", position_id)
    capacity = _exact_nonnegative("curve exit capacity", curve_exit_capacity_cents)
    now = time.time_ns()
    current = _roll_to_now(book, now)
    if (position in {item.position_id for item in current.allocations}
            or current.halted_for_day):
        return None
    notional = next_position_cents(current, curve_exit_capacity_cents=capacity)
    if notional is None:
        return None
    auth_id = _authorization_id(
        position_id=position, book_revision=current.revision,
        issued_unix_nanos=now, day_id=current.day_id, capacity=capacity,
        notional=notional)
    return current, SizeAuthorization(
        position, current.revision, now, current.day_id, capacity, notional, auth_id)


def open_authorized(book: Portfolio, authorization: SizeAuthorization) -> Portfolio:
    """Consume one exact sizing decision; arbitrary notional opens are impossible."""
    if not isinstance(book, Portfolio) or not isinstance(authorization, SizeAuthorization):
        raise RefusedExecution("portfolio open requires typed state/authorization")
    now = time.time_ns()
    current = _roll_to_now(book, now)
    auth = authorization
    if (auth.book_revision != current.revision or auth.day_id != current.day_id
            or auth.issued_unix_nanos > now
            or now - auth.issued_unix_nanos > AUTHORIZATION_TTL_NANOS
            or auth.position_id in {item.position_id for item in current.allocations}
            or auth.authorization_id in {
                item.authorization_id for item in current.allocations}):
        raise RefusedExecution("portfolio sizing authorization is stale or already consumed")
    expected_notional = next_position_cents(
        current, curve_exit_capacity_cents=auth.curve_exit_capacity_cents)
    expected_id = _authorization_id(
        position_id=auth.position_id, book_revision=auth.book_revision,
        issued_unix_nanos=auth.issued_unix_nanos, day_id=auth.day_id,
        capacity=auth.curve_exit_capacity_cents, notional=auth.notional_cents)
    if (expected_notional is None or auth.notional_cents != expected_notional
            or auth.authorization_id != expected_id):
        raise RefusedExecution("portfolio sizing authorization was forged or capacity drifted")
    allocation = Allocation(auth.position_id, auth.notional_cents, auth.authorization_id)
    return replace(current, allocations=current.allocations + (allocation,),
                   revision=current.revision + 1)


def _pnl_cents(notional: int, return_num: int, return_den: int) -> int:
    if type(return_num) is not int or type(return_den) is not int or return_den <= 0:
        raise RefusedExecution("portfolio settlement return is not an exact fraction")
    product = notional * return_num
    if product >= 0:
        return product // return_den
    return -((-product + return_den - 1) // return_den)


def settle_position(book: Portfolio, *, position_id: str, resolution_id: str,
                    net_return_num: int, net_return_den: int) -> Portfolio:
    """Settle one all-cost result; positive cents are 75% compounded and 25% locked."""
    if not isinstance(book, Portfolio):
        raise RefusedExecution("portfolio settlement requires typed state")
    position = _identifier("position id", position_id)
    resolution = _identifier("resolution id", resolution_id)
    current = _roll_to_now(book, time.time_ns())
    if resolution in current.settled_resolution_ids:
        raise RefusedExecution("portfolio resolution was already settled")
    matches = [item for item in current.allocations if item.position_id == position]
    if len(matches) != 1:
        raise RefusedExecution("portfolio settlement does not bind one open position")
    notional = matches[0].notional_cents
    pnl = _pnl_cents(notional, net_return_num, net_return_den)
    if pnl < -notional:
        raise RefusedExecution("portfolio settlement loses more than the full position")
    lock_units = current.profit_lock_remainder
    if pnl > 0:
        lock_units += pnl * PROFIT_LOCK_NUM
    locked, remainder = divmod(lock_units, PROFIT_LOCK_DEN)
    trading = current.trading_equity_cents + pnl - locked
    if trading < 0:
        raise RefusedExecution("portfolio settlement makes trading equity negative")
    daily = current.day_realized_pnl_cents + pnl
    daily_floor = -(current.day_start_trading_cents * DAILY_LOSS_NUM // DAILY_LOSS_DEN)
    remaining = tuple(item for item in current.allocations if item.position_id != position)
    return replace(
        current, trading_equity_cents=trading,
        locked_profit_cents=current.locked_profit_cents + locked,
        profit_lock_remainder=remainder, allocations=remaining,
        day_realized_pnl_cents=daily,
        halted_for_day=(daily <= daily_floor), revision=current.revision + 1,
        settled_resolution_ids=current.settled_resolution_ids + (resolution,))
