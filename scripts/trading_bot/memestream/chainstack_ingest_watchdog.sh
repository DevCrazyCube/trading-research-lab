#!/usr/bin/env bash
# Keep the Chainstack real-time 1s candle ingester alive (PAPER / READ-ONLY, no wallet/orders).
# Idempotent -- safe to run from cron every couple of minutes. Uses the isolated venv python
# (the system python has no `websockets`). Mirrors bitquery_watchdog.sh.
cd /home/anont/meme || exit 1
VENV="scripts/trading_bot/memestream/.venv/bin/python"
if ! pgrep -f "memestream.chainstack_ingest" >/dev/null 2>&1; then
  setsid nohup "$VENV" -m scripts.trading_bot.memestream.chainstack_ingest \
      >> scripts/trading_bot/memestream/chainstack_ingest.log 2>&1 < /dev/null &
  echo "$(date -Is) watchdog: chainstack candle ingester restarted (pid $!)" \
      >> scripts/trading_bot/memestream/chainstack_ingest_watchdog.log
fi
