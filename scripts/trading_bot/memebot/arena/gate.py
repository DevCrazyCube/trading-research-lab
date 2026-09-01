#!/usr/bin/env python3
"""MEME ARENA — the exitability gate, two honestly-labelled tiers.

- tier1_proxy_pass: the FREE count-based deadness proxy (memebot/screen.py + the virality_probe SPEC). It
  is a PROXY, not the validated B20B screen — its floors are buy/sell TRANSACTION counts, not unique
  wallets, so it is labelled as such and never reported as B20B's 77.7%/69.7% numbers.
- tier2 exact B20B (largest wallet >=0.95 of net tokens bought at t0+60) runs OFFLINE against
  b11a_bodies.sqlite; it is the ex-post audit / the V3 live gate, NOT on today's live decision path.

Each arm records which tier it entered on in the ledger.
"""
from __future__ import annotations

from .. import screen
from ..virality_probe import SPEC


def tier1_proxy_pass(coin: dict) -> bool:
    """Free count-based deadness proxy. `coin` carries reserve_usd/fdv_usd/age_minutes/buys/sells/dex."""
    c = dict(coin, buyers=coin.get("buys"), sellers=coin.get("sells"))
    try:
        return screen.screen_coin(c, {"screen": SPEC}).get("verdict") == "PASS"
    except Exception:  # noqa: BLE001 — a screen error is a non-pass, never a crash on the live path
        return False
