#!/usr/bin/env python3
"""Operational package-identity-safe launcher for the sealed PAC V2.5 paper runner."""
import sys

from scripts.trading_bot.aftershock import pac_v25_runner


if __name__ == "__main__":
    sys.exit(pac_v25_runner.main())
