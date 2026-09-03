#!/usr/bin/env bash
# MEMEBOT continuous loop (PAPER ONLY -- no orders/wallet/SOL/on-chain writes).
# Starts the detached PumpPortal realtime listener ONCE, then each cycle: scan -> track ->
# EVAL-AFTER-EACH-TRADE for BOTH frozen variants (MEMEBOT1 180-min, MEMEBOT_FAST 25-min+dead-exit).
cd /home/anont/meme || exit 1
export PATH="/home/anont/.local/bin:/usr/local/bin:/usr/bin:/bin"
DIR="research/trading_bot/memebot"
EVLOG="$DIR/eval_after_each_trade.jsonl"
PREV="$DIR/.eval_prev_counts.json"

# 1) Ensure the read-only PumpPortal new-token stream is running (detached, self-reconnecting).
if ! pgrep -f "scripts.trading_bot.memebot listen" >/dev/null 2>&1; then
  nohup python -m scripts.trading_bot.memebot listen >"$DIR/pumpportal_listener.log" 2>&1 &
fi

# 2) Reactive loop for both variants.
#    scan/track are network-bound (throttled GeckoTerminal polls); a `timeout` guards against a hung
#    socket stalling the whole loop, and stderr goes to a VISIBLE log (not /dev/null) so a REFUSED /
#    crash can never again silently no-op every cycle. track resolves BOTH variants (FAST first).
while true; do
  timeout 120 python -m scripts.trading_bot.memebot scan  >/dev/null 2>>"$DIR/loop_scan.err"
  timeout 180 python -m scripts.trading_bot.memebot track  >/dev/null 2>>"$DIR/loop_track.err"
  # Log a fresh eval snapshot for any variant whose resolved-trade count rose since last cycle.
  python -m scripts.trading_bot.memebot score 2>/dev/null | python3 -c "
import sys,json,datetime,os
prev_path='$PREV'; evlog='$EVLOG'
try: reports=json.load(sys.stdin)
except Exception: sys.exit()
try: prev=json.load(open(prev_path))
except Exception: prev={}
now={}
for inst,d in reports.items():
    n=(d.get('resolved_pass_trades',0) or 0)+(d.get('resolved_control_trades',0) or 0)
    now[inst]=n
    inp=d.get('inputs_that_are_not_results',{}) or {}
    sp=inp.get('screen_pass',{}) if isinstance(inp.get('screen_pass'),dict) else {}
    if inst in prev and n!=prev[inst]:
        row={'ts':datetime.datetime.now(datetime.timezone.utc).isoformat(),'instrument':inst,
             'resolved_pass':d.get('resolved_pass_trades'),'resolved_control':d.get('resolved_control_trades'),
             'expectancy_R':sp.get('expectancy_R'),
             'edge_vs_null_R':inp.get('expectancy_edge_of_screen_over_null_R'),
             'beats_zero':inp.get('screen_expectancy_beats_zero'),'beats_null':inp.get('screen_expectancy_beats_null'),
             'reason_counts':inp.get('resolution_reason_counts'),
             'verdict':d.get('verdict'),'kill':(d.get('kill_switch') or {}).get('verdict')}
        open(evlog,'a').write(json.dumps(row)+'\n')
json.dump(now, open(prev_path,'w'))
" 2>/dev/null
  sleep 90
done
