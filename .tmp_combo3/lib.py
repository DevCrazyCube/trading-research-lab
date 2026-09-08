import pickle, math, itertools, time
import numpy as np

D='/home/anont/meme/.tmp_combo3/'
BIG=1<<30
TOLL=0.0114/2.0
TOLL_HI=0.025/2.0
CAP=3.0   # winsorise a single trade's net return at +300% (a $60 book cannot realise a 10,000x dust fill)

_S=None
def S():
    global _S
    if _S is None:
        with open(D+'panel.pkl','rb') as f: _S=pickle.load(f)
    return _S

def mints_of(k):
    st=S()
    return [m for m,P in st['panel'].items() if P['k']==k and len(st['ELIG'][m])>0]

def sim_mint(m,H,tp,sl,tr,pos,drop=-0.30,toll=TOLL):
    st=S(); P=st['panel'][m]; PA=st['PATH'][m]
    n=P['n']; ts=P['ts']; op=P['op']
    if H in PA['T']: te=PA['T'][H]
    else:
        te=np.searchsorted(ts,ts+H*60,side='left'); te=np.where(te>=n,-1,te); PA['T'][H]=te
    te_eff=np.where(te<0,BIG,te); ent=op
    a_sl=PA['fsl'][sl] if sl is not None else np.full(n,BIG,dtype=np.int64)
    a_tr=PA['ftr'][tr] if tr is not None else np.full(n,BIG,dtype=np.int64)
    a_tp=PA['ftp'][tp] if tp is not None else np.full(n,BIG,dtype=np.int64)
    s_=np.where(a_sl<te_eff,a_sl,BIG); r_=np.where(a_tr<te_eff,a_tr,BIG); t_=np.where(a_tp<te_eff,a_tp,BIG)
    mn=np.minimum(np.minimum(s_,r_),t_); ev=mn<BIG
    px_ev=np.where(s_==mn, ent*(1.0+(sl if sl is not None else 0.0)),
          np.where(r_==mn, PA['ptr'][tr] if tr is not None else np.zeros(n),
                   ent*(1.0+(tp if tp is not None else 0.0))))
    te_c=np.clip(te,0,n-1)
    exit_idx=np.where(ev,mn,te_eff); exit_px=np.where(ev,px_ev,op[te_c])
    resolved=ev|(te>=0)
    j3=PA['p3']; j3c=np.clip(j3,0,n-1); px3=op[j3c]
    j3ok=(j3>=0)&(j3<np.where(resolved,exit_idx,BIG))
    if pos=='flat':
        f1=np.ones(n); f2=np.zeros(n)
    else:
        f1=np.full(n,0.5)
        if pos=='split3': cond=j3ok
        elif pos=='dip3': cond=j3ok&(px3<=ent*0.97)
        elif pos=='str3': cond=j3ok&(px3>=ent*1.03)
        else: raise ValueError(pos)
        f2=np.where(cond,0.5,0.0)
    dep=f1+f2
    val_res=f1*(exit_px/ent)+f2*(exit_px/np.maximum(px3,1e-30))
    val=np.where(resolved,val_res,dep*(1.0+drop))
    net=val+(1.0-dep)-1.0-toll*dep-np.where(resolved,toll*val,0.0)
    netw=np.minimum(net,CAP)
    ex_ts=np.where(resolved, ts[np.clip(exit_idx,0,n-1)].astype(np.float64), np.inf)
    return net,netw,ex_ts,resolved

def sim_all(mints,spec,drop=-0.30,toll=TOLL):
    H,tp,sl,tr,pos=spec
    return {m:sim_mint(m,H,tp,sl,tr,pos,drop,toll) for m in mints}

def eval_cells(mints,cellid,sims):
    """returns cell -> [permint_w, permint_raw, n_trades, n_resolved, best_mint_w]"""
    st=S(); res={}
    for m in mints:
        el=st['ELIG'][m]; cid=cellid[m]
        net,netw,ex_ts,resv=sims[m]
        ts=st['panel'][m]['ts']
        acc={}
        for a in range(len(el)):
            c=int(cid[a])
            if c<0: continue
            e=int(el[a])+1
            r=acc.get(c)
            if r is None: r=[0.0,0.0,0,-1.0,0]; acc[c]=r
            if ts[e]<r[3]: continue
            r[0]+=netw[e]; r[1]+=net[e]; r[2]+=1; r[3]=ex_ts[e]; r[4]+=1 if resv[e] else 0
        for c,r in acc.items():
            d=res.get(c)
            if d is None: d=[[],[],0,0]; res[c]=d
            d[0].append(r[0]/r[2]); d[1].append(r[1]/r[2]); d[2]+=r[2]; d[3]+=r[4]
    return res

def stats(vals):
    k=len(vals)
    if k<2: return None
    a=np.array(vals,dtype=float)
    mu=float(a.mean()); sd=float(a.std(ddof=1)); med=float(np.median(a))
    se=sd/math.sqrt(k) if sd>0 else 0.0
    return mu,med,sd,se,k

def tstat(s,base):
    if s is None or s[3]<=0: return 0.0
    return (s[0]-base)/s[3]

def pval_t(t):
    return math.erfc(abs(t)/math.sqrt(2.0))

def bh(pvals,q=0.10):
    n=len(pvals)
    if n==0: return set()
    idx=sorted(range(n),key=lambda i:pvals[i]); thr=0
    for rank,i in enumerate(idx,1):
        if pvals[i]<=q*rank/n: thr=rank
    return set(idx[:thr])

def boot(vals,base,B=4000,seed=7):
    a=np.array(vals,dtype=float); k=len(a)
    rng=np.random.default_rng(seed)
    idx=rng.integers(0,k,size=(B,k))
    mus=a[idx].mean(axis=1)
    lo,hi=np.quantile(mus,[0.025,0.975])
    pe=float((mus<=base).mean())
    return float(lo),float(hi),min(1.0,2*min(pe,1-pe))

QE=[0.0,0.15,0.35,0.50,0.65,0.85,1.0]

def is_mint_constant(mints,f):
    st=S()
    for m in mints[:60]:
        v=st['FEAT'][m][f]
        if len(v)>2 and np.nanstd(v)>1e-12: return False
    return True

def make_edges(mints,f):
    st=S()
    if is_mint_constant(mints,f):
        vals=np.array([st['FEAT'][m][f][0] for m in mints],dtype=float)
    else:
        vals=np.concatenate([st['FEAT'][m][f][st['ELIG'][m]] for m in mints])
    vals=vals[np.isfinite(vals)]
    if len(vals)<20: return None
    e=np.unique(np.quantile(vals,QE))
    if len(e)<3: return None
    e=e.astype(float); e[0]=-np.inf; e[-1]=np.inf
    return e

def bin_of(mints,f,edges):
    st=S(); out={}; nb=len(edges)-1
    for m in mints:
        v=st['FEAT'][m][f][st['ELIG'][m]]
        b=np.searchsorted(edges,v,side='right')-1
        b=np.where(np.isfinite(v),np.clip(b,0,nb-1),-1)
        out[m]=b.astype(np.int64)
    return out,nb
