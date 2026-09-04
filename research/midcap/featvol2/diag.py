import sys,gc
import numpy as np
sys.path.insert(0,'/home/anont/meme/research/midcap/featvol2')
from core import *
mints,data,nres=load()
book=Book(mints,data); N=book.N
BH=book.hh[book.MID]
print("mints=%d bars=%d"%(book.nm,N))
# bar-level integrity
gapoc=np.full(N,np.nan)
for i in range(book.nm):
    s,e=book.starts[i],book.ends[i]
    gapoc[s+1:e]=book.O[s+1:e]/book.C[s:e-1]-1.0
intra=book.C/book.O-1.0
print("intrabar C/O-1: median=%+.5f mean=%+.5f"%(np.median(intra),np.mean(intra)))
g=gapoc[np.isfinite(gapoc)]
print("open-gap O[t]/C[t-1]-1: median=%+.5f mean=%+.5f  (should be ~0 if bars are contiguous)"%(np.median(g),np.mean(g)))
# 15m forward open-to-open, ALL bars (overlapping) -- pure drift measurement, no greedy
for Hm in (5,15,60):
    k=build_exit(book,Hm)
    j=np.arange(N)
    ok=(k>=0)&book.valid_sig
    r=np.full(N,np.nan)
    r[ok]=book.O[k[ok]]/book.O[ok]-1.0
    mid=book.MID
    pm=[];pmed=[]
    for i in range(book.nm):
        s,e=book.starts[i],book.ends[i]
        v=r[s:e]; v=v[np.isfinite(v)]
        if v.size>=3: pm.append(v.mean()); pmed.append(np.median(v))
    pm=np.array(pm); pmed=np.array(pmed)
    print("H%-3d overlapping ALL-bar open->open GROSS: mint-mean-of-means=%+.4f  median-of-mint-means=%+.4f  median-of-mint-medians=%+.4f  trim5=%+.4f  fracpos=%.3f k=%d"%(
        Hm,pm.mean(),np.median(pm),np.median(pmed),np.mean(np.sort(pm)[int(.05*pm.size):pm.size-int(.05*pm.size)]),(pm>0).mean(),pm.size))
    # pooled by bar (violates C, but tells us about the raw tape)
    rr=r[np.isfinite(r)]
    print("      pooled-by-bar: mean=%+.4f median=%+.4f n=%d"%(rr.mean(),np.median(rr),rr.size))
    del k,r; gc.collect()
# life-cycle: buy first bar open, sell last bar open
lc=[]
for i in range(book.nm):
    s,e=book.starts[i],book.ends[i]
    lc.append(book.O[e-1]/book.O[s]-1.0)
lc=np.array(lc)
print("first-open -> last-open per mint: median=%+.4f mean=%+.4f fracpos=%.3f"%(np.median(lc),lc.mean(),(lc>0).mean()))
nb=np.array([book.ends[i]-book.starts[i] for i in range(book.nm)])
print("bars per mint: median=%d p10=%d p90=%d"%(np.median(nb),np.percentile(nb,10),np.percentile(nb,90)))
span=np.array([(book.TS[book.ends[i]-1]-book.TS[book.starts[i]])/60.0 for i in range(book.nm)])
print("observed span minutes: median=%.0f p10=%.0f p90=%.0f"%(np.median(span),np.percentile(span,10),np.percentile(span,90)))
