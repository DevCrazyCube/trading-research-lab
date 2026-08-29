#!/usr/bin/env python3
"""Isolated PAC V2.1 PAPER-SCENARIO runner over the audited PAC V2 execution core.

The V2 control module is frozen and must not be edited.  This adapter reuses that causal state machine in
one V2.1 process while replacing only the instrument identity, paths, detector, and calibrated latency
authority.  Configuration is scoped under a process-local lock and restored after every call, so importing
this module cannot mutate V2.  There is no wallet, signer, transaction builder, or order sender here.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
import pathlib
import threading
import time
from types import SimpleNamespace

from .execution import RefusedExecution
from . import pac_detector
from . import pac_v21_calibration as calibration
from . import pac_v21_detector
from . import pac_v2_runner as core


INSTRUMENT = "AFTERSHOCK_PAC_V21"
ROOT = pathlib.Path(__file__).resolve().parents[3]
RESEARCH = ROOT / "research" / "trading_bot" / "aftershock"
STATE = RESEARCH / f"{INSTRUMENT}_RUNNER_STATE.json"
LEDGER = RESEARCH / f"{INSTRUMENT}_SCENARIO_LEDGER.jsonl"
LOCK = RESEARCH / f"{INSTRUMENT}_RUNNER.lock"
SCAN_INTERVAL_SECONDS = core.SCAN_INTERVAL_SECONDS
_CONFIG_LOCK = threading.RLock()


@dataclass(frozen=True)
class RuntimeProof:
    seal_sha256: str
    activation_unix_nanos: int
    calibration: calibration.Calibration

    def __post_init__(self) -> None:
        if (not isinstance(self.seal_sha256, str) or len(self.seal_sha256) != 64
                or any(char not in "0123456789abcdef" for char in self.seal_sha256)):
            raise RefusedExecution("PAC V2.1 runtime seal hash is invalid")
        if type(self.activation_unix_nanos) is not int or self.activation_unix_nanos <= 0:
            raise RefusedExecution("PAC V2.1 activation clock is invalid")
        if not isinstance(self.calibration, calibration.Calibration):
            raise RefusedExecution("PAC V2.1 runtime lacks typed processed calibration")
        if max(self.calibration.last_processed_unix_nanos,
               self.calibration.last_attested_unix_nanos) >= self.activation_unix_nanos:
            raise RefusedExecution("PAC V2.1 activation must follow processed calibration and attestation")


class _DetectorAdapter:
    """Present V2.1 qualification to the unchanged V2 execution-state interface."""

    pac_detector = pac_detector

    @staticmethod
    def qualify(events, *, reaction_p90_nanos: int, quote_input_lamports: int):
        result = pac_v21_detector.qualify(
            events, processed_p90_nanos=reaction_p90_nanos,
            quote_input_lamports=quote_input_lamports)
        if result is None:
            return None
        return SimpleNamespace(
            evidence_indices=result.evidence_indices,
            evidence_event_ids=result.evidence_event_ids,
            dwell_nanos=result.dwell_nanos,
            buyer_breadth=result.buyer_breadth_ex_seller,
            largest_observed_sell_lamports=result.shock_lamports,
            reserve_cover_lamports=result.reserve_cover_lamports,
        )


_DETECTOR = _DetectorAdapter()


def _bridge(proof: RuntimeProof):
    if not isinstance(proof, RuntimeProof):
        raise RefusedExecution("PAC V2.1 runner requires manifest-derived runtime proof")
    authority = SimpleNamespace(
        artifact_sha256=proof.calibration.artifact_sha256,
        reaction_p90_nanos=proof.calibration.processed_p90_nanos,
        last_land_unix_nanos=proof.calibration.last_processed_unix_nanos,
        last_attested_unix_nanos=proof.calibration.last_attested_unix_nanos,
    )
    return SimpleNamespace(
        seal_sha256=proof.seal_sha256,
        activation_unix_nanos=proof.activation_unix_nanos,
        calibration=authority,
    )


@contextmanager
def _configured_core():
    """Temporarily bind the frozen V2 core to V2.1, then restore it even on refusal."""
    with _CONFIG_LOCK:
        original_instrument, original_detector = core.INSTRUMENT, core.detector
        core.INSTRUMENT, core.detector = INSTRUMENT, _DETECTOR
        try:
            yield
        finally:
            core.INSTRUMENT, core.detector = original_instrument, original_detector


def _run_once_at(proof: RuntimeProof, provider, *, now: int,
                 quote_input_lamports: int | None = None,
                 state_path: pathlib.Path = STATE, ledger_path: pathlib.Path = LEDGER,
                 events_path: pathlib.Path = core.feed.EVENTS,
                 receipts_path: pathlib.Path = core.feed.RECEIPTS,
                 initialize_at_eof: bool = True) -> dict:
    """Deterministic test seam. Production uses :func:`run_once` and an engine-owned clock."""
    with _configured_core():
        return core._run_once_at(
            _bridge(proof), provider, now=now,
            quote_input_lamports=quote_input_lamports,
            state_path=pathlib.Path(state_path), ledger_path=pathlib.Path(ledger_path),
            events_path=pathlib.Path(events_path), receipts_path=pathlib.Path(receipts_path),
            initialize_at_eof=initialize_at_eof,
        )


def run_once(proof: RuntimeProof, provider, *, quote_input_lamports: int | None = None,
             state_path: pathlib.Path = STATE, ledger_path: pathlib.Path = LEDGER,
             events_path: pathlib.Path = core.feed.EVENTS,
             receipts_path: pathlib.Path = core.feed.RECEIPTS,
             initialize_at_eof: bool = True) -> dict:
    """Run one causal paper cycle. No caller can supply the production decision clock."""
    return _run_once_at(
        proof, provider, now=time.time_ns(), quote_input_lamports=quote_input_lamports,
        state_path=state_path, ledger_path=ledger_path,
        events_path=events_path, receipts_path=receipts_path,
        initialize_at_eof=initialize_at_eof,
    )


def _lock(path: pathlib.Path = LOCK):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        handle.close()
        raise RefusedExecution("another PAC V2.1 runner owns the state lock") from exc
    return handle


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="PAC V2.1 calibrated paper-scenario runner")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=float, default=SCAN_INTERVAL_SECONDS)
    args = parser.parse_args(argv)
    try:
        from .pac_v21_manifest import load_runtime_proof
        proof = load_runtime_proof()
        provider = core.PublicRpcSnapshotProvider()
        with _lock():
            while True:
                started = time.monotonic()
                try:
                    result = run_once(proof, provider)
                except RefusedExecution as exc:
                    result = {"status": "CYCLE_REFUSED", "reason": str(exc)[:240]}
                    print(core.json.dumps(result, sort_keys=True), flush=True)
                    if args.once:
                        return 2
                else:
                    print(core.json.dumps(result, sort_keys=True), flush=True)
                if args.once:
                    break
                remaining = args.interval - (time.monotonic() - started)
                if remaining > 0:
                    time.sleep(remaining)
        return 0
    except (RefusedExecution, ImportError) as exc:
        print(core.json.dumps({"status": "REFUSED", "reason": str(exc)[:240]}, sort_keys=True),
              flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
