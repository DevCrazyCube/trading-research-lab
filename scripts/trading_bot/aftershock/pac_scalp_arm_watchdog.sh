#!/usr/bin/env bash
# Operational launcher for the PAC SCALP anti-exhaustion ENTRY arms (dip-reclaim + early-curve),
# paper-scenario only. Never deletes, rewrites, or repairs runner state/ledger/mark data.
# It keeps two tmux sessions alive -- the DIP arm runner and the EARLY arm runner -- each launched as
# an imported package (python -m the launcher) to avoid the double-module RuntimeProof identity bug.
# The pump feed is SHARED with the momentum arm (started by pac_scalp_watchdog.sh); this watchdog does
# NOT start a feed, so the three arms consume the identical event stream = a matched comparison.
set -u

ROOT="/home/anont/meme"
RESEARCH="$ROOT/research/trading_bot/aftershock"
ENV_FILE="${PAC_SCALP_ENV_FILE:-$ROOT/.env}"
WATCHDOG_LOCK="$RESEARCH/AFTERSHOCK_PAC_SCALP_ARM_WATCHDOG.lock"
WATCHDOG_LOG="$RESEARCH/AFTERSHOCK_PAC_SCALP_ARM_WATCHDOG.log"
DIP_LOG="$RESEARCH/AFTERSHOCK_PAC_SCALP_DIP_RUNNER.log"
EARLY_LOG="$RESEARCH/AFTERSHOCK_PAC_SCALP_EARLY_RUNNER.log"

DIP_SESSION="pac-scalp-dip"
EARLY_SESSION="pac-scalp-early"

DIP_CMD="cd $ROOT && set -a && source '$ENV_FILE' 2>/dev/null && set +a && exec python3 -m scripts.trading_bot.aftershock.pac_scalp_arm_launch dip"
EARLY_CMD="cd $ROOT && set -a && source '$ENV_FILE' 2>/dev/null && set +a && exec python3 -m scripts.trading_bot.aftershock.pac_scalp_arm_launch early"

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
  echo "another PAC SCALP arm watchdog owns the lock" >&2
  exit 1
fi

log "arm watchdog up"
while true; do
  ensure_session "$DIP_SESSION" "$DIP_CMD" "$DIP_LOG"
  ensure_session "$EARLY_SESSION" "$EARLY_CMD" "$EARLY_LOG"
  sleep 5
done
