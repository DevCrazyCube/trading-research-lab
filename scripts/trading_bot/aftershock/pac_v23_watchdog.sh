#!/usr/bin/env bash
# Operational launcher for the sealed+activated PAC V2.3 cross-venue paper runtime and read-only
# dashboard. This file NEVER deletes, rewrites, or repairs runner state/ledger/evidence data.
# It keeps three tmux sessions alive: the V2.2 low-lag feed collector (shared by V2.3), the V2.3
# runner (launched as an imported package to avoid the python -m double-module identity bug that
# makes the adapter's manifest-derived RuntimeProof fail its isinstance gate), and the dashboard.
set -u

ROOT="/home/anont/meme"
RESEARCH="$ROOT/research/trading_bot/aftershock"
ENV_FILE="${PAC_V23_ENV_FILE:-$ROOT/.env}"
WATCHDOG_LOCK="$RESEARCH/AFTERSHOCK_PAC_V23_WATCHDOG.lock"
WATCHDOG_LOG="$RESEARCH/AFTERSHOCK_PAC_V23_WATCHDOG.log"
FEED_LOG="$RESEARCH/AFTERSHOCK_PAC_V23_FEED.log"
RUNNER_LOG="$RESEARCH/AFTERSHOCK_PAC_V23_RUNNER.log"
DASH_LOG="$RESEARCH/AFTERSHOCK_PAC_V23_DASHBOARD.log"

FEED_SESSION="pac-v23-feed"
RUNNER_SESSION="pac-v23"
DASH_SESSION="pac-dash"

FEED_CMD="cd $ROOT && set -a && source '$ENV_FILE' 2>/dev/null && set +a && exec python3 -m scripts.trading_bot.aftershock.pac_v22_feed"
RUNNER_CMD="cd $ROOT && set -a && source '$ENV_FILE' 2>/dev/null && set +a && exec python3 -m scripts.trading_bot.aftershock.pac_v23_launch"
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
  echo "another PAC V2.3 watchdog owns the lock" >&2
  exit 1
fi

log "watchdog up"
while true; do
  ensure_session "$FEED_SESSION" "$FEED_CMD" "$FEED_LOG"
  ensure_session "$RUNNER_SESSION" "$RUNNER_CMD" "$RUNNER_LOG"
  ensure_session "$DASH_SESSION" "$DASH_CMD" "$DASH_LOG"
  sleep 5
done
