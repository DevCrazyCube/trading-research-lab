#!/usr/bin/env python3
"""The evolutionary engine -- registry, forward accumulation, selection, breeding, and the honest
generation report. Pure CPU stdlib; no GPU, no neural net, no training.

One GENERATION = accumulate forward paper trades for every ACTIVE genome (reusing the memebot's shared
feed + screen), then -- only if enough genomes have reached the pre-registered minimum of resolved
trades -- rank the MATURE genomes by terminal full-loss-stress mean R, kill the bottom fraction, and breed replacements
from the survivors (crossover + mutation) plus fresh-random diversity. K (cumulative distinct genomes
ever evaluated) only ever grows, and every report states the K-corrected noise bar and whether anything
clears it. Selection is ALWAYS on forward trades the genome was not bred on; the reality gate then
requires a genome to REPEAT above the bar on a FRESH out-of-sample slice before it is called REAL.

Network is bounded regardless of population size: one `new_pools` pull per scan (shared), and one
refresh per UNIQUE open pool per track (shared cache) -- the fan-out over genomes is pure arithmetic.
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import random
import time

from . import Refused
from . import genome as G
from . import evo_paper, stats
from ..memebot import feed, screen as screen_mod
from ..memebot import Refused as MemeRefused

# ---- Frozen search configuration (see EVO_PREREGISTRATION.md) -------------------------------------
POP_SIZE = 24
N_MIN_EVAL = 20                 # resolved PASS trades before a genome is eligible to rank / gate
MIN_MATURE_FOR_SELECTION = 3    # need >= this many mature genomes before a kill/breed generation.
                                # Lowered 4 -> 3 (2026-08-26): 3 strong mature genomes is enough to
                                # SEED a generation. This is an operational GA parameter (when to start
                                # breeding), NOT a strategy/significance threshold -- the K-corrected
                                # noise bar and the reality gate are untouched and still adjudicate edge.
SURVIVE_FRAC = 0.50             # top half of mature genomes survive a generation (once the mature pool
                                # is larger than MIN_SURVIVORS; below that MIN_SURVIVORS governs).
MIN_SURVIVORS = 3               # with a small mature pool, keep at least this many top genomes as the
                                # breeding parents (so all of the top-3 survive and breed a generation);
                                # SURVIVE_FRAC dominates again once the mature pool grows past this.
MIN_CHILDREN_PER_GEN = 4        # breed at least this many children from the survivors each selection, so
                                # a low/zero-kill generation still forward-tests the survivors' bred
                                # signature (bounded by POP_CEILING so the loop cannot balloon).
POP_CEILING = 60                # hard cap on the active population: kill-free breeding stops here, so the
                                # continuous 180s loop cannot grow the population without bound.
FRESH_FRAC = 0.20               # fraction of each new generation drawn fresh-random
MUT_RATE = 0.30
MUT_SCALE = 0.20
M_GENERATIONS_KILL = 8          # HALT if no confirmed edge after this many real generations
MAX_NEW_PER_SCAN = 4
MAX_CONTROL_PER_SCAN = 2
MAX_OPEN_PER_GENOME = 8
MAX_REFRESH_CALLS_PER_TRACK = 10
REFRESH_WALLCLOCK_BUDGET_S = 45.0
SCHEMA_VERSION = 1
FITNESS_VERSION = 2                 # terminal full-loss stress; v1 excluded UNPRICED outcomes

PKG_DIR = pathlib.Path(__file__).resolve().parent
LEDGERS = PKG_DIR / "ledgers"
POP_PATH = PKG_DIR / "population.json"
STATE_PATH = PKG_DIR / "evo_state.json"
GENLOG = PKG_DIR / "generation_log.jsonl"


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


# ---- Per-genome ledger (own sub-ledger under ledgers/{genome_id}.jsonl) ---------------------------
def _ledger_path(gid: str) -> pathlib.Path:
    return LEDGERS / f"{gid}.jsonl"


def _append(gid: str, record: dict) -> None:
    LEDGERS.mkdir(parents=True, exist_ok=True)
    with _ledger_path(gid).open("a") as fh:
        fh.write(json.dumps(record, sort_keys=True, default=str) + "\n")


def _read_ledger(gid: str) -> list:
    p = _ledger_path(gid)
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


def open_positions(gid: str) -> list:
    recs = _read_ledger(gid)
    resolved = {r["setup_sha256"] for r in recs
                if r.get("kind") == "resolution" and r.get("status") == "RESOLVED"}
    return [r for r in recs if r.get("kind") == "entry" and r["setup_sha256"] not in resolved]


def resolved_stream(gid: str, *, control: bool | None = False) -> list:
    """De-duplicated resolved records for one genome, oldest first. control=False -> PASS trades only,
    control=True -> null trades only, control=None -> both."""
    out, seen = [], set()
    for r in _read_ledger(gid):
        if r.get("kind") != "resolution" or r.get("status") != "RESOLVED":
            continue
        if r["setup_sha256"] in seen or r.get("realized_r") is None:
            continue
        if control is not None and bool(r.get("control")) != control:
            continue
        seen.add(r["setup_sha256"])
        out.append(r)
    out.sort(key=lambda r: r.get("resolved_utc", ""))
    return out


def pass_R(gid: str) -> list:
    return [r["realized_r"] for r in resolved_stream(gid, control=False)]


def terminal_stream(gid: str, *, control: bool | None = False) -> list:
    """Every de-duplicated terminal record, including rows whose executable price was unavailable."""
    out, seen = [], set()
    for r in _read_ledger(gid):
        if r.get("kind") != "resolution" or r.get("status") != "RESOLVED":
            continue
        key = r.get("setup_sha256")
        if not key or key in seen:
            continue
        if control is not None and bool(r.get("control")) != control:
            continue
        seen.add(key)
        out.append(r)
    out.sort(key=lambda r: r.get("resolved_utc", ""))
    return out


def stress_pass_R(gid: str) -> list:
    """Promotion/fitness stream: unavailable or unexitable terminal exits are a full position loss.

    This is a conservative adjudication bound, not a claim that each missing mark was literally zero.
    It prevents the v1 survivorship failure in which a genome improved merely by producing more
    ``UNPRICED`` rows that were silently excluded from ``pass_R``.
    """
    rows = _read_ledger(gid)
    entries = {str(r.get("setup_sha256")): r for r in rows if r.get("kind") == "entry"}
    out: list[float] = []
    for rec in terminal_stream(gid, control=False):
        entry = entries.get(str(rec.get("setup_sha256")))
        r = rec.get("realized_r")
        if r is None or rec.get("resolution_reason") == "UNEXITABLE_TIMEOUT":
            if not entry:
                continue  # visible in reports as terminal-minus-stress count; never fabricate a risk unit
            stop = float(entry.get("stop_frac") or 0.0)
            toll = float(entry.get("toll_per_side") or 0.0)
            if stop <= 0:
                continue
            r = (-1.0 - 2.0 * toll) / stop
        out.append(float(r))
    return out


# ---- Population + state persistence ---------------------------------------------------------------
def load_pop() -> dict:
    if not POP_PATH.exists():
        raise Refused("no population.json -- run `seed` first")
    return json.loads(POP_PATH.read_text())


def save_pop(pop: dict) -> None:
    POP_PATH.write_text(json.dumps(pop, indent=2, sort_keys=True))


def load_state() -> dict:
    if not STATE_PATH.exists():
        raise Refused("no evo_state.json -- run `seed` first")
    return json.loads(STATE_PATH.read_text())


def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True))


def seed(size: int = POP_SIZE, *, seed_int: int = 20260825) -> dict:
    """Create the initial population and state. Idempotent-refusing: will not clobber an existing run."""
    if POP_PATH.exists() or STATE_PATH.exists():
        raise Refused("a population already exists; refusing to overwrite a running forward search. "
                      "Delete population.json/evo_state.json/ledgers to start a fresh pre-registration.")
    genomes = G.seed_population(size, seed=seed_int)
    active = sorted(genomes)
    pop = {"genomes": genomes, "active": active, "seeded_utc": _now_iso(), "seed_size": size,
           "named_seeds": {name: G.genome_id(make()) for name, make in G.NAMED_SEEDS.items()}}
    state = {
        "schema_version": SCHEMA_VERSION, "created_utc": _now_iso(), "generation": 0,
        "K_all_genome_ids_ever": list(active), "seen_pool_addresses": [],
        "candidates": {}, "confirmed_real": {}, "falsified_on_fresh_slice": {},
        "halted": False, "halt_reason": None,
    }
    save_pop(pop)
    save_state(state)
    LEDGERS.mkdir(parents=True, exist_ok=True)
    return {"seeded": len(genomes), "active": len(active), "K": len(active),
            "named_seed_ids": pop["named_seeds"]}


def extend_population(*, n_random_vol: int = 3, seed_int: int = 20260825) -> dict:
    """Inject the adaptive-exit genomes into the LIVE population IN PLACE, preserving every accumulated
    forward trade (ledgers are untouched; only new genome ids are added to genomes/active/K).

    Adds: the named VOL_TIGHT / VOL_WIDE seeds plus `n_random_vol` fresh random genomes forced to
    use_vol_exits=1, so fixed-vs-adaptive compete head-to-head. Skips any genome id already present.
    Idempotent: re-running only tops up genomes that are missing."""
    pop, state = load_pop(), load_state()
    rng = random.Random(seed_int)

    to_add: dict[str, dict] = {}
    for make in (G._vol_tight_seed, G._vol_wide_seed):
        g = make()
        to_add.setdefault(G.genome_id(g), g)
    attempts = 0
    while sum(1 for g in to_add.values() if g.get("use_vol_exits")) < (2 + n_random_vol) \
            and attempts < 400:
        attempts += 1
        g = G.random_genome(rng)
        g["use_vol_exits"] = 1               # force the adaptive path on for these diversity injectors
        gid = G.genome_id(g)
        if gid not in pop["genomes"] and gid not in to_add:
            to_add[gid] = g

    added = []
    active = list(pop["active"])
    for gid, g in to_add.items():
        if gid in pop["genomes"]:
            if gid not in active:
                active.append(gid)
            continue
        pop["genomes"][gid] = g
        active.append(gid)
        _register(state, gid)
        added.append(gid)

    pop["active"] = sorted(set(active))
    named = pop.get("named_seeds", {})
    named["VOL_TIGHT"] = G.genome_id(G._vol_tight_seed())
    named["VOL_WIDE"] = G.genome_id(G._vol_wide_seed())
    pop["named_seeds"] = named
    save_pop(pop)
    save_state(state)
    return {"added_genomes": added, "population_size": len(pop["active"]), "K": K(state),
            "vol_named_seed_ids": {"VOL_TIGHT": named["VOL_TIGHT"], "VOL_WIDE": named["VOL_WIDE"]},
            "trades_preserved": True}


def extend_subminute(*, n_random_sub: int = 3, seed_int: int = 20260825) -> dict:
    """Inject the SUB-MINUTE (tick-resolved) genomes into the LIVE population IN PLACE, preserving every
    accumulated forward trade (ledgers untouched; only new genome ids join genomes/active/K).

    Adds the 4 named SUBMIN_* seeds plus `n_random_sub` fresh random genomes forced to use_subminute=1,
    so seconds-scale tactics compete head-to-head with the minute-level population. Skips any genome id
    already present; re-running only tops up what is missing (idempotent)."""
    pop, state = load_pop(), load_state()
    rng = random.Random(seed_int + 7)   # distinct stream from the vol-extend

    to_add: dict[str, dict] = {}
    for make in G.SUBMIN_SEEDS.values():
        g = make()
        to_add.setdefault(G.genome_id(g), g)
    attempts = 0
    while sum(1 for g in to_add.values() if g.get("use_subminute")) < (len(G.SUBMIN_SEEDS) + n_random_sub) \
            and attempts < 600:
        attempts += 1
        g = G.random_genome(rng)
        g["use_subminute"] = 1            # force the tick path on for these diversity injectors
        g["use_vol_exits"] = 0            # sub-minute uses fixed stop/target, not the vol-scaled path
        gid = G.genome_id(g)
        if gid not in pop["genomes"] and gid not in to_add:
            to_add[gid] = g

    added = []
    active = list(pop["active"])
    for gid, g in to_add.items():
        if gid in pop["genomes"]:
            if gid not in active:
                active.append(gid)
            continue
        pop["genomes"][gid] = g
        active.append(gid)
        _register(state, gid)
        added.append(gid)

    pop["active"] = sorted(set(active))
    named = pop.get("named_seeds", {})
    for name, make in G.SUBMIN_SEEDS.items():
        named[name] = G.genome_id(make())
    pop["named_seeds"] = named
    save_pop(pop)
    save_state(state)
    return {"added_genomes": added, "population_size": len(pop["active"]), "K": K(state),
            "subminute_named_seed_ids": {n: G.genome_id(m()) for n, m in G.SUBMIN_SEEDS.items()},
            "trades_preserved": True}


def extend_momentum(*, n_random_momo: int = 3, seed_int: int = 20260825) -> dict:
    """Inject the MOMENTUM-ENTRY SCALP genomes into the LIVE population IN PLACE, preserving every
    accumulated forward trade (ledgers untouched; only new genome ids join genomes/active/K).

    Adds the 4 named MOMO_* seeds plus `n_random_momo` fresh random genomes forced to
    use_momentum_entry=1 (and use_subminute=1), so 'only-buy-what-is-pumping' scalps compete
    head-to-head with the rest of the population. Skips any genome id already present; re-running only
    tops up what is missing (idempotent)."""
    pop, state = load_pop(), load_state()
    rng = random.Random(seed_int + 13)   # distinct stream from vol/subminute extends

    named_ids = {G.genome_id(make()) for make in G.MOMENTUM_SEEDS.values()}
    to_add: dict[str, dict] = {}
    for make in G.MOMENTUM_SEEDS.values():
        g = make()
        to_add.setdefault(G.genome_id(g), g)
    # Idempotency: count momentum-random genomes ALREADY in the live population toward the target, so a
    # re-run does NOT keep minting fresh randoms every time (only tops up the shortfall). The 4 named
    # seeds are always ensured above; here we fill only the random quota.
    present_random = sum(1 for gid, g in pop["genomes"].items()
                         if g.get("use_momentum_entry") and gid not in named_ids)
    attempts = 0
    while (present_random + sum(1 for gid in to_add if gid not in named_ids)) \
            < n_random_momo and attempts < 600:
        attempts += 1
        g = G.random_genome(rng)
        g["use_momentum_entry"] = 1       # force the momentum-entry path on for these injectors
        g["use_subminute"] = 1            # momentum scalps are tick-resolved
        g["use_vol_exits"] = 0
        gid = G.genome_id(g)
        if gid not in pop["genomes"] and gid not in to_add:
            to_add[gid] = g

    added = []
    active = list(pop["active"])
    for gid, g in to_add.items():
        if gid in pop["genomes"]:
            if gid not in active:
                active.append(gid)
            continue
        pop["genomes"][gid] = g
        active.append(gid)
        _register(state, gid)
        added.append(gid)

    pop["active"] = sorted(set(active))
    named = pop.get("named_seeds", {})
    for name, make in G.MOMENTUM_SEEDS.items():
        named[name] = G.genome_id(make())
    pop["named_seeds"] = named
    save_pop(pop)
    save_state(state)
    return {"added_genomes": added, "population_size": len(pop["active"]), "K": K(state),
            "momentum_named_seed_ids": {n: G.genome_id(m()) for n, m in G.MOMENTUM_SEEDS.items()},
            "trades_preserved": True}


def subminute_report() -> dict:
    """HONESTY metric: across every sub-minute genome, how many resolved entries had tick data vs were
    UNPRICED, plus both the displayed priced R stream and V2 stress fitness. Read-only."""
    pop, state = load_pop(), load_state()
    sub_ids = [g for g in pop["active"] if pop["genomes"].get(g, {}).get("use_subminute")]
    priced = unpriced = 0
    reason_counts: dict = {}
    per_genome = []
    for gid in sub_ids:
        g_priced = g_unpriced = 0
        for r in _read_ledger(gid):
            if r.get("kind") != "resolution" or r.get("status") != "RESOLVED":
                continue
            if not r.get("subminute"):
                continue
            reason_counts[r.get("resolution_reason")] = \
                reason_counts.get(r.get("resolution_reason"), 0) + 1
            if r.get("tick_data_available"):
                priced += 1; g_priced += 1
            else:
                unpriced += 1; g_unpriced += 1
        rs = pass_R(gid)
        stress_rs = stress_pass_R(gid)
        per_genome.append({"genome_id": gid, "resolved_pass_R": len(rs),
                           "subminute_priced": g_priced, "subminute_unpriced": g_unpriced,
                           "mean_R": (sum(rs) / len(rs)) if rs else None,
                           "stress_n": len(stress_rs),
                           "stress_mean_R": (sum(stress_rs) / len(stress_rs)) if stress_rs else None})
    total = priced + unpriced
    return {
        "subminute_genomes": len(sub_ids),
        "subminute_resolutions_total": total,
        "priced_on_tick_feed": priced,
        "unpriced_no_tickdata": unpriced,
        "tick_data_available_fraction": round(priced / total, 4) if total else None,
        "resolution_reason_counts": reason_counts,
        "per_genome": sorted(per_genome, key=lambda x: -x["resolved_pass_R"]),
        "note": ("Sub-minute R is measured on the Bitquery 1s tick feed; UNPRICED entries (coin not in "
                 "the feed) remain excluded from the DISPLAYED priced R, but V2 selection/promotion "
                 "charges them at the full-loss bound. The ~3% round-trip toll is pinned."),
    }


def _register(state: dict, gid: str) -> None:
    if gid not in state["K_all_genome_ids_ever"]:
        state["K_all_genome_ids_ever"].append(gid)


def K(state: dict) -> int:
    return len(state["K_all_genome_ids_ever"])


# ---- Forward accumulation: scan (open) + track (resolve), fanned out over the population ----------
def _scan_spec(pop: dict) -> dict:
    """A throwaway spec for the shared new_pools / pumpportal pull (feed ignores screen except age)."""
    max_age = max((pop["genomes"][g]["max_pool_age_minutes"] for g in pop["active"]), default=30.0)
    return {"screen": {"max_pool_age_minutes": max_age}}


def scan_once(pop: dict, state: dict, *, pages: int = 1) -> dict:
    """Pull+screen the shared feed ONCE, open the same ordered PASS/control selection in each genome."""
    scan_spec = _scan_spec(pop)
    gt_new_pools_ok = True
    try:
        coins = feed.read_new_pools(scan_spec, pages=pages)
    except MemeRefused:
        # Match the fixed MEMEBOT loop: a free-tier GeckoTerminal 429 must not abort tracking,
        # state persistence, selection and the reality gate. PumpPortal remains the bounded fallback.
        coins = []
        gt_new_pools_ok = False
    pp_n = 0
    try:
        seen0 = set(state.get("seen_pool_addresses", []))
        pp = feed.read_pumpportal_candidates(scan_spec, seen0)
        pp_n = len(pp)
        coins = coins + pp
    except MemeRefused:
        pass  # PumpPortal is a bonus discovery source; a drop never blocks the GeckoTerminal path

    seen = set(state.get("seen_pool_addresses", []))
    uniq: dict = {}
    for c in coins:
        addr = c.get("pool_address")
        if addr and addr not in uniq and addr not in seen:
            uniq[addr] = c
    ordered = sorted(uniq.items(), key=lambda kv: kv[0])   # variant-independent deterministic order

    opened_total, control_total = 0, 0
    for gid in pop["active"]:
        spec = G.build_spec(pop["genomes"][gid])
        room = max(0, MAX_OPEN_PER_GENOME - len(open_positions(gid)))
        n_new = n_ctl = 0
        for addr, coin in ordered:
            res = screen_mod.screen_coin(coin, spec)
            if res["verdict"] == "PASS":
                if n_new >= min(room, MAX_NEW_PER_SCAN):
                    continue
                # MOMENTUM-ENTRY GATE: a momentum genome buys ONLY a confirmed live surge. If the coin's
                # tick feed does not show price up >= entry_surge_bps over the window with buy-dominated
                # flow and enough trades, there is NO entry (owner's "only buy what is pumping" rule).
                if spec.get("use_momentum_entry"):
                    import time as _t
                    bars = evo_paper._load_tick_bars(coin.get("base_token"))
                    ok, _diag = evo_paper.momentum_entry_qualifies(bars, _t.time(), spec)
                    if not ok:
                        continue
                try:
                    setup = evo_paper.build_entry(coin, res, spec, control=False)
                except Refused:
                    continue
                _append(gid, setup); n_new += 1; opened_total += 1
            else:
                if n_ctl >= MAX_CONTROL_PER_SCAN:
                    continue
                try:
                    setup = evo_paper.build_entry(coin, res, spec, control=True)
                except Refused:
                    continue
                _append(gid, setup); n_ctl += 1; control_total += 1

    for addr in uniq:
        seen.add(addr)
    state["seen_pool_addresses"] = sorted(seen)[-8000:]
    return {"coins_seen": len(uniq), "gt_new_pools_ok": gt_new_pools_ok,
            "pumpportal_discovered": pp_n,
            "pass_entries_opened": opened_total, "control_entries_opened": control_total}


def track_once(pop: dict, state: dict) -> dict:
    """Refresh every UNIQUE open pool ONCE (shared cache) and resolve each genome with its own exit."""
    scan_spec = _scan_spec(pop)
    cache: dict = {}
    refresh_calls = 0
    started = time.monotonic()

    def _refresh(addr: str) -> dict:
        nonlocal refresh_calls
        if addr not in cache:
            if (refresh_calls >= MAX_REFRESH_CALLS_PER_TRACK
                    or time.monotonic() - started >= REFRESH_WALLCLOCK_BUDGET_S):
                cache[addr] = {"price_usd": None, "_data_unavailable": True,
                               "_data_reason": "refresh_budget_exhausted"}
            else:
                refresh_calls += 1
                try:
                    cache[addr] = feed.refresh_pool(scan_spec, addr)
                except MemeRefused:
                    cache[addr] = {"price_usd": None, "_data_unavailable": True,
                                   "_data_reason": "provider_refused"}
        return cache[addr]

    resolved_total = 0
    sub_priced = sub_unpriced = 0
    for gid in pop["active"]:
        spec = G.build_spec(pop["genomes"][gid])
        for setup in open_positions(gid):
            if setup.get("use_subminute"):
                # SUB-MINUTE: resolve on the coin's Bitquery 1s tick candles (no network refresh).
                rec = evo_paper.resolve_subminute(setup, spec)
                if rec is not None:
                    _append(gid, rec); resolved_total += 1
                    if rec.get("tick_data_available"):
                        sub_priced += 1
                    else:
                        sub_unpriced += 1
            else:
                current = _refresh(setup["pool_address"])
                rec = evo_paper.resolve_position(setup, current, spec)
                if rec is not None:
                    _append(gid, rec); resolved_total += 1
    return {"unique_pools_seen": len(cache), "refresh_calls": refresh_calls,
            "data_unavailable_pools": sum(bool(x.get("_data_unavailable")) for x in cache.values()),
            "resolutions": resolved_total,
            "subminute_priced": sub_priced, "subminute_unpriced": sub_unpriced}


# ---- Selection, breeding, and the reality gate ---------------------------------------------------
def _genome_report(pop: dict, gid: str, k: int) -> dict:
    rs = pass_R(gid)
    stress_rs = stress_pass_R(gid)
    bar = stats.clears_bar(rs, k)
    stress_bar = stats.clears_bar(stress_rs, k)
    exp = stats.expectancy(rs)
    stress_exp = stats.expectancy(stress_rs)
    return {"genome_id": gid, "resolved_pass": len(rs), "mean_R": bar["mean_R"], "t": bar["t"],
            "se": bar["se"], "expectancy_R": exp["expectancy_R"], "win_rate": exp["win_rate"],
            "beats_noise_bar": bar["beats_noise_bar"],
            "resolved_terminal_pass": len(stress_rs), "stress_mean_R": stress_bar["mean_R"],
            "stress_t": stress_bar["t"], "stress_expectancy_R": stress_exp["expectancy_R"],
            "stress_beats_noise_bar": stress_bar["beats_noise_bar"],
            "mature": len(stress_rs) >= N_MIN_EVAL}


def _check_reality_gate(pop: dict, state: dict, mature_ids: list, k: int, bar: float) -> dict:
    """Declare/confirm/falsify candidates. A genome that clears the bar becomes a CANDIDATE; it is only
    REAL once a FRESH slice of >= N_MIN_EVAL later trades ALSO clears the (current K) bar."""
    events = {"declared": [], "confirmed": [], "falsified": [], "suppressed_redeclarations": []}
    # Repair the v1 state bug: a genome falsified on a fresh slice was immediately eligible for
    # re-declaration from its full history in the same call.
    for gid in list(state["candidates"]):
        if gid in state["falsified_on_fresh_slice"]:
            del state["candidates"][gid]
            events["suppressed_redeclarations"].append(gid)
    # 1. Confirm/falsify existing candidates on their fresh (post-declaration) slice.
    for gid, cand in list(state["candidates"].items()):
        full = pass_R(gid)
        stress_full = stress_pass_R(gid)
        # Existing v1 candidates had no stress watermark.  Start a genuinely fresh stress slice now;
        # never retroactively pretend terminal rows were part of their declaration.
        if "stress_watermark_n" not in cand:
            cand["stress_watermark_n"] = len(stress_full)
            continue
        fresh = full[cand["watermark_n"]:]
        stress_fresh = stress_full[cand["stress_watermark_n"]:]
        if len(fresh) < N_MIN_EVAL or len(stress_fresh) < N_MIN_EVAL:
            continue
        res = stats.clears_bar(fresh, k)
        stress_res = stats.clears_bar(stress_fresh, k)
        if res["beats_noise_bar"] and stress_res["beats_noise_bar"]:
            state["confirmed_real"][gid] = {"confirmed_utc": _now_iso(), "fresh_slice": res,
                                             "fresh_stress_slice": stress_res,
                                             "fitness_version": FITNESS_VERSION}
            events["confirmed"].append(gid)
        else:
            state["falsified_on_fresh_slice"][gid] = {
                "falsified_utc": _now_iso(), "fresh_slice": res,
                "fresh_stress_slice": stress_res, "fitness_version": FITNESS_VERSION}
            events["falsified"].append(gid)
        del state["candidates"][gid]
    # 2. Declare new candidates.
    for gid in mature_ids:
        if (gid in state["candidates"] or gid in state["confirmed_real"]
                or gid in state["falsified_on_fresh_slice"]):
            continue
        rs = pass_R(gid)
        stress_rs = stress_pass_R(gid)
        if (stats.clears_bar(rs, k)["beats_noise_bar"]
                and stats.clears_bar(stress_rs, k)["beats_noise_bar"]):
            state["candidates"][gid] = {"declared_gen": state["generation"],
                                        "watermark_n": len(rs),
                                        "stress_watermark_n": len(stress_rs),
                                        "fitness_version": FITNESS_VERSION,
                                        "declared_utc": _now_iso()}
            events["declared"].append(gid)
    return events


def _breed(pop: dict, state: dict, survivors: list, n_children: int, rng: random.Random) -> list:
    """Fill `n_children` new genomes: FRESH_FRAC fresh-random, the rest crossover(survivors)+mutate."""
    children = []
    n_fresh = int(round(FRESH_FRAC * n_children))
    attempts = 0
    while len(children) < n_children and attempts < n_children * 40:
        attempts += 1
        if len(children) < n_fresh or len(survivors) < 2:
            child = G.random_genome(rng)
        else:
            a = pop["genomes"][rng.choice(survivors)]
            b = pop["genomes"][rng.choice(survivors)]
            child = G.mutate(G.crossover(a, b, rng), rng, rate=MUT_RATE, scale=MUT_SCALE)
        cid = G.genome_id(child)
        if cid in pop["genomes"] or cid in [G.genome_id(c) for c in children]:
            continue
        children.append(child)
    return children


def evolve_generation(*, cycles: int = 1, pages: int = 1, live: bool = True) -> dict:
    """Accumulate forward trades (optional live cycles), then run one selection+breed generation if
    enough genomes are mature. Always returns the honest generation report with the K-corrected bar."""
    pop, state = load_pop(), load_state()
    if state.get("halted"):
        return {"halted": True, "halt_reason": state.get("halt_reason"),
                "note": "search HALTED; no further generations. See report below.",
                "report": _last_report(pop, state)}

    accum = []
    if live:
        for _ in range(max(1, cycles)):
            t = track_once(pop, state)
            s = scan_once(pop, state, pages=pages)
            accum.append({"track": t, "scan": s})
        save_state(state)

    return _select_and_report(pop, state, accum, did_live=live)


def _select_and_report(pop: dict, state: dict, accum: list, *, did_live: bool) -> dict:
    k = K(state)
    bar = stats.noise_bar(k)
    reports = [_genome_report(pop, gid, k) for gid in pop["active"]]
    reports.sort(key=lambda r: (r["mature"],
                                (r["stress_mean_R"] if r["stress_mean_R"] is not None else -9)),
                 reverse=True)
    mature = [r for r in reports if r["mature"]]
    mature_ids = [r["genome_id"] for r in mature]

    gate = _check_reality_gate(pop, state, mature_ids, k, bar)

    selection = {"performed": False, "reason": None, "killed": [], "bred": []}
    if len(mature) >= MIN_MATURE_FOR_SELECTION:
        rng = random.Random(f"gen{state['generation']}:{k}")
        # Survivors = the top full-loss-stress mean-R mature genomes. MIN_SURVIVORS keeps the small pool as
        # breeding parents when few genomes are mature (so all of the top-3 survive and breed); once the
        # mature pool is larger, SURVIVE_FRAC governs again and the bottom fraction is culled.
        n_survive = min(len(mature), max(MIN_SURVIVORS, int(round(SURVIVE_FRAC * len(mature)))))
        survivors = mature_ids[:n_survive]
        killed = mature_ids[n_survive:]
        active = [g for g in pop["active"] if g not in killed]
        # Breed at least MIN_CHILDREN_PER_GEN from the survivors so a low/zero-kill generation still
        # forward-tests the survivors' bred signature -- but never push the active population past
        # POP_CEILING (this bounds the continuous loop: kill-free breeding stops at the ceiling).
        n_children = max(len(killed), MIN_CHILDREN_PER_GEN)
        if len(active) + n_children > POP_CEILING:
            n_children = max(len(killed), POP_CEILING - len(active))
        n_children = max(0, n_children)
        if killed or n_children:
            children = _breed(pop, state, survivors, n_children, rng)
            for child in children:
                cid = G.genome_id(child)
                pop["genomes"][cid] = child
                active.append(cid)
                _register(state, cid)
            pop["active"] = active
            state["generation"] += 1
            selection.update(performed=True, killed=killed, bred=[G.genome_id(c) for c in children],
                             survivors=survivors)
            save_pop(pop)
        else:
            selection["reason"] = (f"population at the {POP_CEILING}-genome ceiling with no kills this "
                                   "generation, so no new children were bred (bounds unbounded growth). "
                                   "Accumulating forward.")
    else:
        selection["reason"] = (f"only {len(mature)} genome(s) reached the {N_MIN_EVAL}-trade minimum; "
                               f"need {MIN_MATURE_FOR_SELECTION}. Accumulating -- NO selection yet.")

    # Kill switch: after M real generations with no confirmed edge and a significantly-negative best.
    best = mature[0] if mature else None
    halted = False
    if state["generation"] >= M_GENERATIONS_KILL and not state["confirmed_real"]:
        if best is not None:
            kb = stats.kill_bound(stress_pass_R(best["genome_id"]))
            if kb.get("significantly_negative"):
                halted = True
        elif not mature:
            halted = True
    if halted:
        state["halted"] = True
        state["halt_reason"] = ("no evolvable edge found: after "
                                f"{state['generation']} generations the best forward expectancy is "
                                "not distinguishable from (or is significantly below) zero, and nothing "
                                "cleared the K-corrected bar on a fresh slice.")

    save_state(state)
    report = _build_report(pop, state, k, bar, reports, mature, best, gate, selection, accum, did_live)
    _append_genlog(report)
    return report


def _build_report(pop, state, k, bar, reports, mature, best, gate, selection, accum, did_live) -> dict:
    total_resolved = sum(r["resolved_pass"] for r in reports)
    total_terminal = sum(r["resolved_terminal_pass"] for r in reports)
    eligible_clearers = [r for r in mature
                         if r["beats_noise_bar"] and r["stress_beats_noise_bar"]]
    if not mature:
        verdict = (f"NO VERDICT -- 0 genomes have reached the {N_MIN_EVAL}-trade minimum. "
                   "Population expectancy is BEHAVIOUR, not evidence. Honest prior ~0 or negative.")
        beaten = False
    else:
        beaten = bool(eligible_clearers)
        if state["confirmed_real"]:
            verdict = f"REAL EDGE CONFIRMED on a fresh slice: {list(state['confirmed_real'])}."
        elif beaten:
            leader = eligible_clearers[0]
            verdict = (f"genome {leader['genome_id']} clears the reported AND full-loss-stress K-bars "
                       f"(reported t={leader['t']:.2f}; stress t={leader['stress_t']:.2f}; bar={bar:.2f}) "
                       "but is NOT confirmed -- it must repeat both on a fresh slice.")
        elif best["beats_noise_bar"] and not best["stress_beats_noise_bar"]:
            verdict = (f"best stress-fitness genome {best['genome_id']} looks positive only after missing "
                       f"exits are excluded (reported t={best['t']:.2f}, stress t={best['stress_t']:.2f}, "
                       f"bar={bar:.2f}). It FAILS the executable/full-loss gate; no real edge.")
        else:
            bt = best["t"]
            verdict = (f"best genome {best['genome_id']}: forward t={bt:.2f} vs K-corrected noise bar "
                       f"{bar:.2f} -> DOES NOT clear it. No real edge. Consistent with the negative-sum "
                       "prior; evolution cannot manufacture an edge that is not there.")
    return {
        "generation": state["generation"], "reported_utc": _now_iso(),
        "cpu_only_no_gpu_no_neural_net": True,
        "population_size": len(pop["active"]), "K_genomes_ever_evaluated": k,
        "fitness_version": FITNESS_VERSION,
        "fitness_definition": ("full-loss stress over every terminal PASS; UNPRICED and UNEXITABLE are "
                               "-100% before pinned toll; conservative bound, not a literal zero-price claim"),
        "K_corrected_noise_bar_SE": round(bar, 4),
        "resolved_pass_trades_total": total_resolved,
        "resolved_terminal_pass_trades_total": total_terminal,
        "mature_genomes": len(mature), "N_min_eval": N_MIN_EVAL,
        "best_genome": None if best is None else {
            "genome_id": best["genome_id"], "genome": pop["genomes"][best["genome_id"]],
            "resolved_pass": best["resolved_pass"], "forward_mean_R": best["mean_R"],
            "forward_t_stat": best["t"], "expectancy_R": best["expectancy_R"],
            "win_rate": best["win_rate"], "beats_K_corrected_bar": best["beats_noise_bar"],
            "resolved_terminal_pass": best["resolved_terminal_pass"],
            "stress_mean_R": best["stress_mean_R"], "stress_t_stat": best["stress_t"],
            "stress_beats_K_corrected_bar": best["stress_beats_noise_bar"]},
        "anything_beats_bar": beaten,
        "reality_gate_events": gate,
        "candidates_awaiting_fresh_slice": state["candidates"],
        "confirmed_real": state["confirmed_real"],
        "selection": selection,
        "kill_switch": {"M_generations": M_GENERATIONS_KILL, "halted": state["halted"],
                        "halt_reason": state["halt_reason"]},
        "verdict": verdict,
        "leaderboard_top5": [{"genome_id": r["genome_id"], "priced_n": r["resolved_pass"],
                              "reported_mean_R": r["mean_R"], "reported_t": r["t"],
                              "terminal_n": r["resolved_terminal_pass"],
                              "stress_mean_R": r["stress_mean_R"], "stress_t": r["stress_t"],
                              "mature": r["mature"]}
                             for r in reports[:5]],
        "live_cycles": accum if did_live else "offline (no live cycles run)",
        "framing": ("PAPER ONLY -- no orders/wallet/SOL/on-chain. Forward-selected, never "
                    "backtest-optimized. Below the minimum this is behaviour, not evidence."),
    }


def _append_genlog(report: dict) -> None:
    slim = {k: report[k] for k in ("generation", "reported_utc", "population_size",
            "K_genomes_ever_evaluated", "K_corrected_noise_bar_SE", "resolved_pass_trades_total",
            "mature_genomes", "anything_beats_bar", "verdict") if k in report}
    if report.get("best_genome"):
        slim["best_genome_id"] = report["best_genome"]["genome_id"]
        slim["best_forward_mean_R"] = report["best_genome"]["forward_mean_R"]
        slim["best_forward_t"] = report["best_genome"]["forward_t_stat"]
    with GENLOG.open("a") as fh:
        fh.write(json.dumps(slim, default=str) + "\n")


def _last_report(pop: dict, state: dict) -> dict:
    k = K(state)
    bar = stats.noise_bar(k)
    reports = [_genome_report(pop, gid, k) for gid in pop["active"]]
    reports.sort(key=lambda r: (r["mature"],
                                (r["stress_mean_R"] if r["stress_mean_R"] is not None else -9)),
                 reverse=True)
    mature = [r for r in reports if r["mature"]]
    best = mature[0] if mature else None
    return _build_report(pop, state, k, bar, reports, mature, best,
                         {"declared": [], "confirmed": [], "falsified": [],
                          "suppressed_redeclarations": []},
                         {"performed": False,
                          "reason": "halted" if state.get("halted") else "read_only_status"}, [], False)


def status() -> dict:
    """Read-only snapshot of the population and the current K-corrected bar."""
    pop, state = load_pop(), load_state()
    return _last_report(pop, state)
