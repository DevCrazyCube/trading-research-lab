#!/usr/bin/env bash
# status.sh -- 1 overzicht van wat alle motoren zeggen.  Draai:  bash status.sh
cd "$(dirname "$0")" || exit 1
line(){ printf '%s\n' "----------------------------------------------------------------------"; }
echo "======================================================================"
echo "  STATUS  --  $(date '+%Y-%m-%d %H:%M')     (papertrading, 0 euro, geen orders)"
echo "======================================================================"

line; echo "1. DE MAND  (14 getoetste strategieen, forward)"
python -m scripts.trading_bot.basket_eval report 2>/dev/null \
  | grep -iE "settled sessions|VERDICT|PAPER-LOGGER" | head -3 \
  || echo "   (geen data)"

line; echo "2. NEWSDESK  (leest nieuws -> stelt trades voor)"
python -m scripts.trading_bot.newsdesk score 2>/dev/null \
  | grep -iE "resolved_setups|verdict" | head -3 \
  || echo "   (nog geen resoluties)"

line; echo "3. PREDICTION MARKETS  (agent-kansen vs de menigte)"
python3 -m scripts.trading_bot.predmarket score 2>/dev/null \
  | grep -iE "resolved_markets|primary_metric|verdict" | head -3 \
  || echo "   (nog geen resoluties)"

line; echo "4. AUTONOOM SYSTEEM  (draait de duurzame cron?)"
crontab -l 2>/dev/null | grep -q durable_tick \
  && echo "   AAN -- vuurt elke 3 uur (00 03 06 09 12 15 18 21)" \
  || echo "   UIT -- draai: bash scripts/agent_graph/install_durable_cron.sh"
echo "   laatste ticks:"
tail -3 scripts/agent_graph/logs/durable_heartbeat.log 2>/dev/null | sed 's/^/     /' \
  || echo "     (nog geen ticks)"

line; echo "5. LAATSTE DENK-RONDE  (strateeg / uitvinder)"
latest=$(ls -t scripts/agent_graph/logs/claude_*.log 2>/dev/null | head -1)
[ -n "$latest" ] && tail -4 "$latest" | sed 's/^/     /' \
  || echo "     (denk-deel draait voor het eerst rond 23:00)"

line
echo "MEEKIJKEN LIVE:  tail -f scripts/agent_graph/logs/durable_heartbeat.log"
echo "ALLE COMMANDO'S:  cat COMMANDS.txt"
echo "======================================================================"
