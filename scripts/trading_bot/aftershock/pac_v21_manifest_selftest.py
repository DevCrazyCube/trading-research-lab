#!/usr/bin/env python3
"""Negative controls for the PAC V2.1 seal and activation authority."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import pathlib
import tempfile

from .execution import RefusedExecution
from . import pac_v21_calibration as calibration
from . import pac_v21_evidence as evidence
from . import pac_v21_manifest as manifest
from . import pac_v21_runner as runner


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
    except (RefusedExecution, FileExistsError):
        check(True, label)
    else:
        raise AssertionError(label)


def activation_fixture() -> tuple[dict, dict, evidence.Evidence]:
    seal = {"seal_sha256": "a" * 64}
    calibrated = calibration.Calibration(
        artifact_sha256="b" * 64,
        attestation_sha256="c" * 64,
        campaign_sha256="d" * 64,
        campaign_id="e" * 64,
        processed_samples=100,
        failed_samples=2,
        processed_p90_nanos=900_000_000,
        first_decision_unix_nanos=1_000_000_000,
        last_processed_unix_nanos=2_000_000_000,
        last_attested_unix_nanos=2_100_000_000,
    )
    closed = evidence.Evidence(
        calibration=calibrated, journal_sha256="f" * 64,
        attempts=102, processed=100, failed=2, budgeted_lamports=510_000)
    body = {
        "schema": 1, "instrument_id": manifest.INSTRUMENT,
        "seal_sha256": seal["seal_sha256"],
        "campaign_sha256": calibrated.campaign_sha256,
        "journal_sha256": closed.journal_sha256,
        "samples_sha256": calibrated.artifact_sha256,
        "attestations_sha256": calibrated.attestation_sha256,
        "activation_unix_nanos": 2_200_000_000,
        "processed_p90_nanos": calibrated.processed_p90_nanos,
        "processed_samples": closed.processed,
        "failed_samples": closed.failed,
        "live_verification_origin": "https://verify.example.com",
        "live_verification_digest": "1" * 64,
    }
    return seal, {**body, "activation_sha256": manifest._sha(manifest._canonical(body))}, closed


def main() -> int:
    seal, activation, closed = activation_fixture()
    manifest._activation_body(activation, seal, closed)
    check(True, "closed causal activation validates")

    refuses(lambda: manifest._activation_body([], seal),
            "non-object activation refuses without type confusion")
    for field, value, label in (
            ("activation_unix_nanos", 2.2, "float activation clock refuses"),
            ("processed_samples", True, "boolean processed count refuses"),
            ("failed_samples", -1, "negative failure count refuses"),
            ("live_verification_digest", "z" * 64, "non-hex live digest refuses")):
        bad = deepcopy(activation); bad[field] = value
        body = dict(bad); body.pop("activation_sha256")
        bad["activation_sha256"] = manifest._sha(manifest._canonical(body))
        refuses(lambda bad=bad: manifest._activation_body(bad, seal, closed), label)

    stale = deepcopy(activation); stale["activation_unix_nanos"] = 2_000_000_000
    body = dict(stale); body.pop("activation_sha256")
    stale["activation_sha256"] = manifest._sha(manifest._canonical(body))
    refuses(lambda: manifest._activation_body(stale, seal, closed),
            "activation at or before evidence refuses")

    forged = deepcopy(activation); forged["processed_samples"] = 101
    body = dict(forged); body.pop("activation_sha256")
    forged["activation_sha256"] = manifest._sha(manifest._canonical(body))
    refuses(lambda: manifest._activation_body(forged, seal, closed),
            "self-consistent activation count differing from evidence refuses")

    runner.RuntimeProof(seal["seal_sha256"], activation["activation_unix_nanos"],
                        closed.calibration)
    check(True, "typed manifest proof admits only post-evidence activation")
    refuses(lambda: runner.RuntimeProof(
        seal["seal_sha256"], closed.calibration.last_attested_unix_nanos,
        closed.calibration), "runtime proof refuses an evidence-time activation")

    original = (manifest.ROOT, manifest.RESEARCH, manifest.PREREG, manifest.FROZEN,
                manifest.SEAL, manifest.CAMPAIGN, manifest.DEPENDENCY_PATHS)
    with tempfile.TemporaryDirectory(prefix="pac_v21_manifest_") as temporary:
        root = pathlib.Path(temporary)
        prereg = root / "prereg.md"; prereg.write_text("precommitted\n")
        dependency = root / "dep.py"; dependency.write_text("VALUE = 1\n")
        frozen = root / "frozen.json"; seal_path = root / "seal.json"
        campaign_path = root / "campaign.json"
        manifest.ROOT, manifest.RESEARCH = root, root
        manifest.PREREG, manifest.FROZEN = prereg, frozen
        manifest.SEAL, manifest.CAMPAIGN = seal_path, campaign_path
        manifest.DEPENDENCY_PATHS = ("dep.py",)
        config = {
            "instrument_id": manifest.INSTRUMENT,
            "preregistration_sha256": hashlib.sha256(prereg.read_bytes()).hexdigest(),
            "dependency_paths": ["dep.py"],
        }
        frozen.write_text(json.dumps(config) + "\n")
        expected = manifest.write_seal()
        check(manifest.verify_seal() == expected and manifest.anchor_status() == "UNANCHORED",
              "seal closes prereg/config/dependency but is not evidence before git anchoring")
        refuses(lambda: manifest.write_campaign(
            calibration_fee_payer="1" * 32,
            submit_origin="https://submit.example.com",
            verification_origin="https://verify.example.com",
            max_transactions=100, max_lamports=500_000),
            "unanchored seal cannot create a campaign authority")
        dependency.write_text("VALUE = 2\n")
        refuses(manifest.verify_seal, "dependency-byte drift refuses the written seal")
        try:
            manifest._exclusive_json(campaign_path, {"once": 1})
            refuses(lambda: manifest._exclusive_json(campaign_path, {"once": 2}),
                    "authority artifact is set-once")
        finally:
            (manifest.ROOT, manifest.RESEARCH, manifest.PREREG, manifest.FROZEN,
             manifest.SEAL, manifest.CAMPAIGN, manifest.DEPENDENCY_PATHS) = original

    print(f"PAC V2.1 MANIFEST SELFTEST: PASS — {CHECKS} checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
