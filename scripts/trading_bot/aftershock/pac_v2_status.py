#!/usr/bin/env python3
"""Read-only operational status for the PAC V2 challenger."""
from __future__ import annotations

import json
import time

from .execution import RefusedExecution
from . import pac_v2_manifest as manifest
from . import pac_v2_runner as runner


def status() -> dict:
    anchor = manifest.anchor_status()
    runtime = None
    runtime_refusal = None
    try:
        runtime = manifest.load_runtime_proof()
    except RefusedExecution as exc:
        runtime_refusal = str(exc)[:240]
    state_status = "ABSENT"
    open_count = pending_count = 0
    if runner.STATE.exists():
        if runtime is None:
            state_status = "REFUSED_WITHOUT_ACTIVE_RUNTIME"
        else:
            try:
                state = json.loads(runner.STATE.read_text())
                runner._validate_state(state, runtime)
                state_status = "VALID"
                open_count = int(state["open_position"] is not None)
                pending_count = int(state["pending_order"] is not None)
            except (OSError, json.JSONDecodeError, RefusedExecution) as exc:
                state_status = f"REFUSED:{str(exc)[:160]}"
    rows = 0
    if runner.LEDGER.exists():
        try:
            for line in runner.LEDGER.read_text().splitlines():
                if not line.strip():
                    continue
                row = json.loads(line); runner._validate_ledger(row); rows += 1
        except (OSError, json.JSONDecodeError, RefusedExecution) as exc:
            state_status = f"REFUSED_LEDGER:{str(exc)[:160]}"
    active = runtime is not None and state_status not in {
        "REFUSED_WITHOUT_ACTIVE_RUNTIME"} and not state_status.startswith("REFUSED")
    return {
        "instrument_id": runner.INSTRUMENT,
        "status": "ACTIVE_PAPER_SCENARIO" if active else "CALIBRATION_REQUIRED_NOT_ACTIVE",
        "seal": anchor,
        "activation": "ANCHORED" if runtime is not None else "ABSENT_OR_REFUSED",
        "calibration": ("PINNED_AUTHENTIC_ARTIFACT" if runtime is not None
                        else "REQUIRED_100_LANDED_FORWARD_CLOCKS"),
        "reaction_p90_nanos": runtime.calibration.reaction_p90_nanos if runtime else None,
        "runtime_refusal": runtime_refusal,
        "state": state_status,
        "open": open_count,
        "pending": pending_count,
        "ledger_rows": rows,
        "entry_formula": "PAC + measured-p90 dwell + ≥3 observed buyers + 6× largest-shock cover",
        "execution": "post-target processed account snapshot; no later trade required",
        "exit": "absolute 12m horizon → 6× capacity → 12% full-position trail",
        "evidence_boundary": "PAPER_SCENARIO_ONLY; no wallet/order path; no performance claim",
        "generated_at": time.time(),
    }


if __name__ == "__main__":
    print(json.dumps(status(), indent=2))
