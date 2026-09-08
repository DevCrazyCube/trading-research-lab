#!/usr/bin/env bash
# Entrypoint for the T4 volatility-targeting FORWARD TEST on the Alpaca PAPER account.
#
# WHAT IT RUNS
#   One session of scripts/trading_bot/t4_forward.py: compute the frozen T13 target weight from
#   the previous session's close, settle whatever has printed since the last run, size the
#   position, and either log the intended order (dry-run) or place it against the PAPER
#   endpoint (submit -- owner-gated, see below).
#
# THE ORDER IS A MARKET *DAY* ORDER SENT IN THE FINAL MINUTES -- NOT A MARKET-ON-CLOSE
#   This changed on 2026-08-18 and the reason is measured, not theoretical: Alpaca's PAPER
#   account does not run the closing auction, so a tif=cls order sits all day and EXPIRES
#   unfilled. Order 3a5487f8, 93 SPY, submitted 2026-08-17T13:50Z, expired 20:00Z with
#   filled_qty=0. Nothing ever filled, so nothing ever settled. The bot now sends
#   type=market/tif=day inside 15:50-15:58 ET, which fills immediately against the paper book.
#
# WHY THE SCHEDULE MATTERS MORE THAN IT USED TO
#   A market DAY order fills WHEN IT IS SENT, so the firing minute IS the execution price. The
#   action window is 15:50-15:58 US/Eastern and --skip-outside-window makes every other fire a
#   no-op; --skip-if-logged makes it a no-op once the session has been recorded, so the first
#   successful in-window run wins and every later one exits 0 without touching the ledger.
#
#   The installed `*/10 12-23 * * 1-5` fires exactly ONCE inside that window, at 15:50 ET, so a
#   single network blip costs the session. RECOMMENDED: change it to
#     55-58 12-23 * * 1-5    (tightest to the close, four attempts)
#   or 50-58 12-23 * * 1-5   (nine attempts, first fill at 15:50)
#   Both are covered by the bot's own Eastern-time window check, which is what actually decides.
#
#   A run that starts at or after 15:59 ET REFUSES to submit: a market DAY order landing after
#   the bell queues to the NEXT open and would establish the weight one session late, at a
#   price from the wrong session. That guard is separate from the window on purpose.
#
# THE CREDENTIAL IS NEVER PASSED AS AN ARGUMENT, AND IS NOT SOURCED HERE EITHER
#   Anything handed to a process on its command line shows up in `ps` for every user on the
#   box, so it is not passed. It is also not `.`-sourced into the shell, which the other
#   entrypoints in this repository do: `load_env_credentials()` parses `.env` itself, in
#   Python, keeping the secret out of this shell's environment and out of any child process
#   that is not the bot.
#
#   That is not only hygiene. As of 2026-08-17 `.env` line 5 is a bare token with no `=`, so
#   `set -e; . ./.env` aborts before it reaches the Alpaca keys -- every `*_entrypoint.sh` in
#   `scripts/` currently dies there. Parsing the file rather than executing it sidesteps a
#   class of failure where a comment-shaped line takes the process down.
#
#   t4_forward.py asserts before every ledger write that no credential reached the record.
#
# MODE, AND THE ONE THING THIS SCRIPT WILL NOT DECIDE FOR YOU
#   T4_MODE defaults to dry-run. Setting T4_MODE=submit is not enough on its own: the bot also
#   requires research/trading_bot/T4_OWNER_AUTHORISATION.json, which only the owner creates.
#   Deleting that file is the stop switch -- the bot keeps computing and logging, and stops
#   sending orders.
#
#   There is no setting, here or anywhere in this rig, that reaches the LIVE endpoint. That is
#   enforced by hostname in paper.py, not by this comment.
#
# START
#   crontab -e, then:
#     50-58 12-23 * * 1-5 /home/anont/meme/scripts/trading_bot/t4_entrypoint.sh
#   (the broad hour range covers 09:00-17:00 ET across every combination of US and EU DST --
#   they switch on different dates -- and the bot does the precise windowing itself, in
#   Eastern time, per day, from the frozen et_offset_hours. NOTE the minute field: a */10 cron
#   never fires between 15:51 and 15:58, so with a 15:50-15:58 window it gets exactly one
#   attempt per day.)
#
# STOP
#   Remove the crontab line.                       -- stops everything
#   rm research/trading_bot/T4_OWNER_AUTHORISATION.json  -- stops orders, keeps the log accruing
#   T4_MODE=dry-run                                -- same, from the scheduler side
#
# INSPECT
#   python -m scripts.trading_bot.t4_forward status
#   python -m scripts.trading_bot.t4_forward report
#   tail -n 1 research/trading_bot/T4_FORWARD_LOG.jsonl | python3 -m json.tool
set -euo pipefail
cd "$(dirname "$0")/../.."
mkdir -p research/trading_bot/logs

MODE="${T4_MODE:-dry-run}"
ACCOUNT_SOURCE="${T4_ACCOUNT_SOURCE:-broker}"

exec python3 -m scripts.trading_bot.t4_forward session \
  --mode "$MODE" \
  --account-source "$ACCOUNT_SOURCE" \
  --refresh-cash \
  --skip-outside-window \
  --skip-if-logged \
  >> research/trading_bot/logs/t4_forward.stdout.log \
  2>> research/trading_bot/logs/t4_forward.stderr.log
