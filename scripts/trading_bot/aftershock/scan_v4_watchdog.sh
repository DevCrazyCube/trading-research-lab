#!/usr/bin/env bash
# Keep the AFTERSHOCK V4 (PROFIT-LOCK) 3-arm forward loop alive. PAPER/READ-ONLY: no orders/wallet/SOL.
cd /home/anont/meme || exit 1
if ! pgrep -f "aftershock run-v4 --loop" >/dev/null 2>&1; then
  setsid nohup python -m scripts.trading_bot.aftershock run-v4 --loop --interval 90 \
      >> scripts/trading_bot/aftershock/scan_v4.log 2>&1 < /dev/null &
  echo "$(date -Is) watchdog: aftershock V4 loop restarted (pid $!)" >> scripts/trading_bot/aftershock/scan_v4_watchdog.log
fi
