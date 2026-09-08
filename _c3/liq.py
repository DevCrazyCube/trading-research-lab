import numpy as np, sys, json
sys.path.insert(0,'/home/anont/meme/_c3')
from engine import load, net_array, evaluate
P=load(); N=len(P['TS']); FN=P['FEATNAMES']
CN=[c[0] for c in P['COMBOS']]
O=open('/home/anont/meme/_c3/liq.out','w')
def p(*a): O.write(' '.join(str(x) for x in a)+'\n')
# reconstruct per-bar volume + entry-bar volume
import sqlite3, json as J, hashlib
def H(m): return int(hashlib.md5(m.encode()).hexdigest(),16)%3
c=sqlite3.connect('file:/home/anont/meme/research/midcap/grad_ohlcv.sqlite?mode=ro',uri=True)
bars={}
for m,bj,st in c.execute("select mint,bars_json,status from ohlcv"):
    if H(m)==0 or st!='ok' or not bj: continue
    b=J.loads(bj)
    if len(b)<3: continue
    b.sort(key=lambda x:x[0]); bars[m]=np.asarray(b,float)
segs=[]; segs_next=[]; segs_px=[]
for m in P['mints']:
    a=bars[m]; v=a[:,5]; cl=a[:,4]
    nx=np.empty(len(v)); nx[:-1]=v[1:]; nx[-1]=np.nan     # volume of the ENTRY bar (i+1)
    segs.append(v); segs_next.append(nx); segs_px.append(cl)
VOL=np.concatenate(segs); ENTVOL=np.concatenate(segs_next); CLS=np.concatenate(segs_px)
p("bar volume quantiles (USD?)", np.round(np.quantile(VOL,[0.05,0.25,0.5,0.75,0.9,0.99]),2))
p("entry-bar volume quantiles", np.round(np.nanquantile(ENTVOL,[0.05,0.25,0.5,0.75,0.9,0.99]),2))
p("mcap proxy = close*1e9 quantiles", np.round(np.quantile(CLS*1e9,[0.05,0.25,0.5,0.75,0.95]),0))
for thr in (0,60,200,600,2000,10000):
    m=ENTVOL>=thr
    p("entry-vol>=%6d : bars %6d (%.1f%%) mints %3d"%(thr,m.sum(),100*m.mean(),len(set(P['mint_id'][m]))))
np.save('/home/anont/meme/_c3/entvol.npy',ENTVOL)

p("\n=== baselines and the cumvol_log=q1 cell under a tradability floor ===")
def bk(v,q):
    TR=P['bar_h']==1; x=v[TR]; x=x[np.isfinite(x)]
    e=np.unique(np.quantile(x,np.linspace(0,1,q+1)[1:-1]))
    return np.searchsorted(e,v,'right').astype(np.int8)
cv=bk(P['FEAT'][:,FN.index('cumvol_log')],6)
rv=bk(P['FEAT'][:,FN.index('rvol10')],6)
for thr in (0,600,2000):
    tm=(ENTVOL>=thr)
    for ci in [CN.index('t15'),CN.index('t60tr35')]:
        nt=net_array(ci)
        b=evaluate(tm,ci,nt,hsel=1); b2=evaluate(tm,ci,nt,hsel=2)
        p(" thr=%5d %-8s BASE tr %+7.4f (n%5d k%3d) va %+7.4f (n%5d k%3d)"%(thr,CN[ci],b['mean'],b['n'],b['k'],b2['mean'],b2['n'],b2['k']))
        for nm,mk in (('cumvol_q1',cv<=0),('cumvol_q12',cv<=1),('rvol10_q1',rv<=0)):
            r=evaluate(tm&mk,ci,nt,hsel=1); r2=evaluate(tm&mk,ci,nt,hsel=2)
            p("        %-11s tr %+7.4f (n%5d k%3d)  va %+7.4f (n%5d k%3d)"%(nm,
              r['mean'] if r else float('nan'), r['n'] if r else 0, r['k'] if r else 0,
              r2['mean'] if r2 else float('nan'), r2['n'] if r2 else 0, r2['k'] if r2 else 0))
O.close()
