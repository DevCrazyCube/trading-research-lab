#!/usr/bin/env python3
"""Seal, campaign ancestry, and activation authority for PAC_SCALP_LL.

The seal is set once over the preregistration, frozen configuration, and complete executable
dependency list.  A broadcast campaign must be a clean tracked artifact committed strictly after the
seal.  Calibration/attestation/activation support is intentionally fail-closed until those artifacts
exist; no latency default or inherited strategy evidence is permitted.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
import pathlib
import subprocess
import tempfile

from .execution import RefusedExecution
from . import pac_scalp_ll_campaign as campaigns


INSTRUMENT = campaigns.INSTRUMENT
ROOT = pathlib.Path(__file__).resolve().parents[3]
RESEARCH = ROOT / "research" / "trading_bot" / "aftershock"
PREREG = RESEARCH / f"{INSTRUMENT}_PREREGISTRATION.md"
FROZEN = RESEARCH / f"{INSTRUMENT}_FROZEN.json"
SEAL = RESEARCH / f"{INSTRUMENT}_SEAL.json"
CAMPAIGN = RESEARCH / f"{INSTRUMENT}_CAMPAIGN.json"
CALIBRATION_SUMMARY = RESEARCH / f"{INSTRUMENT}_CALIBRATION_SUMMARY.json"
ATTESTATION = RESEARCH / f"{INSTRUMENT}_CALIBRATION_ATTESTATION.json"
ACTIVATION = RESEARCH / f"{INSTRUMENT}_ACTIVATION.json"
RAW_ROOT = ROOT / "research" / "data" / "aftershock" / "pac_scalp_ll"
RAW_JOURNAL = RAW_ROOT / "calibration_journal.json"
RAW_ATTESTATION = RAW_ROOT / "calibration_attestation_raw.json"
CAMPAIGN_LOCK = RAW_ROOT / "campaign.lock"
FROZEN_MAX_LAMPORTS = 3_000_000

DEPENDENCY_PATHS = (
    "scripts/b9d_transaction_bodies.py",
    "scripts/b9i_quote_reproduction.py",
    "scripts/b10a_simulator_kernel.py",
    "scripts/trading_bot/aftershock/execution.py",
    "scripts/trading_bot/aftershock/ecr.py",
    "scripts/trading_bot/aftershock/feasibility.py",
    "scripts/trading_bot/aftershock/pac_v2_calibration.py",
    "scripts/trading_bot/aftershock/pac_v2_snapshot.py",
    "scripts/trading_bot/aftershock/pac_v2_pumpswap.py",
    "scripts/trading_bot/aftershock/pac_scalp_ll_accounting.py",
    "scripts/trading_bot/aftershock/pac_scalp_ll_policy.py",
    "scripts/trading_bot/aftershock/pac_scalp_ll_portfolio.py",
    "scripts/trading_bot/aftershock/pac_scalp_ll_route.py",
    "scripts/trading_bot/aftershock/pac_scalp_ll_clock.py",
    "scripts/trading_bot/aftershock/pac_scalp_ll_marklog.py",
    "scripts/trading_bot/aftershock/pac_scalp_ll_ledger.py",
    "scripts/trading_bot/aftershock/pac_scalp_ll_engine.py",
    "scripts/trading_bot/aftershock/pac_scalp_ll_venue.py",
    "scripts/trading_bot/aftershock/pac_scalp_ll_tx.py",
    "scripts/trading_bot/aftershock/pac_scalp_ll_campaign.py",
    "scripts/trading_bot/aftershock/pac_scalp_ll_calibration.py",
    "scripts/trading_bot/aftershock/pac_scalp_ll_attest.py",
    "scripts/trading_bot/aftershock/pac_scalp_ll_manifest.py",
    "scripts/trading_bot/aftershock/pac_scalp_ll_selftest.py",
)


def _sha_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _json(path: pathlib.Path) -> dict:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise RefusedExecution(f"PAC_SCALP_LL artifact unreadable: {path.name}") from exc
    if not isinstance(value, dict):
        raise RefusedExecution(f"PAC_SCALP_LL artifact is not an object: {path.name}")
    return value


def _atomic(path: pathlib.Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=".pac_scalp_ll_manifest_")
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(_canonical(value) + b"\n"); handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _relative(path: pathlib.Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve()))
    except ValueError as exc:
        raise RefusedExecution("PAC_SCALP_LL artifact escaped the repository") from exc


def require_exact_path(observed: pathlib.Path, expected: pathlib.Path, *, label: str) -> None:
    if pathlib.Path(observed).resolve() != pathlib.Path(expected).resolve():
        raise RefusedExecution(f"PAC_SCALP_LL {label} path is not manifest-owned")


@contextmanager
def exclusive_campaign():
    """One host-wide writer covers load, budget check, every send, and final persist."""
    RAW_ROOT.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(CAMPAIGN_LOCK, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        if os.fstat(descriptor).st_mode & 0o077:
            raise RefusedExecution("PAC_SCALP_LL campaign lock permissions are unsafe")
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RefusedExecution("PAC_SCALP_LL campaign already has an active writer") from exc
        yield
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


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
        raise RefusedExecution(f"PAC_SCALP_LL lacks git anchor for {path.name}")
    return commit


def _strict_ancestor(earlier: pathlib.Path, later: pathlib.Path) -> bool:
    first, second = _commit_for(earlier), _commit_for(later)
    return (first != second
            and _git("merge-base", "--is-ancestor", first, second).returncode == 0)


def compute_seal() -> dict:
    frozen = _json(FROZEN)
    if (frozen.get("instrument_id") != INSTRUMENT
            or frozen.get("dependency_paths") != list(DEPENDENCY_PATHS)):
        raise RefusedExecution("PAC_SCALP_LL frozen dependency closure mismatch")
    dependencies = {}
    for relative in DEPENDENCY_PATHS:
        try:
            dependencies[relative] = _sha_bytes((ROOT / relative).read_bytes())
        except OSError as exc:
            raise RefusedExecution(f"PAC_SCALP_LL dependency unavailable: {relative}") from exc
    try:
        preregistration_sha = _sha_bytes(PREREG.read_bytes())
    except OSError as exc:
        raise RefusedExecution("PAC_SCALP_LL preregistration is unavailable") from exc
    body = {
        "schema": 1, "instrument_id": INSTRUMENT,
        "preregistration_sha256": preregistration_sha,
        "frozen_canonical_sha256": _sha_bytes(_canonical(frozen)),
        "dependency_sha256": dependencies,
    }
    return {**body, "seal_sha256": _sha_bytes(_canonical(body))}


def write_seal() -> dict:
    if SEAL.exists():
        raise RefusedExecution("PAC_SCALP_LL seal is set-once")
    value = compute_seal(); _atomic(SEAL, value); return value


def verify_seal(*, require_anchor: bool = True) -> dict:
    observed = _json(SEAL)
    if observed != compute_seal():
        raise RefusedExecution("PAC_SCALP_LL seal/dependency drift refuses")
    if require_anchor and not all(_anchored(path) for path in (PREREG, FROZEN, SEAL)):
        raise RefusedExecution("PAC_SCALP_LL seal is unanchored or dirty")
    return observed


def require_campaign_authority(path: pathlib.Path, *, file_sha256: str) -> campaigns.Campaign:
    candidate = pathlib.Path(path).resolve()
    if candidate != CAMPAIGN.resolve():
        raise RefusedExecution("PAC_SCALP_LL broadcast requires the manifest campaign path")
    verify_seal(require_anchor=True)
    campaign = campaigns.load(candidate, expected_sha256=file_sha256)
    frozen_calibration = _json(FROZEN).get("calibration")
    if (not isinstance(frozen_calibration, dict)
            or campaign.samples_per_arm != frozen_calibration.get("attempted_pairs")
            or campaign.profile.compute_unit_limit
            != frozen_calibration.get("compute_unit_limit")
            or campaign.profile.micro_lamports_per_cu
            != frozen_calibration.get("micro_lamports_per_cu")
            or campaign.profile.tip_lamports != frozen_calibration.get("tip_lamports")
            or campaign.max_lamports != frozen_calibration.get("max_lamports")
            or campaign.max_lamports != FROZEN_MAX_LAMPORTS
            or campaigns.POLL_INTERVAL_NANOS
            != frozen_calibration.get("poll_interval_nanos")
            or campaigns.LANDING_DEADLINE_NANOS
            != frozen_calibration.get("landing_deadline_nanos")):
        raise RefusedExecution("PAC_SCALP_LL campaign differs from frozen calibration parameters")
    if not _anchored(candidate) or not _strict_ancestor(SEAL, candidate):
        raise RefusedExecution("PAC_SCALP_LL campaign must be clean-anchored after the seal")
    return campaign


def status() -> dict:
    def safe_anchor(path: pathlib.Path) -> bool:
        return path.exists() and _anchored(path)
    return {
        "instrument_id": INSTRUMENT,
        "seal": "ANCHORED" if safe_anchor(SEAL) else ("UNANCHORED" if SEAL.exists() else "ABSENT"),
        "campaign": ("ANCHORED" if safe_anchor(CAMPAIGN)
                     else "UNANCHORED" if CAMPAIGN.exists() else "ABSENT"),
        "calibration": ("ANCHORED" if safe_anchor(CALIBRATION_SUMMARY)
                        else "UNANCHORED" if CALIBRATION_SUMMARY.exists() else "ABSENT"),
        "attestation": ("ANCHORED" if safe_anchor(ATTESTATION)
                        else "UNANCHORED" if ATTESTATION.exists() else "ABSENT"),
        "activation": ("ANCHORED" if safe_anchor(ACTIVATION)
                       else "UNANCHORED" if ACTIVATION.exists() else "ABSENT"),
        "authority": "DEFAULT_OFF_NO_BROADCAST" if not safe_anchor(CAMPAIGN)
        else "CAMPAIGN_ANCHORED_BROADCAST_REQUIRES_EXPLICIT_FLAG",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="PAC_SCALP_LL manifest")
    parser.add_argument("command", choices=("status", "write-seal"))
    args = parser.parse_args(argv)
    result = write_seal() if args.command == "write-seal" else status()
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
