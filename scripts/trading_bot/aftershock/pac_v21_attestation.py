#!/usr/bin/env python3
"""Independent finalized-RPC attester for PAC V2.1 processed calibration.

This module is read-only: it cannot sign or send.  It first proves that the samples are the exact terminal
projection of the externally pinned attempt journal, then asks the pre-committed independent origin for
the finalized transaction bytes of every processed success.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib

from .execution import RefusedExecution
from . import pac_v2_calibration_attestation as base
from . import pac_v21_calibration as calibration
from . import pac_v21_send as sender


ENV_NAME = "PAC_V21_ATTEST_RPC_URL"


def _project(*, campaign_path: pathlib.Path, campaign_sha256: str,
             journal_path: pathlib.Path, journal_sha256: str,
             samples_path: pathlib.Path, samples_sha256: str):
    campaign = calibration.load_campaign(
        pathlib.Path(campaign_path), expected_sha256=campaign_sha256)
    calibration._read(
        pathlib.Path(journal_path), expected_sha256=journal_sha256,
        label="V2.1 attempt journal")
    try:
        journal = sender.load_journal(pathlib.Path(journal_path), campaign)
    except sender.SendRefused as exc:
        raise RefusedExecution("PAC V2.1 attempt journal refuses before attestation") from exc
    if any(item["stage"] not in {"PROCESSED", "FAILED"} for item in journal["attempts"]):
        raise RefusedExecution("PAC V2.1 cannot attest a campaign with an unclassified attempt")
    payload = calibration._read(
        pathlib.Path(samples_path), expected_sha256=samples_sha256, label="V2.1 samples")
    samples = calibration._jsonl(payload, "V2.1 samples")
    projected = [item["sample"] for item in journal["attempts"] if item["stage"] == "PROCESSED"]
    if samples != projected or len(samples) < calibration.MIN_PROCESSED_SAMPLES:
        raise RefusedExecution("PAC V2.1 samples are not the complete 100+ journal projection")
    return campaign, samples


def attest(*, campaign_path: pathlib.Path, campaign_sha256: str,
           journal_path: pathlib.Path, journal_sha256: str,
           samples_path: pathlib.Path, samples_sha256: str,
           output_path: pathlib.Path, rpc_url: str, opener=None, resolver=None,
           rpc_call=None) -> dict:
    campaign, samples = _project(
        campaign_path=campaign_path, campaign_sha256=campaign_sha256,
        journal_path=journal_path, journal_sha256=journal_sha256,
        samples_path=samples_path, samples_sha256=samples_sha256)
    origin = base._scheme_host(rpc_url, resolver=resolver)
    if origin != campaign.verification_origin or origin == campaign.submit_origin:
        raise RefusedExecution("PAC V2.1 verifier origin differs from the independent campaign origin")
    rows = []
    for index, sample in enumerate(samples):
        request = {"jsonrpc": "2.0", "id": index + 1, "method": "getTransaction",
                   "params": [sample["transaction_signature"], {
                       "commitment": "finalized", "encoding": "base64",
                       "maxSupportedTransactionVersion": 0}]}
        started, received, response = (rpc_call or base._rpc)(
            rpc_url, request, opener=opener)
        body = {
            "schema": calibration.ATTESTATION_SCHEMA,
            "instrument_id": calibration.INSTRUMENT,
            "campaign_id": campaign.campaign_id,
            "sample_id": sample["sample_id"],
            "transaction_signature": sample["transaction_signature"],
            "verification_endpoint_scheme_host": origin,
            "request_started_unix_nanos": started,
            "response_received_unix_nanos": received,
            "request_json": request, "response_json": response,
            "raw_response_sha256": calibration._sha(response),
        }
        rows.append({**body, "attestation_id": calibration._sha(body)})
    base._atomic_write(pathlib.Path(output_path), rows)
    return {
        "rows": len(rows),
        "sha256": hashlib.sha256(pathlib.Path(output_path).read_bytes()).hexdigest(),
        "verification_origin": origin,
    }


def live_verify(*, evidence, campaign, rpc_url: str, opener=None, resolver=None,
                rpc_call=None) -> dict:
    """Re-read every successful finalized transaction at activation; returns a provider-bound digest."""
    origin = base._scheme_host(rpc_url, resolver=resolver)
    if origin != campaign.verification_origin or origin == campaign.submit_origin:
        raise RefusedExecution("PAC V2.1 live verifier origin differs from its campaign authority")
    samples = [item["sample"] for item in evidence["attempts"] if item["stage"] == "PROCESSED"]
    pairs = []
    for index, sample in enumerate(samples):
        request = {"jsonrpc": "2.0", "id": index + 1, "method": "getTransaction",
                   "params": [sample["transaction_signature"], {
                       "commitment": "finalized", "encoding": "base64",
                       "maxSupportedTransactionVersion": 0}]}
        _started, _received, response = (rpc_call or base._rpc)(
            rpc_url, request, opener=opener)
        result = response.get("result") if isinstance(response, dict) else None
        if (not isinstance(result, dict) or result.get("slot") != sample["processed_slot"]
                or not isinstance(result.get("blockTime"), int)
                or not isinstance(result.get("meta"), dict) or result["meta"].get("err") is not None
                or result["meta"].get("fee") != sample["raw_evidence"]["quoted_fee_lamports"]):
            raise RefusedExecution(f"PAC V2.1 live finalized sample {index} identity/cost mismatch")
        transaction = result.get("transaction")
        if not isinstance(transaction, list) or len(transaction) != 2 or transaction[1] != "base64":
            raise RefusedExecution(f"PAC V2.1 live finalized sample {index} lacks wire bytes")
        wire, signature, payer = calibration.base._wire_identity(transaction[0])
        if (signature != sample["transaction_signature"]
                or payer != campaign.calibration_fee_payer
                or hashlib.sha256(wire).hexdigest()
                != sample["raw_evidence"]["wire_transaction_sha256"]):
            raise RefusedExecution(f"PAC V2.1 live finalized sample {index} wire differs")
        pairs.append([signature, result["slot"], result["blockTime"], result["meta"]["fee"]])
    return {"verified": len(pairs), "verification_origin": origin,
            "digest": calibration._sha(sorted(pairs))}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="PAC V2.1 independent finalized attester")
    parser.add_argument("--campaign", required=True, type=pathlib.Path)
    parser.add_argument("--campaign-sha256", required=True)
    parser.add_argument("--journal", required=True, type=pathlib.Path)
    parser.add_argument("--journal-sha256", required=True)
    parser.add_argument("--samples", required=True, type=pathlib.Path)
    parser.add_argument("--samples-sha256", required=True)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    args = parser.parse_args(argv)
    rpc_url = os.environ.get(ENV_NAME)
    if not rpc_url:
        raise SystemExit(f"{ENV_NAME} is required")
    result = attest(
        campaign_path=args.campaign, campaign_sha256=args.campaign_sha256,
        journal_path=args.journal, journal_sha256=args.journal_sha256,
        samples_path=args.samples, samples_sha256=args.samples_sha256,
        output_path=args.output, rpc_url=rpc_url)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
