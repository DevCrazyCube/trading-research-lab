#!/usr/bin/env python3
"""Isolation and seal controls for the PAC V2.2 authority adapter."""
from __future__ import annotations

import hashlib
import json
import pathlib
import tempfile

from .execution import RefusedExecution
from . import pac_v21_attestation as attestation
from . import pac_v21_calibration as calibration
from . import pac_v21_manifest as legacy
from . import pac_v21_send as sender
from . import pac_v22_manifest as manifest


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


def main() -> int:
    originals = (legacy.INSTRUMENT, calibration.INSTRUMENT, attestation.ENV_NAME,
                 sender.ENV_SUBMIT, legacy.runner)
    with manifest._configured():
        check(legacy.INSTRUMENT == calibration.INSTRUMENT == manifest.INSTRUMENT
              and attestation.ENV_NAME == "PAC_V22_ATTEST_RPC_URL"
              and sender.ENV_SUBMIT == "PAC_V22_SUBMIT_RPC_URL"
              and legacy.runner is manifest.runner,
              "all reused campaign machinery is scoped to V2.2 inside the lock")
    check((legacy.INSTRUMENT, calibration.INSTRUMENT, attestation.ENV_NAME,
           sender.ENV_SUBMIT, legacy.runner) == originals,
          "V2.1 authority globals are restored after every V2.2 call")

    names = ("ROOT", "RESEARCH", "PREREG", "FROZEN", "SEAL", "CAMPAIGN",
             "JOURNAL", "SAMPLES", "ATTESTATIONS", "ACTIVATION", "DEPENDENCY_PATHS")
    production = {name: getattr(manifest, name) for name in names}
    with tempfile.TemporaryDirectory(prefix="pac_v22_manifest_") as td:
        root = pathlib.Path(td)
        prereg = root / "prereg.md"; prereg.write_text("V2.2 precommit\n")
        dependency = root / "dep.py"; dependency.write_text("VALUE = 1\n")
        replacements = {
            "ROOT": root, "RESEARCH": root, "PREREG": prereg,
            "FROZEN": root / "frozen.json", "SEAL": root / "seal.json",
            "CAMPAIGN": root / "campaign.json", "JOURNAL": root / "journal.json",
            "SAMPLES": root / "samples.jsonl", "ATTESTATIONS": root / "attest.jsonl",
            "ACTIVATION": root / "activation.json", "DEPENDENCY_PATHS": ("dep.py",),
        }
        for name, value in replacements.items():
            setattr(manifest, name, value)
        config = {
            "instrument_id": manifest.INSTRUMENT,
            "preregistration_sha256": hashlib.sha256(prereg.read_bytes()).hexdigest(),
            "dependency_paths": ["dep.py"],
        }
        manifest.FROZEN.write_text(json.dumps(config) + "\n")
        try:
            sealed = manifest.write_seal()
            check(manifest.verify_seal() == sealed and manifest.anchor_status() == "UNANCHORED",
                  "V2.2 seal closes its own prereg/config/dependency without claiming anchoring")
            refuses(lambda: manifest.write_campaign(
                calibration_fee_payer="1" * 32,
                submit_origin="https://submit.example.com",
                verification_origin="https://verify.example.com",
                max_transactions=100, max_lamports=500_000),
                "unanchored V2.2 seal cannot authorize a campaign")
            dependency.write_text("VALUE = 2\n")
            refuses(manifest.verify_seal, "V2.2 dependency drift refuses")
        finally:
            for name, value in production.items():
                setattr(manifest, name, value)

    check((legacy.INSTRUMENT, calibration.INSTRUMENT, attestation.ENV_NAME,
           sender.ENV_SUBMIT, legacy.runner) == originals,
          "hostile seal failures cannot leak V2.2 configuration into V2.1")
    print(f"PAC V2.2 MANIFEST SELFTEST: PASS — {CHECKS} checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
