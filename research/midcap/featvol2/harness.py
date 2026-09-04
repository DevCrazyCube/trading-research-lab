import sqlite3, json, hashlib, math, sys, os
import numpy as np

DB='/home/anont/meme/research/midcap/grad_ohlcv.sqlite'

def h_of(m):
    return int(hashlib.md5(m.encode()).hexdigest(),16)%3

def load():
    c=sqlite3.connect('file:%s?mode=ro'%DB,uri=True)
    rows=c.execute("select mint,bars_json,status from ohlcv where bars_json is not null").fetchall()
    mints=[];data=[]
    n_reserved=0
    for mint,bj,status in rows:
        hh=h_of(mint)
        if hh==0:
            n_reserved+=1
            continue          # NEVER touch reserved holdout
        try: b=json.loads(bj)
        except Exception: continue
        if not b or len(b)<6: continue
        b=sorted(b,key=lambda x:x[0])
        # dedupe ts
        out=[];seen=set()
        for r in b:
            if r[0] in seen: continue
            seen.add(r[0]); out.append(r)
        if len(out)<6: continue
        a=np.array(out,dtype=np.float64)
        if not np.all(np.isfinite(a)): continue
        if np.any(a[:,1:5]<=0): continue
        mints.append((mint,hh)); data.append(a)
    c.close()
    return mints,data,n_reserved

class Book:
    """Global concatenated bar store with mint boundaries."""
    def __init__(self,mints,data):
        self.mints=[m for m,_ in mints]
        self.hh=np.array([x for _,x in mints],dtype=np.int64)
        self.starts=[];self.ends=[]
        TS=[];O=[];HI=[];LO=[];C=[];V=[];MID=[]
        off=0
        for i,a in enumerate(data):
            n=a.shape[0]
            self.starts.append(off); self.ends.append(off+n); off+=n
            TS.append(a[:,0]);O.append(a[:,1]);HI.append(a[:,2]);LO.append(a[:,3]);C.append(a[:,4]);V.append(a[:,5])
            MID.append(np.full(n,i,dtype=np.int64))
        self.TS=np.concatenate(TS);self.O=np.concatenate(O);self.HI=np.concatenate(HI)
        self.LO=np.concatenate(LO);self.C=np.concatenate(C);self.V=np.concatenate(V)
        self.MID=np.concatenate(MID)
        self.starts=np.array(self.starts);self.ends=np.array(self.ends)
        self.N=off; self.nm=len(self.mints)
        # sanity: HI>=max(O,C)>=min>=LO
        self.HI=np.maximum(self.HI,np.maximum(self.O,self.C))
        self.LO=np.minimum(self.LO,np.minimum(self.O,self.C))

def build_exit(book,H_min,cap_bars=None):
    """For each bar j (a candidate ENTRY bar) return exit index k (open of first real
    bar with ts>=ts[j]+H*60) or -1 if none (dropout)."""
    N=book.N; k=np.full(N,-1,dtype=np.int64)
    tgt=book.TS+H_min*60.0
    for i in range(book.nm):
        s,e=book.starts[i],book.ends[i]
        ts=book.TS[s:e]
        idx=np.searchsorted(ts,tgt[s:e],side='left')
        good=idx<(e-s)
        kk=np.where(good,idx+s,-1)
        k[s:e]=kk
    return k

def path_extremes(book,k,maxwin):
    """cummax of HI/entryopen and cummin of LO/entryopen over bars j..k-1 (inclusive of j).
    Returns matrices (N,maxwin) of running max ratio and running min ratio, and length L[j]."""
    N=book.N
    L=np.where(k>=0,k-np.arange(N),0)
    L=np.clip(L,0,maxwin)
    Rmax=np.full((N,maxwin),-np.inf); Rmin=np.full((N,maxwin),np.inf)
    for m in range(maxwin):
        src=np.arange(N)+m
        ok=(m<L)
        src_c=np.clip(src,0,N-1)
        Rmax[ok,m]=book.HI[src_c][ok]
        Rmin[ok,m]=book.LO[src_c][ok]
    ent=book.O.copy()
    Rmax=np.maximum.accumulate(Rmax,axis=1)/ent[:,None]
    Rmin=np.minimum.accumulate(Rmin,axis=1)/ent[:,None]
    return Rmax,Rmin,L

def gross_returns(book,k,Rmax,Rmin,L,tp,sl,scale=1.0):
    """gross return for a position ENTERED at open of bar j, per j. NaN where dropout."""
    N=book.N
    exit_open=np.where(k>=0,book.O[np.clip(k,0,N-1)],np.nan)
    time_ret=exit_open/book.O-1.0
    g=time_ret.copy()
    W=Rmax.shape[1]
    if tp is not None:
        itp=(Rmax< (1.0+tp)).sum(axis=1); tp_ok=itp<L
    else:
        itp=np.full(N,W+1); tp_ok=np.zeros(N,bool)
    if sl is not None:
        isl=(Rmin> (1.0+sl)).sum(axis=1); sl_ok=isl<L
    else:
        isl=np.full(N,W+1); sl_ok=np.zeros(N,bool)
    # SL wins ties (conservative)
    sl_first=sl_ok&((~tp_ok)|(isl<=itp))
    tp_first=tp_ok&((~sl_ok)|(itp<isl))
    if sl is not None:
        g=np.where(sl_first,sl,g)
    if tp is not None:
        if scale>=1.0:
            g=np.where(tp_first,tp,g)
        else:
            rem=np.where(sl_ok&(isl>itp),sl,time_ret)
            g=np.where(tp_first,scale*tp+(1.0-scale)*rem,g)
    g=np.where(k>=0,g,np.nan)
    return g

def netify(g,k,toll,drop):
    n=np.where(k>=0,(1.0+g)*(1.0-toll)-1.0,(1.0+drop)*(1.0-toll)-1.0 if drop>-1.0 else -1.0)
    return n

def greedy(book,sigmask,k):
    """No-overlap selection. sigmask over SIGNAL bars i. Returns entry bar array j (=i+1)."""
    N=book.N
    sig=np.flatnonzero(sigmask)
    if sig.size==0: return np.empty(0,dtype=np.int64)
    MID=book.MID; ends=book.ends
    taken=[]
    cur_m=-1; next_ok=-1
    for i in sig:
        m=MID[i]
        if m!=cur_m:
            cur_m=m; next_ok=-1
        if i<next_ok: continue
        j=i+1
        if j>=ends[m]: continue
        kk=k[j]
        taken.append(j)
        next_ok = kk if kk>=0 else ends[m]+1
    return np.array(taken,dtype=np.int64)

def agg(book,js,net):
    """mint-equal aggregation"""
    if js.size==0: return None
    mid=book.MID[js]; r=net[js]
    u,inv=np.unique(mid,return_inverse=True)
    s=np.bincount(inv,weights=r); c=np.bincount(inv)
    pm=s/c
    return dict(n=int(js.size),clusters=int(u.size),mean=float(pm.mean()),
                median=float(np.median(pm)),pm=pm,u=u)

def boot_ci(pm,B=2000,seed=7):
    rng=np.random.default_rng(seed); n=pm.size
    if n<3: return (float('nan'),float('nan'))
    idx=rng.integers(0,n,size=(B,n))
    ms=pm[idx].mean(axis=1)
    return (float(np.percentile(ms,2.5)),float(np.percentile(ms,97.5)))
