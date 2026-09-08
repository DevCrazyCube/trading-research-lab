import numpy as np, pickle
SP='/home/anont/meme/.fc3'
_d=np.load(SP+'/ev.npz',allow_pickle=True)
F=_d['F']; G=_d['G'].astype(np.float64); X=_d['X']; R=_d['R']
HS=[5,15,30,60,120,240]; TPS=[None,0.15,0.40,1.00]; SLS=[None,-0.25,-0.50]
EX=[(h,tp,sl) for h in HS for tp in TPS for sl in SLS]
AGE,BIDX,DD,LVL,RELV,VOLI,GAP,RET1,PRI,PRIG,V0,ETS,HH,MI,STS,EGAP=range(16)
mi=F[:,MI].astype(int); hh=F[:,HH].astype(int); ets=F[:,ETS].astype(np.int64)
NM=mi.max()+1
# contiguous per-mint slices
starts=np.zeros(NM,dtype=int); ends=np.zeros(NM,dtype=int)
order=np.argsort(mi,kind='stable')
assert (np.diff(mi)>=0).all(), 'rows not grouped by mint'
for m in range(NM):
    w=np.nonzero(mi==m)[0]
    if len(w): starts[m]=w[0]; ends[m]=w[-1]+1
MTRAIN=np.array([ (hh[starts[m]]==1) if ends[m]>starts[m] else False for m in range(NM)])
MVAL  =np.array([ (hh[starts[m]]==2) if ends[m]>starts[m] else False for m in range(NM)])

def evaluate(mask,k,mode='all',charge=-0.30,toll=0.0114,split='train',ret_trades=False):
    """mint-equal weighted evaluation with non-overlap. returns dict."""
    sel_m = MTRAIN if split=='train' else (MVAL if split=='validate' else (MTRAIN|MVAL))
    Gk=G[:,k]; Xk=X[:,k]; Rk=R[:,k]
    permint=[]; alltr=[]; nres=0; ntot=0
    for m in range(NM):
        if not sel_m[m]: continue
        s,e=starts[m],ends[m]
        if e<=s: continue
        idx=np.nonzero(mask[s:e])[0]
        if len(idx)==0: continue
        idx=idx+s
        free=-1; tr=[]
        for r in idx:
            if ets[r] < free: continue
            if Rk[r]:
                net=(1.0+Gk[r])*(1.0-toll)-1.0; nres+=1
            else:
                net=(1.0+charge)*(1.0-toll)-1.0
            ntot+=1
            tr.append(net); free=Xk[r]
            if mode=='first': break
        if tr:
            permint.append(float(np.mean(tr))); alltr.extend(tr)
    if not permint: return None
    pm=np.array(permint); at=np.array(alltr)
    out=dict(mean=float(pm.mean()), median_trade=float(np.median(at)),
             median_mint=float(np.median(pm)), n=int(len(at)), k=int(len(pm)),
             res=float(nres/max(ntot,1)), pm=pm if ret_trades else None,
             trades=at if ret_trades else None)
    return out

def boot_lo(pm,B=1000,seed=0,q=0.05):
    rng=np.random.default_rng(seed); n=len(pm)
    idx=rng.integers(0,n,size=(B,n))
    means=pm[idx].mean(axis=1)
    return float(np.quantile(means,q))
