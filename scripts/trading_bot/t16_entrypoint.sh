#!/usr/bin/env bash
# Entrypoint for the T16 FREE FORWARD-DATA PANELS collector.
#
# WHAT IT RUNS
#   One `daily` pass of scripts/trading_bot/t16_free_panels.py:
#     1. poll FINRA's partitions listing, record any settlement date appearing for the FIRST
#        time (that timestamp is the asset -- it bounds real dissemination, and no vendor
#        sells it back to us), then fetch every listed date not already held;
#     2. snapshot Alpaca's per-asset borrow flags (shortable / easy_to_borrow /
#        borrow_status) -- a live view with no history anywhere, including at Alpaca;
#     3. politely poll the free iborrowdesk mirror for borrow FEES on a small watchlist
#        (DEAD at the source -- the host answers /api/ with a bare connection close; the leg
#        records the failure daily rather than hiding it);
#     4. fetch every FINRA Reg SHO DAILY short-sale-volume session file not already held
#        (free, no key, ~12.2k symbol rows per session -- 252 observations a year against
#        panel 1's 24, and the CDN's retention window is rolling, so a session not collected
#        is a session lost).
#
#   Passing --revisions runs the same pass PLUS a bounded re-observation of the four most
#   recent FINRA settlement dates whose last observation is over a week old. FINRA silently
#   replaces a date's rows when it revises them, so without this nothing here would ever
#   observe a revision. It writes a SECOND snapshot beside the first; it overwrites nothing.
#
#   It COLLECTS. It computes no signal, places no order, and touches no order path. Every
#   endpoint is a read-only GET/POST against a free source. Nothing here costs money and no
#   account or payment detail is required beyond the Alpaca market key already in .env.
#
# WHY IT IS SAFE TO SCHEDULE IT EVERY HOUR
#   Each leg is idempotent per UTC day. The FINRA leg fetches only settlement dates not
#   already in its manifest, so once a day's work is done it makes exactly one cheap
#   partitions call and stops. The two borrow legs skip outright once that UTC day already
#   has a snapshot. A machine that was asleep at 21:00 still gets its collection when it
#   wakes, provided the UTC day has not rolled over -- which is the whole reason the
#   schedule is hourly rather than daily.
#
#   Running it hourly also means the FIRST-SEEN timestamp on a new FINRA settlement date is
#   accurate to within an hour instead of a day. That resolution is the point.
#
# APPEND-ONLY, AND WHAT ENFORCES IT
#   Snapshot paths carry `observed=<UTC timestamp>`; an existing path is a hard refusal, not
#   an overwrite. Manifests and logs are opened in append mode only. `verify` re-hashes every
#   sealed snapshot against its manifest sha256 -- run it after any incident:
#     python3 scripts/trading_bot/t16_free_panels.py verify
#
# INSTALL -- THE OWNER DOES THIS, NOT THE BOT
#   This script installs no crontab and neither does the Python it calls. Run:
#     crontab -e
#   then add exactly:
#
#     17 * * * * /home/anont/meme/scripts/trading_bot/t16_entrypoint.sh
#
#   and, optionally but recommended -- without it no FINRA revision is ever observed:
#
#     41 6 * * 0 /home/anont/meme/scripts/trading_bot/t16_entrypoint.sh --revisions
#
#   (`python3 scripts/trading_bot/t16_free_panels.py crontab-line` prints the same line.)
#   Minute 17 rather than 0 keeps it off the top-of-hour crowd already in this crontab.
#
# STOP
#   Remove the crontab line. There is no other state to unwind: the collected panel is
#   inert data and nothing reads it automatically.
#
# INSPECT
#   python3 scripts/trading_bot/t16_free_panels.py coverage
#   python3 scripts/trading_bot/t16_free_panels.py verify
#   tail -n 1 research/data/t16_panels/COLLECTION_LOG.jsonl | python3 -m json.tool
set -euo pipefail
cd "$(dirname "$0")/../.."
mkdir -p research/trading_bot/logs research/data/t16_panels

# The ONLY argument this accepts. Anything else is refused rather than passed through to the
# collector, so a typo in a crontab line cannot quietly change what gets collected.
EXTRA=()
if [ "$#" -gt 0 ]; then
  case "$1" in
    --revisions) EXTRA=(--refresh-recent 4 --refresh-age-days 7) ;;
    *) echo "t16_entrypoint.sh: unknown argument '$1' (only --revisions)" >&2; exit 2 ;;
  esac
fi

# A single lock, non-blocking. The hourly schedule assumes a pass finishes inside the hour,
# which is true once the panel is seeded but NOT true of a first run or of a long catch-up
# after downtime: those walk years of Reg SHO sessions and take tens of minutes. Two passes
# running at once would race on the same manifests, so a second one exits quietly instead.
exec 9>>research/data/t16_panels/.collector.lock
if ! flock -n 9; then
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) t16: a collection is already running; skipping" \
    >> research/trading_bot/logs/t16_panels.stdout.log
  exit 0
fi

exec python3 -m scripts.trading_bot.t16_free_panels daily "${EXTRA[@]}" \
  >> research/trading_bot/logs/t16_panels.stdout.log \
  2>> research/trading_bot/logs/t16_panels.stderr.log
