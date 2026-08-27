#!/usr/bin/env python3
"""Host-allowlisted, polite, read-only HTTP -- the ONLY network the memebot touches.

A fixed allowlist of FREE, KEYLESS public data hosts, compared as exact parsed hostnames (never
substrings). There is no POST, no auth header, no order path, no wallet host: every call is a GET for
public market data. No trading or RPC-write host is reachable from here by construction.

A polite global throttle keeps the reactive polling loop from ever looking like an aggressive crawl.
GeckoTerminal's free tier is ~30 calls/min; the throttle here stays well under that. Per the project's
standing rule, any rate-limited multi-page CRAWL must run as a detached background subprocess -- this
module is for the light, bounded, inline polls the reactive bot makes.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

from . import Refused

try:
    import fcntl  # POSIX advisory file lock -- present on Linux, where this runs
except ImportError:  # pragma: no cover -- non-POSIX; falls back to the per-process throttle
    fcntl = None

# The only hosts the memebot may reach -- all FREE and KEYLESS. Exact parsed hostnames.
FREE_HOST_ALLOWLIST = frozenset({
    "api.geckoterminal.com",   # primary: new_pools (new launches) + pool detail (price refresh)
    "api.dexscreener.com",     # secondary: token profiles / pair cross-check
})

# Named so a careless edit that points this at execution/wallet/RPC-write refuses loudly.
# NOTE on pumpportal.fun: its host stays FORBIDDEN for HTTP by construction, so every trade/Lightning
# REST path (pumpportal.fun/api/trade*, /api/trade-local, ...) is unreachable from http_get(). The ONE
# read-only exception is the keyless DATA websocket wss://pumpportal.fun/api/data, gated by its own
# assert_data_ws() below (wss scheme + exact /api/data path only). No trading capability is added.
FORBIDDEN_HOSTNAMES = frozenset({
    "api.mainnet-beta.solana.com", "api.devnet.solana.com",  # RPC (read or write) is not this bot's job
    "pumpportal.fun", "pump.fun", "api.pump.fun",            # trade-capable endpoints (HTTP stays blocked)
    "quote-api.jup.ag", "api.jup.ag",                        # swap/execution
})

# The single read-only websocket the bot may open: PumpPortal's free, keyless new-token DATA stream.
DATA_WS_HOST = "pumpportal.fun"
DATA_WS_PATH = "/api/data"

_UA = "meme-research-memebot (officialjoy04@gmail.com) read-only public-data reader"
_LAST_CALL = [0.0]
_MIN_INTERVAL = 2.5  # seconds; ~24 calls/min HOST-WIDE (shared throttle below). Chosen as the balance
# point: comfortably under the ~30/min free tier (so the COMBINED demand of every consumer leaves
# headroom instead of the ~50/min overshoot that used to 429 the scan into entering nothing), yet fast
# enough that a track pass over all open pools still finishes inside the loop's timeout. Measured: 2.1s
# rode the tier's edge; 3.2s starved track. Tune via this ONE constant -- every consumer inherits it
# through the shared throttle. Reliability of scan+track matters more here than raw poll throughput.

# CROSS-PROCESS throttle. Every GeckoTerminal consumer on this host funnels through http_get: the
# memebot scan/track, the evo loop, the dashboard refresher (via feed) and the memestream candle
# ingester (which imports THIS module). A per-process throttle therefore does NOT bound the COMBINED
# rate -- N independent processes each pace themselves to ~28/min and together demand ~N*28/min against
# GeckoTerminal's single ~30/min per-IP budget, so most calls 429 and the bot's scan enters nothing.
# This file lock serialises EVERY call across ALL processes to one shared cadence, so the host-wide rate
# stays under the free tier regardless of how many loops run. Read-only pacing; adds no capability.
try:
    from .frozen import CACHE as _CACHE
    _THROTTLE_LOCK_PATH = str(_CACHE / "gt_throttle.lock")
except Exception:  # pragma: no cover -- if the cache path can't be resolved, use per-process only
    _THROTTLE_LOCK_PATH = None


def _hostname(url: str) -> str:
    parsed = urllib.parse.urlparse(url if "//" in url else f"//{url}")
    host = (parsed.hostname or "").lower()
    if not host:
        raise Refused(f"cannot parse a hostname out of {url!r}; refusing to guess")
    return host


def assert_free_host(url: str) -> str:
    host = _hostname(url)
    if host in FORBIDDEN_HOSTNAMES:
        raise Refused(f"{host!r} is a TRADE/RPC/WALLET-capable host. The memebot reads free public "
                      "market data only and places no orders; any real execution is a SEPARATE, "
                      "owner-gated wallet decision and is not reachable from here.")
    if host not in FREE_HOST_ALLOWLIST:
        raise Refused(f"{host!r} is not on the memebot free-data allowlist {sorted(FREE_HOST_ALLOWLIST)}")
    return url


def assert_data_ws(url: str) -> str:
    """Allow ONLY the read-only PumpPortal data websocket wss://pumpportal.fun/api/data.

    Scheme must be wss, host must be exactly pumpportal.fun, path must be exactly /api/data. Every
    trade/Lightning path (/api/trade, /api/trade-local, ...) and every other scheme REFUSES loudly --
    this is a data subscription only and opens no order/wallet capability.
    """
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "wss":
        raise Refused(f"{url!r}: the data feed is wss-only; refusing scheme {parsed.scheme!r}")
    host = (parsed.hostname or "").lower()
    if host != DATA_WS_HOST:
        raise Refused(f"{host!r} is not the PumpPortal data host; only {DATA_WS_HOST!r} is allowed")
    if parsed.path.rstrip("/") != DATA_WS_PATH:
        raise Refused(f"{parsed.path!r} is NOT the read-only data websocket. The pumpportal.fun "
                      "trade/Lightning paths (/api/trade*) are FORBIDDEN -- this bot places no orders.")
    return url


def _throttle_per_process() -> None:
    wait = _MIN_INTERVAL - (time.monotonic() - _LAST_CALL[0])
    if wait > 0:
        time.sleep(wait)
    _LAST_CALL[0] = time.monotonic()


def _throttle() -> None:
    """Pace this call to keep the HOST-WIDE GeckoTerminal rate under the free tier.

    Uses a file-locked shared timestamp so all processes share one ~28/min budget; the exclusive lock
    is held across the pacing sleep, which serialises every consumer into one global queue. Falls back
    to the per-process throttle if the lock file or fcntl is unavailable, so pacing never fails open.
    """
    if fcntl is None or _THROTTLE_LOCK_PATH is None:
        _throttle_per_process()
        return
    fd = None
    try:
        fd = os.open(_THROTTLE_LOCK_PATH, os.O_RDWR | os.O_CREAT, 0o644)
        fcntl.flock(fd, fcntl.LOCK_EX)
        raw = os.read(fd, 32)
        try:
            last = float((raw or b"0").decode().strip() or "0")
        except ValueError:
            last = 0.0
        now = time.time()
        wait = _MIN_INTERVAL - (now - last)
        if wait > 0:
            time.sleep(wait)
            now = time.time()
        os.lseek(fd, 0, os.SEEK_SET)
        os.ftruncate(fd, 0)
        os.write(fd, f"{now:.6f}".encode())
    except Exception:  # noqa: BLE001 -- any lock/IO failure: degrade to per-process pacing, never open
        _throttle_per_process()
    finally:
        if fd is not None:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except Exception:  # noqa: BLE001
                pass
            os.close(fd)
    _LAST_CALL[0] = time.monotonic()


def http_get(url: str, *, accept: str = "application/json", tries: int = 4, timeout: int = 25,
             backoff_base: float = 1.5) -> bytes:
    """GET raw bytes from an allowlisted free host, with a polite throttle and bounded retries.

    ``tries`` / ``backoff_base`` let a caller FAIL FAST on a saturated tier. GeckoTerminal's free
    budget (~30/min) is shared across every process on this IP, so under contention a call 429s no
    matter how long we wait -- burning the default 4 tries x 1.5s*n backoff (~9s of sleeps) on a
    discovery poll just makes the whole scan hang for ~60s and enter nothing. The discovery/enrichment
    paths therefore pass a small ``tries`` and short ``backoff_base`` so a rate-limited scan gives up
    on GeckoTerminal in a second or two and proceeds with whatever it already has. The retry sleep is
    SKIPPED after the final attempt (no dead wait before the caller sees the Refused)."""
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
                if attempt < tries - 1:
                    time.sleep(backoff_base * (attempt + 1))
                continue
            raise Refused(f"{url}: {last}")
        except Exception as exc:  # noqa: BLE001  -- transient network; retry then refuse
            last = repr(exc)
            if attempt < tries - 1:
                time.sleep(backoff_base * (attempt + 1))
    raise Refused(f"{url} failed after {tries} attempts: {last}")


def http_get_json(url: str, **kw) -> dict:
    return json.loads(http_get(url, **kw).decode("utf-8", "replace"))
