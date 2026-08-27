#!/usr/bin/env python3
"""ChainstackProvider — the PRIMARY real-time source (PAPER / READ-ONLY).

Chainstack serves a dedicated, unmetered Solana node via SOLANA_RPC_URL (JSON-RPC) and SOLANA_WS_URL
(WebSocket) in .env. As of 2026-08-26 the plan is ACTIVE (getHealth -> "ok").

Live trade stream (the unblock): `stream_ticks()` opens the WS and `logsSubscribe`s to the pump.fun
bonding-curve program, then decodes each notified transaction's `Program data:` log line into a
pump.fun `TradeEvent` — mint, SOL/token amounts, buy/sell side, virtual reserves — with NO per-tx
getTransaction round-trip (lowest latency; proven sub-second on the live feed). The decode +
reserve-ratio price derivation live in `_common.py` and mirror the repo's existing pump.fun handling
(scripts/b9d_transaction_bodies.py's TradeEvent layout; sources.py's reserve pricing).

Runner note: the WS client is the SYNCHRONOUS `websockets.sync.client` API. The system Python has no
`websockets`; run the runner under the memestream venv:
    scripts/trading_bot/memestream/.venv/bin/python   (websockets 17.x)

READ-ONLY: this subscribes and decodes only. It never signs, never sends, never loads a wallet/key.
`stream_grpc()` marks the seam where a Yellowstone gRPC (Geyser) feed attaches on a plan upgrade.
"""
from __future__ import annotations

import json
import time
from collections import defaultdict, deque
from typing import Iterator, Optional

from ._common import (
    PUMP_PROGRAM,
    RefusedError,
    SOL_USD_DEFAULT,
    TradeTick,
    decode_pump_trades_from_logs,
    load_cached_bars,
    read_env,
    rpc_call,
    trades_to_bars,
)


class ChainstackProvider:
    """Live pump.fun trade feed over the Chainstack Solana WS, with RPC health probing."""

    name = "chainstack"

    def __init__(self, rpc_url: Optional[str] = None, ws_url: Optional[str] = None,
                 sol_usd: float = SOL_USD_DEFAULT, buffer_secs: int = 900,
                 commitment: str = "processed"):
        # Read endpoints from .env WITHOUT printing them — the URL carries the API key in its path.
        self._rpc_url = rpc_url or read_env("SOLANA_RPC_URL")
        self._ws_url = ws_url or read_env("SOLANA_WS_URL")
        self.sol_usd = sol_usd
        self._commitment = commitment
        self._buffer_secs = buffer_secs
        # Rolling per-mint tick buffer, fed by stream_ticks(), read by recent_bars().
        self._ticks: dict[str, deque] = defaultdict(deque)
        self._last_ts: float = 0.0

    # -- health -------------------------------------------------------------------------------
    def healthy(self) -> bool:
        """True iff getHealth returns "ok". Any 403 / plan-inactive / transport fault -> False, so
        the runner falls back to the next provider without crashing."""
        if not self._rpc_url:
            return False
        try:
            return rpc_call(self._rpc_url, "getHealth", timeout=8) == "ok"
        except Exception:
            return False

    # -- live stream --------------------------------------------------------------------------
    def stream_ticks(self, programs: Optional[list[str]] = None) -> Iterator[TradeTick]:
        """Yield live TradeTicks decoded from the pump.fun program's WS log stream, in arrival order.

        Opens SOLANA_WS_URL, subscribes to logsNotification mentioning the pump.fun program, and for
        every notified transaction decodes its TradeEvent log line(s). Ticks are also appended to the
        per-mint rolling buffer so recent_bars() can serve them. Runs until the caller stops pulling
        or the socket drops (a drop raises; the runner may re-open).
        """
        if not self._ws_url:
            raise RefusedError("ChainstackProvider: SOLANA_WS_URL is not set in .env")
        try:
            from websockets.sync.client import connect
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise RefusedError(
                "ChainstackProvider.stream_ticks needs the `websockets` package; run under "
                "scripts/trading_bot/memestream/.venv/bin/python") from exc

        mentions = programs or [PUMP_PROGRAM]
        sub = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "logsSubscribe",
                          "params": [{"mentions": mentions}, {"commitment": self._commitment}]})
        with connect(self._ws_url, open_timeout=20, max_size=None) as ws:
            ws.send(sub)
            ws.recv(timeout=20)  # subscription id ack
            while True:
                try:
                    raw = ws.recv(timeout=30)
                except TimeoutError:
                    continue
                try:
                    msg = json.loads(raw)
                except (ValueError, TypeError):
                    continue
                if msg.get("method") != "logsNotification":
                    continue
                value = (((msg.get("params") or {}).get("result") or {}).get("value")) or {}
                if value.get("err") is not None:  # failed tx — no real trade happened
                    continue
                logs = value.get("logs") or []
                recv_ts = time.time()
                for ev in decode_pump_trades_from_logs(logs, self.sol_usd):
                    # The TradeEvent timestamp is block time; stamp with receive time for a monotonic
                    # live clock (block time can lag / repeat within a slot).
                    tick = TradeTick(mint=ev["mint"], ts=recv_ts, price_usd=ev["price_usd"],
                                     usd=ev["usd"], side=ev["side"], venue=ev["venue"],
                                     user=ev.get("user"))
                    self._buffer(tick)
                    yield tick

    def _buffer(self, tick: TradeTick) -> None:
        dq = self._ticks[tick.mint]
        dq.append(tick)
        self._last_ts = max(self._last_ts, tick.ts)
        horizon = self._last_ts - self._buffer_secs
        while dq and dq[0].ts < horizon:
            dq.popleft()

    # -- recent bars --------------------------------------------------------------------------
    def recent_bars(self, mint: str, lookback_s: int = 300) -> list:
        """1s bars for a mint from the live tick buffer (the stream is the source of truth). If the
        buffer is cold for this mint, fall back to the on-disk memebot_cache candles."""
        dq = self._ticks.get(mint)
        if dq:
            now = self._last_ts or time.time()
            floor = now - lookback_s
            trades = [{"ts": t.ts, "price_usd": t.price_usd, "usd": t.usd, "side": t.side}
                      for t in dq if t.ts >= floor]
            bars = trades_to_bars(trades)
            if bars:
                return bars
        # Cold buffer -> disk cache (thin, but keeps the stack running before the stream warms up).
        cached = load_cached_bars(mint)
        if not cached:
            return []
        cutoff = cached[-1].t - lookback_s
        return [b for b in cached if b.t >= cutoff]

    # -- upgrade seam -------------------------------------------------------------------------
    def stream_grpc(self, *_args, **_kwargs):
        """STUB — Yellowstone gRPC (Geyser) attach point for when the plan is upgraded.

        A Yellowstone endpoint pushes decoded account/transaction updates over gRPC with lower
        latency and no log-parsing than logsSubscribe. When available it replaces the WS body of
        stream_ticks() while yielding the SAME TradeTick objects, so no downstream module changes.
        Not implemented now: the current plan exposes JSON-RPC + WS only, and the WS path above is
        live and sufficient. Read-only when built — subscribe/decode only, never sign/send.
        """
        raise NotImplementedError(
            "Yellowstone gRPC path not wired: current Chainstack plan is JSON-RPC + WS only. Use "
            "stream_ticks() (WS logsSubscribe). This stub marks where a Geyser feed attaches.")
