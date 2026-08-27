#!/usr/bin/env python3
"""Load and VERIFY the frozen memebot spec -- refusing if the pre-registration has moved.

Mirrors `newsdesk.frozen` / `basket_forward.frozen_spec`: the rules the bot runs forward must be the
rules frozen before the first paper entry, so the loader recomputes the sha256 of the pre-registration
markdown and refuses if it no longer matches the hash pinned in the frozen JSON. A rule that can be
edited after the price prints is not frozen, and a forward test of an unfrozen rule measures nothing.
An improvement is a NEW frozen instrument, never an edit to a running one.
"""

from __future__ import annotations

import hashlib
import json
import pathlib

from . import Refused

ROOT = pathlib.Path(__file__).resolve().parents[3]
RESEARCH = ROOT / "research" / "trading_bot" / "memebot"
CACHE = ROOT / "research" / "data" / "memebot_cache"

# Three frozen instruments run in PARALLEL on the SAME live coins and the SAME entry screen, differing
# ONLY in their exit/take-profit/timescale logic (see each pre-registration). Each is a fully separate
# frozen object -- its own pre-registration markdown + hash, its own two append-only ledgers, its own
# state -- so none can contaminate another and fresh forward data adjudicates which EXIT rule is better.
#   MEMEBOT1       -- the base: 180-min horizon, fixed +50% target (frozen 2026-08-25, untouched).
#   MEMEBOT_FAST   -- variant: ~25-min horizon + dead-coin early exit, fixed +50% target (untouched).
#   MEMEBOT_RUNNER -- variant: HIGH +110% take-profit + dead-exit + 90-min horizon (from an EARLIER
#                     g73c7da snapshot); tests whether letting the fat right tail RUN beats the +50% cap.
#   MEMEBOT_G73    -- variant: the UPDATED best evo genome g73c7da frozen as an instrument -- HIGH +111%
#                     take-profit + dead-exit + 106-min horizon, MINUS the flow-exit (the frozen executor
#                     does not implement a flow-exit, so g73c7da's use_flow_exit is dropped, not faked).
#   MEMEBOT_QUICK  -- variant: identical to MEMEBOT_FAST but a SHORTER 15-min horizon (vs 25). FAST's
#                     first verdict showed every winner resolved by ~21 min while every unexitable death
#                     came at the 25-min horizon (on-chain-verified real rugs, liq -> $0); QUICK tests
#                     the owner's speed thesis that being faster out books non-winners while exit
#                     liquidity still exists. 15 min is a-priori, not fit to the sample's max-winner time.
#   MEMEBOT_EXIT   -- the EXITABILITY-FIRST fast-scalp: shared screen PLUS a positive exit-path rule
#                     (require >= 3 demonstrated sellers -- don't buy what nobody has sold) + a high
#                     liquidity floor, and a FAST 12-min horizon. Attacks the ONE leak that kills the
#                     money -- the unexitable dump. Its decider is the unexitable-dump rate, not a t-stat.
#   MEMEBOT_EXIT_V2 -- clean Pump-only successor: scope exclusions never become controls, stop gaps fill
#                     at the worse observed mark, and unavailable exits are a full paper loss.
INSTRUMENTS = {"MEMEBOT1": "MEMEBOT", "MEMEBOT_FAST": "MEMEBOT_FAST",
               "MEMEBOT_RUNNER": "MEMEBOT_RUNNER", "MEMEBOT_G73": "MEMEBOT_G73",
               "MEMEBOT_QUICK": "MEMEBOT_QUICK", "MEMEBOT_EXIT": "MEMEBOT_EXIT",
               "MEMEBOT_EXIT_V2": "MEMEBOT_EXIT_V2"}
ACTIVE_INSTRUMENTS = ("MEMEBOT1", "MEMEBOT_FAST", "MEMEBOT_RUNNER", "MEMEBOT_G73",
                      "MEMEBOT_QUICK", "MEMEBOT_EXIT", "MEMEBOT_EXIT_V2")

# The base file prefix (kept as the legacy "MEMEBOT" so the running base ledger is never renamed).
FROZEN_PATH = RESEARCH / "MEMEBOT_FROZEN.json"
PREREG_PATH = RESEARCH / "MEMEBOT_PREREGISTRATION.md"

SCHEMA_VERSION = 1


def paths_for(prefix: str) -> dict:
    """The five on-disk artefacts for one frozen instrument, keyed by its file prefix."""
    return {
        "frozen_json": RESEARCH / f"{prefix}_FROZEN.json",
        "prereg_md": RESEARCH / f"{prefix}_PREREGISTRATION.md",
        "prereg_log": RESEARCH / f"{prefix}_PREREGISTRATION_LOG.jsonl",   # append-only, frozen at entry
        "resolution_log": RESEARCH / f"{prefix}_RESOLUTION_LOG.jsonl",    # append-only, mark-to-market
        "state": RESEARCH / f"{prefix}_STATE.json",
    }

FRAMING = (
    "MEMEBOT1 -- fast/light reactive PAPER memecoin bot (sibling of NEWSDESK/BASKET1). It places NO "
    "orders, holds NO wallet, touches NO real SOL, writes NOTHING on-chain, and reads only free "
    "keyless public data. Every position is a hypothetical mark-to-market; each entry is frozen "
    "(sha256+UTC) BEFORE its outcome, so the log is lookahead-proof. It tests ONE honest hypothesis: "
    "can a loss-avoidance screen (deadness-proxy + red-flag filters) plus fixed-fraction sizing and a "
    "defined-risk stop/target produce ANY positive expectancy, net of the ~3% venue toll charged on "
    "every paper trade? The honest prior is ~0 or NEGATIVE. The target is POSITIVE EXPECTANCY, NOT "
    "'double every hour' (the farmer's bait, never a goal here). Below the pre-registered minimum this "
    "is behaviour, not evidence. Real trading is a SEPARATE, owner-gated wallet decision."
)


def _sha256_file(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def frozen_spec(instrument: str = "MEMEBOT1") -> dict:
    """Load one frozen instrument's spec, refusing if its pre-registration markdown moved since freeze."""
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
            "Restore the document. Do NOT update the hash: the rules this bot runs forward are the "
            "rules frozen before the first paper entry. An improvement is a NEW frozen instrument, "
            "never an edit to a running one.")
    spec["_preregistration_sha256_verified"] = actual
    spec["_frozen_json_sha256"] = _sha256_file(paths["frozen_json"])
    spec["_paths"] = paths
    return spec


def active_specs() -> list:
    """Load every parallel instrument that is currently running forward."""
    return [frozen_spec(i) for i in ACTIVE_INSTRUMENTS]


# Envelope fields NOT part of a setup's freeze fingerprint: the hash itself, the storage-envelope
# fields the ledger stamps on AFTER the freeze, and any private/derived marker. Excluding them means
# the fingerprint covers exactly the falsifiable commitment and recomputes byte-for-byte later.
_HASH_EXCLUDE = ("setup_sha256", "_verified", "kind", "status")


def canonical_sha256(obj: dict) -> str:
    """Canonical SHA-256 of a setup's frozen spec (sorted keys, compact separators)."""
    body = {k: v for k, v in obj.items() if k not in _HASH_EXCLUDE}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
