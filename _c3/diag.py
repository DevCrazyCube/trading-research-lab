import numpy as np, json, sys, pickle, hashlib
sys.path.insert(0,'/home/anont/meme/_c3')
from engine import load, net_array, evaluate
O=open('/home/anont/meme/_c3/diag.out','w')
def p(*a): O.write(' '.join(str(x) for x in a)+'\n')
P=load(); N=len(P['TS'])
mints=P['mints']; mid=P['mint_id']
import sqlite3, json as J
c=sqlite3.connect('file:/home/anont/meme/research/midcap/grad_ohlcv.sqlite?mode=ro',uri=True)
def Hh(m): return int(hashlib.md5(m.encode()).hexdigest(),16)%3
bars={}
for m,bj,st in c.execute("select mint,bars_json,status from ohlcv"):
    if Hh(m)==0 or st!='ok' or not bj: continue
    b=J.loads(bj); b.sort(key=lambda x:x[0]); bars[m]=np.asarray(b,float)

# 1. raw forward return distributions under 3 exit conventions
def fwd(conv, Hm=15):
    out=[]; permint=[]
    for m,a in bars.items():
        ts,op,hi,lo,cl=a[:,0],a[:,1],a[:,2],a[:,3],a[:,4]
        n=len(ts); r=[]
        for i in range(n-1):
            j=i+1; e=op[j]
            if e<=0: continue
            dl=ts[j]+Hm*60
            k=int(np.searchsorted(ts,dl,'left'))
            if conv=='next_open':
                if k>=n: continue
                x=op[k]
            elif conv=='last_close':
                kk=int(np.searchsorted(ts,dl,'right'))-1
                x=cl[max(kk,j)]
            elif conv=='next_open_grace30':
                if k>=n or ts[k]>dl+1800: continue
                x=op[k]
            r.append(x/e-1)
        if r: permint.append(np.mean(r)); out+=r
    out=np.array(out); pm=np.array(permint)
    return out,pm

for conv in ('next_open','last_close','next_open_grace30'):
    o,pm=fwd(conv)
    p("%-20s trades n=%d  trade-mean %+9.4f  trade-med %+8.4f | mint-mean %+9.4f mint-med %+8.4f  k=%d"%(
        conv,len(o),o.mean(),np.median(o),pm.mean(),np.median(pm),len(pm)))
    p("     quantiles", np.round(np.quantile(o,[0.001,0.01,0.05,0.25,0.5,0.75,0.95,0.99,0.999]),4), "max",round(o.max(),2))
    p("     mint-mean top5", np.round(np.sort(pm)[-5:],3))

# 2. where do the monsters come from
o,pm=fwd('last_close')
worst=[]
for m,a in bars.items():
    cl=a[:,4]; op=a[:,1]
    rr=cl[1:]/np.maximum(cl[:-1],1e-300)-1
    if len(rr): worst.append((rr.max(), m, len(cl), cl.min(), cl.max()))
worst.sort(reverse=True)
p("\ntop single-bar close-to-close jumps:")
for x in worst[:12]: p("   ", round(x[0],1), x[1], "nbars",x[2], "pxmin %.3g pxmax %.3g"%(x[3],x[4]))

# 3. per-mint mean of 15m last_close returns, winsorized effect
o,pm=fwd('last_close')
for cap in (None,3.0,1.0,0.5):
    tot=[]
    for m,a in bars.items():
        ts,op,cl=a[:,0],a[:,1],a[:,4]
        n=len(ts); r=[]
        for i in range(n-1):
            j=i+1; e=op[j]
            if e<=0: continue
            dl=ts[j]+900; kk=int(np.searchsorted(ts,dl,'right'))-1
            v=cl[max(kk,j)]/e-1
            if cap is not None: v=min(v,cap)
            r.append(v)
        if r: tot.append(np.mean(r))
    tot=np.array(tot)
    p("cap=%s  mint-mean %+8.4f  mint-med %+8.4f"%(cap,tot.mean(),np.median(tot)))
O.close()
