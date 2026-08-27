#!/usr/bin/env python3
"""Live execution LAYER for the sniper stack — built, reviewable, and HARD-DISABLED behind the gate.

This module assembles everything a real, operator-wallet trade would need — a Jupiter route, a
pre-trade round-trip *exit* quote, and a stack of capital-protecting risk checks — WITHOUT being able to
act. Every irreversible step (sign, broadcast) is guarded by a layered gate whose master switch,
``ALLOW_REAL_ORDERS`` (imported from types.py), is hard-coded False. With that switch False, ``execute``
refuses BEFORE any key is touched and BEFORE any network write. Nothing in this file can flip the gate,
loads a wallet, reads a secret, or constructs a transfer.

WHY it exists now (owner-directed): the *brain* (screen, sizing, exits, kill-switches, honest ledger) is
paper-proven. The one thing missing between paper and a real wallet is this execution layer. Building it
behind the gate means it is ready and auditable the day an edge clears the reality-gate and the owner
arms a wallet — the only remaining step then is a human wiring the signer, in one clearly-marked place.

WHAT is fully live-runnable here (all READ-ONLY, no signing, no broadcast, safe to call today):
  * ``preflight_round_trip`` — the STAR of this layer. Before buying, it asks Jupiter for a BUY quote
    (WSOL->mint) and then an immediate SELL quote of the tokens that buy would yield (mint->WSOL). The
    round-trip loss it measures is the honest, real-time answer to "can I actually get OUT of this?" —
    the live version of the rug filter that, on paper, we could only approximate. A coin with no sell
    route, or a round-trip haircut past the cap, is REFUSED before a cent is committed.
  * ``LiveExecutor.plan`` — runs the exit gate + all risk caps and returns a ``LivePlan`` describing
    exactly what a real trade WOULD do and every reason it may be refused. Pure planning; takes no action.

WHAT is a guarded stub (documented, unreachable, no crypto, no key):
  * ``_build_swap_tx`` / ``_sign`` / ``_broadcast`` — each re-checks the gate and raises. They name the
    exact call a human would wire (Jupiter /swap, a runtime-loaded keypair, sendTransaction) so the seam
    is visible, but implement NO signing and NO transmission. Wiring a real signer is a separate,
    human-authorized change made with the wallet physically in hand.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Optional

from .types import ALLOW_REAL_ORDERS, OrderIntent
from .execution import (
    JUPITER_QUOTE_URL,
    WSOL_MINT,
    LAMPORTS_PER_SOL,
    DEFAULT_SOL_PRICE_USD,
)

# PumpPortal LOCAL Transaction API: builds a swap and returns an UNSIGNED serialized transaction for the
# caller to sign locally and broadcast via their OWN RPC. This is the NON-CUSTODIAL path — the private
# key never leaves the machine; PumpPortal is only a tx-builder, never a custodian — and it handles both
# bonding-curve and migrated pump.fun pools via pool="auto". Chosen over the custodial Lightning API so
# custody stays local, matching this layer's whole security posture.
PUMPPORTAL_TRADE_LOCAL_URL = "https://pumpportal.fun/api/trade-local"


class RealOrdersDisabled(RuntimeError):
    """Raised whenever any code path attempts a real, irreversible action while the gate is closed."""


# --------------------------------------------------------------------------------------------------
# The layered gate. A real broadcast requires ALL of these to be true at once. Only the FIRST is a
# code constant (hard False); the rest are operational so that, even in a hypothetical future where a
# human authorizes live trading, arming is explicit, per-run, and revocable — never implicit.
#   1. ALLOW_REAL_ORDERS ......... master code switch, hard-coded False in types.py (never set in code)
#   2. SNIPER_LIVE_ARMED=1 ....... explicit per-process operator arming (env; default off)
#   3. SNIPER_KEYPAIR_PATH ....... a wallet supplied AT RUNTIME (env path; never hardcoded/committed)
#   4. SNIPER_RPC_URL ............ an explicit submit endpoint (env; no default)
# gates_status() reports each independently for audit; assert_can_act() raises unless ALL hold. Because
# gate #1 is hard False, assert_can_act() ALWAYS raises in this codebase.
# --------------------------------------------------------------------------------------------------

def _env_flag(name: str) -> bool:
    return os.getenv(name, "0").strip().lower() in ("1", "true", "yes", "on")


def gates_status() -> dict:
    """Report every gate independently (booleans only — never the key material itself)."""
    return {
        "allow_real_orders_code_switch": bool(ALLOW_REAL_ORDERS),   # hard False
        "armed_env": _env_flag("SNIPER_LIVE_ARMED"),
        "keypair_present": bool(os.getenv("SNIPER_KEYPAIR_PATH", "").strip()),
        "rpc_present": bool(os.getenv("SNIPER_RPC_URL", "").strip()),
    }


def can_act() -> bool:
    """True only if EVERY gate is open. Hard False in this codebase (gate #1 is a False constant)."""
    g = gates_status()
    return all(g.values())


def assert_can_act(action: str) -> None:
    """Raise unless every gate is open. The single chokepoint every irreversible step must pass."""
    if not ALLOW_REAL_ORDERS:
        raise RealOrdersDisabled(
            f"{action}: blocked — ALLOW_REAL_ORDERS is hard-False. Real trading is a separate, "
            "human-authorized change; this layer is built but inert."
        )
    # Unreachable while gate #1 is False; kept as belt-and-braces so removing one guard is not enough.
    if not can_act():
        raise RealOrdersDisabled(f"{action}: blocked — not all operational gates are armed")


# --------------------------------------------------------------------------------------------------
# Capital-protection config. Deliberately tiny defaults: the first real trades are €-scale probes run
# beside paper to verify live fills match the paper assumptions. All overridable by env at arm-time.
# --------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class LiveConfig:
    max_usd_per_trade: float = 10.0            # hard per-trade notional cap
    max_pool_participation: float = 0.01       # order ≤ 1% of the pool's USD reserve (don't move price)
    max_entry_slippage_bps: float = 300.0      # refuse a buy whose route impact exceeds this
    max_exit_round_trip_bps: float = 600.0     # refuse if buy+sell round-trip haircut exceeds this
    daily_loss_cap_usd: float = 50.0           # bot halts for the day past this realized loss
    quote_timeout_s: float = 4.0
    priority_fee_sol: float = 0.00005          # priority fee on the built tx (modest, not an auction bid)

    @classmethod
    def from_env(cls) -> "LiveConfig":
        def _f(name: str, default: float) -> float:
            try:
                return float(os.getenv(name, "").strip() or default)
            except ValueError:
                return default
        return cls(
            max_usd_per_trade=_f("SNIPER_MAX_USD_PER_TRADE", 10.0),
            max_pool_participation=_f("SNIPER_MAX_POOL_PARTICIPATION", 0.01),
            max_entry_slippage_bps=_f("SNIPER_MAX_ENTRY_SLIP_BPS", 300.0),
            max_exit_round_trip_bps=_f("SNIPER_MAX_EXIT_ROUND_TRIP_BPS", 600.0),
            daily_loss_cap_usd=_f("SNIPER_DAILY_LOSS_CAP_USD", 50.0),
        )


# --------------------------------------------------------------------------------------------------
# READ-ONLY Jupiter quote helpers. A GET returns a route; it signs nothing and moves nothing.
# --------------------------------------------------------------------------------------------------
def _jupiter_quote(input_mint: str, output_mint: str, amount_atomic: int,
                   slippage_bps: int = 300, timeout_s: float = 4.0) -> Optional[dict]:
    """READ-ONLY GET against Jupiter's public v6 quote endpoint. Returns the parsed route or None.

    Never submits, routes, signs, or transmits. Any failure (network/HTTP/parse/no-route) -> None.
    """
    if amount_atomic <= 0:
        return None
    params = {
        "inputMint": input_mint,
        "outputMint": output_mint,
        "amount": str(int(amount_atomic)),
        "slippageBps": str(int(slippage_bps)),
        "swapMode": "ExactIn",
        "onlyDirectRoutes": "false",
    }
    url = JUPITER_QUOTE_URL + "?" + urllib.parse.urlencode(params)
    try:
        req = urllib.request.Request(url, method="GET", headers={"User-Agent": "sniper-preflight/1.0"})
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:  # noqa: S310 (read-only GET)
            payload = json.loads(resp.read().decode("utf-8"))
        # v6 returns the quote object directly; an error body has no outAmount.
        if not isinstance(payload, dict) or "outAmount" not in payload:
            return None
        return payload
    except (urllib.error.URLError, ValueError, KeyError, TimeoutError, OSError):
        return None


@dataclass
class ExitCheck:
    """Result of the pre-trade round-trip exit probe."""
    ok: bool
    reason: str
    round_trip_bps: Optional[float] = None
    buy_impact_bps: Optional[float] = None
    sell_impact_bps: Optional[float] = None
    sell_route_exists: bool = False


def preflight_round_trip(mint: str, usd_size: float, cfg: LiveConfig,
                         sol_price_usd: float = DEFAULT_SOL_PRICE_USD) -> ExitCheck:
    """THE exit gate. Ask Jupiter: if I buy ``usd_size`` of ``mint`` now, can I sell it straight back?

    Two READ-ONLY quotes: WSOL->mint (buy), then mint->WSOL of exactly the tokens that buy yields (sell).
    The round-trip haircut = 1 - (WSOL back / WSOL in). A missing sell route, or a haircut beyond
    ``cfg.max_exit_round_trip_bps``, REFUSES the trade before any capital is committed. This is the live,
    enforceable form of the rug filter: the coins that later become unexitable are the ones that fail
    HERE, because their sell side is already thin or absent. Signs nothing; moves nothing.
    """
    sol_notional = (usd_size / sol_price_usd) if sol_price_usd > 0 else 0.0
    amount_in = max(0, int(sol_notional * LAMPORTS_PER_SOL))
    if amount_in <= 0:
        return ExitCheck(ok=False, reason="zero-size")

    buy = _jupiter_quote(WSOL_MINT, mint, amount_in,
                         slippage_bps=int(cfg.max_entry_slippage_bps), timeout_s=cfg.quote_timeout_s)
    if not buy:
        return ExitCheck(ok=False, reason="no-buy-route")
    try:
        tokens_out = int(buy["outAmount"])
        buy_impact_bps = abs(float(buy.get("priceImpactPct", 0.0))) * 10_000.0
    except (KeyError, ValueError, TypeError):
        return ExitCheck(ok=False, reason="bad-buy-quote")
    if tokens_out <= 0:
        return ExitCheck(ok=False, reason="buy-yields-zero")

    sell = _jupiter_quote(mint, WSOL_MINT, tokens_out,
                          slippage_bps=int(cfg.max_entry_slippage_bps), timeout_s=cfg.quote_timeout_s)
    if not sell:
        # No route to sell the tokens we'd receive: the definition of unexitable. Refuse.
        return ExitCheck(ok=False, reason="no-sell-route", buy_impact_bps=buy_impact_bps,
                         sell_route_exists=False)
    try:
        wsol_back = int(sell["outAmount"])
        sell_impact_bps = abs(float(sell.get("priceImpactPct", 0.0))) * 10_000.0
    except (KeyError, ValueError, TypeError):
        return ExitCheck(ok=False, reason="bad-sell-quote", buy_impact_bps=buy_impact_bps,
                         sell_route_exists=True)

    round_trip_bps = (1.0 - (wsol_back / amount_in)) * 10_000.0 if amount_in > 0 else None
    if round_trip_bps is None:
        return ExitCheck(ok=False, reason="round-trip-uncomputable", sell_route_exists=True)
    if round_trip_bps > cfg.max_exit_round_trip_bps:
        return ExitCheck(ok=False, reason="round-trip-too-costly", round_trip_bps=round_trip_bps,
                         buy_impact_bps=buy_impact_bps, sell_impact_bps=sell_impact_bps,
                         sell_route_exists=True)
    return ExitCheck(ok=True, reason="ok", round_trip_bps=round_trip_bps,
                     buy_impact_bps=buy_impact_bps, sell_impact_bps=sell_impact_bps,
                     sell_route_exists=True)


@dataclass
class LivePlan:
    """What a real trade WOULD do, and every reason it may be refused. Taking no action produces this."""
    intent: OrderIntent
    approved: bool
    refusals: list = field(default_factory=list)
    exit_check: Optional[ExitCheck] = None
    pool_reserve_usd: Optional[float] = None
    participation: Optional[float] = None
    gates: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        ec = self.exit_check
        return {
            "mint": self.intent.mint,
            "side": self.intent.side,
            "usd_size": self.intent.usd_size,
            "approved_by_risk": self.approved,       # NOTE: risk-approved != executable; gate is separate
            "refusals": list(self.refusals),
            "exit_check": None if ec is None else {
                "ok": ec.ok, "reason": ec.reason, "round_trip_bps": ec.round_trip_bps,
                "sell_route_exists": ec.sell_route_exists,
            },
            "participation": self.participation,
            "gates": self.gates,
            "would_execute": self.approved and can_act(),  # False in this codebase (gate hard-closed)
        }


@dataclass
class LiveExecutor:
    """The real-execution layer — fully assembled, permanently inert behind the gate.

    ``plan(intent)`` is safe to call today: it runs the exit gate + risk caps and returns a LivePlan,
    taking no action. ``execute(intent)`` funnels through ``assert_can_act`` and therefore always raises
    ``RealOrdersDisabled`` in this codebase. No wallet is loaded, no secret is read, nothing is sent.
    """
    cfg: LiveConfig = field(default_factory=LiveConfig.from_env)
    sol_price_usd: float = DEFAULT_SOL_PRICE_USD
    name: str = "live-gated"

    # -------------------------------- planning (safe, read-only) --------------------------------
    def plan(self, intent: OrderIntent, pool_reserve_usd: Optional[float] = None) -> LivePlan:
        refusals: list = []
        side = intent.side.strip().lower()

        # Cap 1: per-trade notional.
        if intent.usd_size > self.cfg.max_usd_per_trade:
            refusals.append(f"over-max-usd:{intent.usd_size:.2f}>{self.cfg.max_usd_per_trade:.2f}")

        # Cap 2: pool participation (don't be more than a sliver of the pool, so your own exit is cheap).
        participation = None
        if pool_reserve_usd and pool_reserve_usd > 0:
            participation = intent.usd_size / pool_reserve_usd
            if participation > self.cfg.max_pool_participation:
                refusals.append(
                    f"over-participation:{participation:.4f}>{self.cfg.max_pool_participation:.4f}")
        else:
            refusals.append("unknown-pool-liquidity")   # never size into a pool we can't measure

        # Cap 3 (buys only): the round-trip exit gate — can we actually get out?
        exit_check = None
        if side == "buy":
            exit_check = preflight_round_trip(intent.mint, intent.usd_size, self.cfg,
                                              sol_price_usd=self.sol_price_usd)
            if not exit_check.ok:
                refusals.append(f"exit-gate:{exit_check.reason}")

        approved = not refusals
        return LivePlan(intent=intent, approved=approved, refusals=refusals, exit_check=exit_check,
                        pool_reserve_usd=pool_reserve_usd, participation=participation,
                        gates=gates_status())

    # -------------------------------- execution (hard-gated) --------------------------------
    def execute(self, intent: OrderIntent, pool_reserve_usd: Optional[float] = None):
        """Attempt a REAL fill. Always raises in this codebase — the gate is hard-closed.

        Order of operations is capital-safe by construction: risk plan first, THEN the gate, THEN (only
        if it could ever open) build/sign/broadcast. Because ``assert_can_act`` raises while
        ALLOW_REAL_ORDERS is False, control never reaches key handling or the network.
        """
        plan = self.plan(intent, pool_reserve_usd=pool_reserve_usd)
        if not plan.approved:
            raise RealOrdersDisabled(f"refused by risk plan: {plan.refusals}")
        assert_can_act("execute")                         # <-- hard stop; raises here, always
        # ----- unreachable in this codebase; the documented live seam a human would wire -----
        unsigned = self._build_swap_tx(intent)            # PumpPortal Local API -> unsigned tx bytes
        signed = self._sign(unsigned)                     # runtime-loaded keypair signs (stub)
        return self._broadcast(signed)                    # RPC sendTransaction (stub)

    def _build_swap_tx(self, intent: OrderIntent) -> bytes:
        """Build (NON-CUSTODIALLY) the unsigned swap transaction via PumpPortal's LOCAL Transaction API.

        WIRED (behind the gate): POSTs the order to ``/api/trade-local`` and returns the serialized
        UNSIGNED transaction bytes for ``_sign`` to sign locally. This endpoint neither signs nor sends —
        it only builds — so the private key stays on this machine and PumpPortal never has spending
        authority. ``assert_can_act`` raises first while ALLOW_REAL_ORDERS is False, so in THIS codebase
        control never reaches the POST; the wiring exists so a human arming a wallet has a working,
        auditable path with nothing left to write but the local signer.

        The wallet PUBLIC key (not a secret) is read from env ``SNIPER_WALLET_PUBKEY``. A buy is
        denominated in SOL (notional / SOL price); a sell closes the whole position ("100%").
        """
        assert_can_act("build_swap_tx")   # hard stop while gated; nothing below runs in this codebase
        pubkey = os.getenv("SNIPER_WALLET_PUBKEY", "").strip()
        if not pubkey:
            raise RealOrdersDisabled("build_swap_tx: no SNIPER_WALLET_PUBKEY (wallet public key) set")
        side = intent.side.strip().lower()
        if side == "buy":
            amount: object = max(0.0, intent.usd_size / self.sol_price_usd)  # SOL notional
            denominated_in_sol = "true"
        else:
            amount = "100%"                                                  # sell the full position
            denominated_in_sol = "false"
        body = json.dumps({
            "publicKey": pubkey,
            "action": side,                                    # "buy" | "sell"
            "mint": intent.mint,
            "amount": amount,
            "denominatedInSol": denominated_in_sol,
            "slippage": self.cfg.max_entry_slippage_bps / 100.0,   # bps -> percent
            "priorityFee": self.cfg.priority_fee_sol,
            "pool": "auto",                                    # bonding-curve or migrated AMM
        }).encode()
        req = urllib.request.Request(
            PUMPPORTAL_TRADE_LOCAL_URL, data=body,
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=self.cfg.quote_timeout_s) as resp:  # noqa: S310
            return resp.read()   # serialized UNSIGNED VersionedTransaction bytes -> _sign()

    def _sign(self, unsigned_tx):
        assert_can_act("sign")
        raise RealOrdersDisabled(
            "signing not implemented — would load the operator keypair from SNIPER_KEYPAIR_PATH at "
            "runtime (never hardcoded/committed/logged) and sign locally; wired by a human at arm-time")

    def _broadcast(self, signed_tx):
        assert_can_act("broadcast")
        raise RealOrdersDisabled(
            "broadcast not implemented — would send the signed tx via SNIPER_RPC_URL sendTransaction "
            "with a priority fee, then confirm; wired by a human at arm-time")


# Structural Executor-Protocol note: LiveExecutor.execute has an extended signature (pool reserve) and
# raises rather than returning a Fill while gated, so it is intentionally NOT aliased as the stack's
# Executor. The paper DryRunExecutor remains the only wired Executor. This layer is a staged, inert
# component that a human promotes deliberately — never an implicit swap-in.
