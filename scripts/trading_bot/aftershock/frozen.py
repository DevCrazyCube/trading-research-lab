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

INSTRUMENTS = {"AFTERSHOCK": "AFTERSHOCK"}
ACTIVE_INSTRUMENTS = ("AFTERSHOCK",)

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
