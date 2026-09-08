import sqlite3, json, hashlib, statistics
from collections import Counter
OUT=open('/home/anont/meme/.scratch_hv/inspect.txt','w')
def p(*a): OUT.write(' '.join(str(x) for x in a)+'\n')
c=sqlite3.connect('file:/home/anont/meme/research/midcap/grad_ohlcv.sqlite?mode=ro',uri=True)
rows=c.execute("select mint,pool,n_bars,first_ts,last_ts,bars_json,status from ohlcv").fetchall()
p('total rows',len(rows))
p('status',Counter(r[6] for r in rows))
p('h dist',Counter(int(hashlib.md5(r[0].encode()).hexdigest(),16)%3 for r in rows))
ex=[r for r in rows if int(hashlib.md5(r[0].encode()).hexdigest(),16)%3==1 and r[2] and r[2]>60]
p('n h1 with >60 bars',len(ex))
r=ex[0]
b=json.loads(r[5])
p('mint',r[0],'n_bars',r[2],'status',r[6])
p('first 3 raw (newest first):', b[:3])
p('last 3 raw:', b[-3:])
bs=sorted(b,key=lambda x:x[0])
gaps=[bs[i+1][0]-bs[i][0] for i in range(len(bs)-1)]
p('gap counter',Counter(gaps).most_common(8))
p('zero vol bars',sum(1 for x in bs if x[5]==0),'of',len(bs))
vols=[];closes=[];nots=[]
for rr in ex[:60]:
    bb=sorted(json.loads(rr[5]),key=lambda x:x[0])
    for x in bb:
        vols.append(x[5]); closes.append(x[4]); nots.append(x[4]*x[5])
def q(a,f): a=sorted(a); return a[min(len(a)-1,int(f*len(a)))]
p('close med',statistics.median(closes),'min',min(closes),'max',max(closes))
p('vol med',statistics.median(vols),'p10',q(vols,.1),'p90',q(vols,.9),'max',max(vols))
p('cxv med',statistics.median(nots),'p10',q(nots,.1),'p90',q(nots,.9),'max',max(nots))
allg=Counter(); zc=0; tot=0
for rr in ex[:200]:
    bb=sorted(json.loads(rr[5]),key=lambda x:x[0])
    for i in range(len(bb)-1): allg[bb[i+1][0]-bb[i][0]]+=1
    for x in bb:
        tot+=1
        if x[5]==0: zc+=1
p('global gaps',allg.most_common(10))
p('zero-vol',zc,'/',tot)
p('nbars dist', Counter(min(r[2]//50*50,500) for r in rows if r[2]))
OUT.close()
