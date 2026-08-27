#!/usr/bin/env python3
"""Offline selftest for the gated live execution layer. Proves it is safe (cannot act) AND correct
(exit gate + risk caps behave). No network, no wallet, no secret. Run:

    python -m scripts.trading_bot.sniper.live_execution_selftest
"""
from __future__ import annotations

import os

from . import live_execution as LX
from .live_execution import (
    LiveConfig, LiveExecutor, RealOrdersDisabled, preflight_round_trip,
    gates_status, can_act, assert_can_act,
)
from .types import ALLOW_REAL_ORDERS, OrderIntent


def _intent(usd: float = 5.0, side: str = "buy", mint: str = "MintXYZ") -> OrderIntent:
    return OrderIntent(mint=mint, side=side, ts=0.0, ref_price_usd=1e-6, usd_size=usd, venue="pumpswap")


def _check(name: str, ok: bool, detail: str = "") -> bool:
    print(f"  [{'ok' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))
    return ok


def main() -> int:
    ok = True

    # ---- 1. The gate is hard-closed regardless of env ----
    os.environ["SNIPER_LIVE_ARMED"] = "1"
    os.environ["SNIPER_KEYPAIR_PATH"] = "/nonexistent/should/never/be/read"
    os.environ["SNIPER_RPC_URL"] = "https://example.invalid"
    g = gates_status()
    ok &= _check("master code switch ALLOW_REAL_ORDERS is False", ALLOW_REAL_ORDERS is False)
    ok &= _check("gates_status master switch is False even with all env armed",
                 g["allow_real_orders_code_switch"] is False, str(g))
    ok &= _check("can_act() is False (gate hard-closed)", can_act() is False)
    ok &= _check("gates_status returns only booleans (never key material)",
                 all(isinstance(v, bool) for v in g.values()))

    # ---- 2. assert_can_act raises; every irreversible step raises ----
    ex = LiveExecutor(cfg=LiveConfig())
    for fn_name, fn in [("assert_can_act", lambda: assert_can_act("test")),
                        ("_build_swap_tx", lambda: ex._build_swap_tx(_intent())),
                        ("_sign", lambda: ex._sign(object())),
                        ("_broadcast", lambda: ex._broadcast(object()))]:
        try:
            fn(); ok &= _check(f"{fn_name} raises RealOrdersDisabled", False, "did NOT raise")
        except RealOrdersDisabled:
            ok &= _check(f"{fn_name} raises RealOrdersDisabled", True)

    # ---- 3. execute() always raises (never returns a fill) ----
    try:
        ex.execute(_intent(), pool_reserve_usd=1_000_000.0)
        ok &= _check("execute() raises (never a real fill)", False, "returned")
    except RealOrdersDisabled:
        ok &= _check("execute() raises (never a real fill)", True)

    # ---- 4. Risk caps (planning, offline via monkeypatched quote) ----
    # Patch the Jupiter quote so planning is deterministic and offline.
    def fake_quote(input_mint, output_mint, amount_atomic, slippage_bps=300, timeout_s=4.0):
        # Symmetric, cheap round-trip. Buy leg echoes WSOL-in 1:1 as "tokens"; sell leg returns ~99%
        # of that back as WSOL -> round-trip ~100 bps, under the cap.
        if output_mint != LX.WSOL_MINT:      # BUY leg (WSOL -> mint): tokens_out = amount_in
            return {"outAmount": str(int(amount_atomic)), "priceImpactPct": "0.01"}
        return {"outAmount": str(int(amount_atomic * 0.99)), "priceImpactPct": "0.01"}  # SELL leg
    LX._jupiter_quote = fake_quote

    cfg = LiveConfig(max_usd_per_trade=10.0, max_pool_participation=0.01, max_exit_round_trip_bps=600.0)
    ex2 = LiveExecutor(cfg=cfg)

    p_big = ex2.plan(_intent(usd=50.0), pool_reserve_usd=1_000_000.0)
    ok &= _check("over-max-usd is refused", any("over-max-usd" in r for r in p_big.refusals),
                 str(p_big.refusals))

    p_part = ex2.plan(_intent(usd=5.0), pool_reserve_usd=100.0)  # 5% of a $100 pool > 1% cap
    ok &= _check("over-participation is refused", any("over-participation" in r for r in p_part.refusals),
                 str(p_part.refusals))

    p_unk = ex2.plan(_intent(usd=5.0), pool_reserve_usd=None)
    ok &= _check("unknown-liquidity is refused", any("unknown-pool-liquidity" in r for r in p_unk.refusals),
                 str(p_unk.refusals))

    p_ok = ex2.plan(_intent(usd=5.0), pool_reserve_usd=1_000_000.0)  # small, deep, cheap round-trip
    ok &= _check("clean small trade is risk-approved", p_ok.approved, str(p_ok.refusals))
    ok &= _check("risk-approved is STILL not executable (gate)", p_ok.as_dict()["would_execute"] is False)

    # ---- 5. The exit gate refuses the unexitable ----
    def no_sell_route(input_mint, output_mint, amount_atomic, slippage_bps=300, timeout_s=4.0):
        if output_mint != LX.WSOL_MINT:      # buy leg ok
            return {"outAmount": "1000", "priceImpactPct": "0.02"}
        return None                          # sell leg: no route -> unexitable
    LX._jupiter_quote = no_sell_route
    ec = preflight_round_trip("MintXYZ", 5.0, cfg)
    ok &= _check("exit gate REFUSES a coin with no sell route", (not ec.ok) and ec.reason == "no-sell-route",
                 f"{ec.ok}/{ec.reason}")

    def costly_round_trip(input_mint, output_mint, amount_atomic, slippage_bps=300, timeout_s=4.0):
        if output_mint != LX.WSOL_MINT:      # buy leg echoes 1:1
            return {"outAmount": str(int(amount_atomic)), "priceImpactPct": "0.30"}
        return {"outAmount": str(int(amount_atomic * 0.50)), "priceImpactPct": "0.30"}  # 50% haircut
    LX._jupiter_quote = costly_round_trip
    ec2 = preflight_round_trip("MintXYZ", 5.0, cfg)
    ok &= _check("exit gate REFUSES a coin with a too-costly round-trip",
                 (not ec2.ok) and ec2.reason == "round-trip-too-costly",
                 f"{ec2.ok}/{ec2.reason} rt={ec2.round_trip_bps}")

    print("\nLIVE-EXEC SELFTEST: " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
