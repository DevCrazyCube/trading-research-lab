#!/usr/bin/env python3
"""Independent finalized attester for PAC_SCALP_LL matched calibration.

Every selected processed sample is re-read from the neutral verifier at finalized commitment using
base64 encoding.  Exact transaction bytes, signature, fee, slot ordering, memo, priority fee and tip are
checked again.  Raw RPC bodies stay local; the commit-safe artifact contains only hashes and aggregates.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import time

from .execution import RefusedExecution
from . import pac_scalp_ll_calibration as calibration
from . import pac_scalp_ll_campaign as campaigns
from . import pac_scalp_ll_manifest as manifest
from . import pac_scalp_ll_route as routes


RAW_SCHEMA = 1
ATTESTATION_SCHEMA = 1


class AttestationRefused(RefusedExecution):
    pass


def _file_sha(path: pathlib.Path) -> str:
    try:
        return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
    except OSError as exc:
        raise AttestationRefused("attestation input is unavailable") from exc


def _load_summary(path: pathlib.Path, *, expected_sha256: str,
                  campaign: campaigns.Campaign, raw_journal_path: pathlib.Path,
                  journal: dict) -> dict:
    if _file_sha(path) != expected_sha256:
        raise AttestationRefused("calibration summary differs from its external file pin")
    try:
        row = json.loads(pathlib.Path(path).read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise AttestationRefused("calibration summary is unreadable") from exc
    body = dict(row) if isinstance(row, dict) else {}
    observed = body.pop("summary_sha256", None)
    if (observed != campaigns.sha(body)
            or row.get("instrument_id") != campaigns.INSTRUMENT
            or row.get("campaign_sha256") != campaign.campaign_sha256
            or row.get("evidence_status") != "UNATTESTED_LOCAL_COMPLETE"
            or row.get("attempted_pairs") != campaign.samples_per_arm
            or row.get("raw_journal_sha256") != _file_sha(raw_journal_path)):
        raise AttestationRefused("calibration summary hash/completeness binding refuses")
    recomputed = calibration.summary(journal, campaign, raw_path=raw_journal_path)
    if row != recomputed:
        raise AttestationRefused("calibration summary differs from raw-journal recomputation")
    return row


def _selected_attempts(journal: dict, campaign: campaigns.Campaign) -> list[dict]:
    selected = journal["attempts"][:campaign.samples_per_arm * 2]
    pairs = calibration._attempt_pairs(selected)
    if len(pairs) != campaign.samples_per_arm:
        raise AttestationRefused("finalized attestation requires every frozen matched pair")
    output = [row for pair in pairs for row in pair]
    if len(output) != campaign.samples_per_arm * 2:
        raise AttestationRefused("finalized attestation sample cardinality refuses")
    return output


def _get_transaction(url: str, signature: str, request_id: int, *, rpc) -> tuple[dict, dict]:
    request = {
        "jsonrpc": "2.0", "id": request_id, "method": "getTransaction",
        "params": [signature, {"commitment": "finalized", "encoding": "base64",
                               "maxSupportedTransactionVersion": 0}],
    }
    response = rpc(url, request)
    if (not isinstance(response, dict) or response.get("jsonrpc") != "2.0"
            or response.get("id") != request_id
            or response.get("result") is not None
            and not isinstance(response.get("result"), dict)):
        raise AttestationRefused("finalized getTransaction response envelope refuses")
    return request, response


def _verify_finalized(attempt: dict, response: dict, campaign: campaigns.Campaign) -> dict:
    result = response["result"]
    transaction = result.get("transaction")
    meta = result.get("meta")
    if (type(result.get("slot")) is not int or result["slot"] != attempt["processed_slot"]
            or not isinstance(transaction, list) or len(transaction) != 2
            or transaction[1] != "base64" or transaction[0] != attempt["wire_base64"]
            or not isinstance(meta, dict) or meta.get("err") is not None
            or type(meta.get("fee")) is not int or meta["fee"] != attempt["fee_lamports"]):
        raise AttestationRefused("finalized transaction wire/slot/result/fee mismatch")
    # The local loader already reparsed each wire. Repeat via its real validator at this boundary.
    if not isinstance(campaign, campaigns.Campaign):
        raise AttestationRefused("finalized verification requires a typed campaign")
    calibration._validate_attempt(attempt, campaign, attempt["attempt_index"])
    return {"finalized_slot": result["slot"], "meta_fee_lamports": meta["fee"],
            "raw_response_sha256": campaigns.sha(response)}


def attest(*, campaign_path: pathlib.Path, campaign_file_sha256: str,
           journal_path: pathlib.Path, summary_path: pathlib.Path,
           summary_file_sha256: str, raw_output_path: pathlib.Path,
           attestation_output_path: pathlib.Path, verification_url: str,
           rpc=calibration._rpc, clock=time.time_ns) -> dict:
    manifest.require_exact_path(journal_path, manifest.RAW_JOURNAL, label="raw journal")
    manifest.require_exact_path(
        summary_path, manifest.CALIBRATION_SUMMARY, label="calibration summary")
    manifest.require_exact_path(
        raw_output_path, manifest.RAW_ATTESTATION, label="raw attestation")
    manifest.require_exact_path(
        attestation_output_path, manifest.ATTESTATION, label="attestation")
    campaign = manifest.require_campaign_authority(
        campaign_path, file_sha256=campaign_file_sha256)
    if (campaigns.endpoint_identity(verification_url) != campaign.verification_endpoint_identity
            or campaigns.endpoint_config_sha256(verification_url)
            != campaign.verification_config_sha256):
        raise AttestationRefused("finalized verifier URL differs from the campaign pin")
    journal = calibration.load_journal(journal_path, campaign)
    summary = _load_summary(
        summary_path, expected_sha256=summary_file_sha256,
        campaign=campaign, raw_journal_path=journal_path, journal=journal)
    selected = _selected_attempts(journal, campaign)
    raw_rows = []
    safe_rows = []
    for ordinal, attempt in enumerate(selected):
        started = clock()
        request, response = _get_transaction(
            verification_url, attempt["signature"], ordinal + 1, rpc=rpc)
        finished = clock()
        if response["result"] is None:
            if attempt["stage"] != "FAILED":
                raise AttestationRefused("processed sample is absent at finalized commitment")
            verified = {"finalized_slot": None, "meta_fee_lamports": None,
                        "raw_response_sha256": campaigns.sha(response),
                        "finalized_after_local_failure": False}
        else:
            verified = _verify_finalized(attempt, response, campaign)
            verified["finalized_after_local_failure"] = attempt["stage"] == "FAILED"
        raw_body = {
            "schema": RAW_SCHEMA, "instrument_id": campaigns.INSTRUMENT,
            "campaign_sha256": campaign.campaign_sha256,
            "attempt_sha256": attempt["attempt_sha256"],
            "request_started_unix_nanos": started,
            "response_received_unix_nanos": finished,
            "request_json": request, "response_json": response,
        }
        raw_rows.append({**raw_body, "raw_row_sha256": campaigns.sha(raw_body)})
        safe_rows.append({
            "pair_index": attempt["pair_index"], "arm": attempt["arm"],
            "attempt_sha256": attempt["attempt_sha256"],
            "wire_sha256": attempt["wire_sha256"], **verified,
        })
    calibration._atomic_json(raw_output_path, {
        "schema": RAW_SCHEMA, "instrument_id": campaigns.INSTRUMENT,
        "campaign_sha256": campaign.campaign_sha256, "rows": raw_rows,
    })
    arm_fees = {
        arm: sum(row["meta_fee_lamports"] or 0 for row in safe_rows if row["arm"] == arm)
        for arm in routes.ARMS
    }
    body = {
        "schema": ATTESTATION_SCHEMA, "instrument_id": campaigns.INSTRUMENT,
        "campaign_sha256": campaign.campaign_sha256,
        "calibration_summary_sha256": summary["summary_sha256"],
        "calibration_summary_file_sha256": summary_file_sha256,
        "raw_journal_sha256": _file_sha(journal_path),
        "raw_attestation_sha256": _file_sha(raw_output_path),
        "evidence_status": "FINALIZED_ATTESTED_COMPLETE",
        "attested_attempts": len(safe_rows), "attested_pairs": campaign.samples_per_arm,
        "meta_fee_lamports_by_arm": arm_fees,
        "tip_lamports_by_arm": {
            arm: campaign.samples_per_arm * campaign.profile.tip_lamports for arm in routes.ARMS},
        "selected_attempts": safe_rows,
        "boundary": "FINALIZED_CALIBRATION_ONLY_NO_PUMP_ACCOUNTS_NOT_LIVE_CONTENTION",
    }
    value = {**body, "attestation_sha256": campaigns.sha(body)}
    calibration._atomic_json(attestation_output_path, value)
    return value


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="PAC_SCALP_LL finalized attester")
    parser.add_argument("--campaign", required=True, type=pathlib.Path)
    parser.add_argument("--campaign-file-sha256", required=True)
    parser.add_argument("--journal", required=True, type=pathlib.Path)
    parser.add_argument("--summary", required=True, type=pathlib.Path)
    parser.add_argument("--summary-file-sha256", required=True)
    parser.add_argument("--raw-output", required=True, type=pathlib.Path)
    parser.add_argument("--attestation-output", required=True, type=pathlib.Path)
    parser.add_argument("--verification-url", required=True)
    args = parser.parse_args(argv)
    try:
        result = attest(
            campaign_path=args.campaign, campaign_file_sha256=args.campaign_file_sha256,
            journal_path=args.journal, summary_path=args.summary,
            summary_file_sha256=args.summary_file_sha256, raw_output_path=args.raw_output,
            attestation_output_path=args.attestation_output,
            verification_url=args.verification_url)
    except RefusedExecution as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc)[:240]}, sort_keys=True))
        return 2
    print(json.dumps({"status": "OK", **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
