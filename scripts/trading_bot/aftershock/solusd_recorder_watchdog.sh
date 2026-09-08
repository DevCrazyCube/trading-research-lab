#!/usr/bin/env bash
# Read-only PAC SOL/USD recorder. No key, wallet, order, or transaction path.
cd /home/anont/meme || exit 1
if ! pgrep -f '^python -m scripts\.trading_bot\.aftershock\.solusd_recorder$' >/dev/null 2>&1; then
  setsid nohup python -m scripts.trading_bot.aftershock.solusd_recorder \
    >> scripts/trading_bot/aftershock/solusd_recorder.log 2>&1 < /dev/null &
  echo "$(date -Is) watchdog: PAC SOL/USD recorder restarted (pid $!)" \
    >> scripts/trading_bot/aftershock/solusd_recorder_watchdog.log
fi
