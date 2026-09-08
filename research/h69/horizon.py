import json, urllib.request, time, datetime
GT = 'https://api.geckoterminal.com/api/v2'
POOL = '9jDpceRLx7seEYSdbddz7o1KzKTwjBzx5kaXSgJgkC1H'  # LaunchLab migrated, created 2025-09-27
NOW = int(time.time())

def call(u):
    for t in range(200):
        try:
            r = urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'})
            with urllib.request.urlopen(r, timeout=45) as f:
                d = json.loads(f.read())
                L = d['data']['attributes']['ohlcv_list'] or []
                return 200, len(L)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(12); continue
            return e.code, 0
        except Exception:
            time.sleep(8)
    return 'starved', 0

print('probing GeckoTerminal free-tier minute-OHLCV lookback horizon', flush=True)
for days in (1, 7, 14, 21, 30, 45, 60, 90, 180, 365):
    bt = NOW - days * 86400
    for res in ('minute', 'hour', 'day'):
        code, n = call('%s/networks/solana/pools/%s/ohlcv/%s?aggregate=1&limit=1000&before_timestamp=%d'
                       % (GT, POOL, res, bt))
        print('  before=now-%4dd  %-6s -> HTTP %s bars=%d' % (days, res, code, n), flush=True)
        if res == 'minute' and code == 401:
            # once minute is walled, still check hour/day then move on
            pass
print('HORIZON DONE', flush=True)
