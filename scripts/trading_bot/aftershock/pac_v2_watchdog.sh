#!/usr/bin/env bash
# Operational launcher for the sealed PAC V2 paper supervisor and read-only dashboard.
# This file never deletes, rewrites, or repairs runner state/ledger data.

set -u

ROOT="/home/anont/meme"
RESEARCH="$ROOT/research/trading_bot/aftershock"
WATCHDOG_LOCK="$RESEARCH/AFTERSHOCK_PAC_V2_WATCHDOG.lock"
WATCHDOG_LOG="$RESEARCH/AFTERSHOCK_PAC_V2_WATCHDOG.log"
SUPERVISOR_LOG="$RESEARCH/AFTERSHOCK_PAC_V2_SUPERVISOR.log"
DASHBOARD_LOG="$RESEARCH/AFTERSHOCK_PAC_V2_DASHBOARD.log"
ENV_FILE="${PAC_V2_ENV_FILE:-$ROOT/.env}"
SUPERVISOR_MODULE="scripts.trading_bot.aftershock.pac_v2_supervisor"
DASHBOARD_MODULE="scripts.trading_bot.memebot.dashboard.server"

module_running() {
  local target="$1" cmdline index
  local -a argv=()
  for cmdline in /proc/[0-9]*/cmdline; do
    argv=()
    mapfile -d '' -t argv 2>/dev/null < "$cmdline" || continue
    for ((index = 0; index + 1 < ${#argv[@]}; index++)); do
      if [[ "${argv[$index]}" == "-m" && "${argv[$((index + 1))]}" == "$target" ]]; then
        return 0
      fi
    done
  done
  return 1
}

launch_supervisor() {
  tmux kill-session -t pac-v2 2>/dev/null || true
  tmux new-session -d -s pac-v2 "$0 --supervise"
  printf '%s supervisor launch requested\n' "$(date -u +%FT%TZ)" >> "$WATCHDOG_LOG"
}

launch_dashboard() {
  tmux kill-session -t pac-dash 2>/dev/null || true
  tmux new-session -d -s pac-dash "$0 --dashboard"
  printf '%s dashboard launch requested\n' "$(date -u +%FT%TZ)" >> "$WATCHDOG_LOG"
}

case "${1:-}" in
  --supervise)
    cd "$ROOT" || exit 2
    if [[ ! -f "$ENV_FILE" ]]; then
      printf 'PAC V2 env file is absent\n' >&2
      exit 2
    fi
    set -a
    # The operator-owned file may contain unrelated shell lines; authority still fails closed below.
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
    if [[ -z "${PAC_V2_ATTEST_RPC_URL:-}" ]]; then
      printf 'PAC_V2_ATTEST_RPC_URL is absent\n' >&2
      exit 2
    fi
    exec python3 -m "$SUPERVISOR_MODULE" >> "$SUPERVISOR_LOG" 2>&1
    ;;
  --dashboard)
    cd "$ROOT" || exit 2
    exec python3 -m "$DASHBOARD_MODULE" >> "$DASHBOARD_LOG" 2>&1
    ;;
  --status)
    if module_running "$SUPERVISOR_MODULE"; then
      printf 'supervisor=running\n'
    else
      printf 'supervisor=stopped\n'
    fi
    if module_running "$DASHBOARD_MODULE"; then
      printf 'dashboard=running\n'
    else
      printf 'dashboard=stopped\n'
    fi
    exit 0
    ;;
  "")
    ;;
  *)
    printf 'usage: %s [--status]\n' "$0" >&2
    exit 2
    ;;
esac

cd "$ROOT" || exit 2
mkdir -p "$RESEARCH"
exec 9>> "$WATCHDOG_LOCK"
if ! flock -n 9; then
  printf 'PAC V2 watchdog already owns its lock\n' >&2
  exit 2
fi

while true; do
  if ! module_running "$SUPERVISOR_MODULE"; then
    launch_supervisor
  fi
  if ! module_running "$DASHBOARD_MODULE"; then
    launch_dashboard
  fi
  sleep 5
done
