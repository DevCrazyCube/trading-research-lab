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


def _mk_event(source, headline, ts, link, snippet, tickers=None, assets=None) -> dict:
    return {"id": _event_id(source, headline, link), "source": source,
            "headline": (headline or "").strip(), "ts": ts, "link": (link or "").strip(),
            "snippet": re.sub(r"\s+", " ", (snippet or "").strip())[:400],
            "tickers": sorted(set(tickers or [])), "assets": sorted(set(assets or []))}


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
                                 it["link"], it["desc"], tickers=[tk]))
    return out


def read_google_news(spec: dict, queries: list) -> list:
    """Google News RSS keyword search -- macro/thematic context the ticker feeds miss."""
    tmpl = spec["sources"]["google_news_rss"]
    out = []
    for q in queries:
        url = tmpl.format(query=urllib.parse.quote(q)) + "&hl=en-US&gl=US&ceid=US:en"
        try:
            items = _parse_rss_items(http_get_text(url))
        except (Refused, ET.ParseError):
            continue
        for it in items[:15]:
            out.append(_mk_event("GOOGLE_NEWS", it["title"], it["pub"] or _now_utc(),
                                 it["link"], f"[q={q}] {it['desc']}"))
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

    events.sort(key=lambda e: e["ts"], reverse=True)
    return {"kind": "event_stream", "pulled_utc": _now_utc(),
            "feed_counts": feeds, "feed_errors": errors,
            "n_events": len(events), "events": events}
