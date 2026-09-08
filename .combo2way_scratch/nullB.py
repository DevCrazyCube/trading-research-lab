"""NULL-B: within each mint, circularly shift the OUTCOME vector by a random lag.
Preserves feature values, feature/mint clustering, cell sizes, per-mint return distribution and
outcome autocorrelation; destroys only the feature->outcome alignment. This is the honest null
for 'does this cell predict?' (the global feature permutation is anti-conservative because it
breaks the mint-level clustering that makes real cells fat-tailed)."""
import numpy as np, json, itertools, time
OUT='/home/anont/meme/.combo2way_scratch'
d=np.load(OUT+'/matrix2.npz',allow_pickle=True)
F=d['F']; MINT=d['mint'].astype(np.int64); HV=d['hv']; POS=d['pos'].astype(np.int64)
GROSS=d['gross']; EXIT=d['exitpos'].astype(np.int64); CLEAN=d['clean']
FEATS=[str(x) for x in d['feats']]; NF=len(FEATS); NM=int(MINT.max())+1
CAP=3.0
MINT_l=MINT.tolist(); POS_l=POS.tolist(); EXIT_l=EXIT.tolist()
IDX=np.where(CLEAN==1)[0]; TR=IDX[HV[IDX]==1]; VA=IDX[HV[IDX]==2]
def mknet(gross):
    res=np.isfinite(gross)
    g=np.where(res,np.minimum(gross,CAP),0.0)
    return np.where(res,(1+g)*(1-0.0114)-1,-0.30)
def take(rows):
    out=[];lm=-1;le=-1
    for r in rows:
        m=MINT_l[r]
        if m!=lm: lm=m; le=-1
        if le>=0 and POS_l[r]<=le: continue
        out.append(r); x=EXIT_l[r]; le=x if x>=0 else 1<<30
    return out
def stat(t,NET):
    if not t: return None
    t=np.asarray(t)
    s=np.bincount(MINT[t],weights=NET[t],minlength=NM); c=np.bincount(MINT[t],minlength=NM)
    sel=c>0; pm=s[sel]/c[sel]
    return dict(mean=float(pm.mean()),median=float(np.median(pm)),n=int(len(t)),clusters=int(sel.sum()),pm=pm)
rng=np.random.default_rng(99)
def boot(pm,reps=1200):
    b=np.array([pm[rng.integers(0,len(pm),len(pm))].mean() for _ in range(reps)])
    return float(np.percentile(b,2.5))
SCH={'Q5':[0,20,40,60,80,100],'R8':[0,20,30,40,50,60,70,80,100],'M10':[0,10,25,35,45,50,55,65,75,90,100]}
def bins(pcts,fit):
    B=np.full((len(MINT),NF),-1,dtype=np.int8)
    for f in range(NF):
        col=F[:,f]; tr=col[fit]; tr=tr[np.isfinite(tr)]
        if len(tr)<400: continue
        e=np.unique(np.percentile(tr,pcts))
        if len(e)<3: continue
        e[0]=-np.inf; e[-1]=np.inf
        B[:,f]=np.clip(np.searchsorted(e,col,side='right')-1,0,len(e)-2).astype(np.int8)
        B[~np.isfinite(col),f]=-1
    return B
BS={s:bins(p,TR) for s,p in SCH.items()}
# per-mint row blocks (rows are grouped by mint, ascending)
starts={}
for i,m in enumerate(MINT_l):
    if m not in starts: starts[m]=[i,i]
    else: starts[m][1]=i
BLOCKS=[(a,b+1) for m,(a,b) in starts.items()]
MIN_N=40; MIN_CL=12; MIN_CL_V=15
def sweep(NET):
    cands=[]
    for sn,B in BS.items():
        usable=[f for f in range(NF) if B[:,f].max()>=1]
        for f in usable:
            for b in range(int(B[:,f].max())+1):
                rw=TR[B[TR,f]==b]
                if len(rw)<MIN_N: continue
                st=stat(take(np.sort(rw).tolist()),NET)
                if st and st['mean']>0 and st['clusters']>=MIN_CL: cands.append((sn,'1w',f,b,-1,-1))
        for fa,fb in itertools.combinations(usable,2):
            ca=B[TR,fa]; cb=B[TR,fb]
            for ba in range(int(B[:,fa].max())+1):
                ma=ca==ba
                if ma.sum()<MIN_N: continue
                for bb in range(int(B[:,fb].max())+1):
                    sel=ma&(cb==bb)
                    if sel.sum()<MIN_N: continue
                    st=stat(take(np.sort(TR[sel]).tolist()),NET)
                    if st and st['mean']>0 and st['clusters']>=MIN_CL: cands.append((sn,'2w',fa,ba,fb,bb))
    surv=[]
    for sn,kind,fa,ba,fb,bb in cands:
        B=BS[sn]
        sel=(B[VA,fa]==ba)
        if kind=='2w': sel&=(B[VA,fb]==bb)
        rw=VA[sel]
        if len(rw)<MIN_N: continue
        st=stat(take(np.sort(rw).tolist()),NET)
        if not st or st['mean']<=0 or st['n']<MIN_N or st['clusters']<MIN_CL_V: continue
        if boot(st['pm'])<=0: continue
        nmv='%s[%s=%d%s]'%(sn,FEATS[fa],ba,(' & %s=%d'%(FEATS[fb],bb)) if kind=='2w' else '')
        surv.append(nmv)
    return len(cands),surv
t0=time.time()
nc,sv=sweep(mknet(GROSS))
print('REAL: train-positive=%d survivors=%d %s (%.0fs)'%(nc,len(sv),sv,time.time()-t0))
counts=[]
for rep in range(10):
    G2=GROSS.copy()
    for a,b in BLOCKS:
        n=b-a
        if n<4: continue
        k=int(rng.integers(1,n))
        G2[a:b]=np.roll(GROSS[a:b],k)
    nc2,sv2=sweep(mknet(G2))
    counts.append(len(sv2))
    print('NULL-B rep%d train-positive=%d survivors=%d %s'%(rep,nc2,len(sv2),sv2[:6]))
print('NULL-B survivors per replicate: %s mean=%.2f  P(>=%d)=%.3f'%(
    counts,sum(counts)/len(counts),len(sv),sum(1 for c in counts if c>=len(sv))/len(counts)))
json.dump(dict(real=sv,null_counts=counts),open(OUT+'/nullB.json','w'))
