import json,urllib.request,time,datetime
GT='https://api.geckoterminal.com/api/v2'
POOL='9jDpceRLx7seEYSdbddz7o1KzKTwjBzx5kaXSgJgkC1H'
CT=int(datetime.datetime(2025,9,27,16,7,56,tzinfo=datetime.UTC).timestamp())
def call(u,label):
    for t in range(400):
        try:
            r=urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0','Accept':'application/json'})
            with urllib.request.urlopen(r,timeout=45) as f:
                d=json.loads(f.read()); L=d['data']['attributes']['ohlcv_list'] or []
                L=sorted(L,key=lambda z:z[0])
                if L:
                    print('%s -> 200  bars=%d  %s .. %s'%(label,len(L),
                      datetime.datetime.fromtimestamp(L[0][0],datetime.UTC).strftime('%Y-%m-%d %H:%M'),
                      datetime.datetime.fromtimestamp(L[-1][0],datetime.UTC).strftime('%Y-%m-%d %H:%M')),flush=True)
                else:
                    print('%s -> 200  bars=0  (EMPTY)'%label,flush=True)
                return
        except urllib.error.HTTPError as e:
            if e.code==429: time.sleep(15); continue
            print('%s -> HTTP %s'%(label,e.code),flush=True); return
        except Exception as ex: time.sleep(8)
    print('%s -> starved out'%label,flush=True)
call('%s/networks/solana/pools/%s/ohlcv/minute?aggregate=1&limit=1000&before_timestamp=%d'%(GT,POOL,CT+60000),
     'MINUTE @ migration+1000m (2025-09-27, 341d old)')
print('RET1 DONE',flush=True)
