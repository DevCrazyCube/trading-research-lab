#!/usr/bin/env python3
"""B9c evidence-grade signature inventory for the frozen B8b cohort.

Preserves exact JSON-RPC response bodies compressed with zlib and commits each history page with
its normalized rows. Read-only finalized RPC only. SOLANA_RPC_URL is required and never persisted.
"""
import argparse
import concurrent.futures as futures
import hashlib
import importlib.util
import json
import os
import pathlib
import sqlite3
import time
import urllib.error
import urllib.request
import zlib

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, filename):
    """By absolute path: this module is loaded with `spec_from_file_location` from many places,
    where `scripts/` is not on `sys.path` and a plain import would fail."""
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


HTTP = _load("rpc_http_identity", "rpc_http_identity.py")

# The burned B9a cohort, and the two pins below describe IT and nothing else. A `--source` that is
# not this exact path is a fresh window whose population and whose observation horizon this module
# has never seen, so the pins do not apply and must not be silently reused. That is the same
# burned-versus-fresh split `b9d_transaction_bodies.source_mode` already draws; it is drawn here
# because B11a pointed this module at a fresh cohort and both pins were still the B9 ones.
BURNED_SOURCE = "research/b9a_outcomes.sqlite"
SOURCE_MODE_BURNED = "burned"
SOURCE_MODE_FRESH = "fresh"

# The B9 observation horizon. Burned: it belongs to the B9 window and is meaningless outside it.
#
# This pin is the DANGEROUS one, and more dangerous than the count directly below it. The count
# refuses loudly against any population that is not 1,601. This one is consulted by
# `resolve_cutoff_slot`, which brackets with low = the cohort's earliest launch and high = the live
# tip and requires `low_time <= CUTOFF_TIME < high_time`. The tip is always later than a timestamp
# from July, so the upper half of that bracket is satisfied by everything; the ONLY thing standing
# between a fresh window and this burned horizon is `low_time <= CUTOFF_TIME`, and that condition is
# SATISFIED by any fresh window that begins EARLIER than this timestamp. Such a window brackets,
# bisects, and truncates its signature collection at another study's clock with no refusal and no
# mark on the artifact. B11a happened to begin 3h48m AFTER it and so refused; that was the calendar,
# not this module. Fresh mode therefore does not resolve a cutoff from a time at all -- it requires
# the caller to state the slot, and refuses when the caller does not.
CUTOFF_TIME = 1785154782
EXPECTED_MEMBERS = 1601
SCHEMA_VERSION = "b9c-v1"


def source_mode(source_path):
    """Burned when `--source` names the burned B9a artifact, fresh otherwise.

    By path rather than by content: the question is not whether some cohort is well formed but
    whether it is THE cohort the pins were taken against, and only the burned path can be.
    """
    return SOURCE_MODE_BURNED if str(source_path) == BURNED_SOURCE else SOURCE_MODE_FRESH


def _cohort_adapter():
    """Loaded lazily so burned mode keeps working with no dependency on the fresh-cohort adapter."""
    return _load("b11d_cohort_adapter", "b11d_cohort_adapter.py")


def assert_mode_arguments(mode, source_path, cutoff_slot, creates_path):
    """The argv must agree with which corpus `--source` names.

    Extracted rather than left inline in `main`, and the reason is on the record: a mutation sweep
    of this module killed every guard that had a function to call and left every guard sitting in
    `main` alive, including the one immediately below -- the single most important line in this
    change. `main` cannot be entered from a test without a network, so a check that lives only
    there is a check nobody can provoke. B15M learned this and B10B paid for not having.
    """
    if mode == SOURCE_MODE_BURNED:
        for name, value in (("--cutoff-slot", cutoff_slot), ("--creates", creates_path)):
            if value is not None:
                raise SystemExit(
                    f"REFUSING: {name} is fresh-mode only. --source is the burned B9a artifact, "
                    "whose horizon and population are pinned in this file; accepting an override "
                    "against it would let a caller re-point the freeze from argv")
        return
    if cutoff_slot is None:
        # Refuses rather than falling back to CUTOFF_TIME. The fallback is precisely the fail-open
        # documented at that constant: a fresh window earlier than the burned timestamp brackets
        # successfully and truncates itself at another study's clock without a word.
        raise SystemExit(
            f"REFUSING: {source_path} is a fresh cohort and --cutoff-slot was not given. This "
            "module's only horizon is the burned B9 one, which describes a window this cohort is "
            "not part of. State the observation horizon as a slot")


def cutoff_metadata_for(mode, cutoff_slot):
    """What the artifact records about the bound it was collected under.

    Burned mode records the timestamp it resolves from; fresh mode records the slot it was handed.
    Stamping `cutoff_time` on a fresh run would put the B9 horizon on an artifact bounded by
    something else, which is the provenance lie this metadata exists to prevent.
    """
    if mode == SOURCE_MODE_BURNED:
        return {"cutoff_time": str(CUTOFF_TIME)}
    return {"cutoff_slot": str(cutoff_slot), "cutoff_source": "explicit-fresh-window"}


def assert_cohort(members, mode, source_path, creates_path=None):
    """Every refusal here carries its OWN message.

    The single line these replace covered two different conditions, and when B11a tripped it the
    text could not say which -- diagnosing it meant opening the artifact and re-running both
    comparisons by hand. A refusal that does not name what failed is a refusal somebody has to
    reproduce before they can act on it.

    What survives in EVERY mode is everything that is a statement about the cohort itself:
    non-emptiness, because absence is refusal and a zero-member cohort would otherwise sail
    straight through a pin-free guard, and one-to-one bonding curves, because a curve appearing
    twice is structural corruption whatever produced it.

    What is burned-only is the pinned COUNT. Fresh mode replaces it with agreement between two
    separately produced, separately hashed artifacts -- this cohort and the create enumeration it
    was derived from. That is not the tautology the pin was protecting against: the tautology would
    be reading the expected number out of the very file being checked. Two producers agreeing is
    evidence, and it catches something the pin never could, namely truncation between the stage that
    enumerated and the stage that built.
    """
    if not members:
        raise SystemExit(
            "REFUSING: the cohort carries no members. An empty population satisfies every "
            "distinctness and agreement check vacuously, so it is refused before them")
    curves = {row[1] for row in members}
    if len(curves) != len(members):
        raise SystemExit(
            f"REFUSING: {len(members):,} cohort rows carry only {len(curves):,} distinct bonding "
            "curves. A curve on two rows is two populations sharing an address, and every "
            "signature fetched against it would be attributed to whichever row was read last")
    if mode == SOURCE_MODE_BURNED:
        if len(members) != EXPECTED_MEMBERS:
            raise SystemExit(
                f"REFUSING: the burned cohort {source_path} carries {len(members):,} curves, "
                f"pinned at {EXPECTED_MEMBERS:,}. The pin describes the B9 population; an artifact "
                "at the burned path that is not that population is not the artifact this freeze "
                "was written for")
        return

    if creates_path is None:
        raise SystemExit(
            f"REFUSING: {source_path} is a fresh cohort and --creates was not given. The pinned "
            "count does not apply to a fresh window, and dropping it without putting anything in "
            "its place would leave the population unchecked. Name the create enumeration this "
            "cohort was built from")
    adapter = _cohort_adapter()
    try:
        info = adapter.assert_fresh_cohort(source_path)
    except adapter.CohortRefused as error:
        raise SystemExit(f"REFUSING: {source_path} is not a verified fresh cohort: {error}")
    if info["members"] != len(members):
        raise SystemExit(
            f"REFUSING: {source_path} holds {info['members']:,} identity rows but its `outcome` "
            f"view returns {len(members):,}. The view is the consumers' contract and it no longer "
            "projects the table it is defined over")

    recorded = info["source_sha256"]
    actual = hashlib.sha256(open(creates_path, "rb").read()).hexdigest()
    if actual != recorded:
        raise SystemExit(
            f"REFUSING: {creates_path} hashes {actual}, but {source_path} records that it was "
            f"built from {recorded}. Counting against a different enumeration than the one this "
            "cohort came from would compare two windows and call the disagreement a defect")
    creates = sqlite3.connect(f"file:{creates_path}?mode=ro", uri=True)
    try:
        enumerated = creates.execute("SELECT COUNT(*) FROM create_event").fetchone()[0]
    finally:
        creates.close()
    # Exact equality, not a bound: `b11d_cohort_adapter.read_cohort` is exhaustive and REFUSES on a
    # duplicate curve or mint rather than dropping one, so it never filters. Any inequality here is
    # a row that appeared or vanished between the two stages.
    if enumerated != len(members):
        raise SystemExit(
            f"REFUSING: {creates_path} enumerated {enumerated:,} create events but {source_path} "
            f"carries {len(members):,} members. The adapter never filters, so these must agree; "
            "they disagree when one artifact was truncated after the other was written")


def connect(path, readonly=False):
    if readonly:
        return sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    database = sqlite3.connect(path, timeout=120)
    database.execute("PRAGMA journal_mode=WAL")
    database.execute("PRAGMA synchronous=FULL")
    database.execute("PRAGMA busy_timeout=120000")
    return database


def schema(database):
    database.executescript("""
        CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS raw_rpc_response (
            request_key TEXT PRIMARY KEY,
            method TEXT NOT NULL,
            params_json TEXT NOT NULL,
            bonding_curve TEXT,
            page_index INTEGER,
            received_at_unix REAL NOT NULL,
            response_sha256 TEXT NOT NULL,
            raw_zlib BLOB NOT NULL,
            UNIQUE(bonding_curve, page_index)
        );
        CREATE TABLE IF NOT EXISTS curve_scan (
            mint TEXT PRIMARY KEY,
            bonding_curve TEXT NOT NULL UNIQUE,
            launch_slot INTEGER NOT NULL,
            pages INTEGER NOT NULL DEFAULT 0,
            observed_rows INTEGER NOT NULL DEFAULT 0,
            in_window_rows INTEGER NOT NULL DEFAULT 0,
            boundary_proven INTEGER NOT NULL DEFAULT 0 CHECK(boundary_proven IN (0,1)),
            capped INTEGER NOT NULL DEFAULT 0 CHECK(capped IN (0,1)),
            status TEXT NOT NULL DEFAULT 'pending',
            last_signature TEXT,
            terminal_error TEXT
        );
        CREATE TABLE IF NOT EXISTS signature_observation (
            bonding_curve TEXT NOT NULL,
            signature TEXT NOT NULL,
            slot INTEGER,
            block_time INTEGER,
            err_json TEXT,
            memo TEXT,
            confirmation_status TEXT,
            page_index INTEGER NOT NULL,
            row_index INTEGER NOT NULL,
            time_class TEXT NOT NULL,
            PRIMARY KEY(bonding_curve, signature),
            FOREIGN KEY(bonding_curve, page_index)
              REFERENCES raw_rpc_response(bonding_curve, page_index)
        );
        CREATE INDEX IF NOT EXISTS signature_observation_signature
          ON signature_observation(signature);
        CREATE INDEX IF NOT EXISTS signature_observation_time_class
          ON signature_observation(time_class);
        CREATE INDEX IF NOT EXISTS signature_observation_page_coordinate
          ON signature_observation(bonding_curve,page_index,row_index);
    """)


def request_bytes(url, method, params, retries):
    request_body = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
        separators=(",", ":")).encode()
    for attempt in range(retries):
        try:
            request = HTTP.json_rpc_request(url, request_body)
            with urllib.request.urlopen(request, timeout=90) as response:
                raw = response.read()
            payload = json.loads(raw)
            if "error" not in payload:
                return raw, payload.get("result")
            code = payload["error"].get("code")
            if code not in (-32005, -32429, 429):
                raise RuntimeError(
                    f"RPC error {code}: {payload['error'].get('message', 'unknown error')}")
        except urllib.error.HTTPError as error:
            # 408/429/5xx are the server saying "not now" and are worth another bounded attempt.
            # Anything else -- 403 for the client or the plan, 400, 404 -- is terminal at once, and
            # the last attempt raises rather than falling out of the loop as a silent success.
            if not HTTP.is_retryable_status(error.code) or attempt == retries - 1:
                raise
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
            if attempt == retries - 1:
                raise
        if attempt < retries - 1:
            time.sleep(min(0.5 * 2 ** attempt, 12))
    raise RuntimeError(f"rate limit or transport failure persisted for {method}")


def request_key(method, params):
    canonical = json.dumps([method, params], sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()


def preserved_request(database, url, method, params, retries, curve=None, page=None):
    """Return parsed result, replaying a byte-exact stored response when available."""
    key = request_key(method, params)
    row = database.execute(
        "SELECT raw_zlib,response_sha256 FROM raw_rpc_response WHERE request_key=?", (key,)
    ).fetchone()
    if row:
        raw = zlib.decompress(row[0])
        if hashlib.sha256(raw).hexdigest() != row[1]:
            raise RuntimeError(f"stored raw response hash mismatch for {key}")
        return key, raw, json.loads(raw).get("result"), True
    raw, result = request_bytes(url, method, params, retries)
    return key, raw, result, False


def store_raw(database, key, method, params, raw, curve=None, page=None):
    database.execute(
        "INSERT INTO raw_rpc_response VALUES (?,?,?,?,?,?,?,?)",
        (key, method, json.dumps(params, sort_keys=True, separators=(",", ":")), curve, page,
         time.time(), hashlib.sha256(raw).hexdigest(), zlib.compress(raw, 6)))


def block_time(database, url, slot, retries):
    params = [slot]
    key, raw, result, stored = preserved_request(
        database, url, "getBlockTime", params, retries)
    if not stored:
        with database:
            store_raw(database, key, "getBlockTime", params, raw)
    return result


def resolve_cutoff_slot(database, url, low_slot, retries):
    known = dict(database.execute("SELECT key,value FROM metadata"))
    if "cutoff_slot" in known:
        return int(known["cutoff_slot"])
    params = [{"commitment": "finalized"}]
    key, raw, tip, stored = preserved_request(database, url, "getSlot", params, retries)
    if not stored:
        with database:
            store_raw(database, key, "getSlot", params, raw)
    low, high = low_slot, int(tip)
    low_time = block_time(database, url, low, retries)
    high_time = block_time(database, url, high, retries)
    if low_time is None or high_time is None or not (low_time <= CUTOFF_TIME < high_time):
        raise RuntimeError(
            f"cutoff not bracketed: low={low}/{low_time}, high={high}/{high_time}")
    while high - low > 1:
        middle = (low + high) // 2
        stamp = block_time(database, url, middle, retries)
        if stamp is None:
            # Skipped slots are rare. Search backward within a bounded local envelope and refuse
            # if no produced slot can witness this binary-search step.
            witness = None
            for candidate in range(middle - 1, max(low, middle - 64) - 1, -1):
                candidate_time = block_time(database, url, candidate, retries)
                if candidate_time is not None:
                    witness = candidate, candidate_time
                    break
            if witness is None:
                raise RuntimeError(f"no produced slot within 64 slots below skipped slot {middle}")
            middle, stamp = witness
        if stamp <= CUTOFF_TIME:
            low = middle
        else:
            high = middle
    # Prove the immediate produced successor is after the cutoff. Skipped slots between are explicit.
    successor = high
    successor_time = block_time(database, url, successor, retries)
    while successor_time is None and successor - low <= 64:
        successor += 1
        successor_time = block_time(database, url, successor, retries)
    if successor_time is None or successor_time <= CUTOFF_TIME:
        raise RuntimeError("failed to prove produced-slot cutoff successor within 64 slots")
    with database:
        database.executemany("INSERT INTO metadata VALUES (?,?)", [
            ("cutoff_slot", str(low)),
            ("cutoff_successor_slot", str(successor)),
            ("cutoff_successor_time", str(successor_time)),
        ])
    return low


def classify(row, launch_slot, cutoff_slot):
    slot = row.get("slot")
    if not isinstance(slot, int):
        return "unknown"
    if slot < launch_slot:
        return "before_launch"
    if slot > cutoff_slot:
        return "after_cutoff"
    return "in_window"


def normalize_page(curve, page_index, page, launch_slot, cutoff_slot):
    normalized = []
    for row_index, row in enumerate(page):
        signature = row.get("signature")
        if not signature:
            raise RuntimeError(f"missing signature at {curve} page {page_index} row {row_index}")
        normalized.append((
            curve, signature, row.get("slot"), row.get("blockTime"),
            json.dumps(row.get("err"), sort_keys=True, separators=(",", ":")),
            row.get("memo"), row.get("confirmationStatus"), page_index, row_index,
            classify(row, launch_slot, cutoff_slot)))
    return normalized


def verify_raw_replay(database):
    """Reproduce every normalized page from its preserved response; return page/row totals."""
    launch_slots = dict(database.execute("SELECT bonding_curve,launch_slot FROM curve_scan"))
    cutoff_slot = int(dict(database.execute("SELECT key,value FROM metadata"))["cutoff_slot"])
    pages = rows = 0
    for curve, page_index, compressed, expected_hash in database.execute(
            "SELECT bonding_curve,page_index,raw_zlib,response_sha256 FROM raw_rpc_response "
            "WHERE bonding_curve IS NOT NULL ORDER BY bonding_curve,page_index"):
        raw = zlib.decompress(compressed)
        if hashlib.sha256(raw).hexdigest() != expected_hash:
            raise RuntimeError(f"raw hash mismatch for {curve} page {page_index}")
        page = json.loads(raw).get("result") or []
        expected = normalize_page(curve, page_index, page, launch_slots[curve], cutoff_slot)
        actual = database.execute(
            "SELECT bonding_curve,signature,slot,block_time,err_json,memo,confirmation_status,"
            "page_index,row_index,time_class FROM signature_observation "
            "WHERE bonding_curve=? AND page_index=? ORDER BY row_index",
            (curve, page_index)).fetchall()
        if expected != actual:
            raise RuntimeError(
                f"normalized replay mismatch for {curve} page {page_index}: "
                f"expected {len(expected)}, stored {len(actual)}")
        pages += 1
        rows += len(page)
    return pages, rows


def scan_curve(path, url, member, cutoff_slot, max_pages, retries):
    mint, curve, launch_slot = member
    database = connect(path)
    state = database.execute(
        "SELECT pages,status,last_signature FROM curve_scan WHERE mint=?", (mint,)).fetchone()
    page_index, status, before = state
    if status in ("complete", "incomplete_cap"):
        database.close()
        return status
    try:
        while page_index < max_pages:
            options = {"limit": 1000, "commitment": "finalized"}
            if before:
                options["before"] = before
            params = [curve, options]
            key, raw, page, stored = preserved_request(
                database, url, "getSignaturesForAddress", params, retries, curve, page_index)
            page = page or []
            rows = normalize_page(curve, page_index, page, launch_slot, cutoff_slot)
            last = page[-1].get("signature") if page else before
            if page and not last:
                raise RuntimeError("non-empty page lacks pagination cursor")
            slots = [row.get("slot") for row in page if isinstance(row.get("slot"), int)]
            boundary = not page or (slots and min(slots) < launch_slot)
            next_pages = page_index + 1
            capped = next_pages >= max_pages and not boundary
            next_status = "complete" if boundary else ("incomplete_cap" if capped else "scanning")
            with database:
                if not stored:
                    store_raw(database, key, "getSignaturesForAddress", params, raw, curve,
                              page_index)
                database.executemany(
                    "INSERT INTO signature_observation VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
                database.execute("""
                    UPDATE curve_scan SET pages=?, observed_rows=observed_rows+?,
                      in_window_rows=in_window_rows+?, boundary_proven=?, capped=?, status=?,
                      last_signature=?, terminal_error=NULL WHERE mint=?
                """, (next_pages, len(rows), sum(row[-1] == "in_window" for row in rows),
                      int(bool(boundary)), int(capped), next_status, last, mint))
            page_index, before = next_pages, last
            if boundary or capped:
                database.close()
                return next_status
        raise RuntimeError("pagination loop ended without terminal classification")
    except Exception as error:
        with database:
            database.execute(
                "UPDATE curve_scan SET status='error',terminal_error=? WHERE mint=?",
                (f"{type(error).__name__}: {error}", mint))
        database.close()
        raise


def initialize(database, source_path, source_hash, members, max_pages, cutoff_metadata):
    schema(database)
    # `cutoff_metadata` rather than a fixed `cutoff_time`: burned mode records the timestamp it
    # resolves from, fresh mode records the slot it was handed. Writing `cutoff_time` in fresh mode
    # would stamp the B9 horizon onto an artifact collected under a different one, which is the
    # provenance lie this metadata exists to prevent. Both land in `expected`, so the mismatch guard
    # below covers them: resuming a partial inventory under a changed horizon refuses.
    expected = {
        "schema_version": SCHEMA_VERSION, "source_artifact": source_path,
        "source_sha256": source_hash,
        "max_pages": str(max_pages), "endpoint_ref": "configured-mainnet",
        **cutoff_metadata,
    }
    present = dict(database.execute("SELECT key,value FROM metadata"))
    for key, value in expected.items():
        if key in present and present[key] != value:
            raise RuntimeError(f"REFUSING metadata mismatch {key}: {present[key]!r} != {value!r}")
    missing = [(key, value) for key, value in expected.items() if key not in present]
    with database:
        if missing:
            database.executemany("INSERT INTO metadata VALUES (?,?)", missing)
        database.executemany(
            "INSERT OR IGNORE INTO curve_scan(mint,bonding_curve,launch_slot) VALUES (?,?,?)",
            members)
    actual = database.execute("SELECT COUNT(*) FROM curve_scan").fetchone()[0]
    if actual != len(members):
        raise RuntimeError(f"curve_scan membership mismatch: {actual} != {len(members)}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=BURNED_SOURCE)
    parser.add_argument("--database", default="research/b9c_signature_inventory.sqlite")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--max-pages", type=int, default=40)
    parser.add_argument("--retries", type=int, default=8)
    parser.add_argument("--creates", help="fresh mode only: the create enumeration --source was "
                                          "built from, for cross-artifact population agreement")
    parser.add_argument("--cutoff-slot", type=int,
                        help="fresh mode only, and REQUIRED there: the observation horizon as a "
                             "slot. Fresh mode does not resolve one from a time, because the only "
                             "time it has is the burned B9 one")
    arguments = parser.parse_args()
    if not 1 <= arguments.workers <= 8:
        parser.error("--workers must be between 1 and 8")
    if not 1 <= arguments.max_pages <= 100:
        parser.error("--max-pages must be between 1 and 100")
    url = os.environ.get("SOLANA_RPC_URL")
    if not url:
        raise SystemExit("REFUSING: SOLANA_RPC_URL is not set. Source .env silently first.")

    mode = source_mode(arguments.source)
    assert_mode_arguments(mode, arguments.source, arguments.cutoff_slot, arguments.creates)

    source_hash = hashlib.sha256(open(arguments.source, "rb").read()).hexdigest()
    source = connect(arguments.source, readonly=True)
    members = source.execute(
        "SELECT mint,bonding_curve,launch_slot FROM outcome ORDER BY launch_slot,mint").fetchall()
    source.close()
    assert_cohort(members, mode, arguments.source, arguments.creates)

    # Stored, not merely passed: `collect` reads `cutoff_slot` back out of metadata, and
    # `resolve_cutoff_slot` already returns an existing one without bisecting. So the explicit
    # horizon travels by the route the module already had, and the artifact records the bound it was
    # actually collected under instead of a timestamp from a window it never touched.
    cutoff_metadata = cutoff_metadata_for(mode, arguments.cutoff_slot)

    database = connect(arguments.database)
    initialize(database, arguments.source, source_hash, members, arguments.max_pages,
               cutoff_metadata)
    cutoff_slot = resolve_cutoff_slot(
        database, url, min(row[2] for row in members), arguments.retries)
    database.close()
    if mode == SOURCE_MODE_BURNED:
        print(f"cohort={len(members):,} cutoff_time={CUTOFF_TIME} cutoff_slot={cutoff_slot:,}")
    else:
        print(f"cohort={len(members):,} mode={mode} cutoff_slot={cutoff_slot:,}")

    pending_db = connect(arguments.database, readonly=True)
    terminal = dict(pending_db.execute("SELECT mint,status FROM curve_scan"))
    pending_db.close()
    pending = [row for row in members if terminal[row[0]] not in ("complete", "incomplete_cap")]
    print(f"terminal={len(members)-len(pending):,} pending={len(pending):,}")
    completed = 0
    with futures.ThreadPoolExecutor(max_workers=arguments.workers) as executor:
        jobs = {executor.submit(scan_curve, arguments.database, url, row, cutoff_slot,
                                arguments.max_pages, arguments.retries): row for row in pending}
        for job in futures.as_completed(jobs):
            job.result()  # errors are persisted and fail the run visibly
            completed += 1
            if completed % 25 == 0 or completed == len(pending):
                print(f"scanned={completed:,}/{len(pending):,}", flush=True)

    result = connect(arguments.database, readonly=True)
    statuses = dict(result.execute(
        "SELECT status,COUNT(*) FROM curve_scan GROUP BY status"))
    integrity = result.execute("PRAGMA integrity_check").fetchone()[0]
    raw_bad = result.execute("SELECT request_key,response_sha256,raw_zlib FROM raw_rpc_response")
    for key, expected_hash, compressed in raw_bad:
        if hashlib.sha256(zlib.decompress(compressed)).hexdigest() != expected_hash:
            raise SystemExit(f"REFUSING publication: raw hash mismatch {key}")
    replay_pages, replay_rows = verify_raw_replay(result)
    counts = result.execute("""
        SELECT COUNT(*), COUNT(DISTINCT signature),
          SUM(time_class='in_window'),
          COUNT(DISTINCT CASE WHEN time_class='in_window' THEN signature END),
          COUNT(DISTINCT CASE WHEN time_class='in_window' AND err_json='null' THEN signature END),
          COUNT(DISTINCT CASE WHEN time_class='in_window' AND err_json!='null' THEN signature END)
        FROM signature_observation
    """).fetchone()
    result.close()
    if integrity != "ok" or set(statuses) - {"complete", "incomplete_cap"}:
        raise SystemExit(f"REFUSING publication: integrity={integrity}, statuses={statuses}")
    print(f"statuses={statuses} integrity={integrity}")
    print(f"raw_replay_pages={replay_pages:,} raw_replay_rows={replay_rows:,}")
    print("observations=%d distinct=%d in_window_rows=%d in_window_distinct=%d "
          "successful_distinct=%d failed_distinct=%d" % counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
