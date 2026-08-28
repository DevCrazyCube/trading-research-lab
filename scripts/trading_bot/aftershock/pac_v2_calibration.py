#!/usr/bin/env python3
"""PAC V2 forward execution-clock calibration contract.

This module cannot create measurements.  It verifies a caller-supplied, append-only artifact made by a
separately authorised build/sign/send/land recorder and derives one exact nearest-rank p90.  Production
PAC V2 refuses while the artifact is absent, unanchored, too small, internally inconsistent, or contains
caller-asserted/fabricated clock labels.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import pathlib


INSTRUMENT = "AFTERSHOCK_PAC_V2"
SCHEMA = 1
MIN_LANDED_SAMPLES = 100
ALLOWED_OUTCOMES = {"LANDED", "FAILED_OBSERVED"}


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


def _canonical_sha(body: dict) -> str:
    return hashlib.sha256(json.dumps(
        body, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


@dataclass(frozen=True)
class Calibration:
    artifact_sha256: str
    landed_samples: int
    failed_samples: int
    reaction_p90_nanos: int
    first_decision_unix_nanos: int
    last_land_unix_nanos: int


def _validate_sample(row: dict, index: int) -> tuple[str, int | None, int, int | None]:
    if not isinstance(row, dict) or row.get("schema") != SCHEMA or row.get("instrument_id") != INSTRUMENT:
        raise CalibrationRefused(f"calibration sample {index} has wrong schema/instrument")
    _sha(f"sample[{index}].sample_id", row.get("sample_id"))
    _text(f"sample[{index}].transaction_signature", row.get("transaction_signature"))
    outcome = row.get("outcome")
    if outcome not in ALLOWED_OUTCOMES:
        raise CalibrationRefused(f"sample[{index}].outcome is invalid")
    clocks = row.get("clocks")
    if not isinstance(clocks, dict):
        raise CalibrationRefused(f"sample[{index}].clocks must be an object")
    names = ("decision_unix_nanos", "build_start_unix_nanos", "sign_done_unix_nanos",
             "send_start_unix_nanos", "send_ack_unix_nanos", "land_observed_unix_nanos")
    values = []
    for name in names:
        value = clocks.get(name)
        if value is None and outcome == "FAILED_OBSERVED" and name == "land_observed_unix_nanos":
            values.append(None)
            continue
        values.append(_integer(f"sample[{index}].{name}", value))
    present = [value for value in values if value is not None]
    if any(right < left for left, right in zip(present, present[1:])):
        raise CalibrationRefused(f"sample[{index}] execution clocks are backward")
    if outcome == "LANDED" and values[-1] is None:
        raise CalibrationRefused(f"sample[{index}] landed without an observed land clock")
    if outcome == "FAILED_OBSERVED" and values[-1] is not None:
        raise CalibrationRefused(f"sample[{index}] failed sample claims a land clock")
    raw = row.get("raw_evidence")
    if not isinstance(raw, dict):
        raise CalibrationRefused(f"sample[{index}].raw_evidence must be an object")
    _sha(f"sample[{index}].raw_evidence_sha256", row.get("raw_evidence_sha256"))
    if _canonical_sha(raw) != row["raw_evidence_sha256"]:
        raise CalibrationRefused(f"sample[{index}] raw evidence hash mismatch")
    expected = _canonical_sha({key: value for key, value in row.items() if key != "sample_id"})
    if expected != row["sample_id"]:
        raise CalibrationRefused(f"sample[{index}] content id mismatch")
    reaction = None if values[-1] is None else values[-1] - values[0]
    if reaction is not None and reaction <= 0:
        raise CalibrationRefused(f"sample[{index}] reaction latency is not positive")
    return outcome, reaction, values[0], values[-1]


def load(path: pathlib.Path, *, expected_sha256: str) -> Calibration:
    expected_sha256 = _sha("expected calibration artifact hash", expected_sha256)
    try:
        payload = pathlib.Path(path).read_bytes()
    except OSError as exc:
        raise CalibrationRefused(f"calibration artifact unavailable: {exc}") from exc
    actual = hashlib.sha256(payload).hexdigest()
    if actual != expected_sha256:
        raise CalibrationRefused(f"calibration artifact hashes {actual}, expected {expected_sha256}")
    rows = []
    for index, raw in enumerate(payload.splitlines(), 1):
        if not raw.strip():
            continue
        try:
            rows.append(json.loads(raw))
        except json.JSONDecodeError as exc:
            raise CalibrationRefused(f"calibration line {index} is invalid JSON") from exc
    ids: set[str] = set()
    signatures: set[str] = set()
    landed: list[int] = []
    failed = 0
    first = None
    last = None
    for index, row in enumerate(rows):
        outcome, reaction, decision, land = _validate_sample(row, index)
        if row["sample_id"] in ids or row["transaction_signature"] in signatures:
            raise CalibrationRefused("calibration reuses a sample id or transaction signature")
        ids.add(row["sample_id"]); signatures.add(row["transaction_signature"])
        first = decision if first is None else min(first, decision)
        if outcome == "LANDED":
            landed.append(int(reaction)); last = land if last is None else max(last, land)
        else:
            failed += 1
    if len(landed) < MIN_LANDED_SAMPLES:
        raise CalibrationRefused(
            f"calibration has {len(landed)} landed samples; {MIN_LANDED_SAMPLES} required")
    ordered = sorted(landed)
    # Exact nearest-rank percentile: ceil(0.90*n), converted to a zero-based index.
    rank = (9 * len(ordered) + 9) // 10
    p90 = ordered[rank - 1]
    return Calibration(actual, len(landed), failed, p90, int(first), int(last))
