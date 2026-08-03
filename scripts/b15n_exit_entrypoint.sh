#!/usr/bin/env bash
# Entrypoint for the detached B15n native exit-checkpoint worker.
#
# The credential is sourced HERE rather than passed on a command line: anything handed to
# `tmux new-session -e` or to the worker as an argument appears in a process argv, where `ps` shows
# it to every user on the box.
#
# The worker schedules exit horizons from B15i's OWN observations. It does not read B15a's launch
# table or B15f's schedule, and assert_no_b15a_or_b15f_dependency refuses at startup if that ever
# stops being true — which is the only reason this worker exists.
#
# It observes and records. It holds no key, signs nothing, builds no transaction and submits nothing.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a
. ./.env
set +a
mkdir -p research/b15n/logs
exec python scripts/b15n_native_exit_checkpoints.py \
  >> research/b15n/logs/worker.stdout.log 2>> research/b15n/logs/worker.stderr.log
