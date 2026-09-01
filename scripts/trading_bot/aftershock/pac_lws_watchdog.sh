#!/usr/bin/env bash
# Operational launcher for the sealed+activated PAC Launch-Window Sentinel Scalper paper runtime.
# This file NEVER deletes, rewrites, or repairs runner state/ledger/mark/feed data.
# It keeps THREE tmux sessions alive: the creation-anchored LWS feed collector (shared by both arms),
# the VETO arm runner, and the NULL arm runner. The two runners are launched as an imported package
# (python -m the launcher) to avoid the python -m double-module identity bug that makes the manifest-
# derived RuntimeProof fail its isinstance gate. Both arms consume the identical feed = matched arms.
set -u

ROOT="/home/anont/meme"
RESEARCH="$ROOT/research/trading_bot/aftershock"
ENV_FILE="${PAC_LWS_ENV_FILE:-$ROOT/.env}"
WATCHDOG_LOCK="$RESEARCH/AFTERSHOCK_PAC_LWS_WATCHDOG.lock"
WATCHDOG_LOG="$RESEARCH/AFTERSHOCK_PAC_LWS_WATCHDOG.log"
FEED_LOG="$RESEARCH/AFTERSHOCK_PAC_LWS_FEED.log"
VETO_LOG="$RESEARCH/AFTERSHOCK_PAC_LWS_RUNNER.log"
NULL_LOG="$RESEARCH/AFTERSHOCK_PAC_LWS_NULL_RUNNER.log"

FEED_SESSION="pac-lws-feed"
VETO_SESSION="pac-lws"
NULL_SESSION="pac-lws-null"

FEED_CMD="cd $ROOT && set -a && source '$ENV_FILE' 2>/dev/null && set +a && exec python3 -m scripts.trading_bot.aftershock.pac_lws_feed"
VETO_CMD="cd $ROOT && set -a && source '$ENV_FILE' 2>/dev/null && set +a && exec python3 -m scripts.trading_bot.aftershock.pac_lws_launch live --veto"
NULL_CMD="cd $ROOT && set -a && source '$ENV_FILE' 2>/dev/null && set +a && exec python3 -m scripts.trading_bot.aftershock.pac_lws_launch live --no-veto"

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
  echo "another PAC LWS watchdog owns the lock" >&2
  exit 1
fi

log "watchdog up"
while true; do
  ensure_session "$FEED_SESSION" "$FEED_CMD" "$FEED_LOG"
  ensure_session "$VETO_SESSION" "$VETO_CMD" "$VETO_LOG"
  ensure_session "$NULL_SESSION" "$NULL_CMD" "$NULL_LOG"
  sleep 5
done
