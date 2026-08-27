#!/usr/bin/env python3
"""Chainstack-fed real-time 1s candle ingester for the memebot dashboard (PAPER / READ-ONLY).

WHY THIS EXISTS
---------------
The dashboard's sub-minute chart reads LOCAL 1s candles from the memestream pool-keyed cache
(research/data/memebot_cache/candles/{pool}.jsonl, via candles.get_candles). Both prior feeders for
that cache are dry: the GeckoTerminal ``listen`` ingester is rate-limited (429) and throttled to one
poll / 300s to give the bot's scan priority, and the Bitquery stream is quota-dead. So the charts
show the synthetic 2-point line with no real candles.

The Chainstack Solana WS, by contrast, is UNMETERED and live -- the sniper already decodes pump.fun
trades from it in real time. This ingester reuses that exact feed to rebuild the dashboard's local 1s
candle cache from live trades, with ZERO dashboard/server changes: it writes the SAME pool-keyed JSONL
in the SAME schema candles.py already reads.

DATA PATH
---------
    ChainstackProvider.stream_ticks()          # live pump.fun TradeTick(mint, ts, price_usd, usd, side, venue)
      -> bitquery_ingest.Aggregator            # reused per-mint 1s OHLCV+flow aggregation
      -> candles._append_candles(pool, bars)   # reused writer -> research/data/memebot_cache/candles/{pool}.jsonl
      -> dashboard get_candles(pool, '1s'|'1m')

Chainstack gives a token MINT; the dashboard cache is POOL-keyed. The mint->pool map is built from the
memebot ledgers' OPEN positions (each frozen entry carries both ``pool_address`` and ``base_token``)
and refreshed every ~60s, so the watch set follows positions as they open/close.

MEMORY / DISK DISCIPLINE
------------------------
  * Ticks are filtered to TRACKED mints at ingestion -- the pump.fun firehose is thousands of mints,
    but only the memebot's open positions are aggregated, so in-memory state stays tiny.
  * Only tracked pools are written; a mint that leaves the open set has its aggregator state dropped.
  * A dead coin that stopped trading gets NO new candles -- Chainstack only streams ACTIVE trades.
    That is expected and correct; the fix is for coins that are still trading.

COORDINATION WITH THE OTHER WRITER
----------------------------------
The GeckoTerminal ``listen`` ingester may also append to the same pool files, but it is starved
(429 + a 300s per-pool poll gap), so THIS ingester is the primary now. No file is corrupted by having
both: every candle is appended as ONE short JSON line under O_APPEND (atomic, < PIPE_BUF), and
candles._read_1s explicitly collapses a duplicate/re-flushed second to the most complete candle on
read (candles.py was built anticipating "two ingesters"). We reuse candles._append_candles verbatim,
so both writers use identical format + ring-trim behavior.

READ-ONLY: subscribes and decodes only. NO orders, NO wallet, NO key, NO on-chain writes. The WS URL
(which carries the API key in its path) and the token are read from .env and NEVER logged.

Run detached under the memestream venv (it has ``websockets``; the system Python does not):
    setsid nohup scripts/trading_bot/memestream/.venv/bin/python \
        -m scripts.trading_bot.memestream.chainstack_ingest \
        >> scripts/trading_bot/memestream/chainstack_ingest.log 2>&1 < /dev/null &
(the chainstack_ingest_watchdog.sh + cron */2 keep it alive).
"""
from __future__ import annotations

import datetime as dt
import pathlib
import sys
import time

# Ensure the repo root is importable whether launched as a module or a script.
ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.trading_bot.sniper.data.chainstack import ChainstackProvider  # noqa: E402
from scripts.trading_bot.sniper.data._common import RefusedError  # noqa: E402
from scripts.trading_bot.memestream import candles as mstream  # noqa: E402
from scripts.trading_bot.memestream.bitquery_ingest import Aggregator  # noqa: E402
from scripts.trading_bot.memebot import Refused, ledger  # noqa: E402
from scripts.trading_bot.memebot.frozen import ACTIVE_INSTRUMENTS, frozen_spec  # noqa: E402

LOG = ROOT / "scripts" / "trading_bot" / "memestream" / "chainstack_ingest.log"

# The exact 10 fields candles.py get_candles/_read_1s expects (no extras -- match the schema exactly).
CANON_FIELDS = ("t", "o", "h", "l", "c", "v", "buys", "sells", "buy_vol", "sell_vol")

MAP_REFRESH_S = 60.0   # re-read the open-positions map this often (follows the bot's positions)
FLUSH_EVERY_S = 4.0    # append completed 1s candles to disk this often
IDLE_PRUNE_S = 600.0   # finalize + drop a mint's aggregator state after this idle (matches Aggregator)


def _log(msg: str) -> None:
    """Timestamped log line. Never receives or emits a secret (endpoints/tokens are never passed in)."""
    line = f"{dt.datetime.now(dt.timezone.utc).isoformat()} {msg}"
    try:
        with open(LOG, "a") as fh:
            fh.write(line + "\n")
    except OSError:
        pass
    print(line, flush=True)


def build_mint_pool_map() -> dict[str, str]:
    """mint -> pool for every OPEN memebot position across all live instruments.

    Reuses the same ledger view the dashboard uses (ledger.open_positions), so the tracked set is
    exactly the coins the bot currently holds. Each frozen entry carries both base_token (mint) and
    pool_address, which is the only place the two keys are joined.
    """
    mapping: dict[str, str] = {}
    for inst in ACTIVE_INSTRUMENTS:
        try:
            spec = frozen_spec(inst)
        except Refused:
            continue  # variant not frozen / not running
        except Exception:  # noqa: BLE001 -- a malformed spec must not kill the ingester
            continue
        try:
            opens = ledger.open_positions(spec)
        except Exception:  # noqa: BLE001
            continue
        for s in opens:
            pool = s.get("pool_address")
            mint = s.get("base_token")
            if pool and mint:
                mapping[mint] = pool
    return mapping


def _canonical(bar: dict) -> dict:
    """Strip an Aggregator bar to exactly the fields candles.py stores (drops the 'dex' extra)."""
    return {k: bar[k] for k in CANON_FIELDS}


def drain_completed(agg: Aggregator, mint_pool: dict[str, str]) -> int:
    """Append every completed 1s candle for a TRACKED mint to its pool cache; discard the rest.

    Reuses candles._append_candles verbatim so the on-disk format, sort_keys ordering, and the bounded
    ring are byte-identical to what the dashboard already reads and to what the other writer produces.
    """
    wrote = 0
    for mint, bars in list(agg.done.items()):
        pool = mint_pool.get(mint)
        if pool and bars:
            mstream._append_candles(pool, [_canonical(b) for b in bars])
            wrote += len(bars)
        agg.done[mint] = []  # clear whether written or not -- untracked bars are dropped, not stored
    return wrote


def register_all(mint_pool: dict[str, str]) -> None:
    """Record pool<->mint in the shared keymap so a read by EITHER key resolves to the pool file."""
    for mint, pool in mint_pool.items():
        try:
            mstream.register_keys(pool, mint)
        except Exception:  # noqa: BLE001
            pass


def run() -> None:
    provider = ChainstackProvider()  # reads SOLANA_WS_URL from .env; never prints it
    _log("chainstack candle ingester start (PAPER / READ-ONLY; no orders/wallet/key)")
    backoff = 2.0
    while True:
        try:
            agg = Aggregator()
            mint_pool = build_mint_pool_map()
            register_all(mint_pool)
            _log(f"map: {len(mint_pool)} tracked mints/pools; opening Chainstack WS stream...")
            last_flush = time.monotonic()
            last_map = last_flush
            ticks = kept = wrote_total = 0

            for tick in provider.stream_ticks():
                ticks += 1
                # Aggregate ONLY tracked mints -- keeps in-memory state to the open positions, not the
                # whole pump.fun firehose. Feed the reused Aggregator a bitquery-shaped record.
                if tick.mint in mint_pool:
                    agg.add({
                        "mint": tick.mint,
                        "t": dt.datetime.fromtimestamp(tick.ts, dt.timezone.utc).isoformat(),
                        "price_usd": tick.price_usd,
                        "usd": tick.usd,
                        "side": tick.side,
                        "family": tick.venue,
                    })
                    kept += 1

                now = time.monotonic()

                if now - last_flush >= FLUSH_EVERY_S:
                    agg.prune(time.time())          # finalize idle open bars, drop stale state
                    w = drain_completed(agg, mint_pool)
                    wrote_total += w
                    last_flush = now
                    if w:
                        _log(f"flush +{w} candles ({wrote_total} total; {kept}/{ticks} ticks tracked; "
                             f"{len(mint_pool)} pools; {len(agg.open)} live mints)")
                    backoff = 2.0                   # a healthy flush cycle resets the reconnect backoff

                if now - last_map >= MAP_REFRESH_S:
                    new_map = build_mint_pool_map()
                    for mint, pool in new_map.items():
                        if mint not in mint_pool:
                            try:
                                mstream.register_keys(pool, mint)
                            except Exception:  # noqa: BLE001
                                pass
                    # Drop aggregator state for mints that left the open set -- stay memory-frugal.
                    for mint in list(agg.open):
                        if mint not in new_map:
                            agg.open.pop(mint, None)
                            agg.done.pop(mint, None)
                            agg.last_seen.pop(mint, None)
                    if len(new_map) != len(mint_pool):
                        _log(f"map refresh: {len(mint_pool)} -> {len(new_map)} tracked pools")
                    mint_pool = new_map
                    last_map = now

        except RefusedError as e:  # plan inactive / WS refused -- terminal for this attempt
            _log(f"provider refused: {repr(e)[:160]} -- retry in {backoff:.0f}s")
            time.sleep(backoff)
            backoff = min(60.0, backoff * 1.7)
        except Exception as e:  # noqa: BLE001 -- any WS drop -> reconnect with backoff
            _log(f"stream dropped: {repr(e)[:160]} -- reconnect in {backoff:.0f}s")
            time.sleep(backoff)
            backoff = min(60.0, backoff * 1.7)


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        pass
