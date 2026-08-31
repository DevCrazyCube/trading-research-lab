#!/usr/bin/env python3
"""Shared seal-closure list + generic hash/canonical/git-anchor helpers for the PAC Launch-Window
Sentinel Scalper family (paper-only).

This module is a sibling of the sealed engine — it edits nothing.  It centralises (a) the exact
dependency closure both PAC_LWS manifests seal over, so the veto arm and the null arm pin an identical
set of source files, and (b) the small git/hash helpers the manifests reuse (mirrored from
``pac_scalp_arm_manifest``).  Keeping the closure in one place means a new file in the instrument can
never be silently omitted from one arm's seal but not the other's.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess

from .execution import RefusedExecution
from . import pac_v24_manifest as source


ROOT = pathlib.Path(__file__).resolve().parents[3]
RESEARCH = ROOT / "research" / "trading_bot" / "aftershock"

# ---------------------------------------------------------------------------------------------------
# Seal closure.  DEPENDENCY_PATHS = the inherited V2.4 executor/latency closure (which already pins the
# reused pac_v2 runner/feed/snapshot/pumpswap engine, ecr, execution, feasibility, the b10a kernel, the
# b9d/b9i curve reproduction and _common) PLUS the new pac_lws_* files, the validated B20B screen
# closure, and the reused pac_scalp exit policy + mark logger.  Deduped, order-preserving.
# ---------------------------------------------------------------------------------------------------
PAC_LWS_PATHS = (
    "scripts/trading_bot/aftershock/pac_lws_screen.py",
    "scripts/trading_bot/aftershock/pac_lws_feed.py",
    "scripts/trading_bot/aftershock/pac_lws_common.py",
    "scripts/trading_bot/aftershock/pac_lws_runner.py",
    "scripts/trading_bot/aftershock/pac_lws_selftest.py",
)
# The validated deadness screen (b20b) and the create/trade decoders the feed and screen rest on.
SCREEN_CLOSURE = (
    "scripts/b20b_deadness_screen_runner.py",
    "scripts/b15a_shadow_pilot.py",
    "scripts/b15i_processed_feed.py",
)
# Reused byte-identically by the runner (the convex exit policy + the intra-trade mark logger).
REUSED_PATHS = (
    "scripts/trading_bot/aftershock/pac_scalp_policy.py",
    "scripts/trading_bot/aftershock/pac_scalp_marklog.py",
)


def _dedupe(paths) -> tuple[str, ...]:
    seen: dict[str, None] = {}
    for path in paths:
        seen.setdefault(path, None)
    return tuple(seen)


def dependency_paths(*, manifest_path: str) -> tuple[str, ...]:
    """The full sealed closure for one PAC_LWS arm, including that arm's own manifest file."""
    return _dedupe((*source.DEPENDENCY_PATHS, *PAC_LWS_PATHS, *SCREEN_CLOSURE,
                    *REUSED_PATHS, manifest_path))


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _json(path: pathlib.Path) -> dict:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise RefusedExecution(f"PAC_LWS artifact unreadable: {path.name}") from exc
    if not isinstance(value, dict):
        raise RefusedExecution(f"PAC_LWS artifact is not an object: {path.name}")
    return value


def _relative(path: pathlib.Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve()))
    except ValueError as exc:
        raise RefusedExecution("PAC_LWS artifact escaped repository root") from exc


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(("git", *args), cwd=ROOT, text=True, capture_output=True, check=False)


def _anchored(path: pathlib.Path) -> bool:
    relative = _relative(path)
    return (_git("ls-files", "--error-unmatch", relative).returncode == 0
            and not _git("status", "--porcelain", "--", relative).stdout.strip())


def _commit_for(path: pathlib.Path) -> str:
    result = _git("log", "-1", "--format=%H", "--", _relative(path))
    commit = result.stdout.strip()
    if result.returncode != 0 or len(commit) != 40:
        raise RefusedExecution(f"PAC_LWS lacks git anchor for {path.name}")
    return commit


def dependency_digest(*, manifest_path: str) -> dict:
    """Resolve the closure to a {relative_path: sha256} map, refusing if any file is missing.

    This is the load-bearing half of ``compute_seal`` and works with no committed prereg/frozen
    artifacts, so the authority module can be exercised before the main session seals it."""
    digest: dict[str, str] = {}
    for relative in dependency_paths(manifest_path=manifest_path):
        path = ROOT / relative
        try:
            digest[relative] = _sha(path.read_bytes())
        except OSError as exc:
            raise RefusedExecution(f"PAC_LWS dependency unavailable: {relative}") from exc
    return digest
