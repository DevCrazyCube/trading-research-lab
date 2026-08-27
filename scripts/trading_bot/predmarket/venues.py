#!/usr/bin/env python3
"""The venue readers -- pull OPEN politics/policy/soft-news markets and their live implied probability.

Two FREE, KEYLESS, READ-ONLY public sources (verified live 2026-08-23):

  * KALSHI  https://api.elections.kalshi.com/trade-api/v2/events?with_nested_markets=true
            Category lives on the EVENT ('Politics' / 'Elections' / 'World' / ...). Live prices live on
            the nested market in `*_dollars` fields (yes_bid_dollars, yes_ask_dollars, last_price_dollars).
  * POLYMARKET  https://gamma-api.polymarket.com/events?tag_slug=politics&closed=false
            Category lives on the event `tags`; each nested market carries outcomePrices / bestBid /
            bestAsk / spread. YES is outcome[0].

Every market is normalized to a common shape (see `_market_record`). Macro-print and crypto-threshold
markets are the EFFICIENT categories the scope doc says to SKIP (§7 ranks 4-5); `is_selectable`
enforces the rank-1-only concentration in code.

The COST MODEL `round_trip_cost(...)` is the fee+half-spread wall from scope §4: a proposal must clear
this to be worth a hypothetical bet. It is measured PER MARKET from the live book, not assumed.
"""

from __future__ import annotations

import datetime as dt
import json
import math

from . import Refused
from .net import http_get_json

KALSHI_EVENTS = ("https://api.elections.kalshi.com/trade-api/v2/events"
                 "?limit=200&status=open&with_nested_markets=true")
POLY_EVENTS = ("https://gamma-api.polymarket.com/events?closed=false&limit={limit}"
               "&order=volume&ascending=false&tag_slug={tag}")

# Rank-1 categories only (scope §7). Kalshi event categories:
KALSHI_POLITICAL_CATEGORIES = frozenset({"Politics", "Elections", "World"})
# Polymarket tag slugs that map to politics/policy/soft-news:
POLY_POLITICAL_TAGS = ("politics", "geopolitics", "elections", "world", "us-current-affairs",
                       "trump", "world-elections", "policy")

# Ranks 4-5 to SKIP even if they slip into a political event (macro prints, crypto thresholds).
_EFFICIENT_KEYWORDS = ("cpi", "inflation print", "fed ", "fomc", "interest rate decision",
                       "jobs report", "nonfarm", "payrolls", "gdp ", "pce ",
                       "bitcoin", "ethereum", "btc ", "eth ", " price above", " price below",
                       "close above", "close below")


def _iso_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _parse_dt(s: str):
    if not s:
        return None
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _is_efficient_market(question: str) -> bool:
    q = (question or "").lower()
    return any(k in q for k in _EFFICIENT_KEYWORDS)


def round_trip_cost(venue: str, p_mid: float, spread: float, spec: dict) -> float:
    """Modeled round-trip cost (the fee/spread WALL from scope §4), in probability/$ units.

    Kalshi: taker fee per contract per side = ceil(coeff * p*(1-p) * 100)/100; round trip ~= 2 sides,
            plus one half-spread crossed. Polymarket: 0% fee + half-spread crossed.
    `spread` is the measured ask-bid from the live book (already in $/prob units).
    """
    half_spread = max(0.0, spread) / 2.0
    if venue == "kalshi":
        coeff = spec["cost_model"]["kalshi_fee_coeff"]
        fee_one_side = math.ceil(coeff * p_mid * (1.0 - p_mid) * 100.0) / 100.0
        return 2.0 * fee_one_side + half_spread
    if venue == "polymarket":
        return spec["cost_model"]["polymarket_fee"] + half_spread
    raise Refused(f"unknown venue {venue!r} for cost model")


def _market_record(**kw) -> dict:
    """The common normalized market shape both venues emit."""
    return {
        "venue": kw["venue"], "market_id": kw["market_id"], "question": kw["question"],
        "category": kw["category"], "p_market": kw["p_market"],
        "yes_bid": kw["yes_bid"], "yes_ask": kw["yes_ask"], "spread": kw["spread"],
        "volume": kw.get("volume"), "close_time": kw.get("close_time"),
        "resolution_criteria": (kw.get("resolution_criteria") or "")[:600],
        "url_ref": kw.get("url_ref"), "fetched_utc": kw["fetched_utc"],
    }


def is_selectable(m: dict, spec: dict, *, min_volume: float = 0.0) -> tuple[bool, str]:
    """Enforce the rank-1-only, tradeable-book, OPEN, future-close discipline (scope §7 + §4)."""
    if m["p_market"] is None or not (0.0 < m["p_market"] < 1.0):
        return False, "no live two-sided implied probability"
    if _is_efficient_market(m["question"]):
        return False, "efficient category (macro-print / crypto-threshold) -- scope ranks 4-5, skip"
    ct = _parse_dt(m.get("close_time"))
    if ct is not None and ct <= dt.datetime.now(dt.timezone.utc):
        return False, "close_time is in the past; not an OPEN forward market"
    if (m.get("volume") or 0) < min_volume:
        return False, f"volume below min {min_volume}"
    return True, "ok"


# --------------------------------------------------------------------------- Kalshi

def _kalshi_price(m: dict, key: str):
    v = m.get(key)
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def pull_kalshi() -> list:
    data = http_get_json(KALSHI_EVENTS)
    now = _iso_now()
    out = []
    for e in data.get("events", []):
        if e.get("category") not in KALSHI_POLITICAL_CATEGORIES:
            continue
        etitle = e.get("title") or ""
        for m in e.get("markets", []):
            if m.get("status") not in ("active", "open", None):
                continue
            yb = _kalshi_price(m, "yes_bid_dollars")
            ya = _kalshi_price(m, "yes_ask_dollars")
            if yb is None or ya is None or (yb <= 0 and ya <= 0):
                continue
            mid = round((yb + ya) / 2.0, 4)
            sub = m.get("yes_sub_title") or ""
            question = f"{etitle} -- {sub}" if sub else etitle
            out.append(_market_record(
                venue="kalshi", market_id=m.get("ticker"), question=question,
                category=e.get("category"), p_market=mid, yes_bid=yb, yes_ask=ya,
                spread=round(max(0.0, ya - yb), 4),
                volume=_kalshi_price(m, "volume_fp") or _kalshi_price(m, "volume_24h_fp"),
                close_time=m.get("close_time"),
                resolution_criteria=(m.get("rules_primary") or ""),
                url_ref=f"https://kalshi.com/markets/{m.get('event_ticker')}",
                fetched_utc=now))
    return out


# --------------------------------------------------------------------------- Polymarket

def _poly_yes_price(m: dict):
    try:
        prices = json.loads(m.get("outcomePrices") or "[]")
        outcomes = json.loads(m.get("outcomes") or "[]")
    except (TypeError, ValueError):
        return None
    if len(prices) != 2 or len(outcomes) != 2:
        return None  # multi-outcome handled per-market below only for binary Yes/No
    if [o.lower() for o in outcomes] != ["yes", "no"]:
        return None
    try:
        return float(prices[0])
    except (TypeError, ValueError):
        return None


def pull_polymarket(limit: int = 40) -> list:
    now = _iso_now()
    seen, out = set(), []
    for tag in POLY_POLITICAL_TAGS:
        try:
            events = http_get_json(POLY_EVENTS.format(limit=limit, tag=tag))
        except Refused:
            continue
        for e in events:
            tags = [t.get("slug") for t in (e.get("tags") or [])]
            for m in e.get("markets", []):
                mid_from_prices = _poly_yes_price(m)
                bid, ask = m.get("bestBid"), m.get("bestAsk")
                if bid is None or ask is None:
                    continue
                try:
                    bid, ask = float(bid), float(ask)
                except (TypeError, ValueError):
                    continue
                mid = mid_from_prices if mid_from_prices is not None else round((bid + ask) / 2.0, 4)
                mid = round(mid, 4)
                mid_key = m.get("id")
                if mid_key in seen or m.get("closed"):
                    continue
                seen.add(mid_key)
                out.append(_market_record(
                    venue="polymarket", market_id=mid_key, question=m.get("question"),
                    category="/".join(tags[:3]) or "politics", p_market=mid,
                    yes_bid=bid, yes_ask=ask,
                    spread=round(max(0.0, (m.get("spread") if m.get("spread") is not None
                                          else ask - bid)), 4),
                    volume=float(m.get("volume") or 0.0),
                    close_time=m.get("endDate"),
                    resolution_criteria=(m.get("description") or ""),
                    url_ref=f"https://polymarket.com/event/{e.get('slug')}",
                    fetched_utc=now))
    return out


def pull_open_markets(spec: dict, *, min_volume: float = 0.0, poly_limit: int = 40) -> dict:
    """Pull both venues, tag each market selectable/skipped, and attach the modeled round-trip cost."""
    markets, errors = [], {}
    for name, fn in (("kalshi", pull_kalshi),
                     ("polymarket", lambda: pull_polymarket(limit=poly_limit))):
        try:
            markets.extend(fn())
        except Refused as exc:
            errors[name] = str(exc)
    for m in markets:
        ok, reason = is_selectable(m, spec, min_volume=min_volume)
        m["selectable"] = ok
        m["skip_reason"] = None if ok else reason
        if ok:
            m["round_trip_cost"] = round(round_trip_cost(m["venue"], m["p_market"], m["spread"], spec), 4)
    return {"pulled_utc": _iso_now(), "n_markets": len(markets),
            "n_selectable": sum(1 for m in markets if m["selectable"]),
            "errors": errors, "markets": markets}
