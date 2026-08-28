#!/usr/bin/env python3
"""Collect independent finalized-RPC attestations for a PAC V2 calibration artifact.

This is read-only. It cannot build, sign, or send a transaction. The verification endpoint is read
from PAC_V2_ATTEST_RPC_URL so credentials never enter argv or persisted evidence; only its
scheme/host is retained. The endpoint must differ from the campaign's submit origin.
"""
from __future__ import annotations

import argparse
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
from . import pac_v2_calibration as calibration


ENV_NAME = "PAC_V2_ATTEST_RPC_URL"
TIMEOUT_SECONDS = 12.0


def _scheme_host(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise RefusedExecution("PAC V2 attestation requires an HTTPS endpoint without URL credentials")
    port = f":{parsed.port}" if parsed.port is not None else ""
    return f"https://{parsed.hostname}{port}"


def _atomic_write(path: pathlib.Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        dir=path.parent, prefix=".pac_v2_attestation_", suffix=".jsonl")
    try:
        with os.fdopen(descriptor, "wb") as handle:
            for row in rows:
                handle.write(calibration._canonical(row) + bytes([10]))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _rpc(url: str, request_json: dict, *, opener=None) -> tuple[int, int, dict]:
    started = time.time_ns()
    request = urllib.request.Request(
        url, data=calibration._canonical(request_json),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        if opener is None:
            response = urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS)
        else:
            response = opener(request, timeout=TIMEOUT_SECONDS)
        with response:
            status = getattr(response, "status", None)
            payload = response.read()
        result = json.loads(payload)
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise RefusedExecution(f"PAC V2 independent RPC attestation failed: {type(exc).__name__}") from exc
    received = time.time_ns()
    if status != 200 or not isinstance(result, dict):
        raise RefusedExecution("PAC V2 independent RPC attestation returned a non-200/non-object")
    return started, received, result


def attest(*, campaign_path: pathlib.Path, campaign_sha256: str,
           calibration_path: pathlib.Path, calibration_sha256: str,
           output_path: pathlib.Path, rpc_url: str, opener=None) -> dict:
    campaign = calibration.load_campaign(
        campaign_path, expected_sha256=campaign_sha256)
    origin = _scheme_host(rpc_url)
    if origin != campaign.verification_endpoint_scheme_host:
        raise RefusedExecution("PAC V2 verifier endpoint differs from the pre-anchored campaign origin")
    if origin == campaign.submit_endpoint_scheme_host:
        raise RefusedExecution("PAC V2 verifier must be independent from the submit endpoint")
    payload = calibration._read_bytes(
        calibration_path, expected_sha256=calibration_sha256, label="calibration artifact")
    samples = calibration._jsonl(payload, "calibration artifact")
    rows: list[dict] = []
    seen: set[str] = set()
    for index, sample in enumerate(samples):
        signature = sample.get("transaction_signature")
        sample_id = sample.get("sample_id")
        if not isinstance(signature, str) or not isinstance(sample_id, str) or signature in seen:
            raise RefusedExecution(f"PAC V2 calibration sample {index} identity is invalid/duplicated")
        seen.add(signature)
        request_json = {"jsonrpc": "2.0", "id": index + 1, "method": "getTransaction",
                        "params": [signature, {"commitment": "finalized", "encoding": "base64",
                                               "maxSupportedTransactionVersion": 0}]}
        started, received, response_json = _rpc(rpc_url, request_json, opener=opener)
        body = {
            "schema": calibration.ATTESTATION_SCHEMA,
            "instrument_id": calibration.INSTRUMENT,
            "campaign_id": campaign.campaign_id,
            "sample_id": sample_id,
            "transaction_signature": signature,
            "verification_endpoint_scheme_host": origin,
            "request_started_unix_nanos": started,
            "response_received_unix_nanos": received,
            "request_json": request_json,
            "response_json": response_json,
            "raw_response_sha256": calibration._canonical_sha(response_json),
        }
        rows.append({**body, "attestation_id": calibration._canonical_sha(body)})
    _atomic_write(pathlib.Path(output_path), rows)
    return {"rows": len(rows), "sha256": hashlib.sha256(
        pathlib.Path(output_path).read_bytes()).hexdigest(), "verification_origin": origin}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="PAC V2 independent finalized calibration attester")
    parser.add_argument("--campaign", required=True, type=pathlib.Path)
    parser.add_argument("--campaign-sha256", required=True)
    parser.add_argument("--calibration", required=True, type=pathlib.Path)
    parser.add_argument("--calibration-sha256", required=True)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    args = parser.parse_args(argv)
    rpc_url = os.environ.get(ENV_NAME)
    if not rpc_url:
        raise SystemExit(f"{ENV_NAME} is required")
    result = attest(
        campaign_path=args.campaign, campaign_sha256=args.campaign_sha256,
        calibration_path=args.calibration, calibration_sha256=args.calibration_sha256,
        output_path=args.output, rpc_url=rpc_url)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
