#!/usr/bin/env bash
# Entrypoint for the detached B15f checkpoint scheduler.
#
# A 5-second tick under V2, about 12 slots at the nominal rate. The 20-second tick it replaces
# contributed up to 50 slots of lateness before anything was fetched, and the serial drain another
# 40 — together roughly 90 of the 150-slot budget, which is what lost half the checkpoints to
# C_LATE. Each tick now costs one getSlot plus at most ONE getMultipleAccounts, so the request
# count falls while the cadence quadruples.
#
# The credential is sourced here so it never reaches an argv. Read-only throughout.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a
. ./.env
set +a
mkdir -p research/b15f/logs
interval="${1:-5}"
while true; do
  python scripts/b15f_checkpoint.py --run --ticks 1 \
    >> research/b15f/logs/checkpoint.stdout.log 2>> research/b15f/logs/checkpoint.stderr.log || true
  sleep "$interval"
done
