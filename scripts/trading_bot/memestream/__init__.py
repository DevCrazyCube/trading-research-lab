#!/usr/bin/env python3
"""MEMESTREAM -- a self-contained, PAPER/read-only realtime 1-second candle data layer.

This package aggregates real memecoin trades into 1-second OHLCV candles (with a buy/sell split)
for the coins the paper memebot currently holds, and exposes a clean, importable READ API that two
consumers will later wire in:

  * the dashboard's 1s price charts        -> ``get_candles(pool, timeframe=..., lookback_secs=...)``
  * the flow-following exit's buy-pressure -> ``get_flow(pool, window_secs=...)``

It is a *data layer only*. It places NO orders, holds NO wallet, touches NO real SOL, writes NOTHING
on-chain, and reads only FREE, KEYLESS, read-only public data. It does not wire the consumers; it just
publishes candles to a compact on-disk cache and hands back two documented read functions.

TRADE-SOURCE REALITY (discovered live 2026-08-25)
-------------------------------------------------
PumpPortal's per-token push (``subscribeTokenTrade``) is NO LONGER FREE -- the server now replies:

    "'subscribeTokenTrade' ... only available when connecting with an API key funded with at least
     0.02 SOL."

Funding a key is real money + a wallet, which this paper layer must never do. So the *working, free*
source today is GeckoTerminal's keyless, already-allowlisted per-pool ``/trades`` endpoint, polled
politely through ``memebot.net`` (the same 2.1s throttle + 429 backoff the bot already uses). It
returns real trades with a second-resolution ``block_timestamp``, a ``kind`` (buy/sell), USD volume
and prices -- everything the 1s aggregator needs. The PumpPortal push path is still implemented
(``sources.pumpportal_*``) behind the read-only ``net.assert_data_ws`` guard and would light up again
for free if PumpPortal restores it, or via an OWNER-GATED funded key (never done here). Both sources
normalise to the SAME trade shape and feed the SAME aggregator, so the cache and read API are
source-agnostic.

HONEST LATENCY NOTE
-------------------
This tightens the bot's reaction from the ~90s GeckoTerminal ``new_pools`` cadence to ~1-2s per held
coin (real 1s-resolution candles, refreshed every poll cycle). It does NOT out-race millisecond
snipers or MEV bots -- it is a paper monitoring layer, not a co-located execution engine.
"""

from __future__ import annotations


class Refused(RuntimeError):
    """Absence is a refusal, never a silent zero (mirrors memebot.Refused)."""


__all__ = ["Refused"]
