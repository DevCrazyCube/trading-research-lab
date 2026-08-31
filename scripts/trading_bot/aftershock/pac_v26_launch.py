#!/usr/bin/env python3
"""Package-identity-safe launcher for the activated PAC V2.6 paper challenger."""
import sys

from scripts.trading_bot.aftershock import pac_v26_runner


if __name__ == "__main__":
    sys.exit(pac_v26_runner.main())
