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
FEED_SESSION="meme-arena-listener"
RUN_SESSION="meme-arena-runtime"
BUNDLE_SESSION="meme-arena-bundle"
GRAD_SESSION="meme-arena-grad"
DASH_SESSION="meme-arena-dash"
FEED_CMD="cd $ROOT && exec python3 -m scripts.trading_bot.memebot listen"
RUN_CMD="cd $ROOT && exec python3 -m scripts.trading_bot.memebot.arena.runtime"
BUNDLE_CMD="cd $ROOT && exec python3 -m scripts.trading_bot.memebot.arena.bundle_runtime"
GRAD_CMD="cd $ROOT && exec python3 -m scripts.trading_bot.memebot.arena.graduation_runtime"
DASH_CMD="cd $ROOT && exec python3 -m scripts.trading_bot.memebot.arena.dashboard.server"
ACT_DIR="$ROOT/research/trading_bot/memebot/arena/activations"

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

log "arena watchdog up (listener + three paper arms + dashboard; no wallet/orders)"
if [[ -z "${PUMPPORTAL_DATA_API_KEY:-}" ]]; then
  log "paid arms blocked: PUMPPORTAL_DATA_API_KEY absent (free create/migration listener only)"
fi
while true; do
  alive "$FEED_SESSION" || { log "starting read-only listener"; tmux new-session -d -s "$FEED_SESSION" "bash -lc \"$FEED_CMD >> '$DATA/listener.log' 2>&1\""; }
  [[ ! -f "$ACT_DIR/VIRALITY_ARRIVAL_V2_2.json" ]] || alive "$RUN_SESSION" || { log "starting runtime"; tmux new-session -d -s "$RUN_SESSION" "bash -lc \"$RUN_CMD >> '$DATA/runtime.log' 2>&1\""; }
  if [[ -n "${PUMPPORTAL_DATA_API_KEY:-}" ]]; then
    [[ ! -f "$ACT_DIR/BUNDLE_MOMENTUM_V1.json" ]] || alive "$BUNDLE_SESSION" || { log "starting bundle arm"; tmux new-session -d -s "$BUNDLE_SESSION" "bash -lc \"$BUNDLE_CMD >> '$DATA/bundle.log' 2>&1\""; }
    [[ ! -f "$ACT_DIR/MEMEBOT_GRAD_V1.json" ]] || alive "$GRAD_SESSION" || { log "starting graduation arm"; tmux new-session -d -s "$GRAD_SESSION" "bash -lc \"$GRAD_CMD >> '$DATA/graduation.log' 2>&1\""; }
  fi
  alive "$DASH_SESSION" || { log "starting dashboard"; tmux new-session -d -s "$DASH_SESSION" "bash -lc \"$DASH_CMD >> '$DATA/dashboard.log' 2>&1\""; }
  sleep 10
done
