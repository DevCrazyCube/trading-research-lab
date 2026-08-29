#!/usr/bin/env python3
"""Pinned processed-observation calibration contract for PAC V2.1.

This module performs no network, signing, sending, or filesystem mutation. It validates a pre-anchored
campaign, an append-only chain of exact signed memo samples whose first non-null status observation is
preserved, and independent finalized attestations of the identical on-chain bytes.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import json
import pathlib
import urllib.parse

from . import pac_v2_calibration as base


INSTRUMENT = "AFTERSHOCK_PAC_V21"
CAMPAIGN_SCHEMA = 1
SAMPLE_SCHEMA = 1
ATTESTATION_SCHEMA = 1
MIN_PROCESSED_SAMPLES = 100
POLL_INTERVAL_NANOS = 100_000_000
PROCESSED_DEADLINE_NANOS = 30_000_000_000
MAX_WALL_MONOTONIC_DRIFT_NANOS = 1_000_000_000
MAX_BLOCKTIME_DISTANCE_NANOS = 120_000_000_000
EVIDENCE_MODE = "FIRST_STATUS_OBSERVATION_PLUS_INDEPENDENT_FINALIZED_WIRE"
TRANSACTION_PROFILE = base.TRANSACTION_PROFILE
MEMO_PROGRAM_ID = base.MEMO_PROGRAM_ID
CalibrationRefused = base.CalibrationRefused


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _text(label: str, value: object) -> str:
    if not isinstance(value, str) or not value:
        raise CalibrationRefused(f"{label} must be non-empty text")
    return value


def _hash(label: str, value: object) -> str:
    text = _text(label, value)
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise CalibrationRefused(f"{label} must be lowercase sha256")
    return text


def _integer(label: str, value: object, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise CalibrationRefused(f"{label} must be an exact integer >= {minimum}")
    return value


def _origin(label: str, value: object) -> str:
    text = _text(label, value)
    parsed = urllib.parse.urlsplit(text)
    try:
        port = f":{parsed.port}" if parsed.port is not None else ""
    except ValueError as exc:
        raise CalibrationRefused(f"{label} has an invalid port") from exc
    canonical = f"https://{parsed.hostname}{port}" if parsed.hostname else ""
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.path not in {"", "/"} or parsed.query or parsed.fragment
            or not base._is_public_rpc_host(parsed.hostname) or canonical != text):
        raise CalibrationRefused(f"{label} is not a strict public HTTPS origin")
    return text


def _read(path: pathlib.Path, *, expected_sha256: str, label: str) -> bytes:
    expected = _hash(f"{label} pin", expected_sha256)
    try:
        payload = pathlib.Path(path).read_bytes()
    except OSError as exc:
        raise CalibrationRefused(f"{label} unavailable") from exc
    if hashlib.sha256(payload).hexdigest() != expected:
        raise CalibrationRefused(f"{label} hash differs from its external pin")
    return payload


def _json(payload: bytes, label: str) -> dict:
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise CalibrationRefused(f"{label} is invalid JSON") from exc
    if not isinstance(value, dict):
        raise CalibrationRefused(f"{label} must be an object")
    return value


def _jsonl(payload: bytes, label: str) -> list[dict]:
    rows = []
    for number, line in enumerate(payload.splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise CalibrationRefused(f"{label} line {number} is invalid JSON") from exc
        if not isinstance(row, dict):
            raise CalibrationRefused(f"{label} line {number} must be an object")
        rows.append(row)
    return rows


@dataclass(frozen=True)
class Campaign:
    campaign_id: str
    seal_sha256: str
    calibration_fee_payer: str
    submit_origin: str
    verification_origin: str
    started_unix_nanos: int
    max_transactions: int
    max_lamports: int
    artifact_sha256: str


@dataclass(frozen=True)
class Pins:
    campaign_sha256: str
    samples_sha256: str
    attestations_sha256: str

    def __post_init__(self) -> None:
        _hash("campaign_sha256", self.campaign_sha256)
        _hash("samples_sha256", self.samples_sha256)
        _hash("attestations_sha256", self.attestations_sha256)


@dataclass(frozen=True)
class Calibration:
    artifact_sha256: str
    attestation_sha256: str
    campaign_sha256: str
    campaign_id: str
    processed_samples: int
    failed_samples: int
    processed_p90_nanos: int
    first_decision_unix_nanos: int
    last_processed_unix_nanos: int
    last_attested_unix_nanos: int


def load_campaign(path: pathlib.Path, *, expected_sha256: str) -> Campaign:
    payload = _read(path, expected_sha256=expected_sha256, label="V2.1 campaign")
    row = _json(payload, "V2.1 campaign")
    required = {
        "schema", "instrument_id", "campaign_id", "seal_sha256",
        "calibration_fee_payer", "submit_endpoint_scheme_host",
        "verification_endpoint_scheme_host", "started_unix_nanos",
        "max_transactions", "max_lamports", "poll_interval_nanos",
        "processed_deadline_nanos", "evidence_mode", "transaction_profile",
        "memo_program_id", "campaign_sha256",
    }
    if set(row) != required or row.get("schema") != CAMPAIGN_SCHEMA or row.get(
            "instrument_id") != INSTRUMENT:
        raise CalibrationRefused("V2.1 campaign schema/instrument mismatch")
    body = dict(row); campaign_sha = body.pop("campaign_sha256", None)
    if _hash("campaign content id", campaign_sha) != _sha(body):
        raise CalibrationRefused("V2.1 campaign content id mismatch")
    campaign_id = _hash("campaign_id", row["campaign_id"])
    seal = _hash("seal_sha256", row["seal_sha256"])
    payer = _text("calibration_fee_payer", row["calibration_fee_payer"])
    base._b58decode("calibration_fee_payer", payer, exact_length=32)
    submit = _origin("submit origin", row["submit_endpoint_scheme_host"])
    verify = _origin("verification origin", row["verification_endpoint_scheme_host"])
    if submit == verify:
        raise CalibrationRefused("V2.1 campaign submit and verification origins must differ")
    if (row["poll_interval_nanos"] != POLL_INTERVAL_NANOS
            or row["processed_deadline_nanos"] != PROCESSED_DEADLINE_NANOS
            or row["evidence_mode"] != EVIDENCE_MODE
            or row["transaction_profile"] != TRANSACTION_PROFILE
            or row["memo_program_id"] != MEMO_PROGRAM_ID):
        raise CalibrationRefused("V2.1 campaign measurement contract drift")
    started = _integer("campaign start", row["started_unix_nanos"], minimum=1)
    maximum = _integer("campaign max transactions", row["max_transactions"], minimum=100)
    budget = _integer("campaign max lamports", row["max_lamports"], minimum=1)
    return Campaign(campaign_id, seal, payer, submit, verify, started, maximum, budget,
                    hashlib.sha256(payload).hexdigest())


_CLOCKS = ("decision", "build_start", "sign_done", "send_start", "send_ack",
           "processed_observed")


def _clocks(row: dict, index: int) -> tuple[int, int, int, dict, dict]:
    wall, mono = row.get("clocks_unix_nanos"), row.get("clocks_monotonic_nanos")
    if not isinstance(wall, dict) or set(wall) != set(_CLOCKS):
        raise CalibrationRefused(f"sample[{index}] wall clock schema mismatch")
    if not isinstance(mono, dict) or set(mono) != set(_CLOCKS):
        raise CalibrationRefused(f"sample[{index}] monotonic clock schema mismatch")
    wall_values = [_integer(f"sample[{index}].wall.{key}", wall[key], minimum=1)
                   for key in _CLOCKS]
    mono_values = [_integer(f"sample[{index}].mono.{key}", mono[key], minimum=1)
                   for key in _CLOCKS]
    if any(right < left for left, right in zip(wall_values, wall_values[1:])):
        raise CalibrationRefused(f"sample[{index}] wall clocks are backward")
    if any(right < left for left, right in zip(mono_values, mono_values[1:])):
        raise CalibrationRefused(f"sample[{index}] monotonic clocks are backward")
    for left in range(len(_CLOCKS) - 1):
        if abs((wall_values[left + 1] - wall_values[left])
               - (mono_values[left + 1] - mono_values[left])) > MAX_WALL_MONOTONIC_DRIFT_NANOS:
            raise CalibrationRefused(f"sample[{index}] wall/monotonic interval diverges")
    reaction = mono_values[-1] - mono_values[0]
    if reaction <= 0 or reaction > PROCESSED_DEADLINE_NANOS:
        raise CalibrationRefused(f"sample[{index}] processed latency is outside the campaign bound")
    return wall_values[0], wall_values[-1], reaction, wall, mono


def _polls(row: dict, index: int, *, signature: str, processed_slot: int,
           confirmation_status: str, wall: dict, mono: dict) -> None:
    polls = row.get("status_polls")
    if not isinstance(polls, list) or not polls:
        raise CalibrationRefused(f"sample[{index}] has no status-poll evidence")
    previous_wall = wall["send_ack"]
    previous_mono = mono["send_ack"]
    for poll_index, poll in enumerate(polls):
        required = {
            "request_started_unix_nanos", "response_received_unix_nanos",
            "request_started_monotonic_nanos", "response_received_monotonic_nanos",
            "request_json", "response_json", "raw_response_sha256", "poll_id",
        }
        if not isinstance(poll, dict) or set(poll) != required:
            raise CalibrationRefused(f"sample[{index}].poll[{poll_index}] schema mismatch")
        body = dict(poll); poll_id = body.pop("poll_id")
        if _hash(f"sample[{index}].poll[{poll_index}].poll_id", poll_id) != _sha(body):
            raise CalibrationRefused(f"sample[{index}].poll[{poll_index}] content id mismatch")
        sw = _integer("poll request wall", poll["request_started_unix_nanos"], minimum=previous_wall)
        rw = _integer("poll response wall", poll["response_received_unix_nanos"], minimum=sw)
        sm = _integer("poll request monotonic", poll["request_started_monotonic_nanos"],
                      minimum=previous_mono)
        rm = _integer("poll response monotonic", poll["response_received_monotonic_nanos"], minimum=sm)
        if abs((rw - sw) - (rm - sm)) > MAX_WALL_MONOTONIC_DRIFT_NANOS:
            raise CalibrationRefused(f"sample[{index}].poll[{poll_index}] clock interval diverges")
        if poll_index and (sw - previous_wall < POLL_INTERVAL_NANOS
                           or sm - previous_mono < POLL_INTERVAL_NANOS):
            raise CalibrationRefused(f"sample[{index}] status polls violate frozen cadence")
        request, response = poll["request_json"], poll["response_json"]
        if (request != {"jsonrpc": "2.0", "id": poll_index + 1,
                        "method": "getSignatureStatuses",
                        "params": [[signature], {"searchTransactionHistory": True}]}
                or _hash("poll raw response hash", poll["raw_response_sha256"]) != _sha(response)):
            raise CalibrationRefused(f"sample[{index}].poll[{poll_index}] request/response binding fails")
        if (not isinstance(response, dict)
                or set(response) != {"jsonrpc", "id", "result"}
                or response.get("jsonrpc") != "2.0"
                or response.get("id") != poll_index + 1
                or not isinstance(response.get("result"), dict)
                or set(response["result"]) != {"context", "value"}
                or not isinstance(response["result"].get("context"), dict)
                or type(response["result"]["context"].get("slot")) is not int
                or response["result"]["context"]["slot"] <= 0):
            raise CalibrationRefused(
                f"sample[{index}].poll[{poll_index}] JSON-RPC envelope/context mismatch")
        value = response["result"]["value"]
        if not isinstance(value, list) or len(value) != 1:
            raise CalibrationRefused(f"sample[{index}].poll[{poll_index}] result schema mismatch")
        terminal = poll_index == len(polls) - 1
        if not terminal and value[0] is not None:
            raise CalibrationRefused(f"sample[{index}] ignored an earlier non-null status")
        if terminal:
            status = value[0]
            if (not isinstance(status, dict)
                    or status.get("err") is not None
                    or status.get("slot") != processed_slot
                    or status.get("confirmationStatus") != confirmation_status
                    or confirmation_status not in {"processed", "confirmed", "finalized"}):
                raise CalibrationRefused(f"sample[{index}] terminal processed status is invalid")
            if (rw != wall["processed_observed"]
                    or rm != mono["processed_observed"]):
                raise CalibrationRefused(f"sample[{index}] processed clock is not terminal poll receipt")
        previous_wall, previous_mono = rw, rm


def _sample(row: dict, index: int, campaign: Campaign, previous: str) -> dict:
    required = {
        "schema", "instrument_id", "campaign_id", "previous_sample_id", "sample_id",
        "transaction_signature", "outcome", "processed_slot", "confirmation_status",
        "clocks_unix_nanos", "clocks_monotonic_nanos", "raw_evidence",
        "raw_evidence_sha256", "status_polls",
    }
    if (not isinstance(row, dict) or set(row) != required or row.get("schema") != SAMPLE_SCHEMA
            or row.get("instrument_id") != INSTRUMENT or row.get("campaign_id") != campaign.campaign_id
            or row.get("previous_sample_id") != previous or row.get("outcome") != "PROCESSED"):
        raise CalibrationRefused(f"sample[{index}] schema/chain/outcome mismatch")
    body = dict(row); sample_id = body.pop("sample_id")
    if _hash(f"sample[{index}].sample_id", sample_id) != _sha(body):
        raise CalibrationRefused(f"sample[{index}] content id mismatch")
    signature = _text("transaction signature", row["transaction_signature"])
    base._b58decode("transaction signature", signature, exact_length=64)
    processed_slot = _integer("processed slot", row["processed_slot"], minimum=1)
    confirmation = _text("confirmation_status", row["confirmation_status"])
    decision, processed, reaction, wall, mono = _clocks(row, index)
    if decision < campaign.started_unix_nanos:
        raise CalibrationRefused(f"sample[{index}] predates campaign")
    raw = row.get("raw_evidence")
    required_raw = {
        "wire_transaction_base64", "wire_transaction_sha256", "send_request_json",
        "send_request_sha256", "send_response_json", "send_response_sha256",
    }
    if not isinstance(raw, dict) or set(raw) != required_raw or _hash(
            "raw evidence hash", row["raw_evidence_sha256"]) != _sha(raw):
        raise CalibrationRefused(f"sample[{index}] raw evidence binding fails")
    wire, wire_signature, payer = base._wire_identity(
        raw["wire_transaction_base64"],
        expected_memo=base._campaign_memo(campaign.campaign_id, index, previous))
    wire_sha = hashlib.sha256(wire).hexdigest()
    if (wire_sha != _hash("wire hash", raw["wire_transaction_sha256"])
            or wire_signature != signature or payer != campaign.calibration_fee_payer):
        raise CalibrationRefused(f"sample[{index}] signed wire identity mismatch")
    request, response = raw["send_request_json"], raw["send_response_json"]
    expected_request = {
        "jsonrpc": "2.0", "id": index + 1, "method": "sendTransaction",
        "params": [raw["wire_transaction_base64"], {
            "encoding": "base64", "skipPreflight": False,
            "preflightCommitment": "processed",
        }],
    }
    expected_response = {"jsonrpc": "2.0", "id": index + 1, "result": signature}
    if (request != expected_request
            or _hash("send request hash", raw["send_request_sha256"]) != _sha(request)
            or response != expected_response
            or _hash("send response hash", raw["send_response_sha256"]) != _sha(response)):
        raise CalibrationRefused(f"sample[{index}] send evidence mismatch")
    _polls(row, index, signature=signature, processed_slot=processed_slot,
           confirmation_status=confirmation, wall=wall, mono=mono)
    return {"sample_id": sample_id, "signature": signature, "wire_sha256": wire_sha,
            "processed_slot": processed_slot, "decision": decision, "processed": processed,
            "reaction": reaction}


def _attestation(row: dict, index: int, campaign: Campaign, sample: dict) -> tuple[int, int]:
    required = {
        "schema", "instrument_id", "campaign_id", "sample_id", "transaction_signature",
        "verification_endpoint_scheme_host", "request_started_unix_nanos",
        "response_received_unix_nanos", "request_json", "response_json",
        "raw_response_sha256", "attestation_id",
    }
    if (not isinstance(row, dict) or set(row) != required or row.get("schema") != ATTESTATION_SCHEMA
            or row.get("instrument_id") != INSTRUMENT or row.get("campaign_id") != campaign.campaign_id
            or row.get("sample_id") != sample["sample_id"]
            or row.get("transaction_signature") != sample["signature"]
            or row.get("verification_endpoint_scheme_host") != campaign.verification_origin):
        raise CalibrationRefused(f"attestation[{index}] identity/source mismatch")
    body = dict(row); attestation_id = body.pop("attestation_id")
    if _hash("attestation id", attestation_id) != _sha(body):
        raise CalibrationRefused(f"attestation[{index}] content id mismatch")
    started = _integer("attestation start", row["request_started_unix_nanos"],
                       minimum=sample["processed"])
    received = _integer("attestation receipt", row["response_received_unix_nanos"], minimum=started)
    request, response = row["request_json"], row["response_json"]
    if request != {"jsonrpc": "2.0", "id": index + 1, "method": "getTransaction",
                   "params": [sample["signature"], {"commitment": "finalized",
                                                     "encoding": "base64",
                                                     "maxSupportedTransactionVersion": 0}]}:
        raise CalibrationRefused(f"attestation[{index}] is not the exact finalized query")
    if _hash("attestation raw response hash", row["raw_response_sha256"]) != _sha(response):
        raise CalibrationRefused(f"attestation[{index}] raw response hash mismatch")
    if (not isinstance(response, dict)
            or set(response) != {"jsonrpc", "id", "result"}
            or response.get("jsonrpc") != "2.0"
            or response.get("id") != index + 1):
        raise CalibrationRefused(f"attestation[{index}] JSON-RPC envelope mismatch")
    result = response["result"]
    if (not isinstance(result, dict) or result.get("slot") != sample["processed_slot"]
            or not isinstance(result.get("blockTime"), int)
            or not isinstance(result.get("meta"), dict) or result["meta"].get("err") is not None
            or type(result["meta"].get("fee")) is not int or result["meta"]["fee"] < 0):
        raise CalibrationRefused(f"attestation[{index}] does not prove finalized successful landing")
    tx = result.get("transaction")
    if not isinstance(tx, list) or len(tx) != 2 or tx[1] != "base64":
        raise CalibrationRefused(f"attestation[{index}] lacks base64 wire bytes")
    wire, signature, payer = base._wire_identity(tx[0])
    if (signature != sample["signature"] or payer != campaign.calibration_fee_payer
            or hashlib.sha256(wire).hexdigest() != sample["wire_sha256"]):
        raise CalibrationRefused(f"attestation[{index}] finalized wire differs from processed sample")
    if abs(sample["processed"] - result["blockTime"] * 1_000_000_000) > MAX_BLOCKTIME_DISTANCE_NANOS:
        raise CalibrationRefused(f"attestation[{index}] block time is not near processed observation")
    return received, result["meta"]["fee"]


def load(*, campaign_path: pathlib.Path, samples_path: pathlib.Path,
         attestations_path: pathlib.Path, pins: Pins) -> Calibration:
    campaign = load_campaign(campaign_path, expected_sha256=pins.campaign_sha256)
    sample_payload = _read(samples_path, expected_sha256=pins.samples_sha256, label="V2.1 samples")
    attestation_payload = _read(
        attestations_path, expected_sha256=pins.attestations_sha256, label="V2.1 attestations")
    sample_rows = _jsonl(sample_payload, "V2.1 samples")
    attestation_rows = _jsonl(attestation_payload, "V2.1 attestations")
    if (len(sample_rows) < MIN_PROCESSED_SAMPLES or len(sample_rows) != len(attestation_rows)
            or len(sample_rows) > campaign.max_transactions):
        raise CalibrationRefused("V2.1 needs 100+ processed samples and one attestation per sample")
    samples = []
    previous = campaign.campaign_id
    signatures = set()
    for index, row in enumerate(sample_rows):
        sample = _sample(row, index, campaign, previous)
        if sample["signature"] in signatures:
            raise CalibrationRefused("V2.1 calibration reuses a transaction signature")
        signatures.add(sample["signature"]); samples.append(sample); previous = sample["sample_id"]
    attested = [_attestation(row, index, campaign, samples[index])
                for index, row in enumerate(attestation_rows)]
    if sum(fee for _received, fee in attested) > campaign.max_lamports:
        raise CalibrationRefused("V2.1 finalized fees exceed the pre-committed campaign budget")
    reactions = sorted(sample["reaction"] for sample in samples)
    rank = (9 * len(reactions) + 9) // 10  # ceil(0.9*n), one-indexed
    p90 = reactions[rank - 1]
    return Calibration(
        artifact_sha256=hashlib.sha256(sample_payload).hexdigest(),
        attestation_sha256=hashlib.sha256(attestation_payload).hexdigest(),
        campaign_sha256=campaign.artifact_sha256,
        campaign_id=campaign.campaign_id,
        processed_samples=len(samples), failed_samples=0,
        processed_p90_nanos=p90,
        first_decision_unix_nanos=min(sample["decision"] for sample in samples),
        last_processed_unix_nanos=max(sample["processed"] for sample in samples),
        last_attested_unix_nanos=max(received for received, _fee in attested),
    )
