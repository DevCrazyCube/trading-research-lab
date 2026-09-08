"""v2 exhaustive 2-way cell sweep with a causal feed guard, fill-capped returns,
cluster-bootstrap CIs, matched random controls and a permuted-feature NULL for multiplicity.
Train = h==1 mints, Validate = h==2. h==0 never loaded."""
import numpy as np, json, os, itertools, sys, time

OUT='/home/anont/meme/.combo2way_scratch'
d=np.load(OUT+'/matrix2.npz',allow_pickle=True)
F=d['F']; MINT=d['mint'].astype(np.int64); HV=d['hv']; POS=d['pos'].astype(np.int64)
GROSS=d['gross']; EXIT=d['exitpos'].astype(np.int64); CLEAN=d['clean']
FEATS=[str(x) for x in d['feats']]; NF=len(FEATS)
NM=int(MINT.max())+1
CAP=3.0
keep=(CLEAN==1)
print('rows',len(MINT),'feed-clean',int(keep.sum()))
IDX=np.where(keep)[0]

MINT_l=MINT.tolist(); POS_l=POS.tolist(); EXIT_l=EXIT.tolist()
RESOLVED=np.isfinite(GROSS)

def netvec(toll,drop,cap):
    g=np.where(RESOLVED,GROSS,0.0)
    if cap is not None: g=np.minimum(g,cap)
    v=(1.0+g)*(1.0-toll)-1.0
    return np.where(RESOLVED,v,drop)

NET=netvec(0.0114,-0.30,CAP)          # primary: capped, toll 1.14%, dropout -30%
VARIANTS={
 'cap_t114_d30':netvec(0.0114,-0.30,CAP), 'cap_t114_d50':netvec(0.0114,-0.50,CAP),
 'cap_t114_d100':netvec(0.0114,-1.00,CAP),'cap_t250_d30':netvec(0.025,-0.30,CAP),
 'raw_t114_d30':netvec(0.0114,-0.30,None),'raw_t250_d30':netvec(0.025,-0.30,None),
}

def take(rows):
    """no-overlap, one position per mint at a time; dropout blocks the rest of the mint."""
    out=[]; lm=-1; le=-1
    for r in rows:
        m=MINT_l[r]
        if m!=lm: lm=m; le=-1
        if le>=0 and POS_l[r]<=le: continue
        out.append(r)
        x=EXIT_l[r]
        le=x if x>=0 else 1<<30
    return out

def stat(taken,net=NET):
    if not taken: return None
    t=np.asarray(taken)
    s=np.bincount(MINT[t],weights=net[t],minlength=NM)
    c=np.bincount(MINT[t],minlength=NM)
    sel=c>0; pm=s[sel]/c[sel]
    return dict(mean=float(pm.mean()),median=float(np.median(pm)),n=int(len(t)),
                clusters=int(sel.sum()),res=float(RESOLVED[t].mean()),pm=pm)

rng=np.random.default_rng(20260904)
def boot(pm,reps=2000):
    b=np.array([pm[rng.integers(0,len(pm),len(pm))].mean() for _ in range(reps)])
    return float(np.percentile(b,2.5)),float(np.percentile(b,97.5))

def control(split,k,reps=150):
    ms=[]
    for _ in range(reps):
        sel=np.sort(rng.choice(split,size=min(k,len(split)),replace=False))
        st=stat(take(sel.tolist()))
        if st: ms.append(st['mean'])
    ms=np.array(sorted(ms))
    return dict(mean=float(ms.mean()),lo=float(np.percentile(ms,2.5)),hi=float(np.percentile(ms,97.5)))

TR=IDX[HV[IDX]==1]; VA=IDX[HV[IDX]==2]
print('train rows',len(TR),'val rows',len(VA))
for nm_,rows in (('train',TR),('val',VA)):
    st=stat(take(rows.tolist()))
    st2=stat(take(rows.tolist()),VARIANTS['raw_t114_d30'])
    print('ALLBARS %-5s capped mean=%+.4f med=%+.4f n=%d k=%d res=%.3f | raw mean=%+.4f'%(
        nm_,st['mean'],st['median'],st['n'],st['clusters'],st['res'],st2['mean']))

SCHEMES={'Q5':[0,20,40,60,80,100],'R8':[0,20,30,40,50,60,70,80,100]}
def make_bins(pcts):
    nbp=len(pcts)-1
    B=np.full((len(MINT),NF),-1,dtype=np.int8); E={}
    for f in range(NF):
        col=F[:,f]; tr=col[TR]; tr=tr[np.isfinite(tr)]
        if len(tr)<400: continue
        e=np.unique(np.percentile(tr,pcts))
        if len(e)<3: continue
        e[0]=-np.inf; e[-1]=np.inf
        idx=np.clip(np.searchsorted(e,col,side='right')-1,0,len(e)-2)
        idx[~np.isfinite(col)]=-1
        B[:,f]=idx.astype(np.int8); E[f]=[float(x) for x in e]
    return B,E
BINS={};EDGES={}
for s,p in SCHEMES.items():
    BINS[s],EDGES[s]=make_bins(p)

MIN_N=40; MIN_CL=12; MIN_CL_V=15

def run_sweep(BINSET,TRr,VAr,tag,collect=True):
    res=[]; swept=0
    for sname,B in BINSET.items():
        usable=[f for f in range(NF) if B[:,f].max()>=1]
        for f in usable:
            for b in range(int(B[:,f].max())+1):
                swept+=1
                rows=TRr[B[TRr,f]==b]
                if len(rows)<MIN_N: continue
                st=stat(take(np.sort(rows).tolist()))
                if st and st['mean']>0 and st['n']>=MIN_N and st['clusters']>=MIN_CL:
                    res.append((sname,'1w',f,b,-1,-1,st['mean'],st['n'],st['clusters'],st['median']))
        for fa,fb in itertools.combinations(usable,2):
            ca=B[TRr,fa]; cb=B[TRr,fb]
            na=int(B[:,fa].max())+1; nb=int(B[:,fb].max())+1
            for ba in range(na):
                ma=ca==ba
                if ma.sum()<MIN_N:
                    swept+=nb; continue
                for bb in range(nb):
                    swept+=1
                    sel=ma&(cb==bb)
                    if sel.sum()<MIN_N: continue
                    st=stat(take(np.sort(TRr[sel]).tolist()))
                    if st and st['mean']>0 and st['n']>=MIN_N and st['clusters']>=MIN_CL:
                        res.append((sname,'2w',fa,ba,fb,bb,st['mean'],st['n'],st['clusters'],st['median']))
    surv=[]
    for r in res:
        sname,kind,fa,ba,fb,bb=r[:6]
        B=BINSET[sname]
        sel=(B[VAr,fa]==ba)
        if kind=='2w': sel&=(B[VAr,fb]==bb)
        rows=VAr[sel]
        if len(rows)<MIN_N: continue
        tk=take(np.sort(rows).tolist())
        st=stat(tk)
        if not st or st['mean']<=0 or st['n']<MIN_N or st['clusters']<MIN_CL_V: continue
        lo,hi=boot(st['pm'])
        if lo<=0: continue
        surv.append((r,st,lo,hi,tk))
    return swept,len(res),surv

t0=time.time()
swept,ntp,surv=run_sweep(BINS,TR,VA,'main')
print('cells swept on train: %d  train-positive: %d  validate+CI survivors: %d  (%.0fs)'%(
    swept,ntp,len(surv),time.time()-t0))

def nm(r):
    sname,kind,fa,ba,fb,bb=r[:6]
    if kind=='1w': return '%s[%s=%d]'%(sname,FEATS[fa],ba)
    return '%s[%s=%d & %s=%d]'%(sname,FEATS[fa],ba,FEATS[fb],bb)

surv.sort(key=lambda z:-z[1]['mean'])
final=[]
for r,st,lo,hi,tk in surv:
    rc=control(VA,st['n'])
    row=dict(name=nm(r),scheme=r[0],kind=r[1],fa=FEATS[r[2]],ba=r[3],
             fb=(FEATS[r[4]] if r[4]>=0 else None),bb=r[5],
             train_mean=r[6],train_n=r[7],train_k=r[8],train_med=r[9],
             val_mean=st['mean'],val_med=st['median'],val_n=st['n'],val_k=st['clusters'],
             val_res=st['res'],ci_lo=lo,ci_hi=hi,rc_mean=rc['mean'],rc_hi=rc['hi'],
             edge=st['mean']-rc['mean'],beats_rc_hi=bool(st['mean']>rc['hi']))
    for vn,vv in VARIANTS.items():
        s2=stat(tk,vv); row[vn]=s2['mean'] if s2 else None
    final.append(row)
    print('%-46s trM=%+.4f(n=%d,k=%d) vaM=%+.4f vaMed=%+.4f n=%d k=%d res=%.2f CI=[%+.4f,%+.4f] rc=%+.4f(hi %+.4f) edge=%+.4f beat=%s | d50=%+.4f d100=%+.4f t250=%+.4f raw=%+.4f'%(
        row['name'],row['train_mean'],row['train_n'],row['train_k'],row['val_mean'],row['val_med'],
        row['val_n'],row['val_k'],row['val_res'],lo,hi,rc['mean'],rc['hi'],row['edge'],row['beats_rc_hi'],
        row['cap_t114_d50'],row['cap_t114_d100'],row['cap_t250_d30'],row['raw_t114_d30']))

# ---- NULL: permute feature rows (destroys feature->outcome link, keeps marginals+correlations)
nulls=[]
for rep in range(2):
    perm=rng.permutation(len(MINT))
    NB={s:B[perm] for s,B in BINS.items()}
    sw,ntpn,sn=run_sweep(NB,TR,VA,'null%d'%rep)
    nulls.append((ntpn,len(sn)))
    print('NULL rep%d: train-positive %d  validate+CI survivors %d'%(rep,ntpn,len(sn)))

json.dump(dict(swept=swept,train_pos=ntp,survivors=final,nulls=nulls,
               edges={s:{FEATS[f]:e for f,e in E.items()} for s,E in EDGES.items()}),
          open(OUT+'/sweep2_results.json','w'),indent=1,default=float)
print('WROTE sweep2_results.json')
