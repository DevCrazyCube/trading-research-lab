import pickle
import numpy as np
OUT='/home/anont/meme/_r0'
D=pickle.load(open(OUT+'/cache.pkl','rb')); mints=D['mints']
o=open(OUT+'/diag3.log','w')
def L(*a): o.write(' '.join(str(x) for x in a)+'\n')

for emin in (0,1):
    rets=[]
    for m in mints:
        ts=m['ts']; op=m['o']; n=len(ts)
        tgt=np.searchsorted(ts,ts+900,'left')
        e=np.nonzero((tgt<n)&(np.arange(n)>=emin))[0]
        if len(e)==0: continue
        rets.append(op[tgt[e]]/op[e]-1.0)
    R=np.concatenate(rets)
    L('emin=%d n=%d mean %+.4f median %+.4f  p1 %+.4f p99 %+.4f max %+.1f'%(
        emin,len(R),R.mean(),np.median(R),np.percentile(R,1),np.percentile(R,99),R.max()))

# per-mint mean of 15m returns (e>=1), no-overlap tiled
pm=[]
for m in mints:
    ts=m['ts']; op=m['o']; n=len(ts)
    tgt=np.searchsorted(ts,ts+900,'left')
    cur=0; tr=[]
    for e in range(1,n):
        if e<cur: continue
        te=tgt[e]
        if te>=n: tr.append(-0.30); break
        tr.append((1+op[te]/op[e]-1)*(1-0.0114)-1); cur=te+1
    if tr: pm.append((float(np.mean(tr)),len(tr),m['mint']))
v=np.array([x[0] for x in pm])
L('per-mint tiled 15m: k=%d mean %+.4f median %+.4f'%(len(v),v.mean(),np.median(v)))
for q in (1,5,10,25,50,75,90,95,99): L('   p%-3d %+.4f'%(q,np.percentile(v,q)))
pm.sort()
L('worst mints',[('%.3f'%a,b,c[:8]) for a,b,c in pm[:6]])
L('best mints',[('%.3f'%a,b,c[:8]) for a,b,c in pm[-6:]])
L('sum of top-3 mint contributions to mean: %.4f of %.4f'%(sum(x[0] for x in pm[-3:])/len(pm),v.mean()))

# gap: open_e vs close_{e-1}
g=[]
for m in mints:
    op=m['o']; cl=m['c']
    r=op[1:]/np.maximum(cl[:-1],1e-30)
    g.append(r)
G=np.concatenate(g)
L('open_e/close_{e-1} pctiles',[float(np.percentile(G,q)) for q in (0.1,1,5,50,95,99,99.9)])
L('frac gap>3x',float((G>3).mean()),'frac gap<1/3',float((G<1/3.).mean()))
o.close()
