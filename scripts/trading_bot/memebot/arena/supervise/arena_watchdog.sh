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
BUNDLE_SESSION="meme-arena-bundle-v2"
MIGRATION_SESSION="meme-arena-migration"
DASH_SESSION="meme-arena-dash"
FEED_CMD="cd $ROOT && exec python3 -m scripts.trading_bot.memebot listen"
RUN_CMD="cd $ROOT && exec python3 -m scripts.trading_bot.memebot.arena.runtime"
BUNDLE_CMD="cd $ROOT && exec python3 -m scripts.trading_bot.memebot.arena.bundle_v2_runtime"
MIGRATION_CMD="cd $ROOT && exec python3 -m scripts.trading_bot.memebot.arena.migration_acceptance_runtime"
DASH_CMD="cd $ROOT && exec python3 -m scripts.trading_bot.memebot.arena.dashboard.server"
ACT_DIR="$ROOT/research/trading_bot/memebot/arena/activations"

# tmux sessions do not inherit future shell state. Load the gitignored research credentials at each
# watchdog boot so a laptop restart cannot silently launch a keyless paid-data runner.
if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

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

# The trade feed is now the pump.fun program's on-chain anchor events via our FUNDED Helius logsSubscribe
# (PumpPortal IP-banned us 2026-09-02). A Helius endpoint in env OR the repo .env is what authorizes the
# trade-consuming arms now; a legacy PUMPPORTAL_DATA_API_KEY still counts.
feed_ready() {
  [[ -n "${HELIUS_API_KEY:-}${HELIUS_RPC_URL:-}${PUMPPORTAL_DATA_API_KEY:-}" ]] && return 0
  grep -qE '^(HELIUS_API_KEY|HELIUS_RPC_URL|PUMPPORTAL_DATA_API_KEY)=' "$ROOT/.env" 2>/dev/null
}

log "arena watchdog up (listener + three paper arms + dashboard; no wallet/orders)"
if ! feed_ready; then
  log "trade arms blocked: no Helius/feed endpoint in env or .env (create/migration listener only)"
fi
while true; do
  alive "$FEED_SESSION" || { log "starting read-only listener"; tmux new-session -d -s "$FEED_SESSION" "bash -lc \"$FEED_CMD >> '$DATA/listener.log' 2>&1\""; }
  [[ ! -f "$ACT_DIR/VIRALITY_ARRIVAL_V2_2.json" ]] || alive "$RUN_SESSION" || { log "starting runtime"; tmux new-session -d -s "$RUN_SESSION" "bash -lc \"$RUN_CMD >> '$DATA/runtime.log' 2>&1\""; }
  if feed_ready; then
    [[ ! -f "$ACT_DIR/BUNDLE_MOMENTUM_V2.json" ]] || alive "$BUNDLE_SESSION" || { log "starting bundle-v2 arm"; tmux new-session -d -s "$BUNDLE_SESSION" "bash -lc \"$BUNDLE_CMD >> '$DATA/bundle_v2.log' 2>&1\""; }
    [[ ! -f "$ACT_DIR/MIGRATION_ACCEPTANCE_V1.json" ]] || alive "$MIGRATION_SESSION" || { log "starting migration arm"; tmux new-session -d -s "$MIGRATION_SESSION" "bash -lc \"$MIGRATION_CMD >> '$DATA/migration.log' 2>&1\""; }
  fi
  alive "$DASH_SESSION" || { log "starting dashboard"; tmux new-session -d -s "$DASH_SESSION" "bash -lc \"$DASH_CMD >> '$DATA/dashboard.log' 2>&1\""; }
  sleep 10
done
