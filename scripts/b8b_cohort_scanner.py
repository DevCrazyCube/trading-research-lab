#!/usr/bin/env python3
"""B8b — draw the cohort under the frozen subsampling rule.

Frozen rule: `research/B8B_SUBSAMPLING_PREREGISTRATION.md`, sha256
`56d8a83b8cbc0821fabb5e5b8e098728caa2d7775d46f0c9fb55e673cf848374`.
Owner authorisation: `agent_discussion.md` Seq 121 — 4 minutes/hour.
Window pinned by the Seq-123 pre-flight: `[433894233, 434097833]`.

The launch window is a **union of 24 sub-intervals**, one per clock hour, each 4 minutes long and
beginning at `offset(h) = (27 * h) mod 59` minutes into that hour. Enumeration inside each block is
**exhaustive** — every `CreateEvent`, no filtering on any attribute. That is what keeps C4 intact
while sampling only 6.67% of the window; the alternative, keeping a subset of the *launches*, is a
member-level filter and is exactly what C4 forbids.

Four properties this script exists to guarantee, none of which the substrate provides for free:

1. **Boundaries come from on-chain `blockTime`, never from interpolation.** Slot production drifts,
   so an interpolated block sits off its intended minute-of-hour, and drift attacks the
   stratification itself. Ambiguity fails closed.
2. **Boundaries are resolved once and then frozen in the database.** A resumed run re-reads them
   rather than recomputing them: recomputation against a moved tip would silently redraw the sample.
3. **Partial completion is FAIL, not a result** (freeze §5). A truncated run is a time-of-day-biased
   sample wearing the label of a stratified one. The exit code and the recorded status both say so.
4. **Skipped slots are verified, not assumed.** `getBlock` returns -32009 ambiguously for "skipped
   **or** missing in long-term storage", and the exhaustiveness claim rests on the difference.

`scripts/b7d_create_enumerator.py` is imported and reused **unmodified** — same fetch, decode and
storage path B8a used, so this cohort is comparable to that census by construction.

Read-only. No signing, no spending, no transactions. Credentials come from SOLANA_RPC_URL in the
environment and are never printed or persisted.
"""
import argparse
import concurrent.futures as cf
import hashlib
import importlib.util
import json
import os
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "b7d", str(ROOT / "scripts" / "b7d_create_enumerator.py"))
B7D = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(B7D)

FREEZE_SHA256 = "56d8a83b8cbc0821fabb5e5b8e098728caa2d7775d46f0c9fb55e673cf848374"
STRIDE, MODULUS = 27, 59          # offset(h) = (27h mod 59); 59 prime so all 24 offsets differ
BLOCK_MINUTES = 4                 # smallest whole-minute block meeting +-0.5pp at p~1% (freeze §4)
HOURS = 24
SCHEMA_VERSION = "b8b-v1"


def offsets():
    """The frozen schedule. Every property re-asserted here rather than trusted."""
    offs = [(STRIDE * h) % MODULUS for h in range(HOURS)]
    assert len(set(offs)) == HOURS, "offsets must be distinct (anti-aliasing)"
    assert max(offs) + BLOCK_MINUTES <= 60, "no block may straddle an hour boundary"
    covered = set()
    for o in offs:
        covered |= set(range(o, o + BLOCK_MINUTES))
    assert covered == set(range(60)), "every minute-of-hour must be reachable by some block"
    return offs


# ------------------------------------------------------------------ blockTime resolution

def block_time(url, slot, retries, floor_slot):
    """`(slot, blockTime)` for the newest slot <= `slot` that has one.

    Skipped slots carry no time, so a probe can land on a hole; walking down finds the nearest real
    block. Returns None rather than guessing if the walk leaves the searched region.
    """
    probe = slot
    while probe >= floor_slot and slot - probe < 5000:
        result = _get_block_time(url, probe, retries)
        if result is not None:
            return probe, result
        probe -= 1
    return None


def _get_block_time(url, slot, retries):
    import urllib.error
    import urllib.request
    body = json.dumps({"jsonrpc": "2.0", "id": 1,
                       "method": "getBlockTime", "params": [slot]}).encode()
    for attempt in range(retries):
        try:
            request = urllib.request.Request(
                url, data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(request, timeout=60) as response:
                payload = json.load(response)
            if "error" in payload:
                return None                      # skipped slot: no time, not a transport failure
            return payload["result"]
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
            if attempt == retries - 1:
                raise
            time.sleep(min(2 ** attempt, 20))
    return None


def first_slot_at_or_after(url, target_time, lo, hi, retries):
    """Smallest slot whose blockTime >= target_time. Fails closed by returning None."""
    best = None
    while lo <= hi:
        mid = (lo + hi) // 2
        found = block_time(url, mid, retries, lo)
        if found is None:
            lo = mid + 1
            continue
        slot, when = found
        if when >= target_time:
            best = slot
            hi = slot - 1
        else:
            lo = mid + 1
    return best


def resolve_blocks(url, window_start, window_end, window_start_time, retries):
    """The 24 sampled sub-intervals, as slot ranges derived from on-chain time."""
    resolved = []
    for hour, offset in enumerate(offsets()):
        begin_time = window_start_time + hour * 3600 + offset * 60
        end_time = begin_time + BLOCK_MINUTES * 60
        begin = first_slot_at_or_after(url, begin_time, window_start, window_end, retries)
        after = first_slot_at_or_after(url, end_time, window_start, window_end, retries)
        if begin is None or after is None or after <= begin:
            raise SystemExit(
                f"FAIL CLOSED: hour {hour} offset {offset} could not be resolved against "
                f"blockTime (begin={begin}, after={after}). The freeze requires the slot<->clock "
                f"mapping to come from chain data; guessing it would silently move the sample.")
        resolved.append({"hour": hour, "offset_minutes": offset,
                         "start_slot": begin, "end_slot_exclusive": after,
                         "start_time": begin_time, "end_time": end_time})
    return resolved


# ------------------------------------------------------------------ database

def open_database(path):
    connection = B7D.connect_database(path)          # reuse the B8a schema verbatim
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS sampled_block (
            hour INTEGER PRIMARY KEY, offset_minutes INTEGER NOT NULL,
            start_slot INTEGER NOT NULL, end_slot_exclusive INTEGER NOT NULL,
            start_time INTEGER NOT NULL, end_time INTEGER NOT NULL
        );
    """)
    return connection


def freeze_metadata(window_start, window_end, window_start_time, idl_sha, endpoint_ref):
    """Self-describing artifact: a later reader re-derives the sample without trusting a log entry."""
    return {
        "schema_version": SCHEMA_VERSION,
        "freeze_sha256": FREEZE_SHA256,
        "rule": f"offset(h) = ({STRIDE} * h) mod {MODULUS}, {BLOCK_MINUTES}-minute blocks, "
                f"{HOURS} hourly strata",
        "stride": str(STRIDE), "modulus": str(MODULUS),
        "block_minutes": str(BLOCK_MINUTES),
        "window_start_slot": str(window_start),
        "window_end_slot_inclusive": str(window_end),
        "window_start_time": str(window_start_time),
        "program_id": B7D.PUMP,
        "idl_sha256": idl_sha,
        "endpoint_ref": endpoint_ref,
    }


def assert_complete_schedule(blocks, origin):
    """A schedule is the sample definition, so a partial one is not a smaller sample - it is a
    different, unstratified one wearing the label of a stratified one (freeze §5)."""
    if len(blocks) != HOURS:
        raise SystemExit(
            f"FAIL CLOSED: {origin} schedule has {len(blocks)} blocks, expected {HOURS} hourly "
            f"strata. A truncated schedule would scan a fraction of the strata and report it as "
            f"the sample. Refusing; delete the sampled_block rows to re-resolve from scratch.")
    hours = [b["hour"] for b in blocks]
    if sorted(hours) != list(range(HOURS)):
        raise SystemExit(
            f"FAIL CLOSED: {origin} schedule does not cover hours 0..{HOURS - 1} exactly once "
            f"(got {sorted(hours)}).")
    expected = offsets()
    wrong = [(b["hour"], b["offset_minutes"], expected[b["hour"]])
             for b in blocks if b["offset_minutes"] != expected[b["hour"]]]
    if wrong:
        raise SystemExit(
            f"FAIL CLOSED: {origin} schedule offsets do not match the frozen rule "
            f"offset(h) = ({STRIDE}h mod {MODULUS}); (hour, stored, expected) = {wrong}")
    # Block width. `resolve_blocks` already refuses `after <= begin`, but it is NEVER CALLED on a
    # resume - the stored schedule is used directly - so that guarantee does not reach this path.
    # A zero-width block contributes no slots, so the hour vanishes from `sampled`, nothing is
    # "missing", and a 23-stratum run reports COMPLETE. Same vacuity shape as F1: emptiness making
    # the check that should have caught it trivially true.
    degenerate = [(b["hour"], b["start_slot"], b["end_slot_exclusive"])
                  for b in blocks if b["end_slot_exclusive"] <= b["start_slot"]]
    if degenerate:
        raise SystemExit(
            f"FAIL CLOSED: {origin} schedule has non-positive block width at "
            f"(hour, start, end_exclusive) = {degenerate}. Such an hour contributes zero slots and "
            f"would silently drop a stratum while the run still reported COMPLETE.")
    # The stored TIMES are the block definition; the slot bounds are only their resolution against
    # the chain. Nothing validated the times, so a block whose span was 1 second, or whose start
    # sat hours off the frozen grid, passed every check above. Both are exactly checkable offline.
    #
    # No anchor argument is needed: offset(0) = 0, so hour 0's start_time IS the window anchor and
    # the schedule checks itself. A coherent shift of ALL blocks is deliberately out of scope here
    # - that is what `verify_window_start_time` covers on a fresh resolve, and what the metadata
    # mismatch check covers on a resume.
    span = BLOCK_MINUTES * 60
    bad_span = [(b["hour"], b["end_time"] - b["start_time"])
                for b in blocks if b["end_time"] - b["start_time"] != span]
    if bad_span:
        raise SystemExit(
            f"FAIL CLOSED: {origin} schedule has blocks whose stored time span is not {span}s "
            f"(hour, span) = {bad_span}. The span is the sampling fraction; a wrong one silently "
            f"reweights that stratum.")
    anchor = blocks[0]["start_time"] - (0 * 3600 + expected[0] * 60)
    off_grid = [(b["hour"], b["start_time"], anchor + b["hour"] * 3600 + expected[b["hour"]] * 60)
                for b in blocks
                if b["start_time"] != anchor + b["hour"] * 3600 + expected[b["hour"]] * 60]
    if off_grid:
        raise SystemExit(
            f"FAIL CLOSED: {origin} schedule has start times off the frozen grid "
            f"(hour, stored, expected) = {off_grid}. Times must satisfy "
            f"start(h) = anchor + 3600h + 60*offset(h); a block sampling the wrong minute is not "
            f"the stratified sample the freeze describes.")


def assert_schedule_anchor(blocks, window_start_time, origin):
    """The schedule's TIMES must describe the window the run declares. F9 (Seq 135).

    Kept separate from `assert_complete_schedule` on purpose: that function checks the schedule is
    *internally* coherent, and a coherently shifted grid genuinely satisfies it — Seq 134 pinned
    that as a deliberate non-guarantee and pointed at the metadata check to catch it instead.

    **The metadata check does not catch it.** The schedule and the metadata are separate stores, so
    shifting every `start_time` while leaving `metadata` alone passes `initialize_metadata`
    (metadata unchanged) *and* `assert_complete_schedule` (the grid is self-anchored on hour 0).
    Measured, not argued: a 2-hour shift passes both. A resume would then sample 24 blocks from the
    wrong part of the day and report COMPLETE.

    `offset(0) = 0` identically, so hour 0's `start_time` is the anchor and must equal the declared
    `window_start_time` exactly. No tolerance: this is an equality between two recorded numbers,
    not a measurement against the chain.
    """
    if not blocks:
        return
    anchor = blocks[0]["start_time"]
    if anchor != window_start_time:
        raise SystemExit(
            f"FAIL CLOSED: {origin} schedule is anchored at {anchor} but the run declares "
            f"window_start_time={window_start_time} (differ by {anchor - window_start_time}s). "
            f"The schedule would sample a different span than the one this run claims. Refusing; "
            f"delete the sampled_block rows to re-resolve, or correct --window-start-time.")


def assert_schedule_slots_in_window(blocks, window_start, window_end, origin):
    """The schedule's SLOTS must lie inside the declared window. F10 (Seq 136).

    The mirror of `assert_schedule_anchor`, and the more dangerous half: the anchor ties the
    schedule's times to the declared window, but **slots are what get fetched**. A schedule with
    perfect times and bounds five million slots away passed every other check and would have
    sampled an entirely different span while reporting COMPLETE. The "% of the window" line does
    not help — it divides sampled-slot count by window width, so it prints ~6.67% however far the
    slots have moved.

    Split out of `assert_schedule_matches_window`, where these bounds were **optional** parameters
    (Seq 138). Seq 137 measured that dropping them from the call site left all 75 tests green:
    the check did not vanish, it **degraded to a silent no-op**, which is worse than absent because
    the function still appears to be called. Seq 137's own conclusion was that such an argument
    "should be required unless there is a reason it cannot be" — there is no such reason here, so
    every parameter is now required and a missing one is a `TypeError`, not a quiet pass.

    `window_end` is inclusive and `end_slot_exclusive` is not, hence `<= window_end + 1`.
    """
    outside = [(b["hour"], b["start_slot"], b["end_slot_exclusive"]) for b in blocks
               if b["start_slot"] < window_start or b["end_slot_exclusive"] > window_end + 1]
    if outside:
        raise SystemExit(
            f"FAIL CLOSED: {origin} schedule samples slots outside the declared window "
            f"[{window_start}, {window_end}]: (hour, start, end_exclusive) = {outside}. The slots "
            f"are what get fetched, so this would sample a different span than the run claims.")


def verify_window_start_time(url, window_start, window_end, window_start_time, retries,
                             tolerance_slots=25):
    """Cross-check `--window-start-time` against the chain before it defines 24 boundaries.

    It is a CLI default, and every block time is computed from it. A wrong value shifts all 24
    blocks coherently, so nothing downstream looks odd and nothing fails - the sample simply is
    not the one the freeze describes. Verified only on a fresh resolve; a resumed run reuses the
    stored schedule and never re-derives times.
    """
    found = first_slot_at_or_after(url, window_start_time, window_start, window_end, retries)
    if found is None:
        raise SystemExit(
            f"FAIL CLOSED: no slot at or after window_start_time={window_start_time} inside "
            f"[{window_start}, {window_end}]; the declared start time is not in this window.")
    if abs(found - window_start) > tolerance_slots:
        raise SystemExit(
            f"FAIL CLOSED: window_start_time={window_start_time} resolves to slot {found}, which "
            f"is {abs(found - window_start)} slots from the declared window_start={window_start} "
            f"(tolerance {tolerance_slots}). All 24 boundaries derive from this time, so a wrong "
            f"value moves the entire sample without anything else looking wrong.")
    return found


def store_blocks(connection, blocks):
    """Write the schedule once. On resume, the stored schedule wins - never recompute."""
    existing = connection.execute("SELECT COUNT(*) FROM sampled_block").fetchone()[0]
    if existing:
        stored = [dict(zip(("hour", "offset_minutes", "start_slot", "end_slot_exclusive",
                            "start_time", "end_time"), row))
                  for row in connection.execute(
                      "SELECT hour, offset_minutes, start_slot, end_slot_exclusive, start_time, "
                      "end_time FROM sampled_block ORDER BY hour")]
        # A stored schedule always wins over a recomputed one - but only if it is a WHOLE
        # schedule. Reusing a truncated one would silently scan a fraction of the strata and
        # report it as the sample; the census would then have to be the thing that catches it.
        assert_complete_schedule(stored, "stored")
        return stored, False
    connection.executemany(
        "INSERT INTO sampled_block(hour, offset_minutes, start_slot, end_slot_exclusive, "
        "start_time, end_time) VALUES (?,?,?,?,?,?)",
        [(b["hour"], b["offset_minutes"], b["start_slot"], b["end_slot_exclusive"],
          b["start_time"], b["end_time"]) for b in blocks])
    connection.commit()
    return blocks, True


# ------------------------------------------------------------------ main

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--window-start", type=int, default=433894233)
    parser.add_argument("--window-end", type=int, default=434097833, help="inclusive")
    parser.add_argument("--window-start-time", type=int, default=1784463582)
    parser.add_argument("--database", default="research/b8b_cohort_433894233_434097833.sqlite")
    parser.add_argument("--idl", default="research/pump_idl_9c82f61.json")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--retries", type=int, default=6)
    parser.add_argument("--resolve-only", action="store_true",
                        help="resolve and store the 24 block boundaries, then stop before fetching")
    args = parser.parse_args()

    idl_bytes = pathlib.Path(args.idl).read_bytes()
    idl = json.loads(idl_bytes)
    types = {item["name"]: item for item in idl["types"]}
    create_type = types["CreateEvent"]
    create_disc = hashlib.sha256(b"event:CreateEvent").digest()[:8]
    create_instruction_discs = {
        bytes(instruction["discriminator"])
        for instruction in idl["instructions"] if instruction["name"] in ("create", "create_v2")}

    url = os.environ.get("SOLANA_RPC_URL", B7D.DEFAULT_RPC)
    endpoint_ref = "public-mainnet" if url == B7D.DEFAULT_RPC else "configured-mainnet"

    connection = open_database(args.database)
    B7D.initialize_metadata(connection, freeze_metadata(
        args.window_start, args.window_end, args.window_start_time,
        hashlib.sha256(idl_bytes).hexdigest(), endpoint_ref))

    stored = connection.execute("SELECT COUNT(*) FROM sampled_block").fetchone()[0]
    if stored:
        blocks, fresh = store_blocks(connection, None)
        print(f"schedule: reusing {len(blocks)} stored blocks (resumed run; NOT recomputed)")
    else:
        print(f"resolving 48 boundaries against on-chain blockTime "
              f"(endpoint={endpoint_ref}) ...", flush=True)
        anchor = verify_window_start_time(url, args.window_start, args.window_end,
                                          args.window_start_time, args.retries)
        print(f"window_start_time verified against chain: resolves to slot {anchor:,} "
              f"(declared start {args.window_start:,})")
        resolved = resolve_blocks(url, args.window_start, args.window_end,
                                  args.window_start_time, args.retries)
        assert_complete_schedule(resolved, "resolved")
        blocks, fresh = store_blocks(connection, resolved)
        print(f"schedule: resolved and frozen into the database")

    # F9/F10: tie the schedule to the window this run declares - its times AND its slots. Placed
    # here rather than inside `store_blocks` so both the stored and the freshly-resolved path are
    # covered from one site, and `store_blocks` has no access to the declared window anyway.
    # Two calls rather than one function with optional bounds: dropping the bounds from a single
    # combined call left all 75 tests green at Seq 137, because the check degraded to a no-op
    # instead of disappearing. With every argument required, a dropped call site is a TypeError.
    origin = "stored" if not fresh else "resolved"
    assert_schedule_anchor(blocks, args.window_start_time, origin)
    assert_schedule_slots_in_window(blocks, args.window_start, args.window_end, origin)

    sampled = []
    for b in blocks:
        sampled.extend(range(b["start_slot"], b["end_slot_exclusive"]))
    print(f"{'hour':>4} {'off':>4} {'start_slot':>12} {'end_excl':>12} {'slots':>6}")
    for b in blocks:
        print(f"{b['hour']:>4} {b['offset_minutes']:>4} {b['start_slot']:>12,} "
              f"{b['end_slot_exclusive']:>12,} {b['end_slot_exclusive']-b['start_slot']:>6}")
    print(f"\ntotal sampled slots: {len(sampled):,}  "
          f"({len(sampled)/(args.window_end-args.window_start+1):.2%} of the window)")

    overlaps = [(a, b) for a, b in zip(blocks, blocks[1:])
                if a["end_slot_exclusive"] > b["start_slot"]]
    if overlaps:
        raise SystemExit(f"FAIL CLOSED: sampled blocks overlap: {overlaps}")
    if len(set(sampled)) != len(sampled):
        raise SystemExit("FAIL CLOSED: duplicate slots in the sample")

    if args.resolve_only:
        print("\n--resolve-only: stopping before any cohort slot is fetched.")
        connection.close()
        return 0

    done = {row[0] for row in connection.execute(
        "SELECT slot FROM slot_scan WHERE status IN ('retrieved', 'skipped')")}
    pending = [s for s in sampled if s not in done]
    print(f"\nalready complete: {len(done):,}   pending: {len(pending):,}", flush=True)

    started = time.time()
    with cf.ThreadPoolExecutor(max_workers=args.workers) as executor:
        results = executor.map(lambda s: B7D.rpc_block(url, s, args.retries), pending)
        for index, (slot, status, block, error) in enumerate(results, 1):
            B7D.store_result(connection, slot, status, block, error, create_disc, create_type,
                             types, create_instruction_discs)
            if index % 200 == 0 or index == len(pending):
                creates = connection.execute("SELECT COUNT(*) FROM create_event").fetchone()[0]
                rate = index / max(time.time() - started, 1e-9)
                remaining = (len(pending) - index) / rate / 3600 if rate else float("inf")
                print(f"{index:,}/{len(pending):,} slot={slot} creates={creates} "
                      f"{rate:.2f} slots/s eta={remaining:.2f}h", flush=True)

    B7D.verify_skipped_slots(connection, url, args.retries)

    counts = dict(connection.execute("SELECT status, COUNT(*) FROM slot_scan GROUP BY status"))
    creates = connection.execute("SELECT COUNT(*) FROM create_event").fetchone()[0]
    decode_errors = connection.execute("SELECT COUNT(*) FROM decode_error").fetchone()[0]
    accounted = {row[0] for row in connection.execute(
        "SELECT slot FROM slot_scan WHERE status IN ('retrieved', 'skipped')")}
    missing = [s for s in sampled if s not in accounted]

    print(f"\nslot_status={counts} creates={creates} decode_errors={decode_errors}")
    print(f"sampled={len(sampled):,} accounted={len(accounted & set(sampled)):,} "
          f"missing={len(missing):,}")

    # Freeze §5: a truncated stratified sample is worse than a smaller honest one.
    if missing or decode_errors:
        print(f"\nRESULT: **FAIL** — {len(missing):,} sampled slots unaccounted for, "
              f"{decode_errors} decode errors. Per the freeze, partial completion is FAIL, not a "
              f"result. Re-run to resume; the stored schedule is reused, so the sample cannot move.")
        connection.close()
        return 1
    print(f"\nRESULT: **COMPLETE** — all {len(sampled):,} sampled slots accounted for, "
          f"{creates} CreateEvents, 0 decode errors.")
    connection.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
