#!/usr/bin/env python3
"""Host-allowlisted, polite, read-only HTTP -- the ONLY network the tracker touches.

Mirror of the Newsdesk's `net.py`. It reaches a fixed allowlist of FREE, KEYLESS public prediction-
market read hosts and refuses every other host by construction -- most importantly, no ORDER, wallet,
or account host is reachable from here at all. There is no POST, no auth header, no order path: every
call is a GET for public data.

A polite global throttle keeps a single pull from ever looking like an aggressive crawl. Per the
project's standing rule, this module is for the ONE-SHOT pulls the tracker makes inline; any
rate-limited multi-page crawl must run as a detached background subprocess, not here.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request

from . import Refused

# The only hosts this tracker may reach. Compared as exact parsed hostnames, never substrings.
# All are FREE, KEYLESS, READ-ONLY public prediction-market data endpoints.
FREE_HOST_ALLOWLIST = frozenset({
    "api.elections.kalshi.com",   # Kalshi public REST: markets, events, settlements (keyless read)
    "gamma-api.polymarket.com",   # Polymarket Gamma: market/event discovery + implied prices
    "clob.polymarket.com",        # Polymarket CLOB: order book / prices-history (keyless read)
})

# Explicitly named so a careless edit that points this at execution/funding refuses loudly. These are
# the ORDER / WALLET / ACCOUNT surfaces that this $0 forward tracker must never touch.
FORBIDDEN_HOSTNAMES = frozenset({
    "trading-api.kalshi.com",     # Kalshi authenticated trading (orders) -- owner-gated, not reachable
    "demo-api.kalshi.com",        # Kalshi paper/demo trading -- still an order path, refused
    "neg-risk-ctf-exchange",      # Polymarket on-chain exchange contract families
    "clob.polymarket.com/order",  # (defensive; order POST is refused by method anyway)
})

_UA = "meme-research-predmarket (officialjoy04@gmail.com) read-only public-data reader"
_LAST_CALL = [0.0]
_MIN_INTERVAL = 0.4  # seconds; polite, single-shot pulls only


def _hostname(url: str) -> str:
    parsed = urllib.parse.urlparse(url if "//" in url else f"//{url}")
    host = (parsed.hostname or "").lower()
    if not host:
        raise Refused(f"cannot parse a hostname out of {url!r}; refusing to guess")
    return host


def assert_free_host(url: str) -> str:
    host = _hostname(url)
    if host in FORBIDDEN_HOSTNAMES:
        raise Refused(f"{host!r} is a TRADING/ORDER host. This tracker reads free public data only and "
                      "places NO bets; execution is owner-gated and not reachable from here.")
    if host not in FREE_HOST_ALLOWLIST:
        raise Refused(f"{host!r} is not on the predmarket free-data allowlist "
                      f"{sorted(FREE_HOST_ALLOWLIST)}")
    return url


def _throttle() -> None:
    wait = _MIN_INTERVAL - (time.monotonic() - _LAST_CALL[0])
    if wait > 0:
        time.sleep(wait)
    _LAST_CALL[0] = time.monotonic()


def http_get(url: str, *, accept: str = "application/json", tries: int = 4, timeout: int = 30) -> bytes:
    """GET raw bytes from an allowlisted free host, with a polite throttle and bounded retries."""
    assert_free_host(url)
    headers = {"User-Agent": _UA, "Accept": accept}
    last = None
    for attempt in range(tries):
        _throttle()
        try:
            req = urllib.request.Request(url, headers=headers)  # GET only; no method override, no body
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")[:200]
            last = f"HTTP {exc.code}: {body}"
            if exc.code in (429, 500, 502, 503, 504):
                time.sleep(1.0 * (attempt + 1))
                continue
            raise Refused(f"{url}: {last}")
        except Exception as exc:  # noqa: BLE001
            last = repr(exc)
            time.sleep(1.0 * (attempt + 1))
    raise Refused(f"{url} failed after {tries} attempts: {last}")


def http_get_json(url: str, **kw):
    return json.loads(http_get(url, **kw).decode("utf-8", "replace"))
