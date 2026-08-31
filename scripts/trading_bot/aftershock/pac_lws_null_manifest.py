#!/usr/bin/env python3
"""Seal and activation authority for the PAC Launch-Window Sentinel Scalper — NULL arm (paper-only).

The null arm is byte-identical to the veto arm in every runner path except that admission ignores the
B20B screen verdict (still logged as a shadow).  It is a fully independent set-once sealed instrument:
its seal closure differs from the veto arm's only by THIS manifest file, and its activation body pins
``veto_enabled=false``, so the two ledgers isolate the screen's marginal book.

Self-contained (imports no sibling manifest) so its seal has no un-sealed dependency — mirrors
``pac_scalp_arm_manifest`` exactly.  Does NOT write seals/activations (git commits by the main
session); provides the authority + ``compute_seal`` / ``status`` that work against the closure.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import time

from . import pac_lws_common as common
from . import pac_v24_manifest as source
from . import pac_lws_runner as runner


INSTRUMENT = "AFTERSHOCK_PAC_LWS_NULL"
VETO_ENABLED = False
MANIFEST_PATH = "scripts/trading_bot/aftershock/pac_lws_null_manifest.py"

ROOT = common.ROOT
RESEARCH = common.RESEARCH
PREREG = RESEARCH / f"{INSTRUMENT}_PREREGISTRATION.md"
FROZEN = RESEARCH / f"{INSTRUMENT}_FROZEN.json"
SEAL = RESEARCH / f"{INSTRUMENT}_SEAL.json"
ACTIVATION = RESEARCH / f"{INSTRUMENT}_ACTIVATION.json"

_sha = common._sha
_canonical = common._canonical
_json = common._json
_anchored = common._anchored
_commit_for = common._commit_for
RefusedExecution = runner.RefusedExecution


def dependency_paths() -> tuple[str, ...]:
    return common.dependency_paths(manifest_path=MANIFEST_PATH)


def compute_seal() -> dict:
    frozen = _json(FROZEN)
    if frozen.get("instrument_id") != INSTRUMENT:
        raise RefusedExecution("PAC_LWS_NULL frozen instrument mismatch")
    if frozen.get("dependency_paths") != list(dependency_paths()):
        raise RefusedExecution("PAC_LWS_NULL frozen dependency closure mismatch")
    body = {
        "schema": 1, "instrument_id": INSTRUMENT, "veto_enabled": VETO_ENABLED,
        "preregistration_sha256": _sha(PREREG.read_bytes()),
        "frozen_canonical_sha256": _sha(_canonical(frozen)),
        "dependency_sha256": common.dependency_digest(manifest_path=MANIFEST_PATH),
    }
    return {**body, "seal_sha256": _sha(_canonical(body))}


def write_seal() -> dict:
    if SEAL.exists():
        raise RefusedExecution("PAC_LWS_NULL seal is set-once")
    value = compute_seal()
    runner.core._atomic_write(SEAL, value)
    return value


def verify_seal(*, require_anchor: bool = True) -> dict:
    observed = _json(SEAL)
    if observed != compute_seal():
        raise RefusedExecution("PAC_LWS_NULL seal/dependency drift refuses")
    if require_anchor and not all(_anchored(p) for p in (PREREG, FROZEN, SEAL)):
        raise RefusedExecution("PAC_LWS_NULL seal is unanchored or dirty")
    return observed


def write_activation() -> dict:
    if ACTIVATION.exists():
        raise RefusedExecution("PAC_LWS_NULL activation is set-once")
    seal = verify_seal(require_anchor=True)
    inherited = source.load_runtime_proof()
    source_activation = _json(source.ACTIVATION)
    now = time.time_ns()
    body = {
        "schema": 1, "instrument_id": INSTRUMENT, "veto_enabled": VETO_ENABLED,
        "activation_unix_nanos": now, "seal_sha256": seal["seal_sha256"],
        "calibration_inheritance": "V24_EXECUTOR_PATH_BYTE_UNCHANGED_STRATEGY_RESULTS_NOT_INHERITED",
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
            or bool(activation.get("veto_enabled")) != VETO_ENABLED
            or observed_hash != _sha(_canonical(body))
            or activation.get("seal_sha256") != seal["seal_sha256"]
            or not _anchored(ACTIVATION)):
        raise RefusedExecution("PAC_LWS_NULL activation/hash/anchor/veto-flag refuses")
    seal_commit, activation_commit = _commit_for(SEAL), _commit_for(ACTIVATION)
    if (seal_commit == activation_commit
            or common._git("merge-base", "--is-ancestor", seal_commit, activation_commit).returncode != 0):
        raise RefusedExecution("PAC_LWS_NULL activation must be committed after the seal")
    inherited = source.load_runtime_proof()
    source_activation = _json(source.ACTIVATION)
    if (activation.get("source_activation_sha256") != source_activation.get("activation_sha256")
            or activation.get("source_seal_sha256") != inherited.seal_sha256
            or activation.get("processed_p90_nanos") != inherited.calibration.processed_p90_nanos
            or activation.get("calibration_artifact_sha256") != inherited.calibration.artifact_sha256):
        raise RefusedExecution("PAC_LWS_NULL inherited executor calibration drift refuses")
    return runner.RuntimeProof(seal_sha256=seal["seal_sha256"],
                               activation_unix_nanos=activation["activation_unix_nanos"],
                               calibration=inherited.calibration)


def status() -> dict:
    resolvable = True
    reason = None
    try:
        common.dependency_digest(manifest_path=MANIFEST_PATH)
    except RefusedExecution as exc:
        resolvable = False
        reason = str(exc)
    return {
        "instrument_id": INSTRUMENT, "veto_enabled": VETO_ENABLED,
        "dependency_files": len(dependency_paths()),
        "closure_resolvable": resolvable, "closure_reason": reason,
        "seal": SEAL.exists() and _anchored(SEAL),
        "activation": ACTIVATION.exists() and _anchored(ACTIVATION),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="PAC_LWS_NULL (null arm) seal/activation authority")
    parser.add_argument("command", choices=("status", "compute-seal", "write-seal", "write-activation"))
    args = parser.parse_args(argv)
    if args.command == "write-seal":
        result = write_seal()
    elif args.command == "write-activation":
        result = write_activation()
    elif args.command == "compute-seal":
        result = compute_seal()
    else:
        result = status()
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
