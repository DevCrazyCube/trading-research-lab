import json,time,datetime,sys
sys.path.insert(0,'/home/anont/meme/research/h69')
from gtlib import *
S=json.load(open('/home/anont/meme/research/h69/h69_sample.json'))['sample']
ds=json.load(open('/home/anont/meme/research/h69/ds_pairs.json'))
tests=[x for x in S if x['mint'] not in ds][:3]+[x for x in S if x['mint'] in ds][:1]
for x in tests:
    d=pools_for(x['mint']); time.sleep(4)
    if 'data' not in d: print(x['mint'][:12],'no-pools',list(d),flush=True); continue
    b=pick_pool(d)
    if not b: print(x['mint'][:12],'zero pools',flush=True); continue
    addr,created,res,name=b
    ct=int(datetime.datetime.strptime(created,'%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=datetime.UTC).timestamp())
    age=(time.time()-ct)/86400
    L,err=ohlcv_minute(addr, before_ts=ct+1000*60); time.sleep(4)
    if L is None: print('%s pool=%s age=%.0fd -> OHLCV ERR %s'%(x['mint'][:12],addr[:10],age,err),flush=True); continue
    if not L:
        print('%s pool=%s age=%.0fd res=$%.0f -> 0 minute bars (NO RETENTION)'%(x['mint'][:12],addr[:10],age,res),flush=True)
    else:
        L=sorted(L,key=lambda z:z[0])
        print('%s pool=%s age=%.0fd res=$%.0f -> %d bars  %s .. %s'%(
            x['mint'][:12],addr[:10],age,res,len(L),
            datetime.datetime.fromtimestamp(L[0][0],datetime.UTC).strftime('%Y-%m-%d %H:%M'),
            datetime.datetime.fromtimestamp(L[-1][0],datetime.UTC).strftime('%Y-%m-%d %H:%M')),flush=True)
