#!/usr/bin/env bash
# RETIRED 2026-08-27: V2 uses the burned pre-execution-realism resolver.  Preserve ledgers; never
# restart this paper loop.  A future instrument must use the sealed causal execution chain.
pkill -TERM -f '^python -m scripts\.trading_bot\.aftershock run-v2 --loop --interval 90$' 2>/dev/null || true
exit 0
