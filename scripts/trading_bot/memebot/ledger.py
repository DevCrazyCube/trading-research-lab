#!/usr/bin/env python3
"""State + two append-only logs -- the lookahead-proof record. Mirror of newsdesk/basket discipline.

  * MEMEBOT_PREREGISTRATION_LOG.jsonl -- every frozen paper entry (and abstention), written the MOMENT
    it is decided, BEFORE any outcome is known.
  * MEMEBOT_RESOLUTION_LOG.jsonl      -- every mark-to-market resolution, written when a position hits
    its stop / target / horizon.

The state file is a convenience index of resolved hashes; the two logs are the source of truth and are
never truncated or rewritten (ITERATION_PROTOCOL).
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib

from . import Refused
from .frozen import SCHEMA_VERSION, canonical_sha256

# Every ledger op is keyed to ONE frozen instrument's on-disk paths (spec["_paths"]), so the two
# parallel variants (MEMEBOT1 / MEMEBOT_FAST) never share a file -- ITERATION_PROTOCOL §4b.


def _append(path: pathlib.Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as fh:
        fh.write(json.dumps(record, sort_keys=True, default=str) + "\n")


def _read(path: pathlib.Path) -> list:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def append_entry(spec: dict, record: dict) -> None:
    _append(spec["_paths"]["prereg_log"], record)


def append_resolution(spec: dict, record: dict) -> None:
    _append(spec["_paths"]["resolution_log"], record)


def read_entries(spec: dict) -> list:
    return _read(spec["_paths"]["prereg_log"])


def read_resolutions(spec: dict) -> list:
    return _read(spec["_paths"]["resolution_log"])


def verify_entry_hashes(records: list) -> None:
    """Re-verify every frozen entry's sha256 -- a tampered forward commitment refuses the whole run."""
    for rec in records:
        if rec.get("kind") != "entry":
            continue
        want = rec.get("setup_sha256")
        got = canonical_sha256(rec)
        if want != got:
            raise Refused(f"pre-registration tampering: entry frozen at {rec.get('decided_utc')} has "
                          f"sha256 {want} on disk but recomputes to {got}. A forward commitment whose "
                          "spec was edited after freeze is not evidence. Restore the log.")


def blank_state(spec: dict) -> dict:
    return {"schema_version": SCHEMA_VERSION, "instrument_id": spec["instrument_id"],
            "freeze": {"utc": spec["frozen_utc"],
                       "preregistration_sha256": spec["preregistration_sha256"]},
            "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "resolved_setup_hashes": [],
            "seen_pool_addresses": []}


def load_state(spec: dict) -> dict:
    state_path = spec["_paths"]["state"]
    if not state_path.exists():
        return blank_state(spec)
    state = json.loads(state_path.read_text())
    if state.get("schema_version") != SCHEMA_VERSION:
        raise Refused(f"state is schema {state.get('schema_version')}, this bot writes {SCHEMA_VERSION}")
    if state.get("freeze", {}).get("preregistration_sha256") != spec["preregistration_sha256"]:
        raise Refused("the state file was written under a different freeze hash. A forward test whose "
                      "freeze changed mid-flight is two half-tests; start a new instrument.")
    state.setdefault("seen_pool_addresses", [])
    return state


def save_state(spec: dict, state: dict) -> None:
    state_path = spec["_paths"]["state"]
    state_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = state_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True))
    tmp.replace(state_path)


def open_positions(spec: dict) -> list:
    """Frozen entries with no RESOLVED resolution yet."""
    entries = [r for r in read_entries(spec) if r.get("kind") == "entry"]
    resolved = {r["setup_sha256"] for r in read_resolutions(spec) if r.get("status") == "RESOLVED"}
    return [e for e in entries if e["setup_sha256"] not in resolved]


def resolved_r_stream(spec: dict) -> list:
    """The realised-R stream (PASS and control), de-duplicated by setup hash, oldest first."""
    out, seen = [], set()
    for r in read_resolutions(spec):
        if r.get("status") != "RESOLVED" or r["setup_sha256"] in seen:
            continue
        if r.get("realized_r") is None:
            continue
        seen.add(r["setup_sha256"])
        out.append(r)
    out.sort(key=lambda r: r.get("resolved_utc", ""))
    return out
