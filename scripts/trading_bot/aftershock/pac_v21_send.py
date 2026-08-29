#!/usr/bin/env python3
"""Crash-safe, default-OFF memo campaign sender for PAC V2.1 processed calibration.

Broadcast is impossible without ``--broadcast``, an explicit campaign-bound keypair, and a matching
public submit origin.  Each signed wire is durably journaled before send.  A crash can therefore create a
visible failed calibration attempt, never a forgotten/replaced signature or an invented latency sample.
This module can emit only the parsed-and-ed25519-verified memo-only transaction profile; it cannot trade.
"""
from __future__ import annotations

import argparse
import base64
from copy import deepcopy
import hashlib
import json
import os
import pathlib
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

from .execution import RefusedExecution
from . import pac_v2_calibration as wire_schema
from . import pac_v2_send as v2_send
from . import pac_v21_calibration as calibration
from . import pac_v21_processed_observer as observer


ENV_SUBMIT = "PAC_V21_SUBMIT_RPC_URL"
JOURNAL_SCHEMA = 1
ATTEMPT_SCHEMA = 1
TIMEOUT_SECONDS = 20.0
BOOT_ID = pathlib.Path("/proc/sys/kernel/random/boot_id")


class SendRefused(RefusedExecution):
    pass


def _atomic_json(path: pathlib.Path, value: dict) -> None:
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        dir=path.parent, prefix=".pac_v21_journal_", suffix=".json")
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(calibration._canonical(value) + b"\n")
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


def _atomic_jsonl(path: pathlib.Path, rows: list[dict]) -> None:
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        dir=path.parent, prefix=".pac_v21_samples_", suffix=".jsonl")
    try:
        with os.fdopen(descriptor, "wb") as handle:
            for row in rows:
                handle.write(calibration._canonical(row) + b"\n")
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


def _boot_id() -> str:
    try:
        value = BOOT_ID.read_text().strip()
    except OSError as exc:
        raise SendRefused("PAC V2.1 cannot bind the monotonic clock to a boot epoch") from exc
    if (len(value) != 36 or value.count("-") != 4
            or any(char not in "0123456789abcdef-" for char in value)):
        raise SendRefused("PAC V2.1 boot epoch identifier is malformed")
    return value


def _record(attempt: dict) -> dict:
    body = dict(attempt); body.pop("record_sha256", None)
    return {**body, "record_sha256": calibration._sha(body)}


def _journal_value(body: dict) -> dict:
    core = dict(body); core.pop("journal_sha256", None)
    return {**core, "journal_sha256": calibration._sha(core)}


def _origin(url: str) -> str:
    if not isinstance(url, str) or not url:
        raise SendRefused("PAC V2.1 submit URL is absent")
    parsed = urllib.parse.urlsplit(url)
    try:
        port = f":{parsed.port}" if parsed.port is not None else ""
    except ValueError as exc:
        raise SendRefused("PAC V2.1 submit URL port is invalid") from exc
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or not calibration.base._is_public_rpc_host(parsed.hostname)):
        raise SendRefused("PAC V2.1 submit URL is not a public HTTPS RPC endpoint")
    return f"https://{parsed.hostname}{port}"


def _require_campaign_authority(path: pathlib.Path, campaign: calibration.Campaign) -> None:
    """Refuse broadcast unless the fixed campaign is anchored strictly after the current seal."""
    # Local import avoids a module-initialization cycle: the manifest closes this sender, while the
    # sender consults that manifest only at the moment an explicitly requested broadcast is attempted.
    from . import pac_v21_manifest as manifest

    candidate = pathlib.Path(path).resolve()
    if candidate != manifest.CAMPAIGN.resolve():
        raise SendRefused("PAC V2.1 broadcast requires the manifest-owned campaign path")
    seal = manifest.verify_seal()
    if (manifest.anchor_status() != "ANCHORED" or not manifest._git_clean(candidate)
            or campaign.seal_sha256 != seal["seal_sha256"]):
        raise SendRefused("PAC V2.1 broadcast campaign/seal authority is not anchored")
    manifest._must_precede(
        manifest.SEAL, (candidate,), label="seal-before-campaign-broadcast")


def _rpc(url: str, request_json: dict, *, opener=None) -> dict:
    request = urllib.request.Request(
        url, data=calibration._canonical(request_json),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        response = (opener or urllib.request.urlopen)(request, timeout=TIMEOUT_SECONDS)
        with response:
            status, payload = getattr(response, "status", None), response.read()
        value = json.loads(payload)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError,
            json.JSONDecodeError) as exc:
        raise SendRefused(f"PAC V2.1 submit RPC failed: {type(exc).__name__}") from exc
    if status != 200 or not isinstance(value, dict):
        raise SendRefused("PAC V2.1 submit RPC returned a non-200/non-object response")
    return value


def _latest_blockhash(url: str, *, opener=None) -> bytes:
    request = {"jsonrpc": "2.0", "id": 1, "method": "getLatestBlockhash",
               "params": [{"commitment": "processed"}]}
    response = _rpc(url, request, opener=opener)
    blockhash = ((response.get("result") or {}).get("value") or {}).get("blockhash")
    try:
        return wire_schema._b58decode("recent blockhash", blockhash, exact_length=32)
    except wire_schema.CalibrationRefused as exc:
        raise SendRefused("PAC V2.1 submit RPC returned no valid recent blockhash") from exc


def _message_base64(wire_b64: str) -> str:
    try:
        wire = base64.b64decode(wire_b64, validate=True)
        signature_count, offset = wire_schema._shortvec(wire, 0)
    except (ValueError, wire_schema.CalibrationRefused) as exc:
        raise SendRefused("PAC V2.1 signed wire is not parseable") from exc
    offset += signature_count * 64
    if offset >= len(wire):
        raise SendRefused("PAC V2.1 signed wire has no message")
    return base64.b64encode(wire[offset:]).decode("ascii")


def _fee_quote(url: str, wire_b64: str, attempt_index: int, *, opener=None) -> tuple[dict, dict, int]:
    request = {"jsonrpc": "2.0", "id": attempt_index + 1, "method": "getFeeForMessage",
               "params": [_message_base64(wire_b64), {"commitment": "processed"}]}
    response = _rpc(url, request, opener=opener)
    result = response.get("result") if isinstance(response, dict) else None
    fee = result.get("value") if isinstance(result, dict) else None
    context = result.get("context") if isinstance(result, dict) else None
    if (set(response) != {"jsonrpc", "id", "result"} or response.get("jsonrpc") != "2.0"
            or response.get("id") != attempt_index + 1 or not isinstance(context, dict)
            or type(context.get("slot")) is not int or context["slot"] <= 0
            or type(fee) is not int or fee <= 0):
        raise SendRefused("PAC V2.1 getFeeForMessage response is invalid/unavailable")
    return request, response, fee


def _new_journal(campaign: calibration.Campaign) -> dict:
    return _journal_value({
        "schema": JOURNAL_SCHEMA, "instrument_id": calibration.INSTRUMENT,
        "campaign_id": campaign.campaign_id, "campaign_sha256": campaign.artifact_sha256,
        "seal_sha256": campaign.seal_sha256,
        "max_transactions": campaign.max_transactions,
        "max_lamports": campaign.max_lamports,
        "attempts": [],
    })


_ATTEMPT_KEYS = {
    "schema", "instrument_id", "campaign_id", "attempt_index", "previous_sample_id",
    "boot_id", "stage", "transaction_signature", "quoted_fee_lamports",
    "clocks_unix_nanos", "clocks_monotonic_nanos", "raw_evidence", "status_polls",
    "sample", "failure", "record_sha256",
}


def _validate_attempt(attempt: dict, *, campaign: calibration.Campaign,
                      attempt_index: int, previous_sample_id: str) -> None:
    if (not isinstance(attempt, dict) or set(attempt) != _ATTEMPT_KEYS
            or attempt.get("schema") != ATTEMPT_SCHEMA
            or attempt.get("instrument_id") != calibration.INSTRUMENT
            or attempt.get("campaign_id") != campaign.campaign_id
            or attempt.get("attempt_index") != attempt_index
            or attempt.get("previous_sample_id") != previous_sample_id
            or attempt.get("stage") not in {"SIGNED", "ACKED", "PROCESSED", "FAILED"}):
        raise SendRefused(f"PAC V2.1 journal attempt {attempt_index} schema/chain mismatch")
    body = dict(attempt); record_sha = body.pop("record_sha256")
    if record_sha != calibration._sha(body):
        raise SendRefused(f"PAC V2.1 journal attempt {attempt_index} hash mismatch")
    if not isinstance(attempt["boot_id"], str):
        raise SendRefused(f"PAC V2.1 journal attempt {attempt_index} has no boot epoch")
    signature = attempt["transaction_signature"]
    try:
        wire_schema._b58decode("journal signature", signature, exact_length=64)
    except wire_schema.CalibrationRefused as exc:
        raise SendRefused(f"PAC V2.1 journal attempt {attempt_index} signature is invalid") from exc
    if type(attempt["quoted_fee_lamports"]) is not int or attempt["quoted_fee_lamports"] <= 0:
        raise SendRefused(f"PAC V2.1 journal attempt {attempt_index} fee is invalid")
    raw = attempt["raw_evidence"]
    raw_keys = {
        "wire_transaction_base64", "wire_transaction_sha256",
        "fee_request_json", "fee_request_sha256", "fee_response_json",
        "fee_response_sha256", "quoted_fee_lamports",
        "send_request_json", "send_request_sha256", "send_response_json",
        "send_response_sha256",
    }
    if (not isinstance(raw, dict) or set(raw) != raw_keys
            or not isinstance(raw.get("wire_transaction_base64"), str)):
        raise SendRefused(f"PAC V2.1 journal attempt {attempt_index} wire evidence is invalid")
    try:
        wire, parsed_signature, payer = wire_schema._wire_identity(
            raw["wire_transaction_base64"], expected_memo=wire_schema._campaign_memo(
                campaign.campaign_id, attempt_index, previous_sample_id))
    except wire_schema.CalibrationRefused as exc:
        raise SendRefused(f"PAC V2.1 journal attempt {attempt_index} wire refuses") from exc
    if (parsed_signature != signature or payer != campaign.calibration_fee_payer
            or raw.get("wire_transaction_sha256") != hashlib.sha256(wire).hexdigest()
            or raw.get("quoted_fee_lamports") != attempt["quoted_fee_lamports"]):
        raise SendRefused(f"PAC V2.1 journal attempt {attempt_index} identity/fee mismatch")
    message_b64 = _message_base64(raw["wire_transaction_base64"])
    expected_fee_request = {
        "jsonrpc": "2.0", "id": attempt_index + 1, "method": "getFeeForMessage",
        "params": [message_b64, {"commitment": "processed"}],
    }
    fee_response = raw["fee_response_json"]
    if (raw["fee_request_json"] != expected_fee_request
            or raw["fee_request_sha256"] != calibration._sha(expected_fee_request)
            or not isinstance(fee_response, dict)
            or set(fee_response) != {"jsonrpc", "id", "result"}
            or fee_response.get("jsonrpc") != "2.0"
            or fee_response.get("id") != attempt_index + 1
            or not isinstance(fee_response.get("result"), dict)
            or set(fee_response["result"]) != {"context", "value"}
            or not isinstance(fee_response["result"].get("context"), dict)
            or type(fee_response["result"]["context"].get("slot")) is not int
            or fee_response["result"]["context"]["slot"] <= 0
            or fee_response["result"].get("value") != attempt["quoted_fee_lamports"]
            or raw["fee_response_sha256"] != calibration._sha(fee_response)):
        raise SendRefused(f"PAC V2.1 journal attempt {attempt_index} fee evidence is invalid")
    expected_send_request = {
        "jsonrpc": "2.0", "id": attempt_index + 1, "method": "sendTransaction",
        "params": [raw["wire_transaction_base64"], {
            "encoding": "base64", "skipPreflight": False,
            "preflightCommitment": "processed",
        }],
    }
    if (raw["send_request_json"] != expected_send_request
            or raw["send_request_sha256"] != calibration._sha(expected_send_request)):
        raise SendRefused(f"PAC V2.1 journal attempt {attempt_index} send request is invalid")
    send_response = raw["send_response_json"]
    if send_response is None:
        if raw["send_response_sha256"] is not None or attempt["stage"] in {"ACKED", "PROCESSED"}:
            raise SendRefused(f"PAC V2.1 journal attempt {attempt_index} lacks send response evidence")
    elif (not isinstance(send_response, dict)
          or raw["send_response_sha256"] != calibration._sha(send_response)
          or (attempt["stage"] in {"ACKED", "PROCESSED"}
              and send_response != {"jsonrpc": "2.0", "id": attempt_index + 1,
                                    "result": signature})):
        raise SendRefused(f"PAC V2.1 journal attempt {attempt_index} send response is invalid")
    clocks_w, clocks_m = attempt["clocks_unix_nanos"], attempt["clocks_monotonic_nanos"]
    keys = {"decision", "build_start", "sign_done", "send_start", "send_ack"}
    if not isinstance(clocks_w, dict) or set(clocks_w) != keys or not isinstance(clocks_m, dict) \
            or set(clocks_m) != keys:
        raise SendRefused(f"PAC V2.1 journal attempt {attempt_index} clock schema mismatch")
    for clocks in (clocks_w, clocks_m):
        fixed = [clocks[name] for name in ("decision", "build_start", "sign_done")]
        if any(type(value) is not int or value <= 0 for value in fixed) \
                or any(right < left for left, right in zip(fixed, fixed[1:])):
            raise SendRefused(f"PAC V2.1 journal attempt {attempt_index} pre-send clocks are invalid")
    if attempt["stage"] == "SIGNED":
        if any(clocks[name] is not None for clocks in (clocks_w, clocks_m)
               for name in ("send_start", "send_ack")) or attempt["sample"] is not None \
                or attempt["failure"] is not None:
            raise SendRefused(f"PAC V2.1 SIGNED attempt {attempt_index} is not pre-send")
    elif (attempt["stage"] == "FAILED"
          and all(clocks[name] is None for clocks in (clocks_w, clocks_m)
                  for name in ("send_start", "send_ack"))):
        # A process died after the signed wire was durable but before an ACK clock became durable.
        # It is a visible failed attempt and is never resent or promoted into a latency sample.
        pass
    else:
        for clocks in (clocks_w, clocks_m):
            values = [clocks[name] for name in (
                "decision", "build_start", "sign_done", "send_start", "send_ack")]
            if any(type(value) is not int or value <= 0 for value in values) \
                    or any(right < left for left, right in zip(values, values[1:])):
                raise SendRefused(f"PAC V2.1 attempt {attempt_index} send clocks are invalid")
    if attempt["stage"] == "PROCESSED" and not isinstance(attempt["sample"], dict):
        raise SendRefused(f"PAC V2.1 processed attempt {attempt_index} has no sample")
    if attempt["stage"] == "FAILED":
        failure = attempt["failure"]
        if (not isinstance(failure, dict)
                or set(failure) != {"stage", "reason", "terminal_unix_nanos",
                                   "terminal_monotonic_nanos"}
                or not isinstance(failure["stage"], str) or not failure["stage"]
                or not isinstance(failure["reason"], str) or not failure["reason"]
                or type(failure["terminal_unix_nanos"]) is not int
                or type(failure["terminal_monotonic_nanos"]) is not int):
            raise SendRefused(f"PAC V2.1 failed attempt {attempt_index} has no typed failure record")
    if not isinstance(attempt["status_polls"], list):
        raise SendRefused(f"PAC V2.1 journal attempt {attempt_index} polls are invalid")


def load_journal(path: pathlib.Path, campaign: calibration.Campaign) -> dict:
    path = pathlib.Path(path)
    if not path.exists():
        return _new_journal(campaign)
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise SendRefused("PAC V2.1 journal is unreadable") from exc
    required = {"schema", "instrument_id", "campaign_id", "campaign_sha256", "seal_sha256",
                "max_transactions", "max_lamports", "attempts", "journal_sha256"}
    body = dict(value) if isinstance(value, dict) else {}
    journal_sha = body.pop("journal_sha256", None)
    if (set(value) != required or journal_sha != calibration._sha(body)
            or value.get("schema") != JOURNAL_SCHEMA
            or value.get("instrument_id") != calibration.INSTRUMENT
            or value.get("campaign_id") != campaign.campaign_id
            or value.get("campaign_sha256") != campaign.artifact_sha256
            or value.get("seal_sha256") != campaign.seal_sha256
            or value.get("max_transactions") != campaign.max_transactions
            or value.get("max_lamports") != campaign.max_lamports
            or not isinstance(value.get("attempts"), list)):
        raise SendRefused("PAC V2.1 journal binding/hash mismatch")
    previous = campaign.campaign_id
    signatures: set[str] = set()
    active = 0
    for index, attempt in enumerate(value["attempts"]):
        _validate_attempt(attempt, campaign=campaign, attempt_index=index,
                          previous_sample_id=previous)
        if attempt["transaction_signature"] in signatures:
            raise SendRefused("PAC V2.1 journal reuses a signature")
        signatures.add(attempt["transaction_signature"])
        if attempt["stage"] == "PROCESSED":
            try:
                calibration._sample(
                    attempt["sample"], sum(1 for prior in value["attempts"][:index]
                                           if prior["stage"] == "PROCESSED"),
                    campaign, previous)
            except calibration.CalibrationRefused as exc:
                raise SendRefused(f"PAC V2.1 journal sample {index} refuses") from exc
            previous = attempt["sample"]["sample_id"]
        elif attempt["stage"] in {"SIGNED", "ACKED"}:
            active += 1
            if index != len(value["attempts"]) - 1:
                raise SendRefused("PAC V2.1 journal has a non-terminal attempt before its tail")
    if active > 1 or len(value["attempts"]) > campaign.max_transactions \
            or sum(item["quoted_fee_lamports"] for item in value["attempts"]) > campaign.max_lamports:
        raise SendRefused("PAC V2.1 journal exceeds its active/count/budget bounds")
    return value


def _persist(path: pathlib.Path, journal: dict) -> None:
    _atomic_json(path, _journal_value(journal))
    journal.update(_journal_value(journal))


def materialize_samples(journal: dict, output_path: pathlib.Path) -> list[dict]:
    samples = [deepcopy(item["sample"]) for item in journal["attempts"]
               if item["stage"] == "PROCESSED"]
    _atomic_jsonl(pathlib.Path(output_path), samples)
    return samples


def _fail(attempt: dict, *, stage: str, reason: str, polls: tuple[dict, ...],
          clock=time.time_ns, monotonic=time.monotonic_ns) -> dict:
    attempt = deepcopy(attempt)
    attempt["stage"] = "FAILED"
    attempt["status_polls"] = list(polls)
    attempt["sample"] = None
    attempt["failure"] = {
        "stage": stage, "reason": reason[:240],
        "terminal_unix_nanos": clock(),
        "terminal_monotonic_nanos": monotonic(),
    }
    return _record(attempt)


def _complete_acked(attempt: dict, *, campaign: calibration.Campaign,
                    rpc_url: str, opener, clock, monotonic, sleep) -> dict:
    try:
        observed = observer.observe(
            attempt["transaction_signature"],
            rpc=lambda request: _rpc(rpc_url, request, opener=opener),
            decision_monotonic_nanos=attempt["clocks_monotonic_nanos"]["decision"],
            clock=clock, monotonic=monotonic, sleep=sleep)
    except observer.ProcessedObservationRefused as exc:
        return _fail(attempt, stage="STATUS_OBSERVATION", reason=str(exc), polls=exc.polls,
                     clock=clock, monotonic=monotonic)
    attempt = deepcopy(attempt)
    wall = {**attempt["clocks_unix_nanos"],
            "processed_observed": observed.response_received_unix_nanos}
    mono = {**attempt["clocks_monotonic_nanos"],
            "processed_observed": observed.response_received_monotonic_nanos}
    raw = attempt["raw_evidence"]
    sample_body = {
        "schema": calibration.SAMPLE_SCHEMA, "instrument_id": calibration.INSTRUMENT,
        "campaign_id": campaign.campaign_id,
        "campaign_attempt_index": attempt["attempt_index"],
        "previous_sample_id": attempt["previous_sample_id"],
        "transaction_signature": attempt["transaction_signature"],
        "outcome": "PROCESSED", "processed_slot": observed.slot,
        "confirmation_status": observed.confirmation_status,
        "clocks_unix_nanos": wall, "clocks_monotonic_nanos": mono,
        "raw_evidence": raw, "raw_evidence_sha256": calibration._sha(raw),
        "status_polls": list(observed.polls),
    }
    sample = {**sample_body, "sample_id": calibration._sha(sample_body)}
    attempt["stage"], attempt["status_polls"] = "PROCESSED", list(observed.polls)
    attempt["sample"], attempt["failure"] = sample, None
    return _record(attempt)


def run(*, campaign_path: pathlib.Path, campaign_sha256: str, keypair_path: pathlib.Path,
        journal_path: pathlib.Path, samples_path: pathlib.Path, successful_samples: int,
        broadcast: bool, submit_rpc_url: str | None, opener=None,
        clock=time.time_ns, monotonic=time.monotonic_ns, sleep=time.sleep,
        boot_id: str | None = None) -> dict:
    campaign = calibration.load_campaign(
        pathlib.Path(campaign_path), expected_sha256=campaign_sha256)
    if broadcast:
        _require_campaign_authority(pathlib.Path(campaign_path), campaign)
    try:
        private, payer = v2_send.load_fee_payer(pathlib.Path(keypair_path))
    except v2_send.SendRefused as exc:
        raise SendRefused(str(exc)) from exc
    if payer != campaign.calibration_fee_payer:
        raise SendRefused("PAC V2.1 keypair differs from the pre-committed fee payer")
    if type(successful_samples) is not int or not 1 <= successful_samples <= campaign.max_transactions:
        raise SendRefused("PAC V2.1 successful-sample target exceeds the campaign count cap")
    if not broadcast:
        for index in range(successful_samples):
            memo = wire_schema._campaign_memo(campaign.campaign_id, index, campaign.campaign_id)
            v2_send.build_signed_memo(private, payer, memo, bytes(32))
        return {"broadcast": False, "dry_run_built": successful_samples, "spent_lamports": 0}
    if not submit_rpc_url or _origin(submit_rpc_url) != campaign.submit_origin:
        raise SendRefused("PAC V2.1 broadcast RPC origin differs from the campaign")

    epoch = boot_id or _boot_id()
    journal = load_journal(pathlib.Path(journal_path), campaign)
    attempts = journal["attempts"]
    if attempts and attempts[-1]["stage"] in {"SIGNED", "ACKED"}:
        active = attempts[-1]
        if active["stage"] == "SIGNED" or active["boot_id"] != epoch:
            reason = ("PRESEND_RESUME_IS_UNCERTAIN" if active["stage"] == "SIGNED"
                      else "MONOTONIC_BOOT_EPOCH_CHANGED")
            attempts[-1] = _fail(
                active, stage="CRASH_RESUME", reason=reason, polls=(),
                clock=clock, monotonic=monotonic)
            _persist(pathlib.Path(journal_path), journal)
        else:
            attempts[-1] = _complete_acked(
                active, campaign=campaign, rpc_url=submit_rpc_url, opener=opener,
                clock=clock, monotonic=monotonic, sleep=sleep)
            _persist(pathlib.Path(journal_path), journal)
    materialize_samples(journal, pathlib.Path(samples_path))

    while sum(item["stage"] == "PROCESSED" for item in attempts) < successful_samples:
        if len(attempts) >= campaign.max_transactions:
            raise SendRefused("PAC V2.1 campaign count cap reached before the success target")
        spent = sum(item["quoted_fee_lamports"] for item in attempts)
        attempt_index = len(attempts)
        previous = next((item["sample"]["sample_id"] for item in reversed(attempts)
                         if item["stage"] == "PROCESSED"), campaign.campaign_id)
        decision_w, decision_m = clock(), monotonic()
        blockhash = _latest_blockhash(submit_rpc_url, opener=opener)
        build_w, build_m = clock(), monotonic()
        memo = wire_schema._campaign_memo(campaign.campaign_id, attempt_index, previous)
        try:
            wire_b64, signature = v2_send.build_signed_memo(private, payer, memo, blockhash)
        except v2_send.SendRefused as exc:
            raise SendRefused(str(exc)) from exc
        sign_w, sign_m = clock(), monotonic()
        fee_request, fee_response, fee = _fee_quote(
            submit_rpc_url, wire_b64, attempt_index, opener=opener)
        if spent + fee > campaign.max_lamports:
            raise SendRefused("PAC V2.1 exact fee quote would exceed the campaign lamport cap")
        send_request = {
            "jsonrpc": "2.0", "id": attempt_index + 1, "method": "sendTransaction",
            "params": [wire_b64, {"encoding": "base64", "skipPreflight": False,
                                    "preflightCommitment": "processed"}],
        }
        raw = {
            "wire_transaction_base64": wire_b64,
            "wire_transaction_sha256": hashlib.sha256(base64.b64decode(wire_b64)).hexdigest(),
            "fee_request_json": fee_request, "fee_request_sha256": calibration._sha(fee_request),
            "fee_response_json": fee_response, "fee_response_sha256": calibration._sha(fee_response),
            "quoted_fee_lamports": fee,
            "send_request_json": send_request, "send_request_sha256": calibration._sha(send_request),
            "send_response_json": None, "send_response_sha256": None,
        }
        attempt = _record({
            "schema": ATTEMPT_SCHEMA, "instrument_id": calibration.INSTRUMENT,
            "campaign_id": campaign.campaign_id, "attempt_index": attempt_index,
            "previous_sample_id": previous, "boot_id": epoch, "stage": "SIGNED",
            "transaction_signature": signature, "quoted_fee_lamports": fee,
            "clocks_unix_nanos": {"decision": decision_w, "build_start": build_w,
                                   "sign_done": sign_w, "send_start": None, "send_ack": None},
            "clocks_monotonic_nanos": {"decision": decision_m, "build_start": build_m,
                                        "sign_done": sign_m, "send_start": None, "send_ack": None},
            "raw_evidence": raw, "status_polls": [], "sample": None, "failure": None,
        })
        attempts.append(attempt)
        _persist(pathlib.Path(journal_path), journal)  # durable before the first send byte

        send_w, send_m = clock(), monotonic()
        try:
            send_response = _rpc(submit_rpc_url, send_request, opener=opener)
        except SendRefused as exc:
            attempt = deepcopy(attempt)
            attempt["clocks_unix_nanos"].update(send_start=send_w, send_ack=clock())
            attempt["clocks_monotonic_nanos"].update(send_start=send_m, send_ack=monotonic())
            attempts[-1] = _fail(
                attempt, stage="SEND_TRANSPORT_UNCERTAIN", reason=str(exc), polls=(),
                clock=clock, monotonic=monotonic)
            _persist(pathlib.Path(journal_path), journal)
            continue
        ack_w, ack_m = clock(), monotonic()
        expected = {"jsonrpc": "2.0", "id": attempt_index + 1, "result": signature}
        attempt = deepcopy(attempt)
        attempt["clocks_unix_nanos"].update(send_start=send_w, send_ack=ack_w)
        attempt["clocks_monotonic_nanos"].update(send_start=send_m, send_ack=ack_m)
        attempt["raw_evidence"]["send_response_json"] = send_response
        attempt["raw_evidence"]["send_response_sha256"] = calibration._sha(send_response)
        if send_response != expected:
            attempts[-1] = _fail(
                attempt, stage="SEND_RESPONSE", reason="send response did not bind the signature",
                polls=(), clock=clock, monotonic=monotonic)
            _persist(pathlib.Path(journal_path), journal)
            continue
        attempt["stage"] = "ACKED"
        attempts[-1] = _record(attempt)
        _persist(pathlib.Path(journal_path), journal)
        attempts[-1] = _complete_acked(
            attempts[-1], campaign=campaign, rpc_url=submit_rpc_url, opener=opener,
            clock=clock, monotonic=monotonic, sleep=sleep)
        _persist(pathlib.Path(journal_path), journal)
        materialize_samples(journal, pathlib.Path(samples_path))

    samples = materialize_samples(journal, pathlib.Path(samples_path))
    return {
        "broadcast": True, "attempts": len(attempts), "processed": len(samples),
        "failed": sum(item["stage"] == "FAILED" for item in attempts),
        "budgeted_lamports": sum(item["quoted_fee_lamports"] for item in attempts),
        "journal": str(journal_path), "samples": str(samples_path),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="PAC V2.1 processed campaign sender (default OFF)")
    parser.add_argument("--campaign", required=True, type=pathlib.Path)
    parser.add_argument("--campaign-sha256", required=True)
    parser.add_argument("--keypair", required=True, type=pathlib.Path)
    parser.add_argument("--journal", required=True, type=pathlib.Path)
    parser.add_argument("--samples", required=True, type=pathlib.Path)
    parser.add_argument("--successful-samples", required=True, type=int)
    parser.add_argument("--broadcast", action="store_true",
                        help="ACTUALLY send memo transactions; absent means build-only dry-run")
    args = parser.parse_args(argv)
    try:
        result = run(
            campaign_path=args.campaign, campaign_sha256=args.campaign_sha256,
            keypair_path=args.keypair, journal_path=args.journal, samples_path=args.samples,
            successful_samples=args.successful_samples, broadcast=args.broadcast,
            submit_rpc_url=os.environ.get(ENV_SUBMIT) if args.broadcast else None)
    except RefusedExecution as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc)[:240]}, sort_keys=True))
        return 2
    print(json.dumps({"status": "OK", **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
