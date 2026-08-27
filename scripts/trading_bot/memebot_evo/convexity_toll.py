#!/usr/bin/env python3
"""REALISTIC PER-VENUE TOLL + SLIPPAGE MODEL -- follow-up cost re-scoring of the convexity probe.

PAPER ONLY. No orders, no wallet, no money, no git-commit. Frozen memebot + dashboard untouched.
This module does NOT import or mutate engine.py / evo_paper.py / genome.py. It reuses convexity_probe's
policy-B walker + momentum entries UNCHANGED and only replaces the flat pinned 3% toll with a venue-
aware toll + a liquidity-scaled slippage curve, so this is a clean COST RE-SCORING, not a new strategy.

-----------------------------------------------------------------------------------------------------
WHY A PROXY (honesty on the venue label)
-----------------------------------------------------------------------------------------------------
The Bitquery ingester (memestream/bitquery_ingest.py) subscribed ONLY to ProtocolFamily in
["Pumpfun","Pumpswap"], so every trade in the on-disk cache is from exactly one of two venues:
    - Pumpfun  = the pump.fun BONDING CURVE   (EXPENSIVE: ~1%/side protocol fee, thin, high impact)
    - Pumpswap = the migrated constant-product AMM (CHEAP: swappable via Jupiter at ~0.25-0.4%/side)
The ingester's _flatten() DID read Trade.Dex.ProtocolName, BUT the 1s Aggregator DROPPED it: the
persisted candle is only {t,o,h,l,c,v,buys,sells,buy_vol,sell_vol}. So the per-candle venue LABEL is
NOT recoverable from the cache (grep '"dex"' over all 1076 files == 0 hits). Nor is the mint suffix a
migration signal: 881/1076 mints end in "pump" (a pump.fun CREATION vanity), which says nothing about
whether the coin has since MIGRATED to the Pumpswap AMM.

Therefore, exactly as the task's fallback instructs, we classify venue from a LIQUIDITY PROXY:
    liq_usd_per_s = (total USD volume over the entry window) / (window span seconds)
already computed by convexity_probe.momentum_entry_qualifies and stored per entry. A migrated Pumpswap
pool sustains far higher USD throughput and two-sided flow than a bonding-curve microcap, so a
throughput floor is a defensible (if imperfect) migration/tradeability proxy. It is a FLOW proxy, not a
pool-depth measurement -- it can be fooled by a burst of wash prints and says nothing about the bid
stack. It is the best signal the free feed left us. Entries above LIQ_SPLIT USD/s are treated as
CHEAP/liquid (Jupiter-tradeable AMM); below, as EXPENSIVE bonding-curve microcaps.

-----------------------------------------------------------------------------------------------------
COST MODEL (pessimistic, venue-appropriate, NOT weakened to force a positive)
-----------------------------------------------------------------------------------------------------
Per side:
    toll (fee)  = CHEAP 0.35% / EXPENSIVE 1.00%
                  CHEAP  = Jupiter swap on a migrated AMM: ~0.25% pool fee + ~0.10% aggregator/route/
                           priority overhead.  EXPENSIVE = pump.fun bonding-curve 1%/side protocol fee.
    slippage    = min(CAP, FLOOR + COEF / liq_usd_per_s) bps, i.e. an INVERSE-THROUGHPUT curve:
                  a liquid pool (high USD/s) slips near the FLOOR; a thin coin slips toward the CAP.
                  FLOOR=25 bps, CAP=300 bps, COEF=1125  ->  at the liq gate 5 USD/s slip=250 bps/side;
                  20 USD/s ->81; 50 ->48; 100 ->36; 500 ->27 bps. Slippage is charged on BOTH sides and
                  is NEVER zeroed even for the most liquid coin (floor 25 bps/side).

Net return per trade (symmetric, both-sides slippage, fees additive -- the probe's convention):
    net = gross_mult * (1 - s)/(1 + s) - 1 - (toll_in + toll_out)
where gross_mult = exit_px/entry_px is the RAW price path from the UNCHANGED policy-B walker (obtained
by walking with cost pinned to zero: policy B's exit BAR is chosen by flow logic + max_hold only, never
by toll/slip, so the raw path is identical to the frozen probe's).
"""
from __future__ import annotations

from dataclasses import dataclass

# ---- Per-venue base toll (fee) per side ----------------------------------------------------------
TOLL_CHEAP_SIDE = 0.0035     # migrated AMM via Jupiter: ~0.25% pool fee + ~0.10% route/priority
TOLL_EXPENSIVE_SIDE = 0.0100  # pump.fun bonding curve: 1%/side protocol fee

# ---- Liquidity-scaled slippage curve (bps per side) ----------------------------------------------
SLIP_FLOOR_BPS = 25.0        # even the most liquid coin here is not a blue-chip pair
SLIP_CAP_BPS = 300.0         # pessimistic ceiling for the thinnest coin that still clears the gate
SLIP_COEF = 1125.0           # inverse-throughput coefficient (see docstring for the calibration grid)


def classify_venue(liq_usd_per_s: float, split: float) -> str:
    """CHEAP (migrated/liquid, Jupiter-tradeable) if throughput >= split, else EXPENSIVE bonding-curve."""
    return "CHEAP" if (liq_usd_per_s is not None and liq_usd_per_s >= split) else "EXPENSIVE"


def toll_side(venue: str) -> float:
    return TOLL_CHEAP_SIDE if venue == "CHEAP" else TOLL_EXPENSIVE_SIDE


def slippage_bps_side(liq_usd_per_s: float | None) -> float:
    """Inverse-throughput slippage, one side, in bps. Floored and capped; never zero."""
    if not liq_usd_per_s or liq_usd_per_s <= 0:
        return SLIP_CAP_BPS
    return min(SLIP_CAP_BPS, SLIP_FLOOR_BPS + SLIP_COEF / liq_usd_per_s)


@dataclass
class Cost:
    venue: str
    toll_side: float
    slip_bps_side: float

    @property
    def slip_frac(self) -> float:
        return self.slip_bps_side / 1e4

    @property
    def round_trip_toll(self) -> float:
        return 2.0 * self.toll_side

    @property
    def round_trip_slip_bps(self) -> float:
        return 2.0 * self.slip_bps_side


def cost_for(liq_usd_per_s: float | None, split: float) -> Cost:
    venue = classify_venue(liq_usd_per_s, split)
    return Cost(venue=venue, toll_side=toll_side(venue),
                slip_bps_side=slippage_bps_side(liq_usd_per_s))


def net_return(gross_mult: float, cost: Cost) -> float:
    """Realistic net return per trade. Slippage on BOTH sides (multiplicative), fees additive."""
    s = cost.slip_frac
    return gross_mult * (1.0 - s) / (1.0 + s) - 1.0 - cost.round_trip_toll
