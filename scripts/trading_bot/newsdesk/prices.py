#!/usr/bin/env python3
"""Free, keyless price PATHS for mark-to-market resolution.

Equities/ETFs are priced on the Yahoo Finance chart endpoint (OHLC bars); crypto on CoinGecko's
market_chart range (price points). Both are free and keyless. A bar is normalized to
(ts_epoch, high, low, close); CoinGecko gives price POINTS only, so for crypto high=low=close=point
-- a granularity limitation recorded honestly in every resolution record, never hidden.

The resolver consumes ONLY bars strictly after a setup's freeze (that assertion lives in resolve.py);
this module just returns the raw path.
"""

from __future__ import annotations

import datetime as dt

from . import Refused
from .net import http_get_json


def _epoch(iso_utc: str) -> int:
    s = iso_utc.replace("Z", "+00:00")
    d = dt.datetime.fromisoformat(s)
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    return int(d.timestamp())


def equity_path(symbol: str, since_iso: str, until_iso: str, spec: dict) -> list:
    """Yahoo chart OHLC bars in (since, until]. Interval chosen from the span; returns normalized bars.

    Yahoo intraday history is only served for recent windows, so the interval widens with the span:
    <=7d -> 15m, <=60d -> 60m, else 1d. That is a data-availability choice, not a rule.
    """
    t0, t1 = _epoch(since_iso), _epoch(until_iso)
    if t1 <= t0:
        raise Refused(f"equity_path: until ({until_iso}) not after since ({since_iso})")
    span_days = (t1 - t0) / 86400.0
    interval = "15m" if span_days <= 7 else ("60m" if span_days <= 60 else "1d")
    url = (spec["sources"]["yahoo_chart"].format(symbol=symbol)
           + f"?period1={t0}&period2={t1 + 1}&interval={interval}&includePrePost=false")
    payload = http_get_json(url)
    chart = (payload.get("chart") or {})
    if chart.get("error"):
        raise Refused(f"Yahoo chart error for {symbol}: {chart['error']}")
    results = chart.get("result") or []
    if not results:
        raise Refused(f"Yahoo chart returned no result for {symbol}; absence is a refusal")
    res = results[0]
    ts = res.get("timestamp") or []
    quote = ((res.get("indicators") or {}).get("quote") or [{}])[0]
    highs, lows, closes = quote.get("high") or [], quote.get("low") or [], quote.get("close") or []
    bars = []
    for i, t in enumerate(ts):
        h, l, c = (highs[i] if i < len(highs) else None), \
                  (lows[i] if i < len(lows) else None), \
                  (closes[i] if i < len(closes) else None)
        if c is None:
            continue
        h = h if h is not None else c
        l = l if l is not None else c
        bars.append((int(t), float(h), float(l), float(c)))
    bars.sort()
    return {"bars": bars, "interval": interval, "granularity": "ohlc",
            "source": "yahoo_chart", "symbol": symbol}


def crypto_path(coingecko_id: str, since_iso: str, until_iso: str, spec: dict) -> list:
    """CoinGecko market_chart range price POINTS in (since, until]. high=low=close=point (documented)."""
    t0, t1 = _epoch(since_iso), _epoch(until_iso)
    if t1 <= t0:
        raise Refused(f"crypto_path: until ({until_iso}) not after since ({since_iso})")
    url = (spec["sources"]["coingecko_market_chart"].format(id=coingecko_id)
           + f"?vs_currency=usd&from={t0}&to={t1 + 1}")
    payload = http_get_json(url)
    prices = payload.get("prices")
    if prices is None:
        raise Refused(f"CoinGecko returned no 'prices' for {coingecko_id}; absence is a refusal")
    bars = []
    for ms, px in prices:
        bars.append((int(ms // 1000), float(px), float(px), float(px)))
    bars.sort()
    return {"bars": bars, "interval": "auto", "granularity": "price_point_no_intrabar_range",
            "source": "coingecko_market_chart", "symbol": coingecko_id}


def path_for(setup: dict, since_iso: str, until_iso: str, spec: dict) -> dict:
    if setup["asset_class"] == "equity":
        return equity_path(setup["instrument"], since_iso, until_iso, spec)
    return crypto_path(setup["instrument"], since_iso, until_iso, spec)


def spot_price(setup: dict, spec: dict) -> float:
    """A single current reference price (used only to help the agent, never to resolve)."""
    now = dt.datetime.now(dt.timezone.utc)
    since = (now - dt.timedelta(days=2)).isoformat()
    path = path_for(setup, since, now.isoformat(), spec)
    if not path["bars"]:
        raise Refused(f"no recent price for {setup['instrument']}")
    return path["bars"][-1][3]
