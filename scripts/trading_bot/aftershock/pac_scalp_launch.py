#!/usr/bin/env python3
"""Persistent package-import launcher for the PAC scalp runner (dodges the python -m double-module bug)."""
import sys
from scripts.trading_bot.aftershock import pac_scalp_runner
if __name__ == "__main__":
    sys.exit(pac_scalp_runner.main())
