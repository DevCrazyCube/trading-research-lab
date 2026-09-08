#!/usr/bin/env bash
# Detached, resumable transaction-body decode for the window-2 deadness-screen OOS test.
# Points b9d at the FREE public Solana RPC (read-only getBlock/getTransaction). Restart loop:
# b9d run checkpoints per row (raw_block_signatures / raw_transaction) and resumes via
# done_blocks / done_transactions, so on any crash we sleep and re-launch -- same endpoint, so
# no metadata drift. Exit 0 from b9d means the frozen population is fully collected: stop.
# NO orders, NO money, NO wallet, NO on-chain writes. getBlock + getTransaction only.
set -u
cd /home/anont/meme
export FREE_SOLANA_RPC="https://api.mainnet-beta.solana.com"

OUT=research/b11m_window2/b11a_bodies.sqlite
B9C=research/b11m_window2/b11a_signatures.sqlite
B9A=research/b11m_window2/b11a_subsample.sqlite
CUTOFF=438854169
LOG=research/b11m_window2/logs/free_decode.log

mkdir -p research/b11m_window2/logs
MAX_RESTARTS=1000
attempt=0
while [ "$attempt" -lt "$MAX_RESTARTS" ]; do
  attempt=$((attempt+1))
  echo "=== attempt $attempt at $(date -u +%FT%TZ) ===" >>"$LOG"
  python3 scripts/b9d_transaction_bodies.py run "$OUT" \
      --rpc-env FREE_SOLANA_RPC \
      --b9c "$B9C" --b9a "$B9A" \
      --cutoff-slot "$CUTOFF" \
      --workers 2 --calls-per-second 4 \
      --progress-every 200 >>"$LOG" 2>&1
  rc=$?
  echo "=== attempt $attempt exited rc=$rc at $(date -u +%FT%TZ) ===" >>"$LOG"
  if [ "$rc" -eq 0 ]; then
    echo "=== COLLECTION COMPLETE (rc=0) ===" >>"$LOG"
    break
  fi
  sleep 60
done
echo "=== launcher finished after $attempt attempt(s) at $(date -u +%FT%TZ) ===" >>"$LOG"
