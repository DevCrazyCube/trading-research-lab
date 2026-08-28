#!/usr/bin/env bash
# Keep the read-only memebot dashboard server alive (127.0.0.1:8791). Idempotent — safe from cron.
cd /home/anont/meme || exit 1
# Match argv fields, not a loose substring: otherwise an inspector/rg command containing the module
# name can impersonate the server and leave port 8791 down indefinitely.
if ! ps -eo args= | awk '$2 == "-m" && $3 == "scripts.trading_bot.memebot.dashboard.server" { found=1 }
  END { exit(found ? 0 : 1) }'; then
  mkdir -p scripts/trading_bot/memebot/dashboard/logs
  setsid nohup python -m scripts.trading_bot.memebot.dashboard.server \
      >> scripts/trading_bot/memebot/dashboard/logs/server.log 2>&1 < /dev/null &
  echo "$(date -Is) watchdog: dashboard restarted (pid $!)" \
      >> scripts/trading_bot/memebot/dashboard/logs/watchdog.log
fi
