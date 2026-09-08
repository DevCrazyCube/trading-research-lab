"""Evaluation engine. Enforces harness contract B (non-overlap), C (mint-equal),
D (dropout charge), E (toll), F (simple returns)."""
import numpy as np, pickle, hashlib, math

OUT='/home/anont/meme/_c3'
_P=None
def load():
    global _P
    if _P is None:
        d=pickle.load(open(OUT+'/panel.pkl','rb'))
        d['EXTS']=np.load(OUT+'/exts.npy'); d['ENTTS']=np.load(OUT+'/entts.npy')
        mints=d['mints']
        d['h']=np.array([int(hashlib.md5(m.encode()).hexdigest(),16)%3 for m in mints],dtype=np.int8)
        assert (d['h']!=0).all(), "holdout leaked"
        d['nm']=len(mints)
        # per-bar mint h
        d['bar_h']=d['h'][d['mint_id']]
        _P=d
    return _P

def net_array(ci, drop=0.30, toll=0.0114, cap=3.0):
    """cap: per-position gross return cap. The uncapped mint-equal mean on this
    universe is dominated by a single +19,700% mint (see diag.out); an
    unbounded statistic cannot be measured with k~200 clusters. cap=None = raw."""
    P=load()
    g=P['GROSS'][ci].astype(np.float64); st=P['STATE'][ci]; sz=P['SIZE'][ci].astype(np.float64)
    if cap is not None: g=np.minimum(g,cap)
    net=np.full(len(g),np.nan)
    ok=st==1
    net[ok]=g[ok]-sz[ok]*toll
    dr=st==-1
    net[dr]=-drop*sz[dr]
    return net

def base_sel(mask, hsel):
    """precompute the candidate index set once so a cell can be scored against
    many exit structures without re-scanning the whole panel each time."""
    P=load()
    m=mask if hsel is None else (mask & (P['bar_h']==hsel))
    return np.flatnonzero(m)

def evaluate(mask, ci, net=None, drop=0.30, toll=0.0114, hsel=None, sel=None):
    """mask: bool over bars (signal bars). ci: combo index.
    Returns dict with mint-equal mean/median, n positions, k mints, resolution rate."""
    P=load()
    if net is None: net=net_array(ci,drop,toll)
    st=P['STATE'][ci]
    if sel is None:
        m=mask & (st!=0)
        if hsel is not None: m = m & (P['bar_h']==hsel)
        sel=np.flatnonzero(m)
    else:
        sel=sel[st[sel]!=0]
    if len(sel)==0: return None
    ent=P['ENTTS']; ex=P['EXTS'][ci]; mid=P['mint_id']
    nm=P['nm']
    s=np.zeros(nm); cnt=np.zeros(nm); res=np.zeros(nm); rc=np.zeros(nm)
    cur=-1; free=-1e18
    for k in sel:
        mm=mid[k]
        if mm!=cur: cur=mm; free=-1e18
        e=ent[k]
        if e<free: continue
        free=ex[k]
        s[mm]+=net[k]; cnt[mm]+=1.0
        if st[k]==1: res[mm]+=1.0
    live=cnt>0
    if live.sum()==0: return None
    pm=s[live]/cnt[live]
    return dict(mean=float(pm.mean()), median=float(np.median(pm)),
                n=int(cnt.sum()), k=int(live.sum()),
                res=float(res[live].sum()/cnt[live].sum()),
                permint=pm, mintidx=np.flatnonzero(live), sd=float(pm.std(ddof=1)) if live.sum()>1 else float('nan'))

def welch(a,b):
    na,nb=len(a),len(b)
    if na<3 or nb<3: return float('nan'),float('nan')
    va,vb=a.var(ddof=1),b.var(ddof=1)
    se=math.sqrt(va/na+vb/nb)
    if se<=0: return float('nan'),float('nan')
    t=(a.mean()-b.mean())/se
    df=(va/na+vb/nb)**2/max(1e-300,(va/na)**2/(na-1)+(vb/nb)**2/(nb-1))
    # normal approx tail (df is large enough here); one-sided
    from math import erfc,sqrt
    pz=0.5*erfc(t/sqrt(2))
    return t,pz

def bh(pvals, q=0.10):
    idx=np.argsort(pvals); m=len(pvals); keep=np.zeros(m,bool); thr=0.0
    for r,i in enumerate(idx,1):
        if pvals[i]<= q*r/m: thr=q*r/m; kmax=r
    else:
        pass
    kmax=0
    for r,i in enumerate(idx,1):
        if pvals[i]<= q*r/m: kmax=r
    for r,i in enumerate(idx,1):
        if r<=kmax: keep[i]=True
    return keep
