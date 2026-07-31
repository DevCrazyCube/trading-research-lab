#!/usr/bin/env python3
"""B9g decode-readiness gate: one fail-closed offline command, run immediately before decoding.

B9e bounds the reserve population and B9f bounds the instruction population. Both run **after** a
decode pass and both take the artifact as given. This runs **before** one, and asks the question
neither can: is this artifact finished being written?

That question is not answered by the row counts alone. The collector is resumable, so it exits for
many reasons and most of them are not completion. An artifact caught mid-run has a self-consistent
prefix of the frozen population — every gate that compares rows to other rows passes, and the
counts are exactly what a resumed collector is in the business of changing. Decoding it would
produce a derived stream over a partial evidence set, and `refuse_if_complete` then makes the
mistake permanent.

So readiness is established from four independent directions:

- **Nobody is writing.** The single-writer lock must be unheld.
- **Somebody finished.** An immutable marker, written only after the population assertions passed,
  must be present. "The collector stopped" and "the collector completed" are different claims.
- **The evidence is exactly the frozen set**, its bytes hash to what was recorded, and the §4
  boundary evidence and version coverage are present.
- **Nothing has been decoded yet.** A partially materialised derived stream means a previous pass
  ran and did not finish, and mixing two passes is refused rather than resumed.

On fetch order, correcting an earlier draft of this gate: boundary evidence is deliberately
collected AFTER the bodies, to preserve the single-writer invariant. It need only complete before
decode. Finalized current ProgramData evidence whose latest deploy slot precedes the observation
start proves no in-range upgrade regardless of when it was fetched, so this gate checks boundary
*completeness*, never boundary *ordering*.

This command never takes the lock from a live collector: it probes non-blockingly and refuses.
"""
import argparse
import fcntl
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

# Tables a decode pass materialises. Any row in any of them means a pass already ran.
DERIVED_TABLES = ("instruction", "reserve_observation", "classification_failure")
DERIVED_METADATA = ("decoded_at_unix", "decoder_classification_failures",
                    "reserve_reconciliation_failures")


def assert_collector_lock_unheld(artifact_path):
    """Refuse while a collector holds the single-writer lock. Never steals it.

    The probe is non-blocking: if the lock is held the call fails immediately rather than queueing
    behind a live collector and eventually acquiring it. A readiness check that can take the lock
    is a readiness check that can stop the thing it is inspecting.

    A missing lock file is not evidence of readiness and is not treated as such — it simply cannot
    be held. The population checks below are what establish that collection actually happened.
    """
    lock_path = pathlib.Path(f"{artifact_path}.collector.lock")
    if not lock_path.exists():
        return False
    with lock_path.open("a+b") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise FreezeViolation(
                f"a collector currently holds the single-writer lock {lock_path}; the artifact is "
                "still being written and must not be decoded") from error
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    return True


def assert_collection_complete(database):
    """The immutable completion marker must be present.

    Row counts alone cannot distinguish a finished collector from a resumable one that stopped at
    exactly the right moment, because the counts are what resuming changes. The marker is written
    by `mark_collection_complete` only after the population assertions pass, so its presence is a
    statement that they did.
    """
    marker = database.execute(
        "SELECT value FROM metadata WHERE key=?", (B9D.COLLECTION_COMPLETE_KEY,)).fetchone()
    if not marker:
        raise FreezeViolation(
            f"{B9D.COLLECTION_COMPLETE_KEY} is absent: no verified-complete collection has been "
            "recorded. Run `mark_collection_complete` against a finished artifact; it writes the "
            "marker only if the frozen population verifies")
    return marker[0]


def assert_nothing_decoded_yet(database):
    """A partially materialised derived stream means a previous pass ran and did not finish."""
    populated = {}
    for table in DERIVED_TABLES:
        count = database.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        if count:
            populated[table] = count
    present = [row[0] for row in database.execute(
        "SELECT key FROM metadata WHERE key IN (%s)" % ",".join("?" * len(DERIVED_METADATA)),
        DERIVED_METADATA)]
    if populated or present:
        raise FreezeViolation(
            f"derived decoder output already exists (rows={populated}, metadata={sorted(present)}); "
            "a second pass would mix or overwrite it. Restore the pre-decode artifact rather than "
            "resuming")
    return True


def assert_decode_ready(database, artifact_path, b9c_path=None, b9a_path=None):
    """Every readiness condition, in one fail-closed pass. Raises on the first failure."""
    lock_present = assert_collector_lock_unheld(artifact_path)
    marker = assert_collection_complete(database)
    assert_nothing_decoded_yet(database)
    # The heavy structural verification last: it is the slowest, and the three checks above are
    # what distinguish "not ready yet" from "broken", which is a more useful thing to be told first.
    summary = B9D.verify_artifact(
        database,
        **({"b9c_path": b9c_path} if b9c_path else {}),
        **({"b9a_path": b9a_path} if b9a_path else {}))
    return {
        "ready": True,
        "collection_completed_at_unix": marker,
        "collector_lock_file_present": lock_present,
        "verification": summary,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("artifact", help="path to the B9d evidence artifact (opened read-only)")
    parser.add_argument("--b9c", default=None, help="override the pinned B9c source path")
    parser.add_argument("--b9a", default=None, help="override the pinned B9a source path")
    args = parser.parse_args(argv)

    database = B9D.connect(args.artifact, readonly=True)
    try:
        report = assert_decode_ready(database, args.artifact, args.b9c, args.b9a)
    finally:
        database.close()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except FreezeViolation as error:
        print(f"NOT READY: {error}", file=sys.stderr)
        sys.exit(2)
