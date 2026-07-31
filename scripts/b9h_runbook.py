#!/usr/bin/env python3
"""The frozen post-collection runbook, as executable data rather than prose in a document.

A runbook that lives only in a handoff is a runbook whose steps can be silently reordered, and the
order is the substance here: every step exists to make a specific later step recoverable. Backing up
after the boundary write means a failed boundary fetch has no clean state to return to; decoding
before readiness means decoding a partial artifact and `refuse_if_complete` then makes it permanent.

So the sequence is a tuple, the rehearsal executes it and records what it actually ran, and the test
compares the trace to the tuple. Swapping or dropping a step changes the trace and fails.

Two steps cannot be rehearsed offline and are marked as such: the collector's natural exit and the
boundary fetch, which is the only remaining network call. Everything else runs for real against a
synthetic artifact, including both backups, byte-for-byte restoration, the atomic decode, and both
publication gates.
"""
import argparse
import hashlib
import importlib.util
import json
import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B9D = _load("b9d_transaction_bodies", "b9d_transaction_bodies.py")
FreezeViolation = B9D.FreezeViolation

# The frozen order. `offline` marks the steps a rehearsal can execute; the other two are the
# collector's own exit and the single remaining network call.
RUNBOOK = (
    {"step": 1, "name": "collector_exits_naturally", "offline": False,
     "detail": "wait for the body collector to exit on its own; never stop it early"},
    {"step": 2, "name": "seal_collection", "offline": True,
     "detail": "mark_collection_complete under the free single-writer lock, after exact "
               "body/coordinate verification"},
    {"step": 3, "name": "backup_raw_bodies", "offline": True,
     "detail": "recoverable raw-body backup, taken BEFORE the remaining boundary write"},
    {"step": 4, "name": "collect_boundary", "offline": False,
     "detail": "collect-boundary under the free single-writer lock; the only network step"},
    # Inserted after a real decode reached its first missing-column write and rolled back. The
    # migration MUST precede the canonical backup below, or the backup preserves a schema the
    # decode cannot use -- restoring it would reproduce the same failure.
    {"step": 5, "name": "migrate_failure_categories", "offline": True,
     "detail": "add classification_failure.category under the free lock; never backfills"},
    {"step": 6, "name": "verify_and_readiness", "offline": True,
     "detail": "raw verification plus the fail-closed B9g readiness gate, which refuses a "
               "pre-migration schema"},
    {"step": 7, "name": "backup_sealed_raw_and_boundary", "offline": True,
     "detail": "second canonical backup, hashed, of the MIGRATED artifact; the only state a "
               "failed decode may restore from"},
    {"step": 8, "name": "atomic_decode", "offline": True,
     "detail": "one transaction; any error rolls the whole pass back"},
    {"step": 9, "name": "verify_decoded", "offline": True,
     "detail": "verify_decoded_artifact over the derived rows"},
    {"step": 10, "name": "b9f_gate", "offline": True,
     "detail": "measure classification-failure coverage, then apply the ratified zero ceilings"},
    {"step": 11, "name": "b9e_gate", "offline": True,
     "detail": "measure cohort reserve coverage, then apply the ratified 100% threshold"},
)
STEP_NAMES = tuple(entry["name"] for entry in RUNBOOK)
OFFLINE_STEPS = tuple(entry["name"] for entry in RUNBOOK if entry["offline"])


def digest(path):
    """SHA-256 of a file, streamed. A backup nobody hashed is a backup nobody can trust."""
    hasher = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def backup_artifact(source, destination):
    """Copy an artifact and return the digest of the copy, verified against the source.

    Refuses to overwrite. A backup step that silently replaces the previous backup destroys the
    earlier recovery point, which is the one you need when the later state is the broken one.
    """
    source, destination = pathlib.Path(source), pathlib.Path(destination)
    if destination.exists():
        raise FreezeViolation(
            f"backup destination {destination} already exists; refusing to overwrite an earlier "
            "recovery point")
    shutil.copy2(source, destination)
    source_digest, copy_digest = digest(source), digest(destination)
    if source_digest != copy_digest:
        raise FreezeViolation(
            f"backup {destination} hashes {copy_digest}, source hashes {source_digest}")
    return copy_digest


def restore_artifact(backup, target, expected_digest=None):
    """Restore byte-for-byte, verifying the backup still hashes to what it did when taken."""
    backup, target = pathlib.Path(backup), pathlib.Path(target)
    actual = digest(backup)
    if expected_digest is not None and actual != expected_digest:
        raise FreezeViolation(
            f"backup {backup} hashes {actual}, expected {expected_digest}; it is not the state it "
            "was when taken and must not be restored")
    shutil.copy2(backup, target)
    restored = digest(target)
    if restored != actual:
        raise FreezeViolation(f"restored {target} hashes {restored}, backup hashes {actual}")
    return restored


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true", help="emit the runbook as JSON")
    args = parser.parse_args(argv)
    if args.json:
        print(json.dumps(RUNBOOK, indent=2))
        return 0
    for entry in RUNBOOK:
        marker = " " if entry["offline"] else "*"
        print(f"{entry['step']:>2}.{marker} {entry['name']}\n      {entry['detail']}")
    print("\n* not rehearsable offline: the collector's own exit, and the single network call.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
