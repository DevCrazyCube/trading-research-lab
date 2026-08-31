#!/usr/bin/env python3
"""Seal and activation authority for the PAC scalp anti-exhaustion ENTRY arms (paper-only).

Parameterised sibling of :mod:`pac_scalp_manifest`.  Each arm (DIP, EARLY) is an independent set-once
sealed instrument whose dependency closure includes the reused engine, the shared exit policy, and its
OWN entry detector, so its seal is distinct.  Every arm inherits V2.4's already-anchored
processed-inclusion calibration byte-for-byte (the send/sign/land measurement path is unchanged), so
latency modelling is matched across the momentum arm and both entry arms.  Strategy results and
activation watermarks are never inherited.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import subprocess
import time

from .execution import RefusedExecution
from . import pac_v24_manifest as source
from . import pac_scalp_runner as runner


ROOT = pathlib.Path(__file__).resolve().parents[3]
RESEARCH = ROOT / "research" / "trading_bot" / "aftershock"

# arm instrument id -> its own entry detector source file
ARM_DETECTORS = {
    "AFTERSHOCK_PAC_SCALP_DIP": "scripts/trading_bot/aftershock/pac_scalp_detector_dip.py",
    "AFTERSHOCK_PAC_SCALP_EARLY": "scripts/trading_bot/aftershock/pac_scalp_detector_early.py",
}
_SHARED_PATHS = (
    "scripts/trading_bot/aftershock/pac_scalp_policy.py",
    "scripts/trading_bot/aftershock/pac_scalp_marklog.py",
    "scripts/trading_bot/aftershock/pac_scalp_runner.py",
    "scripts/trading_bot/aftershock/pac_scalp_arm_runner.py",
    "scripts/trading_bot/aftershock/pac_scalp_arm_manifest.py",
    "scripts/trading_bot/aftershock/pac_scalp_arm_selftest.py",
)


def _dependency_paths(instrument: str) -> tuple[str, ...]:
    if instrument not in ARM_DETECTORS:
        raise RefusedExecution(f"unknown PAC scalp arm instrument: {instrument}")
    return (*source.DEPENDENCY_PATHS, ARM_DETECTORS[instrument], *_SHARED_PATHS)


def _artifacts(instrument: str):
    return (RESEARCH / f"{instrument}_PREREGISTRATION.md",
            RESEARCH / f"{instrument}_FROZEN.json",
            RESEARCH / f"{instrument}_SEAL.json",
            RESEARCH / f"{instrument}_ACTIVATION.json")


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _json(path: pathlib.Path) -> dict:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise RefusedExecution(f"PAC scalp arm artifact unreadable: {path.name}") from exc
    if not isinstance(value, dict):
        raise RefusedExecution(f"PAC scalp arm artifact is not an object: {path.name}")
    return value


def _relative(path: pathlib.Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve()))
    except ValueError as exc:
        raise RefusedExecution("PAC scalp arm artifact escaped repository root") from exc


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
        raise RefusedExecution(f"PAC scalp arm lacks git anchor for {path.name}")
    return commit


def compute_seal(instrument: str) -> dict:
    prereg, frozen_path, _seal, _act = _artifacts(instrument)
    dependency_paths = _dependency_paths(instrument)
    frozen = _json(frozen_path)
    if frozen.get("instrument_id") != instrument:
        raise RefusedExecution("PAC scalp arm frozen instrument mismatch")
    if frozen.get("dependency_paths") != list(dependency_paths):
        raise RefusedExecution("PAC scalp arm frozen dependency closure mismatch")
    dependencies = {}
    for relative in dependency_paths:
        path = ROOT / relative
        try:
            dependencies[relative] = _sha(path.read_bytes())
        except OSError as exc:
            raise RefusedExecution(f"PAC scalp arm dependency unavailable: {relative}") from exc
    body = {
        "schema": 1, "instrument_id": instrument,
        "preregistration_sha256": _sha(prereg.read_bytes()),
        "frozen_canonical_sha256": _sha(_canonical(frozen)),
        "dependency_sha256": dependencies,
    }
    return {**body, "seal_sha256": _sha(_canonical(body))}


def write_seal(instrument: str) -> dict:
    _prereg, _frozen, seal_path, _act = _artifacts(instrument)
    if seal_path.exists():
        raise RefusedExecution("PAC scalp arm seal is set-once")
    value = compute_seal(instrument)
    runner.core._atomic_write(seal_path, value)
    return value


def verify_seal(instrument: str, *, require_anchor: bool = True) -> dict:
    prereg, frozen_path, seal_path, _act = _artifacts(instrument)
    observed = _json(seal_path)
    if observed != compute_seal(instrument):
        raise RefusedExecution("PAC scalp arm seal/dependency drift refuses")
    if require_anchor and not all(_anchored(p) for p in (prereg, frozen_path, seal_path)):
        raise RefusedExecution("PAC scalp arm seal is unanchored or dirty")
    return observed


def write_activation(instrument: str) -> dict:
    _prereg, _frozen, seal_path, act_path = _artifacts(instrument)
    if act_path.exists():
        raise RefusedExecution("PAC scalp arm activation is set-once")
    seal = verify_seal(instrument, require_anchor=True)
    inherited = source.load_runtime_proof()
    source_activation = _json(source.ACTIVATION)
    now = time.time_ns()
    body = {
        "schema": 1, "instrument_id": instrument,
        "activation_unix_nanos": now, "seal_sha256": seal["seal_sha256"],
        "calibration_inheritance": "V24_EXECUTOR_PATH_BYTE_UNCHANGED_STRATEGY_RESULTS_NOT_INHERITED",
        "source_instrument_id": source.INSTRUMENT,
        "source_activation_sha256": source_activation["activation_sha256"],
        "source_seal_sha256": inherited.seal_sha256,
        "processed_p90_nanos": inherited.calibration.processed_p90_nanos,
        "calibration_artifact_sha256": inherited.calibration.artifact_sha256,
    }
    value = {**body, "activation_sha256": _sha(_canonical(body))}
    runner.core._atomic_write(act_path, value)
    return value


def load_runtime_proof(instrument: str) -> runner.RuntimeProof:
    _prereg, _frozen, seal_path, act_path = _artifacts(instrument)
    seal = verify_seal(instrument, require_anchor=True)
    activation = _json(act_path)
    body = dict(activation); observed_hash = body.pop("activation_sha256", None)
    if (activation.get("instrument_id") != instrument
            or observed_hash != _sha(_canonical(body))
            or activation.get("seal_sha256") != seal["seal_sha256"]
            or not _anchored(act_path)):
        raise RefusedExecution("PAC scalp arm activation/hash/anchor refuses")
    seal_commit, activation_commit = _commit_for(seal_path), _commit_for(act_path)
    if (seal_commit == activation_commit
            or _git("merge-base", "--is-ancestor", seal_commit, activation_commit).returncode != 0):
        raise RefusedExecution("PAC scalp arm activation must be committed after the seal")
    inherited = source.load_runtime_proof()
    source_activation = _json(source.ACTIVATION)
    if (activation.get("source_activation_sha256") != source_activation.get("activation_sha256")
            or activation.get("source_seal_sha256") != inherited.seal_sha256
            or activation.get("processed_p90_nanos") != inherited.calibration.processed_p90_nanos
            or activation.get("calibration_artifact_sha256") != inherited.calibration.artifact_sha256):
        raise RefusedExecution("PAC scalp arm inherited executor calibration drift refuses")
    return runner.RuntimeProof(seal_sha256=seal["seal_sha256"],
                               activation_unix_nanos=activation["activation_unix_nanos"],
                               calibration=inherited.calibration)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="PAC scalp arm seal/activation authority")
    parser.add_argument("command", choices=("status", "write-seal", "write-activation"))
    parser.add_argument("instrument", choices=tuple(ARM_DETECTORS))
    args = parser.parse_args(argv)
    if args.command == "write-seal":
        result = write_seal(args.instrument)
    elif args.command == "write-activation":
        result = write_activation(args.instrument)
    else:
        _prereg, _frozen, seal_path, act_path = _artifacts(args.instrument)
        result = {"seal": seal_path.exists() and _anchored(seal_path),
                  "activation": act_path.exists() and _anchored(act_path)}
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
