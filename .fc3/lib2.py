import numpy as np, pickle
SP='/home/anont/meme/.fc3'
_d=np.load(SP+'/ev.npz',allow_pickle=True)
F=_d['F']; G=_d['G'].astype(np.float64); X=_d['X']; R=_d['R']
HS=[5,15,30,60,120,240]; TPS=[None,0.15,0.40,1.00]; SLS=[None,-0.25,-0.50]
EX=[(h,tp,sl) for h in HS for tp in TPS for sl in SLS]
AGE,BIDX,DD,LVL,RELV,VOLI,GAP,RET1,PRI,PRIG,V0,ETS,HH,MI,STS,EGAP=range(16)
mi=F[:,MI].astype(int); hh=F[:,HH].astype(int); ets=F[:,ETS].astype(np.int64)
NM=int(mi.max())+1
starts=np.searchsorted(mi,np.arange(NM),'left'); ends=np.searchsorted(mi,np.arange(NM),'right')
MSPLIT=np.zeros(NM,dtype=int)
for m in range(NM):
    if ends[m]>starts[m]: MSPLIT[m]=hh[starts[m]]
TRAIN=np.nonzero(MSPLIT==1)[0]; VAL=np.nonzero(MSPLIT==2)[0]
CAP=9.0   # cap gross at +900% (feed artifacts reach +10000x in 15 min)

def prep(mask,split):
    ms=TRAIN if split=='train' else (VAL if split=='validate' else np.concatenate([TRAIN,VAL]))
    out=[]
    idx_all=np.nonzero(mask)[0]
    if len(idx_all)==0: return out
    for m in ms:
        s,e=starts[m],ends[m]
        if e<=s: continue
        a=np.searchsorted(idx_all,s,'left'); b=np.searchsorted(idx_all,e,'left')
        if b>a: out.append(idx_all[a:b])
    return out

def run(pr,k,mode='all',charge=-0.30,toll=0.0114,cap=CAP):
    Gk=G[:,k]; Xk=X[:,k]; Rk=R[:,k]
    dropnet=(1.0+charge)*(1.0-toll)-1.0
    permint=[]; alltr=[]; nres=0; ntot=0
    for idx in pr:
        free=-1; tr=[]
        for r in idx:
            if ets[r]<free: continue
            if Rk[r]:
                g=Gk[r]
                if cap is not None and g>cap: g=cap
                net=(1.0+g)*(1.0-toll)-1.0; nres+=1
            else:
                net=dropnet
            ntot+=1; tr.append(net); free=Xk[r]
            if mode=='first': break
        if tr:
            permint.append(sum(tr)/len(tr)); alltr.extend(tr)
    if not permint: return None
    pm=np.array(permint); at=np.array(alltr)
    return dict(mean=float(pm.mean()),median_trade=float(np.median(at)),
                median_mint=float(np.median(pm)),n=int(len(at)),k=int(len(pm)),
                res=float(nres/max(ntot,1)),pm=pm)

def boot_lo(pm,B=2000,seed=0,q=0.05):
    if len(pm)<3: return -9.0
    rng=np.random.default_rng(seed); n=len(pm)
    return float(np.quantile(pm[rng.integers(0,n,size=(B,n))].mean(axis=1),q))
