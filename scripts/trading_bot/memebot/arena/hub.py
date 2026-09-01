#!/usr/bin/env python3
"""MEME ARENA — the shared feed hub. ONE feed pull per cycle, cached, handed to every arm so N arms cost
one network budget, not N. ARM 1 (virality_arrival, snapshot basis) reuses the proven virality_tracker
feed (DexScreener attention universe + identity-pinned pairs); ARM 2/3 add the PumpPortal create/trade
tape + migration lane (Codex / owner-gated). Read-only; the network chokepoint stays memebot/net.py.
"""
from __future__ import annotations

import hashlib
import json
import time

from .. import virality_tracker as VT   # proven feed: _universe, _deepest_pair, _pinned_pair, _shape


class Hub:
    """Per-cycle feed snapshot. `pairs` maps mint -> normalized pair dict (price, reserves, m5 flow, age)."""

    def __init__(self):
        self._pinned: dict[str, str] = {}     # mint -> chosen pair address (identity pin)

    def snapshot(self) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for mint in VT._universe():
            pair_addr = self._pinned.get(mint)
            c = VT._pinned_pair(pair_addr) if pair_addr else VT._deepest_pair(mint)
            if c is None or not c.get("pair") or not c.get("price") or c["price"] <= 0:
                continue
            self._pinned[mint] = c["pair"]     # pin identity on first sight
            observed = time.time_ns()
            body = dict(c)
            body["observed_unix_nanos"] = observed
            body["normalized_evidence_sha256"] = hashlib.sha256(json.dumps(
                c, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
            out[mint] = body
        return out

    def refresh_pair(self, pair_addr: str) -> dict | None:
        """Re-fetch one pinned pair (used to mark an open position on its own market)."""
        c = VT._pinned_pair(pair_addr)
        if c is None:
            return None
        c = dict(c)
        c["observed_unix_nanos"] = time.time_ns()
        c["normalized_evidence_sha256"] = hashlib.sha256(json.dumps(
            {k: v for k, v in c.items() if k not in {"observed_unix_nanos", "normalized_evidence_sha256"}},
            sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
        return c
