#!/usr/bin/env python3
"""DRY-RUN Executor for the sniper paper stack.

PAPER / DRY-RUN ONLY. See ARCHITECTURE.md. This module turns an ``OrderIntent`` into a *simulated*
``Fill`` at a realistic price after slippage, venue toll, and an estimated priority tip. It NEVER
authorizes, broadcasts, or transmits a transaction; it NEVER loads a wallet or reads a secret; it makes
NO on-chain write. The only network it may touch is a READ-ONLY, free public price-quote endpoint used
solely to make the paper fill price more realistic (off by default, fails soft to the reference price).

The live submit path is a documented STUB (`_submit_real`) hard-gated behind ``ALLOW_REAL_ORDERS``
(imported from types.py, hard-coded False). It contains no wallet, no secret handling, and no transfer
logic — it exists only to mark where a future, human-gated, operator-wallet path would one day attach.
Nothing here can flip ``ALLOW_REAL_ORDERS``.
"""
from __future__ import annotations

import json
import math
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Optional

from .types import ALLOW_REAL_ORDERS, Fill, OrderIntent

# --------------------------------------------------------------------------------------------------
# Cost-model constants (all deliberately PESSIMISTIC — paper P&L should never be flattered).
# --------------------------------------------------------------------------------------------------

# Slippage is floored so a paper fill is never free, even on a huge, deep pool.
SLIP_FLOOR_BPS: float = 25.0

# Square-root market-impact coefficient (bps at a participation ratio of 1.0, i.e. when the order's
# notional equals ~one second of the pool's USD throughput). Memecoin pools are thin and reflexive, so
# this is set high. impact_bps = IMPACT_COEFF * sqrt(usd_size / liq_usd_per_s).
IMPACT_COEFF_BPS: float = 130.0

# Conservative default per-second USD throughput when the caller gives no liquidity hint. Low on
# purpose so an unknown-liquidity coin is modeled as expensive to trade.
DEFAULT_LIQ_USD_PER_S: float = 150.0

# Clamp so a near-zero liquidity hint cannot produce an infinite impact / NaN.
MIN_LIQ_USD_PER_S: float = 1.0

# Cap the modeled impact so a pathological size does not print an absurd fill (paper realism, not a
# promise the real book would honor it — we simply refuse to invent unbounded numbers).
MAX_SLIP_BPS: float = 5000.0

# --------------------------------------------------------------------------------------------------
# Venue toll mapping (per-SIDE bps). Documented rationale:
#   * Pumpfun  — bonding-curve venue. The curve itself levies ~1% per trade => ~100 bps/side.
#   * Pumpswap / migrated pools — routed like any Jupiter/AMM swap; LP + route fees ~25-40 bps/side.
#   * Unknown / other — treated as the expensive (bonding-curve) case, never the cheap one.
# These are the ~toll the strategy pins per venue; execution reports the per-side figure on the Fill.
# --------------------------------------------------------------------------------------------------
VENUE_TOLL_BPS: dict[str, float] = {
    "pumpfun": 125.0,      # bonding-curve — official pump.fun fee is 1.25%/trade (was understated at 100)
    "pump": 125.0,         # alias
    "bonk": 125.0,         # bonk-launchpad bonding-curve, same order of fee
    "pumpswap": 30.0,      # migrated AMM, Jupiter-routable
    "migrated": 30.0,      # alias
    "jupiter": 30.0,       # generic routed swap
    "raydium": 35.0,       # AMM route
    "amm": 35.0,           # generic AMM route
}
DEFAULT_TOLL_BPS: float = 100.0  # unknown venue => assume the expensive bonding-curve toll

# --------------------------------------------------------------------------------------------------
# Priority-tip estimate (paper context only). This is a MODEST inclusion fee, NOT a competitive
# block-0 auction bid. Our research found competitive real tips run 0.05-0.5 SOL and the tip auction
# surrenders 50-70% of the edge (why real block-0 sniping is -EV). We deliberately do NOT model a
# competitive tip here: this stack targets liquid follow-through, not the auction. The tip is reported
# on every V3 fill and the strategy charges it against net R.
# --------------------------------------------------------------------------------------------------
PAPER_TIP_SOL: float = 0.00025          # a small priority fee, not an auction bid
DEFAULT_SOL_PRICE_USD: float = 150.0    # only used to express the tip in USD for the scorecard

# Jupiter public quote endpoint (v6). Used READ-ONLY for price realism, never to route a real trade.
JUPITER_QUOTE_URL: str = "https://quote-api.jup.ag/v6/quote"
# Wrapped SOL mint — the quote's base leg for a paper buy/sell.
WSOL_MINT: str = "So11111111111111111111111111111111111111112"
LAMPORTS_PER_SOL: int = 1_000_000_000


def venue_toll_bps(venue: Optional[str]) -> float:
    """Per-side toll in bps for a venue. Unknown venues get the expensive default."""
    if not venue:
        return DEFAULT_TOLL_BPS
    return VENUE_TOLL_BPS.get(venue.strip().lower(), DEFAULT_TOLL_BPS)


def model_slippage_bps(usd_size: float, liq_usd_per_s: Optional[float]) -> float:
    """Pessimistic square-root impact model, floored (never zero), capped, monotone.

    Grows with order size, SHRINKS as liquidity (per-second USD throughput) grows.
    """
    liq = liq_usd_per_s if (liq_usd_per_s and liq_usd_per_s > 0) else DEFAULT_LIQ_USD_PER_S
    liq = max(liq, MIN_LIQ_USD_PER_S)
    size = max(usd_size, 0.0)
    participation = size / liq
    impact = IMPACT_COEFF_BPS * math.sqrt(participation)
    return max(SLIP_FLOOR_BPS, min(impact, MAX_SLIP_BPS))


def estimate_tip_usd(sol_price_usd: float = DEFAULT_SOL_PRICE_USD,
                     tip_sol: float = PAPER_TIP_SOL) -> float:
    """A small SOL-denominated priority-fee estimate expressed in USD (paper context only)."""
    return max(0.0, tip_sol) * max(0.0, sol_price_usd)


def build_jupiter_quote_request(intent: OrderIntent,
                                sol_price_usd: float = DEFAULT_SOL_PRICE_USD,
                                slippage_bps: Optional[float] = None) -> dict:
    """Build (but do NOT transmit) the Jupiter v6 quote request for this intent.

    Returns a dict with the target ``url`` and query ``params`` in Jupiter's public shape. This makes
    the seam to a future real-execution path visible without taking any action. A buy quotes WSOL->mint;
    a sell quotes mint->WSOL. The atomic ``amount`` is derived from the paper USD notional via the SOL
    price for the base leg (approximate — this is a request template, not an order).
    """
    is_buy = intent.side.strip().lower() == "buy"
    if is_buy:
        input_mint, output_mint = WSOL_MINT, intent.mint
    else:
        input_mint, output_mint = intent.mint, WSOL_MINT

    # Amount is expressed on the WSOL leg in lamports for a rough, template-only sizing.
    sol_notional = (intent.usd_size / sol_price_usd) if sol_price_usd > 0 else 0.0
    amount_lamports = max(0, int(sol_notional * LAMPORTS_PER_SOL))

    slip = slippage_bps if slippage_bps is not None else SLIP_FLOOR_BPS
    params = {
        "inputMint": input_mint,
        "outputMint": output_mint,
        "amount": str(amount_lamports),
        "slippageBps": str(int(round(slip))),
        "swapMode": "ExactIn",
        "onlyDirectRoutes": "false",
    }
    return {"url": JUPITER_QUOTE_URL, "params": params}


def fetch_live_quote_impact_bps(intent: OrderIntent,
                                sol_price_usd: float = DEFAULT_SOL_PRICE_USD,
                                timeout_s: float = 4.0) -> Optional[float]:
    """READ-ONLY, best-effort live price-impact lookup for extra realism. Returns impact in bps or
    None on any failure. This performs a GET against Jupiter's free public quote endpoint and reads the
    ``priceImpactPct`` field ONLY; it never submits, routes, or transmits an order. Any error (network,
    HTTP, parse) falls back to None so the caller can use the modeled/reference figure instead.
    """
    req_spec = build_jupiter_quote_request(intent, sol_price_usd=sol_price_usd)
    if int(req_spec["params"]["amount"]) <= 0:
        return None
    url = req_spec["url"] + "?" + urllib.parse.urlencode(req_spec["params"])
    try:
        req = urllib.request.Request(url, method="GET", headers={"User-Agent": "paper-sim/1.0"})
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:  # noqa: S310 (read-only GET)
            payload = json.loads(resp.read().decode("utf-8"))
        pct = float(payload.get("priceImpactPct", 0.0))
        if pct < 0:
            pct = -pct
        return pct * 10_000.0  # fraction -> bps
    except (urllib.error.URLError, ValueError, KeyError, TimeoutError, OSError):
        return None


@dataclass
class DryRunExecutor:
    """Paper Executor. Implements the ``Executor`` Protocol from types.py.

    ``execute(intent) -> Fill`` always returns a SIMULATED fill. No wallet, no secret, no broadcast.
    """
    sol_price_usd: float = DEFAULT_SOL_PRICE_USD
    tip_sol: float = PAPER_TIP_SOL
    use_live_quote: bool = False      # opt-in READ-ONLY price realism; default OFF (fully offline)
    default_liq_usd_per_s: float = DEFAULT_LIQ_USD_PER_S
    name: str = "dry-run"

    def execute(self, intent: OrderIntent, liq_usd_per_s: Optional[float] = None) -> Fill:
        """Return a realistic PAPER ``Fill`` for ``intent``. Always dry_run=True."""
        # Hard guarantee: this executor is paper. The real path stays a raising stub.
        assert not ALLOW_REAL_ORDERS, "ALLOW_REAL_ORDERS must be False in the paper stack"

        side = intent.side.strip().lower()
        liq_hint = liq_usd_per_s if liq_usd_per_s is not None else self.default_liq_usd_per_s

        slip_bps = model_slippage_bps(intent.usd_size, liq_hint)

        # Optional READ-ONLY live refinement: if the live quote reports a LARGER impact than our model,
        # take the worse (more pessimistic) of the two. Never let a live quote make the fill cheaper.
        if self.use_live_quote:
            live_bps = fetch_live_quote_impact_bps(intent, sol_price_usd=self.sol_price_usd)
            if live_bps is not None:
                slip_bps = max(slip_bps, min(live_bps, MAX_SLIP_BPS))

        # Slippage direction: a buy pays UP, a sell receives DOWN.
        adj = slip_bps / 10_000.0
        if side == "buy":
            fill_price = intent.ref_price_usd * (1.0 + adj)
        else:
            fill_price = intent.ref_price_usd * (1.0 - adj)
        fill_price = max(fill_price, 0.0)

        toll_bps = venue_toll_bps(intent.venue)
        tip_usd = estimate_tip_usd(self.sol_price_usd, self.tip_sol)

        return Fill(
            mint=intent.mint,
            side=side,
            ts=intent.ts,
            price_usd=fill_price,
            usd_size=intent.usd_size,
            toll_bps=toll_bps,
            slip_bps=slip_bps,
            tip_usd=tip_usd,
            dry_run=True,
        )

    # ----------------------------------------------------------------------------------------------
    # HARD-DISABLED live path. STUB ONLY.
    #
    # This method exists SOLELY to document the single seam where a future, human-gated, operator-
    # supplied-wallet live path would one day attach. It is guarded by ``ALLOW_REAL_ORDERS`` (hard-
    # coded False in types.py) and ALWAYS raises. It contains NO wallet handling, NO secret handling,
    # NO transaction construction, and NO broadcast. It is unreachable in this codebase and must stay
    # that way. Do NOT implement it here — a real path is a separate, human-authorized change.
    # ----------------------------------------------------------------------------------------------
    def _submit_real(self, intent: OrderIntent) -> Fill:
        if not ALLOW_REAL_ORDERS:
            raise RuntimeError(
                "real orders disabled — human-gated, operator wallet required, not implemented"
            )
        # Intentionally still unreachable even if the guard above were ever removed: no live path
        # is implemented in this codebase. This second raise is a belt-and-braces backstop.
        raise RuntimeError(
            "real orders disabled — human-gated, operator wallet required, not implemented"
        )


# Protocol conformance is structural; expose a plain constructor alias for the runner.
Executor = DryRunExecutor
