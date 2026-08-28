#!/usr/bin/env python3
"""PAC V2 closed seal, calibrated activation, and runtime authority.

The seal is not evidence until every byte in its closure is committed and clean.  Activation is set
once with an internal clock and pins one authentic calibration artifact by whole-file hash.  Runtime
loading repeats every check; command-line latency values do not exist.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import time

from .execution import RefusedExecution
from .pac_v2_calibration import CalibrationRefused, load as load_calibration
from .pac_v2_runner import RuntimeProof


INSTRUMENT = "AFTERSHOCK_PAC_V2"
ROOT = pathlib.Path(__file__).resolve().parents[3]
RESEARCH = ROOT / "research" / "trading_bot" / "aftershock"
PREREG = RESEARCH / f"{INSTRUMENT}_PREREGISTRATION.md"
FROZEN = RESEARCH / f"{INSTRUMENT}_FROZEN.json"
SEAL = RESEARCH / f"{INSTRUMENT}_SEAL.json"
ACTIVATION = RESEARCH / f"{INSTRUMENT}_ACTIVATION.json"

DEPENDENCY_PATHS = (
    "research/pump_amm_idl_9c82f61.json",
    "research/pump_idl_9c82f61.json",
    "scripts/b10a_simulator_kernel.py",
    "scripts/b10b_position_path.py",
    "scripts/b15a_websocket.py",
    "scripts/b9d_transaction_bodies.py",
    "scripts/b9i_quote_reproduction.py",
    "scripts/rpc_http_identity.py",
    "scripts/trading_bot/aftershock/__init__.py",
    "scripts/trading_bot/aftershock/ecr.py",
    "scripts/trading_bot/aftershock/execution.py",
    "scripts/trading_bot/aftershock/feasibility.py",
    "scripts/trading_bot/aftershock/pac_detector.py",
    "scripts/trading_bot/aftershock/pac_v2_calibration.py",
    "scripts/trading_bot/aftershock/pac_v2_detector.py",
    "scripts/trading_bot/aftershock/pac_v2_feed.py",
    "scripts/trading_bot/aftershock/pac_v2_manifest.py",
    "scripts/trading_bot/aftershock/pac_v2_policy.py",
    "scripts/trading_bot/aftershock/pac_v2_runner.py",
    "scripts/trading_bot/aftershock/pac_v2_snapshot.py",
    "scripts/trading_bot/aftershock/pac_v2_status.py",
    "scripts/trading_bot/aftershock/solusd_recorder.py",
    "scripts/trading_bot/sniper/data/_common.py",
    "scripts/trading_bot/sniper/types.py",
)


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _repo_file(relative: str) -> pathlib.Path:
    if not isinstance(relative, str) or not relative or pathlib.PurePosixPath(relative).is_absolute():
        raise RefusedExecution("PAC V2 dependency path is not repo-relative")
    path = (ROOT / relative).resolve()
    try:
        path.relative_to(ROOT)
    except ValueError as exc:
        raise RefusedExecution("PAC V2 dependency escapes the repository") from exc
    if not path.is_file():
        raise RefusedExecution(f"PAC V2 dependency missing: {relative}")
    return path


def _json(path: pathlib.Path) -> dict:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise RefusedExecution(f"PAC V2 cannot parse {path.name}") from exc
    if not isinstance(value, dict):
        raise RefusedExecution(f"PAC V2 {path.name} is not an object")
    return value


def _git_clean(path: pathlib.Path) -> bool:
    try:
        relative = str(path.resolve().relative_to(ROOT))
        tracked = subprocess.run(["git", "ls-files", "--error-unmatch", "--", relative],
                                 cwd=ROOT, capture_output=True, timeout=10, check=False)
        clean = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", relative],
                               cwd=ROOT, capture_output=True, timeout=10, check=False)
        return tracked.returncode == 0 and clean.returncode == 0
    except (OSError, subprocess.SubprocessError, ValueError):
        return False


def compute_seal() -> dict:
    if not PREREG.is_file():
        raise RefusedExecution("PAC V2 preregistration is missing")
    frozen = _json(FROZEN)
    prereg_sha = _sha(PREREG.read_bytes())
    if (frozen.get("instrument_id") != INSTRUMENT
            or frozen.get("preregistration_sha256") != prereg_sha
            or frozen.get("dependency_paths") != list(DEPENDENCY_PATHS)):
        raise RefusedExecution("PAC V2 frozen config does not close the preregistration/dependency set")
    dependencies = {relative: _sha(_repo_file(relative).read_bytes())
                    for relative in DEPENDENCY_PATHS}
    body = {"schema": 1, "instrument_id": INSTRUMENT,
            "preregistration_sha256": prereg_sha,
            "frozen_canonical_sha256": _sha(_canonical(frozen)),
            "dependency_sha256": dependencies}
    return {**body, "seal_sha256": _sha(_canonical(body))}


def write_seal() -> dict:
    expected = compute_seal()
    if SEAL.exists():
        if _json(SEAL) != expected:
            raise RefusedExecution("PAC V2 existing seal differs; never overwrite a seal")
        return expected
    SEAL.write_text(json.dumps(expected, indent=2, sort_keys=True) + "\n")
    return expected


def verify_seal() -> dict:
    written = _json(SEAL)
    if written != compute_seal():
        raise RefusedExecution("PAC V2 seal or dependency closure drifted")
    return written


def anchor_status() -> str:
    try:
        verify_seal()
    except RefusedExecution:
        return "UNSEALED"
    closed = (PREREG, FROZEN, SEAL, *(_repo_file(path) for path in DEPENDENCY_PATHS))
    return "ANCHORED" if all(_git_clean(path) for path in closed) else "UNANCHORED"


def write_activation(calibration_path: pathlib.Path, *, expected_sha256: str) -> dict:
    seal = verify_seal()
    if anchor_status() != "ANCHORED":
        raise RefusedExecution("PAC V2 seal is unanchored; activation prohibited")
    if ACTIVATION.exists():
        raise RefusedExecution("PAC V2 activation is set-once")
    try:
        relative = str(pathlib.Path(calibration_path).resolve().relative_to(ROOT))
        calibration = load_calibration(pathlib.Path(calibration_path), expected_sha256=expected_sha256)
    except (ValueError, CalibrationRefused) as exc:
        raise RefusedExecution(f"PAC V2 calibration refused: {exc}") from exc
    recorded = time.time_ns()
    if recorded <= calibration.last_land_unix_nanos:
        raise RefusedExecution("PAC V2 activation does not follow calibration completion")
    body = {"schema": 1, "instrument_id": INSTRUMENT, "seal_sha256": seal["seal_sha256"],
            "calibration_path": relative, "calibration_sha256": calibration.artifact_sha256,
            "activation_unix_nanos": recorded}
    event = {**body, "activation_sha256": _sha(_canonical(body))}
    descriptor = os.open(ACTIVATION, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        os.write(descriptor, (json.dumps(event, indent=2, sort_keys=True) + "\n").encode())
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return event


def load_runtime_proof() -> RuntimeProof:
    seal = verify_seal()
    if anchor_status() != "ANCHORED":
        raise RefusedExecution("PAC V2 seal is not git-anchored")
    if not ACTIVATION.is_file() or not _git_clean(ACTIVATION):
        raise RefusedExecution("PAC V2 calibrated activation is absent or unanchored")
    activation = _json(ACTIVATION)
    stored = activation.get("activation_sha256"); body = dict(activation); body.pop("activation_sha256", None)
    required = {"schema", "instrument_id", "seal_sha256", "calibration_path",
                "calibration_sha256", "activation_unix_nanos"}
    if (set(body) != required or stored != _sha(_canonical(body)) or body["schema"] != 1
            or body["instrument_id"] != INSTRUMENT or body["seal_sha256"] != seal["seal_sha256"]):
        raise RefusedExecution("PAC V2 activation is malformed, forged, or references another seal")
    path = _repo_file(body["calibration_path"])
    try:
        calibration = load_calibration(path, expected_sha256=body["calibration_sha256"])
    except CalibrationRefused as exc:
        raise RefusedExecution(f"PAC V2 calibration refused: {exc}") from exc
    return RuntimeProof(seal["seal_sha256"], body["activation_unix_nanos"], calibration)
