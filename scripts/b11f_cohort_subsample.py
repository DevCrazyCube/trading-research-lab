#!/usr/bin/env python3
"""B11F cohort subsample -- a deterministic hash-on-mint uniform draw.

Preregistered in research/B11F_COHORT_SUBSAMPLE_PREREGISTRATION.json (frozen a55125b,
amended e189fa4, both before any selected-set outcome existed). The rule:

    key(mint) = int.from_bytes(sha256(SEED-bytes || mint-bytes), "big")
    select the N mints with the SMALLEST key.

The selection reads the mint -- the creation-time identity -- and the frozen SEED, and
NOTHING ELSE. It never reads a signature count, a trade, a graduation, a price or a
reserve: those ARE the outcome, and choosing the sample on them would be choosing on the
dependent variable, which is exactly what the preregistration forbids. N sets HOW MANY
curves are drawn, never WHICH -- the hash order fixes which, and N takes a prefix of it.

The draw is uniform (a hash is uniform on its input) and reproducible from (SEED, N) and
the cohort's mints alone, so a reviewer recomputes the exact set. It is also NESTED: a
larger N returns a superset of a smaller N's selection.

This module reads only identity columns. The subsample artifact it writes is itself a
fresh_cohort_identity artifact -- identity and regime only, no outcome -- so the downstream
collection gate accepts it exactly where the full cohort stood.
"""
import argparse
import hashlib
import importlib.util
import json
import pathlib
import sqlite3

# Frozen in the preregistration. Changing either value is a NEW study, not a re-run: SEED
# fixes which curves, N fixes how many. Neither may move once a selected-set outcome exists.
SEED = "b11f-cohort-subsample-v1"
DEFAULT_N = 5000

SCHEMA_VERSION = "1.0.0"
COHORT_COLUMNS = ("mint", "bonding_curve", "launch_slot", "is_mayhem_mode")


class SubsampleRefused(Exception):
    """Raised when the subsample cannot be produced without asserting something untrue."""


def selection_key(mint, seed=SEED):
    """A curve's position in the draw: a hash of its mint and the seed.

    The ONLY inputs are the creation-time identity (the mint) and the frozen seed. There is
    no path from here to any activity quantity, and the AST test proves it.
    """
    if not isinstance(mint, str) or not mint:
        raise SubsampleRefused(f"a cohort member has an empty or non-string mint: {mint!r}")
    if not isinstance(seed, str) or not seed:
        raise SubsampleRefused(f"the seed must be a non-empty string, got {seed!r}")
    return int.from_bytes(
        hashlib.sha256(seed.encode("utf-8") + mint.encode("utf-8")).digest(), "big")


def selected(cohort_mints, seed=SEED, n=DEFAULT_N):
    """The N mints with the smallest selection key. Pure: (mints, seed, n) -> mints.

    Ordered by the total key (selection_key, mint) so the result is deterministic even under
    the astronomically unlikely key collision -- the tie-break is the mint itself, a
    creation-time value, never an outcome. Nested by construction: ordered[:a] is a prefix of
    ordered[:b] for a < b, so a larger N is a superset of a smaller one.
    """
    mints = list(cohort_mints)
    if len(mints) != len(set(mints)):
        raise SubsampleRefused(
            "the cohort carries a duplicate mint; identity is not unique and a draw over it "
            "would weight some curves twice")
    if not mints:
        raise SubsampleRefused("the cohort is empty; absence is refusal, not a zero-size draw")
    if not isinstance(n, int) or isinstance(n, bool) or n < 1:
        raise SubsampleRefused(f"n must be a positive integer, got {n!r}")
    if n > len(mints):
        raise SubsampleRefused(
            f"n={n} exceeds the {len(mints)} available curves; a subsample cannot be larger "
            "than the cohort it draws from, and silently truncating to the population would "
            "make N a promise the data cannot keep")
    ordered = sorted(mints, key=lambda m: (selection_key(m, seed), m))
    return ordered[:n]


def _load_adapter():
    """The cohort adapter, loaded from this script's own directory.

    Reused so the subsample's recorded hash is computed by the SAME cohort_digest the
    downstream gate recomputes and checks -- the two can never disagree by construction.
    """
    path = pathlib.Path(__file__).resolve().parent / "b11d_cohort_adapter.py"
    spec = importlib.util.spec_from_file_location("b11d_cohort_adapter", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read_parent(source_path, adapter):
    """Verify the parent is a sealed fresh cohort, then read its full membership and window.

    Verifying first is the structural leakage guard: a parent that declared contains_outcomes
    != 0 -- i.e. carried any activity column -- is refused by assert_fresh_cohort before a
    single row is read, so the subsample can only ever draw from identity-and-regime rows.
    """
    adapter.assert_fresh_cohort(source_path)  # refuses a non-cohort or an outcome-bearing one
    database = sqlite3.connect(f"file:{source_path}?mode=ro", uri=True)
    try:
        members = [
            {"mint": m, "bonding_curve": c, "launch_slot": int(s),
             "is_mayhem_mode": int(g), "create_signature": sig}
            for m, c, s, g, sig in database.execute(
                "SELECT mint, bonding_curve, launch_slot, is_mayhem_mode, create_signature "
                "FROM cohort_identity")]
        metadata = dict(database.execute("SELECT key, value FROM metadata"))
        provenance = database.execute(
            "SELECT start_slot, end_slot_exclusive, slots_scanned, slots_retrieved, "
            "slots_skipped FROM provenance").fetchone()
    finally:
        database.close()
    if provenance is None:
        raise SubsampleRefused(
            f"{source_path} has no provenance row; the observation window it was enumerated "
            "over is unknown, and a subsample may not invent one")
    return members, metadata, provenance


def build_subsample(source_path, output_path, seed=SEED, n=DEFAULT_N):
    """Write the subsampled fresh-cohort artifact the collection gate will read.

    Deterministic: same (source, seed, n) -> same bytes. The written artifact is a
    fresh_cohort_identity artifact carrying exactly the N selected members, so the gate
    accepts it where the full cohort stood; its metadata records seed, n and the parent's
    cohort hash so the draw is auditable back to the population.
    """
    source_path = str(source_path)
    output_path = pathlib.Path(output_path)
    if output_path.exists():
        raise SubsampleRefused(
            f"{output_path} already exists. A subsample artifact is written once; rebuilding "
            "over one would silently replace the population a downstream hash was taken against")
    adapter = _load_adapter()
    members, parent_meta, provenance = _read_parent(source_path, adapter)

    by_mint = {m["mint"]: m for m in members}
    if len(by_mint) != len(members):
        raise SubsampleRefused("the parent cohort carries a duplicate mint")
    chosen_mints = selected(by_mint.keys(), seed=seed, n=n)
    chosen = [by_mint[mint] for mint in chosen_mints]

    source_sha256 = adapter.sha256_file(source_path)
    parent_cohort_sha256 = parent_meta.get("cohort_sha256")
    start_slot, end_slot_exclusive, slots_scanned, slots_retrieved, slots_skipped = provenance

    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    if temporary.exists():
        temporary.unlink()
    out = sqlite3.connect(str(temporary))
    try:
        out.executescript("""
            CREATE TABLE cohort_identity (
                mint TEXT PRIMARY KEY, bonding_curve TEXT NOT NULL UNIQUE,
                launch_slot INTEGER NOT NULL, is_mayhem_mode INTEGER NOT NULL,
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
            CREATE VIEW outcome AS
                SELECT mint, bonding_curve, launch_slot, is_mayhem_mode FROM cohort_identity;
        """)
        out.executemany(
            "INSERT INTO cohort_identity(mint, bonding_curve, launch_slot, is_mayhem_mode, "
            "create_signature) VALUES (?, ?, ?, ?, ?)",
            [(m["mint"], m["bonding_curve"], m["launch_slot"], m["is_mayhem_mode"],
              m["create_signature"]) for m in chosen])
        digest = adapter.cohort_digest(chosen)
        out.executemany("INSERT INTO metadata(key, value) VALUES (?, ?)", [
            ("schema_version", SCHEMA_VERSION),
            ("artifact_kind", "fresh_cohort_identity"),
            ("contains_outcomes", "0"),
            ("outcome_view_columns", ",".join(COHORT_COLUMNS)),
            ("cohort_sha256", digest),
            ("source_sha256", source_sha256),
            ("start_slot", str(int(start_slot))),
            ("end_slot_exclusive", str(int(end_slot_exclusive))),
            # Subsample provenance: the draw is auditable back to the population it came from.
            ("subsample_kind", "b11f_hash_on_mint_uniform"),
            ("subsample_seed", seed),
            ("subsample_n", str(int(n))),
            ("subsample_population", str(len(members))),
            ("subsample_parent_cohort_sha256", parent_cohort_sha256 or ""),
        ])
        out.execute(
            "INSERT INTO provenance VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (source_path, source_sha256, int(start_slot), int(end_slot_exclusive),
             int(slots_scanned), int(slots_retrieved), int(slots_skipped), len(chosen), digest))
        out.commit()
    finally:
        out.close()
    temporary.replace(output_path)

    # Fail closed: re-open through the same gate the consumers use. If what we just wrote is
    # not a cohort the gate accepts, that is discovered here, not by a collection run.
    verified = adapter.assert_fresh_cohort(str(output_path))
    if verified["members"] != n:
        raise SubsampleRefused(
            f"wrote {verified['members']} members, expected {n}; the artifact does not match "
            "the draw")
    return {"artifact": str(output_path), "members": len(chosen), "population": len(members),
            "cohort_sha256": digest, "source_sha256": source_sha256,
            "parent_cohort_sha256": parent_cohort_sha256, "seed": seed, "n": n,
            "start_slot": int(start_slot), "end_slot_exclusive": int(end_slot_exclusive)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", required=True,
                        help="the full fresh-cohort artifact to draw from (e.g. b11a_cohort.sqlite)")
    parser.add_argument("--output", required=True,
                        help="path to write the subsampled fresh-cohort artifact")
    parser.add_argument("--seed", default=SEED,
                        help=f"selection seed (frozen; default {SEED!r})")
    parser.add_argument("--n", type=int, default=DEFAULT_N,
                        help=f"number of curves to draw (owner-set; default {DEFAULT_N})")
    args = parser.parse_args(argv)
    try:
        result = build_subsample(args.source, args.output, seed=args.seed, n=args.n)
    except SubsampleRefused as error:
        raise SystemExit(f"REFUSING: {error}")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
