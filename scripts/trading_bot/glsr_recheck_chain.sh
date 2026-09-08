#!/usr/bin/env bash
# Chain: wait for the detached metrics backfill to finish, rebuild the glsr metapanel
# on the full (un-truncated) cross-section, then re-run the XS_GLSR_Z recheck eval.
# Launch detached:
#   setsid nohup bash scripts/trading_bot/glsr_recheck_chain.sh <BACKFILL_PID> \
#     > research/data/perpmicro_cache/logs/glsr_chain.log 2>&1 &
set -euo pipefail
cd /home/anont/meme
BF_PID="${1:?need backfill pid}"

echo "[chain] $(date -u) waiting on backfill pid $BF_PID"
while kill -0 "$BF_PID" 2>/dev/null; do sleep 60; done
echo "[chain] $(date -u) backfill process exited; rebuilding metapanel"

cd scripts/trading_bot
python3 perpmicro_r3_metapanel.py
echo "[chain] $(date -u) metapanel rebuilt; running recheck eval"
python3 glsr_recheck_eval.py
echo "[chain] $(date -u) DONE"
