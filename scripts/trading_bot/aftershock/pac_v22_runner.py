#!/usr/bin/env python3
"""PAC V2.2 paper runner adapter over the low-lag feed and V2.1 strategy rule.

The inherited execution and exit core is unchanged.  This adapter replaces instrument identity,
detector and feed together under one process-local lock.  Entry qualification additionally requires
fresh, hash-valid V2.2 feed health; exit servicing remains available when the entry feed is degraded.
Production refuses until a V2.2 manifest supplies a seal-bound runtime proof.
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
from . import pac_v22_feed as feed


INSTRUMENT = "AFTERSHOCK_PAC_V22"
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
            raise RefusedExecution("PAC V2.2 runtime seal hash is invalid")
        if type(self.activation_unix_nanos) is not int or self.activation_unix_nanos <= 0:
            raise RefusedExecution("PAC V2.2 activation clock is invalid")
        if not isinstance(self.calibration, calibration.Calibration):
            raise RefusedExecution("PAC V2.2 runtime lacks typed processed calibration")
        if max(self.calibration.last_processed_unix_nanos,
               self.calibration.last_attested_unix_nanos) >= self.activation_unix_nanos:
            raise RefusedExecution("PAC V2.2 activation must follow calibration and attestation")


class _DetectorAdapter:
    pac_detector = pac_detector

    @staticmethod
    def qualify(events, *, reaction_p90_nanos: int, quote_input_lamports: int):
        # This check is entry-only: core services open/pending exits before asking the detector for a
        # new candidate, so feed degradation cannot wedge an already-filled paper position.
        feed.load_health(require_fresh=True)
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
        raise RefusedExecution("PAC V2.2 runner requires manifest-derived runtime proof")
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
    with _CONFIG_LOCK:
        originals = core.INSTRUMENT, core.detector, core.feed
        core.INSTRUMENT, core.detector, core.feed = INSTRUMENT, _DETECTOR, feed
        try:
            yield
        finally:
            core.INSTRUMENT, core.detector, core.feed = originals


def _run_once_at(proof: RuntimeProof, provider, *, now: int,
                 quote_input_lamports: int | None = None,
                 state_path: pathlib.Path = STATE, ledger_path: pathlib.Path = LEDGER,
                 events_path: pathlib.Path = feed.EVENTS,
                 receipts_path: pathlib.Path = feed.RECEIPTS,
                 initialize_at_eof: bool = True) -> dict:
    with _configured_core():
        return core._run_once_at(
            _bridge(proof), provider, now=now,
            quote_input_lamports=quote_input_lamports,
            state_path=pathlib.Path(state_path), ledger_path=pathlib.Path(ledger_path),
            events_path=pathlib.Path(events_path), receipts_path=pathlib.Path(receipts_path),
            initialize_at_eof=initialize_at_eof)


def run_once(proof: RuntimeProof, provider, *, quote_input_lamports: int | None = None,
             state_path: pathlib.Path = STATE, ledger_path: pathlib.Path = LEDGER,
             events_path: pathlib.Path = feed.EVENTS,
             receipts_path: pathlib.Path = feed.RECEIPTS,
             initialize_at_eof: bool = True) -> dict:
    return _run_once_at(
        proof, provider, now=time.time_ns(), quote_input_lamports=quote_input_lamports,
        state_path=state_path, ledger_path=ledger_path,
        events_path=events_path, receipts_path=receipts_path,
        initialize_at_eof=initialize_at_eof)


def _lock(path: pathlib.Path = LOCK):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        handle.close()
        raise RefusedExecution("another PAC V2.2 runner owns the state lock") from exc
    return handle


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="PAC V2.2 low-lag paper-scenario runner")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=float, default=SCAN_INTERVAL_SECONDS)
    args = parser.parse_args(argv)
    try:
        from .pac_v22_manifest import load_runtime_proof
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
