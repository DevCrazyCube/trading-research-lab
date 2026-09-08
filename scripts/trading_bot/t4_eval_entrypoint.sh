#!/usr/bin/env bash
# Daily EVALUATE step for the paper forward tests. READ-ONLY with respect to every ledger.
#
# WHAT IT RUNS
#   python -m scripts.trading_bot.forward_eval report --write --write-status
#
#   That recomputes the whole evaluation from the append-only ledger, writes the JSON to
#   research/trading_bot/FORWARD_EVAL.json, and refreshes the one-line dashboard status in
#   research/trading_bot/FORWARD_STATUS.txt. It touches no ledger, no state file, no
#   authorisation and no pre-registration -- forward_eval._refuse_if_protected() refuses
#   those paths by suffix, so the guarantee survives someone passing --write a bad argument.
#
# WHY A SEPARATE ENTRYPOINT FROM t4_entrypoint.sh
#   The trade step and the evaluate step must be able to fail independently. A broker outage
#   should not stop the owner reading the record, and a bug in the evaluator must never be
#   able to stop or alter a session. They share nothing but the ledger, and the evaluator
#   only opens it for reading.
#
# THE CRON LINE  (crontab -e, then:)
#
#     30 22 * * 1-5 /home/anont/meme/scripts/trading_bot/t4_eval_entrypoint.sh
#
#   This box is Europe/Amsterdam and cron fires in LOCAL time. US/Eastern is local-6 all
#   year (both zones shift on almost the same dates), so 22:30 local is 16:30 ET -- half an
#   hour after the close, by which time t4_entrypoint.sh's last in-window run has logged the
#   session. Running it twice, or not at all, changes nothing: the report is a pure function
#   of the ledger.
#
#   If you would rather pin it to UTC regardless of the box's zone, use:
#     CRON_TZ=America/New_York
#     30 16 * * 1-5 /home/anont/meme/scripts/trading_bot/t4_eval_entrypoint.sh
#
# READ IT
#   python -m scripts.trading_bot.forward_eval report          # the full page
#   python -m scripts.trading_bot.forward_eval status-line     # the one line
#   cat research/trading_bot/FORWARD_STATUS.txt
#
# WHAT TO DO WITH WHAT IT SAYS
#   Nothing, unless the certifiability section says otherwise. That is not a joke: the
#   answer on almost every day is "no action, the sample has not moved". If a result makes
#   you want to change the running rule, read research/trading_bot/ITERATION_PROTOCOL.md
#   first -- the honest response is a NEW pre-registered forward test, never an edit.
set -euo pipefail
cd "$(dirname "$0")/../.."
mkdir -p research/trading_bot/logs

STRATEGY="${FORWARD_EVAL_STRATEGY:-}"
ARGS=(report --write --write-status)
if [ -n "$STRATEGY" ]; then
  ARGS+=(--strategy "$STRATEGY")
fi

exec python3 -m scripts.trading_bot.forward_eval "${ARGS[@]}" \
  >> research/trading_bot/logs/forward_eval.stdout.log \
  2>> research/trading_bot/logs/forward_eval.stderr.log
