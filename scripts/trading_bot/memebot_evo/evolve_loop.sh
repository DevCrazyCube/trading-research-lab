#!/usr/bin/env bash
# MEMEBOT_EVO continuous evolution loop (PAPER ONLY -- no orders/wallet/SOL/on-chain writes).
# Each interval runs ONE forward cycle: track (refresh+resolve open paper positions) then scan (open
# new frozen paper entries) for EVERY active genome, then attempts a selection generation. Selection
# is a no-op until >= MIN_MATURE genomes reach the pre-registered N_min resolved-trade minimum, so the
# early loop just ACCUMULATES forward trades -- which is the honest state below the minimum.
#
# CPU-only. No GPU, no neural net, no training. Reuses the memebot's free/keyless feed read-only.
set -u
cd /home/anont/meme || exit 1
export PATH="/home/anont/.local/bin:/usr/local/bin:/usr/bin:/bin"
DIR="scripts/trading_bot/memebot_evo"
LOG="$DIR/evolve_run.log"
INTERVAL="${EVO_INTERVAL:-180}"   # seconds between cycles (override with EVO_INTERVAL)

echo "$(date -u +%FT%TZ) evolve_loop start (interval=${INTERVAL}s)" >>"$LOG"
while true; do
  python -m scripts.trading_bot.memebot_evo evolve --cycles 1 \
      >>"$LOG" 2>&1 || echo "$(date -u +%FT%TZ) evolve cycle errored (continuing)" >>"$LOG"
  sleep "$INTERVAL"
done
