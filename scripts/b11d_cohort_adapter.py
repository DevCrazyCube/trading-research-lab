"""B11d — deterministic fresh-cohort adapter: B7d create enumeration to a B9c/B9d cohort artifact.

Why this exists
---------------
B9c and B9d were written against B9a, whose `outcome` table carries reserves, completeness and
account state — genuinely outcome-bearing columns. A fresh window has no B9a and must never have
one manufactured: inventing an outcome table to satisfy a schema would put fabricated results
underneath every gate downstream.

But B9c and B9d do not actually read the outcomes. Between them they read exactly four columns:

    b9c   SELECT mint, bonding_curve, launch_slot FROM outcome
    b9d   SELECT bonding_curve, is_mayhem_mode FROM outcome
    b9d   SELECT mint, bonding_curve FROM outcome WHERE is_mayhem_mode = 0

All four are **identity or regime** facts, and all four are present in B7d's `create_event`. So this
adapter carries those and nothing else.

What it will not do
-------------------
- **It manufactures no outcome.** The artifact's real table is `cohort_identity` and holds four
  columns. An `outcome` VIEW over it exists only so the consumers' existing SQL works unchanged, and
  a view cannot grow a reserves column by accident. `metadata.contains_outcomes` is `0`, and the
  consumers check it.
- **It filters nothing.** Every create the enumeration found becomes a cohort member. A cohort
  selected on any property of what happened afterwards would be a cohort selected on the answer, so
  the only rows excluded are ones that fail an integrity check — and those abort the build rather
  than being dropped.
- **It assumes no coverage.** The enumeration must have visited every slot in its declared window
  and resolved every one; an unscanned slot is a create nobody looked for.
"""
import argparse
import hashlib
import json
import pathlib
import sqlite3
import sys

SCHEMA_VERSION = "1.0.0"

# The complete set of columns any downstream consumer reads from a B9a-shaped source, established
# by inspection of b9c/b9d/b9e rather than by assumption.
COHORT_COLUMNS = ("mint", "bonding_curve", "launch_slot", "is_mayhem_mode")

# Slot statuses B7d may legitimately record. `skipped` is a slot the chain never produced, which is
# normal; the two error statuses are unresolved evidence and abort the build.
STATUS_RETRIEVED = "retrieved"
STATUS_SKIPPED = "skipped"
RESOLVED_STATUSES = (STATUS_RETRIEVED, STATUS_SKIPPED)
ERROR_STATUSES = ("decode_error", "reconciliation_error")


class CohortRefused(Exception):
    """Raised when a fresh cohort cannot be derived without asserting something untrue."""


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_metadata(source):
    present = dict(source.execute("SELECT key, value FROM metadata"))
    for key in ("start_slot", "end_slot_exclusive"):
        if key not in present:
            raise CohortRefused(
                f"the enumeration states no {key}; a cohort whose window is undeclared cannot be "
                "checked for coverage, and an unchecked window is one nobody can show was complete")
    return present


def assert_enumeration_complete(source):
    """Every slot in the declared window visited, and every visit resolved.

    An unscanned slot is a create nobody looked for. A slot that errored is a create nobody could
    read. Neither may be silently absent from a cohort that calls itself exhaustive.
    """
    metadata = _read_metadata(source)
    start = int(metadata["start_slot"])
    end_exclusive = int(metadata["end_slot_exclusive"])
    if end_exclusive <= start:
        raise CohortRefused(f"the enumeration window {start}..{end_exclusive} is empty")

    scanned = dict(source.execute("SELECT slot, status FROM slot_scan"))
    expected = end_exclusive - start
    if len(scanned) != expected:
        missing = expected - len(scanned)
        raise CohortRefused(
            f"the enumeration visited {len(scanned)} of {expected} slots in "
            f"[{start}, {end_exclusive}); {missing} were never looked at, and an unscanned slot is "
            "a create nobody looked for")
    outside = [slot for slot in scanned if not start <= slot < end_exclusive]
    if outside:
        raise CohortRefused(
            f"{len(outside)} scanned slots fall outside the declared window (first {min(outside)})")
    unresolved = sorted(slot for slot, status in scanned.items()
                        if status not in RESOLVED_STATUSES)
    if unresolved:
        statuses = sorted({scanned[slot] for slot in unresolved})
        raise CohortRefused(
            f"{len(unresolved)} slots are unresolved with statuses {statuses} (first "
            f"{unresolved[0]}); a slot that errored is a create nobody could read")

    errors = source.execute("SELECT COUNT(*) FROM decode_error").fetchone()[0]
    if errors:
        raise CohortRefused(
            f"the enumeration recorded {errors} decode errors; each one is an instruction that may "
            "have been a create, and a cohort built over them is a lower bound calling itself a "
            "population")
    return {"start_slot": start, "end_slot_exclusive": end_exclusive, "slots_scanned": len(scanned),
            "slots_retrieved": sum(1 for s in scanned.values() if s == STATUS_RETRIEVED),
            "slots_skipped": sum(1 for s in scanned.values() if s == STATUS_SKIPPED)}


def read_cohort(source, coverage):
    """One row per bonding curve, exhaustively, with every integrity failure aborting the build."""
    rows = list(source.execute(
        "SELECT mint, bonding_curve, slot, is_mayhem_mode, signature "
        "FROM create_event ORDER BY slot, transaction_index, outer_instruction_index, "
        "inner_instruction_index"))
    cohort, by_mint = {}, {}
    for mint, curve, slot, mayhem, signature in rows:
        if not mint or not curve:
            raise CohortRefused(
                f"a create at slot {slot} names mint {mint!r} and curve {curve!r}; an identity "
                "that is missing is not an identity we may guess")
        if slot is None:
            raise CohortRefused(f"the create for {curve} has no slot")
        if not coverage["start_slot"] <= slot < coverage["end_slot_exclusive"]:
            raise CohortRefused(
                f"a create at slot {slot} lies outside the enumerated window "
                f"[{coverage['start_slot']}, {coverage['end_slot_exclusive']}); a cohort wider than "
                "the window it was derived from has members nobody enumerated")
        if mayhem is None:
            raise CohortRefused(
                f"the create for {curve} does not state is_mayhem_mode. It is a regime field the "
                "fetch set depends on, and an unknown regime is not a permissive one")
        if curve in cohort:
            raise CohortRefused(
                f"bonding curve {curve} has two create events; a curve created twice is two "
                "populations sharing an address, and picking one would be a filter")
        if mint in by_mint:
            raise CohortRefused(
                f"mint {mint} appears on two bonding curves ({by_mint[mint]} and {curve}); the "
                "identity map must be one-to-one before anything is fetched against it")
        cohort[curve] = {"mint": mint, "bonding_curve": curve, "launch_slot": int(slot),
                         "is_mayhem_mode": int(mayhem), "create_signature": signature}
        by_mint[mint] = curve
    if not cohort:
        raise CohortRefused(
            "the enumeration found no creates in its window. That may be true, and it is not "
            "something this adapter may decide: an empty cohort aborts rather than producing an "
            "artifact every downstream gate would pass vacuously")
    return [cohort[curve] for curve in sorted(cohort)]


def cohort_digest(members):
    """A hash of exactly the identities and regimes, in canonical order."""
    payload = [[m["mint"], m["bonding_curve"], m["launch_slot"], m["is_mayhem_mode"]]
               for m in sorted(members, key=lambda m: (m["launch_slot"], m["mint"]))]
    return hashlib.sha256(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")).hexdigest()


def build(source_path, output_path):
    """Derive the fresh cohort artifact. Deterministic: same input, same bytes."""
    source_path = str(source_path)
    output_path = pathlib.Path(output_path)
    if output_path.exists():
        raise CohortRefused(
            f"{output_path} already exists. A cohort artifact is written once; rebuilding over one "
            "would silently replace the population every downstream hash was taken against")
    source = sqlite3.connect(f"file:{source_path}?mode=ro", uri=True)
    try:
        coverage = assert_enumeration_complete(source)
        members = read_cohort(source, coverage)
        source_sha256 = sha256_file(source_path)
    finally:
        source.close()

    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    if temporary.exists():
        temporary.unlink()
    out = sqlite3.connect(str(temporary))
    try:
        out.executescript("""
            CREATE TABLE cohort_identity (
                mint TEXT PRIMARY KEY, bonding_curve TEXT NOT NULL UNIQUE,
                launch_slot INTEGER NOT NULL, is_mayhem_mode INTEGER NOT NULL,
                -- Which create event produced this row. Provenance, and deliberately NOT in the
                -- view: the view is the consumers' contract and must expose exactly what they
                -- read, so a column here that is absent there is what proves the view is a
                -- projection rather than the table wearing a different name.
                create_signature TEXT NOT NULL
            );
            CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE provenance (
                source_path TEXT NOT NULL, source_sha256 TEXT NOT NULL,
                start_slot INTEGER NOT NULL, end_slot_exclusive INTEGER NOT NULL,
                slots_scanned INTEGER NOT NULL, slots_retrieved INTEGER NOT NULL,
                slots_skipped INTEGER NOT NULL, members INTEGER NOT NULL,
                cohort_sha256 TEXT NOT NULL
            );
            -- The consumers' SQL says `FROM outcome`. This view exists so that keeps working, and
            -- it exposes four columns: a view cannot grow a reserves column by accident, and the
            -- table underneath is named for what it actually is.
            CREATE VIEW outcome AS
                SELECT mint, bonding_curve, launch_slot, is_mayhem_mode FROM cohort_identity;
        """)
        out.executemany(
            "INSERT INTO cohort_identity(mint, bonding_curve, launch_slot, is_mayhem_mode, "
            "create_signature) VALUES (?, ?, ?, ?, ?)",
            [(m["mint"], m["bonding_curve"], m["launch_slot"], m["is_mayhem_mode"],
              m["create_signature"]) for m in members])
        digest = cohort_digest(members)
        out.executemany("INSERT INTO metadata(key, value) VALUES (?, ?)", [
            ("schema_version", SCHEMA_VERSION),
            ("artifact_kind", "fresh_cohort_identity"),
            # The marker the consumers check. This artifact is identity and regime, and says so.
            ("contains_outcomes", "0"),
            ("outcome_view_columns", ",".join(COHORT_COLUMNS)),
            ("cohort_sha256", digest),
            ("source_sha256", source_sha256),
            ("start_slot", str(coverage["start_slot"])),
            ("end_slot_exclusive", str(coverage["end_slot_exclusive"])),
        ])
        out.execute(
            "INSERT INTO provenance VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (source_path, source_sha256, coverage["start_slot"], coverage["end_slot_exclusive"],
             coverage["slots_scanned"], coverage["slots_retrieved"], coverage["slots_skipped"],
             len(members), digest))
        out.commit()
    finally:
        out.close()
    temporary.replace(output_path)
    return {"artifact": str(output_path), "members": len(members), "cohort_sha256": digest,
            "source_sha256": source_sha256, **coverage}


def assert_fresh_cohort(path):
    """What a consumer checks before trusting a path that is not the burned B9a.

    The marker is checked rather than the filename: a fresh artifact that cannot say what it is has
    not earned the right to stand where B9a stood.
    """
    try:
        database = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.Error as error:
        # Read-only URI mode fails AT CONNECT for a path that does not exist, before any statement
        # runs — so this cannot be caught by the per-statement handlers below. It escaped as a bare
        # OperationalError, which meant b9d's `except CohortRefused` around this very call did not
        # catch it: the wrapper that exists to turn a bad cohort into a refusal was silently
        # inapplicable to the most ordinary bad cohort of all, one that is not there.
        raise CohortRefused(f"cannot open {path}: {error}") from error
    try:
        try:
            metadata = dict(database.execute("SELECT key, value FROM metadata"))
        except sqlite3.DatabaseError as error:
            raise CohortRefused(f"{path} has no metadata table: {error}")
        if metadata.get("artifact_kind") != "fresh_cohort_identity":
            raise CohortRefused(
                f"{path} does not declare itself a fresh cohort identity artifact; a source that "
                "cannot say what it is may not stand where B9a stood")
        if metadata.get("contains_outcomes") != "0":
            raise CohortRefused(
                f"{path} claims to contain outcomes. A fresh cohort carries identity and regime "
                "only, and anything else underneath a collection gate is fabricated")
        columns = [row[1] for row in database.execute("PRAGMA table_info(outcome)")]
        if tuple(columns) != COHORT_COLUMNS:
            raise CohortRefused(
                f"{path} exposes outcome columns {columns}, expected {list(COHORT_COLUMNS)}")
        members = database.execute("SELECT COUNT(*) FROM cohort_identity").fetchone()[0]
        if not members:
            raise CohortRefused(f"{path} carries no cohort members")
        recorded = metadata.get("cohort_sha256")
        rows = [{"mint": m, "bonding_curve": c, "launch_slot": s, "is_mayhem_mode": g}
                for m, c, s, g in database.execute(
                    "SELECT mint, bonding_curve, launch_slot, is_mayhem_mode FROM cohort_identity")]
        recomputed = cohort_digest(rows)
        if recorded != recomputed:
            raise CohortRefused(
                f"{path} records cohort hash {recorded} but its rows hash to {recomputed}; the "
                "population changed after the artifact was sealed")
        return {"members": members, "cohort_sha256": recomputed,
                "source_sha256": metadata.get("source_sha256"),
                "start_slot": int(metadata["start_slot"]),
                "end_slot_exclusive": int(metadata["end_slot_exclusive"])}
    finally:
        database.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    build_parser = sub.add_parser("build", help="derive the fresh cohort artifact from B7d output")
    build_parser.add_argument("--source", required=True, help="B7d create-enumeration database")
    build_parser.add_argument("--output", required=True, help="cohort artifact to write")
    verify = sub.add_parser("verify", help="offline: assert an artifact is a fresh cohort")
    verify.add_argument("path")
    args = parser.parse_args(argv)

    if args.command == "build":
        print(json.dumps(build(args.source, args.output), indent=2, sort_keys=True))
    else:
        print(json.dumps(assert_fresh_cohort(args.path), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except CohortRefused as error:
        print(f"CohortRefused: {error}", file=sys.stderr)
        sys.exit(2)
