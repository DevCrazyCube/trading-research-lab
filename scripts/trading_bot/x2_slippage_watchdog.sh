#!/usr/bin/env bash
# Keep the X2_FLOWSTREAK capacity dashboard alive. Read-only view of a measurement — no trading, no
# orders. flock-guarded so a second watchdog can't double-bind the port.
set -u

ROOT="/home/anont/meme"
DATA="$ROOT/research/data/x2_slippage"
LOCK="$DATA/dash_watchdog.lock"
LOG="$DATA/dash_watchdog.log"
SESSION="x2-dash"
CMD="cd $ROOT && exec python3 -m scripts.trading_bot.x2_slippage_dashboard"

mkdir -p "$DATA"
log() { printf '%s %s\n' "$(date -u +%FT%TZ)" "$1" >> "$LOG"; }
session_alive() { tmux has-session -t "=$1" 2>/dev/null; }

exec 9>"$LOCK"
if ! flock -n 9; then
  echo "another x2 dashboard watchdog owns the lock" >&2
  exit 1
fi

log "x2 dashboard watchdog up"
while true; do
  if ! session_alive "$SESSION"; then
    log "starting x2 dashboard session"
    tmux new-session -d -s "$SESSION" "bash -lc \"$CMD >> '$DATA/dashboard.log' 2>&1\""
  fi
  sleep 10
done
