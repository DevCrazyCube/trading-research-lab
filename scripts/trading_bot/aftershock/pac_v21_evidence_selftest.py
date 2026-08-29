#!/usr/bin/env python3
"""Negative controls for closed PAC V2.1 journal/sample/attestation evidence."""
from __future__ import annotations

import base64
import hashlib
import json
import pathlib
import tempfile

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from . import pac_v2_calibration as wire_schema
from . import pac_v2_send
from . import pac_v21_calibration as calibration
from .pac_v21_calibration_selftest import bundle
from . import pac_v21_evidence as evidence
from . import pac_v21_send as sender


CHECKS = 0


def check(condition: bool, label: str) -> None:
    global CHECKS
    if not condition:
        raise AssertionError(label)
    CHECKS += 1
    print(f"[ok] {label}")


def refuses(fn, label: str) -> None:
    try:
        fn()
    except (calibration.CalibrationRefused, sender.SendRefused):
        check(True, label)
    else:
        raise AssertionError(label)


def write_journal(path: pathlib.Path, campaign, samples: list[dict], *, failure: bool = False,
                  active: bool = False) -> str:
    attempts = []
    for index, sample in enumerate(samples):
        clocks_w = {name: sample["clocks_unix_nanos"][name]
                    for name in ("decision", "build_start", "sign_done", "send_start", "send_ack")}
        clocks_m = {name: sample["clocks_monotonic_nanos"][name]
                    for name in ("decision", "build_start", "sign_done", "send_start", "send_ack")}
        attempts.append(sender._record({
            "schema": sender.ATTEMPT_SCHEMA, "instrument_id": calibration.INSTRUMENT,
            "campaign_id": campaign.campaign_id, "attempt_index": index,
            "previous_sample_id": sample["previous_sample_id"],
            "boot_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "stage": "PROCESSED",
            "transaction_signature": sample["transaction_signature"],
            "quoted_fee_lamports": sample["raw_evidence"]["quoted_fee_lamports"],
            "clocks_unix_nanos": clocks_w, "clocks_monotonic_nanos": clocks_m,
            "raw_evidence": sample["raw_evidence"],
            "status_polls": sample["status_polls"], "sample": sample, "failure": None,
        }))
    if failure or active:
        index = len(attempts)
        previous = samples[-1]["sample_id"]
        private = Ed25519PrivateKey.from_private_bytes(
            hashlib.sha256(b"v21-calibration-key").digest())
        memo = wire_schema._campaign_memo(campaign.campaign_id, index, previous)
        wire_b64, signature = pac_v2_send.build_signed_memo(
            private, campaign.calibration_fee_payer, memo,
            hashlib.sha256(b"failure-blockhash").digest())
        wire = base64.b64decode(wire_b64)
        signature_count, offset = wire_schema._shortvec(wire, 0)
        offset += signature_count * 64
        message_b64 = base64.b64encode(wire[offset:]).decode("ascii")
        fee_request = {"jsonrpc": "2.0", "id": index + 1, "method": "getFeeForMessage",
                       "params": [message_b64, {"commitment": "processed"}]}
        fee_response = {"jsonrpc": "2.0", "id": index + 1,
                        "result": {"context": {"slot": 1}, "value": 5_000}}
        send_request = {"jsonrpc": "2.0", "id": index + 1, "method": "sendTransaction",
                        "params": [wire_b64, {"encoding": "base64", "skipPreflight": False,
                                               "preflightCommitment": "processed"}]}
        raw = {
            "wire_transaction_base64": wire_b64,
            "wire_transaction_sha256": hashlib.sha256(wire).hexdigest(),
            "fee_request_json": fee_request, "fee_request_sha256": calibration._sha(fee_request),
            "fee_response_json": fee_response, "fee_response_sha256": calibration._sha(fee_response),
            "quoted_fee_lamports": 5_000,
            "send_request_json": send_request, "send_request_sha256": calibration._sha(send_request),
            "send_response_json": None, "send_response_sha256": None,
        }
        terminal = not active
        attempts.append(sender._record({
            "schema": sender.ATTEMPT_SCHEMA, "instrument_id": calibration.INSTRUMENT,
            "campaign_id": campaign.campaign_id, "attempt_index": index,
            "previous_sample_id": previous,
            "boot_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "stage": "FAILED" if terminal else "SIGNED",
            "transaction_signature": signature, "quoted_fee_lamports": 5_000,
            "clocks_unix_nanos": {"decision": 2_000_000_000_000_000_000,
                                   "build_start": 2_000_000_000_000_000_001,
                                   "sign_done": 2_000_000_000_000_000_002,
                                   "send_start": None, "send_ack": None},
            "clocks_monotonic_nanos": {"decision": 2_000_000_000,
                                        "build_start": 2_000_000_001,
                                        "sign_done": 2_000_000_002,
                                        "send_start": None, "send_ack": None},
            "raw_evidence": raw, "status_polls": [], "sample": None,
            "failure": ({"stage": "CRASH_RESUME", "reason": "synthetic durable failure",
                         "terminal_unix_nanos": 2_000_000_000_000_000_003,
                         "terminal_monotonic_nanos": 2_000_000_003} if terminal else None),
        }))
    journal = sender._journal_value({
        "schema": sender.JOURNAL_SCHEMA, "instrument_id": calibration.INSTRUMENT,
        "campaign_id": campaign.campaign_id, "campaign_sha256": campaign.artifact_sha256,
        "seal_sha256": campaign.seal_sha256,
        "max_transactions": campaign.max_transactions, "max_lamports": campaign.max_lamports,
        "attempts": attempts,
    })
    path.write_bytes(calibration._canonical(journal) + b"\n")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="pac_v21_evidence_") as temporary:
        root = pathlib.Path(temporary)
        campaign_path, samples_path, attestations_path, pins, samples, _attestations = bundle(root)
        campaign_row = json.loads(campaign_path.read_text())
        campaign_row["max_transactions"] = 101
        campaign_row["max_lamports"] = 505_000
        campaign_body = dict(campaign_row); campaign_body.pop("campaign_sha256")
        campaign_row["campaign_sha256"] = calibration._sha(campaign_body)
        campaign_path.write_bytes(calibration._canonical(campaign_row) + b"\n")
        campaign_pin = hashlib.sha256(campaign_path.read_bytes()).hexdigest()
        campaign = calibration.load_campaign(campaign_path, expected_sha256=campaign_pin)
        journal_path = root / "journal.json"
        journal_sha = write_journal(journal_path, campaign, samples, failure=True)
        closed = evidence.load(
            campaign_path=campaign_path, journal_path=journal_path,
            samples_path=samples_path, attestations_path=attestations_path,
            pins=evidence.EvidencePins(
                campaign_pin, journal_sha, pins.samples_sha256,
                pins.attestations_sha256))
        check(closed.processed == 100 and closed.failed == 1
              and closed.calibration.failed_samples == 1,
              "100 successes plus every terminal failure remain visible in closed evidence")
        check(closed.attempts == 101 and closed.budgeted_lamports == 505_000,
              "journal exposes campaign-wide attempt count and exact quoted-fee budget")

        active_path = root / "active.json"
        active_sha = write_journal(active_path, campaign, samples, active=True)
        refuses(lambda: evidence.load(
            campaign_path=campaign_path, journal_path=active_path,
            samples_path=samples_path, attestations_path=attestations_path,
            pins=evidence.EvidencePins(
                campaign_pin, active_sha, pins.samples_sha256,
                pins.attestations_sha256)),
            "an unclassified pre-send attempt refuses the evidence bundle")

        tampered = journal_path.read_bytes() + b" "
        tampered_path = root / "tampered.json"
        tampered_path.write_bytes(tampered)
        refuses(lambda: evidence.load(
            campaign_path=campaign_path, journal_path=tampered_path,
            samples_path=samples_path, attestations_path=attestations_path,
            pins=evidence.EvidencePins(
                campaign_pin, journal_sha, pins.samples_sha256,
                pins.attestations_sha256)),
            "journal whole-file tamper refuses against its external pin")

        altered_samples = root / "altered-samples.jsonl"
        altered_samples.write_bytes(samples_path.read_bytes() + b"\n")
        altered_sha = hashlib.sha256(altered_samples.read_bytes()).hexdigest()
        # Parsed rows are equal, so this confirms whole-file pins and exact projection are separate:
        # the explicitly supplied altered pin admits byte formatting but never changes any row.
        formatted = evidence.load(
            campaign_path=campaign_path, journal_path=journal_path,
            samples_path=altered_samples, attestations_path=attestations_path,
            pins=evidence.EvidencePins(
                campaign_pin, journal_sha, altered_sha, pins.attestations_sha256))
        check(formatted.processed == 100,
              "externally pinned formatting is accepted only when parsed sample projection is identical")

    print(f"PAC V2.1 EVIDENCE SELFTEST: PASS — {CHECKS} checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
