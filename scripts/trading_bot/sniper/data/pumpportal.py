#!/usr/bin/env python3
"""PumpPortal live DataProvider — a FREE-with-funded-key, quota-independent trade feed (PAPER/READ-ONLY).

WHY: the primary ChainstackProvider hit its monthly Request-Unit quota (HTTP 403) on 2026-08-26, so its
WS trade stream is dead until the quota resets. PumpPortal's data websocket streams pump.fun trades for
a funded api-key (.env ``LIGHTNING_API``) at no per-request cost. This provider tracks freshly-created
mints and subscribes to their trades, yielding the same ``TradeTick`` the sniper already consumes, so it
drops into ``pick_provider`` / ``for tick in provider.stream_ticks()`` with zero downstream change.

READ-ONLY: it opens ONLY the data websocket and sends ONLY subscribe/unsubscribe methods
(subscribeNewToken / subscribeTokenTrade / unsubscribeTokenTrade). It NEVER sends a trade, loads a
wallet beyond reading the api-key string, or writes on-chain. The api-key is never logged (a connect
error can echo the URI, so the URL is never printed).

Price basis mirrors _common.decode_pump_trade_event: marginal reserve price vSol/vTokens (SOL) times
SOL_USD_DEFAULT, with the executed solAmount/tokenAmount price as the migrated-pool fallback — so ticks
are on the SAME scale as the Chainstack feed and switching back is seamless.
"""
from __future__ import annotations

import json
import time
from collections import OrderedDict
from typing import Iterator

from websockets.sync.client import connect  # sync client (memestream venv)

from ..types import TradeTick
from ._common import read_env, SOL_USD_DEFAULT

DATA_WS_URL = "wss://pumpportal.fun/api/data"
_MAX_TRACKED = 400          # cap subscribed mints; unsubscribe the oldest beyond this (bounded memory)
_RECV_TIMEOUT_S = 30.0


def _f(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _trade_to_tick(ev: dict) -> TradeTick | None:
    """Turn a PumpPortal trade event into a TradeTick, or None if it cannot be priced."""
    mint = ev.get("mint")
    side = ev.get("txType")
    if not mint or side not in ("buy", "sell"):
        return None
    v_sol = _f(ev.get("vSolInBondingCurve"))
    v_tok = _f(ev.get("vTokensInBondingCurve"))
    sol_amount = _f(ev.get("solAmount"))
    tok_amount = _f(ev.get("tokenAmount"))
    if v_sol > 0 and v_tok > 0:
        price_sol = v_sol / v_tok
    elif sol_amount > 0 and tok_amount > 0:
        price_sol = sol_amount / tok_amount
    else:
        return None
    price_usd = price_sol * SOL_USD_DEFAULT
    if price_usd <= 0:
        return None
    return TradeTick(
        mint=mint,
        ts=time.time(),                       # PumpPortal pushes live; receive time == trade time
        price_usd=price_usd,
        usd=sol_amount * SOL_USD_DEFAULT,
        side=side,
        venue=ev.get("pool") or "pumpfun",
        user=ev.get("traderPublicKey"),
    )


class PumpPortalProvider:
    """DataProvider over PumpPortal's keyed trade websocket. name/healthy/stream_ticks/recent_bars."""

    name = "pumpportal"

    def __init__(self) -> None:
        self._key = (read_env("LIGHTNING_API") or "").strip()

    def healthy(self) -> bool:
        """Streamable only with a funded api-key (subscribeTokenTrade is gated behind one)."""
        return bool(self._key)

    def _url(self) -> str:
        return DATA_WS_URL + ("?api-key=" + self._key if self._key else "")

    def stream_ticks(self) -> Iterator[TradeTick]:
        """Yield live pump.fun trade ticks. Tracks freshly-created mints and subscribes to their trades;
        the sniper's surge detector then fires on whichever tracked mint pumps. Bounded to the most
        recent _MAX_TRACKED mints (oldest unsubscribed) so subscription state never grows without limit.
        """
        if not self._key:
            raise RuntimeError("PumpPortalProvider needs LIGHTNING_API (funded api-key) to stream trades")
        tracked: "OrderedDict[str, float]" = OrderedDict()   # mint -> first_seen (insertion order == age)
        with connect(self._url(), open_timeout=20, max_size=None) as ws:
            ws.send(json.dumps({"method": "subscribeNewToken"}))
            while True:
                try:
                    raw = ws.recv(timeout=_RECV_TIMEOUT_S)
                except TimeoutError:
                    continue
                try:
                    ev = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    continue
                if not isinstance(ev, dict):
                    continue

                tx = ev.get("txType")
                if tx == "create" and ev.get("mint"):
                    mint = ev["mint"]
                    if mint not in tracked:
                        tracked[mint] = time.time()
                        ws.send(json.dumps({"method": "subscribeTokenTrade", "keys": [mint]}))
                        # evict oldest beyond the cap so subscription state stays bounded
                        while len(tracked) > _MAX_TRACKED:
                            old, _ = tracked.popitem(last=False)
                            try:
                                ws.send(json.dumps({"method": "unsubscribeTokenTrade", "keys": [old]}))
                            except Exception:  # noqa: BLE001 -- best-effort unsubscribe
                                pass
                    continue

                if tx in ("buy", "sell"):
                    tick = _trade_to_tick(ev)
                    if tick is not None:
                        yield tick

    def recent_bars(self, mint: str, lookback_s: int = 300) -> list:
        """Not served by the push stream; the sniper builds bars from stream_ticks. Empty by design."""
        return []
