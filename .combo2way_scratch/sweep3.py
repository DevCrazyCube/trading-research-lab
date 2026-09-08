"""v3: wider grid (3 binning schemes incl. a fine-middle one), both split directions,
6 permuted-feature NULL replicates for an empirical multiplicity rate."""
import numpy as np, json, os, itertools, time
OUT='/home/anont/meme/.combo2way_scratch'
d=np.load(OUT+'/matrix2.npz',allow_pickle=True)
F=d['F']; MINT=d['mint'].astype(np.int64); HV=d['hv']; POS=d['pos'].astype(np.int64)
GROSS=d['gross']; EXIT=d['exitpos'].astype(np.int64); CLEAN=d['clean']
FEATS=[str(x) for x in d['feats']]; NF=len(FEATS); NM=int(MINT.max())+1
CAP=3.0; RES=np.isfinite(GROSS)
MINT_l=MINT.tolist(); POS_l=POS.tolist(); EXIT_l=EXIT.tolist()
def netvec(toll,drop,cap):
    g=np.where(RES,GROSS,0.0)
    if cap is not None: g=np.minimum(g,cap)
    return np.where(RES,(1.0+g)*(1.0-toll)-1.0,drop)
NET=netvec(0.0114,-0.30,CAP)
VAR={'cap_t114_d30':NET,'cap_t114_d50':netvec(0.0114,-0.5,CAP),'cap_t114_d100':netvec(0.0114,-1.0,CAP),
     'cap_t250_d30':netvec(0.025,-0.3,CAP),'raw_t114_d30':netvec(0.0114,-0.3,None),
     'raw_t250_d30':netvec(0.025,-0.3,None)}
IDX=np.where(CLEAN==1)[0]
A=IDX[HV[IDX]==1]; Bv=IDX[HV[IDX]==2]
def take(rows):
    out=[];lm=-1;le=-1
    for r in rows:
        m=MINT_l[r]
        if m!=lm: lm=m; le=-1
        if le>=0 and POS_l[r]<=le: continue
        out.append(r); x=EXIT_l[r]; le=x if x>=0 else 1<<30
    return out
def stat(t,net=NET):
    if not t: return None
    t=np.asarray(t)
    s=np.bincount(MINT[t],weights=net[t],minlength=NM); c=np.bincount(MINT[t],minlength=NM)
    sel=c>0; pm=s[sel]/c[sel]
    return dict(mean=float(pm.mean()),median=float(np.median(pm)),n=int(len(t)),
                clusters=int(sel.sum()),res=float(RES[t].mean()),pm=pm)
rng=np.random.default_rng(7)
def boot(pm,reps=2000):
    b=np.array([pm[rng.integers(0,len(pm),len(pm))].mean() for _ in range(reps)])
    return float(np.percentile(b,2.5)),float(np.percentile(b,97.5))
def control(split,k,reps=200):
    ms=[]
    for _ in range(reps):
        s=np.sort(rng.choice(split,size=min(k,len(split)),replace=False))
        st=stat(take(s.tolist()))
        if st: ms.append(st['mean'])
    ms=np.array(ms)
    return float(ms.mean()),float(np.percentile(ms,97.5))
SCHEMES={'Q5':[0,20,40,60,80,100],'R8':[0,20,30,40,50,60,70,80,100],
         'M10':[0,10,25,35,45,50,55,65,75,90,100]}
def make_bins(pcts,fit_rows):
    B=np.full((len(MINT),NF),-1,dtype=np.int8)
    for f in range(NF):
        col=F[:,f]; tr=col[fit_rows]; tr=tr[np.isfinite(tr)]
        if len(tr)<400: continue
        e=np.unique(np.percentile(tr,pcts))
        if len(e)<3: continue
        e[0]=-np.inf; e[-1]=np.inf
        idx=np.clip(np.searchsorted(e,col,side='right')-1,0,len(e)-2)
        idx[~np.isfinite(col)]=-1
        B[:,f]=idx.astype(np.int8)
    return B
MIN_N=40; MIN_CL=12; MIN_CL_V=15
def sweep(BS,TR,VA):
    cands=[]; swept=0
    for sn,B in BS.items():
        usable=[f for f in range(NF) if B[:,f].max()>=1]
        for f in usable:
            for b in range(int(B[:,f].max())+1):
                swept+=1
                rw=TR[B[TR,f]==b]
                if len(rw)<MIN_N: continue
                st=stat(take(np.sort(rw).tolist()))
                if st and st['mean']>0 and st['n']>=MIN_N and st['clusters']>=MIN_CL:
                    cands.append((sn,'1w',f,b,-1,-1,st))
        for fa,fb in itertools.combinations(usable,2):
            ca=B[TR,fa]; cb=B[TR,fb]
            na=int(B[:,fa].max())+1; nb=int(B[:,fb].max())+1
            for ba in range(na):
                ma=ca==ba
                if ma.sum()<MIN_N: swept+=nb; continue
                for bb in range(nb):
                    swept+=1
                    sel=ma&(cb==bb)
                    if sel.sum()<MIN_N: continue
                    st=stat(take(np.sort(TR[sel]).tolist()))
                    if st and st['mean']>0 and st['n']>=MIN_N and st['clusters']>=MIN_CL:
                        cands.append((sn,'2w',fa,ba,fb,bb,st))
    surv=[]
    for c in cands:
        sn,kind,fa,ba,fb,bb,tst=c
        B=BS[sn]
        sel=(B[VA,fa]==ba)
        if kind=='2w': sel&=(B[VA,fb]==bb)
        rw=VA[sel]
        if len(rw)<MIN_N: continue
        tk=take(np.sort(rw).tolist()); st=stat(tk)
        if not st or st['mean']<=0 or st['n']<MIN_N or st['clusters']<MIN_CL_V: continue
        lo,hi=boot(st['pm'])
        if lo<=0: continue
        surv.append((c,st,lo,hi,tk))
    return swept,len(cands),surv
def nm(c):
    sn,kind,fa,ba,fb,bb=c[:6]
    return '%s[%s=%d]'%(sn,FEATS[fa],ba) if kind=='1w' else '%s[%s=%d & %s=%d]'%(sn,FEATS[fa],ba,FEATS[fb],bb)

report={}
for tag,TR,VA in (('fwd(train h1 -> val h2)',A,Bv),('rev(train h2 -> val h1)',Bv,A)):
    BS={s:make_bins(p,TR) for s,p in SCHEMES.items()}
    t0=time.time(); sw,nc,sv=sweep(BS,TR,VA)
    st_all=stat(take(np.sort(VA).tolist()))
    print('\n===== %s ====='%tag)
    print('all-bars on VAL: mean=%+.4f med=%+.4f n=%d k=%d'%(st_all['mean'],st_all['median'],st_all['n'],st_all['clusters']))
    print('swept=%d train-positive=%d validate+CI survivors=%d (%.0fs)'%(sw,nc,len(sv),time.time()-t0))
    rows=[]
    sv.sort(key=lambda z:-z[1]['mean'])
    for c,st,lo,hi,tk in sv:
        rcm,rchi=control(VA,st['n'])
        r=dict(name=nm(c),train_mean=c[6]['mean'],train_med=c[6]['median'],train_n=c[6]['n'],train_k=c[6]['clusters'],
               val_mean=st['mean'],val_med=st['median'],val_n=st['n'],val_k=st['clusters'],val_res=st['res'],
               ci_lo=lo,ci_hi=hi,rc=rcm,rc_hi=rchi,edge=st['mean']-rcm,beat_rc_hi=bool(st['mean']>rchi))
        for k,v in VAR.items():
            s2=stat(tk,v); r[k]=s2['mean'] if s2 else None
        rows.append(r)
        print(' %-44s trM=%+.4f(n=%d,k=%d) vaM=%+.4f vaMed=%+.4f n=%d k=%d res=%.2f CI=[%+.4f,%+.4f] rc=%+.4f(hi%+.4f) edge=%+.4f beat=%s d50=%+.4f d100=%+.4f t250=%+.4f raw=%+.4f'%(
            r['name'],r['train_mean'],r['train_n'],r['train_k'],r['val_mean'],r['val_med'],r['val_n'],r['val_k'],
            r['val_res'],lo,hi,rcm,rchi,r['edge'],r['beat_rc_hi'],r['cap_t114_d50'],r['cap_t114_d100'],
            r['cap_t250_d30'],r['raw_t114_d30']))
    report[tag]=dict(swept=sw,train_pos=nc,survivors=rows)

# ---- NULL replicates on the forward split ----
BS0={s:make_bins(p,A) for s,p in SCHEMES.items()}
nullres=[]
for rep in range(6):
    perm=rng.permutation(len(MINT))
    NB={s:B[perm] for s,B in BS0.items()}
    sw,nc,sv=sweep(NB,A,Bv)
    nullres.append((nc,len(sv),[nm(c) for c,_,_,_,_ in sv]))
    print('NULL rep%d train-positive=%d survivors=%d %s'%(rep,nc,len(sv),[nm(c) for c,_,_,_,_ in sv]))
ns=[x[1] for x in nullres]
print('NULL survivors per replicate: %s  mean=%.2f'%(ns,sum(ns)/len(ns)))
report['nulls']=nullres
json.dump(report,open(OUT+'/sweep3_results.json','w'),indent=1,default=float)
print('WROTE sweep3_results.json')
