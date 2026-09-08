#!/usr/bin/env bash
# RETIRED 2026-08-27: V1 uses the burned pre-execution-realism resolver.  Preserve ledgers; never
# restart this paper loop.  Reuse this existing cron heartbeat only to keep PAC's read-only SOL/USD
# evidence recorder alive; it has no strategy/order path.
cd /home/anont/meme || exit 1
bash scripts/trading_bot/aftershock/solusd_recorder_watchdog.sh
pkill -TERM -f '^python -m scripts\.trading_bot\.aftershock run --loop --interval 90$' 2>/dev/null || true
exit 0
