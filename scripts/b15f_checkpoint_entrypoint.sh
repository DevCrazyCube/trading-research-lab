#!/usr/bin/env bash
# Entrypoint for the detached B15f checkpoint scheduler.
#
# A 20-second tick, which is about 50 slots at the nominal rate and comfortably inside the frozen
# 150-slot lateness tolerance. Fast enough that a target is not missed, slow enough that the poll
# itself is negligible RPC. Each tick costs one getSlot plus one getAccountInfo per due cell.
#
# The credential is sourced here so it never reaches an argv. Read-only throughout.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a
. ./.env
set +a
mkdir -p research/b15f/logs
interval="${1:-20}"
while true; do
  python scripts/b15f_checkpoint.py --run --ticks 1 \
    >> research/b15f/logs/checkpoint.stdout.log 2>> research/b15f/logs/checkpoint.stderr.log || true
  sleep "$interval"
done
