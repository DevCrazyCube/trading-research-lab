#!/usr/bin/env python3
"""B9f classification-failure coverage gate.

Implements `research/B9F_FAILURE_COVERAGE_PREREGISTRATION.md`. Offline, read-only, no network.

B9e bounds the RESERVE population. This bounds the INSTRUCTION population that sits inside.

`decode_artifact` persists every unrecognised target discriminator into `classification_failure`
rather than dropping it, which is right, and `verify_decoded_artifact` reconciles the total against
its own metadata. Neither establishes that the failures are *attributable* or *bounded*. A decode
pass could therefore produce a large and growing unknown-discriminator population, agree with its
own metadata, satisfy B9e, and still mean the instruction stream is not understood.

Two things follow, and both are enumeration choices rather than thresholds:

- The denominator is the **target instruction population**, read from the `instruction` table, not
  the number of failures. A rate over observed failures cannot fall.
- Every target instruction must be either **named** or **explained**. A target row with no
  `idl_name` and no failure at its coordinates is a silent omission: the decoder neither understood
  it nor recorded that it did not. That is the failure mode this gate exists to make impossible,
  and it is invisible to a check that only walks the failure table.
"""
import argparse
import importlib.util
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load_b9d():
    spec = importlib.util.spec_from_file_location(
        "b9d_transaction_bodies", ROOT / "scripts" / "b9d_transaction_bodies.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B9D = _load_b9d()
FreezeViolation = B9D.FreezeViolation

# Reserve-chain discontinuities are governed by B9e. They are validated here for coordinates and
# attribution, then reported separately and excluded from every B9f ceiling, so a curve break is
# never counted twice against two different gates.
DELEGATED_CATEGORY = B9D.FAILURE_RESERVE_CHAIN
DELEGATED_PREFIX = "reserve chain: "

# The class is READ FROM THE `category` COLUMN, which the decoder writes at the moment it knows it.
# Names come from B9d's own constants so the two cannot drift apart by editing one file.
#
# The prose prefixes below are a CROSS-CHECK, not the classification: a row whose stated category
# disagrees with its own message is refused. Prose alone was the earlier design and it is weaker in
# both directions -- a reworded message silently changes a class, and a message that happens to
# match a prefix is counted as something it is not.
FAILURE_CATEGORIES = (
    (B9D.FAILURE_SHORT_DISCRIMINATOR,
     "target instruction data too short to carry a discriminator"),
    (B9D.FAILURE_UNKNOWN_DISCRIMINATOR, "unknown "),
    (B9D.FAILURE_EVENTLESS_RESERVE, "reserve transition unresolved: eventless PumpSwap"),
    (B9D.FAILURE_BALANCE_UNRESOLVED, "reserve balance reconciliation unresolved:"),
    (B9D.FAILURE_BALANCE_MISMATCH, "reserve balance reconciliation mismatch:"),
)
CATEGORY_NAMES = tuple(name for name, _ in FAILURE_CATEGORIES)

# Ratified in `research/B9F_FAILURE_COVERAGE_PREREGISTRATION.md` §5 BEFORE any full decode pass, and
# frozen from correctness invariants rather than fitted counts: every category is zero. Each one is
# a statement that some part of the instruction stream was not understood or not reconciled, and
# the remedy is repairing the evidence -- pinning the interface that explains a discriminator,
# resolving the quote identity -- not tolerating a quota of them.
RATIFIED_CEILINGS = {name: 0 for name in CATEGORY_NAMES}


def categorise(reason):
    """The one category a reason belongs to, or `None` if it belongs to none.

    Deliberately returns `None` rather than an `other` bucket. An `other` bucket is where an
    unrecognised failure class goes to stop being noticed.
    """
    if reason.startswith(DELEGATED_PREFIX):
        return DELEGATED_CATEGORY
    for name, prefix in FAILURE_CATEGORIES:
        if reason.startswith(prefix):
            return name
    return None


def assert_canonical_failure_coordinates(database):
    """Every failure must sit at a real, canonical, parent-bearing coordinate.

    A failure that cannot be located is not evidence of anything: it can be neither reviewed nor
    excluded from a measurement. `inner_index` is -1 for an outer instruction, so it is the one
    coordinate allowed to be negative.
    """
    malformed = database.execute(
        "SELECT count(*) FROM classification_failure "
        "WHERE slot IS NULL OR transaction_index IS NULL OR outer_index IS NULL "
        "OR inner_index IS NULL OR signature IS NULL OR signature = '' "
        "OR slot < 0 OR transaction_index < 0 OR outer_index < 0 OR inner_index < -1").fetchone()[0]
    if malformed:
        raise FreezeViolation(
            f"{malformed:,} classification failure(s) carry no valid canonical coordinate; an "
            "unlocatable failure can be neither reviewed nor excluded")
    orphans = database.execute(
        "SELECT count(*) FROM classification_failure f LEFT JOIN instruction i "
        "ON i.slot=f.slot AND i.transaction_index=f.transaction_index "
        "AND i.outer_index=f.outer_index AND i.inner_index=f.inner_index "
        "WHERE i.slot IS NULL OR i.signature != f.signature").fetchone()[0]
    if orphans:
        raise FreezeViolation(
            f"{orphans:,} classification failure(s) have no parent instruction at their "
            "coordinates; the failure is not attributable to decoded evidence")
    return True


def assert_no_silent_target_instruction(database):
    """Every target instruction is either named or explained.

    This is the whole reason the denominator is the instruction population. A target row with no
    `idl_name` and no failure at its coordinates was neither understood nor reported, and walking
    the failure table can never reveal it -- there is nothing there to walk.
    """
    silent = database.execute(
        "SELECT count(*) FROM instruction i WHERE i.target = 1 AND i.idl_name IS NULL "
        "AND NOT EXISTS (SELECT 1 FROM classification_failure f "
        "WHERE f.slot=i.slot AND f.transaction_index=i.transaction_index "
        "AND f.outer_index=i.outer_index AND f.inner_index=i.inner_index)").fetchone()[0]
    if silent:
        raise FreezeViolation(
            f"{silent:,} target instruction(s) are neither named nor explained by a recorded "
            "failure; the decoder did not understand them and did not say so")
    return True


def failure_coverage(database):
    """Categorise every persisted failure against the frozen target-instruction denominator."""
    assert_canonical_failure_coordinates(database)
    assert_no_silent_target_instruction(database)

    target_instructions = database.execute(
        "SELECT count(*) FROM instruction WHERE target = 1").fetchone()[0]
    if not target_instructions:
        raise FreezeViolation(
            "no target instructions are present; a failure-coverage rate over an empty population "
            "is vacuous rather than clean")

    if "category" not in {row[1] for row in database.execute(
            "PRAGMA table_info(classification_failure)")}:
        raise FreezeViolation(
            "classification_failure has no `category` column: this artifact predates machine-"
            "readable failure classes. Run `migrate_failure_categories` and re-decode; the "
            "categories are deliberately not reconstructed from prose after the fact")

    counts = {name: 0 for name in CATEGORY_NAMES}
    counts[DELEGATED_CATEGORY] = 0
    legacy = unrecognised = 0
    disagreements = []
    for category, reason, total in database.execute(
            "SELECT category,reason,count(*) FROM classification_failure "
            "GROUP BY category,reason ORDER BY category,reason"):
        if category is None:
            legacy += total
            continue
        if category not in counts:
            unrecognised += total
            continue
        # The decoder stated the class; the message must agree with it. Disagreement means one of
        # the two was edited without the other, and there is no way to tell which is right.
        if categorise(reason or "") != category:
            disagreements.append((category, reason, total))
            continue
        counts[category] += total

    if legacy:
        raise FreezeViolation(
            f"{legacy:,} classification failure(s) carry no category; they were written before the "
            "column existed. Re-decode rather than backfilling: a class inferred from prose after "
            "the fact is a guess wearing a fact's column name")
    if unrecognised:
        raise FreezeViolation(
            f"{unrecognised:,} classification failure(s) declare a category outside "
            f"{sorted(counts)}. An uncategorised failure class is exactly what this gate refuses; "
            "there is no `other` bucket by design")
    if disagreements:
        category, reason, total = disagreements[0]
        raise FreezeViolation(
            f"{len(disagreements):,} failure class(es) disagree with their own message; first "
            f"category {category!r} on reason {reason!r} x{total:,}, which reads as "
            f"{categorise(reason or '')!r}")

    persisted = database.execute("SELECT count(*) FROM classification_failure").fetchone()[0]
    # Bidirectional reconciliation, the other direction from `assert_no_silent_target_instruction`:
    # the decoder's own tally must agree with what is on disk. A pass that recorded a count and
    # then wrote a different number of rows has lost failures somewhere between the two.
    recorded = database.execute(
        "SELECT value FROM metadata WHERE key='decoder_classification_failures'").fetchone()
    if recorded is None:
        raise FreezeViolation(
            "decoder_classification_failures metadata is absent; the failure population cannot be "
            "reconciled against the pass that produced it")
    if recorded[0] != str(persisted):
        raise FreezeViolation(
            f"decoder recorded {recorded[0]} classification failures, {persisted:,} are persisted")
    # Structural invariant rather than a live check: every grouped reason either increments a
    # category or lands in `unrecognised`, which raises above. Kept so that stops being true
    # loudly. The reachable guard is the refusal directly above it.
    if sum(counts.values()) != persisted:
        raise FreezeViolation(
            f"categories account for {sum(counts.values()):,} failures, {persisted:,} are "
            "persisted")
    return {
        "target_instructions": target_instructions,
        "counts": {name: counts[name] for name in CATEGORY_NAMES},
        "delegated_to_b9e": counts[DELEGATED_CATEGORY],
        "rates": {name: counts[name] / target_instructions for name in CATEGORY_NAMES},
    }


def assert_failure_coverage(database, ceilings=None):
    """Fail closed unless every category is within its RATIFIED ceiling.

    `ceilings` maps every declared category to a maximum absolute count. It has no default, and a
    partial mapping is refused rather than treated as unbounded for the missing categories: a
    category silently exempted from its own gate is the failure this is meant to prevent.
    """
    if ceilings is None:
        raise FreezeViolation(
            "B9f category ceilings are not ratified: set them in "
            "research/B9F_FAILURE_COVERAGE_PREREGISTRATION.md §5 before any measurement consumes "
            "this instruction stream")
    # Checked before the generic name check below, which would otherwise report this as merely an
    # unrecognised key. Someone writing a reserve_chain ceiling has a specific wrong idea, and
    # deserves the specific answer.
    if DELEGATED_CATEGORY in ceilings:
        raise FreezeViolation(
            f"{DELEGATED_CATEGORY} is governed by B9e and must not be given a B9f ceiling; "
            "counting a curve break against two gates makes neither of them mean anything")
    missing = sorted(set(CATEGORY_NAMES) - set(ceilings))
    unknown = sorted(set(ceilings) - set(CATEGORY_NAMES))
    if missing or unknown:
        raise FreezeViolation(
            f"ceilings must name exactly the declared categories; missing {missing}, unknown "
            f"{unknown}")

    coverage = failure_coverage(database)
    exceeded = sorted(
        (name, coverage["counts"][name], ceilings[name])
        for name in CATEGORY_NAMES if coverage["counts"][name] > ceilings[name])
    if exceeded:
        rendered = "; ".join(f"{name}={count:,} exceeds {limit:,}"
                             for name, count, limit in exceeded)
        raise FreezeViolation(f"classification-failure coverage exceeds preregistered ceilings: "
                              f"{rendered}")
    coverage["ceilings"] = dict(ceilings)
    return coverage


def assert_publication_gate(database):
    """The ratified §5 gate, applied with no caller-supplied ceilings.

    `assert_failure_coverage` stays parameterised so the gate can be exercised at other settings in
    tests. Publication must not route through numbers chosen at a call site.
    """
    return assert_failure_coverage(database, dict(RATIFIED_CEILINGS))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("artifact", help="path to the B9d evidence artifact (opened read-only)")
    parser.add_argument("--ceilings", default=None,
                        help='ceilings as JSON, e.g. \'{"unknown_discriminator": 0}\'')
    parser.add_argument("--publication-gate", action="store_true",
                        help="apply the ratified §5 ceilings; overrides --ceilings")
    args = parser.parse_args(argv)

    database = B9D.connect(args.artifact, readonly=True)
    try:
        if args.publication_gate:
            report = assert_publication_gate(database)
        elif args.ceilings is None:
            report = failure_coverage(database)
        else:
            report = assert_failure_coverage(database, json.loads(args.ceilings))
    finally:
        database.close()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except FreezeViolation as error:
        print(f"FreezeViolation: {error}", file=sys.stderr)
        sys.exit(2)
