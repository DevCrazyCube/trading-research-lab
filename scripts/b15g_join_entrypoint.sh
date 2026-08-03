#!/usr/bin/env bash
# Entrypoint for the detached B15g join materializer.
# Offline and read-only: every input is already on disk, so it needs no credential.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p research/b15g/logs
interval="${1:-600}"
while true; do
  python scripts/b15g_checkpoint_join.py --run \
    >> research/b15g/logs/join.stdout.log 2>> research/b15g/logs/join.stderr.log || true
  sleep "$interval"
done
