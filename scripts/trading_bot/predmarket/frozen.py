#!/usr/bin/env python3
"""Load and VERIFY the frozen PREDMARKET spec -- refusing if the pre-registration has moved.

Mirror of the Newsdesk's `frozen.py`: the rules the tracker runs forward must be the rules frozen
before the first forward observation, so the loader recomputes the sha256 of the pre-registration
markdown and refuses if it no longer matches the hash pinned in the frozen JSON. A rule that can be
edited after the outcomes print is not frozen, and a forward test of an unfrozen rule measures nothing.
"""

from __future__ import annotations

import hashlib
import json
import pathlib

from . import Refused

ROOT = pathlib.Path(__file__).resolve().parents[3]
RESEARCH = ROOT / "research" / "trading_bot" / "predmarket"
CACHE = ROOT / "research" / "data" / "predmarket_cache"

FROZEN_PATH = RESEARCH / "PREDMARKET_FROZEN.json"
PREREG_PATH = RESEARCH / "PREDMARKET_PREREGISTRATION.md"
PREREG_LOG_PATH = RESEARCH / "PREDMARKET_PREREGISTRATION_LOG.jsonl"  # append-only, frozen at proposal
RESOLUTION_LOG_PATH = RESEARCH / "PREDMARKET_RESOLUTION_LOG.jsonl"   # append-only, at settlement
STATE_PATH = RESEARCH / "PREDMARKET_STATE.json"

SCHEMA_VERSION = 1

FRAMING = (
    "PREDMARKET -- agent-driven prediction-market FORWARD CALIBRATION tracker (a sibling of the "
    "Newsdesk). It places NO bets, holds NO position, touches NO account, wallet or real money, and "
    "reads only free keyless public data (Kalshi + Polymarket). An agent reads an OPEN, unresolved "
    "POLITICS/POLICY/SOFT-NEWS market and COMMITS its OWN probability q_agent (sha256+UTC) BEFORE "
    "resolution; the market-implied p_market is recorded at the same instant. The PRIMARY metric is "
    "CALIBRATION: when markets settle, is the agent's Brier score BETTER than the market's? Hypothetical "
    "bet-expectancy net of the fee/spread wall is a NOISY SECONDARY only. The honest prior: the agent is "
    "roughly calibration-competitive but NOT decisively better, expectancy pinned near zero by fees. "
    "The log is not yet evidence of anything."
)


def _sha256_file(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def frozen_spec() -> dict:
    """Load the frozen spec, refusing if the pre-registration markdown moved since the freeze."""
    for path in (FROZEN_PATH, PREREG_PATH):
        if not path.exists():
            raise Refused(f"{path} is missing; the frozen predmarket tracker cannot be loaded")
    spec = json.loads(FROZEN_PATH.read_text())
    expected = spec.get("preregistration_sha256")
    if not expected:
        raise Refused("PREDMARKET_FROZEN.json carries no preregistration_sha256")
    actual = _sha256_file(PREREG_PATH)
    if actual != expected:
        raise Refused(
            "PREDMARKET_PREREGISTRATION.md changed since the freeze.\n"
            f"  frozen expects: {expected}\n  on disk:        {actual}\n"
            "Restore the document. Do NOT update the hash: the point of the hash is that the rules this "
            "tracker runs forward are the rules frozen before the first forward observation. An "
            "improvement is a NEW frozen instrument, never an edit to a running one.")
    spec["_preregistration_sha256_verified"] = actual
    spec["_frozen_json_sha256"] = _sha256_file(FROZEN_PATH)
    return spec


# Envelope fields that are NOT part of a frozen estimate's fingerprint: the hash itself, and the
# storage-envelope fields the ledger stamps on AFTER the freeze. Excluding them means the freeze
# fingerprint covers exactly the falsifiable commitment -- venue, market_id, question, p_market at
# freeze, q_agent, side, edge, cost model, thesis, confidence, close/resolution date, proposed_utc.
_HASH_EXCLUDE = ("estimate_sha256", "_verified", "kind", "status")


def canonical_sha256(obj: dict) -> str:
    """Canonical SHA-256 of a frozen probability estimate (sorted keys, compact separators).

    The freeze fingerprint of a single estimate -- the thing that makes a forward commitment
    tamper-evident. Envelope fields (`_HASH_EXCLUDE`) are removed so the fingerprint is stable across
    the freeze and every later re-verification, regardless of the storage wrapper.
    """
    body = {k: v for k, v in obj.items() if k not in _HASH_EXCLUDE}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
