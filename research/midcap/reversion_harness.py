import sqlite3, json, random, statistics
from collections import defaultdict
DB='/home/anont/meme/research/midcap/grad_ohlcv.sqlite'
TOLL=0.0114
def load():
    c=sqlite3.connect('file:%s?mode=ro'%DB,uri=True); out={}
    for mint,bj in c.execute("select mint,bars_json from ohlcv where n_bars>0"):
        b=json.loads(bj); d={}
        for r in b: d[int(r[0])]=r
        b=[d[k] for k in sorted(d)]
        if len(b)>=3: out[mint]=b
    return out
def grid(bars):
    t0,t1=bars[0][0],bars[-1][0]; bm={r[0]:r for r in bars}
    g=[]; lastc=bars[0][1]; t=t0
    while t<=t1:
        r=bm.get(t)
        if r: o,h,l,cl,v,real=r[1],r[2],r[3],r[4],r[5],1
        else: o=h=l=cl=lastc; v=0.0; real=0
        g.append((t,o,h,l,cl,v,real)); lastc=cl; t+=60
    return g
DATA=load(); GRIDS={m:grid(b) for m,b in DATA.items()}
def clstats(trades,rets):
    s=defaultdict(float); n=defaultdict(int)
    for t,x in zip(trades,rets): s[t['mint']]+=x; n[t['mint']]+=1
    ks=list(s); return ks,[s[k] for k in ks],[n[k] for k in ks]
def boot(ks,sums,cnts,B=1200,seed=7):
    K=len(ks)
    if K<3: return float('nan'),float('nan')
    rnd=random.Random(seed); ms=[]
    for _ in range(B):
        S=0.0; C=0
        for _ in range(K):
            j=rnd.randrange(K); S+=sums[j]; C+=cnts[j]
        ms.append(S/C*100 if C else 0.0)
    ms.sort(); return ms[int(.025*B)],ms[int(.975*B)]
def agg(trades,dropcharge=-0.30,toll=TOLL,B=1200,seed=7):
    if not trades: return None
    gr=[(dropcharge if t['xp'] is None else t['xp']/t['ep']-1.0) for t in trades]
    net=[x-toll for x in gr]
    ks,su,cn=clstats(trades,net); lo,hi=boot(ks,su,cn,B,seed)
    return dict(n=len(net),clusters=len(ks),mean=statistics.mean(net)*100,
                median=statistics.median(net)*100,gross=statistics.mean(gr)*100,
                gmedian=statistics.median(gr)*100,
                lo=lo,hi=hi,dropn=sum(1 for t in trades if t['xp'] is None))
def make(W,H,require_signal_real=True):
    out=[]
    for m,g in GRIDS.items():
        n=len(g)
        # prefix sums of vol & real
        pv=[0.0]*(n+1); pr=[0]*(n+1)
        for k in range(n): pv[k+1]=pv[k]+g[k][5]; pr[k+1]=pr[k]+g[k][6]
        for i in range(W,n-1):
            if require_signal_real and g[i][6]==0: continue
            ci=g[i][4]; cp=g[i-W][4]
            if cp<=0 or ci<=0: continue
            ep=g[i+1][1]
            if ep<=0: continue
            j=i+1+H
            out.append(dict(mint=m,ts=g[i][0],prior=ci/cp-1.0,ep=ep,
                            xp=(g[j][4] if j<n else None),
                            volw=pv[i+1]-pv[i-W+1],realfrac=(pr[i+1]-pr[i-W+1])/float(W)))
    return out
