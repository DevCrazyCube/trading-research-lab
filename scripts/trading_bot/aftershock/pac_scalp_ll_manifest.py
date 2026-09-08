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
SPEND_HIGH_WATER = RAW_ROOT / "spend_high_water.jsonl"
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
        yield {"descriptor": descriptor, "path": str(CAMPAIGN_LOCK.resolve())}
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def require_campaign_lock(token: object) -> None:
    """Prove the sender owns a live OS lock, not a module-global capability object."""
    if (not isinstance(token, dict) or set(token) != {"descriptor", "path"}
            or token.get("path") != str(CAMPAIGN_LOCK.resolve())
            or type(token.get("descriptor")) is not int):
        raise RefusedExecution("PAC_SCALP_LL broadcast lacks an active campaign lock")
    descriptor = token["descriptor"]
    try:
        observed = os.fstat(descriptor)
        expected = CAMPAIGN_LOCK.stat()
        if (observed.st_dev, observed.st_ino) != (expected.st_dev, expected.st_ino):
            raise RefusedExecution("PAC_SCALP_LL campaign lock inode differs")
        # Reasserting LOCK_EX on the same open description is harmless; a caller cannot pass a
        # closed/arbitrary descriptor and pretend the manifest-owned lock is held.
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (OSError, BlockingIOError) as exc:
        raise RefusedExecution("PAC_SCALP_LL campaign lock is not live") from exc


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
    if SPEND_HIGH_WATER.exists():
        rows = _read_spend_high_water()
        if len(rows) != 1 or rows[0]["attempts"] != 0 \
                or rows[0]["journal_sha256"] != genesis["journal_sha256"]:
            raise RefusedExecution("PAC_SCALP_LL pre-authority spend high-water is not genesis")
    else:
        _append_spend_high_water(genesis)
    high_water_sha = _sha_bytes(SPEND_HIGH_WATER.read_bytes())
    high_water_head = _read_spend_high_water()[-1]["record_sha256"]
    body = {"schema": 1, "instrument_id": INSTRUMENT,
            "campaign_sha256": campaign.campaign_sha256,
            "max_lamports": campaign.max_lamports,
            "journal_genesis_sha256": _sha_bytes(RAW_JOURNAL.read_bytes()),
            "spend_high_water_genesis_file_sha256": high_water_sha,
            "spend_high_water_genesis_record_sha256": high_water_head,
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
            or value.get("boundary") != "SET_ONCE_CALIBRATION_SPEND_CAP_NO_TRADING"
            or not isinstance(value.get("spend_high_water_genesis_file_sha256"), str)
            or not isinstance(value.get("spend_high_water_genesis_record_sha256"), str)):
        raise RefusedExecution("PAC_SCALP_LL spend authority content refuses")
    if not RAW_JOURNAL.exists():
        raise RefusedExecution("PAC_SCALP_LL campaign journal is missing after spend authorization")
    journal = calibration.load_journal(RAW_JOURNAL, campaign)
    rows = _read_spend_high_water()
    first, last = rows[0], rows[-1]
    if (_sha_bytes((_canonical(first) + b"\n"))
            != value["spend_high_water_genesis_file_sha256"]
            or first["record_sha256"] != value["spend_high_water_genesis_record_sha256"]):
        raise RefusedExecution("PAC_SCALP_LL journal differs from irreversible spend high-water")
    _assert_spend_high_water(journal, rows)
    return value


def _assert_spend_high_water(journal: dict, rows: list[dict]) -> None:
    last = rows[-1] if rows else None
    if (last is None or last["journal_sha256"] != journal.get("journal_sha256")
            or last["attempts"] != len(journal.get("attempts", []))
            or last["reserved_lamports"]
            != sum(row.get("reserved_lamports", -1) for row in journal.get("attempts", []))):
        raise RefusedExecution("PAC_SCALP_LL journal differs from irreversible spend high-water")


def _read_spend_high_water(path: pathlib.Path = SPEND_HIGH_WATER) -> list[dict]:
    previous = "0" * 64; rows = []
    try:
        lines = path.read_text().splitlines()
    except OSError as exc:
        raise RefusedExecution("PAC_SCALP_LL spend high-water is missing") from exc
    for sequence, line in enumerate(lines, 1):
        try:
            row = json.loads(line); body = dict(row); observed = body.pop("record_sha256", None)
        except (json.JSONDecodeError, TypeError) as exc:
            raise RefusedExecution("PAC_SCALP_LL spend high-water is malformed") from exc
        if (set(body) != {"schema", "instrument_id", "sequence", "previous_record_sha256",
                         "campaign_sha256", "journal_sha256", "attempts", "reserved_lamports"}
                or body["schema"] != 1 or body["instrument_id"] != INSTRUMENT
                or body["sequence"] != sequence or body["previous_record_sha256"] != previous
                or observed != _sha_bytes(_canonical(body))
                or type(body["attempts"]) is not int or body["attempts"] < 0
                or type(body["reserved_lamports"]) is not int or body["reserved_lamports"] < 0
                or (rows and (body["attempts"] < rows[-1]["attempts"]
                              or body["reserved_lamports"] < rows[-1]["reserved_lamports"]))):
            raise RefusedExecution("PAC_SCALP_LL spend high-water chain refuses")
        rows.append(row); previous = observed
    if not rows:
        raise RefusedExecution("PAC_SCALP_LL spend high-water is empty")
    return rows


def _append_spend_high_water(journal: dict, path: pathlib.Path = SPEND_HIGH_WATER) -> dict:
    rows = _read_spend_high_water(path) if path.exists() else []
    previous = rows[-1]["record_sha256"] if rows else "0" * 64
    body = {"schema": 1, "instrument_id": INSTRUMENT, "sequence": len(rows) + 1,
            "previous_record_sha256": previous,
            "campaign_sha256": journal["campaign_sha256"],
            "journal_sha256": journal["journal_sha256"],
            "attempts": len(journal["attempts"]),
            "reserved_lamports": sum(row["reserved_lamports"] for row in journal["attempts"])}
    row = {**body, "record_sha256": _sha_bytes(_canonical(body))}
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        payload = _canonical(row) + b"\n"
        if os.write(descriptor, payload) != len(payload):
            raise OSError("short spend high-water append")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return row


def checkpoint_spend_journal(campaign: campaigns.Campaign, journal: dict) -> dict:
    """Advance the non-rewritable budget high-water before replacing the convenience journal."""
    require_spend_authority(campaign)
    rows = _read_spend_high_water(); last = rows[-1]
    attempts = len(journal.get("attempts", []))
    reserved = sum(row.get("reserved_lamports", -1) for row in journal.get("attempts", []))
    if (journal.get("campaign_sha256") != campaign.campaign_sha256
            or journal.get("journal_sha256") != campaigns.sha(
                {k: v for k, v in journal.items() if k != "journal_sha256"})
            or attempts < last["attempts"] or reserved < last["reserved_lamports"]):
        raise RefusedExecution("PAC_SCALP_LL spend checkpoint regresses or is malformed")
    return _append_spend_high_water(journal)


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
            absent = (row.get("finalized_slot") is None
                      and row.get("meta_fee_lamports") is None
                      and row.get("finalized_after_local_failure") is False
                      and row.get("blockhash_expired_at_finalized") is True
                      and type(row.get("absence_finalized_slot")) is int
                      and row["absence_finalized_slot"] > 0
                      and isinstance(row.get("expiry_response_sha256"), str)
                      and len(row["expiry_response_sha256"]) == 64)
            late = (type(row.get("finalized_slot")) is int
                    and row["finalized_slot"] > 0
                    and row.get("meta_fee_lamports") == attempt["fee_lamports"]
                    and row.get("finalized_after_local_failure") is True
                    and row.get("blockhash_expired_at_finalized") is False
                    and row.get("absence_finalized_slot") is None
                    and row.get("expiry_response_sha256") is None)
            if not (absent or late):
                raise RefusedExecution("PAC_SCALP_LL failed ITT finalized evidence is inconsistent")
        else:
            raise RefusedExecution("PAC_SCALP_LL activation saw a nonterminal ITT attempt")
    profile = runtime.load(
        RUNTIME_PROFILE, expected_file_sha256=_sha_bytes(RUNTIME_PROFILE.read_bytes()),
        campaign=campaign, attestation=attestation)
    if profile.get("attestation_sha256") != attestation["attestation_sha256"]:
        raise RefusedExecution("PAC_SCALP_LL runtime cost profile lacks this attestation authority")
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
