#!/usr/bin/env python3
"""PublicRpcProvider — the free api.mainnet-beta.solana.com fallback (dev/testing, READ-ONLY).

The public RPC is heavily rate-limited and offers no cheap trade push, so this provider is a
health-probing fallback only: `healthy()` does a real getHealth, and — when it also has a live WS
URL — it can stream pump.fun trades exactly like ChainstackProvider (same shared decoder). Its
`recent_bars` is deliberately thin (see below). It exists so the runner still has a live seam when
Chainstack is down, and for local development. Nothing here signs, sends, or loads a wallet/key.

Throttling: calls are spaced by a conservative minimum interval (default 2s) to stay polite on the
free tier; a 429/403 flips `healthy()` to False rather than hammering.
"""
from __future__ import annotations

import time
from typing import Iterator, Optional

from . import chainstack as _chainstack
from ._common import RefusedError, SOL_USD_DEFAULT, load_cached_bars, read_env, rpc_call

PUBLIC_RPC_URL = "https://api.mainnet-beta.solana.com"
PUBLIC_WS_URL = "wss://api.mainnet-beta.solana.com"


class PublicRpcProvider:
    """Free public Solana RPC — rate-limited. Health probe + optional WS trade stream; thin bars."""

    name = "public_rpc"

    def __init__(self, rpc_url: str = PUBLIC_RPC_URL, ws_url: Optional[str] = PUBLIC_WS_URL,
                 sol_usd: float = SOL_USD_DEFAULT, min_interval_s: float = 2.0):
        self._rpc_url = rpc_url
        self._ws_url = ws_url
        self.sol_usd = sol_usd
        self._min_interval = min_interval_s
        self._last_call = 0.0
        # Reuse the Chainstack WS decode path verbatim (same pump.fun log decoder), pointed at the
        # public WS. Keeps one implementation of the live trade stream.
        self._ws_delegate = _chainstack.ChainstackProvider(
            rpc_url=rpc_url, ws_url=ws_url, sol_usd=sol_usd)

    def _throttle(self) -> None:
        wait = self._min_interval - (time.time() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.time()

    def healthy(self) -> bool:
        """getHealth on the free endpoint, throttled. Any 429/403/fault -> False."""
        self._throttle()
        try:
            return rpc_call(self._rpc_url, "getHealth", timeout=8) == "ok"
        except Exception:
            return False

    def stream_ticks(self) -> Iterator:
        """Stream pump.fun trades over the public WS (same decoder as Chainstack). The free WS is
        far less reliable than the dedicated node; prefer Chainstack when healthy."""
        if not self._ws_url:
            raise RefusedError("PublicRpcProvider: no WS URL configured")
        return self._ws_delegate.stream_ticks()

    def recent_bars(self, mint: str, lookback_s: int = 300) -> list:
        """Thin by design: the free RPC has no cheap 1s-bar endpoint and building bars from
        getSignaturesForAddress + getTransaction decode would blow the rate limit. If the WS
        delegate has buffered live ticks, use them; otherwise fall back to the on-disk cache."""
        bars = self._ws_delegate.recent_bars(mint, lookback_s)
        if bars:
            return bars
        cached = load_cached_bars(mint)
        if not cached:
            return []
        cutoff = cached[-1].t - lookback_s
        return [b for b in cached if b.t >= cutoff]
