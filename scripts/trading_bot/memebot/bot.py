#!/usr/bin/env python3
"""The reactive loop -- scan the free feed, screen, open frozen paper entries, track & resolve.

Runs TWO frozen instruments in PARALLEL on the SAME live coins and the SAME entry screen:
  * MEMEBOT1     -- base, 180-min horizon.
  * MEMEBOT_FAST -- variant, ~25-min horizon + dead-coin early exit (memecoin-appropriate timescale).
They differ ONLY in exit/timescale logic, so fresh forward data adjudicates which EXIT rule is better
(ITERATION_PROTOCOL §4b: two forward tests, separate ledgers, both declared). Discovery is shared and
identical: one GeckoTerminal `new_pools` pull PLUS the PumpPortal realtime push buffer, screened once;
the SAME ordered PASS/control selection is offered to every variant, so entries are maximally paired.

Light and fast: one scan is a couple of feed pulls + a bounded number of GeckoTerminal enrichments +
deterministic screening; one track pass refreshes each unique OPEN pool ONCE (cached across variants).
No LLM in the loop, no wallet, no order, no on-chain write. Continuous running is a DETACHED background
subprocess per the project's standing rule; `run --cycles N` is a bounded in-process demo only.
"""

from __future__ import annotations

import datetime as dt
import random
import time

import json
import pathlib

from . import Refused
from . import feed, screen as screen_mod, paper, ledger
from .frozen import CACHE

# Where the FREE local price series live. The reactive TRACK pass resolves from these FIRST so it never
# blocks on a per-position GeckoTerminal call (the old bottleneck: ~90 open positions x ~2.5s throttle
# blew past live_loop.sh's `timeout 180` and most positions never resolved). GeckoTerminal is used ONLY
# as a last resort for a coin with no local candles, and capped so a pass ALWAYS finishes fast.
_BITQUERY_CANDLE_DIR = CACHE / "bitquery_candles"      # keyed by token MINT (the entry's base_token)
_GT_CALLS_PER_TRACK_PASS = 10                          # hard cap: <= this many GT refreshes per pass
# A wall-clock budget for the GT fallback too. The GT throttle is a HOST-WIDE file lock shared with
# scan, the evo loop, the dashboard and the candle ingester; under contention a single refresh can wait
# many seconds for its turn, so a call-count cap alone does not bound the pass. Once the pass has spent
# this long, no further GT calls are issued (remaining coins resolve from local candles / no-network
# horizon only), guaranteeing a full pass over 90+ positions finishes well inside live_loop's timeout.
_GT_WALLCLOCK_BUDGET_S = 45.0


def _read_local_candles(setup: dict) -> list:
    """The FREE local 1s candle history for a held coin, oldest-first, or [] if none exists yet.

    Source order: the memestream cache (pool-keyed, mint via its keymap) FIRST, then the Bitquery 1s
    cache (mint-keyed). Both share the {t,o,h,l,c,v,buys,sells,...} bar schema. The Bitquery live feed
    may be quota-limited/stale, so its file is treated as possibly-absent and read soft -- never blocks.
    """
    from scripts.trading_bot.memestream import candles as mc

    pool = setup.get("pool_address")
    mint = setup.get("base_token")
    try:
        bars = (mc.get_candles(pool) if pool else []) or (mc.get_candles(mint) if mint else [])
    except Exception:  # noqa: BLE001 -- a bad cache read must never break resolution
        bars = []
    if bars:
        return bars
    if mint:
        path = _BITQUERY_CANDLE_DIR / f"{mint}.jsonl"
        try:
            if path.exists():
                return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
        except Exception:  # noqa: BLE001
            return []
    return []


def scan_once(specs: list, *, pages: int = 1) -> dict:
    """Pull+screen the shared feed ONCE, then open the same PASS/control selection in each variant."""
    base = specs[0]
    state_base = ledger.load_state(base)
    # Keep the seen-cache in RECENCY order (insertion order preserved by dict.fromkeys), so bounding it
    # evicts the OLDEST addresses -- not a lexicographic slice that could drop a just-seen coin and let it
    # re-enter/re-count next scan (the old sorted()[-5000:] double-counting bug).
    seen_list = list(dict.fromkeys(state_base.get("seen_pool_addresses", [])))
    seen = set(seen_list)

    # Discovery must NOT hinge on GeckoTerminal alone: its free tier (~30/min, shared with the price
    # refresher, the evo loop and the candle ingester) frequently 429s, and a raised Refused here used
    # to abort the WHOLE scan -- so a single rate-limit hit stopped every new entry and the bot looked
    # dead. GeckoTerminal new_pools is now best-effort; when it drops we fall through to the FREE,
    # rate-limit-exempt PumpPortal realtime buffer (already streaming via the `listen` process) so the
    # scan keeps discovering coins regardless.
    gt_new_pools_ok = True
    try:
        coins = feed.read_new_pools(base, pages=pages)
    except Refused:
        coins = []
        gt_new_pools_ok = False
    pp_n = 0
    try:
        pp = feed.read_pumpportal_candidates(base, seen)
        pp_n = len(pp)
        coins = coins + pp
    except Refused:
        pp = []  # PumpPortal is a bonus discovery source; a drop never blocks the GeckoTerminal path

    uniq: dict = {}
    for c in coins:
        addr = c.get("pool_address")
        if addr and addr not in uniq:
            uniq[addr] = c

    # The set of coins new THIS scan (shared discovery dedup). Screening is done PER VARIANT below --
    # each variant applies its OWN frozen screen to these coins, so a variant that differs in its ENTRY
    # rules (e.g. MEMEBOT_EXIT's $10k reserve + min_sellers) selects a DIFFERENT PASS list than one that
    # only differs in its exit (FAST/QUICK/RUNNER/G73 share MEMEBOT1's screen and so still get the same
    # coins). Screening with specs[0] for every variant -- the old behavior -- silently ignored a
    # variant's own entry rules; that made MEMEBOT_EXIT a fiction (it traded MEMEBOT1's picks).
    newly = [addr for addr, coin in uniq.items() if addr not in seen]
    seen.update(newly)
    seen_bounded = (seen_list + newly)[-5000:]  # keep the 5000 MOST-RECENTLY seen (oldest evicted)
    newly_coins = [(addr, uniq[addr]) for addr in newly]

    # Top-line summary counts use the base screen (specs[0]); each variant's own counts are per-variant.
    base_passed = sum(1 for _, c in newly_coins if screen_mod.screen_coin(c, base)["verdict"] == "PASS")

    variants = {}
    for spec in specs:
        # Screen THIS variant's spec -> its OWN passed / rejected lists.
        passed, rejected, out_of_scope = [], [], []
        for _addr, coin in newly_coins:
            res = screen_mod.screen_coin(coin, spec)
            if any(r.startswith("REJECT_OUT_OF_SCOPE_VENUE") for r in res["reasons"]):
                out_of_scope.append((coin, res))
            else:
                (passed if res["verdict"] == "PASS" else rejected).append((coin, res))
        # Deterministic ordering so paired variants stay nested; each variant's own seed keeps it stable.
        passed.sort(key=lambda cr: cr[0]["pool_address"])
        rng = random.Random(spec["preregistration_sha256"] + str(len(seen)))
        rejected_order = list(rejected)
        rng.shuffle(rejected_order)

        n_open = len(ledger.open_positions(spec))
        room = max(0, spec["max_open_positions"] - n_open)
        opened, controls = [], []
        for coin, res in passed[: min(room, spec["max_new_per_scan"])]:
            try:
                setup = paper.build_entry(coin, res, spec, control=False)
            except Refused:
                continue
            ledger.append_entry(spec, setup)
            opened.append(_brief(setup))
        for coin, res in rejected_order[: spec["max_control_per_scan"]]:
            try:
                setup = paper.build_entry(coin, res, spec, control=True)
            except Refused:
                continue
            ledger.append_entry(spec, setup)
            controls.append(_brief(setup))
        st = ledger.load_state(spec)
        st["seen_pool_addresses"] = seen_bounded
        ledger.save_state(spec, st)
        variants[spec["instrument_id"]] = {
            "screen_passed": len(passed),
            "out_of_scope_not_traded_or_controlled": len(out_of_scope),
            "paper_entries_opened": opened,
            "control_entries_opened": controls,
            "now_open_positions": len(ledger.open_positions(spec)),
        }

    return {
        "pulled_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "coins_seen": len(uniq),
        "newly_seen": len(newly),
        "gt_new_pools_ok": gt_new_pools_ok,   # False when GeckoTerminal 429'd and we ran PumpPortal-only
        "pumpportal_discovered": pp_n,
        "passed_screen_base": base_passed,    # base (specs[0]) screen pass count; per-variant in variants[]
        "variants": variants,
    }


def track_once(specs: list) -> dict:
    """Resolve every OPEN position from the FREE LOCAL price series first; GeckoTerminal only as a
    capped last resort. This removes the per-position GT call that used to make TRACK the bottleneck.

    Per position:
      1. Reconstruct the frozen exit from the local candle HISTORY (memestream/Bitquery) -- this closes
         target/stop CROSSINGS at the frozen level (a winner that ran past +50% resolves as TARGET at
         the target price, not at the +6000% fantasy tick) and marks past-horizon positions to the
         last-known local close. NO network.
      2. Only when a coin has NO local candles at all do we fall back to a SINGLE GeckoTerminal refresh,
         and only while a per-pass budget remains -- so a full pass over 90+ positions always finishes
         well within live_loop.sh's timeout. Past-horizon coins with neither candles nor budget still
         resolve UNEXITABLE_TIMEOUT with no network, so the backlog always drains.
    """
    base = specs[0]
    gt_cache: dict = {}            # pool -> live GT snapshot, shared across variants
    candle_cache: dict = {}        # pool -> local candle bars, shared across variants
    budget = {"gt": _GT_CALLS_PER_TRACK_PASS}
    t_start = time.monotonic()

    def _candles(setup: dict) -> list:
        pool = setup["pool_address"]
        if pool not in candle_cache:
            candle_cache[pool] = _read_local_candles(setup)
        return candle_cache[pool]

    def _gt(setup: dict) -> dict:
        """A capped, cached single GT refresh. Returns {'price_usd': None} once the budget is spent so
        resolve_position still fires horizon/UNEXITABLE without any network call."""
        pool = setup["pool_address"]
        if pool in gt_cache:
            return gt_cache[pool]
        if budget["gt"] <= 0 or (time.monotonic() - t_start) >= _GT_WALLCLOCK_BUDGET_S:
            snap = {"price_usd": None}
        else:
            budget["gt"] -= 1
            try:
                snap = feed.refresh_pool(base, pool)
            except Exception:  # noqa: BLE001 -- Refused OR raw network error: fall back to no price
                snap = {"price_usd": None}
        gt_cache[pool] = snap
        return snap

    variants = {}
    # Shortest-horizon variant FIRST. The time-critical FAST book (25-min horizon + dead-exit) must
    # never be starved behind the slow base book; both books resolve independently every pass.
    for spec in sorted(specs, key=lambda s: s.get("horizon_minutes") or 1e9):
        # A tampered forward commitment in ONE variant must refuse only THAT variant -- it must not
        # abort the whole pass and block the OTHER (healthy) variant from resolving.
        try:
            ledger.verify_entry_hashes(ledger.read_entries(spec))
        except Refused as exc:
            variants[spec["instrument_id"]] = {"error": str(exc), "resolved_now": 0}
            continue
        state = ledger.load_state(spec)
        open_pos = ledger.open_positions(spec)
        results, errors = [], []
        for setup in open_pos:
            # One bad position (network hiccup, malformed record) must not abort the rest of the book.
            try:
                bars = _candles(setup)
                rec = paper.resolve_position_from_candles(setup, bars, spec) if bars else None
                if rec is None:
                    # No candle resolution. If the coin has NO local series at all, take a capped GT
                    # mark; otherwise (candles exist but no crossing yet) use a no-price mark, which
                    # keeps it OPEN inside the horizon and closes it UNEXITABLE once past horizon.
                    current = _gt(setup) if not bars else {"price_usd": None}
                    rec = paper.resolve_position(setup, current, spec)
            except Exception as exc:  # noqa: BLE001 -- isolate so the pass keeps resolving
                errors.append({"pool": setup.get("pool_address"), "error": repr(exc)})
                continue
            if rec is None:
                continue
            ledger.append_resolution(spec, rec)
            if setup["setup_sha256"] not in state["resolved_setup_hashes"]:
                state["resolved_setup_hashes"].append(setup["setup_sha256"])
            results.append({"name": rec.get("name"), "control": rec["control"],
                            "reason": rec["resolution_reason"], "realized_r": rec["realized_r"],
                            "held_minutes": rec.get("held_minutes"),
                            "price_source": rec.get("price_source")})
        ledger.save_state(spec, state)
        variants[spec["instrument_id"]] = {"open_before": len(open_pos), "resolved_now": len(results),
                                           "resolutions": results, "errors": errors,
                                           "still_open": len(ledger.open_positions(spec))}
    return {"gt_calls_used": _GT_CALLS_PER_TRACK_PASS - budget["gt"],
            "local_candle_lookups": len(candle_cache),
            "pass_seconds": round(time.monotonic() - t_start, 1), "variants": variants}


def run_cycle(specs: list, *, pages: int = 1) -> dict:
    """One reactive cycle: track existing positions, then scan for new ones (both variants)."""
    tracked = track_once(specs)
    scanned = scan_once(specs, pages=pages)
    return {"tracked": tracked, "scanned": scanned}


def run_loop(specs: list, *, cycles: int, interval_s: float, pages: int = 1):
    """Bounded in-process loop for a quick live demo. Long runs belong in a detached subprocess."""
    out = []
    for i in range(cycles):
        out.append(run_cycle(specs, pages=pages))
        if i < cycles - 1:
            time.sleep(interval_s)
    return out


def _brief(setup: dict) -> dict:
    return {"name": setup.get("name"), "pool_address": setup["pool_address"],
            "dex": setup.get("dex"), "entry_price_usd": setup["entry_price_usd"],
            "stop_price_usd": setup["stop_price_usd"], "target_price_usd": setup["target_price_usd"],
            "size_sol": setup["size_sol"], "control": setup["control"],
            "horizon_minutes": setup["horizon_minutes"],
            "setup_sha256": setup["setup_sha256"][:16]}


def _reject_histogram(rejected: list) -> dict:
    hist = {}
    for _coin, res in rejected:
        for reason in res["reasons"]:
            key = reason.split(":", 1)[0]
            hist[key] = hist.get(key, 0) + 1
    return dict(sorted(hist.items(), key=lambda kv: -kv[1]))
