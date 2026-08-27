#!/usr/bin/env python3
"""1-second OHLCV aggregation + the cache + the two read functions the consumers import.

CACHE FORMAT
------------
One append-only JSONL file per held pool, bounded to a ring of the most recent candles:

    research/data/memebot_cache/candles/{pool}.jsonl

Each line is one COMPLETED 1-second candle (only seconds that actually had >=1 trade are written --
the series is sparse; gaps mean "no trades that second"):

    {
      "t":        <int>   # epoch seconds, start-of-second bucket (UTC)
      "o","h","l","c":    # base-token price in USD (open/high/low/close within the second)
      "v":        <float> # total traded volume in USD in the second
      "buys":     <int>   # number of BUY trades
      "sells":    <int>   # number of SELL trades
      "buy_vol":  <float> # BUY volume in USD
      "sell_vol": <float> # SELL volume in USD
    }

The dashboard reads OHLCV for its 1s chart; the flow-exit reads buys/sells/buy_vol/sell_vol for
realtime buy-pressure. 5s and 1m frames are DERIVED from the 1s base on read (no separate storage).

READ API (import these -- they are read-only and cross-process safe; they touch only the JSONL cache)
------
    get_candles(pool, timeframe='1s', lookback_secs=None) -> list[dict]
    get_flow(pool, window_secs=60)                         -> dict

Both accept a POOL address (what the bot/dashboard key on); a token MINT is also accepted and resolved
via the small keymap the ingester maintains. Missing data returns an empty series / a zeroed flow that
is EXPLICITLY marked ``trades: 0`` -- an honest "nothing traded", never a fabricated number.
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import time

from . import Refused

ROOT = pathlib.Path(__file__).resolve().parents[3]
CACHE_DIR = ROOT / "research" / "data" / "memebot_cache" / "candles"
KEYMAP_PATH = CACHE_DIR / "_keymap.json"  # {mint_or_pool: pool} so reads can key by either

# Bounded ring: keep ~4h of 1s candles per pool so a long run never grows without limit.
MAX_CANDLES = 14400

# timeframe label -> bucket size in seconds
TIMEFRAMES = {"1s": 1, "5s": 5, "1m": 60}


def _cache_path(pool: str) -> pathlib.Path:
    return CACHE_DIR / f"{pool}.jsonl"


# --------------------------------------------------------------------------------------------------
# keymap: let a consumer call get_candles/get_flow with EITHER a pool address or a token mint.
# --------------------------------------------------------------------------------------------------
def load_keymap() -> dict:
    if not KEYMAP_PATH.exists():
        return {}
    try:
        return json.loads(KEYMAP_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def register_keys(pool: str, mint: str | None = None) -> None:
    """Record pool<->mint so reads by either key resolve to the same candle file (pool-keyed)."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    km = load_keymap()
    km[pool] = pool
    if mint:
        km[mint] = pool
    tmp = KEYMAP_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(km, indent=0, sort_keys=True))
    tmp.replace(KEYMAP_PATH)


def resolve_pool(key: str) -> str:
    """Map a pool address OR a token mint to the pool the candle file is stored under."""
    return load_keymap().get(key, key)


# --------------------------------------------------------------------------------------------------
# CandleBook -- the in-memory 1s aggregator used ONLY by the ingester (not by the read API).
# --------------------------------------------------------------------------------------------------
class CandleBook:
    """Rolls deduplicated trades into 1s OHLCV candles per pool and flushes completed seconds to disk.

    Trades may arrive slightly out of order or in overlapping batches (polling returns the last N
    trades each cycle), so each trade is deduplicated by its ``tx_hash`` and a second-bucket is only
    flushed once it is COMPLETE (its second is strictly older than the newest second seen for that
    pool, minus a small guard). Flushing appends to the pool's JSONL and trims the ring.
    """

    def __init__(self, *, guard_secs: int = 2, seen_ring: int = 4000):
        self._buckets: dict[str, dict[int, dict]] = {}   # pool -> {second -> candle}
        self._seen: dict[str, dict[str, float]] = {}     # pool -> {tx_hash -> monotonic_seen}
        self._max_second: dict[str, int] = {}            # pool -> newest trade second seen
        self._flushed_upto: dict[str, int] = {}          # pool -> last flushed second (exclusive)
        self._guard = guard_secs
        self._seen_ring = seen_ring

    def add_trade(self, pool: str, *, ts: int, price: float, vol: float,
                  side: str, tx_hash: str) -> bool:
        """Add one trade to its 1s bucket. Returns False if it was a duplicate (already counted)."""
        if price is None or price <= 0:
            return False
        # A second that has already been flushed to disk is CLOSED -- dropping a late trade for it
        # keeps candles append-only-consistent and never emits a partial re-flush of the same second.
        if int(ts) <= self._flushed_upto.get(pool, -1):
            return False
        seen = self._seen.setdefault(pool, {})
        if tx_hash in seen:
            return False
        seen[tx_hash] = time.monotonic()
        if len(seen) > self._seen_ring:  # bound the dedup memory
            for k in sorted(seen, key=seen.get)[: len(seen) - self._seen_ring]:
                seen.pop(k, None)

        sec = int(ts)
        book = self._buckets.setdefault(pool, {})
        c = book.get(sec)
        if c is None:
            c = {"t": sec, "o": price, "h": price, "l": price, "c": price,
                 "v": 0.0, "buys": 0, "sells": 0, "buy_vol": 0.0, "sell_vol": 0.0}
            book[sec] = c
        c["h"] = max(c["h"], price)
        c["l"] = min(c["l"], price)
        c["c"] = price  # last trade in the second wins as close (batches are time-ordered enough)
        v = float(vol or 0.0)
        c["v"] += v
        if side == "buy":
            c["buys"] += 1
            c["buy_vol"] += v
        else:
            c["sells"] += 1
            c["sell_vol"] += v
        self._max_second[pool] = max(self._max_second.get(pool, sec), sec)
        return True

    def flush_completed(self, pool: str, now_epoch: int | None = None) -> list[dict]:
        """Append every completed 1s candle for ``pool`` to disk and return what was written."""
        book = self._buckets.get(pool)
        if not book:
            return []
        now_epoch = int(now_epoch if now_epoch is not None else time.time())
        # A second is complete once the newest activity is at least ``guard`` seconds past it.
        horizon = max(self._max_second.get(pool, now_epoch), now_epoch) - self._guard
        ready = sorted(s for s in book if s <= horizon)
        out = []
        for s in ready:
            out.append(book.pop(s))
        if out:
            _append_candles(pool, out)
            self._flushed_upto[pool] = max(self._flushed_upto.get(pool, 0), out[-1]["t"])
        return out

    def flush_all(self, pool: str) -> list[dict]:
        """Force-flush every buffered bucket (used on shutdown)."""
        book = self._buckets.get(pool)
        if not book:
            return []
        out = [book.pop(s) for s in sorted(book)]
        if out:
            _append_candles(pool, out)
        return out


def _append_candles(pool: str, candles: list[dict]) -> None:
    path = _cache_path(pool)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as fh:
        for c in candles:
            fh.write(json.dumps(c, sort_keys=True) + "\n")
    _trim_ring(path)


def _trim_ring(path: pathlib.Path) -> None:
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return
    if len(lines) > MAX_CANDLES:
        path.write_text("\n".join(lines[-MAX_CANDLES:]) + "\n")


# --------------------------------------------------------------------------------------------------
# READ API -- the two documented functions the dashboard and the flow-exit import.
# --------------------------------------------------------------------------------------------------
def _read_1s(pool: str) -> list[dict]:
    """Read the raw 1s candle series for a pool (oldest-first). Empty if nothing cached yet."""
    path = _cache_path(pool)
    if not path.exists():
        return []
    by_t: dict[int, dict] = {}
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            c = json.loads(line)
        except json.JSONDecodeError:
            continue
        # Collapse any duplicate/re-flushed second (e.g. two ingesters, or a restart) to the MOST
        # complete candle for that second, so counts and volume are never double-summed on read.
        prev = by_t.get(c["t"])
        if prev is None or (c["buys"] + c["sells"]) >= (prev["buys"] + prev["sells"]):
            by_t[c["t"]] = c
    return [by_t[t] for t in sorted(by_t)]


def _rollup(candles: list[dict], size: int) -> list[dict]:
    """Aggregate 1s candles into ``size``-second OHLCV buckets. Sparse in -> sparse out."""
    if size <= 1:
        return candles
    buckets: dict[int, dict] = {}
    for c in candles:
        b = (c["t"] // size) * size
        agg = buckets.get(b)
        if agg is None:
            buckets[b] = {"t": b, "o": c["o"], "h": c["h"], "l": c["l"], "c": c["c"],
                          "v": c["v"], "buys": c["buys"], "sells": c["sells"],
                          "buy_vol": c["buy_vol"], "sell_vol": c["sell_vol"]}
        else:
            agg["h"] = max(agg["h"], c["h"])
            agg["l"] = min(agg["l"], c["l"])
            agg["c"] = c["c"]  # candles are oldest-first, so last wins as close
            agg["v"] += c["v"]
            agg["buys"] += c["buys"]
            agg["sells"] += c["sells"]
            agg["buy_vol"] += c["buy_vol"]
            agg["sell_vol"] += c["sell_vol"]
    return [buckets[b] for b in sorted(buckets)]


def get_candles(pool: str, timeframe: str = "1s", lookback_secs: int | None = None) -> list[dict]:
    """Return cached OHLCV candles for ``pool`` (or a token mint), oldest-first.

    Args:
        pool:          pool address, or a token mint (resolved via the ingester's keymap).
        timeframe:     '1s' (base), '5s', or '1m' (5s/1m are derived from the 1s series on read).
        lookback_secs: if set, only candles whose start time is within the last N seconds of the most
                       recent cached candle are returned (a light, wall-clock-independent window).

    Returns a list of candle dicts {t,o,h,l,c,v,buys,sells,buy_vol,sell_vol}. Empty list if the pool
    has no cache yet (honest absence -- never a fabricated candle).
    """
    if timeframe not in TIMEFRAMES:
        raise Refused(f"unknown timeframe {timeframe!r}; supported: {sorted(TIMEFRAMES)}")
    base = _read_1s(resolve_pool(pool))
    if not base:
        return []
    if lookback_secs is not None:
        cutoff = base[-1]["t"] - int(lookback_secs)
        base = [c for c in base if c["t"] >= cutoff]
    return _rollup(base, TIMEFRAMES[timeframe])


def get_flow(pool: str, window_secs: int = 60) -> dict:
    """Return realtime buy/sell PRESSURE over the last ``window_secs`` for ``pool`` (or a mint).

    This is what the flow-following exit consumes. ``net`` is (buy_vol - sell_vol) in USD: positive =
    net buying pressure, negative = net selling. ``as_of`` is the newest cached candle's epoch second,
    so a stale feed is visible (compare to wall clock). A pool with no recent trades returns all zeros
    with ``trades: 0`` -- an explicit "nothing traded", not a silent zero.
    """
    base = _read_1s(resolve_pool(pool))
    now_ref = base[-1]["t"] if base else int(time.time())
    cutoff = now_ref - int(window_secs)
    window = [c for c in base if c["t"] >= cutoff] if base else []
    buys = sum(c["buys"] for c in window)
    sells = sum(c["sells"] for c in window)
    buy_vol = sum(c["buy_vol"] for c in window)
    sell_vol = sum(c["sell_vol"] for c in window)
    total_vol = buy_vol + sell_vol
    return {
        "pool": resolve_pool(pool),
        "window_secs": int(window_secs),
        "trades": buys + sells,
        "buys": buys,
        "sells": sells,
        "buy_vol": round(buy_vol, 6),
        "sell_vol": round(sell_vol, 6),
        "net": round(buy_vol - sell_vol, 6),
        "buy_frac": round(buy_vol / total_vol, 4) if total_vol > 0 else None,
        "as_of": now_ref,
        "as_of_utc": dt.datetime.fromtimestamp(now_ref, dt.timezone.utc).isoformat(),
    }


def cached_pools() -> list[str]:
    """List pools that currently have a candle cache file (for dashboards / diagnostics)."""
    if not CACHE_DIR.exists():
        return []
    return sorted(p.stem for p in CACHE_DIR.glob("*.jsonl") if not p.stem.startswith("_"))
