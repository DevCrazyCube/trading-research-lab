#!/usr/bin/env python3
"""Hermetic wiring check -- NO network. Exercises screen -> freeze -> resolve -> score end to end."""

from __future__ import annotations

import sys

from .frozen import frozen_spec, canonical_sha256
from . import screen as screen_mod, paper, scoring


def _check(name: str, cond: bool, detail: str = "") -> bool:
    print(f"  [{'ok' if cond else 'FAIL'}] {name}{(' -- ' + detail) if detail else ''}")
    return cond


def _coin(**kw) -> dict:
    base = {"pool_address": "PoolTest1111", "chain": "solana", "dex": "pump-fun", "name": "TEST / SOL",
            "base_token": "Tok111", "price_usd": 1e-6, "fdv_usd": 50000.0, "market_cap_usd": None,
            "reserve_usd": 20000.0, "pool_created_at": None, "age_minutes": 3.0,
            "buys": 40, "sells": 20, "buyers": 30, "sellers": 15, "volume_usd_m5": 5000.0,
            "pulled_utc": "2026-01-01T00:00:00+00:00"}
    base.update(kw)
    return base


def run_selftest() -> int:
    spec = frozen_spec()
    ok = True

    # --- screen: a clean coin PASSes ---
    clean = screen_mod.screen_coin(_coin(), spec)
    ok &= _check("clean coin PASSes", clean["verdict"] == "PASS", str(clean["reasons"]))

    # --- screen: each red flag REJECTs ---
    lowcap = screen_mod.screen_coin(_coin(fdv_usd=1000.0), spec)
    ok &= _check("sub-floor FDV REJECTed", lowcap["verdict"] == "REJECT"
                 and any("MIN_FDV" in r for r in lowcap["reasons"]))
    dead = screen_mod.screen_coin(_coin(buyers=2, buys=2), spec)
    ok &= _check("deadness proxy (few buyers) REJECTed", dead["verdict"] == "REJECT"
                 and any("DEADNESS" in r for r in dead["reasons"]))
    bundle = screen_mod.screen_coin(_coin(buys=200, buyers=12), spec)
    ok &= _check("bundle proxy (buys/buyer high) REJECTed", bundle["verdict"] == "REJECT"
                 and any("BUNDLE" in r for r in bundle["reasons"]))
    honey = screen_mod.screen_coin(_coin(buys=40, sellers=0), spec)
    ok &= _check("honeypot proxy (0 sellers) REJECTed", honey["verdict"] == "REJECT"
                 and any("HONEYPOT" in r for r in honey["reasons"]))
    thin = screen_mod.screen_coin(_coin(reserve_usd=100.0), spec)
    ok &= _check("thin liquidity REJECTed", thin["verdict"] == "REJECT"
                 and any("MIN_LIQUIDITY" in r for r in thin["reasons"]))

    # --- freeze: entry hash is stable and tamper-evident ---
    setup = paper.build_entry(_coin(), clean, spec, control=False)
    ok &= _check("entry hash verifies", canonical_sha256(setup) == setup["setup_sha256"])
    tampered = dict(setup, entry_price_usd=setup["entry_price_usd"] * 2)
    ok &= _check("tampered entry FAILS its hash", canonical_sha256(tampered) != setup["setup_sha256"])
    ok &= _check("sizing is fixed fraction (no martingale)",
                 abs(setup["size_sol"] - spec["bankroll_sol"] * spec["position_fraction"]) < 1e-9,
                 f"{setup['size_sol']} SOL")
    ok &= _check("stop/target asymmetric (target move > stop move)",
                 spec["target_frac"] > spec["stop_frac"])

    # --- resolve: stop, target, horizon, unexitable all price the toll correctly ---
    stop_hit = paper.resolve_position(dict(setup, decided_utc="2000-01-01T00:00:00+00:00"),
                                      {"price_usd": setup["stop_price_usd"] * 0.9}, spec)
    ok &= _check("stop resolves ~ -1R minus toll", stop_hit["resolution_reason"] == "STOP"
                 and -1.4 < stop_hit["realized_r"] < -1.0, f"R={stop_hit['realized_r']}")
    tgt_hit = paper.resolve_position(dict(setup, decided_utc="2000-01-01T00:00:00+00:00"),
                                     {"price_usd": setup["target_price_usd"] * 1.1}, spec)
    ok &= _check("target resolves positive, < raw reward/risk (toll drag)",
                 tgt_hit["resolution_reason"] == "TARGET" and 0 < tgt_hit["realized_r"]
                 < spec["target_frac"] / spec["stop_frac"], f"R={tgt_hit['realized_r']}")
    unexit = paper.resolve_position(dict(setup, decided_utc="2000-01-01T00:00:00+00:00"),
                                    {"price_usd": None}, spec)
    ok &= _check("no live price past horizon = UNEXITABLE_TIMEOUT loss",
                 unexit["resolution_reason"] == "UNEXITABLE_TIMEOUT" and unexit["realized_r"] < 0)
    still_open = paper.resolve_position(setup, {"price_usd": setup["entry_price_usd"]}, spec)
    ok &= _check("fresh position between stop/target/horizon stays OPEN", still_open is None)

    # --- MEMEBOT_FAST parallel variant: loads, is a DISTINCT frozen object, and dead-exits ---
    from .frozen import ACTIVE_INSTRUMENTS
    ok &= _check("all seven variants declared active",
                 set(ACTIVE_INSTRUMENTS) == {"MEMEBOT1", "MEMEBOT_FAST", "MEMEBOT_RUNNER",
                                             "MEMEBOT_G73", "MEMEBOT_QUICK", "MEMEBOT_EXIT",
                                             "MEMEBOT_EXIT_V2"})

    # MEMEBOT_EXIT's whole point is a STRICTER ENTRY screen -- it must actually REJECT coins the base
    # passes, or the exitability test is a fiction (the bug Codex caught: the scanner screened every
    # variant with specs[0], ignoring EXIT's own rules). Assert the screen truly differs.
    from .screen import screen_coin as _screen
    exit_spec = frozen_spec("MEMEBOT_EXIT")
    thin = {"fdv_usd": 20000, "reserve_usd": 6375, "buyers": 15, "buys": 30, "sellers": 1, "age_minutes": 5}
    ok &= _check("EXIT screen REJECTS a coin the base PASSes (thin reserve / no proven seller)",
                 _screen(thin, spec)["verdict"] == "PASS" and _screen(thin, exit_spec)["verdict"] == "REJECT",
                 f"base={_screen(thin, spec)['verdict']} exit={_screen(thin, exit_spec)['verdict']}")
    exitable = {"fdv_usd": 20000, "reserve_usd": 15000, "buyers": 15, "buys": 30, "sellers": 5, "age_minutes": 5}
    ok &= _check("EXIT screen PASSES a deep, proven-exitable coin",
                 _screen(exitable, exit_spec)["verdict"] == "PASS")
    exit_v2 = frozen_spec("MEMEBOT_EXIT_V2")
    v2_pump = _coin(dex="pump-fun", reserve_usd=5000.0, sellers=5)
    v2_amm = _coin(dex="raydium", reserve_usd=50000.0, sellers=20)
    ok &= _check("EXIT_V2 is Pump-only even when an AMM coin otherwise clears every threshold",
                 _screen(v2_pump, exit_v2)["verdict"] == "PASS"
                 and any("OUT_OF_SCOPE_VENUE" in r for r in _screen(v2_amm, exit_v2)["reasons"]))
    v2_setup = paper.build_entry(v2_pump, _screen(v2_pump, exit_v2), exit_v2, control=False)
    v2_unexit = paper.resolve_position(
        dict(v2_setup, decided_utc="2000-01-01T00:00:00+00:00"), {"price_usd": None}, exit_v2)
    ok &= _check("EXIT_V2 unavailable exit is the frozen full loss (-4.12R), not a stop-floor mark",
                 v2_unexit["resolution_reason"] == "UNEXITABLE_TIMEOUT"
                 and abs(v2_unexit["realized_r"] + 4.12) < 1e-9, str(v2_unexit["realized_r"]))
    v2_gap = paper.resolve_position(
        dict(v2_setup, decided_utc="2000-01-01T00:00:00+00:00"),
        {"price_usd": v2_setup["entry_price_usd"] * 0.40}, exit_v2)
    ok &= _check("EXIT_V2 stop gap fills at worse observed price, below -1R",
                 v2_gap["resolution_reason"] == "STOP" and v2_gap["realized_r"] < -1.0,
                 str(v2_gap["realized_r"]))
    fast = frozen_spec("MEMEBOT_FAST")
    ok &= _check("FAST loads with a short horizon (< base)", fast["horizon_minutes"] < spec["horizon_minutes"],
                 f"{fast['horizon_minutes']}m vs {spec['horizon_minutes']}m")
    ok &= _check("FAST carries a dead_exit spec; base does not",
                 isinstance(fast.get("dead_exit"), dict) and spec.get("dead_exit") is None)
    ok &= _check("FAST ledger paths are separate from base",
                 fast["_paths"]["prereg_log"] != spec["_paths"]["prereg_log"])

    # --- MEMEBOT_QUICK: identical to FAST but a SHORTER horizon (the owner's speed thesis) ---
    quick = frozen_spec("MEMEBOT_QUICK")
    ok &= _check("QUICK horizon is SHORTER than FAST (15m < 25m)",
                 quick["horizon_minutes"] == 15 and quick["horizon_minutes"] < fast["horizon_minutes"],
                 f"{quick['horizon_minutes']}m vs FAST {fast['horizon_minutes']}m")
    ok &= _check("QUICK keeps FAST's target/stop/screen (only the horizon differs)",
                 quick["target_frac"] == fast["target_frac"] and quick["stop_frac"] == fast["stop_frac"]
                 and quick["screen"] == fast["screen"] and isinstance(quick.get("dead_exit"), dict))
    ok &= _check("QUICK ledger paths are separate from FAST",
                 quick["_paths"]["prereg_log"] != fast["_paths"]["prereg_log"])

    fast_setup = paper.build_entry(_coin(), clean, fast, control=False)
    ok &= _check("same coin -> DIFFERENT entry hash across variants (distinct commitment)",
                 fast_setup["setup_sha256"] != setup["setup_sha256"])
    old = "2000-01-01T00:00:00+00:00"
    # flat price + ~zero recent trades, held past after_minutes -> DEAD_EXIT
    dead_mark = {"price_usd": fast_setup["entry_price_usd"] * 1.02, "buys": 0, "sells": 1}
    dead_res = paper.resolve_position(dict(fast_setup, decided_utc=old), dead_mark, fast)
    ok &= _check("FAST flat corpse with ~no trades -> DEAD_EXIT",
                 dead_res is not None and dead_res["resolution_reason"] == "DEAD_EXIT",
                 str(dead_res and dead_res["resolution_reason"]))
    # active coin (many recent trades) at a flat price is NOT dead -> holds to horizon mark
    alive_mark = {"price_usd": fast_setup["entry_price_usd"] * 1.02, "buys": 30, "sells": 20}
    alive_res = paper.resolve_position(dict(fast_setup, decided_utc=old), alive_mark, fast)
    ok &= _check("FAST flat-but-ACTIVE coin is NOT dead-exited",
                 alive_res is not None and alive_res["resolution_reason"] != "DEAD_EXIT",
                 str(alive_res and alive_res["resolution_reason"]))
    # feed cannot report activity -> never kill on absence (before horizon: stays open)
    absent = paper.resolve_position(fast_setup, {"price_usd": fast_setup["entry_price_usd"]}, fast)
    ok &= _check("FAST never kills on absent buys/sells (fresh position stays OPEN)", absent is None)
    # base variant (no dead_exit) never dead-exits on the same flat corpse
    base_dead = paper.resolve_position(dict(setup, decided_utc=old), dead_mark, spec)
    ok &= _check("base variant does NOT dead-exit (no dead_exit spec)",
                 base_dead is not None and base_dead["resolution_reason"] != "DEAD_EXIT",
                 str(base_dead and base_dead["resolution_reason"]))

    # --- MEMEBOT_RUNNER parallel variant: high +110% take-profit + dead-exit, distinct frozen object ---
    runner = frozen_spec("MEMEBOT_RUNNER")
    ok &= _check("RUNNER take-profit is HIGH (not the fixed +50% cap)",
                 runner["target_frac"] > fast["target_frac"] and runner["target_frac"] >= 1.10,
                 f"target_frac {runner['target_frac']} vs FAST {fast['target_frac']}")
    ok &= _check("RUNNER keeps a dead_exit spec (cut losers cheaply so winners can run)",
                 isinstance(runner.get("dead_exit"), dict))
    ok &= _check("RUNNER ledger paths are separate from base and FAST",
                 len({runner["_paths"]["prereg_log"], fast["_paths"]["prereg_log"],
                      spec["_paths"]["prereg_log"]}) == 3)
    runner_setup = paper.build_entry(_coin(), clean, runner, control=False)
    # A resolved TARGET pays the fat tail: R = (target_frac - 2*toll)/stop_frac, well above the +1.88R
    # of the fixed-50% bots.
    tgt_mark = {"price_usd": runner_setup["target_price_usd"], "buys": 5, "sells": 5}
    tgt_res = paper.resolve_position(dict(runner_setup, decided_utc="2000-01-01T00:00:00+00:00"),
                                     tgt_mark, runner)
    ok &= _check("RUNNER TARGET resolves to a fat-tail R (> +1.88R of the 50% bots)",
                 tgt_res is not None and tgt_res["resolution_reason"] == "TARGET"
                 and tgt_res["realized_r"] > 1.88,
                 str(tgt_res and (tgt_res["resolution_reason"], tgt_res["realized_r"])))

    # --- MEMEBOT_G73 parallel variant: the updated best evo genome (106m/+111%), MINUS flow-exit ---
    g73 = frozen_spec("MEMEBOT_G73")
    ok &= _check("G73 take-profit is HIGH (+111%, the g73c7da genome, not the +50% cap)",
                 g73["target_frac"] >= 1.11 and g73["target_frac"] > fast["target_frac"],
                 f"target_frac {g73['target_frac']}")
    ok &= _check("G73 horizon is the g73c7da 106-min hold (longer than RUNNER's 90)",
                 g73["horizon_minutes"] == 106 and g73["horizon_minutes"] > runner["horizon_minutes"],
                 f"{g73['horizon_minutes']}m vs RUNNER {runner['horizon_minutes']}m")
    ok &= _check("G73 keeps a dead_exit spec (cut losers cheaply so winners can run)",
                 isinstance(g73.get("dead_exit"), dict))
    ok &= _check("G73 carries NO flow-exit (frozen executor does not implement one; not faked)",
                 g73.get("flow_exit") is None and "flow_exit" not in g73)
    ok &= _check("G73 ledger paths are separate from base/FAST/RUNNER",
                 len({g73["_paths"]["prereg_log"], runner["_paths"]["prereg_log"],
                      fast["_paths"]["prereg_log"], spec["_paths"]["prereg_log"]}) == 4)

    # --- score + kill: negative stream halts only after N_min ---
    losers = [{"realized_r": -1.1, "control": False, "resolution_reason": "STOP"}] * 5
    rep = scoring.score(spec, losers)
    ok &= _check("below N_min -> NO VERDICT", not rep["readable"]
                 and "NO VERDICT" in rep["verdict"])
    ok &= _check("kill not evaluable below N_min", "not evaluable" in rep["kill_switch"]["verdict"]
                 or rep["kill_switch"]["verdict"].startswith("ALIVE"))
    big_neg = [{"realized_r": -1.1, "control": False, "resolution_reason": "STOP"}] * spec["kill_switch"]["N_min"]
    rep2 = scoring.score(spec, big_neg)
    ok &= _check("clearly-negative stream past N_min -> HALTED",
                 rep2["kill_switch"]["verdict"].startswith("HALTED"))

    print("\nSELFTEST:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(run_selftest())
