#!/usr/bin/env python3
"""MEME ARENA — ARM 1: VIRALITY_ARRIVAL_V2_1 (snapshot basis, free data, ships today).

Enters exitable, past-t0 coins on buyer-breadth acceleration (m5 buy-rate up >=40% on the pinned pair,
net demand, confirming price rise), tier-1-gated, convex exit. It is an OPTIMISTIC-BOUND cheap filter:
fills at the observed snapshot with a multiplicative two-leg toll (arena/fill honest_fill_snapshot). A
KILL is decisive; a PASS earns only a stricter causal test, never a money claim. The known mirage (F6):
the DexScreener boosted universe is PAID promotion, so the m5 acceleration may LAG the true arrival — the
runtime logs time-since-first-seen so the decision can detect a lagging-exhaustion signature.

Supersedes virality_tracker V2 by plugging into the shared honesty spine (one exit engine, one fill, one
hash-chained ledger, one cluster-bootstrap scorer) instead of its own bespoke loop.
"""
from __future__ import annotations

import hashlib
import pathlib

from ..arm import Arm

MIN_AGE_MIN = 60
M5_BUYS_FLOOR = 10
BREADTH_INFLECT_MIN = 0.40
_SPEC = {"MIN_AGE_MIN": MIN_AGE_MIN, "M5_BUYS_FLOOR": M5_BUYS_FLOOR,
         "BREADTH_INFLECT_MIN": BREADTH_INFLECT_MIN, "fill_basis": "snapshot"}
PREREG = pathlib.Path(__file__).resolve().parents[1] / "arms" / "VIRALITY_ARRIVAL_PREREGISTRATION.md"


def _sha_str(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


class ViralityArrival(Arm):
    instrument = "VIRALITY_ARRIVAL_V2_1"
    fill_basis = "snapshot"
    target_n = 120
    extended_cap = 200

    def code_sha256(self) -> str:
        return hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest()

    def prereg_sha256(self) -> str:
        try:
            return hashlib.sha256(PREREG.read_bytes()).hexdigest()
        except OSError:
            return ""

    def spec_sha256(self) -> str:
        return _sha_str(repr(sorted(_SPEC.items())))

    def candidates(self, feed: dict) -> list[dict]:
        return [dict(c, mint=m) for m, c in feed.items()]

    def entry_ok(self, c: dict, history: list[dict]) -> bool:
        from .. import gate
        if (c.get("age_minutes") or 0) < MIN_AGE_MIN or not history:
            return False
        prev = history[-1]
        pb = prev.get("m5_buys", 0)
        if pb <= 0:
            return False
        accel = c.get("m5_buys", 0) >= M5_BUYS_FLOOR and (c["m5_buys"] - pb) / pb >= BREADTH_INFLECT_MIN
        net_demand = c.get("m5_buys", 0) > c.get("m5_sells", 0)
        price_up = c.get("price", 0) > prev.get("price", 0)
        return bool(accel and net_demand and price_up and gate.tier1_proxy_pass(c))


ARM = ViralityArrival()


if __name__ == "__main__":
    a = ViralityArrival()
    assert a.instrument == "VIRALITY_ARRIVAL_V2_1" and a.fill_basis == "snapshot"
    assert len(a.code_sha256()) == 64 and len(a.spec_sha256()) == 64
    # entry predicate: needs accel + net demand + price up (gate is checked last; use a passing-ish coin)
    hist = [{"m5_buys": 10, "price": 1.0}]
    cand = {"mint": "m", "age_minutes": 120, "m5_buys": 20, "m5_sells": 5, "price": 1.1,
            "reserve_usd": 50000, "fdv_usd": 100000, "buys": 200, "sells": 120, "dex": "raydium"}
    # accel 100% >= 40, net demand, price up -> predicate short-circuits to the gate; just assert no crash
    _ = a.entry_ok(cand, hist)
    assert a.entry_ok({"age_minutes": 10}, hist) is False   # too young
    assert a.entry_ok(cand, []) is False                    # no history
    print("virality_arrival.py self-check OK")
