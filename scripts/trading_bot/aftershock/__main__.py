#!/usr/bin/env python3
"""AFTERSHOCK CLI. PAPER / READ-ONLY: no orders, no wallet, no SOL, free tape only.

    python -m scripts.trading_bot.aftershock selftest
    python -m scripts.trading_bot.aftershock scan            # one entry-scan pass
    python -m scripts.trading_bot.aftershock track           # one resolve pass
    python -m scripts.trading_bot.aftershock run [--loop] [--interval 90]
    python -m scripts.trading_bot.aftershock score
    python -m scripts.trading_bot.aftershock status
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys

from . import frozen, scan, scoring
from . import FRAMING
from scripts.trading_bot.memebot import ledger as _ledger

_SELFTESTS = ("ecr_selftest", "detector_selftest", "resolve_scoring_selftest", "integration_selftest")


def _dump(obj) -> int:
    print(json.dumps(obj, indent=2, default=str))
    return 0


def cmd_selftest(_args) -> int:
    ok = True
    for mod in _SELFTESTS:
        print(f"=== {mod} ===")
        rc = subprocess.run([sys.executable, "-m", f"scripts.trading_bot.aftershock.{mod}"]).returncode
        ok &= (rc == 0)
    print("\nAFTERSHOCK SELFTEST: " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


def cmd_scan(_args) -> int:
    return _dump(scan.scan_entries(frozen.frozen_spec("AFTERSHOCK")))


def cmd_track(_args) -> int:
    return _dump(scan.track_open(frozen.frozen_spec("AFTERSHOCK")))


def cmd_run(args) -> int:
    if args.loop:
        scan.run_loop(interval_s=args.interval)
        return 0
    return _dump(scan.run_cycle())


def cmd_score(_args) -> int:
    spec = frozen.frozen_spec("AFTERSHOCK")
    return _dump(scoring.score(spec, _ledger.resolved_r_stream(spec)))


def cmd_status(_args) -> int:
    spec = frozen.frozen_spec("AFTERSHOCK")
    rep = scoring.score(spec, _ledger.resolved_r_stream(spec))
    n_open = len(_ledger.open_positions(spec))
    print(rep["status_line"] + f" | open {n_open}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="aftershock", description=FRAMING)
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("selftest")
    sub.add_parser("scan")
    sub.add_parser("track")
    r = sub.add_parser("run")
    r.add_argument("--loop", action="store_true")
    r.add_argument("--interval", type=float, default=90.0)
    sub.add_parser("score")
    sub.add_parser("status")
    args = ap.parse_args(argv)
    dispatch = {"selftest": cmd_selftest, "scan": cmd_scan, "track": cmd_track,
                "run": cmd_run, "score": cmd_score, "status": cmd_status}
    fn = dispatch.get(args.cmd)
    if fn is None:
        ap.print_help()
        return 2
    return fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
