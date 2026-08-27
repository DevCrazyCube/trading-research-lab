#!/usr/bin/env python3
"""BitqueryProvider — HTTP aggregated GraphQL for recent bars + health (PAPER / READ-ONLY).

Uses the Bitquery EAP HTTP endpoint with the BITQUERY_API bearer token from .env, reusing the query
+ parse patterns from scripts/smartmoney/collect_trades.py. This is the aggregated *query* path, NOT
the streaming subscription (that quota is spent) — so there is no live push here: `stream_ticks()`
refuses and the runner uses the Chainstack WS for streaming. `recent_bars()` pulls a mint's recent
pump.fun DEXTrades and rolls them into 1s bars. `healthy()` runs a tiny probe and returns False when
the quota is exhausted or the endpoint errors. Nothing here signs, sends, or loads a wallet/key. The
token is read from .env and never printed.
"""
from __future__ import annotations

import datetime as dt
import json
import time
import urllib.error
import urllib.request
from typing import Iterator, Optional

from ._common import HTTP, RefusedError, SOL_MINTS, read_env, trades_to_bars

BITQUERY_URL = "https://streaming.bitquery.io/eap"

# Recent pump.fun DEXTrades for one mint (token on either the Buy or Sell leg), newest first.
_BARS_QUERY = """{ Solana { DEXTrades(
  limit: {count: %d}, orderBy: {descending: Block_Time},
  where: {Trade: {Dex: {ProtocolFamily: {is: "Pumpfun"}}},
          Block: {Time: {after: "%s"}},
          any: [{Trade: {Buy: {Currency: {MintAddress: {is: "%s"}}}}},
                {Trade: {Sell: {Currency: {MintAddress: {is: "%s"}}}}}]}) {
  Block { Time }
  Trade { Buy {Amount AmountInUSD PriceInUSD Currency{MintAddress}}
          Sell {Amount AmountInUSD PriceInUSD Currency{MintAddress}} } } } }"""

# Tiny liveness probe — one recent trade, no mint filter.
_PROBE_QUERY = """{ Solana { DEXTrades(limit: {count: 1}, orderBy: {descending: Block_Time},
  where: {Trade: {Dex: {ProtocolFamily: {is: "Pumpfun"}}}}) { Block { Time } } } }"""


class BitqueryProvider:
    """Bitquery EAP HTTP: recent-bars + health. No live stream (subscription quota spent)."""

    name = "bitquery"

    def __init__(self, token: Optional[str] = None, timeout: float = 30.0):
        self._token = token or read_env("BITQUERY_API")
        self._timeout = timeout

    # -- HTTP ---------------------------------------------------------------------------------
    def _post(self, query: str) -> dict:
        """POST a GraphQL query. Raises RefusedError on 403/quota, urllib errors on transport."""
        if not self._token:
            raise RefusedError("BitqueryProvider: BITQUERY_API not set in .env")
        body = json.dumps({"query": query}).encode()
        req = HTTP.json_rpc_request(BITQUERY_URL, body)
        req.add_header("Authorization", "Bearer " + self._token)
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                data = json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 402, 403):
                raise RefusedError(f"Bitquery refused: HTTP {exc.code} (auth / quota)") from exc
            raise
        if isinstance(data, dict) and data.get("errors"):
            # GraphQL-level errors include quota exhaustion ("payment required" / rate messages).
            raise RefusedError(f"Bitquery errors: {data['errors']}")
        return data

    # -- health -------------------------------------------------------------------------------
    def healthy(self) -> bool:
        """Tiny probe query. False on 403 / quota-exhausted / any error."""
        if not self._token:
            return False
        try:
            data = self._post(_PROBE_QUERY)
        except Exception:
            return False
        return bool(((data.get("data") or {}).get("Solana")) is not None)

    # -- stream (unavailable) -----------------------------------------------------------------
    def stream_ticks(self) -> Iterator:
        """Bitquery HTTP is pull-only and the streaming subscription quota is spent — no live push.
        Use ChainstackProvider.stream_ticks() for the live feed; call recent_bars() here instead."""
        raise RefusedError(
            "BitqueryProvider has no live stream (HTTP aggregated is pull-only; subscription quota "
            "spent). Use ChainstackProvider.stream_ticks(); use BitqueryProvider.recent_bars().")
        yield  # pragma: no cover - marks this as a generator for the Protocol

    # -- recent bars --------------------------------------------------------------------------
    def _parse_trades(self, rows: list, mint: str) -> list:
        """Adapted from collect_trades.parse(): keep only trades where `mint` is the memecoin leg."""
        out = []
        for t in rows:
            try:
                b, s = t["Trade"]["Buy"], t["Trade"]["Sell"]
                bm, sm = b["Currency"]["MintAddress"], s["Currency"]["MintAddress"]
                ts = int(dt.datetime.strptime(t["Block"]["Time"], "%Y-%m-%dT%H:%M:%SZ")
                         .replace(tzinfo=dt.timezone.utc).timestamp())
                if bm == mint and sm in SOL_MINTS:            # token acquired, SOL spent -> BUY
                    side, price, usd = "buy", float(b["PriceInUSD"] or 0), float(s["AmountInUSD"] or 0)
                elif sm == mint and bm in SOL_MINTS:          # token given up, SOL received -> SELL
                    side, price, usd = "sell", float(s["PriceInUSD"] or 0), float(b["AmountInUSD"] or 0)
                else:
                    continue
                out.append({"ts": ts, "price_usd": price, "usd": usd, "side": side})
            except (KeyError, TypeError, ValueError):
                continue
        return out

    def recent_bars(self, mint: str, lookback_s: int = 300, limit: int = 5000) -> list:
        """Pull the mint's recent pump.fun trades and roll them into 1s bars. Empty on refusal."""
        after = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=lookback_s)) \
            .strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            data = self._post(_BARS_QUERY % (limit, after, mint, mint))
        except (RefusedError, urllib.error.URLError, TimeoutError, OSError):
            return []
        rows = (((data.get("data") or {}).get("Solana") or {}).get("DEXTrades")) or []
        return trades_to_bars(self._parse_trades(rows, mint))
