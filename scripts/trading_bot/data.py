#!/usr/bin/env python3
"""Alpaca bar loader. DATA endpoint only, fully paged, cached with a manifest.

ENDPOINT SAFETY (guardrail 3)
=============================
Only `data.alpaca.markets` is reachable from this module, taken from the frozen B22B
constant rather than retyped. The live trading host is listed in `FORBIDDEN_HOSTS` and any
attempt to point this loader at it refuses. Order submission does not live here at all --
see `paper.py`, where it is owner-gated.

CREDENTIALS
===========
`.env` values in this repo are quote-wrapped. `load_env_credentials` strips single and double
quotes and refuses on an empty result, because a credential that silently reads as `"KEY"`
including the quotes produces a 401 that looks like a data problem.

POINT-IN-TIME DISCIPLINE, AND THE ONE PLACE IT IS IMPERFECT
===========================================================
Bars are requested with `adjustment=all`, giving split- and dividend-adjusted prices. That is
correct for measuring TOTAL RETURN and it is **retroactive**: the adjusted price of a 2019 bar
depends on splits and dividends that had not happened in 2019.

Two consequences, both recorded in the manifest rather than left implicit:

1. **Returns are fine.** An adjusted return series is the return an investor actually earned.
2. **Price LEVELS are not point-in-time.** Any universe filter on a price level -- for
   instance Zarattini's "open > $5" -- must use `adjustment=raw`, because the adjusted price
   of a stock that later split 10:1 is not the price the filter would have seen. A filter run
   on adjusted prices is a survivorship-flavoured lookahead.

`load_bars` records the adjustment mode in the manifest and `assert_levels_are_point_in_time`
refuses if a caller tries to filter levels on an adjusted series.

SURVIVORSHIP
============
Alpaca serves data for symbols that exist today. A universe assembled from today's listings
is survivorship-biased and this loader cannot fix that; `manifest["survivorship"]` says so on
every dataset so no downstream report can claim otherwise by silence.
"""

from __future__ import annotations

import json
import pathlib
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from .engine import Bar, validate_series
from .frozen import ALPACA_DATA_HOST, API_PAGE_LIMIT, Refused

ROOT = pathlib.Path(__file__).resolve().parents[2]
DEFAULT_CACHE_DIR = ROOT / "research" / "data" / "trading_bot_cache"

# Compared as exact HOSTNAMES, never as substrings. "api.alpaca.markets" is a substring of
# "paper-api.alpaca.markets", so a substring check would refuse the paper endpoint while a
# careless one in the other direction would ALLOW the live endpoint. Both are caught by
# parsing the netloc.
FORBIDDEN_HOSTNAMES = frozenset({"api.alpaca.markets"})          # live trading
PAPER_TRADING_HOST = "https://paper-api.alpaca.markets"
PAPER_HOSTNAME = "paper-api.alpaca.markets"


def hostname_of(url: str) -> str:
    parsed = urllib.parse.urlparse(url if "//" in url else f"//{url}")
    host = (parsed.hostname or "").lower()
    if not host:
        raise Refused(f"cannot parse a hostname out of {url!r}; refusing to guess")
    return host

VALID_ADJUSTMENTS = ("raw", "split", "dividend", "all")
VALID_FEEDS = ("iex", "sip")


def load_env_credentials(env_path=None) -> tuple[str, str]:
    """Read ALPACA keys from the environment, falling back to `.env`, stripping quotes.

    Guardrail 3: `.env` values in this repo are quote-wrapped. Stripping is done for both
    quote characters and the result is checked for emptiness, because `""` strips to `""`
    and an empty credential must refuse rather than produce a mystifying 401.
    """
    import os

    path = pathlib.Path(env_path) if env_path else ROOT / ".env"
    from_file = {}
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            from_file[key.strip()] = value.strip().strip('"').strip("'")

    key = (os.environ.get("ALPACA_API_KEY_ID") or from_file.get("ALPACA_API_KEY_ID") or "")
    secret = (os.environ.get("ALPACA_API_SECRET_KEY")
              or from_file.get("ALPACA_API_SECRET_KEY") or "")
    key, secret = key.strip().strip('"').strip("'"), secret.strip().strip('"').strip("'")
    if not key or not secret:
        raise Refused(
            "ALPACA_API_KEY_ID / ALPACA_API_SECRET_KEY not found in the environment or .env. "
            "Absent is not empty-string: refusing rather than sending an unauthenticated "
            "request that would fail as if the data were missing."
        )
    return key, secret


def assert_data_host(host: str) -> str:
    """Only the market-data host is permitted here. Matched on the parsed hostname."""
    name = hostname_of(host)
    if name in FORBIDDEN_HOSTNAMES:
        raise Refused(
            f"{host!r} is the LIVE trading endpoint. This module reads market data only. "
            "Real-money execution is owner-gated and is not reachable from the backtest "
            "rig by construction."
        )
    if name != hostname_of(ALPACA_DATA_HOST):
        raise Refused(f"{host!r} is not the Alpaca market-data host ({ALPACA_DATA_HOST})")
    return host


def _fetch_page(path: str, params: dict, key: str, secret: str) -> dict:
    url = f"{assert_data_host(ALPACA_DATA_HOST)}{path}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={
        "APCA-API-KEY-ID": key,
        "APCA-API-SECRET-KEY": secret,
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:400]
        raise Refused(f"HTTP {exc.code} for {path}: {detail}") from exc


def fetch_bars(
    symbol: str,
    start: str,
    end: str,
    timeframe: str,
    *,
    feed: str = "sip",
    adjustment: str = "all",
) -> list:
    """Every bar in the window, fully paged. A truncated response is a wrong answer.

    That paging rule is B22B's (`api_get_paged`: 'a truncated response is a wrong answer, not
    a small one'). It is re-stated here because this is the one place a silently short series
    would look exactly like a quiet market.
    """
    if adjustment not in VALID_ADJUSTMENTS:
        raise Refused(f"adjustment {adjustment!r} not in {VALID_ADJUSTMENTS}")
    if feed not in VALID_FEEDS:
        raise Refused(f"feed {feed!r} not in {VALID_FEEDS}")

    key, secret = load_env_credentials()
    raw, token, pages = [], None, 0
    while True:
        params = {
            "symbols": symbol, "timeframe": timeframe, "start": start, "end": end,
            "limit": API_PAGE_LIMIT, "feed": feed, "adjustment": adjustment,
        }
        if token:
            params["page_token"] = token
        payload = _fetch_page("/v2/stocks/bars", params, key, secret)
        block = payload.get("bars")
        if block is None:
            raise Refused("response has no 'bars' key; refusing to treat that as zero bars")
        raw.extend(block.get(symbol, []))
        pages += 1
        token = payload.get("next_page_token")
        if not token:
            break
        if pages > 10_000:
            raise Refused("paging did not terminate after 10,000 pages")
    if not raw:
        raise Refused(
            f"no bars for {symbol} in {start}..{end} on feed {feed}. An empty window is a "
            "refusal, not an empty backtest."
        )
    return raw


def _manifest(symbol, start, end, timeframe, feed, adjustment, n_bars, source) -> dict:
    return {
        "symbol": symbol,
        "start": start,
        "end": end,
        "timeframe": timeframe,
        "feed": feed,
        "adjustment": adjustment,
        "n_bars": n_bars,
        "source": source,
        "host": ALPACA_DATA_HOST,
        "retrieved_utc": datetime.now(timezone.utc).isoformat(),
        "point_in_time_caveats": {
            "returns": "adjusted returns are what an investor earned; these are point-in-time correct",
            "price_levels": (
                "adjustment != 'raw' makes price LEVELS retroactive. Any universe filter on a "
                "price level (e.g. 'open > $5') run on these bars is a lookahead. Refetch with "
                "adjustment='raw' for that."
                if adjustment != "raw" else
                "raw prices: levels are point-in-time, but returns across a split are NOT."
            ),
        },
        "survivorship": (
            "Alpaca serves symbols that exist today. A universe assembled from today's "
            "listings is survivorship-biased, and this loader cannot correct that."
        ),
    }


def load_bars(
    symbol: str,
    start: str,
    end: str,
    timeframe: str = "1Day",
    *,
    feed: str = "sip",
    adjustment: str = "all",
    cache_dir=None,
    allow_network: bool = True,
) -> tuple:
    """Bars for one symbol, from cache if present, otherwise from the API. Returns (bars, manifest).

    `allow_network=False` makes the loader cache-only, which is how the test suite stays
    hermetic (`tests/_netguard.py` blocks outbound sockets for the whole session).
    """
    cache_dir = pathlib.Path(cache_dir) if cache_dir else DEFAULT_CACHE_DIR
    stem = f"{symbol}_{timeframe}_{start}_{end}_{feed}_{adjustment}".replace(":", "")
    cache_path = cache_dir / f"{stem}.json"

    if cache_path.exists():
        blob = json.loads(cache_path.read_text())
        bars = validate_series(Bar.from_alpaca(symbol, raw) for raw in blob["bars"])
        return bars, dict(blob["manifest"], source="cache", cache_path=str(cache_path))

    if not allow_network:
        raise Refused(
            f"no cached dataset at {cache_path} and allow_network=False. Refusing to run a "
            "backtest on data that does not exist."
        )

    raw = fetch_bars(symbol, start, end, timeframe, feed=feed, adjustment=adjustment)
    bars = validate_series(Bar.from_alpaca(symbol, item) for item in raw)
    manifest = _manifest(symbol, start, end, timeframe, feed, adjustment, len(bars), "alpaca")
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps({"manifest": manifest, "bars": raw}))
    return bars, dict(manifest, cache_path=str(cache_path))


def assert_levels_are_point_in_time(manifest: dict) -> None:
    """Call before any filter on a PRICE LEVEL. Refuses on an adjusted series."""
    if manifest.get("adjustment") != "raw":
        raise Refused(
            f"this dataset is adjustment={manifest.get('adjustment')!r}, so its price LEVELS "
            "are retroactive: the adjusted price of a bar depends on splits and dividends that "
            "had not happened yet. Filtering a universe on a level (open > $5, ATR > $0.50) "
            "with these bars is lookahead. Refetch with adjustment='raw' for the filter."
        )


def bars_per_year(timeframe: str) -> int:
    """Observations per year for a US-equity RTH series. Explicit table, no inference.

    `annualised_sharpe` refuses to infer this, so it has to come from somewhere; a table that
    can be read and disputed is better than arithmetic buried in a call site.
    """
    table = {
        "1Day": 252,
        "1Hour": 252 * 7,        # 09:30-16:00 is 6.5h, but Alpaca emits a partial 7th bar
        "30Min": 252 * 13,
        "15Min": 252 * 26,
        "5Min": 252 * 78,
        "1Min": 252 * 390,
    }
    if timeframe not in table:
        raise Refused(
            f"no periods-per-year entry for timeframe {timeframe!r}. Add it to the table "
            "deliberately rather than letting a Sharpe be annualised by guesswork."
        )
    return table[timeframe]


__all__ = [
    "load_env_credentials", "assert_data_host", "fetch_bars", "load_bars",
    "assert_levels_are_point_in_time", "bars_per_year", "hostname_of",
    "DEFAULT_CACHE_DIR", "FORBIDDEN_HOSTNAMES", "PAPER_TRADING_HOST", "PAPER_HOSTNAME",
]
