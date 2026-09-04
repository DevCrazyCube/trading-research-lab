import sys,gc
import numpy as np
sys.path.insert(0,'/home/anont/meme/research/midcap/featvol2')
from core import *
mints,data,nres=load()
book=Book(mints,data); N=book.N
eq=0;tot=0
for i in range(book.nm):
    s,e=book.starts[i],book.ends[i]
    d=np.abs(book.O[s+1:e]-book.C[s:e-1])/book.C[s:e-1]
    eq+=int((d<1e-12).sum()); tot+=d.size
print("O[t]==C[t-1] exactly: %d/%d = %.4f  -> contract-A 'next real bar open' == signal-bar CLOSE"%(eq,tot,eq/tot))
k=build_exit(book,15)
r=np.full(N,np.nan); ok=(k>=0)&book.valid_sig
r[ok]=book.O[k[ok]]/book.O[ok]-1.0
rr=r[np.isfinite(r)]
print("15m gross quantiles:", {q:round(float(np.quantile(rr,q)),4) for q in (0.001,0.01,0.05,0.25,0.5,0.75,0.95,0.99,0.999,0.9999)})
print("max=%.1f  #>10x=%d  #>100x=%d"%(rr.max(),(rr>9).sum(),(rr>99).sum()))
idx=np.argsort(r[np.isfinite(r)])[::-1]
fin=np.flatnonzero(np.isfinite(r))
top=fin[np.argsort(r[fin])[::-1][:12]]
for j in top:
    m=book.MID[j]
    print("  mint=%s ts=%d O_in=%.3e O_out=%.3e ret=%.1f  vol_in=%.2f vol_out=%.2f"%(
        book.mints[m][:8],int(book.TS[j]),book.O[j],book.O[k[j]],r[j],book.V[j],book.V[k[j]]))
# effect of capping the right tail on the mint-equal mean
for cap in (None,50.0,10.0,3.0):
    x=r.copy()
    if cap is not None: x=np.minimum(x,cap)
    pm=[]
    for i in range(book.nm):
        s,e=book.starts[i],book.ends[i]
        v=x[s:e]; v=v[np.isfinite(v)]
        if v.size>=3: pm.append(v.mean())
    pm=np.array(pm)
    print("cap=%s  mint-equal mean=%+.4f median=%+.4f"%(cap,pm.mean(),np.median(pm)))
# how far is the next real bar?  (fill-realism)
nxt=np.full(N,np.nan)
for i in range(book.nm):
    s,e=book.starts[i],book.ends[i]
    nxt[s:e-1]=np.diff(book.TS[s:e])
v=nxt[np.isfinite(nxt)]
print("seconds to NEXT real bar (the modelled entry): median=%.0f p75=%.0f p90=%.0f p99=%.0f frac<=60s=%.3f"%(
    np.median(v),np.percentile(v,75),np.percentile(v,90),np.percentile(v,99),(v<=60).mean()))
