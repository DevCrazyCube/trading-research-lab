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
V21_RUNNER_LOG="$RESEARCH/AFTERSHOCK_PAC_V21_RUNNER.log"
V21_ACTIVATION="$RESEARCH/AFTERSHOCK_PAC_V21_ACTIVATION.json"
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

# Read one exact NAME=value assignment without sourcing the operator-owned file.  The previous
# launcher sourced the whole file, so an unrelated malformed line could execute as a shell command
# and pollute (or abort) PAC startup.
env_value() {
  local wanted="$1" line value
  [[ -f "$ENV_FILE" ]] || return 1
  while IFS= read -r line || [[ -n "$line" ]]; do
    case "$line" in
      "$wanted="*)
        value="${line#*=}"
        if [[ "$value" == \'*\' && "$value" == *\' && ${#value} -ge 2 ]]; then
          value="${value:1:${#value}-2}"
        elif [[ "$value" == \"*\" && "$value" == *\" && ${#value} -ge 2 ]]; then
          value="${value:1:${#value}-2}"
        fi
        printf '%s' "$value"
        return 0
        ;;
    esac
  done < "$ENV_FILE"
  return 1
}

v21_running() {
  tmux has-session -t pac-v21 2>/dev/null
}

launch_supervisor() {
  tmux kill-session -t pac-v2 2>/dev/null || true
  # Never leak the watchdog's singleton-lock descriptor into the tmux server. If the watchdog is
  # interrupted (for example by a laptop/session crash), an inherited fd 9 would otherwise keep the
  # lock alive forever and prevent the watchdog itself from restarting.
  tmux new-session -d -s pac-v2 "$0 --supervise" 9>&-
  printf '%s supervisor launch requested\n' "$(date -u +%FT%TZ)" >> "$WATCHDOG_LOG"
}

launch_dashboard() {
  tmux kill-session -t pac-dash 2>/dev/null || true
  tmux new-session -d -s pac-dash "$0 --dashboard" 9>&-
  printf '%s dashboard launch requested\n' "$(date -u +%FT%TZ)" >> "$WATCHDOG_LOG"
}

launch_v21() {
  tmux kill-session -t pac-v21 2>/dev/null || true
  tmux new-session -d -s pac-v21 "$0 --v21-runner" 9>&-
  printf '%s PAC V2.1 runner launch requested\n' "$(date -u +%FT%TZ)" >> "$WATCHDOG_LOG"
}

case "${1:-}" in
  --supervise)
    cd "$ROOT" || exit 2
    if [[ -z "${PAC_V2_ATTEST_RPC_URL:-}" ]]; then
      PAC_V2_ATTEST_RPC_URL="$(env_value PAC_V2_ATTEST_RPC_URL)" || {
        printf 'PAC_V2_ATTEST_RPC_URL is absent\n' >&2
        exit 2
      }
    fi
    export PAC_V2_ATTEST_RPC_URL
    exec python3 -m "$SUPERVISOR_MODULE" >> "$SUPERVISOR_LOG" 2>&1
    ;;
  --v21-runner)
    cd "$ROOT" || exit 2
    if [[ -z "${PAC_V21_ATTEST_RPC_URL:-}" ]]; then
      PAC_V21_ATTEST_RPC_URL="$(env_value PAC_V21_ATTEST_RPC_URL)" || \
        PAC_V21_ATTEST_RPC_URL="$(env_value PAC_V2_ATTEST_RPC_URL)" || {
          printf 'PAC_V21_ATTEST_RPC_URL is absent\n' >&2
          exit 2
        }
    fi
    export PAC_V21_ATTEST_RPC_URL
    exec python3 -c \
      'from scripts.trading_bot.aftershock.pac_v21_runner import main; raise SystemExit(main())' \
      >> "$V21_RUNNER_LOG" 2>&1
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
    if v21_running; then
      printf 'pac_v21_runner=running\n'
    else
      printf 'pac_v21_runner=stopped\n'
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
  if [[ -f "$V21_ACTIVATION" ]] && ! v21_running; then
    launch_v21
  fi
  # The child timer is not the lock owner and must not transiently inherit fd 9 either.
  sleep 5 9>&-
done
