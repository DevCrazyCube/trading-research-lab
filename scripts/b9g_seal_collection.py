#!/usr/bin/env python3
"""Seal a finished B9d raw collection: verify the frozen population, then mark it complete.

This exists because the running collector predates the completion marker. It cannot write one, and
the two alternatives are both worse than a separate command: restarting the collector would abandon
a resumable run for a cosmetic reason, and pretending the marker existed would defeat the only
thing it is for.

The seal is the one deliberate write in the pre-decode sequence, and it is the narrowest possible
one — a single metadata row. It is taken **under the collector's own single-writer lock**, so it
cannot run while a collector is alive: acquiring that lock IS the proof that body collection has
exited. It runs after the natural exit, never to force one.

`mark_collection_complete` verifies the exact coordinate and body population before writing, so a
seal on a partial artifact fails and writes nothing. The marker is immutable, so re-running is a
no-op that reports the original value rather than re-stamping a later, possibly partial, state.
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


def seal_collection(artifact_path, now=None):
    """Verify and seal. Raises if a collector holds the lock or the population is incomplete."""
    # Acquiring the collector's own lock is the proof no collector is running. It is non-blocking
    # inside `collector_lock`, so this refuses rather than queueing behind a live writer.
    with B9D.collector_lock(artifact_path):
        database = B9D.connect(artifact_path)
        try:
            already = database.execute(
                "SELECT value FROM metadata WHERE key=?",
                (B9D.COLLECTION_COMPLETE_KEY,)).fetchone()
            with database:
                marker = B9D.mark_collection_complete(database, now=now)
        finally:
            database.close()
    return {"artifact": str(artifact_path), "sealed_at_unix": marker,
            "already_sealed": already is not None}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("artifact", help="path to the finished B9d evidence artifact")
    args = parser.parse_args(argv)
    print(json.dumps(seal_collection(args.artifact), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except FreezeViolation as error:
        print(f"NOT SEALED: {error}", file=sys.stderr)
        sys.exit(2)
