import json,urllib.request,time
GT='https://api.geckoterminal.com/api/v2'
POOL='9jDpceRLx7seEYSdbddz7o1KzKTwjBzx5kaXSgJgkC1H'
NOW=int(time.time())
def call(bt):
    u='%s/networks/solana/pools/%s/ohlcv/minute?aggregate=1&limit=1000&before_timestamp=%d'%(GT,POOL,bt)
    for t in range(300):
        try:
            r=urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0','Accept':'application/json'})
            with urllib.request.urlopen(r,timeout=45) as f:
                d=json.loads(f.read()); return 200,len(d['data']['attributes']['ohlcv_list'] or [])
        except urllib.error.HTTPError as e:
            if e.code==429: time.sleep(10); continue
            return e.code,0
        except Exception: time.sleep(6)
    return 'starved',0
for days in (30,60,120,180,240,300):
    code,n=call(NOW-days*86400)
    print('MINUTE before=now-%3dd -> HTTP %s bars=%d'%(days,code,n),flush=True)
print('HZ2 DONE',flush=True)
