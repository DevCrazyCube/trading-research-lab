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
import time

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
RUNTIME_PROFILE = RESEARCH / f"{INSTRUMENT}_RUNTIME_PROFILE.json"
SPEND_AUTHORITY = RESEARCH / f"{INSTRUMENT}_SPEND_AUTHORITY.json"
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
    "scripts/trading_bot/aftershock/pac_scalp_ll_runtime.py",
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


def write_spend_authority() -> dict:
    """Create the set-once, pre-spend journal genesis and its commit-safe authority artifact."""
    from . import pac_scalp_ll_calibration as calibration
    if SPEND_AUTHORITY.exists():
        raise RefusedExecution("PAC_SCALP_LL spend authority is set-once")
    campaign = require_campaign_authority(CAMPAIGN, file_sha256=_sha_bytes(CAMPAIGN.read_bytes()))
    genesis = calibration._new_journal(campaign)
    if RAW_JOURNAL.exists():
        observed = calibration.load_journal(RAW_JOURNAL, campaign)
        if observed != genesis:
            raise RefusedExecution("PAC_SCALP_LL pre-authority journal is not pristine genesis")
    else:
        calibration._atomic_json(RAW_JOURNAL, genesis)
    body = {"schema": 1, "instrument_id": INSTRUMENT,
            "campaign_sha256": campaign.campaign_sha256,
            "max_lamports": campaign.max_lamports,
            "journal_genesis_sha256": _sha_bytes(RAW_JOURNAL.read_bytes()),
            "created_unix_nanos": time.time_ns(),
            "boundary": "SET_ONCE_CALIBRATION_SPEND_CAP_NO_TRADING"}
    value = {**body, "spend_authority_sha256": _sha_bytes(_canonical(body))}
    _atomic(SPEND_AUTHORITY, value)
    return value


def require_spend_authority(campaign: campaigns.Campaign) -> dict:
    from . import pac_scalp_ll_calibration as calibration
    if not _anchored(SPEND_AUTHORITY) or not _strict_ancestor(CAMPAIGN, SPEND_AUTHORITY):
        raise RefusedExecution("PAC_SCALP_LL spend authority must be clean-anchored after campaign")
    value = _json(SPEND_AUTHORITY); body = dict(value)
    observed = body.pop("spend_authority_sha256", None)
    if (observed != _sha_bytes(_canonical(body)) or value.get("schema") != 1
            or value.get("instrument_id") != INSTRUMENT
            or value.get("campaign_sha256") != campaign.campaign_sha256
            or value.get("max_lamports") != campaign.max_lamports
            or value.get("boundary") != "SET_ONCE_CALIBRATION_SPEND_CAP_NO_TRADING"):
        raise RefusedExecution("PAC_SCALP_LL spend authority content refuses")
    if not RAW_JOURNAL.exists():
        raise RefusedExecution("PAC_SCALP_LL campaign journal is missing after spend authorization")
    calibration.load_journal(RAW_JOURNAL, campaign)
    return value


def _evidence_bundle() -> tuple[campaigns.Campaign, dict, dict, dict]:
    """Recompute the complete calibration authority from canonical local+anchored artifacts."""
    from . import pac_scalp_ll_calibration as calibration
    from . import pac_scalp_ll_runtime as runtime
    campaign = require_campaign_authority(CAMPAIGN, file_sha256=_sha_bytes(CAMPAIGN.read_bytes()))
    journal = calibration.load_journal(RAW_JOURNAL, campaign)
    expected_summary = calibration.summary(journal, campaign, raw_path=RAW_JOURNAL)
    summary = _json(CALIBRATION_SUMMARY)
    if summary != expected_summary or summary.get("evidence_status") != "UNATTESTED_LOCAL_COMPLETE":
        raise RefusedExecution("PAC_SCALP_LL calibration summary does not recompute from raw evidence")
    attestation = _json(ATTESTATION)
    attestation_body = dict(attestation); attestation_sha = attestation_body.pop("attestation_sha256", None)
    selected = journal["attempts"][:campaign.samples_per_arm * 2]
    safe = attestation.get("selected_attempts")
    if (attestation_sha != campaigns.sha(attestation_body)
            or attestation.get("instrument_id") != INSTRUMENT
            or attestation.get("campaign_sha256") != campaign.campaign_sha256
            or attestation.get("calibration_summary_sha256") != summary["summary_sha256"]
            or attestation.get("calibration_summary_file_sha256")
            != _sha_bytes(CALIBRATION_SUMMARY.read_bytes())
            or attestation.get("raw_journal_sha256") != _sha_bytes(RAW_JOURNAL.read_bytes())
            or attestation.get("raw_attestation_sha256") != _sha_bytes(RAW_ATTESTATION.read_bytes())
            or attestation.get("evidence_status") != "FINALIZED_ATTESTED_COMPLETE"
            or attestation.get("attested_attempts") != len(selected)
            or attestation.get("attested_pairs") != campaign.samples_per_arm
            or not isinstance(safe, list) or len(safe) != len(selected)):
        raise RefusedExecution("PAC_SCALP_LL finalized attestation authority refuses")
    for attempt, row in zip(selected, safe):
        if (not isinstance(row, dict) or row.get("pair_index") != attempt["pair_index"]
                or row.get("arm") != attempt["arm"]
                or row.get("attempt_sha256") != attempt["attempt_sha256"]
                or row.get("wire_sha256") != attempt["wire_sha256"]):
            raise RefusedExecution("PAC_SCALP_LL attested sample differs from selected ITT attempt")
        if attempt["stage"] == "PROCESSED":
            if (row.get("finalized_slot") != attempt["processed_slot"]
                    or row.get("meta_fee_lamports") != attempt["fee_lamports"]):
                raise RefusedExecution("PAC_SCALP_LL processed attempt lacks exact finalized evidence")
        elif attempt["stage"] == "FAILED":
            if row.get("finalized_slot") is not None or row.get("meta_fee_lamports") is not None:
                raise RefusedExecution("PAC_SCALP_LL failed ITT attempt gained invented finalized evidence")
        else:
            raise RefusedExecution("PAC_SCALP_LL activation saw a nonterminal ITT attempt")
    profile = runtime.load(
        RUNTIME_PROFILE, expected_file_sha256=_sha_bytes(RUNTIME_PROFILE.read_bytes()),
        campaign=campaign)
    return campaign, summary, attestation, profile


def _activation_body(*, activated_unix_nanos: int) -> dict:
    campaign, summary, attestation, profile = _evidence_bundle()
    frozen = _json(FROZEN); rule = frozen.get("calibration", {})
    public = summary["arms"].get("PUBLIC_CONTROL", {})
    intervention = summary["arms"].get("LOW_LATENCY_INTERVENTION", {})
    p_public, p_intervention = public.get("p90_effective_nanos"), intervention.get("p90_effective_nanos")
    if (type(p_public) is not int or type(p_intervention) is not int
            or public.get("paired_samples") != campaign.samples_per_arm
            or intervention.get("paired_samples") != campaign.samples_per_arm
            or p_intervention > rule.get("intervention_p90_max_nanos")
            or p_intervention * rule.get("intervention_to_control_p90_max_den", 0)
            > p_public * rule.get("intervention_to_control_p90_max_num", 0)):
        raise RefusedExecution("PAC_SCALP_LL measured latency failed the frozen promotion threshold")
    arms = {}
    for arm in sorted(("PUBLIC_CONTROL", "LOW_LATENCY_INTERVENTION")):
        value = summary["arms"][arm]
        arms[arm] = {"p90_nanos": value["p90_effective_nanos"],
                     "paired_samples": value["paired_samples"],
                     "failed_samples": value["failed_samples"],
                     "evidence_digest": campaigns.sha({
                         "arm": arm, "summary": summary["summary_sha256"],
                         "attestation": attestation["attestation_sha256"],
                         "p90": value["p90_effective_nanos"]})}
    return {
        "schema": 1, "instrument_id": INSTRUMENT, "activated_unix_nanos": activated_unix_nanos,
        "seal_sha256": verify_seal(require_anchor=True)["seal_sha256"],
        "campaign_sha256": campaign.campaign_sha256,
        "samples_sha256": summary["summary_sha256"],
        "attestations_sha256": attestation["attestation_sha256"],
        "runtime_profile_sha256": profile["runtime_profile_sha256"], "arms": arms,
        "boundary": "PAPER_SCENARIO_ONLY_NO_LIVE_ORDERS",
    }


def write_activation() -> dict:
    if ACTIVATION.exists():
        raise RefusedExecution("PAC_SCALP_LL activation is set-once")
    for artifact in (CALIBRATION_SUMMARY, ATTESTATION, RUNTIME_PROFILE):
        if not _anchored(artifact) or not _strict_ancestor(CAMPAIGN, artifact):
            raise RefusedExecution("PAC_SCALP_LL evidence/runtime must be clean-anchored after campaign")
    body = _activation_body(activated_unix_nanos=time.time_ns())
    value = {**body, "activation_sha256": _sha_bytes(_canonical(body))}
    _atomic(ACTIVATION, value)
    return value


def verify_activation(*, require_anchor: bool = True) -> dict:
    observed = _json(ACTIVATION)
    clock = observed.get("activated_unix_nanos")
    if type(clock) is not int or clock <= 0:
        raise RefusedExecution("PAC_SCALP_LL activation clock refuses")
    body = _activation_body(activated_unix_nanos=clock)
    expected = {**body, "activation_sha256": _sha_bytes(_canonical(body))}
    if observed != expected or (require_anchor and not _anchored(ACTIVATION)):
        raise RefusedExecution("PAC_SCALP_LL activation/evidence drift refuses")
    return observed


def status() -> dict:
    def safe_anchor(path: pathlib.Path) -> bool:
        return path.exists() and _anchored(path)
    return {
        "instrument_id": INSTRUMENT,
        "seal": "ANCHORED" if safe_anchor(SEAL) else ("UNANCHORED" if SEAL.exists() else "ABSENT"),
        "campaign": ("ANCHORED" if safe_anchor(CAMPAIGN)
                     else "UNANCHORED" if CAMPAIGN.exists() else "ABSENT"),
        "spend_authority": ("ANCHORED" if safe_anchor(SPEND_AUTHORITY)
                            else "UNANCHORED" if SPEND_AUTHORITY.exists() else "ABSENT"),
        "calibration": ("ANCHORED" if safe_anchor(CALIBRATION_SUMMARY)
                        else "UNANCHORED" if CALIBRATION_SUMMARY.exists() else "ABSENT"),
        "attestation": ("ANCHORED" if safe_anchor(ATTESTATION)
                        else "UNANCHORED" if ATTESTATION.exists() else "ABSENT"),
        "runtime_profile": ("ANCHORED" if safe_anchor(RUNTIME_PROFILE)
                            else "UNANCHORED" if RUNTIME_PROFILE.exists() else "ABSENT"),
        "activation": ("ANCHORED" if safe_anchor(ACTIVATION)
                       else "UNANCHORED" if ACTIVATION.exists() else "ABSENT"),
        "authority": "DEFAULT_OFF_NO_BROADCAST" if not safe_anchor(CAMPAIGN)
        else "CAMPAIGN_ANCHORED_BROADCAST_REQUIRES_EXPLICIT_FLAG",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="PAC_SCALP_LL manifest")
    parser.add_argument("command", choices=(
        "status", "write-seal", "write-spend-authority", "write-activation"))
    args = parser.parse_args(argv)
    result = (write_seal() if args.command == "write-seal" else
              write_spend_authority() if args.command == "write-spend-authority" else
              write_activation() if args.command == "write-activation" else status())
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
