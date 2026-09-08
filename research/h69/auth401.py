import json, urllib.request, time, datetime
GT = 'https://api.geckoterminal.com/api/v2'

def raw(u):
    for t in range(15):
        try:
            r = urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'})
            with urllib.request.urlopen(r, timeout=45) as f:
                d = json.loads(f.read())
                L = d['data']['attributes']['ohlcv_list']
                return 200, len(L), ((L[-1][0], L[0][0]) if L else None)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(25); continue
            try:
                body = e.read()[:200].decode()
            except Exception:
                body = ''
            return e.code, 0, body
        except Exception as ex:
            time.sleep(10); continue
    return 429, 0, 'gave up after 15 retries'

def pools(mint):
    for t in range(12):
        try:
            r = urllib.request.Request('%s/networks/solana/tokens/%s/pools' % (GT, mint),
                                       headers={'User-Agent': 'Mozilla/5.0'})
            return json.load(urllib.request.urlopen(r, timeout=45))
        except urllib.error.HTTPError as e:
            print('  pools retry HTTP %s' % e.code, flush=True); time.sleep(20)
        except Exception as e:
            print('  pools retry %s' % str(e)[:60], flush=True); time.sleep(10)
    raise SystemExit('pools() gave up')

d = pools('CqqF99vTsqqwjJ5YMBVRMVJT2Cu1jTgmGnsw8S9Hbonk')
time.sleep(3)
p = d['data'][0]
OLDPOOL = p['attributes']['address']
created = p['attributes']['pool_created_at']
ct = int(datetime.datetime.strptime(created, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=datetime.UTC).timestamp())
print('OLD pool', OLDPOOL, 'created', created, flush=True)
NOW = int(time.time())

cases = [
    ('no before_timestamp       ', '%s/networks/solana/pools/%s/ohlcv/minute?aggregate=1&limit=1000' % (GT, OLDPOOL)),
    ('before=now                ', '%s/networks/solana/pools/%s/ohlcv/minute?aggregate=1&limit=1000&before_timestamp=%d' % (GT, OLDPOOL, NOW)),
    ('before=now-7d             ', '%s/networks/solana/pools/%s/ohlcv/minute?aggregate=1&limit=1000&before_timestamp=%d' % (GT, OLDPOOL, NOW - 7 * 86400)),
    ('before=now-90d            ', '%s/networks/solana/pools/%s/ohlcv/minute?aggregate=1&limit=1000&before_timestamp=%d' % (GT, OLDPOOL, NOW - 90 * 86400)),
    ('before=migration+1000m    ', '%s/networks/solana/pools/%s/ohlcv/minute?aggregate=1&limit=1000&before_timestamp=%d' % (GT, OLDPOOL, ct + 60000)),
    ('DAY before=migration+1000d', '%s/networks/solana/pools/%s/ohlcv/day?aggregate=1&limit=1000&before_timestamp=%d' % (GT, OLDPOOL, ct + 86400000)),
]
for name, u in cases:
    code, n, extra = raw(u)
    ex = extra
    if isinstance(extra, tuple):
        ex = '%s .. %s' % (datetime.datetime.fromtimestamp(extra[0], datetime.UTC).strftime('%Y-%m-%d %H:%M'),
                           datetime.datetime.fromtimestamp(extra[1], datetime.UTC).strftime('%Y-%m-%d %H:%M'))
    print('%s -> HTTP %s  bars=%d  %s' % (name, code, n, ex), flush=True)
    time.sleep(4)
print('AUTH401 DONE', flush=True)
