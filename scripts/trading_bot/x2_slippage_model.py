#!/usr/bin/env python3
"""X2_FLOWSTREAK slippage model + decision logic — the frozen-prereg pieces, isolated and testable.

This module implements ONLY what the pre-registration
(`research/trading_bot/X2_FLOWSTREAK_SLIPPAGE_PREREGISTRATION.md`) fixes: the ±1%-band slippage model, the
per-side all-in cost, the capacity aggregation, and the SIZE/KILL rule. It contains no data access and no
signal logic, so it can be unit-tested without the panel or the depth cache. The harness imports these.
"""
from __future__ import annotations

import math

BREAKEVEN_BP = 17.9          # from FORMULA_SWEEP_MASTER.md:139 (X2_FLOWSTREAK virgin)
TAKER_FEE_BP = 5.0           # Binance USD-M taker ~4.5 bp, rounded up
AUM_GRID = (100_000, 250_000, 500_000, 1_000_000, 2_500_000, 5_000_000)
AUM_MIN = 100_000
AUM_TARGET = 250_000
CORR_MAX = 0.70              # corr(L5,L6) gate; a sized leg cannot duplicate L5


def slippage_bp(trade_notional: float, band_notional_1pct: float) -> float:
    """Per-side modeled slippage from the ±1% book notional, uniform-density walk (prereg §Slippage model).

    Fill of `trade_notional` against depth `band_notional_1pct` available within 100 bp of mid; the mean
    fill price under uniform density is half-way into the consumed fraction. Exhausting the ±1% band is
    treated as >= 100 bp (a hard, deliberately pessimistic cap)."""
    if band_notional_1pct is None or band_notional_1pct <= 0 or trade_notional <= 0:
        return 100.0
    frac = trade_notional / band_notional_1pct
    if frac >= 1.0:
        return 100.0
    return 100.0 * frac * 0.5


def per_side_cost_bp(trade_notional: float, band_notional_1pct: float, half_spread_bp: float) -> float:
    """All-in per-side cost = modeled slippage + taker fee + half the observed bid/ask spread."""
    return slippage_bp(trade_notional, band_notional_1pct) + TAKER_FEE_BP + max(0.0, half_spread_bp or 0.0)


def recharge_net_returns(gross_returns, per_side_costs_bp) -> tuple[float, float, int]:
    """Given per-rebalance gross returns (fraction) and the per-rebalance TWO-SIDED cost (bp, entry+exit),
    return (mean_net_R, t_stat, n). Cost in bp is converted to a return fraction (bp/1e4)."""
    nets = [g - (c / 1e4) for g, c in zip(gross_returns, per_side_costs_bp)]
    n = len(nets)
    if n == 0:
        return 0.0, 0.0, 0
    mean = sum(nets) / n
    if n < 2:
        return mean, 0.0, n
    var = sum((x - mean) ** 2 for x in nets) / (n - 1)
    se = math.sqrt(var / n) if var > 0 else 0.0
    return mean, (mean / se if se > 0 else 0.0), n


def verdict(capacity_curve: list[dict], corr_l5_l6: float | None, is_poc: bool) -> tuple[str, float | None, str]:
    """Apply the frozen decision rule. Returns (verdict, max_tradeable_aum, note).

    KILL if cost@AUM_min >= breakeven, or net<0 at AUM_min. SIZE if net>0 (t>2) at AUM_TARGET and corr gate
    passes. SIZE-DOWN to the largest AUM meeting the net>0/t>2 conditions if it holds at AUM_min but not
    target. A PoC (design window) never emits a real SIZE — it is labelled POC and reports capacity only."""
    by_aum = {c["aum_usd"]: c for c in capacity_curve}
    at_min = by_aum.get(AUM_MIN)
    tradeable = [c["aum_usd"] for c in capacity_curve
                 if (c.get("net_mean_R") or 0) > 0 and (c.get("t") or 0) > 2]
    max_tradeable = max(tradeable) if tradeable else None

    if at_min is None:
        return ("PENDING", max_tradeable, "no cost at AUM_min")
    if (at_min.get("cost_bp_per_side") or 1e9) >= BREAKEVEN_BP or (at_min.get("net_mean_R") or 0) <= 0:
        return ("KILL", max_tradeable,
                "even the smallest tradeable book ($100k) does not clear the 17.9 bp breakeven")
    if is_poc:
        return ("POC", max_tradeable,
                "design-window method check passed; the frozen SIZE/KILL verdict runs on held-out 2025-2026")
    corr_ok = corr_l5_l6 is not None and corr_l5_l6 < CORR_MAX
    at_target = by_aum.get(AUM_TARGET)
    target_ok = at_target and (at_target.get("net_mean_R") or 0) > 0 and (at_target.get("t") or 0) > 2
    if target_ok and corr_ok:
        return ("SIZE", max_tradeable, f"net>0 (t>2) at ${AUM_TARGET:,} and corr(L5,L6)<{CORR_MAX}")
    if max_tradeable and max_tradeable >= AUM_MIN:
        reason = "clears at a smaller book than target" if not target_ok else \
                 f"corr(L5,L6) gate ({corr_l5_l6}) not passed"
        return ("SIZE-DOWN", max_tradeable, f"size to ${max_tradeable:,} — {reason}")
    return ("KILL", max_tradeable, "no AUM clears the net>0/t>2 conditions")


if __name__ == "__main__":
    # self-test the model math (no data needed)
    assert abs(slippage_bp(1000, 100000) - 0.5) < 1e-9, "1% of band -> 0.5 bp"
    assert slippage_bp(200000, 100000) == 100.0, "exhausting band -> 100 bp cap"
    assert slippage_bp(50000, 100000) == 25.0, "half the band -> 25 bp"
    assert per_side_cost_bp(1000, 100000, 1.0) == 0.5 + 5.0 + 1.0
    m, t, n = recharge_net_returns([0.01, 0.02, 0.015], [10, 10, 10])  # 10bp two-sided
    assert n == 3 and abs(m - (0.015 - 0.001)) < 1e-9
    v, mx, note = verdict([{"aum_usd": 100000, "cost_bp_per_side": 25.0, "net_mean_R": -0.001, "t": -1}], None, False)
    assert v == "KILL", v
    v, mx, note = verdict([{"aum_usd": 100000, "cost_bp_per_side": 6.0, "net_mean_R": 0.002, "t": 3.0}], None, True)
    assert v == "POC", v
    print("x2_slippage_model self-test: OK")
