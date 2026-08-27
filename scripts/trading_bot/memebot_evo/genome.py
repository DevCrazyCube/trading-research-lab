#!/usr/bin/env python3
"""The GENOME -- the tunable parameters of one rule-based strategy variant, with sane bounds.

A genome is a plain dict of genes (screen thresholds + entry/exit rule) plus two boolean switches for
the optional early-exit rules. It is NOT a neural net and carries NO learned weights: it is the exact
same knobs a human would tune on the memebot screen/exit, exposed to a CPU-only genetic search.

Fixed, NON-evolved economics (so evolution cannot cheat by pretending trading is cheaper than it is):
    bankroll_sol, position_fraction, and the ~3% round-trip venue TOLL are constants, identical to the
    memebot. The toll is the house edge the whole programme measured; a search allowed to lower it
    would "discover" a fantasy. It stays pinned.

The genome id is a short sha1 of the canonical gene dict, so identical genomes collapse to one id and
K (the cumulative count of DISTINCT genomes ever evaluated) is counted honestly.
"""

from __future__ import annotations

import hashlib
import json
import random

# ---- Fixed economics (NEVER evolved) -------------------------------------------------------------
BANKROLL_SOL = 10.0
POSITION_FRACTION = 0.02
TOLL_PER_SIDE = 0.015           # ~3% round trip -- the irreducible house edge, pinned

# ---- Gene bounds (inclusive). `int` genes are rounded/clipped to int. ----------------------------
GENE_BOUNDS: dict[str, tuple[float, float]] = {
    # Screen (loss-avoidance filter)
    "min_fdv_usd":          (3_000.0, 50_000.0),
    "min_reserve_usd":      (1_000.0, 30_000.0),
    "min_unique_buyers":    (3, 40),          # int
    "max_buys_per_buyer":   (2.0, 12.0),
    "honeypot_min_buys":    (5, 50),          # int
    "max_pool_age_minutes": (5.0, 60.0),
    # Exit -- horizon + defined risk (the FIXED-percent path; used when use_vol_exits=0)
    "horizon_minutes":      (10, 240),        # int
    "stop_frac":            (0.10, 0.50),
    "target_frac":          (0.20, 1.50),
    # Adaptive (volatility-scaled) exits -- MULTIPLIERS of the coin's own measured volatility unit.
    # Used only when use_vol_exits=1 AND vol is measurable; otherwise the fixed stop_frac/target_frac
    # above are the fallback. Searching over these makes the population choose a stop as a multiple of
    # each coin's own recent range instead of an arbitrary fixed %.
    "stop_vol_mult":        (0.5, 5.0),       # stop distance = stop_vol_mult * vol (fraction of price)
    "target_vol_mult":      (1.0, 10.0),      # target distance = target_vol_mult * vol
    # Dead-coin early exit (a flat corpse with ~zero recent trades)
    "dead_after_minutes":   (2.0, 30.0),
    "dead_max_recent_trades": (0, 5),         # int
    "dead_flat_band":       (0.02, 0.20),
    # Flow-following exit (selling pressure has overtaken buying = pressure reversed)
    "flow_after_minutes":   (2.0, 30.0),
    "flow_sell_buy_ratio":  (1.0, 4.0),
    # ---- SUB-MINUTE family (seconds-to-few-minutes horizon; resolved on the Bitquery 1s TICK feed) --
    # These genes are only consulted when use_subminute=1. A sub-minute position is resolved by walking
    # the coin's per-second OHLCV+flow candles (research/data/memebot_cache/bitquery_candles/{mint}.jsonl)
    # instead of the ~40s GeckoTerminal poll. The pinned ~3% round-trip toll STILL applies per round trip
    # -- on a 30-second hold that is brutal, which is the whole point of the honesty test.
    "horizon_seconds":      (30, 300),        # int -- hard time cap for a sub-minute position
    "momentum_window_s":    (3, 30),          # int -- rolling tick window for the momentum/flow exits
    "momentum_exit_bps":    (20.0, 500.0),    # take-profit: exit if price gains >= X bps within window
    "flowflip_min_seconds": (5.0, 120.0),     # min hold before the tick flow-flip exit can fire
    "flowflip_buy_frac":    (0.20, 0.50),     # exit when rolling 1s buy-vol fraction drops BELOW this
    # ---- MOMENTUM-ENTRY SCALP family (owner's thesis: only buy what is ALREADY moving) ------------
    # Consulted only when use_momentum_entry=1. A coin qualifies for entry ONLY if, from its recent
    # tick data at the entry instant, ALL of: (a) price is up >= entry_surge_bps over the last
    # entry_window_s seconds, (b) the buy-volume fraction over that window >= entry_min_buyfrac, and
    # (c) there were >= entry_min_trades trades in the window (liquidity-of-attention). No surge -> no
    # entry. Then a FAST, disciplined exit: take-profit tp_bps, hard stop sl_bps, hard time cap
    # max_hold_s. The pinned ~3% round-trip toll STILL applies -- a tp below ~300bps NETS NEGATIVE even
    # on a win, which is exactly the honesty test the owner asked for.
    "entry_surge_bps":      (100.0, 1500.0),  # required price gain over the entry window (bps)
    "entry_window_s":       (5, 60),          # int -- lookback window for the surge/flow/trade test
    "entry_min_buyfrac":    (0.55, 0.85),     # required buy-vol fraction over the entry window
    "entry_min_trades":     (3, 40),          # int -- required # trades (buys+sells) over the window
    "tp_bps":               (50.0, 600.0),    # take-profit distance (bps) -- the "small profit FAST"
    "sl_bps":               (50.0, 400.0),    # hard stop distance (bps) -- "cut losers immediately"
    "max_hold_s":           (10, 180),        # int -- hard time cap for a momentum scalp
}
INT_GENES = {"min_unique_buyers", "honeypot_min_buys", "horizon_minutes", "dead_max_recent_trades",
             "horizon_seconds", "momentum_window_s",
             "entry_window_s", "entry_min_trades", "max_hold_s"}
FLAG_GENES = ("use_dead_exit", "use_flow_exit", "use_vol_exits",
              "use_subminute", "use_tick_momentum", "use_tick_flowflip",
              "use_momentum_entry")   # 0/1 optional-rule switches

# Legacy-safe defaults for genes/flags a genome seeded BEFORE the sub-minute family may not carry.
# crossover/mutate/build_spec all read new genes through these so a legacy genome never KeyErrors and
# builds cleanly as a minute-level genome (use_subminute defaults to 0).
GENE_DEFAULTS: dict[str, float] = {
    "horizon_seconds": 60, "momentum_window_s": 10, "momentum_exit_bps": 150.0,
    "flowflip_min_seconds": 20.0, "flowflip_buy_frac": 0.35,
    # Momentum-entry family defaults (legacy genomes lack these; they build as use_momentum_entry=0).
    "entry_surge_bps": 300.0, "entry_window_s": 20, "entry_min_buyfrac": 0.60,
    "entry_min_trades": 5, "tp_bps": 200.0, "sl_bps": 150.0, "max_hold_s": 60,
}


def _gene_default(name: str) -> float:
    return GENE_DEFAULTS.get(name, GENE_BOUNDS[name][0])


def _clip(name: str, value: float) -> float:
    lo, hi = GENE_BOUNDS[name]
    value = max(lo, min(hi, value))
    return int(round(value)) if name in INT_GENES else round(float(value), 6)


def random_genome(rng: random.Random) -> dict:
    """A fresh random genome uniformly within bounds (diversity injection)."""
    g = {name: _clip(name, rng.uniform(lo, hi)) for name, (lo, hi) in GENE_BOUNDS.items()}
    for flag in FLAG_GENES:
        g[flag] = rng.randint(0, 1)
    return g


def canonical(genome: dict) -> str:
    body = {k: genome[k] for k in sorted(genome) if not k.startswith("_")}
    return json.dumps(body, sort_keys=True, separators=(",", ":"))


def genome_id(genome: dict) -> str:
    return "g" + hashlib.sha1(canonical(genome).encode()).hexdigest()[:11]


def mutate(genome: dict, rng: random.Random, *, rate: float = 0.30, scale: float = 0.20) -> dict:
    """Perturb genes within bounds. Each gene mutates with probability `rate` by a gaussian step of
    `scale` * (range). Flags flip with probability `rate`/2. Always clipped back inside bounds."""
    child = dict(genome)
    for name, (lo, hi) in GENE_BOUNDS.items():
        if rng.random() < rate:
            step = rng.gauss(0.0, scale * (hi - lo))
            child[name] = _clip(name, child.get(name, _gene_default(name)) + step)
    for flag in FLAG_GENES:
        if rng.random() < rate / 2.0:
            child[flag] = 1 - child.get(flag, 0)
    return child


def crossover(a: dict, b: dict, rng: random.Random) -> dict:
    """Uniform crossover: each gene/flag taken from parent a or b with equal probability."""
    child = {}
    for name in GENE_BOUNDS:
        d = _gene_default(name)
        child[name] = a.get(name, d) if rng.random() < 0.5 else b.get(name, d)
    for flag in FLAG_GENES:
        child[flag] = a.get(flag, 0) if rng.random() < 0.5 else b.get(flag, 0)
    return child


def build_spec(genome: dict) -> dict:
    """Map a genome to a memebot-compatible spec dict consumed by ..memebot.screen.screen_coin and by
    this package's evo_paper. `instrument_id` = genome id. Economics are the pinned constants."""
    gid = genome_id(genome)
    dead_exit = None
    if genome.get("use_dead_exit"):
        dead_exit = {
            "after_minutes": genome["dead_after_minutes"],
            "max_recent_trades": genome["dead_max_recent_trades"],
            "flat_band": genome["dead_flat_band"],
        }
    flow_exit = None
    if genome.get("use_flow_exit"):
        flow_exit = {
            "after_minutes": genome["flow_after_minutes"],
            "sell_buy_ratio": genome["flow_sell_buy_ratio"],
        }
    # A momentum-entry genome IS a tick-resolved genome whose fast exit is expressed in bps + seconds.
    # Map tp_bps/sl_bps/max_hold_s onto the tick resolver's fixed stop/target/horizon so the SAME
    # tested resolve_subminute walk prices it -- no separate exit code path, no optimistic shortcut.
    use_momo = int(genome.get("use_momentum_entry", 0))
    if use_momo:
        eff_use_subminute = 1
        eff_use_vol_exits = 0
        eff_stop_frac = genome.get("sl_bps", GENE_DEFAULTS["sl_bps"]) / 1e4
        eff_target_frac = genome.get("tp_bps", GENE_DEFAULTS["tp_bps"]) / 1e4
        eff_horizon_seconds = int(genome.get("max_hold_s", GENE_DEFAULTS["max_hold_s"]))
    else:
        eff_use_subminute = int(genome.get("use_subminute", 0))
        eff_use_vol_exits = int(genome.get("use_vol_exits", 0))
        eff_stop_frac = genome["stop_frac"]
        eff_target_frac = genome["target_frac"]
        eff_horizon_seconds = int(genome.get("horizon_seconds", GENE_DEFAULTS["horizon_seconds"]))

    return {
        "instrument_id": gid,
        "genome_id": gid,
        "bankroll_sol": BANKROLL_SOL,
        "position_fraction": POSITION_FRACTION,
        "toll_per_side": TOLL_PER_SIDE,
        "horizon_minutes": genome["horizon_minutes"],
        "stop_frac": eff_stop_frac,
        "target_frac": eff_target_frac,
        # Adaptive-exit genes. .get() defaults keep genomes seeded BEFORE this feature (which lack the
        # keys) building cleanly: they behave as fixed-percent (use_vol_exits=0), unchanged.
        "use_vol_exits": eff_use_vol_exits,
        "stop_vol_mult": genome.get("stop_vol_mult", GENE_BOUNDS["stop_vol_mult"][0]),
        "target_vol_mult": genome.get("target_vol_mult", GENE_BOUNDS["target_vol_mult"][0]),
        # Sub-minute (TICK-resolved) genes. .get() defaults keep every legacy genome building as a
        # minute-level genome (use_subminute=0) even though it lacks these keys.
        "use_subminute": eff_use_subminute,
        "horizon_seconds": eff_horizon_seconds,
        "momentum_window_s": int(genome.get("momentum_window_s", GENE_DEFAULTS["momentum_window_s"])),
        "momentum_exit_bps": genome.get("momentum_exit_bps", GENE_DEFAULTS["momentum_exit_bps"]),
        "flowflip_min_seconds": genome.get("flowflip_min_seconds", GENE_DEFAULTS["flowflip_min_seconds"]),
        "flowflip_buy_frac": genome.get("flowflip_buy_frac", GENE_DEFAULTS["flowflip_buy_frac"]),
        "use_tick_momentum": int(genome.get("use_tick_momentum", 0)),
        "use_tick_flowflip": int(genome.get("use_tick_flowflip", 0)),
        # Momentum-entry SCALP genes. .get() defaults keep every legacy genome building as a
        # non-momentum genome (use_momentum_entry=0) even though it lacks these keys. When the flag is
        # on, the coin must show a genuine surge (see resolve/qualify), and the fast exit is driven by
        # tp_bps/sl_bps/max_hold_s -- which are mapped onto the tick resolver's stop/target/horizon
        # below so the SAME tested tick walk resolves the position.
        "use_momentum_entry": int(genome.get("use_momentum_entry", 0)),
        "entry_surge_bps": genome.get("entry_surge_bps", GENE_DEFAULTS["entry_surge_bps"]),
        "entry_window_s": int(genome.get("entry_window_s", GENE_DEFAULTS["entry_window_s"])),
        "entry_min_buyfrac": genome.get("entry_min_buyfrac", GENE_DEFAULTS["entry_min_buyfrac"]),
        "entry_min_trades": int(genome.get("entry_min_trades", GENE_DEFAULTS["entry_min_trades"])),
        "tp_bps": genome.get("tp_bps", GENE_DEFAULTS["tp_bps"]),
        "sl_bps": genome.get("sl_bps", GENE_DEFAULTS["sl_bps"]),
        "max_hold_s": int(genome.get("max_hold_s", GENE_DEFAULTS["max_hold_s"])),
        "dead_exit": dead_exit,
        "flow_exit": flow_exit,
        "screen": {
            "min_fdv_usd": genome["min_fdv_usd"],
            "min_reserve_usd": genome["min_reserve_usd"],
            "min_unique_buyers": genome["min_unique_buyers"],
            "max_buys_per_buyer": genome["max_buys_per_buyer"],
            "honeypot_min_buys": genome["honeypot_min_buys"],
            "max_pool_age_minutes": genome["max_pool_age_minutes"],
        },
    }


# ---- Seed genomes: 3 named + fresh random, diverse on purpose -------------------------------------
def _base_seed() -> dict:
    """MEMEBOT1's frozen genome: 180-min horizon, no early exit (the running base)."""
    return {
        "min_fdv_usd": 7000.0, "min_reserve_usd": 3000.0, "min_unique_buyers": 10,
        "max_buys_per_buyer": 4.0, "honeypot_min_buys": 15, "max_pool_age_minutes": 30.0,
        "horizon_minutes": 180, "stop_frac": 0.25, "target_frac": 0.5,
        "stop_vol_mult": 2.0, "target_vol_mult": 4.0,
        "dead_after_minutes": 5.0, "dead_max_recent_trades": 1, "dead_flat_band": 0.08,
        "flow_after_minutes": 8.0, "flow_sell_buy_ratio": 1.5,
        "use_dead_exit": 0, "use_flow_exit": 0, "use_vol_exits": 0,
    }


def _fast_seed() -> dict:
    """MEMEBOT_FAST's frozen genome: ~25-min horizon + dead-coin early exit."""
    g = _base_seed()
    g.update(horizon_minutes=25, dead_after_minutes=5.0, dead_max_recent_trades=1,
             dead_flat_band=0.08, use_dead_exit=1)
    return g


def _flow_seed() -> dict:
    """A flow-following seed: short horizon, exit when sell/buy pressure reverses."""
    g = _base_seed()
    g.update(horizon_minutes=40, flow_after_minutes=8.0, flow_sell_buy_ratio=1.5, use_flow_exit=1)
    return g


def _vol_tight_seed() -> dict:
    """Adaptive-exit seed: a TIGHT stop (1.0x the coin's own recent volatility) with a 2R target.
    Falls back to the fixed stop_frac/target_frac only when the coin has too little candle data."""
    g = _base_seed()
    g.update(horizon_minutes=60, use_vol_exits=1, stop_vol_mult=1.0, target_vol_mult=2.0)
    return g


def _vol_wide_seed() -> dict:
    """Adaptive-exit seed: a WIDE stop (3.0x the coin's own recent volatility) with a ~2R target,
    so a wild coin is given room and a calm coin a tight stop -- both from the same multipliers."""
    g = _base_seed()
    g.update(horizon_minutes=120, use_vol_exits=1, stop_vol_mult=3.0, target_vol_mult=6.0)
    return g


NAMED_SEEDS = {"BASE_180m": _base_seed, "FAST_25m_dead": _fast_seed, "FLOW_follow": _flow_seed,
               "VOL_TIGHT": _vol_tight_seed, "VOL_WIDE": _vol_wide_seed}


# ---- SUB-MINUTE seeds (TICK-resolved, seconds-to-few-minutes) ------------------------------------
# These are the one genuinely-new experiment: seconds-scale tactics resolved on the Bitquery 1s tick
# feed. They are NOT in NAMED_SEEDS (which is frozen at the original seed() run); they are injected
# IN PLACE into the live population by engine.extend_subminute(), preserving all accumulated trades.
def _submin_base() -> dict:
    """A sub-minute genome: fixed (non-vol) stop/target, tick momentum take-profit, 60s hard cap."""
    g = _base_seed()
    g.update(
        use_subminute=1, use_vol_exits=0,
        horizon_seconds=60, momentum_window_s=10, momentum_exit_bps=150.0,
        flowflip_min_seconds=20.0, flowflip_buy_frac=0.35,
        use_tick_momentum=1, use_tick_flowflip=0,
        stop_frac=0.12, target_frac=0.30,
    )
    return g


def _submin_momentum_60s() -> dict:
    """Ride a micro-pop for up to 60s, take profit on a momentum spike, hard stop 12%."""
    g = _submin_base()
    g.update(horizon_seconds=60, momentum_window_s=10, momentum_exit_bps=150.0,
             use_tick_momentum=1, use_tick_flowflip=0, stop_frac=0.12, target_frac=0.30)
    return g


def _submin_scalp_30s() -> dict:
    """Aggressive 30s scalp: tiny 5s window, an 80bps take-profit, tightest 10% stop."""
    g = _submin_base()
    g.update(horizon_seconds=30, momentum_window_s=5, momentum_exit_bps=80.0,
             use_tick_momentum=1, use_tick_flowflip=0, stop_frac=0.10, target_frac=0.20)
    return g


def _submin_flowflip_90s() -> dict:
    """Hold up to 90s, exit when the 1s buy-vol fraction flips below 0.40 (tick-level flow reversal)."""
    g = _submin_base()
    g.update(horizon_seconds=90, momentum_window_s=15, flowflip_min_seconds=15.0,
             flowflip_buy_frac=0.40, use_tick_momentum=0, use_tick_flowflip=1,
             stop_frac=0.15, target_frac=0.40)
    return g


def _submin_momo_flow_120s() -> dict:
    """Both tick exits armed over a 120s cap: momentum take-profit OR flow-flip, whichever fires first."""
    g = _submin_base()
    g.update(horizon_seconds=120, momentum_window_s=15, momentum_exit_bps=200.0,
             flowflip_min_seconds=30.0, flowflip_buy_frac=0.35,
             use_tick_momentum=1, use_tick_flowflip=1, stop_frac=0.15, target_frac=0.50)
    return g


SUBMIN_SEEDS = {"SUBMIN_MOMENTUM_60s": _submin_momentum_60s, "SUBMIN_SCALP_30s": _submin_scalp_30s,
                "SUBMIN_FLOWFLIP_90s": _submin_flowflip_90s, "SUBMIN_MOMO_FLOW_120s": _submin_momo_flow_120s}


# ---- MOMENTUM-ENTRY SCALP seeds (owner's thesis: ONLY buy coins already pumping, take profit fast) --
# These enter ONLY on a confirmed surge (price up over a short window, buy-dominated flow, real trade
# count) and exit fast on tp_bps / sl_bps / max_hold_s. They are tick-resolved (use_momentum_entry=1
# forces use_subminute=1 in build_spec). Injected IN PLACE by engine.extend_momentum(), preserving all
# accumulated trades. NOTE the pinned ~3% round-trip toll: a tp below ~300bps loses even on a WIN.
def _momo_base() -> dict:
    g = _base_seed()
    g.update(
        use_momentum_entry=1, use_subminute=1, use_vol_exits=0,
        use_tick_momentum=0, use_tick_flowflip=0,
        entry_surge_bps=300.0, entry_window_s=20, entry_min_buyfrac=0.60, entry_min_trades=5,
        tp_bps=200.0, sl_bps=150.0, max_hold_s=60,
    )
    return g


def _momo_tp15_sl15_60s() -> dict:
    """Tight symmetric scalp: enter on a 300bps/20s surge, take +150bps, cut at -150bps, cap 60s.
    Its tp is BELOW the ~300bps round-trip toll on purpose -- the honesty stress case."""
    g = _momo_base()
    g.update(entry_surge_bps=300.0, entry_window_s=20, entry_min_buyfrac=0.60, entry_min_trades=5,
             tp_bps=150.0, sl_bps=150.0, max_hold_s=60)
    return g


def _momo_fast_tp30_sl20_30s() -> dict:
    """Fast 30s scalp on a sharper 400bps/15s surge: take +300bps (~= the toll, so a win ~ breakeven),
    cut at -200bps."""
    g = _momo_base()
    g.update(entry_surge_bps=400.0, entry_window_s=15, entry_min_buyfrac=0.65, entry_min_trades=6,
             tp_bps=300.0, sl_bps=200.0, max_hold_s=30)
    return g


def _momo_strong_surge() -> dict:
    """Only the STRONG pumps: require an 800bps/30s surge with 0.70 buy fraction and >=8 trades; give a
    +500bps target (clears the toll) against a -250bps stop, cap 90s. The 'only buy real momentum' seed."""
    g = _momo_base()
    g.update(entry_surge_bps=800.0, entry_window_s=30, entry_min_buyfrac=0.70, entry_min_trades=8,
             tp_bps=500.0, sl_bps=250.0, max_hold_s=90)
    return g


def _momo_ride_tp60_sl30_120s() -> dict:
    """Ride the pump: enter on 250bps/30s, aim +600bps with a -300bps stop over 120s, and arm the tick
    FLOW-FLIP so it sells into strength when buy-vol fraction rolls over (sell-into-strength exit)."""
    g = _momo_base()
    g.update(entry_surge_bps=250.0, entry_window_s=30, entry_min_buyfrac=0.55, entry_min_trades=5,
             tp_bps=600.0, sl_bps=300.0, max_hold_s=120,
             use_tick_flowflip=1, flowflip_min_seconds=20.0, flowflip_buy_frac=0.40, momentum_window_s=15)
    return g


MOMENTUM_SEEDS = {"MOMO_TP15_SL15_60s": _momo_tp15_sl15_60s,
                  "MOMO_FAST_TP30_SL20_30s": _momo_fast_tp30_sl20_30s,
                  "MOMO_STRONG_SURGE": _momo_strong_surge,
                  "MOMO_RIDE_TP60_SL30_120s": _momo_ride_tp60_sl30_120s}


def seed_population(size: int, seed: int = 20260825) -> dict:
    """Return {genome_id: genome} of `size` diverse genomes: the 3 named seeds + fresh random."""
    rng = random.Random(seed)
    pop: dict[str, dict] = {}
    for make in NAMED_SEEDS.values():
        g = make()
        pop[genome_id(g)] = g
    while len(pop) < size:
        g = random_genome(rng)
        pop[genome_id(g)] = g
    return pop
