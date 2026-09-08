#!/usr/bin/env python3
"""Hermetic wiring check + a DETERMINISTIC offline demonstration of the selection / K-bar / confirmation
machinery. NO network. NO real orders. The synthetic R streams here are LABELLED WIRING, NOT EVIDENCE --
they exist only to prove the arithmetic (ranking, the sqrt(2 ln K) bar, breeding, the fresh-slice
confirmation gate) runs end-to-end on CPU. Real numbers come only from forward paper trades.
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import random
import tempfile

from . import genome as G, evo_paper, stats, engine


def _ok(msg: str) -> None:
    print(f"  ok   {msg}")


def _unit_checks() -> None:
    print("[1] genome + spec")
    g = G._base_seed()
    assert G.genome_id(g) == G.genome_id(dict(g)), "id must be deterministic"
    spec = G.build_spec(g)
    assert spec["toll_per_side"] == G.TOLL_PER_SIDE and spec["horizon_minutes"] == 180
    assert spec["dead_exit"] is None and spec["flow_exit"] is None
    fast = G.build_spec(G._fast_seed()); assert fast["dead_exit"] is not None
    flow = G.build_spec(G._flow_seed()); assert flow["flow_exit"] is not None
    vt = G.build_spec(G._vol_tight_seed())
    assert vt["use_vol_exits"] == 1 and vt["stop_vol_mult"] == 1.0 and vt["target_vol_mult"] == 2.0
    assert spec["use_vol_exits"] == 0, "base seed must default to the fixed-percent exit path"
    # A genome seeded BEFORE the adaptive feature (missing the new keys) must still build cleanly.
    legacy = {k: v for k, v in G._base_seed().items()
              if k not in ("use_vol_exits", "stop_vol_mult", "target_vol_mult")}
    lspec = G.build_spec(legacy)
    assert lspec["use_vol_exits"] == 0, "legacy genome must fall back to fixed exits, not crash"
    pop = G.seed_population(24)
    assert len(pop) == 24, f"seed population should be 24, got {len(pop)}"
    _ok(f"24 diverse genomes seeded; toll pinned at {G.TOLL_PER_SIDE}, economics not evolved")

    print("[2] evo_paper entry + every exit path (stop/target/flow/dead/horizon)")
    coin = {"pool_address": "PoolX", "price_usd": 1.0, "name": "T/SOL", "buys": 5, "sells": 20}
    old = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=200)).isoformat()

    def _entry(spec):
        e = evo_paper.build_entry(coin, {"verdict": "PASS", "reasons": []}, spec, control=False)
        e["decided_utc"] = old
        e["setup_sha256"] = e["setup_sha256"]  # keep frozen hash; age is driven off decided_utc
        return e

    e = _entry(spec)
    assert evo_paper.resolve_position(e, {"price_usd": 0.5}, spec)["resolution_reason"] == "STOP"
    assert evo_paper.resolve_position(e, {"price_usd": 2.0}, spec)["resolution_reason"] == "TARGET"
    r = evo_paper.resolve_position(e, {"price_usd": 1.0, "buys": 5, "sells": 20}, spec)
    assert r["resolution_reason"] == "HORIZON_MARK", "base has no flow/dead exit"
    fe = _entry(flow)
    rf = evo_paper.resolve_position(fe, {"price_usd": 1.0, "buys": 5, "sells": 20}, flow)
    assert rf["resolution_reason"] == "FLOW_EXIT", "sell/buy 20/5=4 >= ratio should trip flow exit"
    fa = _entry(fast)
    rd = evo_paper.resolve_position(fa, {"price_usd": 1.0, "buys": 0, "sells": 0}, fast)
    assert rd["resolution_reason"] == "DEAD_EXIT", "flat + ~0 trades should trip dead exit"
    missing = evo_paper.resolve_position(
        e, {"price_usd": None, "_data_unavailable": True, "_data_reason": "selftest"}, spec)
    assert missing["resolution_reason"] == "UNPRICED_PROVIDER_UNAVAILABLE"
    assert missing["realized_r"] is None, "provider outage must not masquerade as an executable stop"
    _ok("entry frozen; all exits fire; provider outage is terminal UNPRICED, not a fake market fill")

    print("[2b] adaptive (vol-scaled) exits freeze off the coin's own volatility")
    # No candle cache for 'PoolX' -> measure_vol returns None -> fixed-frac FALLBACK (never a crash).
    ve = evo_paper.build_entry(coin, {"verdict": "PASS", "reasons": []}, vt, control=False)
    assert ve["exit_mode"] == "fixed" and ve["measured_vol"] is None, "no data must fall back to fixed"
    assert abs(ve["stop_frac"] - vt["stop_frac"]) < 1e-9, "fallback stop must equal the fixed gene"
    # Now force a measurable vol (monkeypatch the local-cache read) and prove the stop/target SCALE.
    orig = evo_paper.measure_vol
    try:
        evo_paper.measure_vol = lambda pool: 0.06     # a 'wild' coin: 6% ATR-like unit
        e_wild = evo_paper.build_entry(coin, {"verdict": "PASS", "reasons": []}, vt, control=False)
        evo_paper.measure_vol = lambda pool: 0.01     # a 'calm' coin: 1% ATR-like unit
        e_calm = evo_paper.build_entry(coin, {"verdict": "PASS", "reasons": []}, vt, control=False)
    finally:
        evo_paper.measure_vol = orig
    # stop_frac = max(floor, stop_vol_mult * vol); target_frac = target_vol_mult * vol.
    assert e_wild["exit_mode"] == "vol" and abs(e_wild["stop_frac"] - 1.0 * 0.06) < 1e-9
    assert abs(e_wild["target_frac"] - 2.0 * 0.06) < 1e-9
    # calm coin: 1.0*0.01 = 0.01 is inside the 0.03 toll floor -> clamped up to the floor.
    assert e_calm["stop_frac"] == evo_paper.VOL_STOP_FRAC_FLOOR, "stop can't sit inside the toll"
    assert e_wild["stop_price_usd"] < e_calm["stop_price_usd"], "wild coin gets the WIDER stop"
    _ok(f"adaptive stop is per-coin: wild(6%)->stop {e_wild['stop_frac']:.3f} vs "
        f"calm(1%)->stop {e_calm['stop_frac']:.3f}; frozen into the pre-outcome entry")

    print("[2c] SUB-MINUTE tick resolution walks the Bitquery 1s candles (STOP/TARGET/MOMENTUM/FLOW/HORIZON/UNPRICED)")
    tickdir = pathlib.Path(tempfile.mkdtemp(prefix="memebot_evo_ticks_"))
    orig_dir = evo_paper.BITQUERY_CANDLE_DIR
    evo_paper.BITQUERY_CANDLE_DIR = tickdir
    try:
        base = 1_800_000_000
        decided = dt.datetime.fromtimestamp(base, dt.timezone.utc)
        far = decided + dt.timedelta(seconds=10_000)      # wall-clock well past horizon+grace

        def _mkentry(seed_fn, mint):
            spec = G.build_spec(seed_fn())
            c = {"pool_address": "PoolS", "price_usd": 1.0, "name": "S/SOL", "base_token": mint}
            e = evo_paper.build_entry(c, {"verdict": "PASS", "reasons": []}, spec, control=False)
            e["decided_utc"] = decided.isoformat()
            return e, spec

        def _write(mint, bars):
            with (tickdir / f"{mint}.jsonl").open("w") as fh:
                for b in bars:
                    row = {"t": b["t"], "o": b.get("o", b["c"]), "h": b["h"], "l": b["l"],
                           "c": b["c"], "v": 100.0, "buys": 5, "sells": 5,
                           "buy_vol": b.get("bv", 50.0), "sell_vol": b.get("sv", 50.0)}
                    fh.write(json.dumps(row) + "\n")

        # STOP: scalp stop_frac=0.10 -> stop at 0.90; second bar dips to low 0.85.
        e, sp = _mkentry(G._submin_scalp_30s, "MINT_STOP")
        _write("MINT_STOP", [{"t": base, "h": 1.0, "l": 1.0, "c": 1.0},
                             {"t": base + 1, "h": 1.0, "l": 0.85, "c": 0.88}])
        assert evo_paper.resolve_subminute(e, sp, now=far)["resolution_reason"] == "TICK_STOP"

        # TARGET: scalp target_frac=0.20 -> target at 1.20; a bar prints high 1.25.
        e, sp = _mkentry(G._submin_scalp_30s, "MINT_TGT")
        _write("MINT_TGT", [{"t": base, "h": 1.0, "l": 1.0, "c": 1.0},
                            {"t": base + 1, "h": 1.25, "l": 1.0, "c": 1.2}])
        assert evo_paper.resolve_subminute(e, sp, now=far)["resolution_reason"] == "TICK_TARGET"

        # MOMENTUM: scalp momentum_exit_bps=80 -> +0.9% inside the window fires the take-profit.
        e, sp = _mkentry(G._submin_scalp_30s, "MINT_MOM")
        _write("MINT_MOM", [{"t": base, "h": 1.0, "l": 1.0, "c": 1.0},
                            {"t": base + 1, "h": 1.01, "l": 1.0, "c": 1.009}])
        assert evo_paper.resolve_subminute(e, sp, now=far)["resolution_reason"] == "TICK_MOMENTUM"

        # FLOWFLIP: flow seed, buy fraction collapses after the min hold -> tick flow reversal.
        e, sp = _mkentry(G._submin_flowflip_90s, "MINT_FLIP")
        flip_bars = [{"t": base, "h": 1.0, "l": 1.0, "c": 1.0, "bv": 90.0, "sv": 10.0}]
        for k in range(1, 20):
            flip_bars.append({"t": base + k, "h": 1.01, "l": 0.99, "c": 1.0, "bv": 1.0, "sv": 9.0})
        _write("MINT_FLIP", flip_bars)
        assert evo_paper.resolve_subminute(e, sp, now=far)["resolution_reason"] == "TICK_FLOWFLIP"

        # HORIZON: flat price, nothing trips; past horizon_seconds -> TICK_HORIZON.
        e, sp = _mkentry(G._submin_scalp_30s, "MINT_HZN")
        _write("MINT_HZN", [{"t": base + k, "h": 1.001, "l": 0.999, "c": 1.0} for k in range(0, 40)])
        assert evo_paper.resolve_subminute(e, sp, now=far)["resolution_reason"] == "TICK_HORIZON"

        # UNPRICED: coin absent from the tick feed, past horizon+grace -> honest terminal UNPRICED.
        e, sp = _mkentry(G._submin_scalp_30s, "MINT_ABSENT")
        u = evo_paper.resolve_subminute(e, sp, now=far)
        assert u["resolution_reason"] == "UNPRICED_NO_TICKDATA" and u["realized_r"] is None
        assert u["tick_data_available"] is False and u["status"] == "RESOLVED"

        # STILL-OPEN: within the horizon and no bars yet -> None (never a fabricated fill).
        e, sp = _mkentry(G._submin_scalp_30s, "MINT_OPEN")
        assert evo_paper.resolve_subminute(e, sp, now=decided + dt.timedelta(seconds=5)) is None
        # ---- MOMENTUM-ENTRY: qualification gate + PESSIMISTIC (gap-through) stop fill ----
        # A momentum genome builds as a tick-resolved genome; tp/sl/hold map onto target/stop/horizon.
        msp = G.build_spec(G._momo_tp15_sl15_60s())
        assert msp["use_momentum_entry"] == 1 and msp["use_subminute"] == 1
        assert abs(msp["stop_frac"] - 0.015) < 1e-9 and abs(msp["target_frac"] - 0.015) < 1e-9
        assert msp["horizon_seconds"] == 60
        # Legacy genome (no momentum keys) must still build cleanly as a non-momentum genome.
        assert G.build_spec(G._base_seed())["use_momentum_entry"] == 0

        # A genuine surge qualifies; a flat / sell-dominated / thin tape does NOT.
        eep = base
        surge_bars = [{"t": eep - 18, "c": 1.00, "buy_vol": 90.0, "sell_vol": 5.0, "buys": 4, "sells": 1},
                      {"t": eep - 10, "c": 1.03, "buy_vol": 90.0, "sell_vol": 5.0, "buys": 4, "sells": 1},
                      {"t": eep - 2,  "c": 1.06, "buy_vol": 90.0, "sell_vol": 5.0, "buys": 4, "sells": 1}]
        ok, diag = evo_paper.momentum_entry_qualifies(surge_bars, eep, msp)
        assert ok, f"a +600bps/20s buy-dominated surge must qualify, got {diag}"
        flat_bars = [{"t": eep - 18, "c": 1.00, "buy_vol": 90.0, "sell_vol": 5.0, "buys": 4, "sells": 1},
                     {"t": eep - 2,  "c": 1.001, "buy_vol": 90.0, "sell_vol": 5.0, "buys": 4, "sells": 1}]
        assert not evo_paper.momentum_entry_qualifies(flat_bars, eep, msp)[0], "flat tape must NOT qualify"
        sell_bars = [dict(b, buy_vol=5.0, sell_vol=90.0) for b in surge_bars]
        assert not evo_paper.momentum_entry_qualifies(sell_bars, eep, msp)[0], "sell-dominated must NOT qualify"
        assert not evo_paper.momentum_entry_qualifies(None, eep, msp)[0], "no tick data -> no entry"

        # The ACTUAL scan admission primitive fails closed on missing/stale/future-only tick data.
        assert not evo_paper.tick_entry_data_ready(None, eep)[0]
        assert not evo_paper.tick_entry_data_ready([{"t": eep + 1}], eep)[0]
        assert not evo_paper.tick_entry_data_ready([{"t": eep - 11}], eep)[0]
        assert evo_paper.tick_entry_data_ready([{"t": eep - 10}], eep)[0]

        # PESSIMISTIC stop fill: a bar gaps THROUGH the stop and CLOSES far below it -> fill at the
        # close (the unexitable dump), NOT the intended stop. sl=150bps -> stop at 0.985; bar closes 0.90.
        e, sp = _mkentry(G._momo_tp15_sl15_60s, "MINT_GAP")
        _write("MINT_GAP", [{"t": base, "h": 1.0, "l": 1.0, "c": 1.0},
                            {"t": base + 1, "h": 1.0, "l": 0.90, "c": 0.90}])
        rgap = evo_paper.resolve_subminute(e, sp, now=far)
        assert rgap["resolution_reason"] == "TICK_STOP"
        assert abs(rgap["exit_price_usd"] - 0.90) < 1e-9, "gap-through must fill at the worse close, not the stop"
        # A win at tp=150bps still NETS NEGATIVE after the ~3% round-trip toll (the honesty point).
        e, sp = _mkentry(G._momo_tp15_sl15_60s, "MINT_TPWIN")
        _write("MINT_TPWIN", [{"t": base, "h": 1.0, "l": 1.0, "c": 1.0},
                              {"t": base + 1, "h": 1.02, "l": 1.0, "c": 1.015}])
        rtp = evo_paper.resolve_subminute(e, sp, now=far)
        assert rtp["resolution_reason"] == "TICK_TARGET" and rtp["realized_r"] < 0, \
            "a +150bps win is < the 300bps round-trip toll -> NET NEGATIVE even on a win"
    finally:
        evo_paper.BITQUERY_CANDLE_DIR = orig_dir
    _ok("sub-minute entries require a causal <=10s tick and resolve on real 1s bars; stale/missing refuses")
    _ok("momentum-entry gate qualifies only genuine surges; stop fills pessimistically on gap-through; "
        "a sub-toll TP nets negative even on a win")

    print("[3] stats: noise bar + kill bound")
    assert abs(stats.noise_bar(24) - (2 * __import__("math").log(24)) ** 0.5) < 1e-9
    _r = random.Random(7)
    assert stats.clears_bar([_r.gauss(0.0, 1.0) for _ in range(30)], 24)["beats_noise_bar"] is False
    big = [_r.gauss(1.0, 0.6) for _ in range(30)]   # strong positive mean, real variance -> big t
    assert stats.clears_bar(big, 24)["beats_noise_bar"] is True
    _ok(f"sqrt(2 ln 24) = {stats.noise_bar(24):.3f} SE; clears_bar + kill_bound wired")


def _write_resolutions(ledger_dir: pathlib.Path, gid: str, rs: list, *, t0: dt.datetime) -> None:
    ledger_dir.mkdir(parents=True, exist_ok=True)
    with (ledger_dir / f"{gid}.jsonl").open("a") as fh:
        for i, r in enumerate(rs):
            sha = f"{gid}-{i}-{random.random()}"
            fh.write(json.dumps({"kind": "entry", "status": "OPEN", "control": False,
                                 "genome_id": gid, "setup_sha256": sha,
                                 "stop_frac": 0.25, "toll_per_side": 0.015}) + "\n")
            fh.write(json.dumps({"kind": "resolution", "status": "RESOLVED", "control": False,
                                 "genome_id": gid, "setup_sha256": sha, "realized_r": round(r, 4),
                                 "resolution_reason": "HORIZON_MARK",
                                 "resolved_utc": (t0 + dt.timedelta(seconds=i)).isoformat()}) + "\n")


def _integration_demo() -> None:
    print("[4] OFFLINE generation demo (SYNTHETIC ledgers = wiring, NOT evidence)")
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="memebot_evo_selftest_"))
    engine.LEDGERS = tmp / "ledgers"
    engine.POP_PATH = tmp / "population.json"
    engine.STATE_PATH = tmp / "evo_state.json"
    engine.GENLOG = tmp / "generation_log.jsonl"
    t0 = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=2)

    # ---- Scenario A: pure noise. Nothing should beat the K-corrected bar. ----
    pop = {"genomes": G.seed_population(6), "active": None}
    pop["active"] = sorted(pop["genomes"])
    state = {"generation": 0, "K_all_genome_ids_ever": list(pop["active"]),
             "seen_pool_addresses": [], "candidates": {}, "confirmed_real": {},
             "falsified_on_fresh_slice": {}, "halted": False, "halt_reason": None}
    rng = random.Random(42)
    for gid in pop["active"]:
        _write_resolutions(engine.LEDGERS, gid, [rng.gauss(0.0, 1.0) for _ in range(22)], t0=t0)
    repA = engine._select_and_report(pop, state, [], did_live=False)
    print(f"       A (noise): K={repA['K_genomes_ever_evaluated']} bar="
          f"{repA['K_corrected_noise_bar_SE']} SE | mature={repA['mature_genomes']} | "
          f"anything_beats_bar={repA['anything_beats_bar']} | selection_performed="
          f"{repA['selection']['performed']}")
    print(f"       verdict: {repA['verdict'][:110]}...")
    assert repA["anything_beats_bar"] is False, "pure noise must NOT clear the bar (anti-overfit works)"
    assert repA["selection"]["performed"] is True, "6 mature >= 4 -> a real generation should run"
    _ok("noise population: honest NO-edge, bottom killed + survivors bred (K grew)")

    # ---- Scenario B: one planted strong genome -> clears bar, then confirms on a FRESH slice. ----
    tmp2 = pathlib.Path(tempfile.mkdtemp(prefix="memebot_evo_selftest_"))
    engine.LEDGERS = tmp2 / "ledgers"; engine.GENLOG = tmp2 / "gl.jsonl"
    pop2 = {"genomes": G.seed_population(6)}; pop2["active"] = sorted(pop2["genomes"])
    state2 = {"generation": 0, "K_all_genome_ids_ever": list(pop2["active"]),
              "seen_pool_addresses": [], "candidates": {}, "confirmed_real": {},
              "falsified_on_fresh_slice": {}, "halted": False, "halt_reason": None}
    star = pop2["active"][0]
    for gid in pop2["active"]:
        draws = ([rng.gauss(0.6, 0.9) for _ in range(40)] if gid == star
                 else [rng.gauss(0.0, 1.0) for _ in range(22)])
        _write_resolutions(engine.LEDGERS, gid, draws, t0=t0)
    repB1 = engine._select_and_report(pop2, state2, [], did_live=False)
    declared = repB1["reality_gate_events"]["declared"]
    print(f"       B1: bar={repB1['K_corrected_noise_bar_SE']} SE | best t="
          f"{repB1['best_genome']['forward_t_stat']:.2f} | declared candidates={declared}")
    assert star in declared, "planted strong genome should be DECLARED a candidate"
    # Fresh out-of-sample slice: 22 more strong trades, then re-evaluate the gate.
    _write_resolutions(engine.LEDGERS, star, [rng.gauss(0.6, 0.9) for _ in range(22)],
                       t0=t0 + dt.timedelta(hours=1))
    repB2 = engine._select_and_report(pop2, state2, [], did_live=False)
    confirmed = list(repB2["confirmed_real"])
    print(f"       B2: confirmed_real={confirmed}")
    assert star in confirmed, "planted genome should CONFIRM on the fresh slice -> REAL"
    _ok("planted edge: declared, then CONFIRMED on a fresh out-of-sample slice (gate works both ways)")

    # ---- Scenario C: missing prices cannot manufacture fitness; falsified ids cannot re-declare. ----
    gid = star
    state2["candidates"].pop(gid, None)
    state2["confirmed_real"].pop(gid, None)
    state2["falsified_on_fresh_slice"][gid] = {"falsified_utc": t0.isoformat()}
    events = engine._check_reality_gate(pop2, state2, [gid], len(state2["K_all_genome_ids_ever"]), 0.0)
    assert gid not in state2["candidates"] and gid not in events["declared"]

    missing_gid = "g_missing_test"
    with (engine.LEDGERS / f"{missing_gid}.jsonl").open("a") as fh:
        for i in range(25):
            sha = f"missing-{i}"
            fh.write(json.dumps({"kind": "entry", "control": False, "genome_id": missing_gid,
                                 "setup_sha256": sha, "stop_frac": 0.25,
                                 "toll_per_side": 0.015}) + "\n")
            fh.write(json.dumps({"kind": "resolution", "status": "RESOLVED", "control": False,
                                 "genome_id": missing_gid, "setup_sha256": sha, "realized_r": None,
                                 "resolution_reason": "UNPRICED_NO_TICKDATA",
                                 "resolved_utc": (t0 + dt.timedelta(seconds=i)).isoformat()}) + "\n")
    assert engine.pass_R(missing_gid) == []
    assert len(engine.stress_pass_R(missing_gid)) >= 25 and max(engine.stress_pass_R(missing_gid)) < -1.0
    _ok("UNPRICED rows are full-loss fitness; a falsified genome cannot re-declare")


def run_selftest() -> int:
    print("MEMEBOT_EVO selftest -- CPU-only, no network, no GPU, no neural net. "
          "Synthetic streams are WIRING, not evidence.\n")
    _unit_checks()
    _integration_demo()
    print("\nALL SELFTESTS PASSED. Machinery verified; no edge is claimed. "
          "Real numbers require forward paper trades.")
    return 0
