#!/usr/bin/env python3
"""B9d transaction-body reconstruction scaffold — OFFLINE ONLY.

Implements the amended freeze `research/B9D_TRANSACTION_BODY_PREREGISTRATION.md` up to, but not
including, network execution. Everything here runs with no RPC: source-hash and population
assertions, the evidence-artifact schema, the signature -> transaction-index mapping that §6 needs
because `getTransaction` does not carry that coordinate, canonical instruction keys, unknown-target
classification, resume, and completed-artifact immutability.

**`run` is deliberately gated closed.** B9d execution is 94,985 transaction fetches plus 38,853
block-signature fetches and requires an explicit owner authorisation that does not exist. The gate
is a hard stop in code, not a comment, so the scaffold cannot be started by accident.
"""
import argparse
import hashlib
import json
import sqlite3
import sys

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
    names = [entry["name"] for entry in idl.get("instructions", [])]
    if not names:
        raise FreezeViolation(
            "pinned IDL declares no instructions; refusing to classify against an empty interface")
    mapping = {}
    for name in names:
        digest = hashlib.sha256(f"global:{name}".encode()).digest()[:8].hex()
        if digest in mapping:
            raise FreezeViolation(
                f"discriminator collision between {mapping[digest]!r} and {name!r} in the pinned "
                "IDL; classification would be ambiguous")
        mapping[digest] = name
    return mapping


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


# ---------------------------------------------------------------------------------------------
# Execution gate (§10)
# ---------------------------------------------------------------------------------------------

AUTHORISATION_GATE = (
    "B9d network execution is NOT authorised and this scaffold refuses to start it.\n"
    f"  Frozen workload: {EXPECTED_SIGNATURES:,} getTransaction + {EXPECTED_SLOTS:,} getBlock "
    f"signature calls = {EXPECTED_SIGNATURES + EXPECTED_SLOTS:,} requests, before boundary "
    "verification.\n"
    "  ~10.6 h for the transaction component at B6j's measured ~2.5 calls/s; getBlock throughput "
    "is unmeasured, so the combined figure is a scenario, not a lower bound.\n"
    "  Standing authorisation on record (Seq 121) is 4 min/hour for ~6.2 h, granted for B8b.\n"
    "  Requires a new explicit owner authorisation covering endpoint and duration. See "
    "research/B9D_TRANSACTION_BODY_PREREGISTRATION.md §10.")


def run_gate():
    raise SystemExit(AUTHORISATION_GATE)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    verify = sub.add_parser("verify", help="offline: assert sources and re-derive the population")
    verify.add_argument("--b9c", default=B9C_PATH)
    verify.add_argument("--b9a", default=B9A_PATH)
    init = sub.add_parser("init", help="offline: create the evidence artifact schema")
    init.add_argument("path")
    sub.add_parser("run", help="GATED: requires explicit owner authorisation")

    args = parser.parse_args(argv)
    if args.command == "verify":
        digests = assert_sources(args.b9c, args.b9a)
        signatures, slots = frozen_population(args.b9c, args.b9a)
        print(json.dumps({
            "sources_ok": digests,
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
            database.commit()
        finally:
            database.close()
        print(f"initialised {SCHEMA_VERSION} artifact at {args.path}")
        return 0
    run_gate()


if __name__ == "__main__":
    sys.exit(main())
