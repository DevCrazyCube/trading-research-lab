#!/usr/bin/env python3
"""MEME ARENA — the convex-exit + resolution engine. ONE exit rule for every arm, and the F1 invariant:
NOTHING opened escapes resolution. A rug / unpriced / dead coin resolves as a total loss (never silently
dropped, never left stuck-open — a stuck-open count > 0 invalidates the read). The exit decision is made
on observed MARKS; the realized number is always priced through fill.py (snapshot or causal_cp basis).
Pure logic; no I/O.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from . import fill as F

HARD_STOP = 0.12          # -12% all-cost hard stop
HORIZON_S = 12 * 3600     # 12h horizon
# widening trail: the wider the peak, the looser the give-back allowed (let winners run)
TRAIL_TIERS = ((0.5, 0.18), (1.5, 0.25), (math.inf, 0.35))


@dataclass
class Position:
    mint: str
    arm: str
    basis: str                       # "snapshot" | "causal_cp"
    entry_price: float               # marginal/observed mark at entry (for exit-trigger math)
    opened_ts: float
    peak: float = 0.0
    size_sol: float = 0.5            # causal_cp only
    entry_reserves: tuple | None = None   # (v_sol, v_tokens) at entry (causal_cp only)
    meta: dict = field(default_factory=dict)

    def __post_init__(self):
        self.peak = max(self.peak, self.entry_price)


def _trail_for(peak_gain: float) -> float:
    for thr, give in TRAIL_TIERS:
        if peak_gain < thr:
            return give
    return TRAIL_TIERS[-1][1]


def exit_signal(pos: Position, mark: float, now_ts: float) -> str | None:
    """Exit reason on the observed mark, or None to hold. Marks drive the trigger; fill.py prices it."""
    if mark is not None and mark > 0:
        pos.peak = max(pos.peak, mark)
        gain = mark / pos.entry_price - 1.0
        peak_gain = pos.peak / pos.entry_price - 1.0
        if gain <= -HARD_STOP:
            return "HARD_STOP"
        if peak_gain >= 0.12 and mark <= pos.peak * (1.0 - _trail_for(peak_gain)):
            return "TRAIL"
    if now_ts - pos.opened_ts > HORIZON_S:
        return "HORIZON"
    return None


def resolve(pos: Position, reason: str, *, exit_mark: float | None = None,
            exit_reserves: tuple | None = None, real_sol_withdrawable: float | None = None,
            latency_s: float = 0.9, now_ts: float | None = None) -> dict:
    """Resolve a position through fill.py. F1: a RUG_UNPRICED / dead resolution is a total loss, never a
    skip. Returns the ledger row (kind added by the ledger)."""
    if pos.basis == "snapshot":
        # a rug / unpriced exit prices at 0 -> honest total loss
        ep = exit_mark if (reason != "RUG_UNPRICED" and exit_mark and exit_mark > 0) else 0.0
        fr = F.honest_fill_snapshot(pos.entry_price, ep) if ep > 0 else \
            F.FillResult("snapshot", pos.entry_price, 0.0, -1.0, -1.0, None, False, 0.0,
                         {"note": "RUG_UNPRICED total loss"})
    else:
        if reason == "RUG_UNPRICED" or exit_reserves is None:
            fr = F.FillResult("causal_cp", pos.entry_price, 0.0, -1.0, -1.0, None, True, latency_s,
                              {"note": "RUG_UNPRICED / unreadable reserves — total loss"})
        else:
            fr = F.causal_fill_cp(pos.entry_reserves, exit_reserves, pos.size_sol, latency_s=latency_s,
                                  real_sol_withdrawable_at_exit=real_sol_withdrawable)
    return {
        "mint": pos.mint, "arm": pos.arm, "reason": reason, "basis": fr.basis,
        "entry_price": pos.entry_price, "exit_price": fr.exit_price,
        "gross_return": round(fr.gross_return, 6), "net_return": round(fr.net_return, 6),
        "net_marginal": (round(fr.net_marginal, 6) if fr.net_marginal is not None else None),
        "real_reserve_bound_hit": fr.real_reserve_bound_hit,
        "held_s": int((now_ts or pos.opened_ts) - pos.opened_ts),
        "decomposition": fr.decomposition,
    }


if __name__ == "__main__":
    # winner: peaks then gives back the trail -> TRAIL exit, positive net
    p = Position("m", "arm", "snapshot", entry_price=1.0, opened_ts=0.0)
    assert exit_signal(p, 1.3, 60) is None            # rising, hold
    r = None
    for mark, t in [(1.4, 120), (1.4 * 0.80, 180)]:   # peak 1.4 (gain .4 -> 0.18 tier) then -20% give-back
        r = exit_signal(p, mark, t)
        if r:
            break
    assert r == "TRAIL", r
    row = resolve(p, r, exit_mark=1.4 * 0.80, now_ts=180)
    assert row["net_return"] > 0 and row["reason"] == "TRAIL"
    # rug: unpriced -> F1 total loss
    p2 = Position("m2", "arm", "snapshot", entry_price=1.0, opened_ts=0.0)
    rug = resolve(p2, "RUG_UNPRICED", now_ts=100)
    assert abs(rug["net_return"] + 1.0) < 1e-9, "rug must be a total loss"
    # hard stop
    p3 = Position("m3", "arm", "snapshot", entry_price=1.0, opened_ts=0.0)
    assert exit_signal(p3, 0.85, 60) == "HARD_STOP"
    # causal rug (unreadable reserves) also total loss
    p4 = Position("m4", "arm", "causal_cp", entry_price=1.0, opened_ts=0.0, entry_reserves=(30.0, 1e9))
    assert abs(resolve(p4, "RUG_UNPRICED", now_ts=1)["net_return"] + 1.0) < 1e-9
    print("exit_engine.py self-check OK: trail winner, hard-stop, F1 rug=total-loss (both bases)")
