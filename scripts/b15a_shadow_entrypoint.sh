#!/usr/bin/env bash
# Entrypoint for the detached B15a shadow pilot session.
#
# The credential is sourced HERE rather than passed on a command line: anything handed to
# `tmux new-session -e` or to the pilot as an argument appears in a process argv, where `ps` shows
# it to every user on the box. Sourcing keeps it in the file that already holds it and in the
# process environment, which is where the contract says it lives.
#
# The pilot observes and records. It holds no key, signs nothing, builds no transaction and submits
# nothing — `assert_no_execution_surface` refuses at startup if that ever stops being true.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a
. ./.env
set +a
mkdir -p research/b15a/logs
exec python scripts/b15a_shadow_pilot.py --watch --commitment "${1:-confirmed}" \
  >> research/b15a/logs/pilot.stdout.log 2>> research/b15a/logs/pilot.stderr.log
