#!/usr/bin/env python3
"""Default-OFF matched submit-latency campaign for PAC_SCALP_LL.

This executable can only emit the exact priority+tip+memo transaction parsed by
``pac_scalp_ll_tx.verify``.  Raw signatures/wires stay in a local journal.  Its exported summary is
credential- and wallet-safe and remains ``UNATTESTED_LOCAL`` until an independent finalized attester
verifies every selected sample.  No Pump program/account can enter this transaction profile.
"""
from __future__ import annotations

import argparse
import base64
from copy import deepcopy
import hashlib
import json
import math
import os
import pathlib
import stat
import tempfile
import time
import urllib.error
import urllib.request

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from .execution import RefusedExecution
from . import pac_scalp_ll_campaign as campaigns
from . import pac_scalp_ll_route as routes
from . import pac_scalp_ll_tx as tx
from . import pac_v2_calibration as solana


JOURNAL_SCHEMA = 1
ATTEMPT_SCHEMA = 1
SUMMARY_SCHEMA = 1
TIMEOUT_SECONDS = 20.0
BOOT_ID_PATH = pathlib.Path("/proc/sys/kernel/random/boot_id")
_BROADCAST_CAPABILITY = object()


class CalibrationRefused(RefusedExecution):
    pass


def _load_fee_payer(path: pathlib.Path) -> tuple[Ed25519PrivateKey, str]:
    key_path = pathlib.Path(path)
    try:
        metadata = key_path.lstat()
    except OSError as exc:
        raise CalibrationRefused("calibration fee payer is unavailable") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode) \
            or stat.S_IMODE(metadata.st_mode) != 0o600:
        raise CalibrationRefused("calibration fee payer must be a regular 0600 non-symlink")
    try:
        payload = key_path.read_bytes().strip()
    except OSError as exc:
        raise CalibrationRefused("calibration fee payer is unavailable") from exc
    declared_public = None
    if payload[:1] == b"[":
        try:
            values = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise CalibrationRefused("calibration fee payer JSON is invalid") from exc
        if (not isinstance(values, list) or len(values) not in {32, 64}
                or any(type(value) is not int or not 0 <= value <= 255 for value in values)):
            raise CalibrationRefused("calibration fee payer must contain 32/64 bytes")
        raw = bytes(values)
    elif len(payload) in {32, 64}:
        raw = payload
    else:
        raise CalibrationRefused("calibration fee payer encoding is invalid")
    if len(raw) == 64:
        declared_public = raw[32:]
    try:
        private = Ed25519PrivateKey.from_private_bytes(raw[:32])
    except ValueError as exc:
        raise CalibrationRefused("calibration fee payer seed is invalid") from exc
    public = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    if declared_public is not None and declared_public != public:
        raise CalibrationRefused("calibration fee payer public half mismatches its seed")
    return private, solana._b58encode(public)


def _atomic_json(path: pathlib.Path, value: object) -> None:
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        dir=path.parent, prefix=".pac_scalp_ll_", suffix=".json")
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(campaigns.canonical(value) + b"\n")
            handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _hash_row(row: dict, field: str) -> dict:
    body = dict(row); body.pop(field, None)
    return {**body, field: campaigns.sha(body)}


def _boot_id() -> str:
    try:
        value = BOOT_ID_PATH.read_text().strip()
    except OSError as exc:
        raise CalibrationRefused("calibration cannot bind monotonic clocks to a boot") from exc
    if (len(value) != 36 or value.count("-") != 4
            or any(char not in "0123456789abcdef-" for char in value)):
        raise CalibrationRefused("calibration boot id is malformed")
    return value


def _rpc(url: str, request_json: dict, *, opener=None) -> dict:
    request = urllib.request.Request(
        url, data=campaigns.canonical(request_json),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        response = (opener or urllib.request.urlopen)(request, timeout=TIMEOUT_SECONDS)
        with response:
            status, payload = getattr(response, "status", None), response.read()
        value = json.loads(payload)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError,
            json.JSONDecodeError) as exc:
        raise CalibrationRefused(f"calibration RPC failed: {type(exc).__name__}") from exc
    if status != 200 or not isinstance(value, dict):
        raise CalibrationRefused("calibration RPC returned a non-200/non-object response")
    return value


def _recent_blockhash(url: str, *, rpc=_rpc) -> bytes:
    response = rpc(url, {"jsonrpc": "2.0", "id": 1, "method": "getLatestBlockhash",
                         "params": [{"commitment": "processed"}]})
    result = response.get("result") if isinstance(response, dict) else None
    context = result.get("context") if isinstance(result, dict) else None
    value = result.get("value") if isinstance(result, dict) else None
    blockhash = value.get("blockhash") if isinstance(value, dict) else None
    if (response.get("jsonrpc") != "2.0" or response.get("id") != 1
            or not isinstance(context, dict) or type(context.get("slot")) is not int
            or context["slot"] <= 0):
        raise CalibrationRefused("neutral blockhash response envelope/context refuses")
    try:
        return solana._b58decode("recent blockhash", blockhash, exact_length=32)
    except (solana.CalibrationRefused, TypeError) as exc:
        raise CalibrationRefused("neutral observer returned no valid blockhash") from exc


def _message_base64(wire_base64: str) -> str:
    try:
        raw = base64.b64decode(wire_base64, validate=True)
        signatures, offset = tx._read_shortvec(raw, 0)
    except (ValueError, RefusedExecution) as exc:
        raise CalibrationRefused("calibration wire cannot expose its message") from exc
    offset += signatures * 64
    if signatures != 1 or offset >= len(raw):
        raise CalibrationRefused("calibration wire signature/message shape is invalid")
    return base64.b64encode(raw[offset:]).decode("ascii")


def _fee_quote(url: str, wire_base64: str, request_id: int, *, rpc=_rpc) -> int:
    response = rpc(url, {"jsonrpc": "2.0", "id": request_id,
                         "method": "getFeeForMessage",
                         "params": [_message_base64(wire_base64),
                                    {"commitment": "processed"}]})
    result = response.get("result") if isinstance(response, dict) else None
    context = result.get("context") if isinstance(result, dict) else None
    value = result.get("value") if isinstance(result, dict) else None
    if (response.get("jsonrpc") != "2.0" or response.get("id") != request_id
            or not isinstance(context, dict) or type(context.get("slot")) is not int
            or context["slot"] <= 0 or type(value) is not int or value <= 0):
        raise CalibrationRefused("neutral observer returned no exact fee quote")
    return value


def _status(url: str, signature: str, request_id: int, *, rpc=_rpc) -> tuple[int, str] | None:
    response = rpc(url, {"jsonrpc": "2.0", "id": request_id,
                         "method": "getSignatureStatuses",
                         "params": [[signature], {"searchTransactionHistory": True}]})
    result = response.get("result") if isinstance(response, dict) else None
    context = result.get("context") if isinstance(result, dict) else None
    values = result.get("value") if isinstance(result, dict) else None
    if (response.get("jsonrpc") != "2.0" or response.get("id") != request_id
            or not isinstance(context, dict) or type(context.get("slot")) is not int
            or context["slot"] <= 0 or not isinstance(values, list) or len(values) != 1):
        raise CalibrationRefused("neutral status response has invalid cardinality")
    if values[0] is None:
        return None
    row = values[0]
    if (not isinstance(row, dict) or row.get("err") is not None
            or type(row.get("slot")) is not int or row["slot"] <= 0
            or row.get("confirmationStatus") not in {"processed", "confirmed", "finalized"}):
        raise CalibrationRefused("first non-null status is not a successful landing")
    return row["slot"], row["confirmationStatus"]


def _new_journal(campaign: campaigns.Campaign) -> dict:
    return _hash_row({
        "schema": JOURNAL_SCHEMA, "instrument_id": campaigns.INSTRUMENT,
        "campaign_sha256": campaign.campaign_sha256,
        "samples_per_arm": campaign.samples_per_arm,
        "max_lamports": campaign.max_lamports, "attempts": [],
    }, "journal_sha256")


def _attempt_body(*, campaign: campaigns.Campaign, attempt_index: int, arm: str,
                  boot_id: str, stage: str, wire_base64: str, signature: str,
                  fee_lamports: int, clocks: dict, polls: list[dict],
                  processed_slot: int | None, confirmation_status: str | None,
                  failure: str | None) -> dict:
    return _hash_row({
        "schema": ATTEMPT_SCHEMA, "instrument_id": campaigns.INSTRUMENT,
        "campaign_sha256": campaign.campaign_sha256, "attempt_index": attempt_index,
        "pair_index": attempt_index // 2, "member_index": attempt_index % 2, "arm": arm,
        "boot_id": boot_id, "stage": stage, "wire_base64": wire_base64,
        "wire_sha256": hashlib.sha256(base64.b64decode(wire_base64)).hexdigest(),
        "signature": signature, "fee_lamports": fee_lamports,
        "tip_lamports": campaign.profile.tip_lamports,
        "reserved_lamports": fee_lamports + campaign.profile.tip_lamports,
        "clocks": clocks, "status_polls": polls, "processed_slot": processed_slot,
        "confirmation_status": confirmation_status, "failure": failure,
    }, "attempt_sha256")


_ATTEMPT_KEYS = frozenset({
    "schema", "instrument_id", "campaign_sha256", "attempt_index", "pair_index",
    "member_index", "arm", "boot_id", "stage", "wire_base64", "wire_sha256",
    "signature", "fee_lamports", "tip_lamports", "reserved_lamports", "clocks",
    "status_polls", "processed_slot", "confirmation_status", "failure", "attempt_sha256",
})


def _validate_attempt(row: dict, campaign: campaigns.Campaign, index: int) -> None:
    if not isinstance(row, dict):
        raise CalibrationRefused("calibration attempt is not an object")
    body = dict(row); record_sha = body.pop("attempt_sha256", None)
    if (set(row) != _ATTEMPT_KEYS or record_sha != campaigns.sha(body)
            or row.get("schema") != ATTEMPT_SCHEMA
            or row.get("instrument_id") != campaigns.INSTRUMENT
            or row.get("campaign_sha256") != campaign.campaign_sha256
            or row.get("attempt_index") != index or row.get("pair_index") != index // 2
            or row.get("member_index") != index % 2
            or row.get("arm") != campaigns.arm_for(campaign.campaign_sha256, index)
            or row.get("stage") not in {"SIGNED", "ACKED", "PROCESSED", "FAILED"}
            or type(row.get("fee_lamports")) is not int or row["fee_lamports"] <= 0
            or row.get("tip_lamports") != campaign.profile.tip_lamports
            or row.get("reserved_lamports")
            != row["fee_lamports"] + campaign.profile.tip_lamports
            or not isinstance(row.get("clocks"), dict)
            or not isinstance(row.get("status_polls"), list)
            or not isinstance(row.get("boot_id"), str) or not row["boot_id"]):
        raise CalibrationRefused(f"calibration attempt {index} schema/binding mismatch")
    memo = tx.campaign_memo(campaign.campaign_sha256, row["arm"], index)
    parsed = tx.verify(row.get("wire_base64"), expected_memo=memo,
                       expected_profile=campaign.profile)
    try:
        wire_sha = hashlib.sha256(base64.b64decode(
            row["wire_base64"], validate=True)).hexdigest()
    except (ValueError, TypeError) as exc:
        raise CalibrationRefused(f"calibration attempt {index} wire is invalid") from exc
    payer_fingerprint = hashlib.sha256(parsed["fee_payer"].encode()).hexdigest()
    if (parsed["signature"] != row.get("signature")
            or wire_sha != row.get("wire_sha256")
            or payer_fingerprint != campaign.fee_payer_fingerprint_sha256):
        raise CalibrationRefused(f"calibration attempt {index} wire identity mismatch")
    clocks = row["clocks"]
    required = {"build_start_wall", "build_start_mono", "sign_done_wall", "sign_done_mono",
                "fee_start_mono", "fee_done_mono", "send_start_wall", "send_start_mono",
                "send_ack_wall", "send_ack_mono", "processed_wall", "processed_mono"}
    if set(clocks) != required:
        raise CalibrationRefused(f"calibration attempt {index} clock schema mismatch")
    fixed = [clocks[name] for name in ("build_start_mono", "sign_done_mono",
                                      "fee_start_mono", "fee_done_mono")]
    if any(type(value) is not int or value <= 0 for value in fixed) \
            or any(right < left for left, right in zip(fixed, fixed[1:])):
        raise CalibrationRefused(f"calibration attempt {index} pre-send clocks are invalid")
    walls = [clocks[name] for name in ("build_start_wall", "sign_done_wall")]
    if any(type(value) is not int or value <= 0 for value in walls) or walls[1] < walls[0]:
        raise CalibrationRefused(f"calibration attempt {index} wall clocks are invalid")
    previous_poll_mono = clocks["send_ack_mono"]
    successful_polls = []
    for poll_index, poll in enumerate(row["status_polls"]):
        if (not isinstance(poll, dict) or set(poll) != {
                "request_start_wall", "request_start_mono", "response_wall", "response_mono",
                "status"}):
            raise CalibrationRefused(
                f"calibration attempt {index} poll {poll_index} schema mismatch")
        poll_values = [poll[key] for key in (
            "request_start_wall", "request_start_mono", "response_wall", "response_mono")]
        if (any(type(value) is not int or value <= 0 for value in poll_values)
                or poll["response_wall"] < poll["request_start_wall"]
                or poll["response_mono"] < poll["request_start_mono"]
                or (previous_poll_mono is not None
                    and poll["request_start_mono"] < previous_poll_mono)):
            raise CalibrationRefused(
                f"calibration attempt {index} poll {poll_index} clocks are invalid")
        status = poll["status"]
        if status is not None and (not isinstance(status, dict)
                or set(status) != {"slot", "confirmation"}
                or type(status["slot"]) is not int or status["slot"] <= 0
                or status["confirmation"] not in {"processed", "confirmed", "finalized"}):
            raise CalibrationRefused(
                f"calibration attempt {index} poll {poll_index} status is invalid")
        if status is not None:
            successful_polls.append(poll_index)
        previous_poll_mono = poll["response_mono"]
    send_values = [clocks[name] for name in (
        "send_start_wall", "send_start_mono", "send_ack_wall", "send_ack_mono")]
    send_complete = all(type(value) is int and value > 0 for value in send_values)
    if any(value is not None for value in send_values) and not send_complete:
        raise CalibrationRefused(f"calibration attempt {index} partial send clocks refuse")
    if row["status_polls"] and not send_complete:
        raise CalibrationRefused(f"calibration attempt {index} polls precede a complete send")
    if send_complete and (clocks["send_ack_wall"] < clocks["send_start_wall"]
                          or clocks["send_ack_mono"] < clocks["send_start_mono"]
                          or clocks["send_start_mono"] < clocks["fee_done_mono"]):
        raise CalibrationRefused(f"calibration attempt {index} send clocks regress")
    if row["stage"] == "SIGNED":
        if (any(value is not None for value in send_values)
                or clocks["processed_wall"] is not None or clocks["processed_mono"] is not None
                or row["status_polls"] or row["processed_slot"] is not None
                or row["confirmation_status"] is not None or row["failure"] is not None):
            raise CalibrationRefused(f"calibration attempt {index} signed state is not pre-send")
    elif row["stage"] == "ACKED":
        if (not send_complete or clocks["processed_wall"] is not None
                or clocks["processed_mono"] is not None or row["status_polls"]
                or row["processed_slot"] is not None or row["confirmation_status"] is not None
                or row["failure"] is not None):
            raise CalibrationRefused(f"calibration attempt {index} acked state is invalid")
    if row["stage"] == "PROCESSED":
        post = [clocks[name] for name in ("send_start_mono", "send_ack_mono",
                                         "processed_mono")]
        if (any(type(value) is not int or value <= 0 for value in post)
                or any(right < left for left, right in zip(post, post[1:]))
                or type(row.get("processed_slot")) is not int or row["processed_slot"] <= 0
                or row.get("confirmation_status")
                not in {"processed", "confirmed", "finalized"} or row.get("failure") is not None
                or not row["status_polls"]
                or successful_polls != [len(row["status_polls"]) - 1]
                or row["status_polls"][-1]["status"] != {
                    "slot": row["processed_slot"],
                    "confirmation": row["confirmation_status"]}
                or row["status_polls"][-1]["response_wall"] != clocks["processed_wall"]
                or row["status_polls"][-1]["response_mono"] != clocks["processed_mono"]
                or clocks["processed_mono"] - clocks["send_start_mono"]
                > campaigns.LANDING_DEADLINE_NANOS):
            raise CalibrationRefused(f"calibration attempt {index} processed state is invalid")
    elif row["stage"] == "FAILED":
        if (not isinstance(row.get("failure"), str) or not row["failure"]
                or row["processed_slot"] is not None or row["confirmation_status"] is not None
                or clocks["processed_wall"] is not None or clocks["processed_mono"] is not None
                or successful_polls):
            raise CalibrationRefused(f"calibration attempt {index} failure is untyped")


def load_journal(path: pathlib.Path, campaign: campaigns.Campaign) -> dict:
    path = pathlib.Path(path)
    if not path.exists():
        return _new_journal(campaign)
    try:
        row = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise CalibrationRefused("calibration journal is unreadable") from exc
    body = dict(row) if isinstance(row, dict) else {}
    journal_sha = body.pop("journal_sha256", None)
    if (set(row) != {"schema", "instrument_id", "campaign_sha256", "samples_per_arm",
                     "max_lamports", "attempts", "journal_sha256"}
            or journal_sha != campaigns.sha(body) or row.get("schema") != JOURNAL_SCHEMA
            or row.get("instrument_id") != campaigns.INSTRUMENT
            or row.get("campaign_sha256") != campaign.campaign_sha256
            or row.get("samples_per_arm") != campaign.samples_per_arm
            or row.get("max_lamports") != campaign.max_lamports
            or not isinstance(row.get("attempts"), list)):
        raise CalibrationRefused("calibration journal hash/binding mismatch")
    signatures: set[str] = set()
    for index, attempt in enumerate(row["attempts"]):
        _validate_attempt(attempt, campaign, index)
        if attempt["signature"] in signatures:
            raise CalibrationRefused("calibration journal reuses a signature")
        signatures.add(attempt["signature"])
    if sum(item["reserved_lamports"] for item in row["attempts"]) > campaign.max_lamports:
        raise CalibrationRefused("calibration journal exceeds the campaign budget")
    return row


def _persist(path: pathlib.Path, journal: dict) -> None:
    sealed = _hash_row(journal, "journal_sha256")
    _atomic_json(path, sealed)
    journal.clear(); journal.update(sealed)


def _attempt_pairs(attempts: list[dict]) -> list[tuple[dict, dict]]:
    output = []
    by_pair: dict[int, list[dict]] = {}
    for row in attempts:
        by_pair.setdefault(row["pair_index"], []).append(row)
    for pair_index in sorted(by_pair):
        pair = by_pair[pair_index]
        if (len(pair) == 2 and {row["arm"] for row in pair} == routes.ARMS
                and all(row["stage"] in {"PROCESSED", "FAILED"} for row in pair)):
            output.append((pair[0], pair[1]))
    return output


def _complete_pairs(attempts: list[dict]) -> list[tuple[dict, dict]]:
    """Diagnostic only: pairs in which both arms actually landed."""
    return [pair for pair in _attempt_pairs(attempts)
            if all(row["stage"] == "PROCESSED" for row in pair)]


def _latency_nanos(row: dict) -> int:
    clocks = row["clocks"]
    # getFeeForMessage is a measurement/budget guard, not a production order-path step.
    latency = (clocks["processed_mono"] - clocks["build_start_mono"]
               - (clocks["fee_done_mono"] - clocks["fee_start_mono"]))
    if latency <= 0:
        raise CalibrationRefused("calibration effective latency is non-positive")
    return latency


def _penalized_latency_nanos(row: dict) -> int:
    if row.get("stage") == "PROCESSED":
        return _latency_nanos(row)
    if row.get("stage") == "FAILED":
        return campaigns.LANDING_DEADLINE_NANOS
    raise CalibrationRefused("non-terminal attempt cannot enter a latency summary")


def _nearest_rank(values: list[int], quantile_num: int, quantile_den: int) -> int:
    if not values:
        raise CalibrationRefused("calibration quantile has no values")
    ordered = sorted(values)
    rank = math.ceil(len(ordered) * quantile_num / quantile_den)
    return ordered[max(0, rank - 1)]


def summary(journal: dict, campaign: campaigns.Campaign, *, raw_path: pathlib.Path) -> dict:
    target_attempts = campaign.samples_per_arm * 2
    selected = journal["attempts"][:target_attempts]
    pairs = _attempt_pairs(selected)
    terminal_complete = (len(selected) == target_attempts
                         and len(pairs) == campaign.samples_per_arm)
    by_arm = {arm: [] for arm in routes.ARMS}
    for pair in pairs:
        for row in pair:
            by_arm[row["arm"]].append(_penalized_latency_nanos(row))
    arm_summary = {}
    for arm in sorted(routes.ARMS):
        values = by_arm[arm]
        arm_summary[arm] = {
            "paired_samples": len(values),
            "failed_samples": sum(row["arm"] == arm and row["stage"] == "FAILED"
                                  for row in selected),
            "p50_effective_nanos": _nearest_rank(values, 1, 2) if values else None,
            "p90_effective_nanos": _nearest_rank(values, 9, 10) if values else None,
            "max_effective_nanos": max(values) if values else None,
        }
    body = {
        "schema": SUMMARY_SCHEMA, "instrument_id": campaigns.INSTRUMENT,
        "campaign_sha256": campaign.campaign_sha256,
        "evidence_status": ("UNATTESTED_LOCAL_COMPLETE" if terminal_complete
                            else "UNATTESTED_LOCAL_INCOMPLETE"),
        "attempted_pairs": len(pairs),
        "both_landed_pairs": len(_complete_pairs(selected)),
        "attempts": len(selected),
        "failures": sum(row["stage"] == "FAILED" for row in selected),
        "reserved_lamports": sum(row["reserved_lamports"] for row in journal["attempts"]),
        "raw_journal_sha256": hashlib.sha256(pathlib.Path(raw_path).read_bytes()).hexdigest(),
        "arms": arm_summary,
        "latency_definition": "BUILD_START_TO_FIRST_NEUTRAL_PROCESSED_OBSERVATION_MINUS_FEE_QUERY",
        "selection": "FIRST_N_DETERMINISTIC_MATCHED_ATTEMPTS_FAILURES_AT_DEADLINE",
        "boundary": "CALIBRATION_ONLY_NO_PUMP_ACCOUNTS_NOT_LIVE_CONTENTION",
    }
    return {**body, "summary_sha256": campaigns.sha(body)}


def _run_unlocked(*, campaign_path: pathlib.Path, campaign_file_sha256: str,
        keypair_path: pathlib.Path, journal_path: pathlib.Path, summary_path: pathlib.Path,
        public_submit_url: str, intervention_submit_url: str, verification_url: str,
        broadcast: bool, rpc=_rpc, clock=time.time_ns, monotonic=time.monotonic_ns,
        sleep=time.sleep, boot_id: str | None = None, _capability=None) -> dict:
    campaign = campaigns.load(campaign_path, expected_sha256=campaign_file_sha256)
    if broadcast:
        # Local import avoids a module cycle: the manifest seals this sender and is consulted only
        # at the explicitly requested spend boundary.
        from . import pac_scalp_ll_manifest as manifest
        manifest.require_campaign_authority(
            pathlib.Path(campaign_path), file_sha256=campaign_file_sha256)
        manifest.require_exact_path(journal_path, manifest.RAW_JOURNAL, label="raw journal")
        manifest.require_exact_path(
            summary_path, manifest.CALIBRATION_SUMMARY, label="calibration summary")
        manifest.require_spend_authority(campaign)
        if _capability is not _BROADCAST_CAPABILITY:
            raise CalibrationRefused("broadcast requires the locked public run wrapper")
    campaigns.assert_runtime_urls(
        campaign, public_submit_url=public_submit_url,
        intervention_submit_url=intervention_submit_url, verification_url=verification_url)
    private, payer = _load_fee_payer(keypair_path)
    payer_fingerprint = hashlib.sha256(payer.encode()).hexdigest()
    if payer_fingerprint != campaign.fee_payer_fingerprint_sha256:
        raise CalibrationRefused("calibration keypair differs from the campaign fingerprint")
    # Dry-run proves every requested arm can build and verify, but creates no journal/evidence.
    if not broadcast:
        for index in range(campaign.samples_per_arm * 2):
            arm = campaigns.arm_for(campaign.campaign_sha256, index)
            tx.build(private, recent_blockhash=bytes(32),
                     memo=tx.campaign_memo(campaign.campaign_sha256, arm, index),
                     profile=campaign.profile)
        return {"broadcast": False, "built": campaign.samples_per_arm * 2,
                "reserved_lamports": 0}

    epoch = boot_id or _boot_id()
    journal = load_journal(journal_path, campaign)
    # No uncertain wire is ever resent after a crash. Its conservative budget reservation remains.
    if journal["attempts"] and journal["attempts"][-1]["stage"] in {"SIGNED", "ACKED"}:
        tail = deepcopy(journal["attempts"][-1])
        tail["stage"], tail["failure"] = "FAILED", "CRASH_RESUME_UNCERTAIN_NOT_RESENT"
        tail["attempt_sha256"] = campaigns.sha({
            key: value for key, value in tail.items() if key != "attempt_sha256"})
        journal["attempts"][-1] = tail; _persist(journal_path, journal)

    target_attempts = campaign.samples_per_arm * 2
    if len(journal["attempts"]) > target_attempts:
        raise CalibrationRefused("calibration journal exceeds the frozen attempt count")
    while len(journal["attempts"]) < target_attempts:
        index = len(journal["attempts"])
        arm = campaigns.arm_for(campaign.campaign_sha256, index)
        submit_url = (public_submit_url if arm == routes.PUBLIC_CONTROL
                      else intervention_submit_url)
        blockhash = _recent_blockhash(verification_url, rpc=rpc)
        build_w, build_m = clock(), monotonic()
        wire, signature, _payer = tx.build(
            private, recent_blockhash=blockhash,
            memo=tx.campaign_memo(campaign.campaign_sha256, arm, index),
            profile=campaign.profile)
        sign_w, sign_m = clock(), monotonic()
        fee_start = monotonic()
        fee = _fee_quote(verification_url, wire, index + 1, rpc=rpc)
        fee_done = monotonic()
        reserved = sum(row["reserved_lamports"] for row in journal["attempts"])
        if reserved + fee + campaign.profile.tip_lamports > campaign.max_lamports:
            raise CalibrationRefused("next exact calibration attempt exceeds campaign budget")
        clocks = {
            "build_start_wall": build_w, "build_start_mono": build_m,
            "sign_done_wall": sign_w, "sign_done_mono": sign_m,
            "fee_start_mono": fee_start, "fee_done_mono": fee_done,
            "send_start_wall": None, "send_start_mono": None,
            "send_ack_wall": None, "send_ack_mono": None,
            "processed_wall": None, "processed_mono": None,
        }
        attempt = _attempt_body(
            campaign=campaign, attempt_index=index, arm=arm, boot_id=epoch, stage="SIGNED",
            wire_base64=wire, signature=signature, fee_lamports=fee, clocks=clocks,
            polls=[], processed_slot=None, confirmation_status=None, failure=None)
        journal["attempts"].append(attempt); _persist(journal_path, journal)
        send_request = {"jsonrpc": "2.0", "id": index + 1, "method": "sendTransaction",
                        "params": [wire, {"encoding": "base64", "skipPreflight": True,
                                          "maxRetries": 0}]}
        send_w, send_m = clock(), monotonic()
        try:
            response = rpc(submit_url, send_request)
            ack_w, ack_m = clock(), monotonic()
            if response != {"jsonrpc": "2.0", "id": index + 1, "result": signature}:
                raise CalibrationRefused("submit response does not bind expected signature")
            attempt = deepcopy(attempt); attempt["stage"] = "ACKED"
            attempt["clocks"].update(send_start_wall=send_w, send_start_mono=send_m,
                                      send_ack_wall=ack_w, send_ack_mono=ack_m)
            attempt = _hash_row(attempt, "attempt_sha256")
            journal["attempts"][-1] = attempt; _persist(journal_path, journal)
            deadline = send_m + campaigns.LANDING_DEADLINE_NANOS
            polls: list[dict] = []
            landed = None
            while monotonic() < deadline:
                poll_start_w, poll_start_m = clock(), monotonic()
                status = _status(verification_url, signature, len(polls) + 1, rpc=rpc)
                poll_end_w, poll_end_m = clock(), monotonic()
                polls.append({"request_start_wall": poll_start_w,
                              "request_start_mono": poll_start_m,
                              "response_wall": poll_end_w, "response_mono": poll_end_m,
                              "status": (None if status is None else
                                         {"slot": status[0], "confirmation": status[1]})})
                if status is not None and poll_end_m <= deadline:
                    landed = (status, poll_end_w, poll_end_m); break
                if poll_end_m >= deadline:
                    break
                sleep(campaigns.POLL_INTERVAL_NANOS / 1_000_000_000)
            attempt = deepcopy(attempt); attempt["status_polls"] = polls
            if landed is None:
                attempt["stage"], attempt["failure"] = "FAILED", "LANDING_DEADLINE"
            else:
                status, processed_w, processed_m = landed
                attempt["stage"] = "PROCESSED"
                attempt["processed_slot"], attempt["confirmation_status"] = status
                attempt["clocks"].update(processed_wall=processed_w,
                                          processed_mono=processed_m)
            attempt = _hash_row(attempt, "attempt_sha256")
        except Exception as exc:
            attempt = deepcopy(attempt); attempt["stage"] = "FAILED"
            attempt["failure"] = f"{type(exc).__name__}:{str(exc)[:160]}"
            if attempt["clocks"]["send_start_mono"] is None:
                attempt["clocks"].update(send_start_wall=send_w, send_start_mono=send_m,
                                          send_ack_wall=clock(), send_ack_mono=monotonic())
            attempt = _hash_row(attempt, "attempt_sha256")
        journal["attempts"][-1] = attempt; _persist(journal_path, journal)

    exported = summary(journal, campaign, raw_path=journal_path)
    _atomic_json(summary_path, exported)
    return {"broadcast": True, **exported}


def run(*, campaign_path: pathlib.Path, campaign_file_sha256: str,
        keypair_path: pathlib.Path, journal_path: pathlib.Path, summary_path: pathlib.Path,
        public_submit_url: str, intervention_submit_url: str, verification_url: str,
        broadcast: bool, rpc=_rpc, clock=time.time_ns, monotonic=time.monotonic_ns,
        sleep=time.sleep, boot_id: str | None = None) -> dict:
    if not broadcast:
        return _run_unlocked(
            campaign_path=campaign_path, campaign_file_sha256=campaign_file_sha256,
            keypair_path=keypair_path, journal_path=journal_path, summary_path=summary_path,
            public_submit_url=public_submit_url,
            intervention_submit_url=intervention_submit_url,
            verification_url=verification_url, broadcast=False, rpc=rpc, clock=clock,
            monotonic=monotonic, sleep=sleep, boot_id=boot_id)
    from . import pac_scalp_ll_manifest as manifest
    manifest.require_exact_path(journal_path, manifest.RAW_JOURNAL, label="raw journal")
    manifest.require_exact_path(
        summary_path, manifest.CALIBRATION_SUMMARY, label="calibration summary")
    with manifest.exclusive_campaign():
        return _run_unlocked(
            campaign_path=campaign_path, campaign_file_sha256=campaign_file_sha256,
            keypair_path=keypair_path, journal_path=journal_path, summary_path=summary_path,
            public_submit_url=public_submit_url,
            intervention_submit_url=intervention_submit_url,
            verification_url=verification_url, broadcast=True, rpc=rpc, clock=clock,
            monotonic=monotonic, sleep=sleep, boot_id=boot_id,
            _capability=_BROADCAST_CAPABILITY)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="PAC_SCALP_LL matched calibration (default OFF)")
    parser.add_argument("--campaign", required=True, type=pathlib.Path)
    parser.add_argument("--campaign-file-sha256", required=True)
    parser.add_argument("--keypair", required=True, type=pathlib.Path)
    parser.add_argument("--journal", required=True, type=pathlib.Path)
    parser.add_argument("--summary", required=True, type=pathlib.Path)
    parser.add_argument("--broadcast", action="store_true")
    args = parser.parse_args(argv)
    try:
        public = os.environ["PAC_SCALP_LL_PUBLIC_SUBMIT_RPC_URL"]
        intervention = os.environ["PAC_SCALP_LL_INTERVENTION_SUBMIT_RPC_URL"]
        verification = os.environ["PAC_SCALP_LL_ATTEST_RPC_URL"]
        result = run(
            campaign_path=args.campaign, campaign_file_sha256=args.campaign_file_sha256,
            keypair_path=args.keypair, journal_path=args.journal, summary_path=args.summary,
            public_submit_url=public, intervention_submit_url=intervention,
            verification_url=verification, broadcast=args.broadcast)
    except (KeyError, RefusedExecution) as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc)[:240]}, sort_keys=True))
        return 2
    print(json.dumps({"status": "OK", **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
