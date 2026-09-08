#!/usr/bin/env bash
# RETIRED 2026-08-28: all three sniper strategy books are negative after honest
# costs.  Preserve every ledger; never restart the paper runner.  Read-only
# memestream ingestion remains independent and stays alive.
pkill -TERM -f '^.*python.* -m scripts\.trading_bot\.sniper\.run$' 2>/dev/null || true
exit 0
