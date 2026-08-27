#!/usr/bin/env python3
"""Load and VERIFY the frozen Newsdesk spec -- refusing if the pre-registration has moved.

Mirrors `basket_forward.frozen_spec`: the rules the logger runs forward must be the rules frozen
before the first forward observation, so the loader recomputes the sha256 of the pre-registration
markdown and refuses if it no longer matches the hash pinned in the frozen JSON. A rule that can be
edited after the data prints is not frozen, and a forward test of an unfrozen rule measures nothing.
"""

from __future__ import annotations

import hashlib
import json
import pathlib

from . import Refused

ROOT = pathlib.Path(__file__).resolve().parents[3]
RESEARCH = ROOT / "research" / "trading_bot" / "newsdesk"
CACHE = ROOT / "research" / "data" / "newsdesk_cache"

FROZEN_PATH = RESEARCH / "NEWSDESK_FROZEN.json"
PREREG_PATH = RESEARCH / "NEWSDESK_PREREGISTRATION.md"
PREREG_LOG_PATH = RESEARCH / "NEWSDESK_PREREGISTRATION_LOG.jsonl"  # append-only, frozen at proposal
RESOLUTION_LOG_PATH = RESEARCH / "NEWSDESK_RESOLUTION_LOG.jsonl"   # append-only, mark-to-market
STATE_PATH = RESEARCH / "NEWSDESK_STATE.json"

SCHEMA_VERSION = 1

FRAMING = (
    "NEWSDESK -- agent-driven read-the-world FORWARD PAPER LOGGER (a sibling of BASKET1). It places "
    "NO orders, holds NO position, touches NO account or real money, and reads only free keyless "
    "public data. An agent reads TODAY's news and COMMITS a falsifiable 2:1-asymmetric trade "
    "(sha256+UTC) BEFORE the move; realised R-multiples are the only evidence. This is lookahead-proof "
    "by construction. The honest prior: public news is priced into liquid instruments within seconds, "
    "so the expectancy is ~0 and could be negative. The log is not yet evidence of anything."
)


def _sha256_file(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def frozen_spec() -> dict:
    """Load the frozen spec, refusing if the pre-registration markdown moved since the freeze."""
    for path in (FROZEN_PATH, PREREG_PATH):
        if not path.exists():
            raise Refused(f"{path} is missing; the frozen Newsdesk cannot be loaded")
    spec = json.loads(FROZEN_PATH.read_text())
    expected = spec.get("preregistration_sha256")
    if not expected:
        raise Refused("NEWSDESK_FROZEN.json carries no preregistration_sha256")
    actual = _sha256_file(PREREG_PATH)
    if actual != expected:
        raise Refused(
            "NEWSDESK_PREREGISTRATION.md changed since the freeze.\n"
            f"  frozen expects: {expected}\n  on disk:        {actual}\n"
            "Restore the document. Do NOT update the hash: the point of the hash is that the rules "
            "this logger runs forward are the rules frozen before the first forward observation. An "
            "improvement is a NEW frozen instrument, never an edit to a running one.")
    spec["_preregistration_sha256_verified"] = actual
    spec["_frozen_json_sha256"] = _sha256_file(FROZEN_PATH)
    return spec


# Envelope fields that are NOT part of the frozen spec fingerprint: the hash itself, and the
# storage-envelope fields the ledger stamps on AFTER the freeze (kind/status). Excluding them means
# the freeze fingerprint covers exactly the falsifiable commitment -- instrument, direction, entry
# reference, stop, target, horizon, thesis, confidence, triggering event ids, sizing, proposed_utc --
# and recomputes byte-for-byte from the stored record however it is later wrapped.
_HASH_EXCLUDE = ("setup_sha256", "_verified", "kind", "status")


def canonical_sha256(obj: dict) -> str:
    """Canonical SHA-256 of a setup's frozen spec (sorted keys, compact separators).

    This is the freeze fingerprint of a single setup -- the thing that makes a forward commitment
    tamper-evident. Envelope fields (`_HASH_EXCLUDE`) are removed so the fingerprint is stable across
    the freeze and every later re-verification, regardless of the storage wrapper.
    """
    body = {k: v for k, v in obj.items() if k not in _HASH_EXCLUDE}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
