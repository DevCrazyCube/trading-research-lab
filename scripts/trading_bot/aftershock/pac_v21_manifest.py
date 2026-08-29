#!/usr/bin/env python3
"""PAC V2.1 closed seal, campaign authority, activation, and runtime proof.

Writing a seal or campaign does not send anything.  Activation is set-once, follows committed campaign
and evidence artifacts, repeats an independent finalized RPC reread, and can authorize only the isolated
paper-scenario runner.  There is no wallet/order authority in this module.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import subprocess
import time

from .execution import RefusedExecution
from . import pac_v21_attestation as attestation
from . import pac_v21_calibration as calibration
from . import pac_v21_evidence as evidence
from . import pac_v21_runner as runner
from . import pac_v21_send as sender


INSTRUMENT = "AFTERSHOCK_PAC_V21"
ROOT = pathlib.Path(__file__).resolve().parents[3]
RESEARCH = ROOT / "research" / "trading_bot" / "aftershock"
PREREG = RESEARCH / f"{INSTRUMENT}_PREREGISTRATION.md"
FROZEN = RESEARCH / f"{INSTRUMENT}_FROZEN.json"
SEAL = RESEARCH / f"{INSTRUMENT}_SEAL.json"
CAMPAIGN = RESEARCH / f"{INSTRUMENT}_CALIBRATION_CAMPAIGN.json"
JOURNAL = RESEARCH / f"{INSTRUMENT}_CALIBRATION_JOURNAL.json"
SAMPLES = RESEARCH / f"{INSTRUMENT}_CALIBRATION_SAMPLES.jsonl"
ATTESTATIONS = RESEARCH / f"{INSTRUMENT}_ATTESTATIONS.jsonl"
ACTIVATION = RESEARCH / f"{INSTRUMENT}_ACTIVATION.json"
MAX_ACTIVATION_LAG_NANOS = 21_600_000_000_000

DEPENDENCY_PATHS = (
    "research/pump_amm_idl_9c82f61.json",
    "research/pump_idl_9c82f61.json",
    "research/trading_bot/aftershock/PAC_V21_PROCESSED_CALIBRATION_DESIGN.md",
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
    "scripts/trading_bot/aftershock/pac_v2_policy.py",
    "scripts/trading_bot/aftershock/pac_v2_runner.py",
    "scripts/trading_bot/aftershock/pac_v2_send.py",
    "scripts/trading_bot/aftershock/pac_v2_snapshot.py",
    "scripts/trading_bot/aftershock/pac_v21_attestation.py",
    "scripts/trading_bot/aftershock/pac_v21_attestation_selftest.py",
    "scripts/trading_bot/aftershock/pac_v21_calibration.py",
    "scripts/trading_bot/aftershock/pac_v21_calibration_selftest.py",
    "scripts/trading_bot/aftershock/pac_v21_detector.py",
    "scripts/trading_bot/aftershock/pac_v21_detector_selftest.py",
    "scripts/trading_bot/aftershock/pac_v21_evidence.py",
    "scripts/trading_bot/aftershock/pac_v21_evidence_selftest.py",
    "scripts/trading_bot/aftershock/pac_v21_manifest.py",
    "scripts/trading_bot/aftershock/pac_v21_manifest_selftest.py",
    "scripts/trading_bot/aftershock/pac_v21_processed_observer.py",
    "scripts/trading_bot/aftershock/pac_v21_processed_observer_selftest.py",
    "scripts/trading_bot/aftershock/pac_v21_runner.py",
    "scripts/trading_bot/aftershock/pac_v21_runner_selftest.py",
    "scripts/trading_bot/aftershock/pac_v21_send.py",
    "scripts/trading_bot/aftershock/pac_v21_send_selftest.py",
    "scripts/trading_bot/aftershock/solusd_recorder.py",
    "scripts/trading_bot/sniper/data/_common.py",
    "scripts/trading_bot/sniper/types.py",
)


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _repo_file(relative: str) -> pathlib.Path:
    if not isinstance(relative, str) or not relative or pathlib.PurePosixPath(relative).is_absolute():
        raise RefusedExecution("PAC V2.1 dependency path is not repository-relative")
    path = (ROOT / relative).resolve()
    try:
        path.relative_to(ROOT)
    except ValueError as exc:
        raise RefusedExecution("PAC V2.1 dependency escapes the repository") from exc
    if not path.is_file():
        raise RefusedExecution(f"PAC V2.1 dependency is missing: {relative}")
    return path


def _json(path: pathlib.Path) -> dict:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise RefusedExecution(f"PAC V2.1 cannot parse {path.name}") from exc
    if not isinstance(value, dict):
        raise RefusedExecution(f"PAC V2.1 {path.name} is not an object")
    return value


def _exclusive_json(path: pathlib.Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, indent=2, sort_keys=True).encode() + b"\n"
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        if os.write(descriptor, payload) != len(payload):
            raise OSError("short authority write")
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
        tracked = subprocess.run(
            ["git", "ls-files", "--error-unmatch", "--", relative], cwd=ROOT,
            capture_output=True, timeout=10, check=False)
        clean = subprocess.run(
            ["git", "diff", "--quiet", "HEAD", "--", relative], cwd=ROOT,
            capture_output=True, timeout=10, check=False)
        return tracked.returncode == 0 and clean.returncode == 0
    except (OSError, subprocess.SubprocessError, ValueError):
        return False


def _git_commit(path: pathlib.Path) -> str:
    try:
        relative = str(path.resolve().relative_to(ROOT))
        result = subprocess.run(
            ["git", "log", "-1", "--format=%H", "--", relative], cwd=ROOT,
            capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise RefusedExecution("PAC V2.1 cannot resolve artifact commit ancestry") from exc
    commit = result.stdout.strip()
    if result.returncode != 0 or len(commit) != 40:
        raise RefusedExecution("PAC V2.1 evidence artifact is not git-anchored")
    return commit


def _must_precede(first: pathlib.Path, later: tuple[pathlib.Path, ...], *, label: str) -> None:
    first_commit = _git_commit(first)
    for path in later:
        later_commit = _git_commit(path)
        if first_commit == later_commit:
            raise RefusedExecution(f"PAC V2.1 {label} artifacts share one commit")
        result = subprocess.run(
            ["git", "merge-base", "--is-ancestor", first_commit, later_commit],
            cwd=ROOT, capture_output=True, timeout=10, check=False)
        if result.returncode != 0:
            raise RefusedExecution(f"PAC V2.1 {label} commit ancestry fails")


def compute_seal() -> dict:
    if not PREREG.is_file():
        raise RefusedExecution("PAC V2.1 preregistration is missing")
    frozen = _json(FROZEN)
    prereg_sha = _sha(PREREG.read_bytes())
    if (frozen.get("instrument_id") != INSTRUMENT
            or frozen.get("preregistration_sha256") != prereg_sha
            or frozen.get("dependency_paths") != list(DEPENDENCY_PATHS)):
        raise RefusedExecution("PAC V2.1 frozen config does not close its declared inputs")
    dependencies = {relative: _sha(_repo_file(relative).read_bytes())
                    for relative in DEPENDENCY_PATHS}
    body = {
        "schema": 1, "instrument_id": INSTRUMENT,
        "preregistration_sha256": prereg_sha,
        "frozen_canonical_sha256": _sha(_canonical(frozen)),
        "dependency_sha256": dependencies,
    }
    return {**body, "seal_sha256": _sha(_canonical(body))}


def write_seal() -> dict:
    expected = compute_seal()
    if SEAL.exists():
        if _json(SEAL) != expected:
            raise RefusedExecution("PAC V2.1 existing seal differs and is never overwritten")
        return expected
    SEAL.write_text(json.dumps(expected, indent=2, sort_keys=True) + "\n")
    return expected


def verify_seal() -> dict:
    written = _json(SEAL)
    if written != compute_seal():
        raise RefusedExecution("PAC V2.1 seal/dependency closure drifted")
    return written


def anchor_status() -> str:
    try:
        verify_seal()
    except RefusedExecution:
        return "UNSEALED"
    closed = (PREREG, FROZEN, SEAL, *(_repo_file(path) for path in DEPENDENCY_PATHS))
    return "ANCHORED" if all(_git_clean(path) for path in closed) else "UNANCHORED"


def write_campaign(*, calibration_fee_payer: str, submit_origin: str,
                   verification_origin: str, max_transactions: int,
                   max_lamports: int) -> dict:
    seal = verify_seal()
    if anchor_status() != "ANCHORED":
        raise RefusedExecution("PAC V2.1 seal must be git-anchored before campaign creation")
    if CAMPAIGN.exists():
        raise RefusedExecution("PAC V2.1 campaign is set-once")
    try:
        calibration.base._b58decode("calibration fee payer", calibration_fee_payer, exact_length=32)
        submit = calibration._origin("submit origin", submit_origin)
        verify = calibration._origin("verification origin", verification_origin)
    except calibration.CalibrationRefused as exc:
        raise RefusedExecution("PAC V2.1 campaign authority input refuses") from exc
    if submit == verify or type(max_transactions) is not int or max_transactions < 100 \
            or type(max_lamports) is not int or max_lamports <= 0:
        raise RefusedExecution("PAC V2.1 campaign count/budget/origin bounds refuse")
    started = time.time_ns()
    campaign_id = _sha(os.urandom(32) + started.to_bytes(8, "big")
                       + seal["seal_sha256"].encode())
    body = {
        "schema": calibration.CAMPAIGN_SCHEMA, "instrument_id": INSTRUMENT,
        "campaign_id": campaign_id, "seal_sha256": seal["seal_sha256"],
        "calibration_fee_payer": calibration_fee_payer,
        "submit_endpoint_scheme_host": submit,
        "verification_endpoint_scheme_host": verify,
        "started_unix_nanos": started, "max_transactions": max_transactions,
        "max_lamports": max_lamports,
        "poll_interval_nanos": calibration.POLL_INTERVAL_NANOS,
        "processed_deadline_nanos": calibration.PROCESSED_DEADLINE_NANOS,
        "evidence_mode": calibration.EVIDENCE_MODE,
        "transaction_profile": calibration.TRANSACTION_PROFILE,
        "memo_program_id": calibration.MEMO_PROGRAM_ID,
    }
    value = {**body, "campaign_sha256": calibration._sha(body)}
    _exclusive_json(CAMPAIGN, value)
    calibration.load_campaign(CAMPAIGN, expected_sha256=_sha(CAMPAIGN.read_bytes()))
    return value


def _pins(activation: dict) -> evidence.EvidencePins:
    return evidence.EvidencePins(
        activation["campaign_sha256"], activation["journal_sha256"],
        activation["samples_sha256"], activation["attestations_sha256"])


def _load_bound_evidence(activation: dict) -> evidence.Evidence:
    return evidence.load(
        campaign_path=CAMPAIGN, journal_path=JOURNAL, samples_path=SAMPLES,
        attestations_path=ATTESTATIONS, pins=_pins(activation))


def _activation_body(value: dict, seal: dict,
                     closed: evidence.Evidence | None = None) -> None:
    required = {
        "schema", "instrument_id", "seal_sha256", "campaign_sha256", "journal_sha256",
        "samples_sha256", "attestations_sha256", "activation_unix_nanos",
        "processed_p90_nanos", "processed_samples", "failed_samples",
        "live_verification_origin", "live_verification_digest", "activation_sha256",
    }
    if not isinstance(value, dict):
        raise RefusedExecution("PAC V2.1 activation must be an object")
    body = dict(value)
    activation_sha = body.pop("activation_sha256", None)
    if (set(value) != required or value.get("schema") != 1
            or value.get("instrument_id") != INSTRUMENT
            or value.get("seal_sha256") != seal["seal_sha256"]
            or activation_sha != _sha(_canonical(body))):
        raise RefusedExecution("PAC V2.1 activation schema/hash/seal mismatch")
    try:
        for name in ("seal_sha256", "campaign_sha256", "journal_sha256",
                     "samples_sha256", "attestations_sha256",
                     "live_verification_digest"):
            calibration._hash(f"activation {name}", value[name])
        activated = calibration._integer(
            "activation clock", value["activation_unix_nanos"], minimum=1)
        p90 = calibration._integer(
            "activation processed p90", value["processed_p90_nanos"], minimum=1)
        processed = calibration._integer(
            "activation processed count", value["processed_samples"],
            minimum=calibration.MIN_PROCESSED_SAMPLES)
        failed = calibration._integer(
            "activation failed count", value["failed_samples"])
        calibration._origin(
            "activation verification origin", value["live_verification_origin"])
    except calibration.CalibrationRefused as exc:
        raise RefusedExecution("PAC V2.1 activation field validation refuses") from exc
    if p90 > calibration.PROCESSED_DEADLINE_NANOS:
        raise RefusedExecution("PAC V2.1 activation p90 exceeds the frozen deadline")
    if closed is not None:
        latest = max(closed.calibration.last_processed_unix_nanos,
                     closed.calibration.last_attested_unix_nanos)
        if (value["campaign_sha256"] != closed.calibration.campaign_sha256
                or value["journal_sha256"] != closed.journal_sha256
                or value["samples_sha256"] != closed.calibration.artifact_sha256
                or value["attestations_sha256"] != closed.calibration.attestation_sha256
                or p90 != closed.calibration.processed_p90_nanos
                or processed != closed.processed or failed != closed.failed):
            raise RefusedExecution("PAC V2.1 activation differs from closed evidence")
        if (activated <= latest
                or activated - closed.calibration.last_processed_unix_nanos
                > MAX_ACTIVATION_LAG_NANOS):
            raise RefusedExecution("PAC V2.1 activation is stale or non-causal")


def write_activation(*, verification_rpc_url: str, opener=None, resolver=None,
                     rpc_call=None) -> dict:
    seal = verify_seal()
    if anchor_status() != "ANCHORED" or ACTIVATION.exists():
        raise RefusedExecution("PAC V2.1 activation requires anchored seal and set-once target")
    artifacts = (CAMPAIGN, JOURNAL, SAMPLES, ATTESTATIONS)
    if not all(_git_clean(path) for path in artifacts):
        raise RefusedExecution("PAC V2.1 campaign/evidence artifacts must be committed and clean")
    campaign_sha, journal_sha, samples_sha, attest_sha = (
        _sha(path.read_bytes()) for path in artifacts)
    _must_precede(CAMPAIGN, (JOURNAL, SAMPLES, ATTESTATIONS), label="campaign-before-evidence")
    closed = evidence.load(
        campaign_path=CAMPAIGN, journal_path=JOURNAL, samples_path=SAMPLES,
        attestations_path=ATTESTATIONS,
        pins=evidence.EvidencePins(campaign_sha, journal_sha, samples_sha, attest_sha))
    campaign = calibration.load_campaign(CAMPAIGN, expected_sha256=campaign_sha)
    if campaign.seal_sha256 != seal["seal_sha256"]:
        raise RefusedExecution("PAC V2.1 campaign targets another seal")
    journal = sender.load_journal(JOURNAL, campaign)
    live = attestation.live_verify(
        evidence=journal, campaign=campaign, rpc_url=verification_rpc_url,
        opener=opener, resolver=resolver, rpc_call=rpc_call)
    if live.get("verified") != closed.processed:
        raise RefusedExecution("PAC V2.1 live verification did not cover every processed sample")
    activated = time.time_ns()
    latest = max(closed.calibration.last_processed_unix_nanos,
                 closed.calibration.last_attested_unix_nanos)
    if activated <= latest or activated - closed.calibration.last_processed_unix_nanos \
            > MAX_ACTIVATION_LAG_NANOS:
        raise RefusedExecution("PAC V2.1 calibration is stale/non-causal at activation")
    body = {
        "schema": 1, "instrument_id": INSTRUMENT, "seal_sha256": seal["seal_sha256"],
        "campaign_sha256": campaign_sha, "journal_sha256": journal_sha,
        "samples_sha256": samples_sha, "attestations_sha256": attest_sha,
        "activation_unix_nanos": activated,
        "processed_p90_nanos": closed.calibration.processed_p90_nanos,
        "processed_samples": closed.processed, "failed_samples": closed.failed,
        "live_verification_origin": live["verification_origin"],
        "live_verification_digest": live["digest"],
    }
    value = {**body, "activation_sha256": _sha(_canonical(body))}
    _activation_body(value, seal, closed)
    _exclusive_json(ACTIVATION, value)
    return value


def load_runtime_proof(*, verification_rpc_url: str | None = None,
                       opener=None, resolver=None, rpc_call=None) -> runner.RuntimeProof:
    seal = verify_seal()
    if anchor_status() != "ANCHORED" or not _git_clean(ACTIVATION):
        raise RefusedExecution("PAC V2.1 runtime authority is not anchored")
    activation = _json(ACTIVATION)
    _activation_body(activation, seal)
    artifacts = (CAMPAIGN, JOURNAL, SAMPLES, ATTESTATIONS)
    if not all(_git_clean(path) for path in artifacts):
        raise RefusedExecution("PAC V2.1 runtime evidence artifact drifted")
    _must_precede(CAMPAIGN, (JOURNAL, SAMPLES, ATTESTATIONS), label="campaign-before-evidence")
    _must_precede(JOURNAL, (ACTIVATION,), label="evidence-before-activation")
    _must_precede(SAMPLES, (ACTIVATION,), label="evidence-before-activation")
    _must_precede(ATTESTATIONS, (ACTIVATION,), label="evidence-before-activation")
    closed = _load_bound_evidence(activation)
    _activation_body(activation, seal, closed)
    campaign = calibration.load_campaign(CAMPAIGN, expected_sha256=activation["campaign_sha256"])
    if campaign.seal_sha256 != seal["seal_sha256"]:
        raise RefusedExecution("PAC V2.1 runtime campaign targets another seal")
    journal = sender.load_journal(JOURNAL, campaign)
    rpc_url = verification_rpc_url or os.environ.get(attestation.ENV_NAME)
    if not rpc_url:
        raise RefusedExecution(f"PAC V2.1 runtime requires {attestation.ENV_NAME}")
    live = attestation.live_verify(
        evidence=journal, campaign=campaign, rpc_url=rpc_url,
        opener=opener, resolver=resolver, rpc_call=rpc_call)
    if (live.get("verified") != closed.processed
            or live["verification_origin"] != activation["live_verification_origin"]
            or live["digest"] != activation["live_verification_digest"]
            or closed.calibration.processed_p90_nanos != activation["processed_p90_nanos"]
            or closed.processed != activation["processed_samples"]
            or closed.failed != activation["failed_samples"]):
        raise RefusedExecution("PAC V2.1 activation/evidence/live verification binding differs")
    return runner.RuntimeProof(
        seal["seal_sha256"], activation["activation_unix_nanos"], closed.calibration)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="PAC V2.1 seal/campaign/activation authority")
    parser.add_argument("command", choices=("status", "write-seal"))
    args = parser.parse_args(argv)
    if args.command == "write-seal":
        print(json.dumps(write_seal(), sort_keys=True))
    else:
        print(json.dumps({"seal": anchor_status(),
                          "campaign": CAMPAIGN.exists(), "activation": ACTIVATION.exists()},
                         sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
