import json, numpy as np
W='/home/anont/meme/.regime1/'
LOG=open(W+'diag.txt','w')
def P(*a): print(*a,file=LOG); LOG.flush()
z=np.load(W+'feats.npz'); EX=np.load(W+'exits.npz'); EPX=EX['EPX']; EROW=EX['EROW']
EXITS=json.load(open(W+'exits.json')); meta=json.load(open(W+'meta.json'))
mint_slice={int(k):tuple(v) for k,v in meta['mint_slice'].items()}
names=meta['mint_names']
mid=z['mid']; ts=z['ts']; op=z['op']; last_of_mint=z['last_of_mint']; mint_h=z['mint_h']
N=len(ts); M=len(mint_h)
valid=~last_of_mint
E0=np.where(valid, op[np.minimum(np.arange(N)+1,N-1)], np.nan)
ei=[i for i,e in enumerate(EXITS) if e['name']=='T15'][0]
X=EPX[ei]; er=EROW[ei]
# non-overlap greedy, ANY entry
for hset,tag in ((1,'train'),(2,'val')):
    sel=np.flatnonzero(valid & np.isfinite(E0) & (mint_h[mid]==hset))
    per={}; drops={}
    cur=-1; block=-1; dead=False
    for r in sel:
        m=mid[r]
        if m!=cur: cur=m; block=-1; dead=False
        if dead or r<block: continue
        if not np.isfinite(X[r]):
            per.setdefault(m,[]).append(-0.30-0.0114); drops[m]=drops.get(m,0)+1; dead=True; continue
        per.setdefault(m,[]).append(X[r]/E0[r]-1-0.0114); block=er[r]
    mm=np.array([np.mean(v) for v in per.values()]); ks=list(per.keys())
    o=np.argsort(-mm)
    P(tag,'k',len(mm),'mean %.4f'%mm.mean(),'median %.4f'%np.median(mm))
    P(' top5 mints:', [(names[ks[i]][:8], round(float(mm[i]),3), len(per[ks[i]])) for i in o[:5]])
    P(' mean excl top1 %.4f  excl top3 %.4f'%(mm[o[1:]].mean(), mm[o[3:]].mean()))
    w=np.clip(mm,-1.0,1.0); P(' winsor[-1,1] mean %.4f'%w.mean())
    w2=np.clip(mm,-1.0,0.5); P(' winsor[-1,0.5] mean %.4f'%w2.mean())
    P(' quantiles', [round(float(np.quantile(mm,q)),4) for q in (0.05,0.25,0.5,0.75,0.9,0.95,0.99)])
    ntr=sum(len(v) for v in per.values())
    P(' trades',ntr,'mints with a dropout',len(drops))
    # per-trade resolution
    P(' bars per mint median', int(np.median([mint_slice[k][1]-mint_slice[k][0] for k in ks])))
# how many trades per mint
LOG.close()
