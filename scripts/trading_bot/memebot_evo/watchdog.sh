#!/usr/bin/env bash
# RETIRED 2026-08-27: EVO V2 mixed a quota-dead tick oracle with its forward population and is now
# immutable.  Preserve every ledger; never restart this loop.  Future work requires frozen EVO V3.
pkill -TERM -f '^bash scripts/trading_bot/memebot_evo/evolve_loop\.sh$' 2>/dev/null || true
exit 0
