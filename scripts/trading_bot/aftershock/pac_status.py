#!/usr/bin/env python3
"""Read-only operational status for the sole memecoin candidate, AFTERSHOCK_PAC_V1."""
from __future__ import annotations

import json
import subprocess
import time

from . import Refused, frozen, manifest, solusd_recorder, tape
from .execution import RefusedExecution


INSTRUMENT = "AFTERSHOCK_PAC_V1"


def _runner_process() -> dict:
    try:
        result = subprocess.run(["ps", "-eo", "args="], capture_output=True, text=True,
                                timeout=5, check=False)
    except (OSError, subprocess.SubprocessError):
        return {"alive": False, "reaction_nanos": None}
    for line in result.stdout.splitlines():
        fields = line.split()
        if (len(fields) >= 3 and fields[0].endswith("python") and fields[1] == "-m"
                and fields[2] == "scripts.trading_bot.aftershock.pac_runner"):
            reaction = None
            if "--reaction-nanos" in fields:
                index = fields.index("--reaction-nanos")
                if index + 1 < len(fields) and fields[index + 1].isdigit():
                    reaction = int(fields[index + 1])
            return {"alive": True, "reaction_nanos": reaction}
    return {"alive": False, "reaction_nanos": None}


def _runner_state_fresh() -> dict:
    path = manifest.RESEARCH / f"{INSTRUMENT}_RUNNER_STATE.json"
    try:
        state = json.loads(path.read_text())
        watermark = state.get("scan_watermark_unix_nanos")
        now = time.time_ns()
        if type(watermark) is not int or watermark > now:
            raise ValueError("invalid/future watermark")
        age = now - watermark
        return {"fresh": age <= 10_000_000_000, "watermark_unix_nanos": watermark,
                "watermark_age_nanos": age, "open": len(state.get("open_positions", [])),
                "pending": len(state.get("pending_orders", []))}
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return {"fresh": False, "watermark_unix_nanos": None, "watermark_age_nanos": None,
                "open": None, "pending": None}


def status() -> dict:
    spec = frozen.frozen_spec(INSTRUMENT)
    computed = manifest.compute_seal(INSTRUMENT)
    written = manifest._seal_path(INSTRUMENT).is_file()
    anchor = manifest.seal_anchor(INSTRUMENT) if written else "UNWRITTEN"
    try:
        proof = manifest.load_session_proof(INSTRUMENT)
        activation = "ANCHORED"
        warmup_scope = proof.warmup_scope
    except Refused:
        activation = "ABSENT_OR_UNANCHORED"
        warmup_scope = spec["execution_realism"].get("warmup_scope")
    try:
        quote = solusd_recorder.latest_observation(decision_unix_nanos=time.time_ns())
        solusd = {"status": "FRESH", "price": quote.value_str,
                  "received_unix_nanos": quote.observed_unix_nanos, "source": quote.source}
    except RefusedExecution as exc:
        solusd = {"status": "REFUSED", "reason": str(exc)}

    causal_files = 0
    for path in tape.TAPE_DIR.glob("*.jsonl"):
        if path.name.startswith("_"):
            continue
        try:
            last = json.loads(path.read_text().splitlines()[-1])
        except (OSError, IndexError, json.JSONDecodeError):
            continue
        if (type(last.get("received_unix_nanos")) is int
                and last.get("observation_source") == "public_rpc_processed"
                and isinstance(last.get("sig"), str) and last["sig"]):
            causal_files += 1
    process = _runner_process()
    runner_state = _runner_state_fresh()
    active = activation == "ANCHORED" and process["alive"] and runner_state["fresh"]
    open_gates = [
        "measured latency/failure calibration",
        "100 resolved discovery positions",
        "untouched confirmation slice",
    ]
    return {
        "instrument": INSTRUMENT,
        "status": "ACTIVE_PAPER_SCENARIO" if active else "READY_NOT_RUNNING",
        "strategy_process": process["alive"],
        "runner_process": process,
        "runner_state": runner_state,
        "runner_core": "READY_PAPER_SCENARIO",
        "runner_audit": "GO_CAUSAL_ALL_COST_CRASH_ATOMIC",
        "latency_calibration": "CALIBRATION_UNCALIBRATED",
        "promotion_discovery_enabled": False,
        "runner_command": "bash scripts/trading_bot/aftershock/pac_runner_supervisor.sh",
        "reaction_nanos": process["reaction_nanos"],
        "scan_interval_millis": 250,
        "session_reverify_max_millis": 5000,
        "boundary": "PAPER SCENARIO ONLY; no wallet/order path",
        "computed_seal_sha256": computed["seal_sha256"],
        "dependency_count": len(computed["dependency_sha256"]),
        "seal": anchor,
        "activation": activation,
        "warmup_scope": warmup_scope,
        "solusd": solusd,
        "tape_files_with_current_causal_schema": causal_files,
        "open_gates": open_gates,
    }


if __name__ == "__main__":
    print(json.dumps(status(), indent=2, sort_keys=True))
