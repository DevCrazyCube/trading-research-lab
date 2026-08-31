#!/usr/bin/env bash
# Supervise only the activated PAC V2.5 paper runner, shared read-only feed, and dashboard.
set -u

ROOT="/home/anont/meme"
RESEARCH="$ROOT/research/trading_bot/aftershock"
ENV_FILE="${PAC_V25_ENV_FILE:-$ROOT/.env}"
WATCHDOG_LOCK="$RESEARCH/AFTERSHOCK_PAC_V25_WATCHDOG.lock"
WATCHDOG_LOG="$RESEARCH/AFTERSHOCK_PAC_V25_WATCHDOG.log"
FEED_LOG="$RESEARCH/AFTERSHOCK_PAC_V25_FEED.log"
RUNNER_LOG="$RESEARCH/AFTERSHOCK_PAC_V25_RUNNER.log"
DASH_LOG="$RESEARCH/AFTERSHOCK_PAC_V25_DASHBOARD.log"

FEED_SESSION="pac-v25-feed"
RUNNER_SESSION="pac-v25"
DASH_SESSION="pac-dash"

FEED_CMD="cd $ROOT && set -a && source '$ENV_FILE' 2>/dev/null && set +a && exec python3 -m scripts.trading_bot.aftershock.pac_v22_feed"
RUNNER_CMD="cd $ROOT && set -a && source '$ENV_FILE' 2>/dev/null && set +a && exec python3 -m scripts.trading_bot.aftershock.pac_v25_launch"
DASH_CMD="cd $ROOT && set -a && source '$ENV_FILE' 2>/dev/null && set +a && exec python3 -m scripts.trading_bot.memebot.dashboard.server"

log() { printf '%s %s\n' "$(date -u +%FT%TZ)" "$1" >> "$WATCHDOG_LOG"; }
session_alive() { tmux has-session -t "=$1" 2>/dev/null; }
ensure_session() {
  local name="$1" cmd="$2" logfile="$3"
  if session_alive "$name"; then return 0; fi
  log "starting session $name"
  tmux new-session -d -s "$name" "bash -lc \"$cmd >> '$logfile' 2>&1\""
}

exec 9>"$WATCHDOG_LOCK"
if ! flock -n 9; then
  echo "another PAC V2.5 watchdog owns the lock" >&2
  exit 1
fi

log "watchdog up"
while true; do
  ensure_session "$FEED_SESSION" "$FEED_CMD" "$FEED_LOG"
  ensure_session "$RUNNER_SESSION" "$RUNNER_CMD" "$RUNNER_LOG"
  ensure_session "$DASH_SESSION" "$DASH_CMD" "$DASH_LOG"
  sleep 5
done
