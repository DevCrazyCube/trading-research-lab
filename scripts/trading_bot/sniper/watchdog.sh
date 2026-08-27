#!/usr/bin/env bash
# Keep the sniper LIVE PAPER runner alive (dry-run, no wallet/orders). Idempotent — safe from cron.
# Uses the websockets-enabled venv python (system python lacks websockets).
cd /home/anont/meme || exit 1
VENV="scripts/trading_bot/memestream/.venv/bin/python"
if ! pgrep -f "scripts.trading_bot.sniper.run" >/dev/null 2>&1; then
  setsid nohup "$VENV" -m scripts.trading_bot.sniper.run \
      >> scripts/trading_bot/sniper/logs/run.log 2>&1 < /dev/null &
  echo "$(date -Is) watchdog: sniper runner restarted (pid $!)" \
      >> scripts/trading_bot/sniper/logs/watchdog.log
fi
