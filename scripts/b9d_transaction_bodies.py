#!/usr/bin/env python3
"""B9d transaction-body reconstruction and resumable evidence collector.

Implements the amended freeze `research/B9D_TRANSACTION_BODY_PREREGISTRATION.md` up to, but not
including, network execution. Everything here runs with no RPC: source-hash and population
assertions, the evidence-artifact schema, the signature -> transaction-index mapping that §6 needs
because `getTransaction` does not carry that coordinate, canonical instruction keys, unknown-target
classification, resume, and completed-artifact immutability.

Network execution was explicitly authorised by the owner in `agent_discussion.md` Seq 218. The
collector remains read-only, resumable, and credential-redacting; it does not sign or submit any
transaction.
"""
import argparse
import base64
import hashlib
import json
import os
import sqlite3
import struct
import sys
import time
import urllib.parse
import urllib.request
import urllib.error
import zlib

# Primary sources. Pinned by hash: a scaffold that silently accepts a different artifact would
# reproduce the frozen counts against the wrong evidence.
B9C_PATH = "research/b9c_signature_inventory.sqlite"
B9A_PATH = "research/b9a_outcomes.sqlite"
B9C_SHA256 = "e735c6c59848ff57958402a7488474415c7f20febce7a12cf7227b4267c7391d"
B9A_SHA256 = "882d47d19a331e805be5796cd7d8ab616c7af65391bd327e0221d3c51c4edc38"

# Frozen population, re-derived from the artifact before the freeze fixed it (§1) and again after
# the Seq 198 ordering correction (§6). Asserted before any network call.
EXPECTED_SIGNATURES = 94_985
EXPECTED_SLOTS = 38_853
SLOT_MIN = 433_894_233
SLOT_MAX = 435_536_000

PUMP_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
PUMPSWAP_PROGRAM = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
TARGET_PROGRAMS = (PUMP_PROGRAM, PUMPSWAP_PROGRAM)
ANCHOR_EVENT_CPI_TAG = bytes.fromhex("e445a52e51cb9a1d")

PUMP_IDL_PATH = "research/pump_idl_9c82f61.json"
PUMP_IDL_SHA256 = "b90bc471327f671449271d5d1d42354d1fae6f5a06502f5834459a3108138e49"

# Retrieved byte-exactly from the primary source on 2026-07-29, at the same pinned commit the Pump
# IDL above is pinned at and that `research/B0_PUMPSWAP_PROGRAM_UPGRADE_INVENTORY.md` cites:
#   https://raw.githubusercontent.com/pump-fun/pump-public-docs/
#     9c82f61cb711b044a17f770ab8ce9f9bdf78f333/idl/pump_amm.json
# The file declares `address` = PUMPSWAP_PROGRAM, and all 31 instruction and 25 event
# discriminators it declares equal the Anchor derivations sha256("global:"/"event:" + name)[:8]
# with zero mismatches and zero collisions — two independent derivations agreeing, which is what
# distinguishes a retrieved interface from a plausible-looking one.
PUMPSWAP_IDL_PATH = "research/pump_amm_idl_9c82f61.json"
PUMPSWAP_IDL_SHA256 = "6b5c7ec4e5ef9742fa99dc57b0d75b1031b379bba02a7e1b3c5a4cad68d77e56"
IDL_SOURCE_COMMIT = "9c82f61cb711b044a17f770ab8ce9f9bdf78f333"
IDL_SOURCE_REPO = "https://github.com/pump-fun/pump-public-docs"
IDL_ACCESS_DATE = "2026-07-29"

SCHEMA_VERSION = "b9d-v1"

# §1a. `err_json` holds `json.dumps(err)`, so success is the STRING 'null' and the column is never
# SQL NULL. `err_json IS NULL` matches nothing and classifies all 1,347,469 signatures as failed
# while every other published figure still reproduces. Written once, here, so no caller reinvents it.
SUCCESS_PREDICATE = "err_json = 'null'"


class FreezeViolation(RuntimeError):
    """A frozen precondition did not hold. Always fatal; never downgraded to a warning."""


def sha256_file(path, chunk=1 << 20):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            block = handle.read(chunk)
            if not block:
                return digest.hexdigest()
            digest.update(block)


def load_pinned_idl(path, expected_sha256, expected_program):
    """Load exactly one pinned interface; hash/address mismatch is fatal."""
    actual = sha256_file(path)
    if actual != expected_sha256:
        raise FreezeViolation(
            f"IDL {path} hashes {actual}, pinned {expected_sha256}; refusing interface drift")
    with open(path, "rb") as handle:
        raw = handle.read()
    try:
        idl = json.loads(raw)
    except json.JSONDecodeError as error:
        raise FreezeViolation(f"pinned IDL {path} is not valid JSON: {error}") from error
    if idl.get("address") != expected_program:
        raise FreezeViolation(
            f"IDL {path} declares {idl.get('address')}, expected {expected_program}")
    return idl


def assert_sources(b9c_path=B9C_PATH, b9a_path=B9A_PATH):
    """Both source artifacts must hash to their pinned values. Mismatch is a hard stop."""
    digests = {}
    for path, expected in ((b9c_path, B9C_SHA256), (b9a_path, B9A_SHA256)):
        actual = sha256_file(path)
        if actual != expected:
            raise FreezeViolation(
                f"{path} hashes {actual}, pinned {expected}; refusing to run B9d against an "
                "artifact that is not the one the freeze was written for")
        digests[path] = actual
    return digests


def frozen_population(b9c_path=B9C_PATH, b9a_path=B9A_PATH, assert_counts=True):
    """The §3 fetch set: distinct successful in-window signatures on non-Mayhem curves.

    Returns `(signatures, slots)`. Streamed rather than joined in SQL: the equivalent
    `count(distinct)` join across 1.35M observation rows did not complete in two minutes, and a
    scaffold whose precondition check times out is a precondition nobody runs.
    """
    outcomes = sqlite3.connect(f"file:{b9a_path}?mode=ro", uri=True)
    try:
        mayhem = dict(outcomes.execute("SELECT bonding_curve, is_mayhem_mode FROM outcome"))
    finally:
        outcomes.close()

    inventory = sqlite3.connect(f"file:{b9c_path}?mode=ro", uri=True)
    signatures, slots, null_slots = set(), set(), 0
    try:
        rows = inventory.execute(
            "SELECT bonding_curve, signature, err_json, slot FROM signature_observation "
            "WHERE time_class = 'in_window'")
        for curve, signature, err_json, slot in rows:
            if curve not in mayhem:
                raise FreezeViolation(
                    f"curve {curve} appears in B9c but not B9a; membership must agree "
                    "bidirectionally before any fetch set is derived")
            if err_json != 'null' or mayhem[curve] != 0:
                continue
            signatures.add(signature)
            if slot is None:
                null_slots += 1
            else:
                slots.add(slot)
    finally:
        inventory.close()

    if null_slots:
        raise FreezeViolation(
            f"{null_slots} in-window rows carry a null slot; §6 needs a slot for every signature "
            "to locate its transaction index, and a null slot is 'unknown', never dropped")
    if assert_counts:
        assert_population(signatures, slots)
    return signatures, slots


def frozen_population_by_slot(b9c_path=B9C_PATH, b9a_path=B9A_PATH, assert_counts=True):
    """Frozen signature population grouped by its B9c slot, with cross-row agreement enforced."""
    signatures, slots = frozen_population(b9c_path, b9a_path, assert_counts=assert_counts)
    outcomes = sqlite3.connect(f"file:{b9a_path}?mode=ro", uri=True)
    try:
        mayhem = dict(outcomes.execute("SELECT bonding_curve,is_mayhem_mode FROM outcome"))
    finally:
        outcomes.close()
    grouped, signature_slots = {}, {}
    inventory = sqlite3.connect(f"file:{b9c_path}?mode=ro", uri=True)
    try:
        for curve, signature, err_json, slot in inventory.execute(
                "SELECT bonding_curve,signature,err_json,slot FROM signature_observation "
                "WHERE time_class='in_window'"):
            if err_json != "null" or mayhem[curve] != 0:
                continue
            previous = signature_slots.setdefault(signature, slot)
            if previous != slot:
                raise FreezeViolation(
                    f"signature {signature} is assigned to slots {previous} and {slot} in B9c")
    finally:
        inventory.close()
    if set(signature_slots) != signatures or set(signature_slots.values()) != slots:
        raise FreezeViolation("grouped population disagrees with the frozen population")
    for signature, slot in signature_slots.items():
        grouped.setdefault(slot, []).append(signature)
    return {slot: sorted(values) for slot, values in grouped.items()}


def assert_population(signatures, slots):
    """§3 and §6: the derived population must be exactly what the freeze fixed."""
    if len(signatures) != EXPECTED_SIGNATURES:
        raise FreezeViolation(
            f"population derived {len(signatures):,} signatures, frozen at "
            f"{EXPECTED_SIGNATURES:,}; the freeze was written against a different fetch set")
    if len(slots) != EXPECTED_SLOTS:
        raise FreezeViolation(
            f"population spans {len(slots):,} distinct slots, frozen at {EXPECTED_SLOTS:,}")
    low, high = min(slots), max(slots)
    if low != SLOT_MIN or high != SLOT_MAX:
        raise FreezeViolation(
            f"slot range {low:,}..{high:,} does not match the frozen "
            f"{SLOT_MIN:,}..{SLOT_MAX:,}")
    return True


# ---------------------------------------------------------------------------------------------
# Evidence artifact (§5)
# ---------------------------------------------------------------------------------------------

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

        -- §5.2 the stored bytes are primary evidence, not a reconstructed JSON object
        CREATE TABLE IF NOT EXISTS raw_transaction (
            signature TEXT PRIMARY KEY,
            method TEXT NOT NULL,
            params_json TEXT NOT NULL,
            received_at_unix REAL NOT NULL,
            response_sha256 TEXT NOT NULL,
            raw_zlib BLOB NOT NULL
        );

        -- §5.6 getTransaction carries no transaction_index; the block signature list supplies it
        CREATE TABLE IF NOT EXISTS raw_block_signatures (
            slot INTEGER PRIMARY KEY,
            method TEXT NOT NULL,
            params_json TEXT NOT NULL,
            received_at_unix REAL NOT NULL,
            response_sha256 TEXT NOT NULL,
            raw_zlib BLOB NOT NULL
        );
        CREATE TABLE IF NOT EXISTS transaction_coordinate (
            signature TEXT PRIMARY KEY,
            slot INTEGER NOT NULL,
            transaction_index INTEGER NOT NULL,
            UNIQUE(slot, transaction_index),
            FOREIGN KEY(slot) REFERENCES raw_block_signatures(slot)
        );

        -- §4 upgrade-boundary re-verification. B0's inventory stops ~2h before the cutoff slot's
        -- block time and its ProgramData history has unverified archival completeness, so coverage
        -- of the observation range is a measurement this artifact must carry, not an assumption.
        CREATE TABLE IF NOT EXISTS raw_boundary_response (
            request_key TEXT PRIMARY KEY,
            program_id TEXT NOT NULL,
            method TEXT NOT NULL,
            params_json TEXT NOT NULL,
            received_at_unix REAL NOT NULL,
            response_sha256 TEXT NOT NULL,
            raw_zlib BLOB NOT NULL
        );
        CREATE TABLE IF NOT EXISTS program_version (
            program_id TEXT NOT NULL,
            from_slot INTEGER NOT NULL,          -- inclusive
            to_slot INTEGER NOT NULL,            -- inclusive
            idl_path TEXT,                       -- NULL only for a KNOWN-UNCOVERED interval
            idl_sha256 TEXT,
            deploy_slot INTEGER,                 -- the deployment that opened this interval
            evidence_key TEXT,                   -- -> raw_boundary_response.request_key
            coverage TEXT NOT NULL CHECK(coverage IN ('covered','uncovered')),
            PRIMARY KEY(program_id, from_slot),
            CHECK(to_slot >= from_slot)
        );

        -- §6 canonical order. Never ROWID, fetch order, or completion order.
        CREATE TABLE IF NOT EXISTS instruction (
            slot INTEGER NOT NULL,
            transaction_index INTEGER NOT NULL,
            outer_index INTEGER NOT NULL,
            inner_index INTEGER NOT NULL,
            signature TEXT NOT NULL,
            program_id TEXT NOT NULL,
            discriminator TEXT,
            idl_name TEXT,
            target INTEGER NOT NULL CHECK(target IN (0,1)),
            accounts_json TEXT,
            data_len INTEGER,
            PRIMARY KEY(slot, transaction_index, outer_index, inner_index)
        );

        CREATE TABLE IF NOT EXISTS reserve_observation (
            slot INTEGER NOT NULL,
            transaction_index INTEGER NOT NULL,
            outer_index INTEGER NOT NULL,
            inner_index INTEGER NOT NULL,
            bonding_curve TEXT NOT NULL,
            virtual_quote_before INTEGER, virtual_token_before INTEGER,
            real_quote_before INTEGER,    real_token_before INTEGER,
            virtual_quote_after INTEGER,  virtual_token_after INTEGER,
            real_quote_after INTEGER,     real_token_after INTEGER,
            evidence TEXT NOT NULL,
            PRIMARY KEY(slot, transaction_index, outer_index, inner_index, bonding_curve)
        );

        -- §5.5 empty is a RESULT, not a precondition
        CREATE TABLE IF NOT EXISTS classification_failure (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signature TEXT,
            slot INTEGER,
            transaction_index INTEGER,
            outer_index INTEGER,
            inner_index INTEGER,
            program_id TEXT,
            discriminator TEXT,
            reason TEXT NOT NULL,
            context_json TEXT
        );
        CREATE INDEX IF NOT EXISTS instruction_signature ON instruction(signature);
        CREATE INDEX IF NOT EXISTS instruction_program ON instruction(program_id);
    """)


def artifact_state(database):
    """`absent`, `partial`, or `complete`, from the metadata the run itself writes."""
    try:
        row = database.execute(
            "SELECT value FROM metadata WHERE key = 'completed_at_unix'").fetchone()
    except sqlite3.OperationalError:
        return "absent"
    if row:
        return "complete"
    started = database.execute(
        "SELECT value FROM metadata WHERE key = 'started_at_unix'").fetchone()
    return "partial" if started else "absent"


def refuse_if_complete(database):
    """§5: a completed artifact can never be overwritten, even with a reset flag."""
    if artifact_state(database) == "complete":
        raise FreezeViolation(
            "this B9d artifact is already marked complete; it can never be overwritten, even with "
            "a reset flag. Move it aside if a genuinely new run is intended.")


def refuse_completed_artifact_before_work(path):
    """Reject a completed rerun before any source scan, writable open, or RPC opportunity.

    `initialize_run()` retains the same check inside the writable transaction path as defense in
    depth. This earlier read-only check is what makes §11's stronger claim true: rerunning against
    a completed artifact cannot rewrite SQLite pragmas or metadata before discovering the marker.
    """
    if not os.path.exists(path):
        return None
    database = connect(path, readonly=True)
    try:
        refuse_if_complete(database)
    finally:
        database.close()
    return None


def assert_resumable(database, digests):
    """§5: a partial artifact resumes only when its source metadata matches exactly."""
    stored = dict(database.execute(
        "SELECT key, value FROM metadata WHERE key IN ('b9c_sha256','b9a_sha256')"))
    if not stored:
        return True
    expected = {"b9c_sha256": digests.get(B9C_PATH, B9C_SHA256),
                "b9a_sha256": digests.get(B9A_PATH, B9A_SHA256)}
    for key, value in expected.items():
        if stored.get(key) and stored[key] != value:
            raise FreezeViolation(
                f"partial artifact was built against {key}={stored[key]}, current source is "
                f"{value}; refusing to resume across a source change")
    return True


# ---------------------------------------------------------------------------------------------
# §6 transaction coordinates
# ---------------------------------------------------------------------------------------------

def transaction_coordinates(slot, block_signatures, wanted):
    """Map each wanted signature to its zero-based index in this slot's signature list.

    `getBlock(transactionDetails="signatures")` returns the block's signatures in execution order,
    which is exactly the `transaction_index` §6 needs and `getTransaction` does not provide.

    Fails visibly on a duplicate signature inside one block and on any wanted signature the block
    does not contain. Neither is repairable by guessing a position, and a coordinate placed by
    guess would silently reorder a reserve path.
    """
    seen = {}
    for index, signature in enumerate(block_signatures):
        if signature in seen:
            raise FreezeViolation(
                f"slot {slot} lists signature {signature} at indexes {seen[signature]} and "
                f"{index}; a block signature list must be unique for the index to be a coordinate")
        seen[signature] = index
    missing = [signature for signature in wanted if signature not in seen]
    if missing:
        raise FreezeViolation(
            f"slot {slot} signature list is missing {len(missing)} expected signature(s), "
            f"first {missing[0]}; the block does not contain a transaction B9c indexed to it")
    return {signature: seen[signature] for signature in wanted}


def assert_coordinate_population(database, expected_slots=None, expected_signatures=None):
    """Fail closed unless the block-to-transaction coordinate phase is exactly complete.

    The expected values resolve from the module constants **at call time**, not as default
    arguments. Bound as defaults they were frozen at import, so patching `EXPECTED_SLOTS` appeared
    to work and silently did nothing — a trap for anyone testing this gate.

    Table uniqueness constraints reject duplicate signatures and duplicate `(slot, index)` pairs.
    This seam assertion supplies the other half of §11: a silently short block or signature
    population must never become the iterable that drives transaction-body collection.
    """
    expected_slots = EXPECTED_SLOTS if expected_slots is None else expected_slots
    expected_signatures = (EXPECTED_SIGNATURES if expected_signatures is None
                           else expected_signatures)
    block_count = database.execute(
        "SELECT count(*) FROM raw_block_signatures").fetchone()[0]
    coordinate_count = database.execute(
        "SELECT count(*) FROM transaction_coordinate").fetchone()[0]
    if block_count != expected_slots or coordinate_count != expected_signatures:
        raise FreezeViolation(
            "coordinate phase is incomplete: "
            f"{block_count:,}/{expected_slots:,} block signature lists and "
            f"{coordinate_count:,}/{expected_signatures:,} transaction coordinates; "
            "refusing to start transaction-body collection")
    return True


def transaction_body_coordinates(database, require_complete=True):
    """Return canonical body-fetch coordinates, gated by exact population completeness."""
    if require_complete:
        assert_coordinate_population(database)
    return list(database.execute(
        "SELECT signature,slot FROM transaction_coordinate ORDER BY slot,transaction_index"))


def assert_raw_transaction_population(database, expected_signatures=None):
    """Fail closed unless every frozen signature has one preserved raw transaction body.

    Resolved at call time, not as a default argument — see `assert_coordinate_population`.

    `raw_transaction.signature` is a primary key, so exact row count establishes uniqueness. The
    coordinate seam separately proves that the frozen population itself has exactly 94,985 unique
    signatures. Together these keep an interrupted collector from looking decoder-ready.
    """
    expected_signatures = (EXPECTED_SIGNATURES if expected_signatures is None
                           else expected_signatures)
    body_count = database.execute("SELECT count(*) FROM raw_transaction").fetchone()[0]
    if body_count != expected_signatures:
        raise FreezeViolation(
            f"raw body phase is incomplete: {body_count:,}/{expected_signatures:,} transaction "
            "bodies; refusing to make the artifact available for decoding")
    return True


# ---------------------------------------------------------------------------------------------
# §11 publication gates. The seams above gate COLLECTION; these gate PUBLICATION.
# ---------------------------------------------------------------------------------------------

RAW_TABLES = (("raw_transaction", "signature"),
              ("raw_block_signatures", "slot"),
              ("raw_boundary_response", "request_key"))


def verify_raw_hashes(database, tables=RAW_TABLES):
    """Re-verify every preserved response against its recorded SHA-256.

    `store_raw` records `sha256(raw)` of the **uncompressed** response and stores
    `zlib.compress(raw)`, so verification decompresses and re-hashes. Bit rot, a truncated write, or
    a hand-edited row all surface here rather than downstream as a decode error, and the hash is the
    only thing that makes the stored bytes *evidence* rather than bytes.
    """
    counts = {}
    for table, key_column in tables:
        verified = 0
        for key, digest, blob in database.execute(
                f"SELECT {key_column}, response_sha256, raw_zlib FROM {table}"):
            try:
                raw = zlib.decompress(blob)
            except zlib.error as error:
                raise FreezeViolation(
                    f"{table} {key}: preserved bytes do not decompress ({error})") from error
            actual = hashlib.sha256(raw).hexdigest()
            if actual != digest:
                raise FreezeViolation(
                    f"{table} {key}: preserved bytes hash {actual}, recorded {digest}")
            verified += 1
        counts[table] = verified
    return counts


def raw_result(blob):
    """The JSON-RPC `result` from one preserved response body."""
    return json.loads(zlib.decompress(blob)).get("result")


def replay_coordinates_from_raw(database):
    """Re-derive every transaction index from the preserved block bodies and require agreement.

    This is the load-bearing gate, and the analogue of B9c's raw-to-normalized replay. Everything
    downstream orders reserve paths by `transaction_index`, and that column is *derived*. Checking
    the row count only proves rows exist; re-deriving the index from the preserved `getBlock`
    response proves the number stored is the number the chain reported. A wrong index would produce
    a plausible reserve path in the wrong order, which is exactly the failure a count cannot see.
    """
    stored = {}
    for signature, slot, index in database.execute(
            "SELECT signature, slot, transaction_index FROM transaction_coordinate"):
        stored.setdefault(slot, {})[signature] = index

    replayed = 0
    for slot, blob in database.execute("SELECT slot, raw_zlib FROM raw_block_signatures"):
        expected = stored.get(slot)
        if expected is None:
            continue
        result = raw_result(blob)
        signatures = (result or {}).get("signatures")
        if signatures is None:
            raise FreezeViolation(
                f"slot {slot}: preserved getBlock response carries no `signatures` list, so no "
                "transaction index can be re-derived from it")
        derived = transaction_coordinates(slot, signatures, list(expected))
        for signature, index in expected.items():
            if derived[signature] != index:
                raise FreezeViolation(
                    f"slot {slot} {signature}: stored transaction_index {index} but the preserved "
                    f"block body places it at {derived[signature]}; canonical ordering would be "
                    "wrong and every reserve path derived from it with it")
            replayed += 1
    missing = sum(len(v) for v in stored.values()) - replayed
    if missing:
        raise FreezeViolation(
            f"{missing:,} coordinate(s) have no preserved block body to replay against")
    return replayed


def verify_body_slots(database):
    """§6: every preserved body's own reported slot must match its coordinate."""
    checked = 0
    for signature, slot, blob in database.execute(
            "SELECT c.signature, c.slot, t.raw_zlib FROM transaction_coordinate c "
            "JOIN raw_transaction t ON t.signature = c.signature"):
        result = raw_result(blob)
        if result is None:
            raise FreezeViolation(f"{signature}: preserved transaction response has a null result")
        reconcile_slot(signature, slot, result.get("slot"))
        checked += 1
    return checked


def assert_body_population_matches(database):
    """The coordinate and body signature SETS must be identical, not merely the same size.

    Both population seams count rows. Two tables can each hold exactly 94,985 unique signatures over
    **different sets** — one coordinate never fetched, one orphan body from an unrelated slot — and
    every other §11 gate still passes: the hashes verify, the coordinate replay covers the block
    bodies, and `verify_body_slots` simply reconciles the smaller intersection and returns a smaller
    number that nothing compared against the population. Reproduced before this was written:
    `decode_artifact` then decoded only the intersection, reported success, and wrote
    `decoded_at_unix`, leaving a partial artifact looking publication-ready.
    """
    missing = database.execute(
        "SELECT count(*) FROM transaction_coordinate c "
        "LEFT JOIN raw_transaction t ON t.signature = c.signature "
        "WHERE t.signature IS NULL").fetchone()[0]
    orphan = database.execute(
        "SELECT count(*) FROM raw_transaction t "
        "LEFT JOIN transaction_coordinate c ON c.signature = t.signature "
        "WHERE c.signature IS NULL").fetchone()[0]
    if missing or orphan:
        raise FreezeViolation(
            f"coordinate and body populations are the same size but not the same set: "
            f"{missing:,} coordinate(s) have no preserved body and {orphan:,} preserved body(ies) "
            "have no coordinate; refusing to decode an intersection and call it the population")
    return True


def verify_source_artifacts(database, b9c_path=B9C_PATH, b9a_path=B9A_PATH):
    """§11: no completed source artifact changed hash since the run recorded it."""
    recorded = dict(database.execute(
        "SELECT key, value FROM metadata WHERE key IN ('b9c_sha256','b9a_sha256')"))
    if not recorded:
        raise FreezeViolation(
            "artifact records no source hashes; it cannot prove which evidence it was built from")
    for key, path in (("b9c_sha256", b9c_path), ("b9a_sha256", b9a_path)):
        actual = sha256_file(path)
        if recorded.get(key) != actual:
            raise FreezeViolation(
                f"{path} now hashes {actual}, but this artifact was built against "
                f"{recorded.get(key)}; a source artifact changed after the run")
    return recorded


def verify_integrity(database):
    row = database.execute("PRAGMA integrity_check").fetchone()
    if not row or row[0] != "ok":
        raise FreezeViolation(f"SQLite integrity_check returned {row[0] if row else None!r}")
    return "ok"


def verify_artifact(database, b9c_path=B9C_PATH, b9a_path=B9A_PATH, check_sources=True):
    """Every §11 gate that can be checked offline, in one pass. Raises on the first failure.

    Deliberately not a boolean-returning "health check": a gate that can be read as "mostly fine"
    is a gate that gets waived. Either the artifact is publishable evidence or the call raises and
    names which property failed.
    """
    summary = {"integrity": verify_integrity(database)}
    assert_coordinate_population(database)
    assert_raw_transaction_population(database)
    assert_body_population_matches(database)
    summary["raw_hashes"] = verify_raw_hashes(database)
    summary["coordinates_replayed"] = replay_coordinates_from_raw(database)
    reconciled = verify_body_slots(database)
    # Assert the count, not just record it. A returned number nobody compares is how the set
    # mismatch above stayed invisible: it reported 1 against a population of 2 and passed.
    expected = EXPECTED_SIGNATURES
    if reconciled != expected:
        raise FreezeViolation(
            f"only {reconciled:,} of {expected:,} bodies reconciled against their coordinates; "
            "the artifact is not the frozen population")
    summary["body_slots_reconciled"] = reconciled
    if check_sources:
        summary["sources"] = verify_source_artifacts(database, b9c_path, b9a_path)
    return summary


# ---------------------------------------------------------------------------------------------
# §4 upgrade-boundary coverage and the fail-closed version map
# ---------------------------------------------------------------------------------------------

# The freeze's range: earliest B8b launch slot through the ratified cutoff slot. Note this is wider
# than SLOT_MAX (435,536,000), which is only the newest slot the population happens to occupy.
CUTOFF_SLOT = 435_536_742
OBSERVATION_RANGE = (SLOT_MIN, CUTOFF_SLOT)


def validate_intervals(program_id, intervals):
    """Sort and check one program's version intervals; refuse anything ambiguous.

    A `covered` interval must name the pinned revision and the preserved evidence that established
    it. An `uncovered` interval must NOT name a revision — otherwise a gap in the evidence could sit
    in the table looking exactly like a decodable interval.
    """
    ordered = sorted(intervals, key=lambda row: (row["from_slot"], row["to_slot"]))
    previous = None
    for row in ordered:
        if row["to_slot"] < row["from_slot"]:
            raise FreezeViolation(
                f"{program_id}: interval {row['from_slot']}..{row['to_slot']} is inverted")
        if previous is not None and row["from_slot"] <= previous["to_slot"]:
            raise FreezeViolation(
                f"{program_id}: intervals {previous['from_slot']}..{previous['to_slot']} and "
                f"{row['from_slot']}..{row['to_slot']} overlap; a slot would resolve to two "
                "interfaces")
        if row["coverage"] == "covered":
            missing = [field for field in ("idl_path", "idl_sha256", "evidence_key")
                       if not row.get(field)]
            if missing:
                raise FreezeViolation(
                    f"{program_id}: interval {row['from_slot']}..{row['to_slot']} claims coverage "
                    f"without {', '.join(missing)}; a pin needs a revision and its evidence")
        elif row["coverage"] == "uncovered":
            if row.get("idl_path") or row.get("idl_sha256"):
                raise FreezeViolation(
                    f"{program_id}: interval {row['from_slot']}..{row['to_slot']} is uncovered but "
                    "names a revision; an evidence gap must not look decodable")
        else:
            raise FreezeViolation(f"{program_id}: unknown coverage {row['coverage']!r}")
        previous = row
    return ordered


def coverage_gaps(intervals, span=OBSERVATION_RANGE):
    """Sub-ranges of `span` that no interval covers at all. Empty means fully tiled."""
    low, high = span
    gaps, cursor = [], low
    for row in sorted(intervals, key=lambda r: r["from_slot"]):
        if row["to_slot"] < low or row["from_slot"] > high:
            continue
        if row["from_slot"] > cursor:
            gaps.append((cursor, row["from_slot"] - 1))
        cursor = max(cursor, row["to_slot"] + 1)
        if cursor > high:
            break
    if cursor <= high:
        gaps.append((cursor, high))
    return gaps


def assert_boundary_coverage(program_id, intervals, span=OBSERVATION_RANGE):
    """§4: the observation range must be fully tiled by intervals that are all `covered`.

    Called before decoding. B0 put the last Pump deploy 798,662 slots before the window opens, but
    B0 ran ~2 h before the cutoff slot's block time and its ProgramData history has unverified
    archival completeness — so this is a check the artifact performs, never a fact it inherits.
    """
    ordered = validate_intervals(program_id, intervals)
    gaps = coverage_gaps(ordered, span)
    if gaps:
        rendered = ", ".join(f"{low:,}..{high:,}" for low, high in gaps)
        raise FreezeViolation(
            f"{program_id}: no boundary evidence covers slot range(s) {rendered} inside the "
            f"observation range {span[0]:,}..{span[1]:,}; refusing to decode an interval whose "
            "interface was never established")
    uncovered = [row for row in ordered if row["coverage"] == "uncovered"
                 and row["to_slot"] >= span[0] and row["from_slot"] <= span[1]]
    if uncovered:
        rendered = ", ".join(f"{row['from_slot']:,}..{row['to_slot']:,}" for row in uncovered)
        raise FreezeViolation(
            f"{program_id}: interval(s) {rendered} overlap the observation range with no pinned "
            "revision. A boundary exists inside the range, so §4 requires a version-aware decoder "
            "with a revision pinned per interval before any transaction is decoded.")
    return ordered


def resolve_version(program_id, slot, intervals):
    """The pinned revision in force at `slot`, or a hard stop. Never a nearest-neighbour guess."""
    for row in validate_intervals(program_id, intervals):
        if row["from_slot"] <= slot <= row["to_slot"]:
            if row["coverage"] != "covered":
                raise FreezeViolation(
                    f"{program_id}: slot {slot:,} falls in an uncovered interval "
                    f"{row['from_slot']:,}..{row['to_slot']:,}; refusing to decode it")
            return row
    raise FreezeViolation(
        f"{program_id}: no version interval contains slot {slot:,}; refusing to attribute it to "
        "the nearest pinned revision")


def intervals_from_boundary_evidence(program_id, last_deploy_slot, in_range_deploys,
                                     idl_path, idl_sha256, evidence_key,
                                     history_complete=False, span=OBSERVATION_RANGE):
    """Turn preserved boundary evidence into version intervals, conservatively.

    The one case that yields a covered range is the freeze's own argument: if the **current**
    ProgramData last-deploy slot is at or before the range start, then since it is the most recent
    deployment that ever happened, no deployment occurred inside the range. Current account state
    alone proves it and no history list is needed.

    Every other case yields `uncovered`. If the last deploy is *after* the range, the build running
    during the range was an earlier one, and a single IDL revision retrieved today cannot be
    attributed to it without further evidence — even when no boundary sits inside the range itself.
    That is deliberately conservative: the failure mode being avoided is decoding 94,985
    transactions against an interface that was not in force.
    """
    low, high = span
    outside = [slot for slot in in_range_deploys if not low <= slot <= high]
    if outside:
        raise FreezeViolation(
            f"{program_id}: deploy slot(s) {outside} were supplied as in-range but fall outside "
            f"{low:,}..{high:,}")

    if last_deploy_slot <= low:
        if in_range_deploys:
            raise FreezeViolation(
                f"{program_id}: current last-deploy slot {last_deploy_slot:,} is at or before the "
                f"range start, which contradicts the in-range deploy(s) {sorted(in_range_deploys)}; "
                "refusing to reconcile contradictory boundary evidence")
        return [{"program_id": program_id, "from_slot": low, "to_slot": high,
                 "idl_path": idl_path, "idl_sha256": idl_sha256,
                 "deploy_slot": last_deploy_slot, "evidence_key": evidence_key,
                 "coverage": "covered"}]

    if not history_complete:
        raise FreezeViolation(
            f"{program_id}: current last-deploy slot {last_deploy_slot:,} is after the range start "
            f"{low:,}, so current account state cannot prove the range's interface. Preserved "
            "loader history crossing below the range is required, and it was not marked complete.")

    edges = sorted(set(in_range_deploys))
    intervals, cursor = [], low
    for edge in edges + [high + 1]:
        if edge > cursor:
            intervals.append({"program_id": program_id, "from_slot": cursor,
                              "to_slot": min(edge - 1, high), "idl_path": None,
                              "idl_sha256": None, "deploy_slot": None,
                              "evidence_key": evidence_key, "coverage": "uncovered"})
        cursor = edge
    return intervals


def reconcile_slot(signature, coordinate_slot, transaction_slot):
    """§6: the slot from the block lookup and from the transaction body must agree."""
    if coordinate_slot != transaction_slot:
        raise FreezeViolation(
            f"{signature}: block lookup places it in slot {coordinate_slot} but its transaction "
            f"response reports slot {transaction_slot}; refusing to order on disagreeing evidence")
    return True


def canonical_key(slot, transaction_index, outer_index, inner_index):
    """§6 ordering key. An outer instruction uses inner_index -1 so it sorts before its own CPIs."""
    for name, value in (("slot", slot), ("transaction_index", transaction_index),
                        ("outer_index", outer_index), ("inner_index", inner_index)):
        if value is None:
            raise FreezeViolation(
                f"canonical ordering key is missing {name}; such an instruction is a "
                "classification_failure, never a row placed by best guess")
    return (slot, transaction_index, outer_index, inner_index)


# ---------------------------------------------------------------------------------------------
# §7 classification
# ---------------------------------------------------------------------------------------------

def instruction_discriminator(data):
    """Anchor instruction discriminator: the first 8 bytes of the instruction data.

    Derivation (`sha256("global:" + snake_case_name)[:8]`) is the repo's existing, verified
    convention — see `scripts/b0c_discriminator_resolve.py`.
    """
    if data is None or len(data) < 8:
        return None
    return bytes(data[:8]).hex()


def idl_instruction_map(idl):
    """{discriminator hex: instruction name} derived from a PINNED IDL document.

    Derived, never hardcoded: an invented instruction list would be exactly the fabricated
    interface AGENTS.md forbids. The caller supplies the pinned IDL; this only hashes its names.
    """
    entries = idl.get("instructions", [])
    if not entries:
        raise FreezeViolation(
            "pinned IDL declares no instructions; refusing to classify against an empty interface")
    mapping = {}
    for entry in entries:
        name = entry["name"]
        declared = entry.get("discriminator")
        if declared is None:
            digest = hashlib.sha256(f"global:{name}".encode()).digest()[:8].hex()
        else:
            if len(declared) != 8 or any(not isinstance(value, int) or not 0 <= value <= 255
                                         for value in declared):
                raise FreezeViolation(f"IDL instruction {name!r} has invalid discriminator")
            digest = bytes(declared).hex()
        if digest in mapping:
            raise FreezeViolation(
                f"discriminator collision between {mapping[digest]!r} and {name!r} in the pinned "
                "IDL; classification would be ambiguous")
        mapping[digest] = name
    return mapping


BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def base58(raw):
    value = int.from_bytes(raw, "big")
    encoded = ""
    while value:
        value, remainder = divmod(value, 58)
        encoded = BASE58_ALPHABET[remainder] + encoded
    zeros = len(raw) - len(raw.lstrip(b"\0"))
    return "1" * zeros + (encoded or "")


def base58_decode(text):
    """Inverse of `base58`. Needed because inner instruction data arrives base58-encoded.

    The outer transaction is base64 under `encoding: "base64"`, but `meta.innerInstructions[].data`
    is base58 — confirmed against a preserved body, whose sample began `1111`, i.e. leading zero
    bytes. Decoding it as base64 would yield plausible garbage with a plausible discriminator.
    """
    value = 0
    for character in text:
        index = BASE58_ALPHABET.find(character)
        if index < 0:
            raise FreezeViolation(f"invalid base58 character {character!r} in instruction data")
        value = value * 58 + index
    zeros = len(text) - len(text.lstrip("1"))
    body = value.to_bytes((value.bit_length() + 7) // 8, "big") if value else b""
    return b"\0" * zeros + body


# ---------------------------------------------------------------------------------------------
# Transaction envelope parsing (§7's prerequisite: there are no instructions to classify without it)
# ---------------------------------------------------------------------------------------------

def compact_u16(data, offset):
    """Read a ShortVec length. Returns `(value, next_offset)`.

    Solana encodes vector lengths as 1-3 bytes, 7 bits each, high bit continuing.
    """
    value = shift = 0
    for _ in range(3):
        if offset >= len(data):
            raise FreezeViolation("truncated compact-u16 length prefix")
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, offset
        shift += 7
    raise FreezeViolation("compact-u16 length prefix exceeded three bytes")


def parse_message(raw):
    """Parse a serialised transaction into its version, static keys and compiled instructions.

    Wire format, in order: signatures, then the message. A versioned message is prefixed by a byte
    with the high bit set carrying the version; a legacy message begins directly with its header.
    After the instructions, a v0 message carries its address-table lookups.

    **Trailing bytes are fatal.** B0e's `TradeEvent` decode established "zero bytes remaining" as
    the discipline that distinguishes a correct layout from one that merely starts correctly, and a
    parser that ignores the tail cannot tell a v0 message from a legacy one it misread.
    """
    offset = 0
    signature_count, offset = compact_u16(raw, offset)
    offset += 64 * signature_count
    if offset > len(raw):
        raise FreezeViolation("truncated signature section")

    version = "legacy"
    if raw[offset] & 0x80:
        version = raw[offset] & 0x7F
        offset += 1

    header = tuple(raw[offset:offset + 3])
    if len(header) != 3:
        raise FreezeViolation("truncated message header")
    offset += 3

    key_count, offset = compact_u16(raw, offset)
    static_keys = []
    for _ in range(key_count):
        chunk = raw[offset:offset + 32]
        if len(chunk) != 32:
            raise FreezeViolation("truncated static account key")
        static_keys.append(base58(chunk))
        offset += 32
    offset += 32                                    # recent blockhash

    instruction_count, offset = compact_u16(raw, offset)
    instructions = []
    for _ in range(instruction_count):
        if offset >= len(raw):
            raise FreezeViolation("truncated instruction")
        program_index = raw[offset]
        offset += 1
        account_count, offset = compact_u16(raw, offset)
        accounts = list(raw[offset:offset + account_count])
        if len(accounts) != account_count:
            raise FreezeViolation("truncated instruction account index list")
        offset += account_count
        data_length, offset = compact_u16(raw, offset)
        data = raw[offset:offset + data_length]
        if len(data) != data_length:
            raise FreezeViolation("truncated instruction data")
        offset += data_length
        instructions.append({"program_index": program_index, "accounts": accounts, "data": data})

    lookups = []
    if version != "legacy":
        lookup_count, offset = compact_u16(raw, offset)
        for _ in range(lookup_count):
            offset += 32                            # the table account itself
            writable_count, offset = compact_u16(raw, offset)
            writable = list(raw[offset:offset + writable_count])
            offset += writable_count
            readonly_count, offset = compact_u16(raw, offset)
            readonly = list(raw[offset:offset + readonly_count])
            offset += readonly_count
            if len(writable) != writable_count or len(readonly) != readonly_count:
                raise FreezeViolation("truncated address table lookup index list")
            lookups.append({"writable": writable, "readonly": readonly})

    if offset != len(raw):
        raise FreezeViolation(
            f"{len(raw) - offset} byte(s) remain after parsing the message; the layout was not "
            "fully consumed and a partially-correct parse is not a parse")
    return {"version": version, "header": header, "static_keys": static_keys,
            "instructions": instructions, "lookups": lookups}


def resolve_account_keys(message, meta):
    """Full account key list: static keys, then loaded writable, then loaded readonly.

    That order is what instruction account indexes are relative to. The wire lookup counts and
    `meta.loadedAddresses` are cross-checked against each other, so a message whose tables were
    resolved into a different number of addresses than it requested fails rather than silently
    shifting every index past the static keys.
    """
    loaded = meta.get("loadedAddresses") or {}
    writable = list(loaded.get("writable") or [])
    readonly = list(loaded.get("readonly") or [])
    requested = sum(len(entry["writable"]) + len(entry["readonly"]) for entry in message["lookups"])
    if requested != len(writable) + len(readonly):
        raise FreezeViolation(
            f"message requests {requested} address-table address(es) but meta.loadedAddresses "
            f"supplies {len(writable) + len(readonly)}; every account index past the static keys "
            "would be misaligned")
    return message["static_keys"] + writable + readonly


def envelope_instructions(result):
    """Every instruction in one preserved body, in canonical order, with resolved program ids.

    Yields dicts carrying `outer_index`, `inner_index` (**-1 for an outer instruction**, so it sorts
    before its own CPIs per §6), `program_id`, `data` bytes and resolved `accounts`. Inner
    instructions come from `meta.innerInstructions`, whose `data` is base58.
    """
    encoded = result.get("transaction")
    if not (isinstance(encoded, list) and len(encoded) == 2 and encoded[1] == "base64"):
        raise FreezeViolation(
            "preserved transaction is not a [base64, 'base64'] pair; the frozen encoding is "
            f"base64 and this body carries {encoded[1] if isinstance(encoded, list) else type(encoded).__name__!r}")
    meta = result.get("meta") or {}
    message = parse_message(base64.b64decode(encoded[0]))
    keys = resolve_account_keys(message, meta)

    def resolve(index, what, outer, inner):
        if not 0 <= index < len(keys):
            raise FreezeViolation(
                f"{what} index {index} at ({outer},{inner}) is outside the {len(keys)} resolved "
                "account keys; refusing to attribute an instruction to an unknown program")
        return keys[index]

    inner_groups = {group["index"]: group.get("instructions") or []
                    for group in (meta.get("innerInstructions") or [])}
    rows = []
    for outer_index, instruction in enumerate(message["instructions"]):
        rows.append({
            "outer_index": outer_index, "inner_index": -1,
            "stack_height": 1,
            "program_id": resolve(instruction["program_index"], "program", outer_index, -1),
            "data": instruction["data"],
            "accounts": [resolve(i, "account", outer_index, -1) for i in instruction["accounts"]]})
        for inner_index, inner in enumerate(inner_groups.get(outer_index, [])):
            rows.append({
                "outer_index": outer_index, "inner_index": inner_index,
                "stack_height": inner.get("stackHeight"),
                "program_id": resolve(inner["programIdIndex"], "program", outer_index, inner_index),
                "data": base58_decode(inner.get("data") or ""),
                "accounts": [resolve(i, "account", outer_index, inner_index)
                             for i in inner.get("accounts") or []]})
    unexpected = set(inner_groups) - set(range(len(message["instructions"])))
    if unexpected:
        raise FreezeViolation(
            f"meta.innerInstructions references outer index(es) {sorted(unexpected)} that the "
            "message does not contain")
    return rows


class BorshReader:
    """Small fail-closed Borsh reader for types declared by the pinned IDL."""

    def __init__(self, data):
        self.data = memoryview(data)
        self.offset = 0

    def take(self, size):
        if size < 0 or self.offset + size > len(self.data):
            raise FreezeViolation(
                f"Borsh payload truncated at offset {self.offset}, need {size}, "
                f"have {len(self.data) - self.offset}")
        out = bytes(self.data[self.offset:self.offset + size])
        self.offset += size
        return out

    def integer(self, width, signed=False):
        return int.from_bytes(self.take(width), "little", signed=signed)

    def remaining(self):
        return len(self.data) - self.offset


def idl_types(idl):
    return {entry["name"]: entry["type"] for entry in idl.get("types", [])}


def decode_borsh(reader, type_spec, types):
    if isinstance(type_spec, str):
        # 128-bit widths are declared by BOTH pinned IDLs and are not optional: `u128` appears in
        # `FeeTier` on each, and `i128` in PumpSwap's `BuyEvent`, `SellEvent`, `Pool`,
        # `InitBoostEvent` and `BoostBuyAndBurnEvent`. Omitting them made 576 of 36,319 preserved
        # bodies raise — 293 SellEvent and 283 BuyEvent — and since the whole materialization is one
        # transaction, the first of them rolled back the entire pass. Decode could never complete.
        # Borsh encodes them as 16-byte little-endian, which `integer()` already handles.
        integers = {"u8": (1, False), "u16": (2, False), "u32": (4, False),
                    "u64": (8, False), "u128": (16, False),
                    "i8": (1, True), "i16": (2, True),
                    "i32": (4, True), "i64": (8, True), "i128": (16, True)}
        if type_spec in integers:
            return reader.integer(*integers[type_spec])
        if type_spec == "bool":
            value = reader.integer(1)
            if value not in (0, 1):
                raise FreezeViolation(f"invalid Borsh bool byte {value}")
            return bool(value)
        if type_spec == "pubkey":
            return base58(reader.take(32))
        if type_spec == "string":
            length = reader.integer(4)
            try:
                return reader.take(length).decode("utf-8")
            except UnicodeDecodeError as error:
                raise FreezeViolation(f"invalid UTF-8 Borsh string: {error}") from error
        raise FreezeViolation(f"unsupported IDL scalar type {type_spec!r}")
    if not isinstance(type_spec, dict) or len(type_spec) != 1:
        raise FreezeViolation(f"unsupported IDL type specification {type_spec!r}")
    kind, value = next(iter(type_spec.items()))
    if kind == "option":
        tag = reader.integer(1)
        if tag == 0:
            return None
        if tag != 1:
            raise FreezeViolation(f"invalid Borsh option tag {tag}")
        return decode_borsh(reader, value, types)
    if kind == "vec":
        count = reader.integer(4)
        return [decode_borsh(reader, value, types) for _ in range(count)]
    if kind == "array":
        child, count = value
        return [decode_borsh(reader, child, types) for _ in range(count)]
    if kind == "defined":
        name = value["name"] if isinstance(value, dict) else value
        if name not in types:
            raise FreezeViolation(f"IDL references missing defined type {name!r}")
        return decode_defined(reader, name, types[name], types)
    raise FreezeViolation(f"unsupported composite IDL type {kind!r}")


def decode_defined(reader, name, definition, types):
    kind = definition.get("kind")
    if kind == "struct":
        fields = definition.get("fields", [])
        if fields and isinstance(fields[0], str):
            return [decode_borsh(reader, field, types) for field in fields]
        return {field["name"]: decode_borsh(reader, field["type"], types)
                for field in fields}
    if kind == "enum":
        index = reader.integer(1)
        variants = definition.get("variants", [])
        if index >= len(variants):
            raise FreezeViolation(f"enum {name} variant {index} is out of range")
        variant = variants[index]
        if variant.get("fields"):
            raise FreezeViolation(f"enum {name} variant fields are not implemented")
        return variant["name"]
    raise FreezeViolation(f"unsupported defined type {name!r} kind {kind!r}")


def instruction_entries(idl):
    return {bytes(entry.get("discriminator") or
                  hashlib.sha256(f"global:{entry['name']}".encode()).digest()[:8]): entry
            for entry in idl.get("instructions", [])}


def flatten_accounts(entries):
    flattened = []
    for entry in entries:
        if "accounts" in entry:
            flattened.extend(flatten_accounts(entry["accounts"]))
        else:
            flattened.append(entry)
    return flattened


def decode_idl_instruction(idl, data, account_keys):
    """Decode one target instruction and require exact argument consumption."""
    if len(data) < 8:
        raise FreezeViolation("target instruction data is shorter than its discriminator")
    entry = instruction_entries(idl).get(bytes(data[:8]))
    if entry is None:
        raise FreezeViolation(f"unknown target discriminator {bytes(data[:8]).hex()}")
    reader = BorshReader(data[8:])
    types = idl_types(idl)
    args = {arg["name"]: decode_borsh(reader, arg["type"], types)
            for arg in entry.get("args", [])}
    if reader.remaining():
        raise FreezeViolation(
            f"{entry['name']} leaves {reader.remaining()} unconsumed argument bytes")
    declared_accounts = flatten_accounts(entry.get("accounts", []))
    if len(account_keys) < len(declared_accounts):
        raise FreezeViolation(
            f"{entry['name']} needs {len(declared_accounts)} accounts, got {len(account_keys)}")
    accounts = {spec["name"]: account_keys[index]
                for index, spec in enumerate(declared_accounts)}
    return {"name": entry["name"], "args": args, "accounts": accounts,
            "remaining_accounts": list(account_keys[len(declared_accounts):])}


def event_entries(idl):
    types = idl_types(idl)
    out = {}
    for event in idl.get("events", []):
        discriminator = event.get("discriminator")
        if discriminator is None or len(discriminator) != 8:
            raise FreezeViolation(f"IDL event {event.get('name')!r} lacks an 8-byte discriminator")
        name = event["name"]
        if name not in types:
            raise FreezeViolation(f"IDL event {name!r} has no matching declared type")
        key = bytes(discriminator)
        if key in out:
            raise FreezeViolation(f"duplicate IDL event discriminator {key.hex()}")
        out[key] = (name, types[name])
    return out


def decode_idl_event(idl, payload):
    """Decode discriminator + Borsh event bytes with exact payload consumption."""
    if len(payload) < 8:
        raise FreezeViolation("event payload shorter than discriminator")
    event = event_entries(idl).get(bytes(payload[:8]))
    if event is None:
        raise FreezeViolation(f"unknown event discriminator {bytes(payload[:8]).hex()}")
    name, definition = event
    reader = BorshReader(payload[8:])
    value = decode_defined(reader, name, definition, idl_types(idl))
    if reader.remaining():
        raise FreezeViolation(f"{name} leaves {reader.remaining()} unconsumed event bytes")
    return name, value


def decode_anchor_cpi_event(program_id, data, idls):
    """Decode one Anchor `emit_cpi!` self-CPI, or return `None` for an ordinary instruction.

    The observed layout is `[8-byte event instruction tag][8-byte event discriminator][Borsh]`.
    A matching wrapper tag on a target program is never treated as an unknown instruction: its
    event discriminator and body must decode exactly against that program's pinned IDL.
    """
    if program_id not in TARGET_PROGRAMS or not data.startswith(ANCHOR_EVENT_CPI_TAG):
        return None
    if program_id not in idls:
        raise FreezeViolation(f"event decoder missing pinned IDL for {program_id}")
    name, fields = decode_idl_event(idls[program_id], data[len(ANCHOR_EVENT_CPI_TAG):])
    return {"name": name, "fields": fields}


def associate_cpi_events(envelopes, idls):
    """Associate decoded CPI events with the invoking instruction using observed stack heights.

    Solana's inner-instruction list is execution order. An event self-CPI at height `h` belongs to
    the most recent instruction at `h-1` in the same outer group. Missing heights or a missing
    parent are ambiguity, never grounds to attach the event to the nearest target by name.
    Returns `(parent_envelope, event_envelope, decoded_event)` tuples.
    """
    parents, out = {}, []
    for envelope in envelopes:
        height = envelope.get("stack_height")
        # A malformed height must fail the same way every other bad field does. Left unchecked, a
        # string height reached `height - 1` and raised TypeError — which still rolls back, but
        # escapes the FreezeViolation contract every caller and gate in this module is written
        # against, and names neither the field nor the coordinate.
        if height is not None and (isinstance(height, bool) or not isinstance(height, int)):
            raise FreezeViolation(
                f"stackHeight {height!r} at ({envelope['outer_index']},{envelope['inner_index']}) "
                "is not an integer; CPI depth cannot be compared and the event's parent would be "
                "guessed")
        if height is None:
            if (envelope["program_id"] in TARGET_PROGRAMS and
                    envelope["data"].startswith(ANCHOR_EVENT_CPI_TAG)):
                raise FreezeViolation(
                    "target CPI event has no stackHeight; its mutating parent is ambiguous")
            continue
        decoded = decode_anchor_cpi_event(envelope["program_id"], envelope["data"], idls)
        if decoded is not None:
            parent = parents.get((envelope["outer_index"], height - 1))
            if parent is None:
                raise FreezeViolation(
                    f"event {decoded['name']} at ({envelope['outer_index']},"
                    f"{envelope['inner_index']}) stack height {height} has no observed parent at "
                    f"height {height - 1}")
            out.append((parent, envelope, decoded))
        parents[(envelope["outer_index"], height)] = envelope
        # A later sibling at this height invalidates descendants from the prior sibling.
        for key in [key for key in parents if key[0] == envelope["outer_index"] and key[1] > height]:
            del parents[key]
    return out


def reserve_after_from_event(name, fields):
    """Return exact post-instruction quote/token reserves only for TradeEvent."""
    if name != "TradeEvent":
        return None
    required = ("virtual_quote_reserves", "virtual_token_reserves",
                "real_quote_reserves", "real_token_reserves")
    missing = [field for field in required if field not in fields]
    if missing:
        raise FreezeViolation(f"TradeEvent lacks reserve field(s): {', '.join(missing)}")
    return {field: fields[field] for field in required}


RESERVE_STATE_ACCOUNTS = {
    PUMP_PROGRAM: frozenset({"bonding_curve", "associated_bonding_curve"}),
    PUMPSWAP_PROGRAM: frozenset({
        "pool", "pool_base_token_account", "pool_quote_token_account",
    }),
}


def reserve_mutation_candidates(program_id, idl):
    """Derive instructions that *may* mutate reserve-bearing state from the pinned IDL.

    This is deliberately a candidate set, not a claim about runtime behaviour. An instruction is
    included when the official IDL marks a curve/pool state account or pool vault writable. The
    transaction's decoded accounts and balance/state evidence must still prove the transition.
    Read-only access is not promoted to a mutation, and an event's absence never clears a writable
    candidate: §7 explicitly forbids the `TradeEvent`-only shortcut.
    """
    if program_id not in RESERVE_STATE_ACCOUNTS:
        raise FreezeViolation(f"no reserve-state account contract for {program_id}")
    roles = RESERVE_STATE_ACCOUNTS[program_id]
    candidates = {}
    for instruction in idl.get("instructions", []):
        writable_roles = sorted({
            account["name"] for account in flatten_accounts(instruction.get("accounts", []))
            if account.get("name") in roles and account.get("writable") is True
        })
        if writable_roles:
            candidates[instruction["name"]] = tuple(writable_roles)
    if not candidates:
        raise FreezeViolation(f"pinned IDL for {program_id} has no writable reserve-state roles")
    return candidates


def reserve_extraction_plan(program_id, instruction_name, candidate_maps):
    """Return the fail-closed evidence obligation for one classified target instruction.

    `TradeEvent` can provide an exact post-state projection for trades, but transaction/account
    reconciliation remains mandatory. Other writable candidates are not guessed unchanged; they
    remain explicitly unresolved until body evidence supplies their transition.
    """
    if program_id not in TARGET_PROGRAMS:
        raise FreezeViolation(f"reserve extraction requested for non-target program {program_id}")
    if program_id not in candidate_maps:
        raise FreezeViolation(f"reserve candidate map missing target program {program_id}")
    roles = candidate_maps[program_id].get(instruction_name)
    if roles is None:
        return {"candidate": False, "writable_roles": (), "event_projection": None,
                "reconciliation_required": False}
    trade_names = {
        PUMP_PROGRAM: {"buy", "buy_exact_sol_in", "buy_v2", "buy_exact_quote_in_v2",
                       "sell", "sell_v2"},
        PUMPSWAP_PROGRAM: {"buy", "buy_exact_quote_in", "sell"},
    }
    projection = "TradeEvent" if instruction_name in trade_names[program_id] else None
    return {"candidate": True, "writable_roles": roles, "event_projection": projection,
            "reconciliation_required": True}


def decoder_manifest(pump_path=PUMP_IDL_PATH, pumpswap_path=PUMPSWAP_IDL_PATH):
    """Offline decoder state: both target interfaces, each pinned by hash and declared address.

    The PumpSwap entry was the `MISSING_PINNED_IDL_HARD_FAILURE` gap Codex left deliberately
    visible in Seq 202 rather than filling with an invented map. It is now a retrieved pin, with
    provenance recorded here and written into artifact metadata: an interface without a source
    URL, commit and access date is not pinned, it is merely present.
    """
    pump = load_pinned_idl(pump_path, PUMP_IDL_SHA256, PUMP_PROGRAM)
    pumpswap = load_pinned_idl(pumpswap_path, PUMPSWAP_IDL_SHA256, PUMPSWAP_PROGRAM)
    return {
        "pump_idl_path": pump_path,
        "pump_idl_sha256": PUMP_IDL_SHA256,
        "pump_program": pump["address"],
        "pumpswap_idl_path": pumpswap_path,
        "pumpswap_idl_sha256": PUMPSWAP_IDL_SHA256,
        "pumpswap_program": pumpswap["address"],
        "idl_source_repo": IDL_SOURCE_REPO,
        "idl_source_commit": IDL_SOURCE_COMMIT,
        "idl_access_date": IDL_ACCESS_DATE,
    }


def target_idl_maps(pump_path=PUMP_IDL_PATH, pumpswap_path=PUMPSWAP_IDL_PATH):
    """{program id: {discriminator hex: instruction name}} for every target program.

    Built in one place so a caller cannot classify against a partial set by accident and then
    record unknown-discriminator failures that are really missing-IDL failures.
    """
    maps = {
        PUMP_PROGRAM: idl_instruction_map(
            load_pinned_idl(pump_path, PUMP_IDL_SHA256, PUMP_PROGRAM)),
        PUMPSWAP_PROGRAM: idl_instruction_map(
            load_pinned_idl(pumpswap_path, PUMPSWAP_IDL_SHA256, PUMPSWAP_PROGRAM)),
    }
    require_all_target_idls(maps)
    return maps


def require_all_target_idls(idl_maps):
    missing = [program for program in TARGET_PROGRAMS if program not in idl_maps]
    if missing:
        raise FreezeViolation(
            "target decoder map missing pinned IDL(s): " + ", ".join(missing))
    return True


def record_decoder_manifest(database, manifest):
    """Write missing keys once; refuse metadata drift on resume."""
    present = dict(database.execute("SELECT key,value FROM metadata"))
    for key, value in manifest.items():
        value = str(value)
        if key in present and present[key] != value:
            raise FreezeViolation(
                f"decoder metadata drift for {key}: {present[key]!r} != {value!r}")
        if key not in present:
            database.execute("INSERT INTO metadata VALUES (?,?)", (key, value))
    return True


def classify_instruction(program_id, data, idl_maps):
    """Classify one instruction. Returns `(target, name_or_None, discriminator_or_None, reason)`.

    §7 as amended by Seq 198: every Pump/PumpSwap instruction is classified and an unknown
    discriminator on those programs **fails visibly**. A non-target program id is preserved as a
    non-target program id — B9d does not pretend an arbitrary third-party program has a Pump IDL,
    and equally never lets an unrecognised program pass as a reserve mutation.
    """
    if program_id not in TARGET_PROGRAMS:
        return False, None, None, None
    discriminator = instruction_discriminator(data)
    if discriminator is None:
        return True, None, None, "target instruction data too short to carry a discriminator"
    name = idl_maps.get(program_id, {}).get(discriminator)
    if name is None:
        return True, None, discriminator, (
            f"unknown {program_id} discriminator {discriminator}; not dropped, not bucketed as "
            "'other', not inferred from an adjacent event")
    return True, name, discriminator, None


def program_version_rows(database, program_id):
    """Load and validate the frozen interface intervals for one target program."""
    columns = ("program_id", "from_slot", "to_slot", "idl_path", "idl_sha256",
               "deploy_slot", "evidence_key", "coverage")
    rows = [dict(zip(columns, row)) for row in database.execute(
        "SELECT program_id,from_slot,to_slot,idl_path,idl_sha256,deploy_slot,evidence_key,coverage "
        "FROM program_version WHERE program_id=? ORDER BY from_slot", (program_id,))]
    rows = assert_boundary_coverage(program_id, rows)
    expected = {
        PUMP_PROGRAM: (PUMP_IDL_PATH, PUMP_IDL_SHA256),
        PUMPSWAP_PROGRAM: (PUMPSWAP_IDL_PATH, PUMPSWAP_IDL_SHA256),
    }[program_id]
    mismatched = [row for row in rows
                  if (row["idl_path"], row["idl_sha256"]) != expected]
    if mismatched:
        first = mismatched[0]
        raise FreezeViolation(
            f"{program_id}: covered interval {first['from_slot']}..{first['to_slot']} names "
            f"{first['idl_path']} at {first['idl_sha256']}, but this decoder loaded "
            f"{expected[0]} at {expected[1]}; version-aware coverage is not permission to decode "
            "with a different revision")
    return rows


def interval_idls(intervals):
    """Pinned IDL documents loaded from the revision each program's intervals declare."""
    documents = {}
    for program, rows in intervals.items():
        declared = {(row["idl_path"], row["idl_sha256"]) for row in rows
                    if row["coverage"] == "covered"}
        if len(declared) != 1:
            raise FreezeViolation(
                f"{program}: covered intervals declare {len(declared)} distinct revisions; a single "
                "decoder pass cannot attribute its output to more than one")
        path, digest = declared.pop()
        documents[program] = load_pinned_idl(path, digest, program)
    return documents


def interval_idl_maps(intervals):
    """Discriminator maps loaded from the revision each program's own intervals declare.

    `program_version_rows` has already asserted that every covered interval names one revision and
    that it equals this decoder's pin, so this cannot load a surprise. The point is provenance: the
    map used to classify is derived from the artifact's declared `idl_path`/`idl_sha256`, so a row's
    `idl_name` is attributable to a revision recorded in the artifact rather than to whatever
    happened to be in memory.
    """
    return {program: idl_instruction_map(idl)
            for program, idl in interval_idls(intervals).items()}


def assert_target_classification_accounted(database):
    """Every target instruction is either named or has a failure row at its own coordinates.

    `classify_instruction` guarantees this by construction today. Asserting it means a later change
    that stops returning a `reason` cannot silently produce unnamed, unaccounted target rows — the
    "97% classified" failure §11 warns about, arriving as absence rather than as a number.
    """
    unaccounted = database.execute(
        "SELECT count(*) FROM instruction i WHERE i.target = 1 AND i.idl_name IS NULL "
        "AND NOT EXISTS (SELECT 1 FROM classification_failure f "
        "  WHERE f.slot = i.slot AND f.transaction_index = i.transaction_index "
        "    AND f.outer_index = i.outer_index AND f.inner_index = i.inner_index)").fetchone()[0]
    if unaccounted:
        raise FreezeViolation(
            f"{unaccounted:,} target instruction(s) are neither named nor recorded as a "
            "classification failure; they would vanish from both the results and the failure count")
    return True


def decode_artifact(database, b9c_path=B9C_PATH, b9a_path=B9A_PATH,
                    check_sources=True, idl_maps=None):
    """Materialize the canonical instruction stream from a complete raw artifact.

    All publication gates and both target-program boundary maps are checked before the first
    derived write. The materialization is one transaction: a decode error rolls the whole attempt
    back, while unknown target discriminators are preserved in both `instruction` and
    `classification_failure` rather than dropped. Existing derived rows are refused so a retry
    cannot silently mix decoder revisions.
    """
    verification = verify_artifact(
        database, b9c_path=b9c_path, b9a_path=b9a_path, check_sources=check_sources)
    refuse_if_complete(database)
    intervals = {program: program_version_rows(database, program)
                 for program in TARGET_PROGRAMS}
    # Build the classifier from the revision the ARTIFACT declares, so what is asserted and what is
    # used are the same object. Previously the intervals were validated against the module pins
    # while classification used a separately supplied map: passing a fabricated map produced a row
    # labelled with an invented instruction name, zero classification failures, and metadata still
    # naming the pinned revision. Reproduced before this changed.
    idls = interval_idls(intervals)
    derived = {program: idl_instruction_map(idl) for program, idl in idls.items()}
    if idl_maps is not None and idl_maps != derived:
        raise FreezeViolation(
            "supplied idl_maps disagree with the revision this artifact's program_version rows "
            "declare; a decoder map that is not the declared revision makes every idl_name in the "
            "output unattributable")
    maps = derived
    require_all_target_idls(maps)

    existing = {
        "instruction": database.execute("SELECT count(*) FROM instruction").fetchone()[0],
        "classification_failure": database.execute(
            "SELECT count(*) FROM classification_failure").fetchone()[0],
        "reserve_observation": database.execute(
            "SELECT count(*) FROM reserve_observation").fetchone()[0],
    }
    decode_metadata = dict(database.execute(
        "SELECT key,value FROM metadata WHERE key IN "
        "('decoded_at_unix','decoder_classification_failures')"))
    if any(existing.values()) or decode_metadata:
        raise FreezeViolation(
            "derived decoder output already exists: refusing to mix or overwrite a prior pass "
            f"(rows={existing}, metadata_keys={sorted(decode_metadata)})")

    instruction_count = target_count = failure_count = 0
    with database:
        rows = database.execute(
            "SELECT c.signature,c.slot,c.transaction_index,t.raw_zlib "
            "FROM transaction_coordinate c JOIN raw_transaction t USING(signature) "
            "ORDER BY c.slot,c.transaction_index")
        for signature, slot, transaction_index, blob in rows:
            result = raw_result(blob)
            if result is None:
                raise FreezeViolation(f"{signature}: preserved transaction response has null result")
            envelopes = envelope_instructions(result)
            # Decode and parent every Anchor CPI event before writing this transaction. This is the
            # reserve-evidence seam: a malformed event or ambiguous stack relation rolls back the
            # pass rather than becoming an unknown instruction or attaching to a nearby trade.
            associate_cpi_events(envelopes, idls)
            for envelope in envelopes:
                program_id = envelope["program_id"]
                if program_id in TARGET_PROGRAMS:
                    # Resolve every target instruction at its own slot. Full-range coverage is a
                    # precondition above; this per-row lookup prevents a later refactor from using
                    # a nearest or current revision by accident.
                    resolve_version(program_id, slot, intervals[program_id])
                event = decode_anchor_cpi_event(program_id, envelope["data"], idls)
                if event is None:
                    target, name, discriminator, reason = classify_instruction(
                        program_id, envelope["data"], maps)
                else:
                    target, name = True, f"event:{event['name']}"
                    discriminator = envelope["data"][:8].hex()
                    reason = None
                coordinates = (slot, transaction_index, envelope["outer_index"],
                               envelope["inner_index"])
                database.execute(
                    "INSERT INTO instruction "
                    "(slot,transaction_index,outer_index,inner_index,signature,program_id,"
                    "discriminator,idl_name,target,accounts_json,data_len) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    coordinates + (signature, program_id, discriminator, name, int(target),
                                   json.dumps(envelope["accounts"], separators=(",", ":")),
                                   len(envelope["data"])))
                instruction_count += 1
                target_count += int(target)
                if reason is not None:
                    database.execute(
                        "INSERT INTO classification_failure "
                        "(signature,slot,transaction_index,outer_index,inner_index,program_id,"
                        "discriminator,reason,context_json) VALUES (?,?,?,?,?,?,?,?,?)",
                        (signature,) + coordinates + (program_id, discriminator, reason,
                         json.dumps({"data_len": len(envelope["data"])},
                                    separators=(",", ":"))))
                    failure_count += 1
        database.execute(
            "INSERT INTO metadata(key,value) VALUES ('decoded_at_unix',?)",
            (str(time.time()),))
        database.execute(
            "INSERT INTO metadata(key,value) VALUES ('decoder_classification_failures',?)",
            (str(failure_count),))
        # Inside the transaction, so a violation rolls the whole materialization back rather than
        # leaving accounted and unaccounted rows committed together.
        assert_target_classification_accounted(database)
    return {"verification": verification, "instructions": instruction_count,
            "target_instructions": target_count, "classification_failures": failure_count}


# ---------------------------------------------------------------------------------------------
# Authorized read-only evidence collection (§10; owner authorization Seq 218)
# ---------------------------------------------------------------------------------------------

def endpoint_reference(endpoint):
    """Credential-free endpoint identity suitable for artifact metadata."""
    parsed = urllib.parse.urlsplit(endpoint)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise FreezeViolation("RPC endpoint must be an http(s) URL")
    port = f":{parsed.port}" if parsed.port else ""
    return f"{parsed.scheme}://{parsed.hostname}{port}{parsed.path}"


def rpc_request(endpoint, method, params, request_id=1, timeout=60, opener=None, retries=8):
    """Return byte-exact response plus parsed result; RPC errors are fatal and preserved by caller."""
    request_body = json.dumps({"jsonrpc": "2.0", "id": request_id, "method": method,
                               "params": params}, separators=(",", ":")).encode()
    request = urllib.request.Request(endpoint, data=request_body,
                                     headers={"Content-Type": "application/json"})
    transport = opener or urllib.request.urlopen
    for attempt in range(retries + 1):
        try:
            with transport(request, timeout=timeout) as response:
                raw = response.read()
            break
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as error:
            retryable = not isinstance(error, urllib.error.HTTPError) or error.code in (
                408, 429, 500, 502, 503, 504)
            if not retryable or attempt == retries:
                raise FreezeViolation(f"{method} transport failed after {attempt + 1} attempt(s): "
                                      f"{type(error).__name__}") from error
            headers = getattr(error, "headers", None)
            retry_after = headers.get("Retry-After") if headers is not None else None
            delay = float(retry_after) if retry_after and retry_after.isdigit() else min(30, 2 ** attempt)
            time.sleep(delay)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise FreezeViolation(f"{method} returned non-JSON bytes: {error}") from error
    if payload.get("error") is not None:
        raise FreezeViolation(f"{method} RPC error: {payload['error']}")
    if "result" not in payload:
        raise FreezeViolation(f"{method} response lacks result")
    return raw, payload["result"]


def store_raw(database, table, key_column, key, method, params, raw, received_at=None):
    """Insert one immutable raw response; an existing key must have identical bytes."""
    digest = hashlib.sha256(raw).hexdigest()
    existing = database.execute(
        f"SELECT response_sha256 FROM {table} WHERE {key_column}=?", (key,)).fetchone()
    if existing:
        if existing[0] != digest:
            raise FreezeViolation(f"{table} {key} changed response bytes on resume")
        return False
    database.execute(
        f"INSERT INTO {table} ({key_column},method,params_json,received_at_unix,response_sha256,"
        "raw_zlib) VALUES (?,?,?,?,?,?)",
        (key, method, json.dumps(params, separators=(",", ":")), received_at or time.time(),
         digest, zlib.compress(raw, 6)))
    return True


REQUIRED_META_FIELDS = ("err", "fee", "innerInstructions", "preBalances", "postBalances",
                        "preTokenBalances", "postTokenBalances", "logMessages")


def assert_transaction_shape(signature, result):
    """Preflight the exact base64 response shape before the main population runs."""
    if not isinstance(result, dict) or not isinstance(result.get("meta"), dict):
        raise FreezeViolation(f"{signature}: getTransaction result/meta is absent")
    missing = [field for field in REQUIRED_META_FIELDS if field not in result["meta"]]
    if missing:
        raise FreezeViolation(f"{signature}: getTransaction meta lacks {', '.join(missing)}")
    transaction = result.get("transaction")
    if not (isinstance(transaction, list) and len(transaction) == 2 and
            isinstance(transaction[0], str) and transaction[1] == "base64"):
        raise FreezeViolation(f"{signature}: transaction is not [base64-bytes,'base64']")
    return True


def initialize_run(database, endpoint, digests):
    schema(database)
    refuse_if_complete(database)
    assert_resumable(database, digests)
    record_decoder_manifest(database, decoder_manifest())
    values = {"b9c_sha256": next((v for k, v in digests.items() if v == B9C_SHA256), B9C_SHA256),
              "b9a_sha256": next((v for k, v in digests.items() if v == B9A_SHA256), B9A_SHA256),
              "endpoint_reference": endpoint_reference(endpoint),
              "authorization_seq": "218", "schema_version": SCHEMA_VERSION,
              "cutoff_slot": str(CUTOFF_SLOT)}
    present = dict(database.execute("SELECT key,value FROM metadata"))
    for key, value in values.items():
        if key in present and present[key] != value:
            raise FreezeViolation(f"run metadata drift for {key}")
        database.execute("INSERT OR IGNORE INTO metadata VALUES (?,?)", (key, value))
    database.execute("INSERT OR IGNORE INTO metadata VALUES ('started_at_unix',?)",
                     (str(time.time()),))
    database.commit()


def collect_raw_population(endpoint, output, b9c_path=B9C_PATH, b9a_path=B9A_PATH,
                           max_slots=None, max_transactions=None, progress_every=100,
                           calls_per_second=2.5):
    """Resumably preserve block coordinates and transaction response bodies; no decoding yet."""
    # §11: this must be the first observable action on an existing output. In particular it comes
    # before source hashing/population scans and before the writable `connect()` that sets WAL and
    # synchronous pragmas. A completed rerun is byte-immutable and has no RPC opportunity.
    refuse_completed_artifact_before_work(output)
    digests = assert_sources(b9c_path, b9a_path)
    grouped = frozen_population_by_slot(b9c_path, b9a_path)
    database = connect(output)
    try:
        initialize_run(database, endpoint, digests)
        if calls_per_second <= 0:
            raise FreezeViolation("calls_per_second must be positive")
        minimum_interval = 1.0 / calls_per_second
        last_call = [None]

        def paced_request(method, params, request_id):
            if last_call[0] is not None:
                remaining = minimum_interval - (time.monotonic() - last_call[0])
                if remaining > 0:
                    time.sleep(remaining)
            raw_result = rpc_request(endpoint, method, params, request_id=request_id)
            last_call[0] = time.monotonic()
            return raw_result

        done_blocks = {row[0] for row in database.execute("SELECT slot FROM raw_block_signatures")}
        block_count = 0
        for slot in sorted(grouped):
            if slot in done_blocks:
                continue
            if max_slots is not None and block_count >= max_slots:
                break
            params = [slot, {"commitment": "finalized", "transactionDetails": "signatures",
                             "rewards": False, "maxSupportedTransactionVersion": 0}]
            raw, result = paced_request("getBlock", params, request_id=slot)
            if not isinstance(result, dict) or not isinstance(result.get("signatures"), list):
                raise FreezeViolation(f"slot {slot}: getBlock lacks a signatures list")
            coordinates = transaction_coordinates(slot, result["signatures"], grouped[slot])
            with database:
                store_raw(database, "raw_block_signatures", "slot", slot, "getBlock", params, raw)
                database.executemany(
                    "INSERT OR IGNORE INTO transaction_coordinate VALUES (?,?,?)",
                    [(signature, slot, index) for signature, index in coordinates.items()])
            block_count += 1
            if progress_every and block_count % progress_every == 0:
                print(f"blocks +{block_count}; latest slot {slot}", flush=True)

        # A bounded `--max-slots` invocation is an explicit partial collection probe and must
        # remain resumable. An unbounded production pass, however, may not cross into transaction
        # bodies until the frozen block and signature populations are both exact.
        coordinates = transaction_body_coordinates(database, require_complete=max_slots is None)
        done_transactions = {row[0] for row in database.execute("SELECT signature FROM raw_transaction")}
        transaction_count = 0
        preflight_done = database.execute(
            "SELECT value FROM metadata WHERE key='transaction_shape_preflight' ").fetchone()
        for signature, slot in coordinates:
            if signature in done_transactions:
                continue
            if max_transactions is not None and transaction_count >= max_transactions:
                break
            params = [signature, {"encoding": "base64", "commitment": "finalized",
                                  "maxSupportedTransactionVersion": 0}]
            raw, result = paced_request("getTransaction", params, transaction_count + 1)
            if result is None:
                raise FreezeViolation(f"{signature}: finalized getTransaction returned null")
            if not preflight_done:
                assert_transaction_shape(signature, result)
            reconcile_slot(signature, slot, result.get("slot"))
            with database:
                store_raw(database, "raw_transaction", "signature", signature,
                          "getTransaction", params, raw)
                if not preflight_done:
                    database.execute(
                        "INSERT INTO metadata VALUES ('transaction_shape_preflight',?)",
                        (signature,))
                    preflight_done = (signature,)
            transaction_count += 1
            if progress_every and transaction_count % progress_every == 0:
                print(f"transactions +{transaction_count}; latest slot {slot}", flush=True)

        # `--max-transactions` is an explicitly partial, resumable probe. Only an unbounded
        # production pass may claim raw collection returned successfully, and it must carry every
        # frozen body before any later decoder orchestration can treat the artifact as ready.
        if max_transactions is None:
            assert_raw_transaction_population(database)
        return {"blocks_added": block_count, "transactions_added": transaction_count,
                "blocks_total": database.execute(
                    "SELECT count(*) FROM raw_block_signatures").fetchone()[0],
                "transactions_total": database.execute(
                    "SELECT count(*) FROM raw_transaction").fetchone()[0]}
    finally:
        database.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    verify = sub.add_parser("verify", help="offline: assert sources and re-derive the population")
    verify.add_argument("--b9c", default=B9C_PATH)
    verify.add_argument("--b9a", default=B9A_PATH)
    init = sub.add_parser("init", help="offline: create the evidence artifact schema")
    init.add_argument("path")
    run = sub.add_parser("run", help="authorized read-only resumable raw evidence collection")
    run.add_argument("output")
    run.add_argument("--rpc-env", default="SOLANA_RPC_URL")
    run.add_argument("--max-slots", type=int)
    run.add_argument("--max-transactions", type=int)
    run.add_argument("--progress-every", type=int, default=100)
    run.add_argument("--calls-per-second", type=float, default=2.5)
    audit = sub.add_parser(
        "verify-artifact",
        help="offline: run every §11 publication gate against a collected artifact")
    audit.add_argument("path")
    audit.add_argument("--b9c", default=B9C_PATH)
    audit.add_argument("--b9a", default=B9A_PATH)
    audit.add_argument("--skip-sources", action="store_true",
                       help="skip source-artifact hashing only; never skips an evidence gate")
    decode = sub.add_parser(
        "decode", help="offline: verify a complete artifact and materialize canonical instructions")
    decode.add_argument("path")
    decode.add_argument("--b9c", default=B9C_PATH)
    decode.add_argument("--b9a", default=B9A_PATH)
    decode.add_argument("--skip-sources", action="store_true",
                        help="skip source-artifact hashing only; never skips an evidence gate")

    args = parser.parse_args(argv)
    if args.command == "decode":
        database = connect(args.path)
        try:
            summary = decode_artifact(database, args.b9c, args.b9a,
                                      check_sources=not args.skip_sources)
        finally:
            database.close()
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0
    if args.command == "verify-artifact":
        # Read-only by construction: publication verification must never be able to repair the
        # evidence it is checking, and the live collector owns the file while it runs.
        database = connect(args.path, readonly=True)
        try:
            summary = verify_artifact(database, args.b9c, args.b9a,
                                      check_sources=not args.skip_sources)
        finally:
            database.close()
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0
    if args.command == "verify":
        digests = assert_sources(args.b9c, args.b9a)
        manifest = decoder_manifest()
        signatures, slots = frozen_population(args.b9c, args.b9a)
        print(json.dumps({
            "sources_ok": digests,
            "decoder": manifest,
            "signatures": len(signatures),
            "slots": len(slots),
            "slot_range": [min(slots), max(slots)],
            "request_floor": len(signatures) + len(slots),
        }, indent=2))
        return 0
    if args.command == "init":
        database = connect(args.path)
        try:
            schema(database)
            refuse_if_complete(database)
            record_decoder_manifest(database, decoder_manifest())
            database.commit()
        finally:
            database.close()
        print(f"initialised {SCHEMA_VERSION} artifact at {args.path}")
        return 0
    endpoint = os.environ.get(args.rpc_env)
    if not endpoint:
        raise SystemExit(f"missing RPC endpoint environment variable {args.rpc_env}")
    result = collect_raw_population(
        endpoint, args.output, max_slots=args.max_slots,
        max_transactions=args.max_transactions, progress_every=args.progress_every,
        calls_per_second=args.calls_per_second)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
