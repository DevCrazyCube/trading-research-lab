#!/usr/bin/env bash
# Keep the Bitquery real-time tick ingester alive (PAPER / READ-ONLY, no wallet/orders).
# Idempotent -- safe to run from cron every couple of minutes. Uses the isolated venv python.
cd /home/anont/meme || exit 1
VENV="scripts/trading_bot/memestream/.venv/bin/python"
if ! pgrep -f "memestream.bitquery_ingest" >/dev/null 2>&1; then
  setsid nohup "$VENV" -m scripts.trading_bot.memestream.bitquery_ingest \
      >> scripts/trading_bot/memestream/bitquery_ingest.log 2>&1 < /dev/null &
  echo "$(date -Is) watchdog: bitquery ingester restarted (pid $!)" \
      >> scripts/trading_bot/memestream/bitquery_watchdog.log
fi
