#!/usr/bin/env python3
"""Independent-source and finalized-byte controls for the PAC V2.1 attester."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import io
import json
import pathlib
import tempfile

from .execution import RefusedExecution
from . import pac_v21_attestation as attestation
from . import pac_v21_calibration as calibration
from .pac_v21_calibration_selftest import bundle
from .pac_v21_evidence_selftest import write_journal
from . import pac_v21_evidence as evidence


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
    except (RefusedExecution, calibration.CalibrationRefused):
        check(True, label)
    else:
        raise AssertionError(label)


class Response(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


class Rpc:
    def __init__(self, by_signature: dict[str, dict]):
        self.by_signature = by_signature
        self.calls = 0

    def __call__(self, request, timeout=None):
        del timeout
        row = json.loads(request.data)
        signature = row["params"][0]
        response = deepcopy(self.by_signature[signature])
        response["id"] = row["id"]
        self.calls += 1
        return Response(calibration._canonical(response))

    def call(self, _url, request, *, opener=None):
        del opener
        signature = request["params"][0]
        response = deepcopy(self.by_signature[signature])
        response["id"] = request["id"]
        self.calls += 1
        started = 2_000_000_000_000_000_000 + self.calls * 2
        return started, started + 1, response


def public_resolver(*_args, **_kwargs):
    return [(2, 1, 6, "", ("8.8.8.8", 443))]


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="pac_v21_attest_") as temporary:
        root = pathlib.Path(temporary)
        campaign_path, samples_path, source_attestations, pins, samples, source_rows = bundle(root)
        campaign = calibration.load_campaign(campaign_path, expected_sha256=pins.campaign_sha256)
        journal_path = root / "journal.json"
        journal_sha = write_journal(journal_path, campaign, samples)
        responses = {row["transaction_signature"]: row["response_json"] for row in source_rows}
        rpc = Rpc(responses)
        output = root / "fresh-attestations.jsonl"
        result = attestation.attest(
            campaign_path=campaign_path, campaign_sha256=pins.campaign_sha256,
            journal_path=journal_path, journal_sha256=journal_sha,
            samples_path=samples_path, samples_sha256=pins.samples_sha256,
            output_path=output, rpc_url="https://verify.example.com/rpc",
            resolver=public_resolver, rpc_call=rpc.call)
        output_sha = hashlib.sha256(output.read_bytes()).hexdigest()
        closed = evidence.load(
            campaign_path=campaign_path, journal_path=journal_path,
            samples_path=samples_path, attestations_path=output,
            pins=evidence.EvidencePins(
                pins.campaign_sha256, journal_sha, pins.samples_sha256, output_sha))
        check(result["rows"] == 100 and rpc.calls == 100 and closed.processed == 100,
              "100 journal-projected samples receive independent finalized attestations")

        journal = json.loads(journal_path.read_text())
        live_rpc = Rpc(responses)
        live = attestation.live_verify(
            evidence=journal, campaign=campaign,
            rpc_url="https://verify.example.com/rpc",
            resolver=public_resolver, rpc_call=live_rpc.call)
        check(live["verified"] == 100 and len(live["digest"]) == 64,
              "activation-time reread binds provider-returned slot/blocktime/fee evidence")

        refuses(lambda: attestation.attest(
            campaign_path=campaign_path, campaign_sha256=pins.campaign_sha256,
            journal_path=journal_path, journal_sha256=journal_sha,
            samples_path=samples_path, samples_sha256=pins.samples_sha256,
            output_path=root / "bad-origin", rpc_url="https://submit.example.com/rpc",
            resolver=public_resolver, rpc_call=rpc.call),
            "submit origin cannot masquerade as the independent verifier")

        bad_responses = deepcopy(responses)
        signature = samples[-1]["transaction_signature"]
        bad_responses[signature]["result"]["transaction"][0] = \
            source_rows[-2]["response_json"]["result"]["transaction"][0]
        bad_rpc = Rpc(bad_responses)
        bad_output = root / "bad-wire.jsonl"
        attestation.attest(
            campaign_path=campaign_path, campaign_sha256=pins.campaign_sha256,
            journal_path=journal_path, journal_sha256=journal_sha,
            samples_path=samples_path, samples_sha256=pins.samples_sha256,
            output_path=bad_output, rpc_url="https://verify.example.com/rpc",
            resolver=public_resolver, rpc_call=bad_rpc.call)
        bad_sha = hashlib.sha256(bad_output.read_bytes()).hexdigest()
        refuses(lambda: evidence.load(
            campaign_path=campaign_path, journal_path=journal_path,
            samples_path=samples_path, attestations_path=bad_output,
            pins=evidence.EvidencePins(
                pins.campaign_sha256, journal_sha, pins.samples_sha256, bad_sha)),
            "finalized wire differing from the processed sample refuses closed evidence")

    print(f"PAC V2.1 ATTESTATION SELFTEST: PASS — {CHECKS} checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
