#!/usr/bin/env bash
# Entrypoint for the detached B15e shadow-path materializer.
#
# Offline and read-only: it needs no credential, because it prices exits from evidence B15a and
# B15d already recorded. Looped so cells mature into figures as later observations accumulate.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p research/b15e/logs
interval="${1:-900}"
while true; do
  python scripts/b15e_shadow_path.py --run \
    >> research/b15e/logs/path.stdout.log 2>> research/b15e/logs/path.stderr.log || true
  sleep "$interval"
done
