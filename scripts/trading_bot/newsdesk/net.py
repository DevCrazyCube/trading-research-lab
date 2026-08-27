#!/usr/bin/env python3
"""Host-allowlisted, polite, read-only HTTP -- the ONLY network the Newsdesk touches.

This is the Newsdesk's equivalent of `data.py::assert_data_host`. It reaches a fixed allowlist of
FREE, KEYLESS public data hosts and refuses every other host by construction -- most importantly, no
trading host is reachable from here at all. There is no POST, no auth header, no order path: every
call is a GET for public data.

A polite global throttle keeps a single day's pull from ever looking like an aggressive crawl. Per the
project's standing rule, this module is for the ONE-SHOT daily pulls the logger makes inline; any
rate-limited multi-page crawl must run as a detached background subprocess, not here.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request

from . import Refused

# The only hosts the Newsdesk may reach. Compared as exact parsed hostnames, never substrings.
FREE_HOST_ALLOWLIST = frozenset({
    "www.sec.gov", "efts.sec.gov",
    "feeds.finance.yahoo.com", "query1.finance.yahoo.com", "query2.finance.yahoo.com",
    "news.google.com", "api.coingecko.com",
})

# Explicitly named so a careless edit that points this at execution refuses loudly.
FORBIDDEN_HOSTNAMES = frozenset({"api.alpaca.markets", "paper-api.alpaca.markets"})

_UA = "meme-research-newsdesk (officialjoy04@gmail.com) read-only public-data reader"
_LAST_CALL = [0.0]
_MIN_INTERVAL = 0.4  # seconds; polite, single-shot daily pulls only


def _hostname(url: str) -> str:
    parsed = urllib.parse.urlparse(url if "//" in url else f"//{url}")
    host = (parsed.hostname or "").lower()
    if not host:
        raise Refused(f"cannot parse a hostname out of {url!r}; refusing to guess")
    return host


def assert_free_host(url: str) -> str:
    host = _hostname(url)
    if host in FORBIDDEN_HOSTNAMES:
        raise Refused(f"{host!r} is a TRADING host. The Newsdesk reads free public data only and "
                      "places no orders; execution is owner-gated and not reachable from here.")
    if host not in FREE_HOST_ALLOWLIST:
        raise Refused(f"{host!r} is not on the Newsdesk free-data allowlist {sorted(FREE_HOST_ALLOWLIST)}")
    return url


def _throttle() -> None:
    wait = _MIN_INTERVAL - (time.monotonic() - _LAST_CALL[0])
    if wait > 0:
        time.sleep(wait)
    _LAST_CALL[0] = time.monotonic()


def http_get(url: str, *, accept: str = "*/*", tries: int = 4, timeout: int = 30) -> bytes:
    """GET raw bytes from an allowlisted free host, with a polite throttle and bounded retries."""
    assert_free_host(url)
    headers = {"User-Agent": _UA, "Accept": accept}
    last = None
    for attempt in range(tries):
        _throttle()
        try:
            req = urllib.request.Request(url, headers=headers)
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


def http_get_text(url: str, **kw) -> str:
    return http_get(url, **kw).decode("utf-8", "replace")


def http_get_json(url: str, **kw) -> dict:
    kw.setdefault("accept", "application/json")
    return json.loads(http_get(url, **kw).decode("utf-8", "replace"))
