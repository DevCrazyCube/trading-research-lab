#!/usr/bin/env bash
# Keep the window-2 transaction-body decode loop (run_free_decode.sh) alive across crashes/reboots.
# READ-ONLY free public Solana RPC: getBlock/getTransaction only. NO orders, NO money, NO wallet, NO writes.
# Relaunch rule mirrors T34_RESTART_2026-08-25.md §5.3 (verbatim, same endpoint/args -> no metadata drift).
# Guard: if the stage has completed (rc=0 marker), do NOT relaunch -- b9d re-scanning the done-sets every
# tick would be pure waste. b9d itself is idempotent (resumes on done_blocks/done_transactions).
cd /home/anont/meme || exit 1
LOG=research/b11m_window2/logs/free_decode.log
WLOG=research/b11m_window2/logs/free_decode_watchdog.log

# 1) already complete? nothing to do.
if [ -f "$LOG" ] && grep -q "=== COLLECTION COMPLETE (rc=0) ===" "$LOG" 2>/dev/null; then
  exit 0
fi

# 2) launcher loop alive? nothing to do.
if pgrep -f "run_free_decode.sh" >/dev/null 2>&1; then
  exit 0
fi

# 3) down and not complete -> relaunch verbatim (T34 §5.3).
setsid nohup research/b11m_window2/run_free_decode.sh >/dev/null 2>&1 < /dev/null &
echo "$(date -Is) watchdog: window-2 free_decode loop was DOWN -> relaunched (pid $!)" >> "$WLOG"
