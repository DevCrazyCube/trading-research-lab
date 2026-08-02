#!/usr/bin/env bash
# Entrypoint for the detached B11a watcher session.
#
# The credential is sourced HERE rather than passed on a command line: anything handed to
# `tmux new-session -e` or to the watcher as an argument appears in a process argv, where `ps`
# shows it to every user on the box. Sourcing keeps it in the file that already holds it and in
# the process environment, which is where the contract says it lives.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a
. ./.env
set +a
mkdir -p research/b11a/logs
exec python scripts/b11c_maturity_watcher.py --watch --poll-seconds "${1:-300}" \
  >> research/b11a/logs/watcher.stdout.log 2>> research/b11a/logs/watcher.stderr.log
