#!/usr/bin/env bash
# Retirement-safe PAC LWS supervisor. The negative LWS/NULL/scalp executors are permanently retired.
# This watchdog maintains only the data-only eligibility recorder. The already-running creation feed
# is deliberately NOT restarted here because its prior credential was exposed locally and must rotate.
set -u

ROOT="/home/anont/meme"
RESEARCH="$ROOT/research/trading_bot/aftershock"
WATCHDOG_LOCK="$RESEARCH/AFTERSHOCK_PAC_LWS_WATCHDOG.lock"
WATCHDOG_LOG="$RESEARCH/AFTERSHOCK_PAC_LWS_WATCHDOG.log"
ELIGIBILITY_LOG="$RESEARCH/AFTERSHOCK_PAC_LWS_ELIGIBILITY.log"
ELIGIBILITY_SESSION="pac-lws-eligibility"
ELIGIBILITY_CMD="cd $ROOT && exec python3 -m scripts.trading_bot.aftershock.pac_lws_eligibility"

log() { printf '%s %s\n' "$(date -u +%FT%TZ)" "$1" >> "$WATCHDOG_LOG"; }
session_alive() { tmux has-session -t "=$1" 2>/dev/null; }

exec 9>"$WATCHDOG_LOCK"
if ! flock -n 9; then
  echo "another PAC LWS watchdog owns the lock" >&2
  exit 1
fi

log "retirement-safe watchdog up (eligibility only; executors disabled; feed restart disabled)"
while true; do
  if ! session_alive "$ELIGIBILITY_SESSION"; then
    log "starting data-only eligibility session"
    tmux new-session -d -s "$ELIGIBILITY_SESSION" \
      "bash -lc \"$ELIGIBILITY_CMD >> '$ELIGIBILITY_LOG' 2>&1\""
  fi
  sleep 5
done
