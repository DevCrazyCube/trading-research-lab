#!/usr/bin/env bash
# Keep the free public-RPC pump.fun ingester alive (candles + AFTERSHOCK trade tape; key-free). READ-ONLY.
cd /home/anont/meme || exit 1
VENV="scripts/trading_bot/memestream/.venv/bin/python"
if ! pgrep -f "python -m scripts.trading_bot.memestream.rpc_ingest" >/dev/null 2>&1; then
  setsid nohup "$VENV" -m scripts.trading_bot.memestream.rpc_ingest \
      >> scripts/trading_bot/memestream/rpc_ingest.log 2>&1 < /dev/null &
  echo "$(date -Is) watchdog: rpc_ingest restarted (pid $!)" \
      >> scripts/trading_bot/memestream/rpc_ingest_watchdog.log
fi
