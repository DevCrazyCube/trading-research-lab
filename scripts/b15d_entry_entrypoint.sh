#!/usr/bin/env bash
# Entrypoint for the detached B15d shadow-entry worker.
#
# Read-only and offline: it needs no credential at all, because it prices from evidence B15a and
# B15b already recorded. It is launched with the same loop shape as the other workers so newly
# eligible launches are picked up as they accumulate.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p research/b15d/logs
interval="${1:-600}"
while true; do
  python scripts/b15d_shadow_entry.py --run \
    >> research/b15d/logs/entry.stdout.log 2>> research/b15d/logs/entry.stderr.log || true
  sleep "$interval"
done
