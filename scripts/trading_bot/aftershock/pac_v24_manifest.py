#!/usr/bin/env python3
"""Versioned PAC V2.4 authority reusing the hostile-tested V2.1 campaign machinery.

The cryptographic/evidence implementation is reused under a process-local configuration context; all
V2.1 globals are restored after every call. V2.3 has distinct preregistration, frozen config, seal,
campaign, evidence, activation, runner state and RPC environment names. Its sealed closure extends the
V2.2 low-lag feed with the new read-only PumpSwap venue module and the V2.3 cross-venue adapter.
"""
from __future__ import annotations

from contextlib import contextmanager
import argparse
import json
import pathlib
import threading

from . import pac_v21_attestation as attestation
from . import pac_v21_calibration as calibration
from . import pac_v21_manifest as legacy
from . import pac_v21_send as sender
from . import pac_v24_runner as runner


INSTRUMENT = "AFTERSHOCK_PAC_V24"
ROOT = pathlib.Path(__file__).resolve().parents[3]
RESEARCH = ROOT / "research" / "trading_bot" / "aftershock"
PREREG = RESEARCH / f"{INSTRUMENT}_PREREGISTRATION.md"
FROZEN = RESEARCH / f"{INSTRUMENT}_FROZEN.json"
SEAL = RESEARCH / f"{INSTRUMENT}_SEAL.json"
CAMPAIGN = RESEARCH / f"{INSTRUMENT}_CALIBRATION_CAMPAIGN.json"
JOURNAL = RESEARCH / f"{INSTRUMENT}_CALIBRATION_JOURNAL.json"
SAMPLES = RESEARCH / f"{INSTRUMENT}_CALIBRATION_SAMPLES.jsonl"
ATTESTATIONS = RESEARCH / f"{INSTRUMENT}_ATTESTATIONS.jsonl"
ACTIVATION = RESEARCH / f"{INSTRUMENT}_ACTIVATION.json"
DEPENDENCY_PATHS = (*legacy.DEPENDENCY_PATHS,
                    "scripts/trading_bot/aftershock/pac_v22_feed.py",
                    "scripts/trading_bot/aftershock/pac_v22_feed_selftest.py",
                    "scripts/trading_bot/aftershock/pac_v2_pumpswap.py",
                    "scripts/trading_bot/aftershock/pac_v2_pumpswap_selftest.py",
                    "scripts/trading_bot/aftershock/pac_v24_runner.py",
                    "scripts/trading_bot/aftershock/pac_v24_manifest.py")
_LOCK = threading.RLock()


@contextmanager
def _configured():
    with _LOCK:
        legacy_names = (
            "INSTRUMENT", "ROOT", "RESEARCH", "PREREG", "FROZEN", "SEAL", "CAMPAIGN",
            "JOURNAL", "SAMPLES", "ATTESTATIONS", "ACTIVATION", "DEPENDENCY_PATHS", "runner")
        old_legacy = {name: getattr(legacy, name) for name in legacy_names}
        old_calibration = calibration.INSTRUMENT
        old_attestation_env = attestation.ENV_NAME
        old_sender_env = sender.ENV_SUBMIT
        replacements = {
            "INSTRUMENT": INSTRUMENT, "ROOT": ROOT, "RESEARCH": RESEARCH,
            "PREREG": PREREG, "FROZEN": FROZEN, "SEAL": SEAL, "CAMPAIGN": CAMPAIGN,
            "JOURNAL": JOURNAL, "SAMPLES": SAMPLES, "ATTESTATIONS": ATTESTATIONS,
            "ACTIVATION": ACTIVATION, "DEPENDENCY_PATHS": DEPENDENCY_PATHS, "runner": runner,
        }
        for name, value in replacements.items():
            setattr(legacy, name, value)
        calibration.INSTRUMENT = INSTRUMENT
        attestation.ENV_NAME = "PAC_V24_ATTEST_RPC_URL"
        sender.ENV_SUBMIT = "PAC_V24_SUBMIT_RPC_URL"
        try:
            yield
        finally:
            for name, value in old_legacy.items():
                setattr(legacy, name, value)
            calibration.INSTRUMENT = old_calibration
            attestation.ENV_NAME = old_attestation_env
            sender.ENV_SUBMIT = old_sender_env


def compute_seal() -> dict:
    with _configured():
        return legacy.compute_seal()


def write_seal() -> dict:
    with _configured():
        return legacy.write_seal()


def verify_seal() -> dict:
    with _configured():
        return legacy.verify_seal()


def anchor_status() -> str:
    with _configured():
        return legacy.anchor_status()


def write_campaign(**kwargs) -> dict:
    with _configured():
        return legacy.write_campaign(**kwargs)


def write_activation(**kwargs) -> dict:
    with _configured():
        return legacy.write_activation(**kwargs)


def load_runtime_proof(**kwargs) -> runner.RuntimeProof:
    with _configured():
        return legacy.load_runtime_proof(**kwargs)


def _canonical(value: object) -> bytes:
    return legacy._canonical(value)


def _sha(payload: bytes) -> str:
    return legacy._sha(payload)


def _json(path: pathlib.Path) -> dict:
    return legacy._json(path)


def _git_clean(path: pathlib.Path) -> bool:
    with _configured():
        return legacy._git_clean(path)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="PAC V2.4 seal/campaign/activation authority")
    parser.add_argument("command", choices=("status", "write-seal"))
    args = parser.parse_args(argv)
    if args.command == "write-seal":
        result = write_seal()
    else:
        result = {"seal": anchor_status(), "campaign": CAMPAIGN.exists(),
                  "activation": ACTIVATION.exists()}
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
