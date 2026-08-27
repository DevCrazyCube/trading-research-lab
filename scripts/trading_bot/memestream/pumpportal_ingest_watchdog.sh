#!/usr/bin/env bash
# Keep the PumpPortal candle ingester alive (the FREE-tier-with-funded-key fallback for the dashboard's
# real-time 1s candles when the Chainstack WS is quota-capped). Restarts it only if it died; no-op
# otherwise. READ-ONLY data subscription; the funded api-key is used ONLY to subscribe to trades, never
# to place one. Mirrors chainstack_ingest_watchdog.sh.
cd /home/anont/meme || exit 1
VENV="scripts/trading_bot/memestream/.venv/bin/python"
if ! pgrep -f "memestream.pumpportal_ingest" >/dev/null 2>&1; then
  setsid nohup "$VENV" -m scripts.trading_bot.memestream.pumpportal_ingest \
      >> scripts/trading_bot/memestream/pumpportal_ingest.log 2>&1 < /dev/null &
  echo "$(date -Is) watchdog: pumpportal candle ingester restarted (pid $!)" \
      >> scripts/trading_bot/memestream/pumpportal_ingest_watchdog.log
fi
