import os, json, math, itertools, time
import numpy as np
S = "/home/anont/meme/research/scratch_combo2"
L = open(os.path.join(S, "final_log.txt"), "w")
def log(*a): L.write(" ".join(str(x) for x in a) + "\n"); L.flush()

d = np.load(os.path.join(S, "mat.npz"))
X=d["X"];MID=d["MID"];HH=d["HH"];SIGT=d["SIGT"];ENTT=d["ENTT"];ENTP=d["ENTP"]
EXTT=d["EXTT"];EXTP=d["EXTP"];RES=d["RES"];ALT=d["ALT"]
meta=json.load(open(os.path.join(S,"mints.json"))); FEATS=meta["feats"]; NF=len(FEATS)
o=np.lexsort((SIGT,MID))
X,MID,HH,SIGT,ENTT,ENTP,EXTT,EXTP,RES,ALT=[a[o] for a in (X,MID,HH,SIGT,ENTT,ENTP,EXTT,EXTP,RES,ALT)]
N=len(MID); CAP=3.0; TOLL=0.0114
def mknet(drop=-0.30,toll=TOLL,cap=CAP):
    g=np.minimum(EXTP/ENTP-1.0,cap); v=(1.0+g)*(1.0-toll)-1.0
    return np.where(RES==1,v,drop)
NET=mknet()
TR=(HH==1); VA=(HH==2); allr=np.arange(N); TRI=allr[TR]; VAI=allr[VA]
def take(idx):
    out=[];cur=-1;blk=-1e18
    for k in idx:
        m=MID[k]
        if m!=cur: cur=m; blk=-1e18
        if SIGT[k]<blk: continue
        blk=EXTT[k]; out.append(k)
    return np.asarray(out,dtype=np.int64)
def me(tk,net=NET):
    mids=MID[tk]; u,inv=np.unique(mids,return_inverse=True)
    pm=np.bincount(inv,weights=net[tk],minlength=len(u))/np.bincount(inv,minlength=len(u))
    return float(pm.mean()),float(np.median(pm)),pm,u

QB={};DB={};VB={}
QBIN=np.full((N,NF),-1,np.int8);DBIN=np.full((N,NF),-1,np.int8);VBIN=np.full((N,NF),-1,np.int8)
for k in range(NF):
    c0=X[TR,k];c0=c0[np.isfinite(c0)]
    if len(c0)<500: QB[k]=None;continue
    QB[k]=np.quantile(c0,[.2,.4,.6,.8]);DB[k]=np.quantile(c0,[.1,.9]);VB[k]=np.quantile(c0,[.05,.95])
    c=X[:,k];fin=np.isfinite(c)
    QBIN[fin,k]=np.searchsorted(QB[k],c[fin],side="right").astype(np.int8)
    DBIN[fin&(c<=DB[k][0]),k]=0;DBIN[fin&(c>=DB[k][1]),k]=1
    VBIN[fin&(c<=VB[k][0]),k]=0;VBIN[fin&(c>=VB[k][1]),k]=1
ARR={"Q":QBIN,"D":DBIN,"V":VBIN}
FI={f:i for i,f in enumerate(FEATS)}
log("thresholds: body Q2 = (%.4f, %.4f];  hilopos D1 >= %.4f" % (QB[FI['body']][1],QB[FI['body']][2],DB[FI['hilopos']][1]))
log("thresholds: rvol Q1 = (%.5f, %.5f];  retlife Q2 = (%.4f, %.4f]" %
    (QB[FI['rvol']][0],QB[FI['rvol']][1],QB[FI['retlife']][1],QB[FI['retlife']][2]))

CANDS=[("body Q2 & hilopos D1",[("body","Q",2),("hilopos","D",1)]),
       ("rvol Q1 & retlife Q2",[("rvol","Q",1),("retlife","Q",2)])]
def mask(rows,spec):
    m=np.ones(len(rows),bool)
    for f,k,q in spec: m &= (ARR[k][rows,FI[f]]==q)
    return m

for name,spec in CANDS:
    log("="*90); log("CANDIDATE:",name)
    for split,idxs in (("TRAIN",TRI),("VALID",VAI)):
        tk=take(idxs[mask(idxs,spec)])
        m,md,pm,u=me(tk)
        log("  %s mean %7.4f med %7.4f n %d clusters %d res %.3f" % (split,m,md,len(tk),len(u),float(RES[tk].mean())))
        # leave-one-mint-out
        loo=np.array([ (pm.sum()-pm[i])/(len(pm)-1) for i in range(len(pm))])
        worst=int(np.argmin(loo))
        log("    per-mint means sorted: %s" % [round(float(x),3) for x in np.sort(pm)])
        log("    leave-one-mint-out mean: min %7.4f max %7.4f  (drop worst-driver mint -> %7.4f)"
            % (float(loo.min()),float(loo.max()),float(loo[worst])))
        log("    frac of mints with positive mean: %.3f ; top-1 mint contributes %.1f%% of total"
            % (float((pm>0).mean()), 100.0*float(pm.max()/pm.sum()) if pm.sum()!=0 else float('nan')))
        # trim top and bottom mint
        if len(pm)>=6:
            s=np.sort(pm); log("    trimmed(10%%) mean %7.4f" % float(s[max(1,len(s)//10):len(s)-max(1,len(s)//10)].mean()))
    # time split on VALIDATE
    tk=take(VAI[mask(VAI,spec)])
    if len(tk)>20:
        med_t=np.median(SIGT[tk])
        for lab,sub in (("early",tk[SIGT[tk]<=med_t]),("late",tk[SIGT[tk]>med_t])):
            if len(sub)>5:
                m,md,pm,u=me(sub); log("  VALID %s-half mean %7.4f n %d cl %d" % (lab,m,len(sub),len(u)))
    # single-leg decomposition
    for f,k,q in spec:
        for split,idxs in (("TRAIN",TRI),("VALID",VAI)):
            tk=take(idxs[ARR[k][idxs,FI[f]]==q]); m,md,pm,u=me(tk)
            log("  leg-only %-14s %s mean %7.4f n %5d cl %4d" % ("%s %s%d"%(f,k,q),split,m,len(tk),len(u)))

# ---- permutation test: shuffle the feature labels within mint, keep the cell size ----
log("="*90); log("PERMUTATION TEST (validate): shuffle signal times within mint, same trade count per mint")
rng=np.random.default_rng(42)
elig={}
for k in VAI: elig.setdefault(MID[k],[]).append(k)
for m in elig: elig[m]=np.array(sorted(elig[m]))
for name,spec in CANDS:
    tk=take(VAI[mask(VAI,spec)]); obs,_,_,u=me(tk)
    mids,cnts=np.unique(MID[tk],return_counts=True)
    null=[]
    for r in range(2000):
        sel=[]
        for m,c in zip(mids,cnts):
            p=elig[m]; sel.append(rng.choice(p,size=min(c,len(p)),replace=False))
        sel=np.sort(np.concatenate(sel)); t2=take(sel)
        if len(t2)<5: continue
        null.append(me(t2)[0])
    null=np.array(null)
    p=float((null>=obs).mean())
    log("  %-24s obs %7.4f | null mean %7.4f sd %6.4f p95 %7.4f p99 %7.4f | one-sided p = %.4f"
        % (name,obs,float(null.mean()),float(null.std()),float(np.quantile(null,.95)),
           float(np.quantile(null,.99)),p))
    log("     -> with 8779 cells tested, expected cells this extreme by chance: %.0f" % (p*8779))
