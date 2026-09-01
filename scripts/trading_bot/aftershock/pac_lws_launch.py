#!/usr/bin/env python3
"""Persistent package-import launcher for the PAC LWS runner (dodges the python -m double-module bug).

Running the runner as ``python -m scripts.trading_bot.aftershock.pac_lws_runner`` imports it a second
time under the ``__main__`` name, so the manifest-derived ``RuntimeProof`` fails its ``isinstance``
gate against the freshly re-imported dataclass.  Importing the package module here and forwarding
``sys.argv[1:]`` to its ``main`` keeps a single module identity, exactly like ``pac_scalp_launch``.
"""
import sys

from scripts.trading_bot.aftershock import pac_lws_runner

if __name__ == "__main__":
    raise SystemExit(pac_lws_runner.main(sys.argv[1:]))
