#!/usr/bin/env bash
# Keep the Gate-B virality forward paper-decider alive. Data-only: it holds NO wallet, places NO orders,
# and only appends to a hash-chained paper ledger — safe to auto-restart. flock-guarded so a second
# watchdog can't double-run the collector (which would double-count paper entries).
set -u

ROOT="/home/anont/meme"
DATA="$ROOT/research/data/virality"
LOCK="$DATA/watchdog.lock"
LOG="$DATA/watchdog.log"
RUN_LOG="$DATA/tracker.log"
SESSION="virality-tracker"
CMD="cd $ROOT && exec python3 -m scripts.trading_bot.memebot.virality_tracker"

mkdir -p "$DATA"
log() { printf '%s %s\n' "$(date -u +%FT%TZ)" "$1" >> "$LOG"; }
session_alive() { tmux has-session -t "=$1" 2>/dev/null; }

exec 9>"$LOCK"
if ! flock -n 9; then
  echo "another virality watchdog owns the lock" >&2
  exit 1
fi

log "virality watchdog up (data-only forward decider; auto-restart on crash)"
while true; do
  if ! session_alive "$SESSION"; then
    log "starting virality tracker session"
    tmux new-session -d -s "$SESSION" \
      "bash -lc \"$CMD >> '$RUN_LOG' 2>&1\""
  fi
  sleep 10
done
