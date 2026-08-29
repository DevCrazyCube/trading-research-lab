#!/usr/bin/env python3
"""Collect independent finalized-RPC attestations for a PAC V2 calibration artifact.

This is read-only. It cannot build, sign, or send a transaction. The verification endpoint is read
from PAC_V2_ATTEST_RPC_URL so credentials never enter argv or persisted evidence; only its
scheme/host is retained. The endpoint must differ from the campaign's submit origin.
"""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import pathlib
import socket
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

from .execution import RefusedExecution
from . import pac_v2_calibration as calibration


ENV_NAME = "PAC_V2_ATTEST_RPC_URL"
TIMEOUT_SECONDS = 12.0


def _scheme_host(url: str, *, resolver=None) -> str:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise RefusedExecution("PAC V2 attestation requires an HTTPS endpoint without URL credentials")
    if not calibration._is_public_rpc_host(parsed.hostname):
        raise RefusedExecution("PAC V2 attestation endpoint host is not a genuine public endpoint")
    # Definitive independence check: resolve the host as urllib will and refuse if ANY resolved address is
    # loopback/private/link-local. This closes a DNS name (or non-canonical literal) that maps to an
    # operator-controlled fake on this machine. It does NOT prove the provider is independent of the
    # operator — a genuinely independent public verification RPC remains the operator's responsibility.
    resolve = resolver or socket.getaddrinfo
    try:
        infos = resolve(parsed.hostname, parsed.port or 443, proto=socket.IPPROTO_TCP)
    except OSError as exc:
        raise RefusedExecution(
            f"PAC V2 attestation endpoint does not resolve: {type(exc).__name__}") from exc
    for info in infos:
        address = info[4][0].split("%")[0]
        if not ipaddress.ip_address(address).is_global:
            raise RefusedExecution("PAC V2 attestation endpoint resolves to a non-global address")
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


_RETRY_DELAYS = (0.5, 1.0, 2.0, 4.0, 8.0, 12.0)
_TRANSIENT_HTTP = (429, 500, 502, 503, 504)


def _rpc(url: str, request_json: dict, *, opener=None) -> tuple[int, int, dict]:
    """One finalized-RPC call, resilient to TRANSIENT failures (public RPCs rate-limit under bursts of
    getTransaction). Retries 429/5xx and network/timeout errors with backoff; a malformed body or a
    genuine non-transient error still fails closed. Read-only getTransaction is safe to retry."""
    request = urllib.request.Request(
        url, data=calibration._canonical(request_json),
        headers={"Content-Type": "application/json"}, method="POST")
    for attempt in range(len(_RETRY_DELAYS) + 1):
        started = time.time_ns()
        try:
            response = (opener or urllib.request.urlopen)(request, timeout=TIMEOUT_SECONDS)
            with response:
                status = getattr(response, "status", None)
                payload = response.read()
            result = json.loads(payload)
        except urllib.error.HTTPError as exc:
            if exc.code in _TRANSIENT_HTTP and attempt < len(_RETRY_DELAYS):
                time.sleep(_RETRY_DELAYS[attempt]); continue
            raise RefusedExecution("PAC V2 independent RPC attestation failed: HTTPError") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            if attempt < len(_RETRY_DELAYS):
                time.sleep(_RETRY_DELAYS[attempt]); continue
            raise RefusedExecution(
                f"PAC V2 independent RPC attestation failed: {type(exc).__name__}") from exc
        except json.JSONDecodeError as exc:
            raise RefusedExecution("PAC V2 independent RPC attestation returned invalid JSON") from exc
        received = time.time_ns()
        if status != 200 or not isinstance(result, dict):
            if attempt < len(_RETRY_DELAYS):
                time.sleep(_RETRY_DELAYS[attempt]); continue
            raise RefusedExecution("PAC V2 independent RPC attestation returned a non-200/non-object")
        return started, received, result
    raise RefusedExecution("PAC V2 independent RPC attestation exhausted retries")


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


def live_verify(*, campaign_path: pathlib.Path, campaign_sha256: str,
                calibration_path: pathlib.Path, calibration_sha256: str,
                rpc_url: str, opener=None, resolver=None) -> dict:
    """Contact the pre-committed independent finalized RPC LIVE and confirm every sample actually landed
    on chain at its sampled slot with the sampled wire bytes. This is the anchor to on-chain reality that
    survives into activation: a hand-written or never-broadcast bundle fails because getTransaction returns
    no finalized result for signatures that were never sent."""
    campaign = calibration.load_campaign(pathlib.Path(campaign_path), expected_sha256=campaign_sha256)
    origin = _scheme_host(rpc_url, resolver=resolver)
    if origin != campaign.verification_endpoint_scheme_host:
        raise RefusedExecution("PAC V2 verifier endpoint differs from the pre-anchored campaign origin")
    if origin == campaign.submit_endpoint_scheme_host:
        raise RefusedExecution("PAC V2 verifier must be independent from the submit endpoint")
    payload = calibration._read_bytes(
        pathlib.Path(calibration_path), expected_sha256=calibration_sha256, label="calibration artifact")
    rows = calibration._jsonl(payload, "calibration artifact")
    if len(rows) < calibration.MIN_LANDED_SAMPLES:
        raise RefusedExecution(
            f"PAC V2 live verification requires >= {calibration.MIN_LANDED_SAMPLES} samples")
    seen: set[str] = set()
    pairs: list[list] = []
    for index, sample in enumerate(rows):
        signature = sample.get("transaction_signature")
        land_slot = sample.get("land_slot")
        raw = sample.get("raw_evidence")
        wire_sha = raw.get("wire_transaction_sha256") if isinstance(raw, dict) else None
        if (not isinstance(signature, str) or signature in seen or type(land_slot) is not int
                or not isinstance(wire_sha, str)):
            raise RefusedExecution(f"PAC V2 live sample {index} identity is invalid/duplicated")
        seen.add(signature)
        request_json = {"jsonrpc": "2.0", "id": index + 1, "method": "getTransaction",
                        "params": [signature, {"commitment": "finalized", "encoding": "base64",
                                               "maxSupportedTransactionVersion": 0}]}
        _started, _received, response_json = _rpc(rpc_url, request_json, opener=opener)
        result = response_json.get("result") if response_json.get("error") is None else None
        if not isinstance(result, dict) or result.get("slot") != land_slot:
            raise RefusedExecution(f"PAC V2 live sample {index} is not finalized at its sampled slot")
        block_time = result.get("blockTime")
        if type(block_time) is not int:
            raise RefusedExecution(f"PAC V2 live sample {index} lacks a finalized on-chain block time")
        meta = result.get("meta")
        if not isinstance(meta, dict) or meta.get("err") is not None:
            raise RefusedExecution(f"PAC V2 live sample {index} did not succeed on chain")
        tx = result.get("transaction")
        if not isinstance(tx, list) or len(tx) != 2 or tx[1] != "base64":
            raise RefusedExecution(f"PAC V2 live sample {index} lacks base64 wire bytes")
        wire, live_signature, fee_payer = calibration._wire_identity(tx[0])
        if (hashlib.sha256(wire).hexdigest() != wire_sha or live_signature != signature
                or fee_payer != campaign.calibration_fee_payer):
            raise RefusedExecution(f"PAC V2 live sample {index} on-chain tx differs from the sampled bytes")
        # The digest binds PROVIDER-returned on-chain evidence (blockTime), so it cannot be reconstructed
        # from the calibration file alone — only an RPC that actually returned the finalized transaction
        # yields it. The runtime gate recomputes it live and refuses on any mismatch.
        pairs.append([signature, land_slot, block_time])
    return {"verified": len(pairs), "verification_origin": origin,
            "digest": calibration._canonical_sha(sorted(pairs))}


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
