#!/usr/bin/env python3
"""Local, read-only terminal dashboard for the PAPER memebot (scripts/trading_bot/memebot/).

    python scripts/trading_bot/memebot/dashboard/server.py     # then open http://localhost:8791

Stdlib-only HTTP server (mirrors scripts/agent_graph/server.py) that serves a dark, GMGN/Padre-style
single-page terminal and a small JSON API over the bot's OWN frozen ledgers. It REUSES the memebot's
own modules (frozen/ledger/feed/scoring/paper) so every number matches the bot exactly.

  GET  /                    the SPA (dashboard.html + app.css + app.js)
  GET  /api/summary         honest scorecard (expectancy, win-rate, totals, #open)  [read-only]
  GET  /api/positions       every paper position, OPEN + CLOSED, with LIVE P&L (% and R)
  GET  /api/pac             fail-closed AFTERSHOCK PAC performance + operational gates [read-only]
  GET  /api/coin/{pool}     one coin's detail: entry, live stats, screen decision, stop/target, markers
  GET  /api/ohlcv/{pool}    GeckoTerminal candles, server-side proxied (avoids CORS)

READ-ONLY DISPLAY OF PAPER DATA. There is NO order path, NO wallet, NO real money, and NO trading
endpoint here by construction -- exactly like the bot it watches. Live prices come from the FREE,
keyless GeckoTerminal public API via the bot's own net.py (host-allowlisted, politely throttled).
Bound to 127.0.0.1 only.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = pathlib.Path(__file__).resolve().parent
# scripts/trading_bot/memebot/dashboard -> repo root is 4 parents up.
ROOT = HERE.parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Reuse the bot's OWN code so the dashboard's numbers are the bot's numbers, never a re-derivation.
from scripts.trading_bot.memebot import Refused, feed, ledger, net, paper, scoring  # noqa: E402
from scripts.trading_bot.memebot.frozen import ACTIVE_INSTRUMENTS, frozen_spec  # noqa: E402

# Optional: the memestream 1-second local candle cache. When present it is the FAST, un-rate-limited
# source for both the chart and live prices (a background ingester writes it). We fall back to
# GeckoTerminal only when a pool has nothing cached yet. Imported defensively so the dashboard runs
# even if the ingester package is absent.
try:
    from scripts.trading_bot.memestream import candles as mstream  # noqa: E402
    LOCAL_TF = {"1s", "5s", "1m"}
except Exception:  # noqa: BLE001
    mstream = None
    LOCAL_TF = set()

# Optional: the sniper's audited, READ-ONLY Chainstack JSON-RPC helper. Used ONLY for getTokenSupply
# (a pure read call -- no wallet, no sign, no send) so a coin's FDV / market cap can be filled when the
# GeckoTerminal snapshot is 429-starved. Imported defensively; if it or the .env RPC URL is absent, FDV
# simply falls back to an honest "—" and nothing else is affected.
try:
    from scripts.trading_bot.sniper.data._common import (  # noqa: E402
        read_env as _read_env,
        rpc_call as _rpc_call,
    )
    _SOLANA_RPC_URL = _read_env("SOLANA_RPC_URL")
except Exception:  # noqa: BLE001
    _rpc_call = None
    _SOLANA_RPC_URL = None

# Optional: the evolutionary tactic-population engine (scripts/trading_bot/memebot_evo). We only ever
# READ from it -- its own read-only status/report functions over its frozen ledgers. Imported
# defensively so the dashboard runs even if that package is mid-edit or absent. NEVER mutated here.
try:
    from scripts.trading_bot.memebot_evo import engine as evo_engine  # noqa: E402
except Exception:  # noqa: BLE001
    evo_engine = None

PORT = int(os.environ.get("MEMEBOT_UI_PORT", "8791"))
STATIC = {".html": "text/html; charset=utf-8", ".css": "text/css", ".js": "application/javascript"}
GT_BASE = feed.GT_BASE
GT_ASSET_HOST = "assets.geckoterminal.com"   # where GeckoTerminal serves token logo images
LOGO_DIR = ROOT / "research" / "data" / "memebot_cache" / "logos"

PRICE_TTL = 240.0       # a pool's live snapshot is considered fresh for this long
OHLCV_TTL = 300.0       # candle cache (warmed off the request path; longer TTL = far fewer GT calls)
# The background refresher deliberately paces itself SLOWER than net.py's floor so it uses only part
# of GeckoTerminal's ~30-call/min free budget, leaving headroom for the BOT'S OWN scan/track (which
# share the same tier and 429 -- entering nothing -- if this UI refresher hogs the budget). The
# refresher is a UI nicety: slightly-stale prices/charts are an acceptable price for the bot's scan
# getting through. TTLs and the inter-call gap below were raised for exactly that reason.
REFRESHER_MIN_GAP = 15.0  # seconds between background price fetches
LOGO_MIN_GAP = 6.0       # seconds between background logo fetches (one-time; logos never change)

# ---- shared caches (written by the background workers, read by request handlers) ----
_price_cache: dict[str, dict] = {}   # pool -> {"snap": {...}|None, "ts": float, "err": str|None}
_ohlcv_cache: dict[tuple, dict] = {}
_logo_mem: dict[str, dict] = {}      # mint -> {"bytes": b..., "type": str} or {"none": True}
_lock = threading.Lock()

# GeckoTerminal rate gate. net.py's throttle is NOT thread-safe, so N concurrent threads (price
# refresher + logo warmer + on-demand OHLCV) would each pass it independently and multiply the call
# rate ~N x, tripping 429s. This ONE process-wide lock serializes every GeckoTerminal API call to a
# safe steady cadence, well under the ~30/min free tier. Read-only; adds no capability.
_GT_LOCK = threading.Lock()
_gt_last = [0.0]
GT_MIN_GAP = 3.0  # seconds between ANY two GeckoTerminal API calls, across all threads (~20/min cap)


def gt_call(fn, *args, **kwargs):
    """Serialize + pace a single GeckoTerminal API call (via the bot's own net.py) across all threads."""
    with _GT_LOCK:
        wait = GT_MIN_GAP - (time.monotonic() - _gt_last[0])
        if wait > 0:
            time.sleep(wait)
        try:
            return fn(*args, **kwargs)
        finally:
            _gt_last[0] = time.monotonic()


# ---------- spec loading (tolerate a not-yet-started variant) ----------
def load_specs() -> list[dict]:
    specs = []
    for inst in ACTIVE_INSTRUMENTS:
        try:
            specs.append(frozen_spec(inst))
        except Refused:
            continue  # variant whose frozen files don't exist yet -- simply not running
    return specs


def _variant_label(setup: dict) -> str:
    inst = setup.get("instrument_id", "?")
    # Distinct short label per instrument. Both FAST and RUNNER carry dead_exit, so the label must key
    # off instrument_id (not the mere presence of dead_exit) or a RUNNER position mislabels as "FAST".
    if inst == "MEMEBOT1":
        tag = "base"
    elif inst == "MEMEBOT_FAST":
        tag = "FAST"
    elif inst == "MEMEBOT_RUNNER":
        tag = "RUNNER"
    else:
        tag = inst
    if setup.get("discovery_source") == "pumpportal":
        tag += "/flow"
    return tag


def _symbol(name: str | None) -> str:
    if not name:
        return "?"
    return name.split("/")[0].strip() or name


def _age_min(iso: str | None) -> float | None:
    if not iso:
        return None
    try:
        t = dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (dt.datetime.now(dt.timezone.utc) - t).total_seconds() / 60.0


# ---------- local candle cache (fast, un-rate-limited) ----------
def local_price(pool: str) -> float | None:
    """Latest close from the local 1s candle cache, if the ingester is tracking this pool. Instant."""
    if mstream is None:
        return None
    try:
        rows = mstream.get_candles(pool, "1s", lookback_secs=180)
        if rows:
            return rows[-1].get("c")
    except Exception:  # noqa: BLE001
        return None
    return None


def local_flow(pool: str) -> dict | None:
    if mstream is None:
        return None
    try:
        f = mstream.get_flow(pool, window_secs=60)
        return f if f.get("trades") else None
    except Exception:  # noqa: BLE001
        return None


# ---------- Chainstack-derived fill-ins for the coin-detail live stat panel ----------
# The coin page's "live" stats (FDV, market cap, Volume 5m, Buys/Sells, unique wallets) normally come
# from the GeckoTerminal pool snapshot, but that free tier is chronically 429-starved, so the snapshot
# is usually empty and every stat renders as "—". We FILL THE BLANKS (never overwrite a real GT value)
# from data we actually have: the Chainstack-fed 1s candle cache (buys/sells counts + USD volume) and
# ONE cached Chainstack getTokenSupply RPC (for FDV = price x supply). Wallet-level "unique buyers /
# sellers" are NOT derivable -- the candle cache stores no addresses -- so those stay honest "—".
_supply_cache: dict[str, dict] = {}   # mint -> {"supply": float|None, "ts": float}
SUPPLY_TTL_OK = 6 * 3600.0            # a pump.fun mint's supply is ~constant; refresh only rarely
SUPPLY_TTL_FAIL = 90.0               # a failed lookup (429 / timeout) retries soon, not forever
SUPPLY_RPC_TIMEOUT = 5.0            # bounded so a cold coin-view never hangs the UI on a slow RPC
STATS_WINDOW_SECS = 300             # "5 minute" window for buys/sells/volume (matches GT's m5 fields)
STATS_FRESH_SECS = 300             # newest candle must be within this (wall clock) to count as "live":
#                                    a coin with no trade in the last ~5 min is treated as dead -> "—".
#                                    Matched to the 5-min stats window; memecoin trades are bursty and
#                                    the ingester only tracks HELD pools, so a tighter bound blanks
#                                    coins that are still genuinely active between trade bursts.


def token_supply(mint: str) -> float | None:
    """uiAmount of a mint's total token supply via a CACHED Chainstack getTokenSupply RPC (read-only).

    Cached per mint (supply is ~constant), so at most one RPC per coin ever. Any failure returns None
    and is cached briefly, so FDV/market cap fall back to an honest "—" and retry a little later."""
    if not mint or _rpc_call is None or not _SOLANA_RPC_URL:
        return None
    now = time.time()
    with _lock:
        hit = _supply_cache.get(mint)
    if hit:
        ttl = SUPPLY_TTL_OK if hit["supply"] is not None else SUPPLY_TTL_FAIL
        if (now - hit["ts"]) < ttl:
            return hit["supply"]
    supply = None
    try:
        res = _rpc_call(_SOLANA_RPC_URL, "getTokenSupply", [mint], timeout=SUPPLY_RPC_TIMEOUT)
        ui = ((res or {}).get("value") or {}).get("uiAmount")
        supply = float(ui) if ui is not None else None
    except Exception:  # noqa: BLE001 -- 429 / plan / transport: leave FDV honest-"—", retry later
        supply = None
    with _lock:
        _supply_cache[mint] = {"supply": supply, "ts": time.time()}
    return supply


def chain_stats(pool: str, mint: str | None) -> dict:
    """Chainstack-derived fill-ins for a coin's live stat panel, from the local 1s candle cache
    (buys/sells counts + USD volume over the last ~5 min) and one cached getTokenSupply RPC (FDV /
    market cap = latest price x total supply). Returns only what the cache can honestly support; a coin
    with no cached candles yields all-None (so a dead coin's stats stay "—"). Never fabricates."""
    out = {"buys": None, "sells": None, "volume_usd_m5": None,
           "fdv_usd": None, "market_cap_usd": None}
    if mstream is None:
        return out
    try:
        rows = mstream.get_candles(pool, "1s", lookback_secs=STATS_WINDOW_SECS) or []
    except Exception:  # noqa: BLE001
        rows = []
    # Only fill when the coin is ACTUALLY still trading: the newest cached candle must be recent in
    # wall-clock terms. A coin that died 10 min ago still has old candles on disk, but surfacing their
    # 5-min stats as "live" would be misleading -- leave those at honest "—".
    if not rows or (time.time() - int(rows[-1].get("t") or 0)) > STATS_FRESH_SECS:
        return out
    out["buys"] = sum(int(c.get("buys") or 0) for c in rows)
    out["sells"] = sum(int(c.get("sells") or 0) for c in rows)
    out["volume_usd_m5"] = round(sum(float(c.get("v") or 0.0) for c in rows), 2)
    price = rows[-1].get("c")
    supply = token_supply(mint) if mint else None
    if price and supply:
        fdv = float(price) * float(supply)
        out["fdv_usd"] = fdv
        # pump.fun bonding-curve tokens mint their full supply up front, so circulating ≈ total and
        # market cap ≈ FDV. This is an APPROXIMATION, surfaced as such (the UI tags it "chain").
        out["market_cap_usd"] = fdv
    return out


# ---------- live price refresh (background) ----------
def get_snapshot(pool: str, *, block_if_missing: bool = False) -> dict:
    """Return the cached live snapshot for a pool. The background thread keeps it fresh; on a cold
    miss for a coin-detail view we may fetch once inline (bounded by net.py's throttle)."""
    now = time.time()
    with _lock:
        hit = _price_cache.get(pool)
    if hit and (now - hit["ts"]) < PRICE_TTL:
        return hit
    if not block_if_missing:
        # List view must never block on the network: return whatever the background refresher has
        # (possibly stale, possibly a placeholder). The refresher keeps open pools warm.
        return hit or {"snap": None, "ts": 0.0, "err": None}
    # Coin-detail view on a cold pool: fetch once now (bounded by net.py's throttle).
    entry = _fetch_snapshot(pool)
    with _lock:
        _price_cache[pool] = entry
    return entry


def _fetch_snapshot(pool: str) -> dict:
    try:
        snap = gt_call(feed.refresh_pool, {}, pool)
        return {"snap": snap, "ts": time.time(), "err": None}
    except Refused as e:
        return {"snap": None, "ts": time.time(), "err": str(e)[:160]}
    except Exception as e:  # noqa: BLE001
        return {"snap": None, "ts": time.time(), "err": repr(e)[:160]}


def _open_pools() -> list[str]:
    pools, seen = [], set()
    for spec in load_specs():
        try:
            for s in ledger.open_positions(spec):
                p = s.get("pool_address")
                if p and p not in seen:
                    seen.add(p)
                    pools.append(p)
        except Exception:  # noqa: BLE001
            continue
    return pools


def refresher_loop():
    """Continuously cycle over open pools, refreshing each price snapshot. net.py's global throttle
    (~2.1s/call) keeps this well under GeckoTerminal's free-tier limit."""
    while True:
        pools = _open_pools()
        if not pools:
            time.sleep(5.0)
            continue
        did_fetch = False
        for pool in pools:
            with _lock:
                hit = _price_cache.get(pool)
            if hit and (time.time() - hit["ts"]) < (PRICE_TTL * 0.6):
                continue  # still fresh, skip -- don't spend budget
            entry = _fetch_snapshot(pool)
            with _lock:
                _price_cache[pool] = entry
            did_fetch = True
            time.sleep(REFRESHER_MIN_GAP)
            # Also keep the 1m OHLCV cache warm off the request path, so opening a coin's chart is
            # instant instead of hanging on a synchronous GeckoTerminal 429. Only when stale; the
            # blocking=True fetch is gated by the same global throttle, so it costs one bounded call.
            key = (pool, "minute", 1, 300)
            with _lock:
                oh = _ohlcv_cache.get(key)
            if not oh or (time.time() - oh["ts"]) >= OHLCV_TTL:
                try:
                    get_ohlcv(pool, "1m", 300, blocking=True)
                except Exception:  # noqa: BLE001
                    pass
                time.sleep(REFRESHER_MIN_GAP)
        if not did_fetch:
            time.sleep(5.0)  # everything fresh; idle so on-demand calls get the whole budget


# ---------- OHLCV: local 1s cache first, GeckoTerminal fallback ----------
# frontend tf label -> (local memestream tf | None, GT timeframe, GT aggregate)
TF_MAP = {
    "1s":  ("1s", "minute", 1),
    "5s":  ("5s", "minute", 1),
    "1m":  ("1m", "minute", 1),
    "5m":  (None, "minute", 5),
    "15m": (None, "minute", 15),
    "1h":  (None, "hour", 1),
}


def _local_candles(pool: str, local_tf: str) -> list:
    if mstream is None or local_tf is None:
        return []
    try:
        return mstream.get_candles(pool, local_tf) or []
    except Exception:  # noqa: BLE001
        return []


def get_ohlcv(pool: str, tf: str, limit: int = 300, since_ts: int | None = None,
              blocking: bool = True) -> dict:
    # blocking=False is the USER-REQUEST path: it must NEVER touch the network. GeckoTerminal is
    # rate-gated (~2.1s/call, shared with the price refresher) and 429s under load, so a synchronous
    # fetch here can hang 25s+ on backoff. Instead we serve the warm GT cache if present, else the
    # local memestream candles instantly, else an explicit "warming" marker -- and let the background
    # refresher populate the GT cache off the request path. blocking=True is the warmer's own path.
    tf = tf if tf in TF_MAP else "1m"
    local_tf, gt_tf, gt_agg = TF_MAP[tf]
    sub_minute = tf in ("1s", "5s")

    # SUB-MINUTE (1s / 5s): only the local memestream cache has this granularity. The free
    # GeckoTerminal tier serves 1-minute minimum, so there is NO honest fallback -- rather than
    # silently returning 1m candles under a "1s" label, we return the (possibly sparse) local series
    # if present, or an explicit "no sub-minute data" marker so the UI can say so instead of resetting.
    if sub_minute:
        rows = _local_candles(pool, local_tf)
        if rows:
            candles = [{"time": int(c["t"]), "open": c["o"], "high": c["h"], "low": c["l"],
                        "close": c["c"], "volume": c.get("v", 0)} for c in rows][-limit:]
            return {"pool_address": pool, "timeframe": tf, "source": "local-1s-cache",
                    "candles": candles, "local_count": len(rows)}
        return {"pool_address": pool, "timeframe": tf, "source": None, "candles": [],
                "no_subminute": True,
                "note": ("no sub-minute data for this coin (free tier only serves 1m; the local 1s "
                         "cache covers currently-tracked coins)")}

    # 1-MINUTE+ : local cache first when it reaches back far enough to contain the bot's entry (so the
    # BUY marker stays on-screen); otherwise GeckoTerminal's longer history keeps the markers visible.
    local_rows = _local_candles(pool, local_tf) if local_tf is not None else []
    if local_rows and (since_ts is None or local_rows[0]["t"] <= since_ts + 90):
        candles = [{"time": int(c["t"]), "open": c["o"], "high": c["h"], "low": c["l"],
                    "close": c["c"], "volume": c.get("v", 0)} for c in local_rows][-limit:]
        return {"pool_address": pool, "timeframe": tf, "source": "local-1s-cache",
                "candles": candles, "local_count": len(local_rows)}

    # 2) GeckoTerminal fallback (cached ~45s, gated, serves stale on 429).
    key = (pool, gt_tf, gt_agg, limit)
    now = time.time()
    with _lock:
        hit = _ohlcv_cache.get(key)
    if hit and (now - hit["ts"]) < OHLCV_TTL:
        d = dict(hit["data"]); d["timeframe"] = tf; return d

    # USER-REQUEST path (non-blocking): never hit the network. Serve any stale GT cache, else whatever
    # sparse local candles exist, else a "warming" marker -- so the page paints instantly and the
    # refresher fills the GT cache in the background instead of the request hanging on 429 backoff.
    if not blocking:
        if hit:
            stale = dict(hit["data"]); stale["stale"] = True; stale["timeframe"] = tf; return stale
        if local_rows:
            candles = [{"time": int(c["t"]), "open": c["o"], "high": c["h"], "low": c["l"],
                        "close": c["c"], "volume": c.get("v", 0)} for c in local_rows][-limit:]
            return {"pool_address": pool, "timeframe": tf, "source": "local-1s-cache",
                    "candles": candles, "local_count": len(local_rows), "sparse": True}
        return {"pool_address": pool, "timeframe": tf, "source": None, "candles": [],
                "warming": True, "note": "chart warming (fetching history off the request path)"}

    url = (f"{GT_BASE}/networks/solana/pools/{pool}/ohlcv/{gt_tf}"
           f"?aggregate={gt_agg}&limit={limit}")
    try:
        payload = gt_call(net.http_get_json, url, tries=2)  # host-allowlisted, read-only, gated
        rows = (((payload.get("data") or {}).get("attributes") or {}).get("ohlcv_list") or [])
        rows = sorted(rows, key=lambda r: r[0])  # ascending time for the chart
        candles = [{"time": int(r[0]), "open": r[1], "high": r[2], "low": r[3],
                    "close": r[4], "volume": r[5]} for r in rows]
        data = {"pool_address": pool, "timeframe": tf, "source": "geckoterminal", "candles": candles}
        with _lock:
            _ohlcv_cache[key] = {"ts": now, "data": data}
        return data
    except Exception as e:  # noqa: BLE001
        if hit:
            stale = dict(hit["data"]); stale["stale"] = True; stale["timeframe"] = tf
            return stale
        return {"pool_address": pool, "candles": [], "error": str(e)[:180], "timeframe": tf}


# ---------- token logos (proxied, disk-cached; logos never change) ----------
_mint_index: dict[str, str] = {}          # pool_address -> base_token mint


def _rebuild_mint_index() -> None:
    idx = {}
    for spec in load_specs():
        try:
            for e in ledger.read_entries(spec):
                if e.get("kind") == "entry" and e.get("pool_address") and e.get("base_token"):
                    idx[e["pool_address"]] = e["base_token"]
        except Exception:  # noqa: BLE001
            continue
    _mint_index.update(idx)


def mint_for_pool(pool: str) -> str | None:
    if pool not in _mint_index:
        _rebuild_mint_index()
    return _mint_index.get(pool)


def _safe_mint(mint: str) -> bool:
    return bool(mint) and mint.isalnum() and 20 <= len(mint) <= 60


def _fetch_image_bytes(url: str) -> tuple[bytes, str] | None:
    """Fetch a token logo image. Only GeckoTerminal's asset host is contacted (read-only, public)."""
    host = urllib.parse.urlparse(url).hostname or ""
    if host != GT_ASSET_HOST:
        return None
    req = urllib.request.Request(url, headers={
        "User-Agent": "meme-research-memebot (officialjoy04@gmail.com) read-only logo reader"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            ctype = r.headers.get("Content-Type", "image/png")
            if not ctype.startswith("image/"):
                return None
            data = r.read(600_000)  # cap ~600KB
            return data, ctype
    except Exception:  # noqa: BLE001
        return None


def get_logo(mint: str) -> dict | None:
    """Return {'bytes','type'} for a token logo, or None. Cached in memory AND on disk permanently."""
    if not _safe_mint(mint):
        return None
    with _lock:
        m = _logo_mem.get(mint)
    if m is not None:
        return None if m.get("none") else m
    LOGO_DIR.mkdir(parents=True, exist_ok=True)
    binp = LOGO_DIR / f"{mint}.bin"
    typp = LOGO_DIR / f"{mint}.type"
    nonep = LOGO_DIR / f"{mint}.none"
    if binp.exists() and typp.exists():
        m = {"bytes": binp.read_bytes(), "type": typp.read_text().strip() or "image/png"}
        with _lock:
            _logo_mem[mint] = m
        return m
    if nonep.exists():
        with _lock:
            _logo_mem[mint] = {"none": True}
        return None
    # Cold: resolve image_url via GeckoTerminal token /info (allowlisted + throttled), then fetch bytes.
    img = None
    try:
        payload = gt_call(net.http_get_json, f"{GT_BASE}/networks/solana/tokens/{mint}/info", tries=2)
        img = (((payload.get("data") or {}).get("attributes") or {}).get("image_url"))
    except Exception:  # noqa: BLE001
        img = None
    got = _fetch_image_bytes(img) if img and img.startswith("http") else None
    if got:
        data, ctype = got
        try:
            binp.write_bytes(data)
            typp.write_text(ctype)
        except Exception:  # noqa: BLE001
            pass
        m = {"bytes": data, "type": ctype}
        with _lock:
            _logo_mem[mint] = m
        return m
    try:
        nonep.write_text("1")
    except Exception:  # noqa: BLE001
        pass
    with _lock:
        _logo_mem[mint] = {"none": True}
    return None


def _placeholder_svg(seed: str) -> bytes:
    """A neutral, SHARP-cornered monogram square used when a token has no logo."""
    letter = (seed or "?")[0].upper()
    # deterministic muted hue from the seed
    h = sum(ord(c) for c in (seed or "?")) % 360
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 40 40">'
            f'<rect width="40" height="40" fill="hsl({h},18%,20%)"/>'
            f'<text x="20" y="26" font-family="monospace" font-size="18" font-weight="700" '
            f'text-anchor="middle" fill="hsl({h},30%,70%)">{letter}</text></svg>').encode()


def logo_loop():
    """Slowly warm logos for tokens currently in the portfolio. One-time cost; then everything is on
    disk and this thread idles. Paced so it never competes hard with price/OHLCV for the GT budget."""
    while True:
        pools = _open_pools()
        # also cover recently-closed so their rows show a logo
        for spec in load_specs():
            try:
                for r in ledger.resolved_r_stream(spec)[-30:]:
                    if r.get("pool_address"):
                        pools.append(r["pool_address"])
            except Exception:  # noqa: BLE001
                continue
        did = False
        seen = set()
        for pool in pools:
            if pool in seen:
                continue
            seen.add(pool)
            mint = mint_for_pool(pool)
            if not mint:
                continue
            with _lock:
                cached = mint in _logo_mem
            if cached or (LOGO_DIR / f"{mint}.bin").exists() or (LOGO_DIR / f"{mint}.none").exists():
                continue
            get_logo(mint)   # one cold fetch
            did = True
            time.sleep(LOGO_MIN_GAP)
        time.sleep(15.0 if did else 30.0)


# ---------- position / summary assembly ----------
def _live_row(setup: dict) -> dict:
    """One OPEN paper position marked to its cached live price. Read-only; nothing is written."""
    pool = setup["pool_address"]
    hit = get_snapshot(pool)
    snap = hit.get("snap") or {}
    # Prefer the local 1s candle close (instant, live, un-rate-limited); fall back to the GT snapshot.
    price = local_price(pool)
    price_source = "local-candle" if price is not None else "geckoterminal"
    if price is None:
        price = snap.get("price_usd")
    entry = setup["entry_price_usd"]
    stop_frac = setup["stop_frac"]
    toll = setup["toll_per_side"]

    pnl_pct = pnl_r = None
    live_hint = "OPEN"
    if price and price > 0 and entry > 0:
        pnl_pct = (price / entry - 1.0) * 100.0
        pnl_r = round(paper._realized_r(entry, price, toll, stop_frac), 3)
        if price <= setup["stop_price_usd"]:
            live_hint = "stop-pending"
        elif price >= setup["target_price_usd"]:
            live_hint = "target-pending"
    age = _age_min(setup.get("decided_utc"))
    horizon = setup.get("horizon_minutes")
    if live_hint == "OPEN" and age is not None and horizon and age >= horizon:
        live_hint = "horizon-due"

    # Is the coin still TRADING? Chainstack streams only active trades, so a dead/idle coin gets no new
    # candles. get_candles(lookback_secs) is candle-RELATIVE (window off the newest candle), which
    # mislabels a coin that traded 20 min ago as "live" — so check the newest candle's age against the
    # WALL CLOCK: live only if its last candle is within LIVE_MAX_AGE_S of NOW.
    LIVE_MAX_AGE_S = 120
    n_recent = 0
    is_live = False
    if mstream is not None:
        try:
            cs = mstream.get_candles(pool, "1s", lookback_secs=LIVE_MAX_AGE_S) or []
            if cs:
                last_t = cs[-1].get("t", 0)
                if (time.time() - last_t) <= LIVE_MAX_AGE_S:
                    is_live = True
                    # count only the candles within the wall-clock window (real recent activity)
                    n_recent = sum(1 for c in cs if (time.time() - c.get("t", 0)) <= LIVE_MAX_AGE_S)
        except Exception:  # noqa: BLE001
            n_recent = 0; is_live = False

    return {
        "pool_address": pool,
        "name": setup.get("name"),
        "symbol": _symbol(setup.get("name")),
        "variant": _variant_label(setup),
        "control": bool(setup.get("control")),
        "screen_verdict": setup.get("screen_verdict"),
        "status": "OPEN",
        "live": is_live,
        "recent_candles": n_recent,
        "live_hint": live_hint,
        "entry_price_usd": entry,
        "current_price_usd": price,
        "price_source": price_source,
        "stop_price_usd": setup["stop_price_usd"],
        "target_price_usd": setup["target_price_usd"],
        "size_sol": setup.get("size_sol"),
        "pnl_pct": pnl_pct,
        "pnl_r": pnl_r,
        # MCAP / LIQ for the table: prefer the live GT snapshot; when it is blank (the free tier is
        # usually 429-starved) fall back to the frozen ENTRY feed_snapshot -- the honest "how it looked
        # when we bought" -- so the portfolio table's MCAP/LIQ columns fill instead of showing "—".
        "market_cap_usd": (snap.get("market_cap_usd") or snap.get("fdv_usd")
                           or (setup.get("feed_snapshot") or {}).get("fdv_usd")),
        "liquidity_usd": (snap.get("reserve_usd")
                          if snap.get("reserve_usd") is not None
                          else (setup.get("feed_snapshot") or {}).get("reserve_usd")),
        "buys": snap.get("buys"),
        "sells": snap.get("sells"),
        "buyers": snap.get("buyers"),
        "age_minutes": age,
        "decided_utc": setup.get("decided_utc"),
        "price_error": hit.get("err"),
    }


def _closed_row(res: dict, entry_by_hash: dict) -> dict:
    setup = entry_by_hash.get(res.get("setup_sha256"), {})
    entry = res.get("entry_price_usd")
    exit_p = res.get("exit_price_usd")
    pnl_pct = ((exit_p / entry - 1.0) * 100.0) if (entry and exit_p and entry > 0) else None
    reason = res.get("resolution_reason", "?")
    status = {"STOP": "stopped", "TARGET": "target", "HORIZON_MARK": "horizon",
              "DEAD_EXIT": "dead-exit", "UNEXITABLE_TIMEOUT": "dead"}.get(reason, reason.lower())
    return {
        "pool_address": res.get("pool_address"),
        "name": res.get("name"),
        "symbol": _symbol(res.get("name")),
        "variant": _variant_label(setup) if setup else ("null" if res.get("control") else "base"),
        "control": bool(res.get("control")),
        "screen_verdict": res.get("screen_verdict"),
        "status": status,
        "live_hint": None,
        "entry_price_usd": entry,
        "current_price_usd": exit_p,
        "exit_price_usd": exit_p,
        "stop_price_usd": setup.get("stop_price_usd"),
        "target_price_usd": setup.get("target_price_usd"),
        "size_sol": setup.get("size_sol"),
        "pnl_pct": pnl_pct,
        "pnl_r": res.get("realized_r"),
        "resolution_reason": reason,
        "held_minutes": res.get("held_minutes"),
        "market_cap_usd": (setup.get("feed_snapshot") or {}).get("fdv_usd"),
        "liquidity_usd": (setup.get("feed_snapshot") or {}).get("reserve_usd"),
        "age_minutes": res.get("held_minutes"),
        "decided_utc": setup.get("decided_utc"),
        "resolved_utc": res.get("resolved_utc"),
    }


# ---------- short-TTL view cache (single-flight) ----------
# The heavy JSON views (positions/summary/evo/exit/aftershock) each re-read every ledger JSONL from
# disk and re-run scoring.score PER REQUEST. With a 6s poll from every open tab this was rebuilding a
# multi-MB payload continuously and requests piled up faster than they completed (the "lag"). The
# underlying ledgers only change when the bot scans (~90s) and live prices come from the background
# refresher, so a few seconds of staleness is invisible. This memoizes each view for a short TTL and
# runs at most ONE build at a time per view (single-flight): concurrent/queued polls get the last
# value instantly instead of each launching another full rebuild.
_VIEW_CACHE: dict = {}                     # name -> (expires_at, value)
_VIEW_LOCKS: dict = {}                     # name -> threading.Lock
_VIEW_REGISTRY_LOCK = threading.Lock()

# Most closed trades a positions payload ever carries. The table is a recent-activity view; the full
# history lives in the ledgers. Capping this is what turns a ~5 MB / 7k-row response into a small one.
CLOSED_ROWS_CAP = 250


def cached_view(name: str, ttl: float, builder):
    now = time.time()
    hit = _VIEW_CACHE.get(name)
    if hit and hit[0] > now:
        return hit[1]
    with _VIEW_REGISTRY_LOCK:
        lock = _VIEW_LOCKS.get(name)
        if lock is None:
            lock = _VIEW_LOCKS[name] = threading.Lock()
    if lock.acquire(blocking=False):
        try:
            value = builder()
            _VIEW_CACHE[name] = (time.time() + ttl, value)
            return value
        finally:
            lock.release()
    # A build is already in flight elsewhere. Serve the last value if we have one (stale-while-
    # rebuilding); only if there is nothing cached yet do we wait for that build to finish.
    if hit:
        return hit[1]
    with lock:
        again = _VIEW_CACHE.get(name)
        return again[1] if again else builder()


def positions_view() -> dict:
    open_rows, closed_rows = [], []
    closed_total = 0
    for spec in load_specs():
        entries = ledger.read_entries(spec)
        entry_by_hash = {e.get("setup_sha256"): e for e in entries if e.get("kind") == "entry"}
        for setup in ledger.open_positions(spec):
            open_rows.append(_live_row(setup))
        for res in ledger.resolved_r_stream(spec):
            closed_total += 1
            closed_rows.append(_closed_row(res, entry_by_hash))
    closed_rows.sort(key=lambda r: r.get("resolved_utc") or "", reverse=True)
    open_rows.sort(key=lambda r: r.get("decided_utc") or "", reverse=True)
    closed_rows = closed_rows[:CLOSED_ROWS_CAP]      # recent-activity view; full history is in the ledgers
    return {"open": open_rows, "closed": closed_rows,
            "closed_total": closed_total, "closed_shown": len(closed_rows),
            "closed_truncated": closed_total > len(closed_rows),
            "generated_at": time.time(), "server_utc": dt.datetime.now(dt.timezone.utc).isoformat()}


def summary_view() -> dict:
    """Honest scorecard, aggregated across active instruments. Uses the bot's own scoring.score."""
    open_rows = []
    total_resolved = []
    total_open = 0
    invested_sol = 0.0
    per_instrument = []
    for spec in load_specs():
        resolved = ledger.resolved_r_stream(spec)
        report = scoring.score(spec, resolved)
        op = ledger.open_positions(spec)
        total_open += len(op)
        invested_sol += sum((s.get("size_sol") or 0.0) for s in op)
        total_resolved += resolved
        inp = report.get("inputs_that_are_not_results") or {}
        per_instrument.append({
            "instrument_id": spec["instrument_id"],
            "resolved_pass": report.get("resolved_pass_trades"),
            "resolved_control": report.get("resolved_control_trades"),
            "minimum": report.get("minimum_before_verdict"),
            "verdict": report.get("verdict"),
            "status_line": report.get("status_line"),
            "kill_verdict": report.get("kill_switch", {}).get("verdict"),
            "screen_pass": inp.get("screen_pass"),
            "control_null": inp.get("control_null_rejected_coins"),
            "edge_vs_null_R": inp.get("expectancy_edge_of_screen_over_null_R"),
            "reason_counts": inp.get("resolution_reason_counts"),
        })

    pass_r = [r["realized_r"] for r in total_resolved
              if not r.get("control") and r.get("realized_r") is not None]
    ctrl_r = [r["realized_r"] for r in total_resolved
              if r.get("control") and r.get("realized_r") is not None]
    scr = scoring._expectancy(pass_r) if pass_r else None
    return {
        "open_positions": total_open,
        "invested_sol": round(invested_sol, 4),
        "resolved_pass": len(pass_r),
        "resolved_control": len(ctrl_r),
        "pass_expectancy": scr,
        "cum_R_pass": round(sum(pass_r), 3) if pass_r else 0.0,
        "cum_R_control": round(sum(ctrl_r), 3) if ctrl_r else 0.0,
        "win_rate": (scr["win_rate"] if scr else None),
        "instruments": per_instrument,
        "note": ("READ-ONLY PAPER display. No orders, no wallet, no real SOL. Numbers below the "
                 "pre-registered minimum are inputs, not a verdict."),
        "generated_at": time.time(),
    }


def _live_stats(pool: str, setup: dict, live: dict, hit: dict) -> dict:
    """Assemble the coin-detail 'live' stat block. Prefer the GeckoTerminal snapshot; where a field is
    missing (the free tier is usually 429-starved), FILL THE BLANK from Chainstack-derived data -- never
    overwrite a real GT value. Wallet-level unique buyers/sellers are left None (the candle cache stores
    no addresses; honest "—" beats a fabricated number). A dead coin with no candles stays all "—"."""
    out = {
        "price_usd": live.get("price_usd"),
        "market_cap_usd": live.get("market_cap_usd") or live.get("fdv_usd"),
        "fdv_usd": live.get("fdv_usd"),
        "liquidity_usd": live.get("reserve_usd"),
        "buys": live.get("buys"),
        "sells": live.get("sells"),
        "buyers": live.get("buyers"),      # unique wallets: not in the candle cache -> stays "—"
        "sellers": live.get("sellers"),    # unique wallets: not in the candle cache -> stays "—"
        "volume_usd_m5": live.get("volume_usd_m5"),
        "error": hit.get("err"),
    }
    # Fill from the candle cache whenever the coin is genuinely still trading (chain_stats gates on
    # candle freshness), regardless of is_open -- a coin can be resolved in one variant yet still live in
    # another, and its stats are honest live data either way. A dead coin yields all-None -> stays "—".
    chain_filled: list[str] = []
    cs = chain_stats(pool, setup.get("base_token"))
    for k in ("buys", "sells", "volume_usd_m5", "fdv_usd", "market_cap_usd"):
        if out.get(k) is None and cs.get(k) is not None:
            out[k] = cs[k]
            chain_filled.append(k)
    # Price too: the GT snapshot price is usually blank, but the latest local 1s candle close is live.
    if out.get("price_usd") is None:
        lp = local_price(pool)
        if lp is not None:
            out["price_usd"] = lp
            chain_filled.append("price_usd")

    # ENTRY-SNAPSHOT fallback (last resort, fill-blanks-only). Explicit source ordering for each stat:
    #   live/chain  ->  GeckoTerminal  ->  entry feed_snapshot  ->  "—"
    # For a DEAD coin the live/chain and GT layers are all None, so this fills fdv/mcap/liquidity plus
    # the entry-time buyers/buys/sellers COUNTS (those are real counts as-of entry, not fabricated) --
    # an honest "how it looked when we bought", far better than blank. The entry snapshot has NO 'sells'
    # count and no 5-min volume, so those two stay "—" for a dead coin (honest -- no entry equivalent).
    entry_filled: list[str] = []
    fs = setup.get("feed_snapshot") or {}
    entry_src = {
        "fdv_usd": fs.get("fdv_usd"),
        "market_cap_usd": fs.get("fdv_usd"),   # pump.fun bonding-curve: mcap ≈ fdv (approximation)
        "liquidity_usd": fs.get("reserve_usd"),
        "buyers": fs.get("buyers"),
        "buys": fs.get("buys"),
        "sellers": fs.get("sellers"),
    }
    for k, v in entry_src.items():
        if out.get(k) is None and v is not None:
            out[k] = v
            entry_filled.append(k)

    # Subtle source tags: which fields the UI should mark Chainstack-derived (live) vs @entry (frozen at
    # buy time) rather than GeckoTerminal. app.js renders a muted "· chain" / "· @entry" on the header.
    out["chain_filled"] = chain_filled
    out["entry_filled"] = entry_filled
    return out


def coin_view(pool: str) -> dict:
    setup = None
    resolution = None
    spec_used = None
    for spec in load_specs():
        for e in ledger.read_entries(spec):
            if e.get("kind") == "entry" and e.get("pool_address") == pool:
                setup = e
                spec_used = spec
        for r in ledger.read_resolutions(spec):
            if r.get("pool_address") == pool and r.get("status") == "RESOLVED":
                resolution = r
    if setup is None:
        return {"_error": f"no paper entry for pool {pool}"}

    is_open = resolution is None
    row = _live_row(setup) if is_open else _closed_row(resolution, {setup.get("setup_sha256"): setup})
    # Non-blocking: serve the cached snapshot so the token page renders instantly. The background
    # refresher + local candle cache keep it fresh; we never block the page on a live GT fetch.
    hit = get_snapshot(pool, block_if_missing=False) if is_open else {"snap": None, "err": None}
    live = hit.get("snap") or {}
    flow = local_flow(pool) if is_open else None

    # Which timeframes actually HAVE data for THIS coin, so the UI can grey out the rest instead of
    # silently snapping back to 1m. Sub-minute (1s/5s) exists ONLY in the local cache; 1m+ is always
    # available via GeckoTerminal (with the local cache preferred when it covers the entry).
    n1s = len(_local_candles(pool, "1s"))
    n5s = len(_local_candles(pool, "5s"))
    tf_counts = {"1s": n1s, "5s": n5s, "1m": len(_local_candles(pool, "1m"))}
    tf_available = {"1s": n1s > 0, "5s": n5s > 0, "1m": True, "1h": True}

    # Markers for the chart: bot BUY at entry, bot SELL at exit (if resolved).
    markers = [{"type": "buy", "utc": setup.get("decided_utc"),
                "price": setup.get("entry_price_usd"),
                "label": "BOT BUY"}]
    if resolution:
        markers.append({"type": "sell", "utc": resolution.get("resolved_utc"),
                        "price": resolution.get("exit_price_usd"),
                        "label": f"BOT SELL ({resolution.get('resolution_reason')})"})

    return {
        "pool_address": pool,
        "row": row,
        "is_open": is_open,
        "variant": _variant_label(setup),
        "control": bool(setup.get("control")),
        "screen_verdict": setup.get("screen_verdict"),
        "screen_reasons": setup.get("screen_reasons"),
        "entry": {
            "entry_price_usd": setup.get("entry_price_usd"),
            "stop_price_usd": setup.get("stop_price_usd"),
            "target_price_usd": setup.get("target_price_usd"),
            "stop_frac": setup.get("stop_frac"),
            "target_frac": setup.get("target_frac"),
            "size_sol": setup.get("size_sol"),
            "horizon_minutes": setup.get("horizon_minutes"),
            "decided_utc": setup.get("decided_utc"),
            "dex": setup.get("dex"),
            "base_token": setup.get("base_token"),
            "feed_snapshot": setup.get("feed_snapshot"),
        },
        "live": _live_stats(pool, setup, live, hit),
        "flow": flow,   # local 1s-cache buy/sell pressure over the last 60s (None if not tracked)
        "tf_available": tf_available,   # which timeframe buttons have real data for this coin
        "tf_counts": tf_counts,         # local candle counts per sub-minute frame (for the label)
        "resolution": resolution,
        "markers": markers,
        "instrument_id": spec_used["instrument_id"] if spec_used else None,
    }


# ---------- evolutionary tactic population (read-only, in-process) ----------
# The honest framing lives HERE too (not only in the UI) so the API is self-describing: a genome's
# population expectancy is BEHAVIOUR, not a result, until it clears the pre-registered gates.
EVO_TTL = 12.0                       # cache the evo snapshot ~12s (polling is cheap, like the others)
_evo_cache: dict = {"data": None, "ts": 0.0}
EVO_FRAMING = (
    "Population expectancy is BEHAVIOUR, not evidence -- NO VERDICT until a genome reaches the N_min "
    "resolved-trade minimum AND beats the K-corrected noise bar sqrt(2 ln K). This is a "
    "forward-selection monitor, not a backtest leaderboard: no genome here is a winner or an edge. "
    "PAPER ONLY -- no orders, no wallet, no SOL, no on-chain.")


def _fmt_pct_gene(v) -> str:
    try:
        return f"{float(v) * 100:.0f}%"
    except Exception:  # noqa: BLE001
        return "—" if v is None else str(v)


def _tactic(genome: dict) -> dict:
    """Decode one genome's entry/exit tactic into a human-readable summary (genes -> tactic). The
    stop/target read as % of price for the fixed-exit path, or as a multiple of the coin's own measured
    volatility when the genome uses the adaptive (vol-scaled) exits. Read-only; nothing is derived as a
    result."""
    g = genome or {}
    horizon = g.get("horizon_minutes")
    use_vol = bool(int(g.get("use_vol_exits", 0) or 0))
    use_dead = bool(int(g.get("use_dead_exit", 0) or 0))
    use_flow = bool(int(g.get("use_flow_exit", 0) or 0))
    if use_vol:
        stop = f"{g.get('stop_vol_mult')}× vol"
        target = f"{g.get('target_vol_mult')}× vol"
    else:
        stop = _fmt_pct_gene(g.get("stop_frac"))
        target = _fmt_pct_gene(g.get("target_frac"))
    tags = []
    if use_vol:
        tags.append("vol-scaled")
    if use_dead:
        tags.append("dead-exit")
    if use_flow:
        tags.append("flow-exit")
    summary = f"{horizon}m · stop {stop} / tgt {target}"
    if tags:
        summary += " · " + "+".join(tags)
    return {
        "horizon_minutes": horizon, "stop": stop, "target": target,
        "use_vol_exits": use_vol, "use_dead_exit": use_dead, "use_flow_exit": use_flow,
        "exits": "+".join(tags) if tags else "fixed only", "summary": summary,
    }


_EVO_LEDGER_DIR = ROOT / "scripts" / "trading_bot" / "memebot_evo" / "ledgers"


def _evo_activity(gid: str) -> dict:
    """Read-only tally of a genome's OWN forward ledger: how many coins it actually entered (PASS
    signal + CONTROL null) and how many are still open. The leaderboard's `resolved_pass` alone
    massively understates activity -- the frozen screen rejects ~84% of coins into the CONTROL arm, so
    a genome with 40+ real entries can show only a handful of resolved PASS trades. Surfacing entered/
    open makes clear the population is busy, not dead, even while PASS-maturity accrues slowly."""
    f = _EVO_LEDGER_DIR / f"{gid}.jsonl"
    entered_pass = entered_ctrl = resolved = 0
    try:
        with open(f) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                is_res = ("resolution_reason" in r) or ("resolved_utc" in r) or r.get("kind") == "resolution"
                if is_res:
                    resolved += 1
                elif ("entry_price_usd" in r) or r.get("kind") == "entry":
                    if r.get("control"):
                        entered_ctrl += 1
                    else:
                        entered_pass += 1
    except OSError:
        pass
    entered = entered_pass + entered_ctrl
    return {"entered": entered, "entered_pass": entered_pass, "entered_control": entered_ctrl,
            "open": max(0, entered - resolved), "resolved_any": resolved}


def _build_evo_view() -> dict:
    if evo_engine is None:
        return {"_error": "memebot_evo engine not importable (package absent or mid-edit)",
                "framing": EVO_FRAMING, "leaderboard": []}
    try:
        report = evo_engine.status()          # canonical read-only snapshot: header + verdict + gate
        pop = evo_engine.load_pop()
        state = evo_engine.load_state()
        k = report.get("K_genomes_ever_evaluated") or evo_engine.K(state)
        genomes = pop.get("genomes", {})
        active = set(pop.get("active", []))
        seed_names = {gid: name for name, gid in (pop.get("named_seeds") or {}).items()}
        n_min = report.get("N_min_eval", getattr(evo_engine, "N_MIN_EVAL", None))

        rows = []
        # EVERY genome the population has ever held: alive (in `active`) + killed (bred out but its
        # forward ledger persists). _genome_report only READS the genome's ledger -- no mutation.
        for gid, genome in genomes.items():
            rep = evo_engine._genome_report(pop, gid, k)
            tac = _tactic(genome)
            act = _evo_activity(gid)
            rows.append({
                "genome_id": gid, "short": gid[:7], "seed_name": seed_names.get(gid),
                "tactic": tac, "tactic_summary": tac["summary"],
                "entered": act["entered"], "entered_pass": act["entered_pass"],
                "entered_control": act["entered_control"], "open": act["open"],
                "resolved_pass": rep["resolved_pass"],
                "mean_R": rep["mean_R"],            # BEHAVIOUR expectancy -- NOT a result
                "expectancy_R": rep["expectancy_R"],
                "win_rate": rep["win_rate"], "t": rep["t"],
                "beats_bar": bool(rep["beats_noise_bar"]), "mature": bool(rep["mature"]),
                "alive": gid in active, "killed": gid not in active,
            })
        # Rank by behaviour expectancy (forward mean R); a genome with no resolved trades sinks last.
        rows.sort(key=lambda r: (r["mean_R"] if r["mean_R"] is not None else -9.99), reverse=True)
        for i, r in enumerate(rows, 1):
            r["rank"] = i

        return {
            "generation": report.get("generation"),
            "population_size": report.get("population_size"),
            "K_genomes_ever_evaluated": k,
            "K_corrected_noise_bar_SE": report.get("K_corrected_noise_bar_SE"),
            "resolved_pass_trades_total": report.get("resolved_pass_trades_total"),
            "mature_genomes": report.get("mature_genomes"),
            "N_min_eval": n_min,
            "anything_beats_bar": bool(report.get("anything_beats_bar")),
            "verdict": report.get("verdict"),
            "reported_utc": report.get("reported_utc"),
            "candidates_awaiting_fresh_slice": report.get("candidates_awaiting_fresh_slice"),
            "confirmed_real": report.get("confirmed_real"),
            "kill_switch": report.get("kill_switch"),
            "framing": EVO_FRAMING, "leaderboard": rows,
            "generated_at": time.time(),
        }
    except Exception as e:  # noqa: BLE001
        return {"_error": repr(e)[:200], "framing": EVO_FRAMING, "leaderboard": []}


def evo_view() -> dict:
    """Cached (~12s) read-only snapshot of the evolutionary tactic population. Never mutates anything."""
    now = time.time()
    with _lock:
        if _evo_cache["data"] is not None and (now - _evo_cache["ts"]) < EVO_TTL:
            return _evo_cache["data"]
    data = _build_evo_view()
    with _lock:
        _evo_cache["data"] = data
        _evo_cache["ts"] = now
    return data


def _dump_rate(report: dict) -> dict:
    """From a scoring.score() report, compute the UNEXITABLE-DUMP rate: what fraction of resolved PASS
    trades ended UNEXITABLE_TIMEOUT (the coin's exit path closed while held). This is MEMEBOT_EXIT's
    honest decider — the whole point is to drive it down vs the other variants."""
    inp = report.get("inputs_that_are_not_results") or {}
    counts = inp.get("resolution_reason_counts") or {}
    pass_total = sum(v for k, v in counts.items() if str(k).startswith("pass:"))
    dumps = counts.get("pass:UNEXITABLE_TIMEOUT", 0)
    rate = (dumps / pass_total) if pass_total else None
    return {"pass_resolved": pass_total, "unexitable_dumps": dumps,
            "dump_rate": rate, "reason_counts": counts}


def exit_view() -> dict:
    """The EXITABILITY-FIRST fast-scalp system page. MEMEBOT_EXIT's scorecard + its unexitable-dump rate,
    compared against every other variant (does buying-only-what-you-can-sell actually lower the dumps?)."""
    try:
        spec = frozen_spec("MEMEBOT_EXIT")
    except Exception as e:  # noqa: BLE001
        return {"_error": f"MEMEBOT_EXIT not loadable: {e}"}
    resolved = ledger.resolved_r_stream(spec)
    report = scoring.score(spec, resolved)
    inp = report.get("inputs_that_are_not_results") or {}
    pass_r = [r.get("realized_r") for r in resolved
              if not r.get("control") and r.get("realized_r") is not None]
    # SCORE = pot growth (cumulative + per-trade expectancy). Dump-rate is a CONSTRAINT, not the score:
    # a 0%-dump bot that loses a little every trade still drains the pot (Codex's correction).
    cum_r = round(sum(pass_r), 3) if pass_r else 0.0
    expectancy = (round(sum(pass_r) / len(pass_r), 4) if pass_r else None)
    op = ledger.open_positions(spec)
    entries = [e for e in ledger.read_entries(spec) if e.get("kind") == "entry"]
    entry_by_hash = {e.get("setup_sha256"): e for e in entries}
    closed = [_closed_row(r, entry_by_hash) for r in resolved if not r.get("control")]
    closed.sort(key=lambda r: r.get("resolved_utc") or "", reverse=True)

    # dump-rate comparison across ALL active variants (the honest decider, side by side)
    comparison = []
    for other in load_specs():
        rep = scoring.score(other, ledger.resolved_r_stream(other))
        dr = _dump_rate(rep)
        comparison.append({"instrument_id": other["instrument_id"],
                           "dump_rate": dr["dump_rate"], "pass_resolved": dr["pass_resolved"],
                           "unexitable_dumps": dr["unexitable_dumps"]})

    return {
        "instrument_id": "MEMEBOT_EXIT",
        "framing": ("Exitability-first fast-scalp: buy only what you can sell (>=3 proven sellers + deep "
                    "reserve, screened with THIS variant's own rules), get out fast (12-min horizon). "
                    "SCORE = pot growth (cumulative R / expectancy). The unexitable-dump rate is a hard "
                    "CONSTRAINT (kill-gate), not the score. PAPER only — no orders, no wallet, no SOL."),
        "screen": spec["screen"],
        "horizon_minutes": spec["horizon_minutes"],
        "cum_R": cum_r,
        "expectancy_R": expectancy,
        "verdict": report.get("verdict"),
        "status_line": report.get("status_line"),
        "kill_verdict": report.get("kill_switch", {}).get("verdict"),
        "resolved_pass": report.get("resolved_pass_trades"),
        "minimum": report.get("minimum_before_verdict"),
        "screen_pass": inp.get("screen_pass"),
        "edge_vs_null_R": inp.get("expectancy_edge_of_screen_over_null_R"),
        "dump": _dump_rate(report),
        "dump_rate_comparison": comparison,
        "open_positions": [_live_row(s) for s in op],
        "closed_positions": closed[:100],
        "generated_at": time.time(),
        "server_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    }


def aftershock_view() -> dict:
    """The AFTERSHOCK rug-absorption survivor arm: pot-growth score + dump-rate kill-gate + edge vs the
    honest null (a shock that fired but was NOT absorbed). Separate frozen registry from the memebot."""
    try:
        from scripts.trading_bot.aftershock import frozen as _asfrozen, scoring as _asscore
        from scripts.trading_bot.memebot import ledger as _asledger
    except Exception as e:  # noqa: BLE001
        return {"_error": f"aftershock package not importable: {e}"}
    try:
        spec = _asfrozen.frozen_spec("AFTERSHOCK")
    except Exception as e:  # noqa: BLE001
        return {"_error": f"AFTERSHOCK not loadable: {e}"}
    resolved = _asledger.resolved_r_stream(spec)
    rep = _asscore.score(spec, resolved)
    body = rep.get("inputs_that_are_not_results", rep)
    op = _asledger.open_positions(spec)
    entries = [e for e in _asledger.read_entries(spec) if e.get("kind") == "entry"]
    entry_by_hash = {e.get("setup_sha256"): e for e in entries}
    closed = []
    for r in resolved:
        if r.get("control"):
            continue
        row = _closed_row(r, entry_by_hash)
        row["stressed_net_return"] = r.get("stressed_net_return")   # aftershock-specific; carry it through
        row["resolution_reason"] = r.get("resolution_reason")
        closed.append(row)
    closed.sort(key=lambda r: r.get("resolved_utc") or "", reverse=True)

    # equity curve E_k = exp(cumulative g) over resolved PASS trades (for the panel sparkline)
    import math as _math
    f = float(spec.get("position_fraction", 0.02))
    gs, equity, curve = [], 1.0, []
    for r in resolved:
        if r.get("control") or r.get("stressed_net_return") is None:
            continue
        equity *= _math.exp(_math.log(max(1e-12, 1.0 + f * max(-1.0, float(r["stressed_net_return"])))))
        curve.append(round(equity, 5))

    return {
        "instrument_id": "AFTERSHOCK",
        "framing": ("Rug-absorption survivor. Never buys before the rug; enters only mints whose first "
                    "material cluster sell is demonstrably ABSORBED by external demand, curve-exact "
                    "ECR-gated, sized 0.1 SOL. SCORE = pot growth; unexitable-dump rate = hard kill-gate. "
                    "Control null = a shock that fired but was NOT absorbed. PAPER, free tape, no key."),
        "verdict": rep.get("verdict"),
        "readable": rep.get("readable"),
        "resolved_pass": rep.get("resolved_pass_trades"),
        "minimum": rep.get("minimum_before_verdict"),
        "log_growth_G": body.get("log_growth_G"),
        "pot_multiple": body.get("pot_multiple"),
        "per_trade_growth": body.get("per_trade_growth"),
        "max_drawdown": body.get("max_drawdown"),
        "cluster_concentration": body.get("cluster_concentration"),
        "dump": body.get("dump"),
        "control_null": body.get("control_null"),
        "kill_switch": rep.get("kill_switch"),
        "equity_curve": curve[-200:],
        "detector_thresholds": spec.get("detector"),
        "open_positions": [_live_row(s) for s in op],
        "closed_positions": closed[:100],
        "generated_at": time.time(),
        "server_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    }


def pac_view() -> dict:
    """Sole active memecoin research candidate. The adapter itself refuses unanchored, gross-only,
    duplicate, partially committed, or state/ledger-inconsistent rows; this HTTP layer performs no
    performance arithmetic and never mutates the runner."""
    try:
        from scripts.trading_bot.aftershock import pac_dashboard as _pac_dashboard
        return _pac_dashboard.focus_snapshot()
    except Exception as e:  # noqa: BLE001 -- a broken evidence adapter must stay visibly unavailable
        return {
            "instrument_id": "AFTERSHOCK_PAC_V2",
            "boundary": "PAPER SCENARIO ONLY · NO WALLET · NO ORDERS",
            "evidence_status": "REFUSED_ADAPTER_ERROR",
            "integrity_errors": [f"{type(e).__name__}: {str(e)[:180]}"],
            "_error": "PAC performance adapter refused the current evidence",
        }


def aftershock_v2_view() -> dict:
    """AFTERSHOCK V2 (PAYABLE ABSORPTION) — the 3 forward arms A/B/C, each scored on its OWN frozen
    ledger. A compact per-arm summary (verdict + pot-growth + dump-gate + edge-vs-null + open + spark)."""
    try:
        from scripts.trading_bot.aftershock import frozen as _asfrozen, scoring as _asscore, scan_v2 as _asv2
        from scripts.trading_bot.memebot import ledger as _asledger
    except Exception as e:  # noqa: BLE001
        return {"_error": f"aftershock v2 not importable: {e}"}
    try:
        base = _asfrozen.frozen_spec("AFTERSHOCK_V2")
    except Exception as e:  # noqa: BLE001
        return {"_error": f"AFTERSHOCK_V2 not loadable: {e}"}
    import math as _math
    frac = float(base.get("position_fraction", 0.02))
    arms_out = []
    for arm in base["arms"]:
        aspec = _asv2.arm_spec(base, arm)
        try:
            resolved = _asledger.resolved_r_stream(aspec)
            rep = _asscore.score(aspec, resolved)
            body = rep.get("inputs_that_are_not_results", rep)
            d = body.get("dump") or {}
            cn = body.get("control_null") or {}
            kg = rep.get("kill_switch") or {}
            eq, curve = 1.0, []
            for r in resolved:
                if r.get("control") or r.get("stressed_net_return") is None:
                    continue
                eq *= _math.exp(_math.log(max(1e-12, 1.0 + frac * max(-1.0, float(r["stressed_net_return"])))))
                curve.append(round(eq, 5))
            arms_out.append({
                "arm": arm["arm"], "label": arm["label"],
                "verdict": rep.get("verdict"),
                "resolved_pass": rep.get("resolved_pass_trades"),
                "minimum": rep.get("minimum_before_verdict"),
                "per_trade_growth": body.get("per_trade_growth"),
                "pot_multiple": body.get("pot_multiple"),
                "log_growth_G": body.get("log_growth_G"),
                "dump_rate": d.get("dump_rate"),
                "unexitable_dumps": d.get("unexitable_dumps"),
                "pass_resolved": d.get("pass_resolved"),
                "edge_vs_null": cn.get("edge_per_trade"),
                "n_control": cn.get("n_control"),
                "open": len(_asledger.open_positions(aspec)),
                "kill": ((kg.get("expectancy_gate") or {}).get("verdict") or rep.get("verdict") or "").split(" ")[0],
                "equity_curve": curve[-120:],
            })
        except Exception as e:  # noqa: BLE001
            arms_out.append({"arm": arm["arm"], "label": arm.get("label"), "_error": str(e)[:140]})
    return {
        "framing": ("PAYABLE ABSORPTION — enter only shocks whose dumped inventory was NET-replaced by real "
                    "external SOL, veto flipping tape, trail on the executable full-position quote. 3 arms "
                    "isolate one change each. PAPER, free tape, curve-exact ECR."),
        "arms": arms_out,
        "generated_at": time.time(),
    }


def aftershock_v3_view() -> dict:
    """AFTERSHOCK V3 (QUOTE-HARVEST) — 3 forward arms A/B/C (trail / ratchet / rollover), each scored on
    its OWN frozen ledger. Same compact per-arm summary as V2."""
    try:
        from scripts.trading_bot.aftershock import frozen as _asfrozen, scoring as _asscore, scan_v3 as _asv3
        from scripts.trading_bot.memebot import ledger as _asledger
    except Exception as e:  # noqa: BLE001
        return {"_error": f"aftershock v3 not importable: {e}"}
    try:
        base = _asfrozen.frozen_spec("AFTERSHOCK_V3")
    except Exception as e:  # noqa: BLE001
        return {"_error": f"AFTERSHOCK_V3 not loadable: {e}"}
    import math as _math
    frac = float(base.get("position_fraction", 0.02))
    arms_out = []
    for arm in base["arms"]:
        aspec = _asv3.arm_spec(base, arm)
        try:
            resolved = _asledger.resolved_r_stream(aspec)
            rep = _asscore.score(aspec, resolved)
            body = rep.get("inputs_that_are_not_results", rep)
            d = body.get("dump") or {}
            cn = body.get("control_null") or {}
            kg = rep.get("kill_switch") or {}
            eq, curve = 1.0, []
            for r in resolved:
                if r.get("control") or r.get("stressed_net_return") is None:
                    continue
                eq *= _math.exp(_math.log(max(1e-12, 1.0 + frac * max(-1.0, float(r["stressed_net_return"])))))
                curve.append(round(eq, 5))
            arms_out.append({
                "arm": arm["arm"], "label": arm["label"],
                "verdict": rep.get("verdict"),
                "resolved_pass": rep.get("resolved_pass_trades"),
                "minimum": rep.get("minimum_before_verdict"),
                "per_trade_growth": body.get("per_trade_growth"),
                "pot_multiple": body.get("pot_multiple"),
                "log_growth_G": body.get("log_growth_G"),
                "dump_rate": d.get("dump_rate"),
                "unexitable_dumps": d.get("unexitable_dumps"),
                "pass_resolved": d.get("pass_resolved"),
                "edge_vs_null": cn.get("edge_per_trade"),
                "n_control": cn.get("n_control"),
                "open": len(_asledger.open_positions(aspec)),
                "kill": ((kg.get("expectancy_gate") or {}).get("verdict") or rep.get("verdict") or "").split(" ")[0],
                "equity_curve": curve[-120:],
            })
        except Exception as e:  # noqa: BLE001
            arms_out.append({"arm": arm["arm"], "label": arm.get("label"), "_error": str(e)[:140]})
    return {
        "framing": ("QUOTE-HARVEST — V2's net-replacement entry (veto dropped) + break-even gate, trailing the "
                    "executable full-position quote. A=12% trail · B=+ratchet (tighten to 5% once +10%) · "
                    "C=+rollover harvest. PAPER, free tape, curve-exact ECR."),
        "arms": arms_out,
        "generated_at": time.time(),
    }


def _aftershock_family_view(instrument_id, arm_spec_mod, framing):
    """Shared per-arm summary for an AFTERSHOCK arm-family (V3/V4)."""
    try:
        from scripts.trading_bot.aftershock import frozen as _asfrozen, scoring as _asscore
        from scripts.trading_bot.memebot import ledger as _asledger
    except Exception as e:  # noqa: BLE001
        return {"_error": f"aftershock not importable: {e}"}
    try:
        base = _asfrozen.frozen_spec(instrument_id)
    except Exception as e:  # noqa: BLE001
        return {"_error": f"{instrument_id} not loadable: {e}"}
    import math as _math
    frac = float(base.get("position_fraction", 0.02))
    arms_out = []
    for arm in base["arms"]:
        aspec = arm_spec_mod.arm_spec(base, arm)
        try:
            resolved = _asledger.resolved_r_stream(aspec)
            rep = _asscore.score(aspec, resolved)
            body = rep.get("inputs_that_are_not_results", rep)
            d = body.get("dump") or {}
            cn = body.get("control_null") or {}
            kg = rep.get("kill_switch") or {}
            eq, curve = 1.0, []
            for r in resolved:
                if r.get("control") or r.get("stressed_net_return") is None:
                    continue
                eq *= _math.exp(_math.log(max(1e-12, 1.0 + frac * max(-1.0, float(r["stressed_net_return"])))))
                curve.append(round(eq, 5))
            arms_out.append({
                "arm": arm["arm"], "label": arm["label"],
                "verdict": rep.get("verdict"), "resolved_pass": rep.get("resolved_pass_trades"),
                "minimum": rep.get("minimum_before_verdict"),
                "per_trade_growth": body.get("per_trade_growth"), "pot_multiple": body.get("pot_multiple"),
                "log_growth_G": body.get("log_growth_G"), "dump_rate": d.get("dump_rate"),
                "unexitable_dumps": d.get("unexitable_dumps"), "pass_resolved": d.get("pass_resolved"),
                "edge_vs_null": cn.get("edge_per_trade"), "n_control": cn.get("n_control"),
                "open": len(_asledger.open_positions(aspec)),
                "kill": ((kg.get("expectancy_gate") or {}).get("verdict") or rep.get("verdict") or "").split(" ")[0],
                "equity_curve": curve[-120:],
            })
        except Exception as e:  # noqa: BLE001
            arms_out.append({"arm": arm["arm"], "label": arm.get("label"), "_error": str(e)[:140]})
    return {"framing": framing, "arms": arms_out, "generated_at": time.time()}


def aftershock_v4_view() -> dict:
    """AFTERSHOCK V4 (PROFIT-LOCK) — 3 arms (trail / trail+lock / lock-early), each scored on its own ledger."""
    from scripts.trading_bot.aftershock import scan_v4 as _asv4
    return _aftershock_family_view(
        "AFTERSHOCK_V4", _asv4,
        "PROFIT-LOCK — V3's net-replacement + quote-trail entry, plus a one-way break-even floor so green "
        "trades can't round-trip to a loss (without capping runners). A=plain trail · B=lock 1.05/1.02 · "
        "C=lock-early 1.02/1.01. PAPER, free tape, curve-exact ECR.")


def aftershock_v5_view() -> dict:
    """AFTERSHOCK V5 (SCALE-OUT) — 3 arms (trail / scale-50@+50% / scale-50@+100%), each on its own ledger."""
    from scripts.trading_bot.aftershock import scan_v5 as _asv5
    return _aftershock_family_view(
        "AFTERSHOCK_V5", _asv5,
        "SCALE-OUT — same net-replacement entry, but sell HALF at a green target (banks a gap-proof gain "
        "on the spike-then-gap losers) and ride HALF on the 12% trail (keeps the fat tail). A=plain trail · "
        "B=scale-half@+50% · C=scale-half@+100%. Both legs costed. PAPER, free tape, curve-exact ECR.")


# ---------- http ----------
class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _file(self, name):
        p = HERE / name
        if not p.exists() or p.parent != HERE:
            return self._json({"_error": "not found"}, 404)
        body = p.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", STATIC.get(p.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _logo(self, pool):
        """Serve a token's logo bytes (proxied, disk-cached) or a neutral SHARP-cornered placeholder."""
        mint = mint_for_pool(pool)
        seed = pool
        m = get_logo(mint) if mint else None
        if m and m.get("bytes"):
            body, ctype = m["bytes"], m["type"]
        else:
            body, ctype = _placeholder_svg(pool[:1]), "image/svg+xml"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "max-age=86400")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        q = urllib.parse.parse_qs(parsed.query)
        try:
            if path == "/api/summary":
                return self._json(cached_view("summary", 4.0, summary_view))
            if path == "/api/positions":
                return self._json(cached_view("positions", 4.0, positions_view))
            if path == "/api/evo":
                return self._json(cached_view("evo", 8.0, evo_view))
            if path == "/api/exit":
                return self._json(cached_view("exit", 5.0, exit_view))
            if path == "/api/aftershock":
                return self._json(cached_view("aftershock", 8.0, aftershock_view))
            if path == "/api/pac":
                return self._json(cached_view("pac", 1.0, pac_view))
            if path == "/api/aftershock_v2":
                return self._json(cached_view("aftershock_v2", 8.0, aftershock_v2_view))
            if path == "/api/aftershock_v3":
                return self._json(cached_view("aftershock_v3", 8.0, aftershock_v3_view))
            if path == "/api/aftershock_v4":
                return self._json(cached_view("aftershock_v4", 8.0, aftershock_v4_view))
            if path == "/api/aftershock_v5":
                return self._json(cached_view("aftershock_v5", 8.0, aftershock_v5_view))
            if path.startswith("/api/coin/"):
                return self._json(coin_view(path[len("/api/coin/"):]))
            if path.startswith("/api/ohlcv/"):
                pool = path[len("/api/ohlcv/"):]
                tf = (q.get("tf", q.get("timeframe", ["1m"]))[0])
                lim = min(2000, int(q.get("limit", ["300"])[0]))
                since = q.get("since", [None])[0]
                since_ts = int(since) if (since and since.isdigit()) else None
                return self._json(get_ohlcv(pool, tf, lim, since_ts, blocking=False))
            if path.startswith("/api/logo/"):
                return self._logo(path[len("/api/logo/"):])
            if path in ("/", "/index.html"):
                return self._file("dashboard.html")
            if path.lstrip("/") in ("app.css", "app.js", "dashboard.html"):
                return self._file(path.lstrip("/"))
            return self._json({"_error": "not found"}, 404)
        except Exception as e:  # noqa: BLE001
            return self._json({"_error": str(e)}, 500)

    # No do_POST: this dashboard is read-only. There is no mutation/order/wallet path by design.


def main():
    # Bind before starting the potentially expensive ledger refresh.  On a large research tree the
    # old order let the refresh thread enter a long JSON/index build before the main thread created
    # the socket, leaving localhost:8791 visibly offline after every watchdog restart.
    server = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    threading.Thread(target=refresher_loop, daemon=True).start()
    threading.Thread(target=logo_loop, daemon=True).start()
    print(f"memebot paper dashboard -> http://localhost:{PORT}  (Ctrl-C to stop)  [READ-ONLY PAPER]")
    server.serve_forever()


if __name__ == "__main__":
    main()
