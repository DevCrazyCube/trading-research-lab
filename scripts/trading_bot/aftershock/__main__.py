#!/usr/bin/env python3
"""AFTERSHOCK CLI. PAPER / READ-ONLY: no orders, no wallet, no SOL, free tape only.

    python -m scripts.trading_bot.aftershock selftest
    python -m scripts.trading_bot.aftershock scan            # one entry-scan pass
    python -m scripts.trading_bot.aftershock track           # one resolve pass
    python -m scripts.trading_bot.aftershock run [--loop] [--interval 90]
    python -m scripts.trading_bot.aftershock score
    python -m scripts.trading_bot.aftershock status
    python -m scripts.trading_bot.aftershock run-pac --reaction-nanos N [--loop]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys

from . import frozen, pac_runner, pac_status, scan, scan_v2, scan_v3, scan_v4, scan_v5, scoring
from . import FRAMING
from scripts.trading_bot.memebot import ledger as _ledger

_SELFTESTS = ("ecr_selftest", "detector_selftest", "resolve_scoring_selftest", "integration_selftest",
              "detector_v2_selftest", "detector_v3_selftest", "detector_v4_selftest", "detector_v5_selftest",
              "execution_selftest", "secondary_sell_selftest", "pac_selftest", "pac_feed_selftest",
              "solusd_recorder_selftest", "pac_runner_selftest", "pac_dashboard_selftest",
              "pac_v2_selftest")


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


def cmd_status_pac(_args) -> int:
    return _dump(pac_status.status())


def cmd_run_pac(args) -> int:
    try:
        if args.loop:
            pac_runner.run_loop(reaction_nanos=args.reaction_nanos, interval_seconds=args.interval)
            return 0
        return _dump(pac_runner.run_cycle(reaction_nanos=args.reaction_nanos))
    except pac_runner.RefusedExecution as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc)[:240]}, indent=2))
        return 2


def cmd_run_v2(args) -> int:
    if args.loop:
        scan_v2.run_loop_v2(interval_s=args.interval)
        return 0
    return _dump(scan_v2.run_cycle_v2())


def cmd_status_v2(_args) -> int:
    base = frozen.frozen_spec("AFTERSHOCK_V2")
    for arm in base["arms"]:
        aspec = scan_v2.arm_spec(base, arm)
        try:
            rep = scoring.score(aspec, _ledger.resolved_r_stream(aspec))
            n_open = len(_ledger.open_positions(aspec))
            print(f"[{arm['arm']}:{arm['label']}] " + rep.get("status_line", "?") + f" | open {n_open}")
        except Exception as e:  # noqa: BLE001
            print(f"[{arm['arm']}:{arm['label']}] no data yet ({type(e).__name__}: {str(e)[:80]})")
    return 0


def cmd_score_v2(_args) -> int:
    base = frozen.frozen_spec("AFTERSHOCK_V2")
    out = {}
    for arm in base["arms"]:
        aspec = scan_v2.arm_spec(base, arm)
        out[arm["arm"]] = scoring.score(aspec, _ledger.resolved_r_stream(aspec))
    return _dump(out)


def cmd_run_v3(args) -> int:
    if args.loop:
        scan_v3.run_loop_v3(interval_s=args.interval)
        return 0
    return _dump(scan_v3.run_cycle_v3())


def cmd_status_v3(_args) -> int:
    base = frozen.frozen_spec("AFTERSHOCK_V3")
    for arm in base["arms"]:
        aspec = scan_v3.arm_spec(base, arm)
        try:
            rep = scoring.score(aspec, _ledger.resolved_r_stream(aspec))
            n_open = len(_ledger.open_positions(aspec))
            print(f"[{arm['arm']}:{arm['label']}] " + rep.get("status_line", "?") + f" | open {n_open}")
        except Exception as e:  # noqa: BLE001
            print(f"[{arm['arm']}:{arm['label']}] no data yet ({type(e).__name__}: {str(e)[:80]})")
    return 0


def cmd_score_v3(_args) -> int:
    base = frozen.frozen_spec("AFTERSHOCK_V3")
    out = {}
    for arm in base["arms"]:
        aspec = scan_v3.arm_spec(base, arm)
        out[arm["arm"]] = scoring.score(aspec, _ledger.resolved_r_stream(aspec))
    return _dump(out)


def cmd_run_v4(args) -> int:
    if args.loop:
        scan_v4.run_loop_v4(interval_s=args.interval)
        return 0
    return _dump(scan_v4.run_cycle_v4())


def cmd_status_v4(_args) -> int:
    base = frozen.frozen_spec("AFTERSHOCK_V4")
    for arm in base["arms"]:
        aspec = scan_v4.arm_spec(base, arm)
        try:
            rep = scoring.score(aspec, _ledger.resolved_r_stream(aspec))
            n_open = len(_ledger.open_positions(aspec))
            print(f"[{arm['arm']}:{arm['label']}] " + rep.get("status_line", "?") + f" | open {n_open}")
        except Exception as e:  # noqa: BLE001
            print(f"[{arm['arm']}:{arm['label']}] no data yet ({type(e).__name__}: {str(e)[:80]})")
    return 0


def cmd_score_v4(_args) -> int:
    base = frozen.frozen_spec("AFTERSHOCK_V4")
    out = {}
    for arm in base["arms"]:
        aspec = scan_v4.arm_spec(base, arm)
        out[arm["arm"]] = scoring.score(aspec, _ledger.resolved_r_stream(aspec))
    return _dump(out)


def cmd_run_v5(args) -> int:
    if args.loop:
        scan_v5.run_loop_v5(interval_s=args.interval)
        return 0
    return _dump(scan_v5.run_cycle_v5())


def cmd_status_v5(_args) -> int:
    base = frozen.frozen_spec("AFTERSHOCK_V5")
    for arm in base["arms"]:
        aspec = scan_v5.arm_spec(base, arm)
        try:
            rep = scoring.score(aspec, _ledger.resolved_r_stream(aspec))
            n_open = len(_ledger.open_positions(aspec))
            print(f"[{arm['arm']}:{arm['label']}] " + rep.get("status_line", "?") + f" | open {n_open}")
        except Exception as e:  # noqa: BLE001
            print(f"[{arm['arm']}:{arm['label']}] no data yet ({type(e).__name__}: {str(e)[:80]})")
    return 0


def cmd_score_v5(_args) -> int:
    base = frozen.frozen_spec("AFTERSHOCK_V5")
    out = {}
    for arm in base["arms"]:
        aspec = scan_v5.arm_spec(base, arm)
        out[arm["arm"]] = scoring.score(aspec, _ledger.resolved_r_stream(aspec))
    return _dump(out)


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
    sub.add_parser("status-pac")
    rp = sub.add_parser("run-pac")
    rp.add_argument("--reaction-nanos", type=int, required=True,
                    help="explicit uncalibrated scenario latency; deliberately has no default")
    rp.add_argument("--loop", action="store_true")
    rp.add_argument("--interval", type=float, default=2.0)
    r2 = sub.add_parser("run-v2")           # the 3-arm PAYABLE ABSORPTION forward loop
    r2.add_argument("--loop", action="store_true")
    r2.add_argument("--interval", type=float, default=90.0)
    sub.add_parser("score-v2")
    sub.add_parser("status-v2")
    r3 = sub.add_parser("run-v3")           # the 3-arm QUOTE-HARVEST forward loop
    r3.add_argument("--loop", action="store_true")
    r3.add_argument("--interval", type=float, default=90.0)
    sub.add_parser("score-v3")
    sub.add_parser("status-v3")
    r4 = sub.add_parser("run-v4")           # the 3-arm PROFIT-LOCK forward loop
    r4.add_argument("--loop", action="store_true")
    r4.add_argument("--interval", type=float, default=90.0)
    sub.add_parser("score-v4")
    sub.add_parser("status-v4")
    r5 = sub.add_parser("run-v5")           # the 3-arm SCALE-OUT forward loop
    r5.add_argument("--loop", action="store_true")
    r5.add_argument("--interval", type=float, default=90.0)
    sub.add_parser("score-v5")
    sub.add_parser("status-v5")
    args = ap.parse_args(argv)
    dispatch = {"selftest": cmd_selftest, "scan": cmd_scan, "track": cmd_track,
                "run": cmd_run, "score": cmd_score, "status": cmd_status,
                "status-pac": cmd_status_pac,
                "run-pac": cmd_run_pac,
                "run-v2": cmd_run_v2, "score-v2": cmd_score_v2, "status-v2": cmd_status_v2,
                "run-v3": cmd_run_v3, "score-v3": cmd_score_v3, "status-v3": cmd_status_v3,
                "run-v4": cmd_run_v4, "score-v4": cmd_score_v4, "status-v4": cmd_status_v4,
                "run-v5": cmd_run_v5, "score-v5": cmd_score_v5, "status-v5": cmd_status_v5}
    fn = dispatch.get(args.cmd)
    if fn is None:
        ap.print_help()
        return 2
    return fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
