#!/usr/bin/env python3
"""Single-owner supervisor for the calibrated PAC V2 paper feed and runner.

The preflight loads the complete anchored runtime proof before either child starts. Both children are
then one failure domain: if one exits, the other is terminated and the supervisor exits visibly.
There is no wallet, signer, transaction builder, or submission path.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import pathlib
import signal
import subprocess
import sys
import time

from .execution import RefusedExecution
from . import pac_v2_manifest as manifest


ROOT = pathlib.Path(__file__).resolve().parents[3]
RESEARCH = ROOT / "research" / "trading_bot" / "aftershock"
LOCK = RESEARCH / "AFTERSHOCK_PAC_V2_SUPERVISOR.lock"
FEED_LOG = RESEARCH / "AFTERSHOCK_PAC_V2_FEED.log"
RUNNER_LOG = RESEARCH / "AFTERSHOCK_PAC_V2_RUNNER.log"
POLL_SECONDS = 0.25


def preflight() -> dict:
    proof = manifest.load_runtime_proof()
    return {
        "status": "READY_AUTHENTICATED_PAPER_RUNTIME",
        "seal_sha256": proof.seal_sha256,
        "campaign_id": proof.calibration.campaign_id,
        "calibration_sha256": proof.calibration.artifact_sha256,
        "attestation_sha256": proof.calibration.attestation_sha256,
        "landed_samples": proof.calibration.landed_samples,
        "reaction_p90_nanos": proof.calibration.reaction_p90_nanos,
        "activation_unix_nanos": proof.activation_unix_nanos,
        "boundary": "PAPER_SCENARIO_ONLY_NO_SIGNING_NO_SUBMISSION",
    }


def _lock():
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    handle = LOCK.open("a+")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        handle.close()
        raise RefusedExecution("another PAC V2 supervisor owns the process lock") from exc
    return handle


def _terminate(children: list[subprocess.Popen]) -> None:
    for child in children:
        if child.poll() is None:
            child.terminate()
    deadline = time.monotonic() + 5.0
    for child in children:
        remaining = max(0.0, deadline - time.monotonic())
        try:
            child.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()


def supervise() -> int:
    authority = preflight()
    children: list[subprocess.Popen] = []
    stopping = False

    def stop(_signum, _frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    with _lock():
        FEED_LOG.parent.mkdir(parents=True, exist_ok=True)
        with FEED_LOG.open("ab", buffering=0) as feed_log, RUNNER_LOG.open(
                "ab", buffering=0) as runner_log:
            children = [
                subprocess.Popen(
                    [sys.executable, "-m", "scripts.trading_bot.aftershock.pac_v2_feed"],
                    cwd=ROOT, stdin=subprocess.DEVNULL, stdout=feed_log,
                    stderr=subprocess.STDOUT, start_new_session=False),
                subprocess.Popen(
                    [sys.executable, "-m", "scripts.trading_bot.aftershock.pac_v2_runner"],
                    cwd=ROOT, stdin=subprocess.DEVNULL, stdout=runner_log,
                    stderr=subprocess.STDOUT, start_new_session=False),
            ]
            print(json.dumps({
                **authority, "status": "ACTIVE_PAPER_SUPERVISOR",
                "feed_pid": children[0].pid, "runner_pid": children[1].pid,
            }, sort_keys=True), flush=True)
            try:
                while not stopping:
                    exits = [child.poll() for child in children]
                    if any(code is not None for code in exits):
                        print(json.dumps({
                            "status": "CHILD_EXITED_FAIL_CLOSED",
                            "feed_exit": exits[0], "runner_exit": exits[1],
                        }, sort_keys=True), flush=True)
                        return 2
                    time.sleep(POLL_SECONDS)
                return 0
            finally:
                _terminate(children)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="PAC V2 authenticated paper supervisor")
    parser.add_argument("--preflight", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.preflight:
            print(json.dumps(preflight(), sort_keys=True))
            return 0
        return supervise()
    except RefusedExecution as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc)[:240]}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
