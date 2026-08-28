#!/usr/bin/env python3
"""Read-only operational status for the PAC V2 challenger."""
from __future__ import annotations

import json
import hashlib
import pathlib
import time

from .execution import RefusedExecution
from . import pac_v2_manifest as manifest
from . import pac_v2_runner as runner


def _module_process(module: str) -> bool:
    proc = pathlib.Path("/proc")
    try:
        candidates = tuple(proc.iterdir())
    except OSError:
        return False
    for candidate in candidates:
        if not candidate.name.isdigit():
            continue
        try:
            argv = candidate.joinpath("cmdline").read_bytes().split(bytes([0]))
        except OSError:
            continue
        decoded = [part.decode(errors="replace") for part in argv if part]
        if "-m" in decoded:
            index = decoded.index("-m")
            if index + 1 < len(decoded) and decoded[index + 1] == module:
                return True
    return False


def status() -> dict:
    anchor = manifest.anchor_status()
    campaign_status = "ABSENT"
    if manifest.CAMPAIGN.exists():
        try:
            campaign = manifest.load_campaign(
                manifest.CAMPAIGN,
                expected_sha256=hashlib.sha256(manifest.CAMPAIGN.read_bytes()).hexdigest())
            campaign_status = (
                "ANCHORED_PRE_SAMPLING"
                if manifest._git_clean(manifest.CAMPAIGN)
                and anchor == "ANCHORED"
                and campaign.seal_sha256 == manifest.verify_seal()["seal_sha256"]
                else "UNANCHORED_OR_WRONG_SEAL")
        except (OSError, RefusedExecution, manifest.CalibrationRefused):
            campaign_status = "REFUSED"
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
    supervisor_alive = _module_process(
        "scripts.trading_bot.aftershock.pac_v2_supervisor")
    feed_alive = _module_process("scripts.trading_bot.aftershock.pac_v2_feed")
    runner_alive = _module_process("scripts.trading_bot.aftershock.pac_v2_runner")
    runtime_valid = runtime is not None and state_status not in {
        "REFUSED_WITHOUT_ACTIVE_RUNTIME"} and not state_status.startswith("REFUSED")
    active = runtime_valid and supervisor_alive and feed_alive and runner_alive
    if active:
        operational_status = "ACTIVE_AUTHENTICATED_PAPER_SCENARIO"
    elif runtime_valid:
        operational_status = "READY_AUTHENTICATED_NOT_RUNNING"
    else:
        operational_status = "CALIBRATION_REQUIRED_NOT_ACTIVE"
    if anchor != "ANCHORED":
        next_action = "ANCHOR_REPAIRED_H439_SEAL"
    elif campaign_status == "ABSENT":
        next_action = "CREATE_AND_ANCHOR_PRE_SAMPLING_CAMPAIGN"
    elif campaign_status != "ANCHORED_PRE_SAMPLING":
        next_action = "REPAIR_OR_ANCHOR_CAMPAIGN"
    elif runtime is None:
        next_action = "COLLECT_AND_ATTEST_100_AUTHENTIC_LANDINGS_THEN_ANCHOR_ACTIVATION"
    elif not active:
        next_action = "START_SEALED_SUPERVISOR"
    else:
        next_action = "NONE_RUNNING"
    return {
        "instrument_id": runner.INSTRUMENT,
        "status": operational_status,
        "seal": anchor,
        "activation": "ANCHORED" if runtime is not None else "ABSENT_OR_REFUSED",
        "campaign": campaign_status,
        "calibration": ("PINNED_CAMPAIGN_WIRE_AND_FINALIZED_RPC_ATTESTATION"
                        if runtime is not None
                        else "REQUIRED_100_CAMPAIGN_BOUND_FINALIZED_LANDINGS"),
        "reaction_p90_nanos": runtime.calibration.reaction_p90_nanos if runtime else None,
        "campaign_id": runtime.calibration.campaign_id if runtime else None,
        "attestation_sha256": runtime.calibration.attestation_sha256 if runtime else None,
        "runtime_refusal": runtime_refusal,
        "state": state_status,
        "processes": {
            "supervisor": supervisor_alive,
            "feed": feed_alive,
            "runner": runner_alive,
        },
        "next_required_action": next_action,
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
