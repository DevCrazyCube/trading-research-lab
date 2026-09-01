#!/usr/bin/env bash
# Keep MEME ARENA alive: the runtime driver (paper forward measurement) + the read-only dashboard. Data-
# only — no wallet, no orders, only appends to hash-chained ledgers. flock-guarded so a second watchdog
# can't double-run the runtime (which would double-count paper entries). Re-arm is session-only.
set -u

ROOT="/home/anont/meme"
DATA="$ROOT/research/data/arena"
LOCK="$DATA/watchdog.lock"
LOG="$DATA/watchdog.log"
RETIREMENT="$DATA/RETIREMENT.json"
RUN_SESSION="meme-arena-runtime"
DASH_SESSION="meme-arena-dash"
RUN_CMD="cd $ROOT && exec python3 -m scripts.trading_bot.memebot.arena.runtime"
DASH_CMD="cd $ROOT && exec python3 -m scripts.trading_bot.memebot.arena.dashboard.server"

mkdir -p "$DATA"
if [[ -f "$RETIREMENT" ]]; then
  echo "REFUSED: MEME ARENA retired; see $RETIREMENT" >&2
  exit 2
fi
log() { printf '%s %s\n' "$(date -u +%FT%TZ)" "$1" >> "$LOG"; }
alive() { tmux has-session -t "=$1" 2>/dev/null; }

exec 9>"$LOCK"
if ! flock -n 9; then
  echo "another arena watchdog owns the lock" >&2
  exit 1
fi

log "arena watchdog up (runtime + dashboard; data-only)"
while true; do
  alive "$RUN_SESSION"  || { log "starting runtime";  tmux new-session -d -s "$RUN_SESSION"  "bash -lc \"$RUN_CMD  >> '$DATA/runtime.log' 2>&1\""; }
  alive "$DASH_SESSION" || { log "starting dashboard"; tmux new-session -d -s "$DASH_SESSION" "bash -lc \"$DASH_CMD >> '$DATA/dashboard.log' 2>&1\""; }
  sleep 10
done
