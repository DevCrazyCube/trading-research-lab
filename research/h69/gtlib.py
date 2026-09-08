import json,urllib.request,time
GT='https://api.geckoterminal.com/api/v2'
def get(u,tries=12,pace=0.0):
    for t in range(tries):
        try:
            r=urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0','Accept':'application/json'})
            d=json.load(urllib.request.urlopen(r,timeout=45))
            time.sleep(pace); return d
        except urllib.error.HTTPError as e:
            if e.code==429: time.sleep(20); continue
            if e.code==404: return {'_404':True}
            return {'_http':e.code}
        except Exception: time.sleep(8)
    return {'_fail':True}

def pools_for(mint):
    return get('%s/networks/solana/tokens/%s/pools'%(GT,mint))

def pick_pool(d):
    """largest-reserve pool; return (pool_addr, created_iso, reserve)"""
    ps=d.get('data') or []
    best=None
    for p in ps:
        a=p['attributes']
        try: res=float(a.get('reserve_in_usd') or 0)
        except: res=0.0
        addr=p['id'].split('solana_')[-1]
        if best is None or res>best[2]: best=(addr,a.get('pool_created_at'),res,a.get('name'))
    return best

def ohlcv_minute(pool, before_ts=None, limit=1000):
    u='%s/networks/solana/pools/%s/ohlcv/minute?aggregate=1&limit=%d'%(GT,pool,limit)
    if before_ts: u+='&before_timestamp=%d'%before_ts
    d=get(u)
    if not isinstance(d,dict) or 'data' not in d: return None,d
    return (d['data']['attributes'].get('ohlcv_list') or []), None
