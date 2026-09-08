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
               "&order=volume&ascending=false&tag_slug={tag}&offset={offset}")

# T48 (2026-09-03) -- SILENT TRUNCATION FIX.  Both venue endpoints are PAGED and both were being read
# one page deep, so the proposer saw an arbitrary slice of an undisclosed API ordering and could not
# tell.  Measured at the fix: Kalshi returned exactly its 200-event page-1 with a non-empty `cursor`,
# of which only 39 events were rank-1 political -> 268 political markets visible out of >=11,687 that
# exist (<=2.3% of the book).  Polymarket hit its per-tag event cap on 6 of 8 declared tags.  Page
# depth is now bounded and, crucially, ALWAYS REPORTED: `feed_stats` carries pages/events/exhausted
# per feed and `pull_open_markets` raises a DATA_PATH warning whenever a feed is still truncated or a
# declared tag returns nothing.  A truncation you can see is a bounded sample; one you cannot is a bug.
KALSHI_MAX_PAGES = 60          # 200 events/page; bounded so a pull can never become an unbounded crawl
POLY_MAX_PAGES_PER_TAG = 6     # per declared tag, at --poly-limit events/page

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


def pull_kalshi(max_pages: int = KALSHI_MAX_PAGES) -> tuple[list, dict]:
    """Page the Kalshi event feed by cursor up to `max_pages`, returning (markets, feed_stats).

    Returns the stats alongside the rows so silent truncation is impossible: the caller always learns
    how deep the read went and whether the feed was exhausted.
    """
    now = _iso_now()
    out = []
    events, cursor, pages = [], None, 0
    while pages < max_pages:
        url = KALSHI_EVENTS + (f"&cursor={cursor}" if cursor else "")
        data = http_get_json(url)
        page = data.get("events", [])
        if not page:
            break
        events.extend(page)
        pages += 1
        cursor = data.get("cursor")
        if not cursor:
            break
    stats = {"pages": pages, "events_scanned": len(events),
             "exhausted": not cursor,
             "political_events": sum(1 for e in events
                                     if e.get("category") in KALSHI_POLITICAL_CATEGORIES)}
    for e in events:
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
    stats["markets"] = len(out)
    return out, stats


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


def pull_polymarket(limit: int = 100, max_pages_per_tag: int = POLY_MAX_PAGES_PER_TAG) -> tuple[list, dict]:
    """Page each declared political tag by offset up to `max_pages_per_tag`; return (markets, stats).

    `stats["tags"][tag]` records events/pages/exhausted per DECLARED tag, so a tag that silently
    returns nothing (a feed declared but not represented) is visible instead of being averaged away.
    """
    now = _iso_now()
    seen, out = set(), []
    tag_stats = {}
    for tag in POLY_POLITICAL_TAGS:
        events, pages, exhausted = [], 0, True
        while pages < max_pages_per_tag:
            try:
                page = http_get_json(POLY_EVENTS.format(limit=limit, tag=tag,
                                                        offset=pages * limit))
            except Refused as exc:
                tag_stats[tag] = {"events": len(events), "pages": pages, "exhausted": False,
                                  "error": str(exc)[:160]}
                events, exhausted = events, False
                break
            pages += 1
            events.extend(page)
            if len(page) < limit:
                exhausted = True
                break
            exhausted = False
        tag_stats.setdefault(tag, {"events": len(events), "pages": pages, "exhausted": exhausted})
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
    stats = {"tags": tag_stats, "markets": len(out),
             "events_scanned": sum(t["events"] for t in tag_stats.values()),
             "exhausted": all(t["exhausted"] for t in tag_stats.values()),
             "empty_tags": sorted(t for t, v in tag_stats.items() if v["events"] == 0)}
    return out, stats


def data_path_warnings(feed_stats: dict) -> list:
    """T48 criterion (b): every DECLARED feed must actually be represented, and no feed may be
    silently truncated. Returns a list of human-readable warnings (empty == clean)."""
    warn = []
    for name, st in feed_stats.items():
        if st.get("error"):
            warn.append(f"{name}: FEED ERROR -- {st['error']}")
        if not st.get("exhausted", True):
            warn.append(f"{name}: TRUNCATED -- page cap hit, the book is deeper than this read "
                        f"({st.get('events_scanned')} events, {st.get('markets')} markets). "
                        "The unseen remainder is selected by the venue's own ordering, not by us.")
        if not st.get("markets"):
            warn.append(f"{name}: NOT REPRESENTED -- contributed 0 markets to this pull")
        for tag in st.get("empty_tags", []):
            warn.append(f"{name}: declared tag {tag!r} returned 0 events (declared but not represented)")
    return warn


def pull_open_markets(spec: dict, *, min_volume: float = 0.0, poly_limit: int = 100,
                      kalshi_max_pages: int = KALSHI_MAX_PAGES,
                      poly_max_pages: int = POLY_MAX_PAGES_PER_TAG) -> dict:
    """Pull both venues, tag each market selectable/skipped, and attach the modeled round-trip cost."""
    markets, errors, feed_stats = [], {}, {}
    for name, fn in (("kalshi", lambda: pull_kalshi(max_pages=kalshi_max_pages)),
                     ("polymarket", lambda: pull_polymarket(limit=poly_limit,
                                                            max_pages_per_tag=poly_max_pages))):
        try:
            rows, stats = fn()
            markets.extend(rows)
            feed_stats[name] = stats
        except Refused as exc:
            errors[name] = str(exc)
            feed_stats[name] = {"markets": 0, "exhausted": False, "error": str(exc)[:160]}
    for m in markets:
        ok, reason = is_selectable(m, spec, min_volume=min_volume)
        m["selectable"] = ok
        m["skip_reason"] = None if ok else reason
        if ok:
            m["round_trip_cost"] = round(round_trip_cost(m["venue"], m["p_market"], m["spread"], spec), 4)
    return {"pulled_utc": _iso_now(), "n_markets": len(markets),
            "n_selectable": sum(1 for m in markets if m["selectable"]),
            "errors": errors, "feed_stats": feed_stats,
            "data_path_warnings": data_path_warnings(feed_stats),
            "markets": markets}
