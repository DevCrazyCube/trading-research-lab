#!/usr/bin/env python3
"""Bitquery real-time Solana trade ingester (PAPER / READ-ONLY).

Subscribes to the Bitquery EAP streaming websocket and records EVERY pump.fun + pumpswap trade to a
rolling per-day JSONL cache. This is a FREE (trial/dev-tier), keyless-wallet, read-only firehose --
NO orders, NO wallet, NO SOL, NO on-chain writes. It exists to give the memebot true per-trade (tick)
data instead of GeckoTerminal's ~40s polling, so we can (a) build real 1s candles and (b) TEST whether
tick granularity actually changes the strategy (our own parameter analysis says longer horizons win,
so this is a genuine test, not an assumption).

Auth: reads BITQUERY_API (an `ory_at_...` OAuth token) from .env. The token is NEVER logged or printed.

Point-budget note: Bitquery's free tier is small; the 7-day trial grants ~100k stream-min. ONE
continuous connection burns ~1 stream-min/min (~10k over 7 days) -- well within trial, but this is a
short experiment window, not a permanent feed. After the trial the dev tier (1,000 points) will not
sustain it; that is a deliberate owner spend-gate, not something this ingester assumes.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import pathlib
import sys

import websockets  # provided by scripts/trading_bot/memestream/.venv

ROOT = pathlib.Path(__file__).resolve().parents[3]
ENV = ROOT / ".env"
OUT_DIR = ROOT / "research" / "data" / "memebot_cache" / "bitquery_candles"   # per-mint 1s candles
LOG = ROOT / "scripts" / "trading_bot" / "memestream" / "bitquery_ingest.log"
STREAM_URL = "wss://streaming.bitquery.io/eap?token="

# The raw stream is ~500 trades/s across thousands of mints -- storing raw ticks would be ~6 GB/day.
# Instead we aggregate per-mint 1-SECOND candles in memory and flush completed buckets to disk. Disk
# stays tiny, and candles are exactly what the charts + the tick-vs-strategy analysis need.
FLUSH_EVERY_S = 8.0        # how often to append completed 1s buckets to disk
IDLE_PRUNE_S = 600.0       # drop a mint's in-memory state after this many seconds with no trades
QUOTA_RETRY_S = 300.0      # a quota refusal is not a transient socket drop; do not hammer the provider


class StreamServerError(RuntimeError):
    """A typed server-side refusal so the outer loop always sleeps before reconnecting."""


def _server_retry_delay(payload: object, backoff: float) -> float:
    """Return the fail-closed reconnect delay for a server error.

    Bitquery acknowledges the websocket before reporting an exhausted traffic allowance.  The old
    loop treated that path as a clean ``break`` and immediately reconnected, hundreds of times per
    minute.  Quota/traffic refusals therefore get a long circuit-breaker; other server errors use the
    ordinary exponential backoff.
    """
    text = json.dumps(payload, sort_keys=True).lower()
    if "quota" in text or "traffic limit" in text or "rate limit" in text:
        return max(float(backoff), QUOTA_RETRY_S)
    return max(2.0, float(backoff))

# Only the venues the memebot plays, AND only trades whose buy leg is >= MIN_TRADE_USD. The unfiltered
# firehose (~500 trades/s, mostly sub-$1 dust) burned the free Bitquery quota in ~90 min. Filtering at
# the SOURCE (server-side `where`) drops the dust before it counts against quota, so a multi-day sample
# becomes feasible on the free tier. ProtocolFamily is now persisted per bar (Pumpfun = bonding-curve
# ~2% round-trip toll; Pumpswap = migrated AMM, Jupiter-tradeable ~0.5-0.8%) so venue is REAL, not a
# throughput proxy. NOTE: deployed while the quota was exhausted (could not live-test); verify the
# filter returns trades once the quota resets.
MIN_TRADE_USD = "5"
SUBSCRIPTION = {
    "query": """
subscription {
  Solana {
    DEXTrades(where: {Trade: {Dex: {ProtocolFamily: {in: ["Pumpfun", "Pumpswap"]}}, Buy: {AmountInUSD: {ge: "%s"}}}}) {
      Block { Time }
      Trade {
        Dex { ProtocolName ProtocolFamily }
        Buy  { AmountInUSD PriceInUSD Currency { Symbol MintAddress } }
        Sell { AmountInUSD PriceInUSD Currency { Symbol MintAddress } }
      }
    }
  }
}
""" % MIN_TRADE_USD
}


def _log(msg: str) -> None:
    line = f"{dt.datetime.now(dt.timezone.utc).isoformat()} {msg}"
    try:
        with open(LOG, "a") as fh:
            fh.write(line + "\n")
    except OSError:
        pass
    print(line, flush=True)


def _load_token() -> str | None:
    try:
        for line in ENV.read_text().splitlines():
            line = line.strip()
            if line.startswith("BITQUERY_API="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        return None
    return None


def _mint_path(mint: str) -> pathlib.Path:
    return OUT_DIR / f"{mint}.jsonl"


def _epoch(iso: str | None) -> int | None:
    if not iso:
        return None
    try:
        return int(dt.datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp())
    except ValueError:
        return None


class Aggregator:
    """Per-mint 1-second OHLCV+flow candles, held in memory; completed buckets are flushed to disk."""

    def __init__(self) -> None:
        self.open: dict[str, dict] = {}          # mint -> current (incomplete) 1s bar
        self.done: dict[str, list] = {}          # mint -> completed bars awaiting flush
        self.sym: dict[str, str] = {}
        self.venue: dict[str, str] = {}          # mint -> ProtocolFamily (Pumpfun/Pumpswap)
        self.last_seen: dict[str, float] = {}

    def add(self, rec: dict) -> None:
        mint = rec.get("mint")
        price = rec.get("price_usd")
        sec = _epoch(rec.get("t"))
        if not mint or price is None or sec is None:
            return
        usd = rec.get("usd") or 0.0
        side = rec.get("side")
        if rec.get("sym"):
            self.sym[mint] = rec["sym"]
        if rec.get("family"):
            self.venue[mint] = rec["family"]
        self.last_seen[mint] = sec
        cur = self.open.get(mint)
        if cur is None or cur["t"] != sec:
            if cur is not None and cur["t"] < sec:
                self.done.setdefault(mint, []).append(cur)   # bucket rolled over -> complete
            cur = {"t": sec, "o": price, "h": price, "l": price, "c": price,
                   "v": 0.0, "buys": 0, "sells": 0, "buy_vol": 0.0, "sell_vol": 0.0,
                   "dex": self.venue.get(mint)}   # persist venue: Pumpfun(bonding) vs Pumpswap(migrated)
            self.open[mint] = cur
        cur["h"] = max(cur["h"], price)
        cur["l"] = min(cur["l"], price)
        cur["c"] = price
        cur["v"] += usd
        if side == "buy":
            cur["buys"] += 1; cur["buy_vol"] += usd
        else:
            cur["sells"] += 1; cur["sell_vol"] += usd

    def flush(self) -> int:
        # Only persist bars with REAL activity -- the raw stream's long tail is dust mints with 1-2
        # trades/s that no one trades. This keeps disk to a fraction while retaining every coin that
        # actually moves (the ones the strategy could touch).
        MIN_TRADES, MIN_USD = 3, 20.0
        n = 0
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        for mint, bars in list(self.done.items()):
            keep = [b for b in bars if (b["buys"] + b["sells"]) >= MIN_TRADES or b["v"] >= MIN_USD]
            if not keep:
                self.done[mint] = []
                continue
            try:
                with open(_mint_path(mint), "a") as fh:
                    for b in keep:
                        fh.write(json.dumps(b) + "\n")
                        n += 1
            except OSError:
                pass
            self.done[mint] = []
        return n

    def prune(self, now_sec: float) -> None:
        for mint, seen in list(self.last_seen.items()):
            if now_sec - seen > IDLE_PRUNE_S:
                # finalize any dangling open bar, then drop state
                cur = self.open.pop(mint, None)
                if cur:
                    self.done.setdefault(mint, []).append(cur)
                self.last_seen.pop(mint, None)


def _flatten(node: dict) -> dict | None:
    """Bitquery trade node -> one compact record. The memecoin side is whichever leg is the SPL token
    (not SOL/USDC), so we can key candles by its mint. Returns None if it can't be identified."""
    trade = node.get("Trade") or {}
    blk = node.get("Block") or {}
    buy = trade.get("Buy") or {}
    sell = trade.get("Sell") or {}
    QUOTES = {"So11111111111111111111111111111111111111112",  # wSOL
              "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
              "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"}  # USDT
    buy_mint = ((buy.get("Currency") or {}).get("MintAddress"))
    sell_mint = ((sell.get("Currency") or {}).get("MintAddress"))
    # the token being traded is the non-quote leg
    if buy_mint and buy_mint not in QUOTES:
        token, side = buy, "buy"
    elif sell_mint and sell_mint not in QUOTES:
        token, side = sell, "sell"
    else:
        return None
    cur = token.get("Currency") or {}

    def _f(v):  # Bitquery returns numeric fields as STRINGS
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    dex = trade.get("Dex") or {}
    return {
        "t": blk.get("Time"),
        "mint": cur.get("MintAddress"),
        "sym": cur.get("Symbol"),
        "dex": dex.get("ProtocolName"),
        "family": dex.get("ProtocolFamily"),   # Pumpfun (bonding-curve) vs Pumpswap (migrated AMM)
        "side": side,  # taker direction relative to the token leg
        "usd": _f(token.get("AmountInUSD")) or 0.0,
        "price_usd": _f(token.get("PriceInUSD")),
    }


async def run() -> None:
    token = _load_token()
    if not token:
        _log("FATAL: BITQUERY_API not found in .env"); sys.exit(1)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    _log(f"ingester start (token len {len(token)}, prefix {token[:7]})")

    backoff = 2.0
    while True:
        try:
            async with websockets.connect(STREAM_URL + token,
                                          subprotocols=["graphql-transport-ws"],
                                          open_timeout=20, ping_interval=15) as ws:
                await ws.send(json.dumps({"type": "connection_init", "payload": {}}))
                agg = Aggregator()
                trades_seen = 0
                bars_written = 0
                last_flush = 0.0
                import time as _time
                async for raw in ws:
                    m = json.loads(raw)
                    mt = m.get("type")
                    if mt == "connection_ack":
                        await ws.send(json.dumps({"id": "1", "type": "subscribe", "payload": SUBSCRIPTION}))
                        _log("connection_ack -> subscribed (Pumpfun + Pumpswap); aggregating 1s candles")
                        last_flush = _time.monotonic()
                    elif mt in ("next", "data"):
                        trades = (((m.get("payload") or {}).get("data") or {})
                                  .get("Solana") or {}).get("DEXTrades") or []
                        for node in trades:
                            rec = _flatten(node)
                            if rec:
                                agg.add(rec)
                                trades_seen += 1
                        # Only actual data proves the subscription is healthy.  A connection ACK followed
                        # by a quota error must not reset the retry backoff.
                        backoff = 2.0
                        now = _time.monotonic()
                        if now - last_flush >= FLUSH_EVERY_S:
                            w = agg.flush()
                            agg.prune(_time.time())
                            bars_written += w
                            last_flush = now
                            _log(f"flush: +{w} bars ({bars_written} total, {trades_seen} trades seen, "
                                 f"{len(agg.open)} live mints)")
                    elif mt in ("error", "connection_error"):
                        payload = m.get("payload")
                        raise StreamServerError(f"server {mt}: {json.dumps(payload)[:300]}")
                    elif mt == "complete":
                        raise StreamServerError("subscription complete")
        except StreamServerError as e:
            delay = _server_retry_delay(str(e), backoff)
            _log(f"{e} -- reconnect in {delay:.0f}s")
            await asyncio.sleep(delay)
            backoff = min(60.0, backoff * 1.7)
        except Exception as e:  # noqa: BLE001 -- any drop -> reconnect with backoff
            _log(f"connection dropped: {repr(e)[:160]} -- reconnect in {backoff:.0f}s")
            await asyncio.sleep(backoff)
            backoff = min(60.0, backoff * 1.7)


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass
