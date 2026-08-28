#!/usr/bin/env python3
"""Load and VERIFY the frozen AFTERSHOCK spec — refusing if the pre-registration has moved.

Mirrors memebot.frozen exactly: the loader recomputes the sha256 of the pre-registration markdown and
refuses if it no longer matches the hash pinned in the frozen JSON. A rule editable after the outcome
prints is not frozen. An improvement is a NEW frozen instrument, never an edit to a running one.

AFTERSHOCK keeps its OWN registry, deliberately NOT in memebot.frozen.INSTRUMENTS, so the memebot
periodic scanner never snapshot-screens it — AFTERSHOCK's entry is event-driven off the trade tape.
It reuses memebot.frozen.canonical_sha256 for the entry-record fingerprint so entries are hashed with
the same primitive (and the same exclusions) as the memebot books.
"""
from __future__ import annotations

import hashlib
import json
import pathlib

from . import Refused
from scripts.trading_bot.memebot.frozen import canonical_sha256  # noqa: F401  (re-exported for entry.py)

ROOT = pathlib.Path(__file__).resolve().parents[3]
RESEARCH = ROOT / "research" / "trading_bot" / "aftershock"

INSTRUMENTS = {"AFTERSHOCK": "AFTERSHOCK", "AFTERSHOCK_V2": "AFTERSHOCK_V2",
               "AFTERSHOCK_V3": "AFTERSHOCK_V3", "AFTERSHOCK_V4": "AFTERSHOCK_V4",
               "AFTERSHOCK_V5": "AFTERSHOCK_V5", "AFTERSHOCK_PAC_V1": "AFTERSHOCK_PAC_V1"}
# V2/V3 are FROZEN (loadable + hash-verified) and run via their OWN detached loops (scan_v2 / scan_v3)
# writing per-arm ledgers; ACTIVE_INSTRUMENTS is only the periodic-scan registry (V1). Kept minimal so
# active_specs() never tries to run an arm-family through the single-instrument path.  Legacy V1 is
# retired operationally; PAC stays inactive until its seal/activation anchors and calibration gate exist.
ACTIVE_INSTRUMENTS = ()

SCHEMA_VERSION = 1


def paths_for(prefix: str) -> dict:
    return {
        "frozen_json": RESEARCH / f"{prefix}_FROZEN.json",
        "prereg_md": RESEARCH / f"{prefix}_PREREGISTRATION.md",
        "prereg_log": RESEARCH / f"{prefix}_PREREGISTRATION_LOG.jsonl",
        "resolution_log": RESEARCH / f"{prefix}_RESOLUTION_LOG.jsonl",
        "state": RESEARCH / f"{prefix}_STATE.json",
    }


def _sha256_file(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def freeze_epoch(spec: dict) -> float:
    """The freeze instant as epoch seconds. NO shock whose event time (t_shock) predates this may be
    entered — a pre-freeze shock is a LOOKAHEAD, not a forward trade (Codex audit 2026-08-27: 31% of the
    'forward' V3 entries, incl. the two biggest winners, had shocks before the freeze).

    FAIL-CLOSED (handoff 422 defect 2): a missing/malformed/naive `frozen_utc` REFUSES — never a silent
    0.0 (which would admit everything) and never a naive string interpreted in local Amsterdam time. Only
    an explicit-offset ISO-8601 instant is accepted (its offset is honoured; the returned epoch is UTC)."""
    import datetime as _dt
    raw = spec.get("frozen_utc")
    if not isinstance(raw, str) or not raw.strip():
        raise Refused("frozen_utc missing/empty — refusing (fail-closed)")
    try:
        parsed = _dt.datetime.fromisoformat(raw)
    except (ValueError, TypeError) as exc:
        raise Refused(f"frozen_utc {raw!r} is malformed: {exc}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise Refused(f"frozen_utc {raw!r} is naive (no timezone) — refusing; must carry an explicit UTC offset")
    return parsed.timestamp()


def frozen_spec(instrument: str = "AFTERSHOCK") -> dict:
    prefix = INSTRUMENTS.get(instrument)
    if prefix is None:
        raise Refused(f"unknown instrument {instrument!r}; known: {sorted(INSTRUMENTS)}")
    paths = paths_for(prefix)
    for path in (paths["frozen_json"], paths["prereg_md"]):
        if not path.exists():
            raise Refused(f"{path} is missing; the frozen {instrument} cannot be loaded")
    spec = json.loads(paths["frozen_json"].read_text())
    if spec.get("instrument_id") != instrument:
        raise Refused(f"{paths['frozen_json'].name} declares instrument_id "
                      f"{spec.get('instrument_id')!r} but was loaded as {instrument!r}")
    expected = spec.get("preregistration_sha256")
    if not expected:
        raise Refused(f"{paths['frozen_json'].name} carries no preregistration_sha256")
    actual = _sha256_file(paths["prereg_md"])
    if actual != expected:
        raise Refused(
            f"{paths['prereg_md'].name} changed since the freeze.\n"
            f"  frozen expects: {expected}\n  on disk:        {actual}\n"
            "Restore the document. Do NOT update the hash: an improvement is a NEW frozen instrument, "
            "never an edit to a running one.")
    spec["_preregistration_sha256_verified"] = actual
    spec["_frozen_json_sha256"] = _sha256_file(paths["frozen_json"])
    spec["_paths"] = paths
    return spec


def active_specs() -> list:
    return [frozen_spec(i) for i in ACTIVE_INSTRUMENTS]
