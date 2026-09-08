#!/usr/bin/env python3
"""State + the two append-only logs -- mirror of the Newsdesk's ledger discipline.

Two append-only JSONL logs, never rewritten:
  * PREDMARKET_PREREGISTRATION_LOG.jsonl -- every frozen probability estimate and every "no trade"
    abstention, written the MOMENT it is proposed, BEFORE the market resolves. The lookahead-proof record.
  * PREDMARKET_RESOLUTION_LOG.jsonl      -- every settlement, written when a market officially resolves.

The state file caches which estimates are still OPEN and the running resolved stream. It is a
convenience index; the two logs are the source of truth and are never truncated.
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib

from . import Refused
from .frozen import (PREREG_LOG_PATH, RESOLUTION_LOG_PATH, STATE_PATH, SCHEMA_VERSION,
                     canonical_sha256)


def _append(path: pathlib.Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as fh:
        fh.write(json.dumps(record, sort_keys=True, default=str) + "\n")


def _read(path: pathlib.Path) -> list:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def append_preregistration(record: dict) -> None:
    _append(PREREG_LOG_PATH, record)


def append_resolution(record: dict) -> None:
    _append(RESOLUTION_LOG_PATH, record)


def read_preregistrations() -> list:
    return _read(PREREG_LOG_PATH)


def read_resolutions() -> list:
    return _read(RESOLUTION_LOG_PATH)


def verify_preregistration_hashes(records: list) -> None:
    """Re-verify every frozen estimate's sha256 -- a tampered forward commitment refuses the whole run."""
    for rec in records:
        if rec.get("kind") != "estimate":
            continue
        want = rec.get("estimate_sha256")
        got = canonical_sha256(rec)
        if want != got:
            raise Refused(f"pre-registration tampering: estimate frozen at {rec.get('proposed_utc')} has "
                          f"sha256 {want} on disk but recomputes to {got}. A forward commitment whose "
                          "spec was edited after freeze is not evidence. Restore the log.")


def blank_state(spec: dict) -> dict:
    return {"schema_version": SCHEMA_VERSION, "instrument_id": spec["instrument_id"],
            "freeze": {"utc": spec["frozen_utc"],
                       "preregistration_sha256": spec["preregistration_sha256"]},
            "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "resolved_estimate_hashes": []}


def load_state(spec: dict) -> dict:
    if not STATE_PATH.exists():
        return blank_state(spec)
    state = json.loads(STATE_PATH.read_text())
    if state.get("schema_version") != SCHEMA_VERSION:
        raise Refused(f"state is schema {state.get('schema_version')}, this tracker writes {SCHEMA_VERSION}")
    if state.get("freeze", {}).get("preregistration_sha256") != spec["preregistration_sha256"]:
        raise Refused("the state file was written under a different freeze hash. A forward test whose "
                      "freeze changed mid-flight is two half-tests; start a new instrument.")
    return state


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True))
    tmp.replace(STATE_PATH)


def open_estimates() -> list:
    """Frozen estimates from the pre-registration log that have no RESOLVED resolution yet."""
    estimates = [r for r in read_preregistrations() if r.get("kind") == "estimate"]
    resolved = {r["estimate_sha256"] for r in read_resolutions() if r.get("status") == "RESOLVED"}
    return [s for s in estimates if s["estimate_sha256"] not in resolved]


def dedupe_keep_first(rows: list) -> list:
    """KEEP-FIRST by (venue, market_id): the EARLIEST-frozen estimate is the one that counts (T43).

    Duplicate freezes of one market (on file: 567621/703257/997488) would otherwise let a single
    world outcome enter the Brier stream several times, inflating n. Pure function; selftested."""
    best: dict = {}
    for r in sorted(rows, key=lambda r: (r.get("proposed_utc") or "", r.get("resolved_utc") or "")):
        best.setdefault((r.get("venue"), r.get("market_id")), r)
    return list(best.values())


def resolved_stream() -> list:
    """Resolved estimates, de-duplicated by hash then keep-first by market, oldest first
    (the Brier/P&L stream)."""
    out, seen = [], set()
    for r in read_resolutions():
        if r.get("status") != "RESOLVED" or r["estimate_sha256"] in seen:
            continue
        if r.get("brier_agent") is None:
            continue
        seen.add(r["estimate_sha256"])
        out.append(r)
    out = dedupe_keep_first(out)
    out.sort(key=lambda r: r.get("resolved_utc", ""))
    return out
