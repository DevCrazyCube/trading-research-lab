#!/usr/bin/env python3
"""DataProvider layer for the sniper paper stack (PAPER / READ-ONLY).

Exposes the four providers + a `pick_provider()` factory. ReplayProvider is always available for
offline testing; the live providers are tried in order of preference for real-time paper runs.

    from scripts.trading_bot.sniper.data import pick_provider, ReplayProvider
    provider = pick_provider()          # first healthy live provider, else Replay

None of these ever sign, send, load a wallet, or read a private key.
"""
from __future__ import annotations

from ._common import RefusedError
from .bitquery import BitqueryProvider
from .chainstack import ChainstackProvider
from .public_rpc import PublicRpcProvider
from .pumpportal import PumpPortalProvider
from .replay import ReplayProvider

__all__ = [
    "ChainstackProvider", "PumpPortalProvider", "PublicRpcProvider", "BitqueryProvider",
    "ReplayProvider", "RefusedError", "pick_provider", "LIVE_PROVIDER_ORDER",
]

# Preference order for a live real-time run. Chainstack is the dedicated WS feed but is on a MONTHLY
# quota (dead on 403 when spent). PublicRpc (free, keyless) is next and is the sniper's ACTIVE feed
# while Chainstack is spent. PumpPortal is placed AFTER it on purpose: PumpPortal limits connections
# per api-key, and the LIGHTNING_API key is already held by the dashboard candle ingester
# (memestream.pumpportal_ingest) — a second consumer on the same key starves. So PumpPortal is only a
# last resort here, to avoid contending with the candle feed. Bitquery has no live stream (pull-only).
LIVE_PROVIDER_ORDER = (ChainstackProvider, PublicRpcProvider, PumpPortalProvider, BitqueryProvider)


def pick_provider(prefer_replay: bool = False, allow_replay_fallback: bool = True):
    """Return the first HEALTHY provider to use.

    - prefer_replay=True            -> always the offline ReplayProvider (default for paper tests).
    - otherwise try LIVE_PROVIDER_ORDER; return the first whose healthy() is True.
    - if none are healthy and allow_replay_fallback, return ReplayProvider (offline).
    - if none are healthy and fallback is disabled, raise RefusedError.
    """
    if prefer_replay:
        return ReplayProvider()
    for cls in LIVE_PROVIDER_ORDER:
        try:
            provider = cls()
            if provider.healthy():
                return provider
        except Exception:
            continue
    if allow_replay_fallback:
        return ReplayProvider()
    raise RefusedError("no healthy live DataProvider and replay fallback disabled")
