#!/usr/bin/env bash
# Fixed, seal-pinned supervisor for the PAC paper-scenario runner. No wallet or order path.
set -u
cd /home/anont/meme || exit 1

child_pid=""
stop_supervisor() {
  if [[ -n "${child_pid}" ]]; then
    kill -TERM "${child_pid}" 2>/dev/null || true
    wait "${child_pid}" 2>/dev/null || true
  fi
  exit 0
}
trap stop_supervisor INT TERM

while true; do
  python -m scripts.trading_bot.aftershock.pac_runner \
    --reaction-nanos 800000000 --interval 0.25 \
    >> scripts/trading_bot/aftershock/pac_runner.log 2>&1 &
  child_pid=$!
  wait "${child_pid}"
  exit_code=$?
  child_pid=""
  printf '%s PAC runner exited code=%s; restarting after 0.25s\n' \
    "$(date -Is)" "${exit_code}" >> scripts/trading_bot/aftershock/pac_runner_supervisor.log
  sleep 0.25
done
