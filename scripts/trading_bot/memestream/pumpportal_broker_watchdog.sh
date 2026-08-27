#!/usr/bin/env bash
# Keep the central PumpPortal broker alive (one keyed connection -> candles + AFTERSHOCK trade tape).
# READ-ONLY; the funded api-key is used only to subscribe, never to trade. Supersedes pumpportal_ingest.
cd /home/anont/meme || exit 1
VENV="scripts/trading_bot/memestream/.venv/bin/python"
if ! pgrep -f "python -m scripts.trading_bot.memestream.pumpportal_broker" >/dev/null 2>&1; then
  setsid nohup "$VENV" -m scripts.trading_bot.memestream.pumpportal_broker \
      >> scripts/trading_bot/memestream/pumpportal_broker.log 2>&1 < /dev/null &
  echo "$(date -Is) watchdog: pumpportal broker restarted (pid $!)" \
      >> scripts/trading_bot/memestream/pumpportal_broker_watchdog.log
fi
