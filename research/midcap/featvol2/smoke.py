import sys,time,numpy as np
sys.path.insert(0,'/home/anont/meme/research/midcap/featvol2')
from harness import *
from feats import build_features
t0=time.time()
mints,data,nres=load()
print("loaded mints(h in 1,2):",len(mints),"reserved skipped:",nres)
book=Book(mints,data)
print("bars:",book.N,"mints:",book.nm, "train(h=1):",int((book.hh==1).sum()),"val(h=2):",int((book.hh==2).sum()))
np.save('/tmp/x.npy',np.array([0]))
F=build_features(book)
print("features built %.1fs"%(time.time()-t0))
# random-bar benchmark at 15m
H=15
k=build_exit(book,H)
maxwin=int(np.percentile(np.where(k>=0,k-np.arange(book.N),0),99.9))+2
maxwin=max(maxwin,3)
print("maxwin",maxwin)
Rmax,Rmin,L=path_extremes(book,k,maxwin)
g=gross_returns(book,k,Rmax,Rmin,L,None,None)
valid_sig=np.zeros(book.N,bool)
for i in range(book.nm):
    s,e=book.starts[i],book.ends[i]
    valid_sig[s:e-1]=True
print("valid signal bars",valid_sig.sum())
res=(k[np.flatnonzero(valid_sig)+1]>=0).mean()
print("raw resolution rate at 15m: %.3f"%res)
for drop in (-0.30,-0.50,-1.00):
    net=netify(g,k,0.0114,drop)
    js=greedy(book,valid_sig,k)   # every bar a signal -> full no-overlap coverage
    a=agg(book,js,net)
    print("ALLBAR 15m drop%.2f n=%d k=%d mean=%.4f median=%.4f"%(drop,a['n'],a['clusters'],a['mean'],a['median']))
