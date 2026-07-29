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
import struct
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
        integers = {"u8": (1, False), "u16": (2, False), "u32": (4, False),
                    "u64": (8, False), "i8": (1, True), "i16": (2, True),
                    "i32": (4, True), "i64": (8, True)}
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
    run_gate()


if __name__ == "__main__":
    sys.exit(main())
