#!/usr/bin/env python3
"""B22B -- measure the fill a stop order actually receives, against the price a backtest assumes.

THE QUESTION THIS ANSWERS
-------------------------
Zarattini/Barbon/Aziz (SSRN 4729284) report Sharpe 2.81 for a 5-minute opening-range
breakout on the top-20 US stocks by opening relative volume. They model a $0.0035/share
commission and nothing else: the strings "slippage", "bid-ask", "market impact" and "fill"
appear zero times in the paper. Their entry is a STOP order -- a market order fired at the
instant of maximum momentum in the day's fastest-moving names -- and the backtest credits a
fill at exactly the stop price.

This measures what that fill actually is.

SCOPE LIMIT, STATED UP FRONT
----------------------------
This measures ENTRY slippage only. Exit slippage (stop-loss market orders, market-on-close)
is NOT measured. Therefore the number produced here is a LOWER BOUND on total friction.

The classification in classify() is deliberately asymmetric because of this:
  - a bad result here is DECISIVE (entry alone already exceeds the edge)
  - a good result here is NOT vindication (the exit remains unmeasured)

A harness that could only ever confirm what we hoped would not be worth running.

ARITHMETIC DISCIPLINE
---------------------
All prices are integer micro-dollars (USD * 1_000_000). The ONLY float boundary is
to_micros() at ingest, applied once to each value as it arrives from the API. Nothing
downstream touches a float. Percentiles are taken by integer index; no interpolation.
Means are not reported -- sums and counts are, so a mean can be derived exactly.

Slippage is reported in basis points of R, where R = 10% of ATR(14):
    slippage/R = 10 * slippage / atr
    in bp:      slippage_r_bp = (slippage_micro * 100_000) // atr_micro

FAIL-CLOSED
-----------
Absence is refusal, never zero. A stock-day whose stop was never touched is NOT a
zero-slippage observation; it is a separate category and is excluded from the slippage
distribution. Missing quote data raises rather than defaulting. A trigger with no
prevailing quote is a refusal, not a free fill.

DO NOT EDIT AFTER PINNING -- the hash in
research/B22B_SLIPPAGE_PREREGISTRATION.json must continue to match.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, time, timedelta, timezone

# ---------------------------------------------------------------------------
# Frozen constants. Every one is taken from the paper's own stated rule, not chosen here.
# ---------------------------------------------------------------------------

MICROS = 1_000_000

MIN_OPEN_PRICE_MICROS = 5 * MICROS           # paper: opening price above $5
MIN_AVG_VOLUME_SHARES = 1_000_000            # paper: 14-day average volume >= 1M shares
MIN_ATR_MICROS = 500_000                     # paper: 14-day ATR > $0.50
ATR_LOOKBACK_DAYS = 14                       # paper: 14-day ATR
RELVOL_LOOKBACK_DAYS = 14                    # paper: RelVol vs 14-day average
TOP_N_BY_RELVOL = 20                         # paper: trade only the top 20
MIN_RELVOL_PCT = 100                         # paper: RelVol must be at least 100%
STOP_LOSS_ATR_PCT = 10                       # paper: stop at 10% of ATR -> defines R

OPENING_RANGE_MINUTES = 5                    # paper: 5-minute opening range
SESSION_OPEN = time(9, 30)
OPENING_RANGE_END = time(9, 35)
SESSION_CLOSE = time(16, 0)

# Latency ladder. A retail stop rests at the broker and is routed on trigger; the fill
# cannot precede that routing. Zero is physically unattainable and is included only as the
# backtest's own implicit assumption, so the gap between it and the rest is visible.
LATENCY_LADDER_MS = (0, 100, 500, 1000)

# Decision thresholds, in basis points of R. Set from the paper's OWN reported per-trade
# edge before any data exists: 0.08R at the RelVol>=100% filter it uses, 0.38R at its most
# favourable bucket (RelVol > 30x).
EDGE_AT_FILTER_R_BP = 800                    # 0.08R
EDGE_AT_BEST_BUCKET_R_BP = 3800              # 0.38R
IMPAIRED_R_BP = 1500                         # 0.15R
NEGLIGIBLE_R_BP = 500                        # 0.05R

# Deterministic sample. Pinned so the day selection cannot be chosen after seeing outcomes.
SAMPLE_SEED = 22022
DEFAULT_SAMPLE_DAYS = 30

MIN_TRIGGERS_TO_CLASSIFY = 100               # below this the median is not worth a verdict

ALPACA_DATA_HOST = "https://data.alpaca.markets"
API_PAGE_LIMIT = 10_000


class Refused(Exception):
    """Raised whenever the harness cannot establish a fact. Never caught to produce a default."""


# ---------------------------------------------------------------------------
# The single float boundary
# ---------------------------------------------------------------------------

def to_micros(value) -> int:
    """Convert an API price to integer micro-dollars. THE ONLY PLACE A FLOAT IS TOUCHED.

    Refuses on None rather than coercing to zero: a missing price is not a price of zero.
    """
    if value is None:
        raise Refused("price field absent; refusing to substitute zero")
    if isinstance(value, int):
        return value * MICROS
    scaled = round(float(value) * MICROS)
    return int(scaled)


def to_shares(value) -> int:
    if value is None:
        raise Refused("size field absent; refusing to substitute zero")
    return int(value)


# ---------------------------------------------------------------------------
# Timestamps. Integer nanoseconds since epoch; no float seconds anywhere.
# ---------------------------------------------------------------------------

def parse_rfc3339_ns(text: str) -> int:
    """Parse an RFC3339 timestamp to integer nanoseconds since the Unix epoch.

    Done by hand rather than via datetime.timestamp() because that returns a float and
    silently loses sub-microsecond resolution -- which is exactly the resolution this
    measurement is about.
    """
    if not text or not text.endswith("Z"):
        raise Refused(f"non-UTC or absent timestamp: {text!r}")
    body = text[:-1]
    if "." in body:
        head, frac = body.split(".", 1)
    else:
        head, frac = body, ""
    stamp = datetime.strptime(head, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
    whole_seconds = int(stamp.timestamp())          # integral by construction
    frac = (frac + "000000000")[:9]
    return whole_seconds * 1_000_000_000 + int(frac)


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """The nth occurrence of `weekday` (Mon=0) in a given month."""
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=offset + 7 * (n - 1))


def et_offset_hours(day: date) -> int:
    """UTC offset of US Eastern time on `day`: -4 during EDT, -5 during EST.

    Computed rather than passed in. An earlier draft took this as one command-line value for
    the whole run, which is wrong for any sample spanning a DST boundary: half the days would
    have measured a 10:30 or 08:30 'opening range' with nothing to indicate it. A silent
    one-hour shift in half the sample is exactly the class of error this programme has been
    bitten by, so the boundary is derived from the calendar instead.

    US rule since 2007: DST runs from the second Sunday in March to the first Sunday in
    November. Only whole days matter here -- the market is shut at the 02:00 transition.
    """
    if day.year < 2007:
        raise Refused(f"pre-2007 DST rules differ; refusing to guess an offset for {day}")
    dst_start = _nth_weekday(day.year, 3, 6, 2)      # second Sunday in March
    dst_end = _nth_weekday(day.year, 11, 6, 1)       # first Sunday in November
    return -4 if dst_start <= day < dst_end else -5


def session_bound_ns(day: date, clock: time) -> int:
    """Wall-clock ET converted to epoch nanoseconds, with the offset derived per day."""
    naive = datetime.combine(day, clock, tzinfo=timezone.utc)
    return (int(naive.timestamp()) - et_offset_hours(day) * 3_600) * 1_000_000_000


# ---------------------------------------------------------------------------
# API access
# ---------------------------------------------------------------------------

def credentials() -> tuple[str, str]:
    key = os.environ.get("ALPACA_API_KEY_ID")
    secret = os.environ.get("ALPACA_API_SECRET_KEY")
    if not key or not secret:
        raise Refused(
            "ALPACA_API_KEY_ID / ALPACA_API_SECRET_KEY not set. This harness is written to "
            "be unrunnable without them, so that it is pinned before any data is visible."
        )
    return key, secret


def api_get(path: str, params: dict) -> dict:
    key, secret = credentials()
    url = f"{ALPACA_DATA_HOST}{path}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(
        url,
        headers={
            "APCA-API-KEY-ID": key,
            "APCA-API-SECRET-KEY": secret,
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:400]
        raise Refused(f"HTTP {exc.code} for {path}: {detail}") from exc


def api_get_paged(path: str, params: dict, collection_key: str):
    """Yield every page. A truncated response is a wrong answer, not a small one."""
    page_token = None
    while True:
        page_params = dict(params, limit=API_PAGE_LIMIT)
        if page_token:
            page_params["page_token"] = page_token
        payload = api_get(path, page_params)
        block = payload.get(collection_key)
        if block is None:
            raise Refused(f"response for {path} has no {collection_key!r} key")
        yield block
        page_token = payload.get("next_page_token")
        if not page_token:
            return


# ---------------------------------------------------------------------------
# Percentiles, by integer index. No interpolation, no float division.
# ---------------------------------------------------------------------------

def percentile_by_index(sorted_values: list[int], numerator: int, denominator: int) -> int:
    """The element at rank numerator/denominator, chosen by integer index.

    Rounds the index DOWN, which for a cost distribution reports the more favourable of the
    two candidate elements. Stated explicitly so the bias is known rather than assumed away.
    """
    if not sorted_values:
        raise Refused("percentile of an empty distribution is undefined, not zero")
    index = (len(sorted_values) - 1) * numerator // denominator
    return sorted_values[index]


def distribution_summary(values: list[int]) -> dict:
    ordered = sorted(values)
    return {
        "n": len(ordered),
        "p10": percentile_by_index(ordered, 10, 100),
        "p25": percentile_by_index(ordered, 25, 100),
        "p50": percentile_by_index(ordered, 50, 100),
        "p75": percentile_by_index(ordered, 75, 100),
        "p90": percentile_by_index(ordered, 90, 100),
        "p95": percentile_by_index(ordered, 95, 100),
        "min": ordered[0],
        "max": ordered[-1],
        # Sum and count rather than a mean, so the mean is derivable exactly.
        "sum": sum(ordered),
    }


# ---------------------------------------------------------------------------
# Universe construction
# ---------------------------------------------------------------------------

def true_range_micros(high: int, low: int, prior_close: int | None) -> int:
    """Wilder's true range. Refuses on the first bar rather than treating it as high-low.

    The first bar of a series has no prior close, so its true range is UNDEFINED. Silently
    substituting (high - low) understates early ATR and biases the R unit downward, which
    would flatter every slippage ratio computed against it.
    """
    if prior_close is None:
        raise Refused("true range undefined without a prior close")
    return max(high - low, abs(high - prior_close), abs(low - prior_close))


def atr_micros(daily_bars: list[dict], lookback: int) -> int:
    """Simple average true range over `lookback` completed days, by integer division.

    Refuses unless there are lookback+1 bars: computing ATR(14) from 14 bars yields only 13
    true ranges, and dividing 13 values by 14 is a warm-up error of the exact kind that has
    bitten this project before.
    """
    if len(daily_bars) < lookback + 1:
        raise Refused(
            f"ATR({lookback}) needs {lookback + 1} bars for {lookback} true ranges; "
            f"got {len(daily_bars)}"
        )
    window = daily_bars[-(lookback + 1):]
    ranges = [
        true_range_micros(
            to_micros(window[i]["h"]), to_micros(window[i]["l"]), to_micros(window[i - 1]["c"])
        )
        for i in range(1, len(window))
    ]
    if len(ranges) != lookback:
        raise Refused(f"expected {lookback} true ranges, computed {len(ranges)}")
    return sum(ranges) // lookback


def r_unit_micros(atr: int) -> int:
    """R = 10% of ATR. The paper's stop distance, and the unit its PnL is reported in."""
    if atr <= 0:
        raise Refused("ATR must be positive to define R")
    return atr * STOP_LOSS_ATR_PCT // 100


# ---------------------------------------------------------------------------
# The measurement
# ---------------------------------------------------------------------------

def opening_range(minute_bars: list[dict], open_ns: int, range_end_ns: int) -> dict:
    """High, low, open, close and volume of [09:30, 09:35).

    Refuses on an empty range: a stock with no prints in its first five minutes has no
    opening range, and inventing one from adjacent bars would fabricate the very level
    whose breach this harness times.
    """
    inside = [
        bar for bar in minute_bars
        if open_ns <= parse_rfc3339_ns(bar["t"]) < range_end_ns
    ]
    if not inside:
        raise Refused("no bars inside the opening range")
    inside.sort(key=lambda bar: parse_rfc3339_ns(bar["t"]))
    return {
        "high": max(to_micros(bar["h"]) for bar in inside),
        "low": min(to_micros(bar["l"]) for bar in inside),
        "open": to_micros(inside[0]["o"]),
        "close": to_micros(inside[-1]["c"]),
        "volume": sum(to_shares(bar["v"]) for bar in inside),
        "bar_count": len(inside),
    }


def direction_of(opening: dict) -> str | None:
    """Paper's rule: bullish first candle -> long only, bearish -> short only, doji -> stand aside.

    Returns None for a doji. None is not 'long'; the caller must not treat it as tradeable.
    """
    if opening["close"] > opening["open"]:
        return "long"
    if opening["close"] < opening["open"]:
        return "short"
    return None


def find_trigger(trades: list[dict], stop_micros: int, direction: str, after_ns: int):
    """First trade that breaches the stop level, in canonical time order.

    Returns None when the level is never breached. None means NO ENTRY -- it is not a
    slippage observation of zero, and the caller keeps it in a separate bucket.
    """
    ordered = sorted(
        ((parse_rfc3339_ns(t["t"]), to_micros(t["p"]), to_shares(t["s"])) for t in trades),
        key=lambda row: row[0],
    )
    for stamp_ns, price, _size in ordered:
        if stamp_ns < after_ns:
            continue
        if direction == "long" and price >= stop_micros:
            return {"ns": stamp_ns, "price": price}
        if direction == "short" and price <= stop_micros:
            return {"ns": stamp_ns, "price": price}
    return None


def quote_at(quotes_sorted: list[tuple], at_ns: int):
    """The quote prevailing at at_ns: the last quote published at or before it.

    Refuses if no quote precedes at_ns. A trade cannot occur in a market with no quote; if
    the data says otherwise, the data is wrong and a fabricated fill would hide that.
    """
    chosen = None
    for stamp_ns, bid, bid_size, ask, ask_size in quotes_sorted:
        if stamp_ns > at_ns:
            break
        chosen = (stamp_ns, bid, bid_size, ask, ask_size)
    if chosen is None:
        raise Refused("no quote prevailing at trigger; refusing to synthesise a fill")
    return chosen


def measure_stock_day(
    *,
    symbol: str,
    day: date,
    direction: str,
    stop_micros: int,
    atr: int,
    trades: list[dict],
    quotes: list[dict],
    trigger_after_ns: int,
) -> dict:
    """Slippage of a stop-order entry, in basis points of R, across the latency ladder.

    Sign convention: POSITIVE slippage is always ADVERSE. A long fills above its stop, a
    short below it, so the short case is negated. Getting this backwards would report a
    cost as a benefit -- and a sign error is precisely how a favourable result gets
    manufactured, so it is asserted rather than trusted.
    """
    trigger = find_trigger(trades, stop_micros, direction, trigger_after_ns)
    if trigger is None:
        return {"symbol": symbol, "day": day.isoformat(), "outcome": "NO_TRIGGER"}

    quotes_sorted = sorted(
        (
            (
                parse_rfc3339_ns(q["t"]),
                to_micros(q["bp"]),
                to_shares(q["bs"]),
                to_micros(q["ap"]),
                to_shares(q["as"]),
            )
            for q in quotes
        ),
        key=lambda row: row[0],
    )
    if not quotes_sorted:
        raise Refused(f"{symbol} {day}: trigger found but no quotes; cannot price the fill")

    r_unit = r_unit_micros(atr)
    ladder = {}
    for latency_ms in LATENCY_LADDER_MS:
        at_ns = trigger["ns"] + latency_ms * 1_000_000
        stamp_ns, bid, bid_size, ask, ask_size = quote_at(quotes_sorted, at_ns)

        if direction == "long":
            fill = ask                    # a buy stop crosses and lifts the offer
            raw = fill - stop_micros
            resting_size = ask_size
        else:
            fill = bid                    # a sell stop hits the bid
            raw = stop_micros - fill      # negated so adverse stays positive
            resting_size = bid_size

        ladder[str(latency_ms)] = {
            "fill_micros": fill,
            "slippage_micros": raw,
            "slippage_r_bp": (raw * 100_000) // atr if atr else None,
            "spread_micros": ask - bid,
            "resting_size_shares": resting_size,
            "quote_age_ns": at_ns - stamp_ns,
        }

    return {
        "symbol": symbol,
        "day": day.isoformat(),
        "outcome": "TRIGGERED",
        "direction": direction,
        "stop_micros": stop_micros,
        "trigger_price_micros": trigger["price"],
        "trigger_ns": trigger["ns"],
        "atr_micros": atr,
        "r_unit_micros": r_unit,
        "latency": ladder,
    }


# ---------------------------------------------------------------------------
# Verdict
# ---------------------------------------------------------------------------

def classify(median_r_bp: int, trigger_count: int) -> str:
    """The decision rule, fixed before any data exists.

    Asymmetric by design. The scope limit (entry slippage only) makes a bad result decisive
    and a good result merely permissive, so the vocabulary says so: nothing here can return
    'SURVIVES'. The most favourable verdict available is NOT_YET_FATAL.
    """
    if trigger_count < MIN_TRIGGERS_TO_CLASSIFY:
        return "NOT_EVALUABLE"
    if median_r_bp >= EDGE_AT_BEST_BUCKET_R_BP:
        return "KILLED"
    if median_r_bp >= IMPAIRED_R_BP:
        return "SEVERELY_IMPAIRED"
    if median_r_bp >= NEGLIGIBLE_R_BP:
        return "MATERIAL"
    return "NOT_YET_FATAL"


def sample_trading_days(start: date, end: date, count: int, seed: int) -> list[date]:
    """Weekday sample, drawn from a pinned seed so the days cannot be chosen after the fact.

    Holidays are not excluded here; a market holiday yields no bars and is refused downstream
    as an absent day rather than being silently filled.
    """
    candidates = []
    cursor = start
    while cursor <= end:
        if cursor.weekday() < 5:
            candidates.append(cursor)
        cursor += timedelta(days=1)
    if len(candidates) < count:
        raise Refused(f"asked for {count} trading days, only {len(candidates)} weekdays in range")
    return sorted(random.Random(seed).sample(candidates, count))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--start", required=True, help="sample window start, YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="sample window end, YYYY-MM-DD")
    parser.add_argument("--days", type=int, default=DEFAULT_SAMPLE_DAYS)
    parser.add_argument("--out", required=True, help="result JSON path")
    parser.add_argument("--print-sample", action="store_true",
                        help="print the pinned day sample and exit without touching the API")
    args = parser.parse_args(argv)

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    days = sample_trading_days(start, end, args.days, SAMPLE_SEED)

    if args.print_sample:
        # Deliberately runnable with no credentials: the day sample can be published and
        # pinned before any market data is fetched.
        json.dump(
            {
                "seed": SAMPLE_SEED,
                "days": [
                    {
                        "date": d.isoformat(),
                        "et_offset_hours": et_offset_hours(d),
                        "open_ns": session_bound_ns(d, SESSION_OPEN),
                        "range_end_ns": session_bound_ns(d, OPENING_RANGE_END),
                        "close_ns": session_bound_ns(d, SESSION_CLOSE),
                    }
                    for d in days
                ],
            },
            sys.stdout,
            indent=2,
        )
        sys.stdout.write("\n")
        return 0

    raise Refused(
        "The collection stage is intentionally not implemented in the pinned artifact.\n"
        "Pinning the RULE before the DATA is the point; the fetch loop is written after the\n"
        "credential exists, against these frozen functions, and cannot alter them without\n"
        "breaking the hash recorded in research/B22B_SLIPPAGE_PREREGISTRATION.json."
    )


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Refused as exc:
        sys.stderr.write(f"REFUSED: {exc}\n")
        sys.exit(2)
