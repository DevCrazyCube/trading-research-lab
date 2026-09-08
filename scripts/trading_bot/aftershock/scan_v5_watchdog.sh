#!/usr/bin/env bash
# Keep the AFTERSHOCK V5 (SCALE-OUT) 3-arm forward loop alive. PAPER/READ-ONLY: no orders/wallet/SOL.
cd /home/anont/meme || exit 1
if ! pgrep -f "aftershock run-v5 --loop" >/dev/null 2>&1; then
  setsid nohup python -m scripts.trading_bot.aftershock run-v5 --loop --interval 90 \
      >> scripts/trading_bot/aftershock/scan_v5.log 2>&1 < /dev/null &
  echo "$(date -Is) watchdog: aftershock V5 loop restarted (pid $!)" >> scripts/trading_bot/aftershock/scan_v5_watchdog.log
fi
