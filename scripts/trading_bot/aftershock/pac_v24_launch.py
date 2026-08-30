#!/usr/bin/env python3
"""Persistent operational launcher for the PAC V2.4 runner.

Run as ``python3 -m scripts.trading_bot.aftershock.pac_v24_launch``. This imports the runner as the
package module (never as ``__main__``), so the adapter's manifest-derived ``RuntimeProof`` passes its
``isinstance`` gate — the ``python -m pac_v24_runner`` double-module identity bug is avoided. This file
is not part of the sealed closure and starts nothing but the already-sealed, already-activated runner.
"""
import sys

from scripts.trading_bot.aftershock import pac_v24_runner


if __name__ == "__main__":
    sys.exit(pac_v24_runner.main())
