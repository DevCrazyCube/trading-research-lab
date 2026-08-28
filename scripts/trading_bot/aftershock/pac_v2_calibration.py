#!/usr/bin/env python3
"""PAC V2 authenticated forward execution-clock calibration contract.

Calibration authority is a three-file bundle, never a self-validating JSONL:

* a campaign manifest committed before sampling, binding one fee payer and two distinct RPC origins;
* append-only local samples binding monotonic/wall clocks to the exact signed wire transaction; and
* an independently collected finalized-RPC attestation that returns those exact wire bytes on chain.

The runtime only trusts hashes pinned by a later, git-anchored activation. This module performs no
signing, sending, wallet access, or network I/O.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import ipaddress
import json
import pathlib
import socket
import urllib.parse

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


INSTRUMENT = "AFTERSHOCK_PAC_V2"
CAMPAIGN_SCHEMA = 2
SAMPLE_SCHEMA = 2
ATTESTATION_SCHEMA = 1
MIN_LANDED_SAMPLES = 100
MAX_WALL_MONOTONIC_DRIFT_NANOS = 1_000_000_000
MAX_BLOCKTIME_DISTANCE_NANOS = 120_000_000_000
_B58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
MEMO_PROGRAM_ID = "MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr"
TRANSACTION_PROFILE = "LEGACY_SINGLE_SIGNER_CAMPAIGN_MEMO_ONLY"


class CalibrationRefused(RuntimeError):
    pass


def _integer(label: str, value, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise CalibrationRefused(f"{label} must be an exact integer >= {minimum}")
    return value


def _text(label: str, value: object) -> str:
    if not isinstance(value, str) or not value:
        raise CalibrationRefused(f"{label} must be non-empty text")
    return value


def _sha(label: str, value: object) -> str:
    text = _text(label, value)
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise CalibrationRefused(f"{label} must be lowercase sha256")
    return text


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _canonical_sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


_RESERVED_SUFFIXES = (".localhost", ".local", ".invalid", ".test", ".example", ".internal", ".home.arpa")


def _is_public_rpc_host(hostname: str) -> bool:
    """A campaign RPC origin must be a genuine public host, never a loopback/private/reserved endpoint an
    operator could stand up locally to fabricate finalized results. This blocks the casual self-deception
    of pointing the 'independent' verifier at a machine the operator controls; a genuine independent public
    RPC is still the operator's responsibility."""
    host = hostname.lower().rstrip(".")
    if not host or host == "localhost" or any(host.endswith(suffix) for suffix in _RESERVED_SUFFIXES):
        return False
    # IPv4 in ANY form (canonical, octal, hex, or dotless integer) — inet_aton canonicalizes 127.1,
    # 0177.0.0.1, 0x7f.0.0.1, 2130706433 all to 127.0.0.1, so a disguised loopback cannot be laundered
    # through ipaddress's strict parser. Require the canonical address to be globally routable.
    try:
        return bool(ipaddress.ip_address(socket.inet_ntoa(socket.inet_aton(host))).is_global)
    except OSError:
        pass                                                # not an IPv4 literal in any form
    try:
        return bool(ipaddress.ip_address(host).is_global)   # bare IPv6 literal (rejects ::1 etc.)
    except ValueError:
        pass
    # A DNS name: require a dotted domain whose labels are not all-numeric (an all-numeric dotted string
    # is a malformed/disguised IP, never a real host). Live resolution is enforced at the network layer.
    if "." not in host or all(all(c in "0123456789" for c in label) for label in host.split(".")):
        return False
    return True


def _b58decode(label: str, text: object, *, exact_length: int) -> bytes:
    value = _text(label, text)
    number = 0
    for char in value:
        if char not in _B58_ALPHABET:
            raise CalibrationRefused(f"{label} is not base58")
        number = number * 58 + _B58_ALPHABET.index(char)
    raw = number.to_bytes((number.bit_length() + 7) // 8, "big") if number else b""
    decoded = bytes([0]) * (len(value) - len(value.lstrip("1"))) + raw
    if len(decoded) != exact_length:
        raise CalibrationRefused(f"{label} does not decode to {exact_length} bytes")
    return decoded


def _b58encode(raw: bytes) -> str:
    number = int.from_bytes(raw, "big")
    out = ""
    while number:
        number, remainder = divmod(number, 58)
        out = _B58_ALPHABET[remainder] + out
    prefix = "1" * (len(raw) - len(raw.lstrip(bytes([0]))))
    return prefix + out if prefix or out else "1"


def _shortvec(raw: bytes, offset: int) -> tuple[int, int]:
    value = 0
    shift = 0
    for _ in range(3):
        if offset >= len(raw):
            raise CalibrationRefused("wire transaction has a truncated shortvec")
        byte = raw[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, offset
        shift += 7
    raise CalibrationRefused("wire transaction has a non-canonical shortvec")


def _campaign_memo(campaign_id: str, index: int, previous_sample_id: str) -> bytes:
    challenge = hashlib.sha256(
        f"{campaign_id}|{index}|{previous_sample_id}".encode("ascii")).hexdigest()
    return f"PACV2|{challenge}".encode("ascii")


def _wire_identity(encoded: object, *, expected_memo: bytes | None = None) -> tuple[bytes, str, str]:
    try:
        wire = base64.b64decode(_text("wire_transaction_base64", encoded), validate=True)
    except (ValueError, TypeError) as exc:
        raise CalibrationRefused("wire transaction is not canonical base64") from exc
    count, message_offset = _shortvec(wire, 0)
    if count < 1 or count > 32 or message_offset + count * 64 >= len(wire):
        raise CalibrationRefused("wire transaction signature vector is invalid")
    signature = wire[message_offset:message_offset + 64]
    message_offset += count * 64
    message_start = message_offset
    if wire[message_offset] & 0x80:
        raise CalibrationRefused("calibration transaction must use the frozen legacy profile")
    if message_offset + 3 >= len(wire):
        raise CalibrationRefused("wire transaction message header is truncated")
    required_signers = wire[message_offset]
    readonly_signed = wire[message_offset + 1]
    readonly_unsigned = wire[message_offset + 2]
    if required_signers != count:
        raise CalibrationRefused("wire transaction signatures do not match required signers")
    message_offset += 3
    account_count, message_offset = _shortvec(wire, message_offset)
    if account_count < 1 or message_offset + account_count * 32 + 32 > len(wire):
        raise CalibrationRefused("wire transaction account vector is invalid")
    accounts = tuple(wire[message_offset + offset * 32:message_offset + (offset + 1) * 32]
                     for offset in range(account_count))
    fee_payer = accounts[0]
    message_offset += account_count * 32 + 32  # static keys plus recent blockhash
    instruction_count, message_offset = _shortvec(wire, message_offset)
    instructions: list[tuple[int, tuple[int, ...], bytes]] = []
    for _ in range(instruction_count):
        if message_offset >= len(wire):
            raise CalibrationRefused("wire transaction instruction is truncated")
        program_index = wire[message_offset]
        message_offset += 1
        account_index_count, message_offset = _shortvec(wire, message_offset)
        if message_offset + account_index_count > len(wire):
            raise CalibrationRefused("wire transaction instruction accounts are truncated")
        instruction_accounts = tuple(wire[message_offset:message_offset + account_index_count])
        message_offset += account_index_count
        data_length, message_offset = _shortvec(wire, message_offset)
        if message_offset + data_length > len(wire):
            raise CalibrationRefused("wire transaction instruction data is truncated")
        data = wire[message_offset:message_offset + data_length]
        message_offset += data_length
        if program_index >= len(accounts) or any(index >= len(accounts) for index in instruction_accounts):
            raise CalibrationRefused("wire transaction instruction references an unknown account")
        instructions.append((program_index, instruction_accounts, data))
    if message_offset != len(wire):
        raise CalibrationRefused("wire transaction has trailing or unsupported message bytes")
    if expected_memo is not None:
        memo_program = _b58decode("memo program id", MEMO_PROGRAM_ID, exact_length=32)
        if (count != 1 or required_signers != 1 or readonly_signed != 0
                or readonly_unsigned != 1 or accounts != (fee_payer, memo_program)
                or instructions != [(1, (), expected_memo)]):
            raise CalibrationRefused(
                "wire transaction is not the frozen campaign-bound memo-only profile")
    # The fee payer (accounts[0]) must have produced a valid ed25519 signature over the message bytes.
    # This closes the "any 64 bytes as a signature" forgery: a bundle now requires a real keypair that
    # actually signed the memo message, not an arbitrary string. (On-chain landing is separately proven
    # by the live finalized-RPC verification wired into activation.)
    try:
        Ed25519PublicKey.from_public_bytes(fee_payer).verify(signature, wire[message_start:])
    except InvalidSignature as exc:
        raise CalibrationRefused(
            "wire transaction signature is not a valid ed25519 signature by the fee payer") from exc
    except ValueError as exc:
        raise CalibrationRefused(
            "wire transaction fee-payer key is not a valid ed25519 public key") from exc
    return wire, _b58encode(signature), _b58encode(fee_payer)


def _read_bytes(path: pathlib.Path, *, expected_sha256: str, label: str) -> bytes:
    expected = _sha(f"{label} pin", expected_sha256)
    try:
        payload = pathlib.Path(path).read_bytes()
    except OSError as exc:
        raise CalibrationRefused(f"{label} unavailable: {exc}") from exc
    actual = hashlib.sha256(payload).hexdigest()
    if actual != expected:
        raise CalibrationRefused(f"{label} hashes {actual}, expected anchored pin {expected}")
    return payload


def _json_object(payload: bytes, label: str) -> dict:
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise CalibrationRefused(f"{label} is invalid JSON") from exc
    if not isinstance(value, dict):
        raise CalibrationRefused(f"{label} must be an object")
    return value


def _jsonl(payload: bytes, label: str) -> list[dict]:
    rows: list[dict] = []
    for number, raw in enumerate(payload.splitlines(), 1):
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise CalibrationRefused(f"{label} line {number} is invalid JSON") from exc
        if not isinstance(row, dict):
            raise CalibrationRefused(f"{label} line {number} is not an object")
        rows.append(row)
    return rows


@dataclass(frozen=True)
class ArtifactPins:
    campaign_sha256: str
    calibration_sha256: str
    attestation_sha256: str

    def __post_init__(self) -> None:
        _sha("campaign pin", self.campaign_sha256)
        _sha("calibration pin", self.calibration_sha256)
        _sha("attestation pin", self.attestation_sha256)


@dataclass(frozen=True)
class Campaign:
    campaign_id: str
    seal_sha256: str
    calibration_fee_payer: str
    submit_endpoint_scheme_host: str
    verification_endpoint_scheme_host: str
    started_unix_nanos: int
    campaign_sha256: str


@dataclass(frozen=True)
class Calibration:
    artifact_sha256: str
    attestation_sha256: str
    campaign_sha256: str
    campaign_id: str
    landed_samples: int
    failed_samples: int
    reaction_p90_nanos: int
    first_decision_unix_nanos: int
    last_land_unix_nanos: int
    last_attested_unix_nanos: int


def load_campaign(path: pathlib.Path, *, expected_sha256: str) -> Campaign:
    payload = _read_bytes(path, expected_sha256=expected_sha256, label="campaign manifest")
    row = _json_object(payload, "campaign manifest")
    stored = row.get("campaign_sha256")
    body = dict(row)
    body.pop("campaign_sha256", None)
    required = {"schema", "instrument_id", "campaign_id", "seal_sha256",
                "calibration_fee_payer", "submit_endpoint_scheme_host",
                "verification_endpoint_scheme_host", "started_unix_nanos",
                "evidence_mode", "transaction_profile", "memo_program_id"}
    if (set(body) != required or body.get("schema") != CAMPAIGN_SCHEMA
            or body.get("instrument_id") != INSTRUMENT
            or body.get("evidence_mode") != "LOCAL_MONOTONIC_PLUS_FINALIZED_INDEPENDENT_RPC"
            or body.get("transaction_profile") != TRANSACTION_PROFILE
            or body.get("memo_program_id") != MEMO_PROGRAM_ID
            or stored != _canonical_sha(body)):
        raise CalibrationRefused("campaign manifest is malformed or self-hash mismatched")
    campaign_id = _sha("campaign_id", body["campaign_id"])
    seal = _sha("campaign seal", body["seal_sha256"])
    _b58decode("calibration_fee_payer", body["calibration_fee_payer"], exact_length=32)
    submit = _text("submit endpoint", body["submit_endpoint_scheme_host"])
    verify = _text("verification endpoint", body["verification_endpoint_scheme_host"])
    def strict_origin(value: str) -> str | None:
        parsed = urllib.parse.urlsplit(value)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                or parsed.path not in {"", "/"} or parsed.query or parsed.fragment
                or not _is_public_rpc_host(parsed.hostname)):
            return None
        port = f":{parsed.port}" if parsed.port is not None else ""
        return f"https://{parsed.hostname}{port}"
    if strict_origin(submit) != submit or strict_origin(verify) != verify or submit == verify:
        raise CalibrationRefused(
            "campaign must use distinct HTTPS submit and verification origins on genuine public hosts")
    started = _integer("campaign started clock", body["started_unix_nanos"], minimum=1)
    return Campaign(campaign_id, seal, body["calibration_fee_payer"], submit, verify,
                    started, hashlib.sha256(payload).hexdigest())


def _validate_clocks(row: dict, index: int) -> tuple[int, int, int]:
    names = ("decision", "build_start", "sign_done", "send_start", "send_ack", "land_observed")
    wall = row.get("clocks_unix_nanos")
    mono = row.get("clocks_monotonic_nanos")
    if not isinstance(wall, dict) or set(wall) != set(names):
        raise CalibrationRefused(f"sample[{index}] wall clock set is invalid")
    if not isinstance(mono, dict) or set(mono) != set(names):
        raise CalibrationRefused(f"sample[{index}] monotonic clock set is invalid")
    wall_values = [_integer(f"sample[{index}].wall.{name}", wall[name], minimum=1) for name in names]
    mono_values = [_integer(f"sample[{index}].mono.{name}", mono[name], minimum=1) for name in names]
    if any(right < left for left, right in zip(wall_values, wall_values[1:])):
        raise CalibrationRefused(f"sample[{index}] wall clocks are backward")
    if any(right < left for left, right in zip(mono_values, mono_values[1:])):
        raise CalibrationRefused(f"sample[{index}] monotonic clocks are backward")
    for left in range(len(names) - 1):
        wall_delta = wall_values[left + 1] - wall_values[left]
        mono_delta = mono_values[left + 1] - mono_values[left]
        if abs(wall_delta - mono_delta) > MAX_WALL_MONOTONIC_DRIFT_NANOS:
            raise CalibrationRefused(f"sample[{index}] wall/monotonic interval diverges")
    reaction = mono_values[-1] - mono_values[0]
    if reaction <= 0:
        raise CalibrationRefused(f"sample[{index}] reaction latency is not positive")
    return wall_values[0], wall_values[-1], reaction


def _validate_sample(row: dict, index: int, campaign: Campaign,
                     expected_previous: str) -> dict:
    required = {"schema", "instrument_id", "campaign_id", "previous_sample_id", "sample_id",
                "transaction_signature", "outcome", "land_slot", "clocks_unix_nanos",
                "clocks_monotonic_nanos", "raw_evidence", "raw_evidence_sha256"}
    if (set(row) != required or row.get("schema") != SAMPLE_SCHEMA
            or row.get("instrument_id") != INSTRUMENT or row.get("campaign_id") != campaign.campaign_id
            or row.get("outcome") != "LANDED"):
        raise CalibrationRefused(f"sample[{index}] schema/campaign/outcome is invalid")
    if row.get("previous_sample_id") != expected_previous:
        raise CalibrationRefused(f"sample[{index}] breaks the append-only sample hash chain")
    sample_id = _sha(f"sample[{index}].sample_id", row.get("sample_id"))
    body = dict(row)
    body.pop("sample_id")
    if sample_id != _canonical_sha(body):
        raise CalibrationRefused(f"sample[{index}] content id mismatch")
    signature_raw = _b58decode(
        f"sample[{index}].transaction_signature", row.get("transaction_signature"), exact_length=64)
    land_slot = _integer(f"sample[{index}].land_slot", row.get("land_slot"), minimum=1)
    decision, land, reaction = _validate_clocks(row, index)
    if decision < campaign.started_unix_nanos:
        raise CalibrationRefused(f"sample[{index}] predates the anchored campaign")
    raw = row.get("raw_evidence")
    if not isinstance(raw, dict) or set(raw) != {
            "wire_transaction_base64", "wire_transaction_sha256",
            "send_request_json", "send_request_sha256",
            "send_response_json", "send_response_sha256"}:
        raise CalibrationRefused(f"sample[{index}] raw execution evidence is incomplete")
    if _canonical_sha(raw) != _sha(
            f"sample[{index}].raw_evidence_sha256", row.get("raw_evidence_sha256")):
        raise CalibrationRefused(f"sample[{index}] raw evidence hash mismatch")
    wire, wire_signature, fee_payer = _wire_identity(
        raw["wire_transaction_base64"],
        expected_memo=_campaign_memo(campaign.campaign_id, index, expected_previous))
    if hashlib.sha256(wire).hexdigest() != _sha(
            f"sample[{index}].wire_transaction_sha256", raw["wire_transaction_sha256"]):
        raise CalibrationRefused(f"sample[{index}] wire transaction hash mismatch")
    if wire_signature != _b58encode(signature_raw) or fee_payer != campaign.calibration_fee_payer:
        raise CalibrationRefused(f"sample[{index}] wire signature/fee payer is not campaign-bound")
    request = raw["send_request_json"]
    response = raw["send_response_json"]
    if (not isinstance(request, dict) or request.get("method") != "sendTransaction"
            or not isinstance(request.get("params"), list) or not request["params"]
            or request["params"][0] != raw["wire_transaction_base64"]
            or _canonical_sha(request) != _sha(
                f"sample[{index}].send_request_sha256", raw["send_request_sha256"])):
        raise CalibrationRefused(f"sample[{index}] send request does not bind the wire bytes")
    if (not isinstance(response, dict) or response.get("result") != row["transaction_signature"]
            or response.get("error") is not None
            or _canonical_sha(response) != _sha(
                f"sample[{index}].send_response_sha256", raw["send_response_sha256"])):
        raise CalibrationRefused(f"sample[{index}] send response does not acknowledge its signature")
    return {"sample_id": sample_id, "signature": row["transaction_signature"],
            "wire_sha256": hashlib.sha256(wire).hexdigest(), "land_slot": land_slot,
            "decision": decision, "land": land, "reaction": reaction}


def _validate_attestation(row: dict, index: int, campaign: Campaign, sample: dict) -> int:
    required = {"schema", "instrument_id", "campaign_id", "sample_id", "transaction_signature",
                "verification_endpoint_scheme_host", "request_started_unix_nanos",
                "response_received_unix_nanos", "request_json", "response_json",
                "raw_response_sha256", "attestation_id"}
    if (set(row) != required or row.get("schema") != ATTESTATION_SCHEMA
            or row.get("instrument_id") != INSTRUMENT or row.get("campaign_id") != campaign.campaign_id
            or row.get("sample_id") != sample["sample_id"]
            or row.get("transaction_signature") != sample["signature"]
            or row.get("verification_endpoint_scheme_host") != campaign.verification_endpoint_scheme_host):
        raise CalibrationRefused(f"attestation[{index}] identity/source is invalid")
    body = dict(row)
    body.pop("attestation_id", None)
    if _sha(f"attestation[{index}].attestation_id", row.get("attestation_id")) != _canonical_sha(body):
        raise CalibrationRefused(f"attestation[{index}] content id mismatch")
    started = _integer(f"attestation[{index}].request_started",
                       row.get("request_started_unix_nanos"), minimum=1)
    received = _integer(f"attestation[{index}].response_received",
                        row.get("response_received_unix_nanos"), minimum=started)
    if started < sample["land"]:
        raise CalibrationRefused(f"attestation[{index}] was not independently observed after landing")
    request = row.get("request_json")
    response = row.get("response_json")
    if (not isinstance(request, dict) or request.get("method") != "getTransaction"
            or request.get("params") != [sample["signature"], {
                "commitment": "finalized", "encoding": "base64", "maxSupportedTransactionVersion": 0}]):
        raise CalibrationRefused(f"attestation[{index}] request is not the frozen finalized query")
    if _canonical_sha(response) != _sha(
            f"attestation[{index}].raw_response_sha256", row.get("raw_response_sha256")):
        raise CalibrationRefused(f"attestation[{index}] response hash mismatch")
    result = response.get("result") if isinstance(response, dict) and response.get("error") is None else None
    if (not isinstance(result, dict) or result.get("slot") != sample["land_slot"]
            or not isinstance(result.get("blockTime"), int)
            or not isinstance(result.get("meta"), dict) or result["meta"].get("err") is not None):
        raise CalibrationRefused(f"attestation[{index}] does not prove a finalized successful landing")
    tx = result.get("transaction")
    if not isinstance(tx, list) or len(tx) != 2 or tx[1] != "base64":
        raise CalibrationRefused(f"attestation[{index}] does not contain base64 wire bytes")
    wire, signature, fee_payer = _wire_identity(tx[0])
    if (signature != sample["signature"] or fee_payer != campaign.calibration_fee_payer
            or hashlib.sha256(wire).hexdigest() != sample["wire_sha256"]):
        raise CalibrationRefused(f"attestation[{index}] on-chain transaction differs from sent bytes")
    block_nanos = result["blockTime"] * 1_000_000_000
    if abs(sample["land"] - block_nanos) > MAX_BLOCKTIME_DISTANCE_NANOS:
        raise CalibrationRefused(f"attestation[{index}] local land clock is not near on-chain block time")
    return received


def load(calibration_path: pathlib.Path, *, attestation_path: pathlib.Path,
         campaign_path: pathlib.Path, pins: ArtifactPins) -> Calibration:
    """Load one externally pinned, independently attested calibration bundle."""
    campaign = load_campaign(campaign_path, expected_sha256=pins.campaign_sha256)
    calibration_payload = _read_bytes(
        calibration_path, expected_sha256=pins.calibration_sha256, label="calibration artifact")
    attestation_payload = _read_bytes(
        attestation_path, expected_sha256=pins.attestation_sha256, label="attestation artifact")
    raw_samples = _jsonl(calibration_payload, "calibration artifact")
    raw_attestations = _jsonl(attestation_payload, "attestation artifact")
    if len(raw_samples) != len(raw_attestations):
        raise CalibrationRefused("every calibration sample requires exactly one independent attestation")
    samples: list[dict] = []
    previous = campaign.campaign_id
    signatures: set[str] = set()
    for index, row in enumerate(raw_samples):
        sample = _validate_sample(row, index, campaign, previous)
        if sample["signature"] in signatures:
            raise CalibrationRefused("calibration reuses a transaction signature")
        signatures.add(sample["signature"])
        samples.append(sample)
        previous = sample["sample_id"]
    by_sample: dict[str, dict] = {}
    for row in raw_attestations:
        sample_id = row.get("sample_id")
        if not isinstance(sample_id, str) or sample_id in by_sample:
            raise CalibrationRefused("attestation reuses or omits a sample id")
        by_sample[sample_id] = row
    reactions: list[int] = []
    last_attested = 0
    for index, sample in enumerate(samples):
        row = by_sample.get(sample["sample_id"])
        if row is None:
            raise CalibrationRefused("calibration sample lacks its independent attestation")
        last_attested = max(last_attested, _validate_attestation(row, index, campaign, sample))
        reactions.append(sample["reaction"])
    if len(reactions) < MIN_LANDED_SAMPLES:
        raise CalibrationRefused(
            f"calibration has {len(reactions)} authenticated landed samples; {MIN_LANDED_SAMPLES} required")
    ordered = sorted(reactions)
    rank = (9 * len(ordered) + 9) // 10
    return Calibration(
        artifact_sha256=pins.calibration_sha256,
        attestation_sha256=pins.attestation_sha256,
        campaign_sha256=pins.campaign_sha256,
        campaign_id=campaign.campaign_id,
        landed_samples=len(reactions), failed_samples=0,
        reaction_p90_nanos=ordered[rank - 1],
        first_decision_unix_nanos=min(sample["decision"] for sample in samples),
        last_land_unix_nanos=max(sample["land"] for sample in samples),
        last_attested_unix_nanos=last_attested,
    )
