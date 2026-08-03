#!/usr/bin/env bash
# Periodic compaction for the shadow feeds' sealed raw segments.
#
# The writers ROTATE in process, because they own the file handles, but they do not compress: the
# replace gate streams a replay over the whole segment set, and doing that on the feed thread would
# stop it reading the socket. Compaction therefore runs here, out of process, on a timer.
#
# Nothing is deleted that has not been sealed, compressed, hash-verified and replay-verified. A
# failure leaves the original in place and is reported; the loop simply tries again next cycle.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p research/b15j/logs
INTERVAL="${1:-3600}"
while true; do
  for target in b15a b15i; do
    python scripts/b15j_raw_retention.py --target "$target" \
      >> "research/b15j/logs/${target}.compaction.log" 2>&1 || true
  done
  sleep "$INTERVAL"
done
