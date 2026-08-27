#!/usr/bin/env bash
# Watchdog: keep the memebot_evo evolution loop alive (restart on crash/reboot). PAPER ONLY.
# Idempotent -- safe to run from cron/at every few minutes.
cd /home/anont/meme || exit 1
export PATH="/home/anont/.local/bin:/usr/local/bin:/usr/bin:/bin"
DIR="scripts/trading_bot/memebot_evo"
if ! pgrep -f "memebot_evo/evolve_loop.sh" >/dev/null 2>&1; then
  setsid nohup bash "$DIR/evolve_loop.sh" >>"$DIR/evolve_run.log" 2>&1 < /dev/null &
  echo "$(date -Is) watchdog: evolve-loop restarted (pid $!)" >>"$DIR/watchdog.log"
fi
