#!/usr/bin/env python3
"""The world-reader -- the Newsdesk's EYES.

Pulls the free, keyless feeds (SEC EDGAR 8-K latest filings, Yahoo Finance per-ticker headline RSS,
Google News RSS, CoinGecko trending) into a single normalized, de-duplicated EVENT STREAM. Each event
carries a timestamp, a source, a headline, the tickers/assets it mentions, a text snippet, a link, and
a stable content id. This is the only place the agent's discretionary read gets its inputs, and it is
strictly read-only public data.

It fabricates nothing: a feed that returns no items yields no events (absence is not a signal), and a
feed that errors is recorded as an error rather than silently dropped.
"""

from __future__ import annotations

import datetime as dt
import email.utils as eut
import hashlib
import re
import urllib.parse
import xml.etree.ElementTree as ET

from . import Refused
from .net import http_get_text, http_get_json

_ATOM = "{http://www.w3.org/2005/Atom}"
_TICKER_RE = re.compile(r"\b[A-Z]{1,5}\b")


def _now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _event_id(source: str, headline: str, link: str) -> str:
    norm = re.sub(r"\s+", " ", (headline or "").strip().lower())
    return hashlib.sha256(f"{source}|{norm}|{link}".encode()).hexdigest()[:16]


def _ts_utc(ts: str):
    """Normalize a feed timestamp to an aware UTC datetime, or None if unparseable.

    The feeds disagree on format: SEC EDGAR emits ISO-8601 ("2026-09-02T15:33:00-04:00") while the
    RSS feeds emit RFC-822 ("Wed, 02 Sep 2026 15:33:00 +0000"). Sorting the RAW strings therefore
    orders the stream by WEEKDAY NAME, not by time -- which silently buried the whole SEC feed below
    every RSS item. Parse to real datetimes and sort on those. Unparseable timestamps sort last
    rather than being dropped: absence of a readable date is not a reason to hide an event.
    """
    ts = (ts or "").strip()
    if not ts:
        return None
    try:
        d = dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        try:
            d = eut.parsedate_to_datetime(ts)
        except (TypeError, ValueError):
            return None
    if d is None:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    return d.astimezone(dt.timezone.utc)


# Company-name aliases for the frozen equity watchlist. Reading surface only: used to decide
# whether a headline actually MENTIONS a universe name, never to price or resolve anything.
_TICKER_ALIASES = {
    "SPY": ("S&P 500", "SPDR S&P"), "QQQ": ("Nasdaq 100", "Nasdaq-100", "Invesco QQQ"),
    "IWM": ("Russell 2000",), "AAPL": ("Apple",), "MSFT": ("Microsoft",),
    "NVDA": ("Nvidia",), "AMZN": ("Amazon",), "GOOGL": ("Google", "Alphabet"),
    "META": ("Meta Platforms", "Facebook", "Instagram"), "TSLA": ("Tesla",),
    "AMD": ("Advanced Micro",), "NFLX": ("Netflix",), "JPM": ("JPMorgan", "JP Morgan"),
    "XOM": ("Exxon",), "AVGO": ("Broadcom",), "COST": ("Costco",),
    "BA": ("Boeing",), "DIS": ("Disney",),
}


def _mentions_ticker(text: str, tk: str) -> bool:
    """True only if `text` literally names the ticker (word-boundary symbol) or a company alias.

    FAULT FIX 2026-09-03: Yahoo's per-ticker RSS returns general market news, so tagging every item
    from ticker tk's feed AS tk produced false attributions (a Goldgroup Mining story tagged NVDA).
    Subscription provenance is kept separately in `feed_ticker`; `tickers` now means "mentioned".
    """
    if not text:
        return False
    if re.search(r"(?<![A-Za-z0-9.])" + re.escape(tk) + r"(?![A-Za-z0-9])", text):
        return True
    low = text.lower()
    return any(a.lower() in low for a in _TICKER_ALIASES.get(tk, ()))


def _mk_event(source, headline, ts, link, snippet, tickers=None, assets=None,
              feed_ticker=None, verify_mentions=False) -> dict:
    parsed = _ts_utc(ts)
    head = (headline or "").strip()
    snip = re.sub(r"\s+", " ", (snippet or "").strip())[:400]
    tks = sorted(set(tickers or []))
    if verify_mentions:
        blob = head + " " + snip
        tks = sorted(t for t in tks if _mentions_ticker(blob, t))
    ev = {"id": _event_id(source, headline, link), "source": source,
          "headline": head, "ts": ts,
          "ts_utc": parsed.isoformat() if parsed else None, "link": (link or "").strip(),
          "snippet": snip,
          "tickers": tks, "assets": sorted(set(assets or []))}
    if feed_ticker:
        ev["feed_ticker"] = feed_ticker
    return ev


# ---------------------------------------------------------------------------
# Individual feeds -- each returns a list of events and never raises past its own boundary
# ---------------------------------------------------------------------------

def read_sec_8k(spec: dict, limit: int = 40) -> list:
    """Latest 8-K material-event filings from the SEC EDGAR current-filings atom feed."""
    url = spec["sources"]["sec_edgar_latest"] + f"&count={limit}"
    out = []
    try:
        root = ET.fromstring(http_get_text(url))
    except Refused:
        raise
    except ET.ParseError as exc:
        raise Refused(f"SEC atom feed did not parse: {exc}")
    for entry in root.findall(f"{_ATOM}entry"):
        title = (entry.findtext(f"{_ATOM}title") or "").strip()
        updated = (entry.findtext(f"{_ATOM}updated") or "").strip()
        summary = (entry.findtext(f"{_ATOM}summary") or "").strip()
        link_el = entry.find(f"{_ATOM}link")
        link = link_el.get("href") if link_el is not None else ""
        out.append(_mk_event("SEC_8K", title, updated or _now_utc(), link, summary))
    return out


def _parse_rss_items(xml_text: str) -> list:
    root = ET.fromstring(xml_text)
    items = []
    for item in root.iter("item"):
        items.append({
            "title": (item.findtext("title") or "").strip(),
            "link": (item.findtext("link") or "").strip(),
            "pub": (item.findtext("pubDate") or "").strip(),
            "desc": (item.findtext("description") or "").strip(),
        })
    return items


def read_yahoo_headlines(spec: dict, tickers: list = None) -> list:
    """Per-ticker Yahoo Finance headline RSS across the frozen equity watchlist (the scanned universe)."""
    tickers = tickers or spec["equity_watchlist"]
    tmpl = spec["sources"]["yahoo_headline_rss"]
    out = []
    for tk in tickers:
        url = tmpl.format(ticker=urllib.parse.quote(tk))
        try:
            items = _parse_rss_items(http_get_text(url))
        except (Refused, ET.ParseError):
            continue  # a single ticker's feed failing must not blind the whole desk
        for it in items:
            out.append(_mk_event("YAHOO_RSS", it["title"], it["pub"] or _now_utc(),
                                 it["link"], it["desc"], tickers=[tk],
                                 feed_ticker=tk, verify_mentions=True))
    return out


class _PartialList(list):
    """A feed result that succeeded only partially; carries the failures so they cannot go silent."""
    partial_errors: list = []


def read_google_news(spec: dict, queries: list) -> list:
    """Google News RSS keyword search -- macro/thematic context the ticker feeds miss.

    A per-query failure used to be swallowed with `continue`, so every query could fail and the feed
    would report zero items with NO error -- a blind eye indistinguishable from "no news today".
    Every query that fails is now raised past the boundary once ALL queries have failed, and partial
    failures are recorded on the returned list so read_world can surface them.
    """
    tmpl = spec["sources"]["google_news_rss"]
    out, failed = [], []
    for q in queries:
        url = tmpl.format(query=urllib.parse.quote(q)) + "&hl=en-US&gl=US&ceid=US:en"
        try:
            items = _parse_rss_items(http_get_text(url))
        except (Refused, ET.ParseError) as exc:
            failed.append(f"{q}: {type(exc).__name__}")
            continue
        if not items:
            # Google throttles by serving a well-formed 200 RSS envelope with ZERO <item>s. For a
            # broad standing query ("earnings", "stock market") a genuinely empty result is not a
            # real state of the world, so a blank is a THROTTLE, not "no news". Measured live
            # 2026-09-03: the same query returned 103 items, then 0, within one minute.
            failed.append(f"{q}: BLANK (valid RSS, 0 items -- throttled)")
            continue
        for it in items[:15]:
            out.append(_mk_event("GOOGLE_NEWS", it["title"], it["pub"] or _now_utc(),
                                 it["link"], f"[q={q}] {it['desc']}"))
    if failed and len(failed) == len(queries):
        raise Refused("GOOGLE_NEWS: every query failed or came back blank (" + "; ".join(failed) + ")")
    if failed:
        out = _PartialList(out)
        out.partial_errors = failed
    return out


def read_coingecko_trending(spec: dict) -> list:
    """CoinGecko trending assets -- the crypto side of the day's attention."""
    url = spec["sources"]["coingecko_trending"]
    payload = http_get_json(url)
    out = []
    for entry in payload.get("coins", []):
        it = entry.get("item", {})
        name, sym = it.get("name", ""), (it.get("symbol", "") or "").upper()
        cid = it.get("id", "")
        rank = it.get("market_cap_rank")
        out.append(_mk_event("COINGECKO_TRENDING", f"Trending crypto: {name} ({sym})", _now_utc(),
                             f"https://www.coingecko.com/en/coins/{cid}",
                             f"market_cap_rank={rank}, coingecko_id={cid}",
                             assets=[sym] if sym else []))
    return out


# ---------------------------------------------------------------------------
# The assembled, de-duplicated stream
# ---------------------------------------------------------------------------

def read_world(spec: dict, *, google_queries: list = None) -> dict:
    """Pull every free feed into one de-duplicated event stream. Returns a stream record.

    De-dupe is by content id (source + normalized headline + link); the first occurrence wins. Each
    feed's success/failure is recorded so a blind eye is visible, never silent.
    """
    google_queries = google_queries if google_queries is not None else [
        "stock market", "Federal Reserve", "earnings", "merger acquisition", "cryptocurrency"]
    feeds, errors, events, seen = {}, {}, [], set()

    def _collect(name, fn):
        try:
            got = fn()
            feeds[name] = len(got)
            partial = getattr(got, "partial_errors", None)
            if partial:
                errors[name] = "PARTIAL: " + "; ".join(partial)
            for e in got:
                if e["id"] not in seen:
                    seen.add(e["id"])
                    events.append(e)
        except Refused as exc:
            errors[name] = str(exc)
            feeds[name] = 0

    _collect("SEC_8K", lambda: read_sec_8k(spec))
    _collect("YAHOO_RSS", lambda: read_yahoo_headlines(spec))
    _collect("GOOGLE_NEWS", lambda: read_google_news(spec, google_queries))
    _collect("COINGECKO_TRENDING", lambda: read_coingecko_trending(spec))

    _floor = dt.datetime.min.replace(tzinfo=dt.timezone.utc)
    events.sort(key=lambda e: _ts_utc(e.get("ts_utc") or e.get("ts")) or _floor, reverse=True)
    # feed_counts is the RAW per-feed count BEFORE cross-feed de-dup; n_raw is their sum. Reporting
    # shown/feed_counts as if it were coverage understates it (T56, 2026-09-06: 440 raw -> 387 unique).
    return {"kind": "event_stream", "pulled_utc": _now_utc(),
            "feed_counts_raw_prededupe": feeds, "feed_counts": feeds, "feed_errors": errors,
            "n_raw": sum(feeds.values()), "n_events": len(events), "events": events}
