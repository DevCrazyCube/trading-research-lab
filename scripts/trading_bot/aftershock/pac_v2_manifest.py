#!/usr/bin/env python3
"""PAC V2 closed seal, calibrated activation, and runtime authority.

The seal is not evidence until every byte in its closure is committed and clean.  Activation is set
once with an internal clock and pins one authentic calibration artifact by whole-file hash.  Runtime
loading repeats every check; command-line latency values do not exist.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import subprocess
import time
import urllib.parse

from .execution import RefusedExecution
from .pac_v2_calibration import (
    ArtifactPins,
    CalibrationRefused,
    load as load_calibration,
    load_campaign,
)
from .pac_v2_runner import RuntimeProof


INSTRUMENT = "AFTERSHOCK_PAC_V2"
ROOT = pathlib.Path(__file__).resolve().parents[3]
RESEARCH = ROOT / "research" / "trading_bot" / "aftershock"
PREREG = RESEARCH / f"{INSTRUMENT}_PREREGISTRATION.md"
FROZEN = RESEARCH / f"{INSTRUMENT}_FROZEN.json"
SEAL = RESEARCH / f"{INSTRUMENT}_SEAL.json"
ACTIVATION = RESEARCH / f"{INSTRUMENT}_ACTIVATION.json"
CAMPAIGN = RESEARCH / f"{INSTRUMENT}_CALIBRATION_CAMPAIGN.json"
MAX_ACTIVATION_LAG_NANOS = 21_600_000_000_000  # six hours after the latest landed sample

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
    "scripts/trading_bot/aftershock/pac_v2_calibration_attestation.py",
    "scripts/trading_bot/aftershock/pac_v2_detector.py",
    "scripts/trading_bot/aftershock/pac_v2_feed.py",
    "scripts/trading_bot/aftershock/pac_v2_manifest.py",
    "scripts/trading_bot/aftershock/pac_v2_policy.py",
    "scripts/trading_bot/aftershock/pac_v2_runner.py",
    "scripts/trading_bot/aftershock/pac_v2_selftest.py",
    "scripts/trading_bot/aftershock/pac_v2_snapshot.py",
    "scripts/trading_bot/aftershock/pac_v2_status.py",
    "scripts/trading_bot/aftershock/pac_v2_supervisor.py",
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


def _scheme_host(value: str) -> str:
    if not isinstance(value, str):
        raise RefusedExecution("PAC V2 campaign endpoint origin must be text")
    parsed = urllib.parse.urlsplit(value)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.path not in {"", "/"} or parsed.query or parsed.fragment):
        raise RefusedExecution("PAC V2 campaign endpoint must be an HTTPS scheme/host origin")
    port = f":{parsed.port}" if parsed.port is not None else ""
    return f"https://{parsed.hostname}{port}"


def _exclusive_durable_json(path: pathlib.Path, event: dict) -> None:
    """Create a set-once authority record and durably publish its directory entry."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(event, indent=2, sort_keys=True) + "\n").encode()
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        written = os.write(descriptor, payload)
        if written != len(payload):
            raise OSError(f"short authority write {written}/{len(payload)}")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    directory = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


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


def _git_commit(path: pathlib.Path) -> str:
    try:
        relative = str(path.resolve().relative_to(ROOT))
        result = subprocess.run(
            ["git", "log", "-1", "--format=%H", "--", relative],
            cwd=ROOT, capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise RefusedExecution("PAC V2 cannot resolve artifact commit ancestry") from exc
    commit = result.stdout.strip()
    if result.returncode != 0 or len(commit) != 40:
        raise RefusedExecution("PAC V2 evidence artifact is not git-anchored")
    return commit


def _require_campaign_precedes_evidence(
        campaign_path: pathlib.Path, calibration_path: pathlib.Path,
        attestation_path: pathlib.Path) -> None:
    campaign_commit = _git_commit(campaign_path)
    for path in (calibration_path, attestation_path):
        evidence_commit = _git_commit(path)
        if campaign_commit == evidence_commit:
            raise RefusedExecution("PAC V2 campaign must be anchored before calibration evidence")
        result = subprocess.run(
            ["git", "merge-base", "--is-ancestor", campaign_commit, evidence_commit],
            cwd=ROOT, capture_output=True, timeout=10, check=False)
        if result.returncode != 0:
            raise RefusedExecution("PAC V2 campaign commit is not an ancestor of calibration evidence")


def _require_evidence_precedes_activation(
        calibration_path: pathlib.Path, attestation_path: pathlib.Path) -> None:
    activation_commit = _git_commit(ACTIVATION)
    for path in (calibration_path, attestation_path):
        evidence_commit = _git_commit(path)
        if evidence_commit == activation_commit:
            raise RefusedExecution("PAC V2 activation must be anchored after calibration evidence")
        result = subprocess.run(
            ["git", "merge-base", "--is-ancestor", evidence_commit, activation_commit],
            cwd=ROOT, capture_output=True, timeout=10, check=False)
        if result.returncode != 0:
            raise RefusedExecution("PAC V2 evidence commit is not an ancestor of activation")


def _require_fresh_activation(activation_unix_nanos: int, calibration) -> None:
    if type(activation_unix_nanos) is not int:
        raise RefusedExecution("PAC V2 activation clock is not exact")
    if activation_unix_nanos <= max(
            calibration.last_land_unix_nanos, calibration.last_attested_unix_nanos):
        raise RefusedExecution("PAC V2 activation does not follow calibration and attestation")
    if activation_unix_nanos - calibration.last_land_unix_nanos > MAX_ACTIVATION_LAG_NANOS:
        raise RefusedExecution("PAC V2 calibration is stale at activation")


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


def write_campaign(*, calibration_fee_payer: str, submit_endpoint_scheme_host: str,
                   verification_endpoint_scheme_host: str) -> dict:
    """Create the set-once pre-sampling manifest. This does not create or use a wallet."""
    seal = verify_seal()
    if anchor_status() != "ANCHORED":
        raise RefusedExecution("PAC V2 repaired seal must be anchored before a campaign")
    if CAMPAIGN.exists():
        raise RefusedExecution("PAC V2 calibration campaign is set-once")
    submit = _scheme_host(submit_endpoint_scheme_host)
    verify = _scheme_host(verification_endpoint_scheme_host)
    if submit == verify:
        raise RefusedExecution("PAC V2 submit and verification origins must differ")
    started = time.time_ns()
    campaign_id = _sha(os.urandom(32) + started.to_bytes(8, "big") + seal["seal_sha256"].encode())
    body = {
        "schema": 1, "instrument_id": INSTRUMENT, "campaign_id": campaign_id,
        "seal_sha256": seal["seal_sha256"],
        "calibration_fee_payer": calibration_fee_payer,
        "submit_endpoint_scheme_host": submit,
        "verification_endpoint_scheme_host": verify,
        "started_unix_nanos": started,
        "evidence_mode": "LOCAL_MONOTONIC_PLUS_FINALIZED_INDEPENDENT_RPC",
        "transaction_profile": "LEGACY_SINGLE_SIGNER_CAMPAIGN_MEMO_ONLY",
        "memo_program_id": "MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr",
    }
    event = {**body, "campaign_sha256": _sha(_canonical(body))}
    # Run the complete schema/base58/source validator before the exclusive write.
    temporary = CAMPAIGN.with_name(f".{CAMPAIGN.name}.{os.getpid()}.validate")
    try:
        temporary.write_text(json.dumps(event, sort_keys=True) + "\n")
        load_campaign(temporary, expected_sha256=_sha(temporary.read_bytes()))
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
    _exclusive_durable_json(CAMPAIGN, event)
    return event


def write_activation(*, calibration_path: pathlib.Path, attestation_path: pathlib.Path,
                     campaign_path: pathlib.Path) -> dict:
    seal = verify_seal()
    if anchor_status() != "ANCHORED":
        raise RefusedExecution("PAC V2 seal is unanchored; activation prohibited")
    if ACTIVATION.exists():
        raise RefusedExecution("PAC V2 activation is set-once")
    try:
        paths = tuple(pathlib.Path(path).resolve() for path in (
            campaign_path, calibration_path, attestation_path))
        relatives = tuple(str(path.relative_to(ROOT)) for path in paths)
        if not all(_git_clean(path) for path in paths):
            raise RefusedExecution("PAC V2 campaign/calibration/attestation must be git-anchored")
        _require_campaign_precedes_evidence(*paths)
        pins = ArtifactPins(
            campaign_sha256=_sha(paths[0].read_bytes()),
            calibration_sha256=_sha(paths[1].read_bytes()),
            attestation_sha256=_sha(paths[2].read_bytes()))
        campaign = load_campaign(paths[0], expected_sha256=pins.campaign_sha256)
        calibration = load_calibration(
            paths[1], attestation_path=paths[2], campaign_path=paths[0], pins=pins)
    except (OSError, ValueError, CalibrationRefused) as exc:
        raise RefusedExecution(f"PAC V2 calibration refused: {exc}") from exc
    if campaign.seal_sha256 != seal["seal_sha256"]:
        raise RefusedExecution("PAC V2 calibration campaign references another seal")
    recorded = time.time_ns()
    _require_fresh_activation(recorded, calibration)
    body = {"schema": 1, "instrument_id": INSTRUMENT, "seal_sha256": seal["seal_sha256"],
            "campaign_path": relatives[0], "campaign_sha256": pins.campaign_sha256,
            "calibration_path": relatives[1], "calibration_sha256": pins.calibration_sha256,
            "attestation_path": relatives[2], "attestation_sha256": pins.attestation_sha256,
            "activation_unix_nanos": recorded}
    event = {**body, "activation_sha256": _sha(_canonical(body))}
    _exclusive_durable_json(ACTIVATION, event)
    return event


def load_runtime_proof() -> RuntimeProof:
    seal = verify_seal()
    if anchor_status() != "ANCHORED":
        raise RefusedExecution("PAC V2 seal is not git-anchored")
    if not ACTIVATION.is_file() or not _git_clean(ACTIVATION):
        raise RefusedExecution("PAC V2 calibrated activation is absent or unanchored")
    activation = _json(ACTIVATION)
    stored = activation.get("activation_sha256"); body = dict(activation); body.pop("activation_sha256", None)
    required = {"schema", "instrument_id", "seal_sha256",
                "campaign_path", "campaign_sha256",
                "calibration_path", "calibration_sha256",
                "attestation_path", "attestation_sha256", "activation_unix_nanos"}
    if (set(body) != required or stored != _sha(_canonical(body)) or body["schema"] != 1
            or body["instrument_id"] != INSTRUMENT or body["seal_sha256"] != seal["seal_sha256"]):
        raise RefusedExecution("PAC V2 activation is malformed, forged, or references another seal")
    campaign_path = _repo_file(body["campaign_path"])
    calibration_path = _repo_file(body["calibration_path"])
    attestation_path = _repo_file(body["attestation_path"])
    if not all(_git_clean(path) for path in (
            campaign_path, calibration_path, attestation_path)):
        raise RefusedExecution("PAC V2 activation evidence is no longer git-clean")
    _require_campaign_precedes_evidence(campaign_path, calibration_path, attestation_path)
    _require_evidence_precedes_activation(calibration_path, attestation_path)
    pins = ArtifactPins(
        campaign_sha256=body["campaign_sha256"],
        calibration_sha256=body["calibration_sha256"],
        attestation_sha256=body["attestation_sha256"])
    try:
        campaign = load_campaign(campaign_path, expected_sha256=pins.campaign_sha256)
        calibration = load_calibration(
            calibration_path, attestation_path=attestation_path,
            campaign_path=campaign_path, pins=pins)
    except CalibrationRefused as exc:
        raise RefusedExecution(f"PAC V2 calibration refused: {exc}") from exc
    if campaign.seal_sha256 != seal["seal_sha256"]:
        raise RefusedExecution("PAC V2 activation campaign references another seal")
    _require_fresh_activation(body["activation_unix_nanos"], calibration)
    return RuntimeProof(seal["seal_sha256"], body["activation_unix_nanos"], calibration)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="PAC V2 campaign/seal/activation authority")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    campaign_parser = sub.add_parser("campaign")
    campaign_parser.add_argument("--fee-payer", required=True)
    campaign_parser.add_argument("--submit-origin", required=True)
    campaign_parser.add_argument("--verification-origin", required=True)
    activation_parser = sub.add_parser("activate")
    activation_parser.add_argument("--campaign", required=True, type=pathlib.Path)
    activation_parser.add_argument("--calibration", required=True, type=pathlib.Path)
    activation_parser.add_argument("--attestation", required=True, type=pathlib.Path)
    args = parser.parse_args(argv)
    if args.command == "status":
        try:
            proof = load_runtime_proof()
        except RefusedExecution as exc:
            print(json.dumps({
                "seal": anchor_status(), "activation": "ABSENT_OR_REFUSED",
                "reason": str(exc)[:240]}, sort_keys=True))
            return 2
        print(json.dumps({
            "seal": anchor_status(), "activation": "ANCHORED",
            "campaign_id": proof.calibration.campaign_id,
            "landed_samples": proof.calibration.landed_samples,
            "reaction_p90_nanos": proof.calibration.reaction_p90_nanos,
        }, sort_keys=True))
        return 0
    try:
        if args.command == "campaign":
            event = write_campaign(
                calibration_fee_payer=args.fee_payer,
                submit_endpoint_scheme_host=args.submit_origin,
                verification_endpoint_scheme_host=args.verification_origin)
        else:
            event = write_activation(
                campaign_path=args.campaign, calibration_path=args.calibration,
                attestation_path=args.attestation)
    except RefusedExecution as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc)[:240]}, sort_keys=True))
        return 2
    print(json.dumps(event, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
