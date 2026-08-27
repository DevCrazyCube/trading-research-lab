#!/usr/bin/env python3
"""Thin launcher: run orphanflush_depthq design harness, timestamp start/end into a status file."""
from __future__ import annotations

import json
import subprocess
import sys
import time
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
RESULT_DIR = HERE.parents[1] / "research" / "trading_bot"
STATUS = RESULT_DIR / "depthq_design_run_status.json"


def main():
    t0 = time.time()
    STATUS.write_text(json.dumps({"phase": "running", "started": t0,
                                  "started_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t0))},
                                 indent=1))
    proc = subprocess.run([sys.executable, str(HERE / "orphanflush_depthq.py"),
                           "--window", "design"],
                          capture_output=True, text=True)
    elapsed = time.time() - t0
    (RESULT_DIR / "depthq_design_run.stdout.log").write_text(proc.stdout)
    (RESULT_DIR / "depthq_design_run.stderr.log").write_text(proc.stderr)
    STATUS.write_text(json.dumps({
        "phase": "done" if proc.returncode == 0 else "error",
        "returncode": proc.returncode,
        "elapsed_s": round(elapsed, 1),
        "started_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t0)),
        "ended_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }, indent=1))
    print(proc.stdout)
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
