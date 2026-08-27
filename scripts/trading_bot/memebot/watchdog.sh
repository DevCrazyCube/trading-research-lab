#!/usr/bin/env bash
# houdt de eval-na-elke-trade loop levend (herstart bij crash/reboot)
cd /home/anont/meme || exit 1
export PATH="/home/anont/.local/bin:/usr/local/bin:/usr/bin:/bin"
if ! pgrep -f "live_loop.sh" >/dev/null 2>&1; then
  setsid nohup bash scripts/trading_bot/memebot/live_loop.sh >> research/trading_bot/memebot/live_run.log 2>&1 < /dev/null &
  echo "$(date -Is) watchdog: eval-loop herstart (pid $!)" >> research/trading_bot/memebot/watchdog.log
fi
