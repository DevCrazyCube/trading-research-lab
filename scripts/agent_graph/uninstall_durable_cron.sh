#!/usr/bin/env bash
# uninstall_durable_cron.sh -- the OFF SWITCH. Removes ONLY the durable_tick line
# from the user crontab and leaves every other entry untouched (the t4 real-money
# lines, battery/updates/posture checks, and the T4_MODE env line all stay).

set -euo pipefail

CURRENT="$(crontab -l 2>/dev/null || true)"

if ! printf '%s\n' "${CURRENT}" | grep -q 'durable_tick.sh'; then
    echo "Nothing to do: no durable_tick line found in the crontab."
    exit 0
fi

printf '%s\n' "${CURRENT}" | grep -v 'durable_tick.sh' | sed '/^$/d' | crontab -

echo "UNINSTALLED. The durable supervisor is stopped (no more ticks will fire)."
echo "Any tick already in flight finishes on its own; nothing new is scheduled."
echo "Verify with:  crontab -l"
