#!/usr/bin/env bash
# RETIRED 2026-08-28: the frozen MEMEBOT variants failed honest-stress or had an
# unavailable exit oracle.  Preserve every ledger; never restart the evaluator.
# The read-only memestream ingesters and dashboard are intentionally separate.
pkill -TERM -f '^bash scripts/trading_bot/memebot/live_loop\.sh$' 2>/dev/null || true
exit 0
