#!/usr/bin/env python3
"""Selftest for execution.py (the DRY-RUN Executor). Proves the paper fill model is correct and that
the real path is a hard-disabled stub with no wallet/secret primitives anywhere in the module.

Run: python3 -m scripts.trading_bot.sniper.execution_selftest
"""
from __future__ import annotations

import pathlib
import re
import sys

from . import execution as ex
from .types import ALLOW_REAL_ORDERS, Fill, OrderIntent


def _intent(side: str, ref: float = 1.0e-4, usd: float = 500.0, venue=None) -> OrderIntent:
    return OrderIntent(mint="MintXYZ", side=side, ts=1000.0, ref_price_usd=ref,
                       usd_size=usd, venue=venue, tag="entry")


def check(label: str, cond: bool) -> None:
    mark = "PASS" if cond else "FAIL"
    print(f"  [{mark}] {label}")
    if not cond:
        raise AssertionError(label)


def main() -> int:
    execu = ex.DryRunExecutor(use_live_quote=False)  # fully offline
    print("== 1. slippage DIRECTION (buy above ref, sell below ref) ==")
    ref = 1.0e-4
    buy = execu.execute(_intent("buy", ref=ref, venue="pumpswap"), liq_usd_per_s=200.0)
    sell = execu.execute(_intent("sell", ref=ref, venue="pumpswap"), liq_usd_per_s=200.0)
    check("buy fills strictly ABOVE ref", buy.price_usd > ref)
    check("sell fills strictly BELOW ref", sell.price_usd < ref)
    check("both marked dry_run", buy.dry_run and sell.dry_run)
    check("slip never zero (>= floor)", buy.slip_bps >= ex.SLIP_FLOOR_BPS > 0)
    print(f"     ref={ref:.3e} buy={buy.price_usd:.3e} sell={sell.price_usd:.3e} "
          f"slip={buy.slip_bps:.1f}bps")

    print("== 2. venue TOLL mapping differs ==")
    pf = execu.execute(_intent("buy", venue="Pumpfun"), liq_usd_per_s=200.0)
    ps = execu.execute(_intent("buy", venue="Pumpswap"), liq_usd_per_s=200.0)
    unk = execu.execute(_intent("buy", venue="totally-unknown"), liq_usd_per_s=200.0)
    check("Pumpfun toll pinned at 125 bps/side", abs(pf.toll_bps - 125.0) < 1e-9)
    check("Pumpswap toll ~30 bps/side", abs(ps.toll_bps - 30.0) < 1e-9)
    check("Pumpfun toll > Pumpswap toll", pf.toll_bps > ps.toll_bps)
    check("unknown venue gets expensive default", unk.toll_bps == ex.DEFAULT_TOLL_BPS)
    print(f"     pumpfun={pf.toll_bps} pumpswap={ps.toll_bps} unknown={unk.toll_bps}")

    print("== 3. slippage GROWS as liquidity SHRINKS ==")
    liqs = [2000.0, 500.0, 200.0, 50.0, 10.0]
    slips = [execu.execute(_intent("buy", venue="pumpswap"), liq_usd_per_s=q).slip_bps for q in liqs]
    monotone = all(slips[i] <= slips[i + 1] for i in range(len(slips) - 1))
    check("slip is monotone non-decreasing as liq falls", monotone)
    check("thin-liquidity slip strictly > deep-liquidity slip", slips[-1] > slips[0])
    print("     liq->slip: " + ", ".join(f"{q:.0f}->{s:.1f}" for q, s in zip(liqs, slips)))

    print("== 3b. slippage GROWS with order SIZE ==")
    sizes = [50.0, 500.0, 5000.0]
    ssl = [execu.execute(_intent("buy", usd=z, venue="pumpswap"), liq_usd_per_s=200.0).slip_bps
           for z in sizes]
    check("slip monotone non-decreasing with size", all(ssl[i] <= ssl[i + 1] for i in range(len(ssl) - 1)))
    print("     size->slip: " + ", ".join(f"{z:.0f}->{s:.1f}" for z, s in zip(sizes, ssl)))

    print("== 4. tip estimate present, small, SOL-denominated ==")
    check("tip_usd > 0", buy.tip_usd > 0.0)
    check("tip_usd is modest (< $1, not an auction bid)", buy.tip_usd < 1.0)
    print(f"     tip_usd={buy.tip_usd:.4f} (= {ex.PAPER_TIP_SOL} SOL @ ${execu.sol_price_usd})")

    print("== 5. Jupiter quote request is BUILT, not sent ==")
    q = ex.build_jupiter_quote_request(_intent("buy", venue="pumpswap"))
    check("request has jup quote url", "quote-api.jup.ag" in q["url"])
    check("buy quotes WSOL -> mint", q["params"]["inputMint"] == ex.WSOL_MINT)
    check("has slippageBps param", "slippageBps" in q["params"])
    qs = ex.build_jupiter_quote_request(_intent("sell", venue="pumpswap"))
    check("sell quotes mint -> WSOL", qs["params"]["outputMint"] == ex.WSOL_MINT)

    print("== 6. REAL path is a hard-disabled STUB that RAISES ==")
    check("ALLOW_REAL_ORDERS is False", ALLOW_REAL_ORDERS is False)
    raised = False
    try:
        execu._submit_real(_intent("buy"))
    except RuntimeError as e:
        raised = True
        print(f"     _submit_real raised: {e}")
    check("_submit_real() RAISES RuntimeError", raised)

    print("== 7. module contains NO wallet/secret primitives ==")
    src = pathlib.Path(ex.__file__).read_text(encoding="utf-8")
    forbidden = ["private_key", "Keypair", "sign"]
    hits = {tok: len(re.findall(re.escape(tok), src)) for tok in forbidden}
    for tok, n in hits.items():
        check(f"no '{tok}' in execution.py", n == 0)
    # There is also no way to flip the flag: assert the module never assigns ALLOW_REAL_ORDERS = True.
    check("no code flips ALLOW_REAL_ORDERS to True",
          re.search(r"ALLOW_REAL_ORDERS\s*=\s*True", src) is None)
    check("no wallet/secret loading imports", not re.search(r"solders|solana\.keypair|nacl", src))

    print("== 8. Fill is a proper types.Fill ==")
    check("execute returns types.Fill", isinstance(buy, Fill))

    print("\nALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
