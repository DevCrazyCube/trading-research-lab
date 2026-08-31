#!/usr/bin/env python3
"""Seal and activation authority for the PAC V2.6 paper-only challenger."""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import subprocess
import time

from .execution import RefusedExecution
from . import pac_v25_manifest as source
from . import pac_v26_policy as policy
from . import pac_v26_runner as runner


INSTRUMENT = "AFTERSHOCK_PAC_V26"
ROOT = pathlib.Path(__file__).resolve().parents[3]
RESEARCH = ROOT / "research" / "trading_bot" / "aftershock"
PREREG = RESEARCH / f"{INSTRUMENT}_PREREGISTRATION.md"
FROZEN = RESEARCH / f"{INSTRUMENT}_FROZEN.json"
SEAL = RESEARCH / f"{INSTRUMENT}_SEAL.json"
ACTIVATION = RESEARCH / f"{INSTRUMENT}_ACTIVATION.json"
DEPENDENCY_PATHS = (*source.DEPENDENCY_PATHS,
                    "scripts/trading_bot/aftershock/pac_v26_policy.py",
                    "scripts/trading_bot/aftershock/pac_v26_runner.py",
                    "scripts/trading_bot/aftershock/pac_v26_selftest.py",
                    "scripts/trading_bot/aftershock/pac_v26_manifest.py",
                    "scripts/trading_bot/aftershock/pac_v26_launch.py")


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _json(path: pathlib.Path) -> dict:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise RefusedExecution(f"PAC V2.6 artifact unreadable: {path.name}") from exc
    if not isinstance(value, dict):
        raise RefusedExecution(f"PAC V2.6 artifact is not an object: {path.name}")
    return value


def _relative(path: pathlib.Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve()))
    except ValueError as exc:
        raise RefusedExecution("PAC V2.6 artifact escaped repository root") from exc


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
        raise RefusedExecution(f"PAC V2.6 lacks git anchor for {path.name}")
    return commit


def compute_seal() -> dict:
    frozen = _json(FROZEN)
    if frozen.get("instrument_id") != INSTRUMENT:
        raise RefusedExecution("PAC V2.6 frozen instrument mismatch")
    if frozen.get("dependency_paths") != list(DEPENDENCY_PATHS):
        raise RefusedExecution("PAC V2.6 frozen dependency closure mismatch")
    exit_spec = frozen.get("exit") if isinstance(frozen.get("exit"), dict) else {}
    promotion = (frozen.get("promotion_gate")
                 if isinstance(frozen.get("promotion_gate"), dict) else {})
    calibration_spec = (frozen.get("calibration")
                        if isinstance(frozen.get("calibration"), dict) else {})
    source_activation = _json(source.ACTIVATION)
    if (frozen.get("paper_scenario_only") is not True
            or frozen.get("live_trading") is not False
            or exit_spec.get("all_cost_risk_budget_num") != policy.RISK_BUDGET_NUM
            or exit_spec.get("all_cost_risk_budget_den") != policy.RISK_BUDGET_DEN
            or exit_spec.get("trail_percent") != policy.TRAIL_NUM
            or exit_spec.get("absolute_horizon_nanos") != policy.MAX_HOLD_NANOS
            or promotion.get("terminal_positions") != 100
            or promotion.get("leave_single_best_out_mean_positive") is not True
            or calibration_spec.get("source_activation_sha256")
            != source_activation.get("activation_sha256")
            or calibration_spec.get("processed_p90_nanos") != 3_788_307_712):
        raise RefusedExecution("PAC V2.6 frozen constants drift from the engine or authority")
    dependencies = {}
    for relative in DEPENDENCY_PATHS:
        path = ROOT / relative
        try:
            dependencies[relative] = _sha(path.read_bytes())
        except OSError as exc:
            raise RefusedExecution(f"PAC V2.6 dependency unavailable: {relative}") from exc
    body = {
        "schema": 1, "instrument_id": INSTRUMENT,
        "preregistration_sha256": _sha(PREREG.read_bytes()),
        "frozen_canonical_sha256": _sha(_canonical(frozen)),
        "dependency_sha256": dependencies,
    }
    return {**body, "seal_sha256": _sha(_canonical(body))}


def write_seal() -> dict:
    if SEAL.exists():
        raise RefusedExecution("PAC V2.6 seal is set-once")
    value = compute_seal()
    runner.core._atomic_write(SEAL, value)
    return value


def verify_seal(*, require_anchor: bool = True) -> dict:
    observed = _json(SEAL)
    if observed != compute_seal():
        raise RefusedExecution("PAC V2.6 seal/dependency drift refuses")
    anchored_paths = (PREREG, FROZEN, SEAL,
                      *(ROOT / relative for relative in DEPENDENCY_PATHS))
    if require_anchor and not all(_anchored(path) for path in anchored_paths):
        raise RefusedExecution("PAC V2.6 seal is unanchored or dirty")
    return observed


def write_activation() -> dict:
    if ACTIVATION.exists():
        raise RefusedExecution("PAC V2.6 activation is set-once")
    seal = verify_seal(require_anchor=True)
    inherited = source.load_runtime_proof()
    source_activation = _json(source.ACTIVATION)
    now = time.time_ns()
    body = {
        "schema": 1, "instrument_id": INSTRUMENT,
        "activation_unix_nanos": now, "seal_sha256": seal["seal_sha256"],
        "calibration_inheritance": "V25_EXECUTOR_PATH_BYTE_UNCHANGED_STRATEGY_RESULTS_NOT_INHERITED",
        "source_instrument_id": source.INSTRUMENT,
        "source_activation_sha256": source_activation["activation_sha256"],
        "source_seal_sha256": inherited.seal_sha256,
        "processed_p90_nanos": inherited.calibration.processed_p90_nanos,
        "calibration_artifact_sha256": inherited.calibration.artifact_sha256,
    }
    value = {**body, "activation_sha256": _sha(_canonical(body))}
    runner.core._atomic_write(ACTIVATION, value)
    return value


def load_runtime_proof() -> runner.RuntimeProof:
    seal = verify_seal(require_anchor=True)
    activation = _json(ACTIVATION)
    body = dict(activation); observed_hash = body.pop("activation_sha256", None)
    if (activation.get("instrument_id") != INSTRUMENT
            or observed_hash != _sha(_canonical(body))
            or activation.get("seal_sha256") != seal["seal_sha256"]
            or not _anchored(ACTIVATION)):
        raise RefusedExecution("PAC V2.6 activation/hash/anchor refuses")
    seal_commit, activation_commit = _commit_for(SEAL), _commit_for(ACTIVATION)
    if (seal_commit == activation_commit
            or _git("merge-base", "--is-ancestor", seal_commit, activation_commit).returncode != 0):
        raise RefusedExecution("PAC V2.6 activation must be committed after the seal")
    inherited = source.load_runtime_proof()
    source_activation = _json(source.ACTIVATION)
    if (activation.get("source_activation_sha256") != source_activation.get("activation_sha256")
            or activation.get("source_seal_sha256") != inherited.seal_sha256
            or activation.get("processed_p90_nanos") != inherited.calibration.processed_p90_nanos
            or activation.get("calibration_artifact_sha256") != inherited.calibration.artifact_sha256):
        raise RefusedExecution("PAC V2.6 inherited executor calibration drift refuses")
    return runner.RuntimeProof(seal_sha256=seal["seal_sha256"],
                               activation_unix_nanos=activation["activation_unix_nanos"],
                               calibration=inherited.calibration)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="PAC V2.6 seal/activation authority")
    parser.add_argument("command", choices=("status", "write-seal", "write-activation"))
    args = parser.parse_args(argv)
    if args.command == "write-seal":
        result = write_seal()
    elif args.command == "write-activation":
        result = write_activation()
    else:
        result = {"seal": SEAL.exists() and _anchored(SEAL),
                  "activation": ACTIVATION.exists() and _anchored(ACTIVATION)}
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
