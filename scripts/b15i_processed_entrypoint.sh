#!/usr/bin/env bash
# Entrypoint for the detached B15i processed-commitment pilot.
#
# The credential is sourced HERE rather than passed on a command line: anything handed to
# `tmux new-session -e` or to the pilot as an argument appears in a process argv, where `ps` shows
# it to every user on the box.
#
# On start, any target left pending by a previous process is marked Q_MISSED_WHILE_DOWN and is
# never fetched. Fetching it now would produce an account read from AFTER the target and record it
# as the state AT the target.
#
# The pilot observes and records. It holds no key, signs nothing, builds no transaction and submits
# nothing — `assert_no_execution_surface` refuses at startup if that ever stops being true.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a
. ./.env
set +a
mkdir -p research/b15i/logs
python scripts/b15i_processed_feed.py --recover \
  >> research/b15i/logs/pilot.stdout.log 2>> research/b15i/logs/pilot.stderr.log || true
exec python scripts/b15i_processed_feed.py --workers "${1:-4}" \
  >> research/b15i/logs/pilot.stdout.log 2>> research/b15i/logs/pilot.stderr.log
