#!/usr/bin/env bash
# Keep the AFTERSHOCK tape-driven scan/track loop alive. PAPER / READ-ONLY: no orders, no wallet, no SOL.
cd /home/anont/meme || exit 1
if ! pgrep -f "aftershock run --loop" >/dev/null 2>&1; then
  setsid nohup python -m scripts.trading_bot.aftershock run --loop --interval 90 \
      >> scripts/trading_bot/aftershock/scan.log 2>&1 < /dev/null &
  echo "$(date -Is) watchdog: aftershock scan loop restarted (pid $!)" \
      >> scripts/trading_bot/aftershock/scan_watchdog.log
fi
