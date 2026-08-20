#!/usr/bin/env bash
# Waits for the wave-1 fetch to drain, fills any symbol that failed, then builds the panel and
# runs the CENSUS and the DESIGN sweep. It deliberately stops there: the held-out stage needs a
# frozen shortlist chosen from the design results, so it is a separate, manual invocation.
set -u
cd /home/anont/meme
LOG=research/trading_bot/logs

while pgrep -f "trading_bot/rv_fetch.py" > /dev/null; do sleep 20; done
echo "wave 1 drained at $(date +%H:%M) with $(ls research/data/rv_cache/*.npz 2>/dev/null | wc -l) symbols"

# gap-fill pass: the script skips symbols whose .npz already exists, so this only retries the
# ones that exhausted their retries under the over-parallel second wave
for i in 0 1 2 3; do
  RV_SHARD=$i RV_NSHARDS=4 python3 scripts/trading_bot/rv_fetch.py > "$LOG/rv_gapfill_$i.log" 2>&1 &
done
wait
echo "gap-fill done at $(date +%H:%M) with $(ls research/data/rv_cache/*.npz | wc -l) symbols"

python3 scripts/trading_bot/rv_panel.py > "$LOG/rv_panel.log" 2>&1 || { echo PANEL_FAILED; exit 1; }
python3 scripts/trading_bot/rv_census.py > "$LOG/rv_census.log" 2>&1 || { echo CENSUS_FAILED; exit 1; }
/usr/bin/time -v python3 scripts/trading_bot/rv_sweep.py --stage design > "$LOG/rv_design.log" 2>&1 \
  || { echo DESIGN_FAILED; exit 1; }
echo "PIPELINE_DONE $(date +%H:%M)"
