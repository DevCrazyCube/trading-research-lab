#!/usr/bin/env python3
"""The resilient ingestion loop -- run DETACHED, it keeps the 1s candle cache fresh for held coins.

Design (free/read-only, CPU-light):
  * Discover held pools from the paper bot's ledgers (``sources.read_holdings``) and RE-discover them
    every ``holdings_refresh_secs`` so the watch set follows the bot's positions as they open/close.
  * Round-robin poll each held pool's GeckoTerminal trades through ``memebot.net`` (which enforces the
    polite 2.1s throttle + 429 backoff), deduplicate by tx_hash, roll trades into 1s candles, and flush
    completed seconds to the JSONL cache.
  * Never dies on a transient error: a bad poll is skipped, the loop backs off and continues; the whole
    loop is wrapped so any unexpected exception is logged and retried after a short sleep.

The PumpPortal push is probed ONCE at startup and logged (it is gated behind a funded key as of
2026-08-25, so the loop falls back to the free GeckoTerminal source). Nothing here funds a key, sends
an order, or touches a wallet.

Run detached (see CANDLES_README.md):
    setsid nohup python -m scripts.trading_bot.memestream listen \
        > research/data/memebot_cache/candles/ingest.log 2>&1 &
"""

from __future__ import annotations

import datetime as dt
import os
import sys
import time

from . import candles, sources

# The bot's scan/track share GeckoTerminal's ~30/min free tier with THIS ingester. Left uncapped, a
# round-robin poll of N held pools loops continuously at the 2.1s net throttle floor (~28 calls/min for
# ~9 pools) and single-handedly saturates the tier, so the bot's scan 429s and enters nothing. Cap each
# held pool to at most one /trades poll per POLL_MIN_GAP seconds (each poll still returns the full recent
# trade page, so 1s-candle fidelity is preserved as long as the pool's trade rate stays under a page per
# gap). This trades slightly less-live candles for giving the bot's scan/track priority on the budget.
POLL_MIN_GAP = float(os.environ.get("MEMESTREAM_POLL_MIN_GAP", "300.0"))


def _log(msg: str) -> None:
    print(f"[{dt.datetime.now(dt.timezone.utc).isoformat()}] {msg}", flush=True)


def run(*, seconds: float | None = None, holdings_refresh_secs: float = 120.0,
        only_pool: str | None = None) -> dict:
    """Poll held pools' trades into 1s candles until interrupted (or for ``seconds`` in test mode).

    ``only_pool`` restricts the loop to a single pool (a tight, low-latency watch used for testing or
    for a consumer that needs sub-sweep latency on one coin).
    """
    book = candles.CandleBook()
    t0 = time.time()
    last_holdings = 0.0
    held: list[dict] = []
    last_poll: dict[str, float] = {}  # pool -> monotonic time of its last /trades poll (cadence cap)
    totals = {"polls": 0, "trades": 0, "candles": 0, "errors": 0, "pools": 0}

    # One-time honest probe of the (gated) PumpPortal push so the log records WHY we use the free poll.
    try:
        seeds = [h["mint"] for h in sources.read_holdings() if h.get("mint")][:20]
        probe = sources.pumpportal_probe(seeds, seconds=6.0) if seeds else {"available": False,
                                                                            "reason": "no holdings"}
        _log(f"pumpportal subscribeTokenTrade available={probe.get('available')} "
             f"reason={probe.get('reason')!r} -> using FREE GeckoTerminal per-pool trades")
    except Exception as exc:  # noqa: BLE001
        _log(f"pumpportal probe skipped ({exc!r}); using FREE GeckoTerminal per-pool trades")

    while True:
        if seconds is not None and time.time() - t0 >= seconds:
            break
        # (re)discover holdings
        if time.time() - last_holdings >= holdings_refresh_secs or not held:
            try:
                discovered = sources.read_holdings()
                if only_pool:
                    discovered = [h for h in discovered if h["pool"] == only_pool] or \
                                 [{"pool": only_pool, "mint": None, "name": "?"}]
                if {h["pool"] for h in discovered} != {h["pool"] for h in held}:
                    _log(f"holdings: watching {len(discovered)} pool(s): "
                         f"{[h['pool'][:6] for h in discovered]}")
                held = discovered
                for h in held:
                    candles.register_keys(h["pool"], h.get("mint"))
                totals["pools"] = len(held)
            except Exception as exc:  # noqa: BLE001
                _log(f"holdings refresh error: {exc!r}")
            last_holdings = time.time()

        if not held:
            time.sleep(2.0)
            continue

        polled_any = False
        for h in held:
            if seconds is not None and time.time() - t0 >= seconds:
                break
            pool, mint = h["pool"], h.get("mint")
            # Cadence cap: skip a pool polled within POLL_MIN_GAP so we don't saturate the shared tier.
            if time.time() - last_poll.get(pool, 0.0) < POLL_MIN_GAP:
                continue
            last_poll[pool] = time.time()
            polled_any = True
            try:
                trades = sources.geckoterminal_trades(pool, mint)  # throttled inside memebot.net
                totals["polls"] += 1
                added = 0
                for tr in trades:
                    if book.add_trade(pool, ts=tr["ts"], price=tr["price"], vol=tr["vol"],
                                      side=tr["side"], tx_hash=tr["tx_hash"]):
                        added += 1
                totals["trades"] += added
                flushed = book.flush_completed(pool, now_epoch=int(time.time()))
                totals["candles"] += len(flushed)
                if added or flushed:
                    _log(f"{pool[:6]} {h.get('name','?'):>16} +{added} trades, "
                         f"+{len(flushed)} candles")
            except Exception as exc:  # noqa: BLE001 -- transient; skip this pool, keep going
                totals["errors"] += 1
                _log(f"{pool[:6]} poll error: {exc!r}")
                time.sleep(1.0)

        # Every held pool was polled within POLL_MIN_GAP -- idle briefly instead of busy-looping so we
        # don't spin the CPU or re-enter the net throttle needlessly while the cadence cap holds.
        if not polled_any:
            time.sleep(min(5.0, POLL_MIN_GAP))

    # final flush of any buffered buckets
    for h in held:
        book.flush_all(h["pool"])
    summary = {"ran_secs": round(time.time() - t0, 1), **totals}
    _log(f"stopping: {summary}")
    return summary


def main(argv: list[str]) -> int:
    seconds = None
    only_pool = None
    i = 0
    while i < len(argv):
        if argv[i] == "--seconds" and i + 1 < len(argv):
            seconds = float(argv[i + 1]); i += 2
        elif argv[i] == "--pool" and i + 1 < len(argv):
            only_pool = argv[i + 1]; i += 2
        else:
            i += 1
    run(seconds=seconds, only_pool=only_pool)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
