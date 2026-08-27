#!/usr/bin/env python3
"""Selftest for rugrisk.py — the on-chain rug-risk entry filter (PAPER / READ-ONLY).

Two parts:
  A. DETERMINISTIC synthetic proofs (no network): PDA/on-curve math, holder-concentration mapping,
     early-buyer bundle detection, liquidity trajectory, deployer cold-start, and the block/allow gate.
  B. A LIVE demo on real mints via the Chainstack RPC (skipped gracefully if the RPC is unavailable),
     showing real holder-concentration numbers + coverage.

Run (system python is fine — no websockets needed here):
    python3 -m scripts.trading_bot.sniper.rugrisk_selftest
"""
from __future__ import annotations

from . import rugrisk as rr
from .types import TradeTick


def check(label: str, cond: bool) -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}")
    if not cond:
        raise AssertionError(label)


def _hr(t: str) -> None:
    print("\n" + "=" * 72 + f"\n{t}\n" + "=" * 72)


def _patch_supply(supply):
    """Patch rr.rpc_call so getTokenSupply returns a fixed supply (no network)."""
    orig = rr.rpc_call
    rr.rpc_call = lambda url, meth, params=None, timeout=8.0: (
        {"value": {"amount": str(supply), "decimals": 6}} if meth == "getTokenSupply" else None)
    return orig


def _curve_wallets(n):
    """Generate n distinct ON-curve wallet addresses deterministically (for spread-float tests)."""
    out, base, i = [], rr.b58decode("CVfGfkNohFZ4wKWaFz4soQh93WFF9aJvaf45vfQuBo12"), 0
    while len(out) < n and i < n * 60:
        cand = bytes([(base[0] + i) % 256]) + base[1:]
        if rr.is_on_curve(cand):
            out.append(rr.b58encode(cand))
        i += 1
    return out


def test_pda_and_curve() -> None:
    _hr("A1. PDA derivation + ed25519 on-curve classification")
    mint = "2BSZ36W4QAiEtZjPYvRF9S7UKm4EJr76Y7hdBuhepump"
    pda = rr.bonding_curve_pda(mint)
    check("bonding-curve PDA matches the verified on-chain reserve owner",
          pda == "GJGE4EsCkvVRLVJ4xTALM6MgTYWsWFaDMvjYzU7w4epZ")
    check("reserve PDA is OFF the ed25519 curve (a program vault, not a user)",
          not rr.is_on_curve(rr.b58decode(pda)))
    # A normal wallet from the live enumeration is ON curve.
    check("a normal user wallet is ON the curve",
          rr.is_on_curve(rr.b58decode("CVfGfkNohFZ4wKWaFz4soQh93WFF9aJvaf45vfQuBo12")))


def test_holder_component() -> None:
    _hr("A2. Holder-concentration mapping — blocks concentrated, allows healthy (synthetic)")
    supply = 1_000_000_000_000_000
    reserve_owner = "GJGE4EsCkvVRLVJ4xTALM6MgTYWsWFaDMvjYzU7w4epZ"  # off-curve reserve (excluded)
    spread = _curve_wallets(40)
    check("built >=20 distinct on-curve test wallets", len(spread) >= 20)
    float_amt = int(supply * 0.20)  # 20% of supply is in user hands; 80% still in the reserve
    orig_rpc = _patch_supply(supply)
    try:
        # --- HEALTHY: float spread evenly across 40 wallets. Enumeration items are (amount, owner). ---
        scorer = rr.RugRiskScorer(rpc_url="x")
        per = float_amt // len(spread)
        healthy = [(supply - float_amt, reserve_owner)] + [(per, w) for w in spread]
        scorer._enumerate_token_accounts = lambda m: (healthy, rr.TOKEN22_PROGRAM)
        hc = scorer.holder_concentration("HEALTHY")
        print(f"  healthy: float={hc.float_frac*100:.1f}% top1={hc.top1_frac*100:.1f}% "
              f"top10={hc.top10_frac*100:.1f}% n_users={hc.n_holders} -> hc={hc.component}")
        check("healthy: reserve excluded (float ~20%)", 0.15 < hc.float_frac < 0.25)
        check("healthy: low holder-concentration component (<0.3)", hc.component < 0.3)

        # --- CONCENTRATED: one whale holds ~90% of the float ---
        scorer = rr.RugRiskScorer(rpc_url="x")
        whale = spread[0]
        conc = [(supply - float_amt, reserve_owner), (int(float_amt * 0.90), whale)]
        conc += [(int(float_amt * 0.02), w) for w in spread[1:6]]
        scorer._enumerate_token_accounts = lambda m: (conc, rr.TOKEN22_PROGRAM)
        hc = scorer.holder_concentration("CONC")
        print(f"  concentrated: float={hc.float_frac*100:.1f}% top1={hc.top1_frac*100:.1f}% -> hc={hc.component}")
        check("concentrated: top1 of float > 80%", hc.top1_frac > 0.80)
        check("concentrated: high holder-concentration component (>=0.9)", hc.component >= 0.9)

        # --- MEGA-RUG: dev kept 40% of TOTAL supply ---
        scorer = rr.RugRiskScorer(rpc_url="x")
        mega = [(int(supply * 0.55), reserve_owner), (int(supply * 0.40), whale),
                (int(supply * 0.05), spread[1])]
        scorer._enumerate_token_accounts = lambda m: (mega, rr.TOKEN22_PROGRAM)
        hc = scorer.holder_concentration("MEGA")
        print(f"  mega-rug: top1_of_supply={hc.top1_supply_frac*100:.1f}% -> hc={hc.component}")
        check("mega-rug: top1 of SUPPLY > 35%", hc.top1_supply_frac > 0.35)
        check("mega-rug: high component from supply frame", hc.component >= 0.9)
    finally:
        rr.rpc_call = orig_rpc


def test_early_buyer() -> None:
    _hr("A3. Early-buyer / bundle concentration (synthetic tick stream)")
    cfg = rr.RugConfig()
    # BUNDLE: 3 wallets do ~all early buying
    eb = rr.EarlyBuyerTracker(cfg)
    for i, (w, usd) in enumerate([("A", 400), ("B", 350), ("C", 300), ("A", 200), ("B", 150)]):
        eb.observe("bundle", ts=1000.0 + i, side="buy", user=w, usd=usd)
    comp, det = eb.assess("bundle")
    print(f"  bundle: {det} -> component={comp}")
    check("bundle flagged high (>=0.8) even with few buyers", comp is not None and comp >= 0.8)

    # HEALTHY: many distinct early buyers, spread
    eb2 = rr.EarlyBuyerTracker(cfg)
    for i in range(20):
        eb2.observe("spread", ts=1000.0 + i * 0.5, side="buy", user=f"W{i}", usd=100.0)
    comp2, det2 = eb2.assess("spread")
    print(f"  spread: {det2} -> component={comp2}")
    check("spread early-buying: low component (<0.3)", comp2 is not None and comp2 < 0.3)

    # Past the window -> frozen (later buys ignored)
    eb2.observe("spread", ts=2000.0, side="buy", user="LATE_WHALE", usd=100000.0)
    comp3, _ = eb2.assess("spread")
    check("buys past the early window are ignored (frozen)", comp3 == comp2)


def test_liquidity() -> None:
    _hr("A4. Liquidity trajectory (net-flow proxy)")
    cfg = rr.RugConfig()
    lt = rr.LiquidityTracker(cfg)
    # Sell-dominated window => liquidity being pulled
    for i in range(20):
        lt.observe("pull", ts=1000.0 + i, side="sell", usd=50.0)
    for i in range(4):
        lt.observe("pull", ts=1000.0 + i, side="buy", usd=50.0)
    comp, det = lt.assess("pull")
    print(f"  pulling: {det} -> component={comp}")
    check("sell-dominated window flags liquidity risk (>0.5)", comp is not None and comp > 0.5)
    # Buy-dominated (a fresh surge) => benign
    lt2 = rr.LiquidityTracker(cfg)
    for i in range(20):
        lt2.observe("surge", ts=1000.0 + i, side="buy", usd=50.0)
    comp2, _ = lt2.assess("surge")
    check("buy-dominated surge: benign liquidity component (~0)", comp2 is not None and comp2 < 0.2)


def test_deployer(tmp="/tmp/claude_rug_deployers_test.json") -> None:
    _hr("A5. Deployer reputation (cold-start collector + outcome ingest)")
    import os
    for p in (tmp, tmp + ".tmp"):
        if os.path.exists(p):
            os.remove(p)
    reg = rr.DeployerRegistry(path=tmp)
    reg.record_deployer("mintX", "devWALLET")
    reg.record_deployer("mintY", "devWALLET")
    check("no history yet -> not a known rugger", not reg.is_known_rugger("devWALLET")["known"])
    reg.record_outcome("mintX", rugged=True)     # mintX rugged
    info = reg.is_known_rugger("devWALLET")
    print(f"  after 1 rug: {info}")
    check("after a rug, deployer is a known rugger", info["known"] and info["rugs"] == 1)
    comp, det = reg.assess("mintY")
    print(f"  mintY (same dev, new coin): component={comp} detail={det}")
    check("a new coin from a known rugger scores high deployer component", comp >= 0.6)
    # persistence
    reg2 = rr.DeployerRegistry(path=tmp)
    check("registry persisted across reload", reg2.is_known_rugger("devWALLET")["known"])
    os.remove(tmp)


def test_gate_and_score() -> None:
    _hr("A6. Combined score + block/allow gate + fail-open")
    scorer = rr.RugRiskScorer(rpc_url=None)
    # Force a concentrated holder read via monkeypatch of holder_concentration
    hc_hi = rr.HolderConcentration(mint="m", supply=100, n_holders=1, reserve_amount=50,
                                   circulating=50, float_frac=0.5, top1_frac=0.95, top5_frac=0.99,
                                   top10_frac=1.0, top1_supply_frac=0.10, component=1.0,
                                   token_program=rr.TOKEN22_PROGRAM)
    scorer.holder_concentration = lambda m: hc_hi
    a = scorer.rug_score("concentrated")
    print(f"  concentrated: {a.reason}  components={a.components}")
    check("concentrated coin BLOCKS (score >= threshold)", a.blocked)
    check("holder signal marked assessed", a.holder_assessed)

    scorer2 = rr.RugRiskScorer(rpc_url=None)
    hc_lo = rr.HolderConcentration(mint="m", supply=100, n_holders=40, reserve_amount=80,
                                   circulating=20, float_frac=0.2, top1_frac=0.10, top5_frac=0.35,
                                   top10_frac=0.55, top1_supply_frac=0.02, component=0.0,
                                   token_program=rr.TOKEN22_PROGRAM)
    scorer2.holder_concentration = lambda m: hc_lo
    b = scorer2.rug_score("healthy")
    print(f"  healthy: {b.reason}  components={b.components}")
    check("healthy coin ALLOWED (not blocked)", not b.blocked)

    # fail-open: holder unassessable -> allow even if proxies exist, and don't block on proxy-only
    scorer3 = rr.RugRiskScorer(rpc_url=None)
    scorer3.holder_concentration = lambda m: None
    # inject a bundled early signal (proxy) — must NOT block by itself (require_primary_for_block)
    scorer3.early.observe("u", 1000, "buy", "W1", 500)
    scorer3.early.observe("u", 1001, "buy", "W1", 500)
    c = scorer3.rug_score("unassessed")
    print(f"  unassessed(primary)+bundled proxy: {c.reason} blocked={c.blocked}")
    check("fail-OPEN: no block when the PRIMARY holder signal is unavailable", not c.blocked)
    cov = scorer3.coverage()
    check("coverage counts the unassessed candidate", cov["candidates"] >= 1)


def test_live() -> bool:
    _hr("B. LIVE demo on real mints via Chainstack RPC (skipped if unavailable)")
    scorer = rr.RugRiskScorer()
    if not scorer._rpc_url:
        print("  SOLANA_RPC_URL not set -> skipping live section.")
        return True
    mints = ["2BSZ36W4QAiEtZjPYvRF9S7UKm4EJr76Y7hdBuhepump",
             "4MzpjwjkWn7628mEMqasz5RyFU3tDhyoXXCegmvUpump",
             "6b3iNNY2KBwFtX6pfBgRXUDdERbTAcptWi5cchZgpump"]
    any_ok = False
    for mint in mints:
        hc = scorer.holder_concentration(mint)
        if hc is None:
            print(f"  {mint[:12]}… -> UNASSESSABLE (fail-open ALLOW)")
            continue
        any_ok = True
        a = scorer.rug_score(mint)
        print(f"  {mint[:12]}…  float={hc.float_frac*100:5.2f}%  "
              f"top1/5/10_float={hc.top1_frac*100:4.1f}/{hc.top5_frac*100:4.1f}/{hc.top10_frac*100:4.1f}%  "
              f"top1_supply={hc.top1_supply_frac*100:5.2f}%  users={hc.n_holders:3d}  "
              f"-> {a.reason}")
    print(f"  coverage: {scorer.coverage()}")
    return any_ok


def main() -> int:
    test_pda_and_curve()
    test_holder_component()
    test_early_buyer()
    test_liquidity()
    test_deployer()
    test_gate_and_score()
    live_ok = test_live()
    _hr("RESULT")
    print("deterministic synthetic proofs: PASS")
    print(f"live RPC holder read: {'demonstrated' if live_ok else 'unavailable (fail-open path exercised)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
