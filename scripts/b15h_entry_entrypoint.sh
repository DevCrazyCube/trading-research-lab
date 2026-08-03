#!/usr/bin/env bash
# Entrypoint for the detached B15h prospective V2 entry scheduler.
#
# A 5-second tick, matching B15f V2: about 12 slots at the nominal rate, well inside the 150-slot
# lateness tolerance that neither document widened. Each tick costs one getSlot plus at most one
# getMultipleAccounts.
#
# The credential is sourced here so it never reaches an argv. Read-only throughout.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a
. ./.env
set +a
mkdir -p research/b15h/logs
interval="${1:-5}"
while true; do
  python scripts/b15h_prospective_entry.py --run --ticks 1 \
    >> research/b15h/logs/entry.stdout.log 2>> research/b15h/logs/entry.stderr.log || true
  sleep "$interval"
done
