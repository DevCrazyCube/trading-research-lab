#!/usr/bin/env bash
# install_durable_cron.sh -- the OWNER runs this ONCE to activate the durable
# supervisor via the OS user crontab (cronie). Idempotent: re-running it does not
# duplicate the line. It PRESERVES every other crontab entry -- especially the t4
# real-money lines, the battery/updates/posture checks, and the T4_MODE env line.
#
# Cadence: every 3 hours (AGGRESSIVE). See README_DURABLE.md for the token cost.
#
# This is the ONLY step that arms the scheduler. Building the scripts does nothing
# on its own; nothing runs until this line is in the crontab.

set -euo pipefail

TICK="/home/anont/meme/scripts/agent_graph/durable_tick.sh"
LOGDIR="/home/anont/meme/scripts/agent_graph/logs"
CRON_LINE="0 */3 * * * ${TICK} >> ${LOGDIR}/cron.log 2>&1"

mkdir -p "${LOGDIR}"
chmod +x "${TICK}" 2>/dev/null || true

# Read the current crontab (empty if none), drop any prior durable_tick line, then
# append exactly one fresh line. `grep -v` with `|| true` so an empty crontab is fine.
CURRENT="$(crontab -l 2>/dev/null || true)"
NEW="$(printf '%s\n' "${CURRENT}" | grep -v 'durable_tick.sh' || true)"

# Install: preserved lines first, then our single durable line.
{
    printf '%s\n' "${NEW}" | sed '/^$/d'
    printf '%s\n' "${CRON_LINE}"
} | crontab -

echo "INSTALLED. Durable supervisor is now armed (every 3 hours)."
echo "Line added:"
echo "  ${CRON_LINE}"
echo
echo "Verify with:  crontab -l"
echo "Watch with :  tail -f ${LOGDIR}/durable_heartbeat.log"
echo "Stop  with :  bash /home/anont/meme/scripts/agent_graph/uninstall_durable_cron.sh"
