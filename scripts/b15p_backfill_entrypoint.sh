#!/usr/bin/env bash
# Entrypoint for the detached B15p fee backfill.
#
# The credential is sourced HERE rather than passed on a command line: anything handed to the
# backfill as an argument appears in a process argv, where ps shows it to every user on the box.
#
# The backfill reads B15N's schedule and B15i's observations, and nothing under research/b15a,
# b15b or b15f. A runtime path guard records every file it opens and refuses a forbidden one, which
# is the check that would have caught B15O's dependency whatever the path was spelled like.
#
# It holds no key, signs nothing, builds no transaction and submits nothing. It computes no strategy
# quantity: it ends at fee schedules.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a
. ./.env
set +a
mkdir -p research/b15p/logs
exec python scripts/b15p_native_fee_backfill.py \
  >> research/b15p/logs/backfill.stdout.log 2>> research/b15p/logs/backfill.stderr.log
