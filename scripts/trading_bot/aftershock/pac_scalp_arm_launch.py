#!/usr/bin/env python3
"""Persistent package-import launcher for a PAC scalp entry arm.

Dodges the ``python -m`` double-module bug (which breaks the RuntimeProof identity checks) by importing
the runner as a package attribute and forwarding argv.  Usage:  python pac_scalp_arm_launch.py <arm> [--once] [--interval S]
"""
import sys

from scripts.trading_bot.aftershock import pac_scalp_arm_runner


if __name__ == "__main__":
    raise SystemExit(pac_scalp_arm_runner.main(sys.argv[1:]))
