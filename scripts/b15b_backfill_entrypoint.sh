#!/usr/bin/env bash
# Entrypoint for the detached B15b backfill worker.
#
# The credential is sourced HERE rather than passed on a command line: anything handed to
# `tmux new-session -e` or to the worker as an argument appears in a process argv, where `ps` shows
# it to every user on the box.
#
# The worker is a bounded batch job, so durability is a loop rather than a long-lived connection.
# Each pass resolves whatever B15a has newly decoded and then sleeps; a pass with nothing pending
# costs one read of a local database and no RPC request at all.
#
# It reads. It holds no key, signs nothing, builds nothing, simulates nothing and submits nothing.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a
. ./.env
set +a
mkdir -p research/b15b/logs
interval="${1:-300}"
while true; do
  python scripts/b15b_backfill.py --run \
    >> research/b15b/logs/backfill.stdout.log 2>> research/b15b/logs/backfill.stderr.log || true
  sleep "$interval"
done
