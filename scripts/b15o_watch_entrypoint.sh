#!/usr/bin/env bash
# Entrypoint for the detached B15o closure watcher.
#
# It does one thing until the population closes: report the locked state and how far away closure
# is. It computes no estimand quantity while locked, because a watcher that had to price a cell to
# learn whether it may price a cell would already have priced it.
#
# One getSlot per poll and nothing else. The evidence it replicates is already on disk, which is why
# no other network call appears in the module. It holds no key, signs nothing, submits nothing.
#
# When the gate opens it materializes exactly once and then reports the existing artifact, so no
# reading of the study can differ from another.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a
. ./.env
set +a
mkdir -p research/b15o/logs
exec python scripts/b15o_closed_replication.py --watch --poll-seconds "${1:-300}" \
  >> research/b15o/logs/watcher.stdout.log 2>> research/b15o/logs/watcher.stderr.log
