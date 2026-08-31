#!/usr/bin/env python3
"""Parameterised runner for the PAC scalp anti-exhaustion ENTRY arms (PAPER-SCENARIO).

The 2026-08-31 forensic proved the momentum entry buys exhaustion (82% of fills go straight down);
the convex EXIT works (EXIT_TRAIL +19.85%).  So these arms keep the audited exit/accounting engine
byte-for-byte and swap ONLY the entry gate, to forward-test "buy the reclaim" and "buy early" against
"buy the spike" as a matched comparison.

It reuses :mod:`pac_scalp_runner` (the momentum arm's sealed engine) WITHOUT editing it -- so the
momentum seal stays intact -- by rebinding the three call-time-looked-up module globals
(``INSTRUMENT``, ``detector``, ``MARKS``) for this process only and passing per-arm state/ledger/lock
paths explicitly (those are import-time default args, so they must be overridden at the call site, not
by rebinding).  Every arm inherits the identical V2.4 executor calibration through its own manifest,
so latency modelling is matched across all three arms.
"""
from __future__ import annotations

import argparse
import json
import time

from .execution import RefusedExecution
from . import pac_scalp_runner as base
from . import pac_scalp_detector_dip as _detector_dip
from . import pac_scalp_detector_early as _detector_early
from .pac_v2_snapshot import PublicRpcSnapshotProvider
from .pac_v2_pumpswap import PumpSwapProvider


# arm name -> (instrument id, entry detector module)
ARMS = {
    "dip": ("AFTERSHOCK_PAC_SCALP_DIP", _detector_dip),
    "early": ("AFTERSHOCK_PAC_SCALP_EARLY", _detector_early),
}


def _paths_for(instrument: str):
    state = base.RESEARCH / f"{instrument}_RUNNER_STATE.json"
    ledger = base.RESEARCH / f"{instrument}_SCENARIO_LEDGER.jsonl"
    lock = base.RESEARCH / f"{instrument}_RUNNER.lock"
    marks = base.ROOT / "research" / "data" / "aftershock" / "pac_scalp" / f"marks_{instrument}.jsonl"
    return state, ledger, lock, marks


def configure(arm: str):
    """Rebind the reused engine's call-time globals for THIS arm/process and return its paths+proof."""
    if arm not in ARMS:
        raise RefusedExecution(f"unknown PAC scalp arm: {arm}")
    instrument, detector = ARMS[arm]
    state_path, ledger_path, lock_path, marks_path = _paths_for(instrument)
    # these three are looked up in base's namespace at call time -> rebinding propagates correctly
    base.INSTRUMENT = instrument
    base.detector = detector
    base.MARKS = marks_path
    from . import pac_scalp_arm_manifest as manifest
    proof = manifest.load_runtime_proof(instrument)
    return instrument, state_path, ledger_path, lock_path, proof


def run_once(proof, provider, pumpswap_provider, *, state_path, ledger_path) -> dict:
    return base._run_once_at(proof, provider, pumpswap_provider, now=time.time_ns(),
                             state_path=state_path, ledger_path=ledger_path)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="PAC scalp anti-exhaustion entry arm (paper-scenario)")
    parser.add_argument("arm", choices=tuple(ARMS))
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=float, default=base.SCAN_INTERVAL_SECONDS)
    args = parser.parse_args(argv)
    try:
        instrument, state_path, ledger_path, lock_path, proof = configure(args.arm)
        provider = PublicRpcSnapshotProvider()
        pumpswap_provider = PumpSwapProvider()
        with base._lock(lock_path):
            while True:
                started = time.monotonic()
                try:
                    result = run_once(proof, provider, pumpswap_provider,
                                      state_path=state_path, ledger_path=ledger_path)
                except RefusedExecution as exc:
                    result = {"status": "CYCLE_REFUSED", "reason": str(exc)[:240]}
                result["arm"] = args.arm
                print(json.dumps(result, sort_keys=True), flush=True)
                if args.once:
                    break
                remaining = args.interval - (time.monotonic() - started)
                if remaining > 0:
                    time.sleep(remaining)
        return 0
    except (RefusedExecution, ImportError) as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc)[:240]}, sort_keys=True), flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
