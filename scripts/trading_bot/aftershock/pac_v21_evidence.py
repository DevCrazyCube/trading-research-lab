#!/usr/bin/env python3
"""Closed PAC V2.1 calibration evidence: journal + samples + independent attestations.

The successful-sample artifact alone is insufficient because it could hide campaign failures.  This
loader externally pins and validates the crash journal, requires every attempt to be terminal, proves the
sample file is the journal's exact deterministic projection, then applies the strict calibration and
finalized-attestation validator.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import pathlib

from . import pac_v21_calibration as calibration
from . import pac_v21_send as sender


@dataclass(frozen=True)
class EvidencePins:
    campaign_sha256: str
    journal_sha256: str
    samples_sha256: str
    attestations_sha256: str

    def __post_init__(self) -> None:
        for label, value in (
                ("campaign", self.campaign_sha256), ("journal", self.journal_sha256),
                ("samples", self.samples_sha256), ("attestations", self.attestations_sha256)):
            calibration._hash(f"{label} pin", value)


@dataclass(frozen=True)
class Evidence:
    calibration: calibration.Calibration
    journal_sha256: str
    attempts: int
    processed: int
    failed: int
    budgeted_lamports: int


def load(*, campaign_path: pathlib.Path, journal_path: pathlib.Path,
         samples_path: pathlib.Path, attestations_path: pathlib.Path,
         pins: EvidencePins) -> Evidence:
    campaign = calibration.load_campaign(
        pathlib.Path(campaign_path), expected_sha256=pins.campaign_sha256)
    journal_payload = calibration._read(
        pathlib.Path(journal_path), expected_sha256=pins.journal_sha256,
        label="V2.1 attempt journal")
    try:
        journal = sender.load_journal(pathlib.Path(journal_path), campaign)
    except sender.SendRefused as exc:
        raise calibration.CalibrationRefused("V2.1 attempt journal refuses") from exc
    if any(item["stage"] not in {"PROCESSED", "FAILED"} for item in journal["attempts"]):
        raise calibration.CalibrationRefused(
            "V2.1 evidence contains an unclassified/non-terminal campaign attempt")
    projected = [item["sample"] for item in journal["attempts"] if item["stage"] == "PROCESSED"]
    sample_payload = calibration._read(
        pathlib.Path(samples_path), expected_sha256=pins.samples_sha256,
        label="V2.1 samples")
    samples = calibration._jsonl(sample_payload, "V2.1 samples")
    if samples != projected:
        raise calibration.CalibrationRefused(
            "V2.1 sample artifact is not the exact terminal-journal projection")
    loaded = calibration.load(
        campaign_path=pathlib.Path(campaign_path), samples_path=pathlib.Path(samples_path),
        attestations_path=pathlib.Path(attestations_path),
        pins=calibration.Pins(
            pins.campaign_sha256, pins.samples_sha256, pins.attestations_sha256))
    failed = sum(item["stage"] == "FAILED" for item in journal["attempts"])
    loaded = replace(loaded, failed_samples=failed)
    return Evidence(
        calibration=loaded,
        journal_sha256=hashlib.sha256(journal_payload).hexdigest(),
        attempts=len(journal["attempts"]), processed=len(projected), failed=failed,
        budgeted_lamports=sum(item["quoted_fee_lamports"] for item in journal["attempts"]),
    )
