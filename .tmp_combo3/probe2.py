import sqlite3, json, hashlib, os, statistics
R='/home/anont/meme/research/'
OUT=open('/home/anont/meme/.tmp_combo3/out_probe.txt','w')
def p(*a): print(*a, file=OUT)
db=sqlite3.connect(R+'midcap/grad_ohlcv.sqlite')
p('cnt', db.execute('select count(*), sum(n_bars) from ohlcv').fetchone())
p('status', db.execute('select status, count(*) from ohlcv group by status').fetchall())
p('ts range', db.execute('select min(first_ts),max(first_ts),min(last_ts),max(last_ts) from ohlcv where n_bars>0').fetchone())
h={0:0,1:0,2:0}; nb={0:0,1:0,2:0}
gaps={}; nbars_dist=[]
for m,n,bj in db.execute('select mint,n_bars,bars_json from ohlcv where n_bars>0'):
    k=int(hashlib.md5(m.encode()).hexdigest(),16)%3
    h[k]+=1; nb[k]+=(n or 0)
    if k!=0:
        nbars_dist.append(n)
        bb=sorted(json.loads(bj), key=lambda x:x[0])
        for i in range(1,len(bb)):
            d=bb[i][0]-bb[i-1][0]
            gaps[d]=gaps.get(d,0)+1
p('splitmints',h,'bars',nb)
p('nbars quantiles', [sorted(nbars_dist)[int(q*(len(nbars_dist)-1))] for q in (0,.1,.25,.5,.75,.9,1)])
tot=sum(gaps.values())
p('ngaps',tot,'gap60 frac', gaps.get(60,0)/tot)
p('gaps top', sorted(gaps.items(), key=lambda x:-x[1])[:10])
# zero volume bars?
zv=0; tv=0
for m,bj in db.execute('select mint,bars_json from ohlcv where n_bars>0'):
    if int(hashlib.md5(m.encode()).hexdigest(),16)%3==0: continue
    for b in json.loads(bj):
        tv+=1
        if b[5]==0: zv+=1
p('zero-vol bars', zv, 'of', tv)

# snapshots
snapmints=set(); tsmin=None; tsmax=None; nl=0
meta={}
with open(R+'midcap/fresh_snapshots.jsonl') as f:
    for line in f:
        nl+=1
        try: d=json.loads(line)
        except: continue
        if 'mint' not in d: continue
        t=d['ts_ms']//1000
        tsmin=t if tsmin is None else min(tsmin,t); tsmax=t if tsmax is None else max(tsmax,t)
        snapmints.add(d['mint'])
p('snap lines',nl,'mints',len(snapmints),'ts range',tsmin,tsmax)
ohl=set(m for (m,) in db.execute('select mint from ohlcv where n_bars>0'))
p('ohlcv mints', len(ohl), 'overlap with snaps', len(ohl & snapmints))
db2=sqlite3.connect(R+'b11a/window_labels.sqlite')
p('wl cols', [d[1] for d in db2.execute('PRAGMA table_info(window_label)')])
p('wl cnt', db2.execute('select count(*), sum(complete) from window_label').fetchone())
wl=set(m for (m,) in db2.execute('select mint from window_label'))
p('ohlcv in wl', len(ohl & wl))
p('wl blocktime range', db2.execute('select min(block_time),max(block_time) from window_label').fetchone())
try:
    import numpy; p('numpy', numpy.__version__)
except Exception: p('NO numpy')
OUT.close()
