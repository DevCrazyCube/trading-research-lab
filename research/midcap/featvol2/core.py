import sqlite3, json, hashlib, math, sys, os
import numpy as np

DB='/home/anont/meme/research/midcap/grad_ohlcv.sqlite'

def h_of(m):
    return int(hashlib.md5(m.encode()).hexdigest(),16)%3

def load():
    c=sqlite3.connect('file:%s?mode=ro'%DB,uri=True)
    rows=c.execute("select mint,bars_json from ohlcv where bars_json is not null").fetchall()
    mints=[];data=[];n_res=0
    for mint,bj in rows:
        hh=h_of(mint)
        if hh==0:
            n_res+=1
            continue                       # RESERVED HOLDOUT - never touched
        try: b=json.loads(bj)
        except Exception: continue
        if not b or len(b)<8: continue
        b=sorted(b,key=lambda x:x[0])
        out=[];seen=set()
        for r in b:
            if r[0] in seen: continue
            seen.add(r[0]); out.append(r)
        if len(out)<8: continue
        a=np.array(out,dtype=np.float64)
        if not np.all(np.isfinite(a)): continue
        if np.any(a[:,1:5]<=0): continue
        mints.append((mint,hh)); data.append(a)
    c.close()
    return mints,data,n_res

class Book:
    def __init__(self,mints,data):
        self.mints=[m for m,_ in mints]
        self.hh=np.array([x for _,x in mints],dtype=np.int64)
        st=[];en=[];TS=[];O=[];HI=[];LO=[];C=[];V=[];MID=[];off=0
        for i,a in enumerate(data):
            n=a.shape[0]; st.append(off); en.append(off+n); off+=n
            TS.append(a[:,0]);O.append(a[:,1]);HI.append(a[:,2]);LO.append(a[:,3]);C.append(a[:,4]);V.append(a[:,5])
            MID.append(np.full(n,i,dtype=np.int64))
        self.TS=np.concatenate(TS);self.O=np.concatenate(O);self.HI=np.concatenate(HI)
        self.LO=np.concatenate(LO);self.C=np.concatenate(C);self.V=np.concatenate(V)
        self.MID=np.concatenate(MID)
        self.starts=np.array(st);self.ends=np.array(en)
        self.N=off;self.nm=len(self.mints)
        self.HI=np.maximum(self.HI,np.maximum(self.O,self.C))
        self.LO=np.minimum(self.LO,np.minimum(self.O,self.C))
        vs=np.zeros(self.N,bool)
        for i in range(self.nm):
            s,e=self.starts[i],self.ends[i]; vs[s:e-1]=True
        self.valid_sig=vs                       # bar i is a legal SIGNAL bar (an entry bar exists)

def build_exit(book,H_min):
    N=book.N; k=np.full(N,-1,dtype=np.int64); tgt=book.TS+H_min*60.0
    for i in range(book.nm):
        s,e=book.starts[i],book.ends[i]
        idx=np.searchsorted(book.TS[s:e],tgt[s:e],side='left')
        k[s:e]=np.where(idx<(e-s),idx+s,-1)
    return k

def path_extremes(book,k,maxwin):
    N=book.N; ar=np.arange(N)
    L=np.where(k>=0,k-ar,0); L=np.clip(L,0,maxwin).astype(np.int32)
    Rmax=np.full((N,maxwin),-np.inf,dtype=np.float32)
    Rmin=np.full((N,maxwin),np.inf,dtype=np.float32)
    for m in range(maxwin):
        ok=(m<L); src=np.clip(ar+m,0,N-1)
        Rmax[ok,m]=book.HI[src][ok]; Rmin[ok,m]=book.LO[src][ok]
    np.maximum.accumulate(Rmax,axis=1,out=Rmax)
    np.minimum.accumulate(Rmin,axis=1,out=Rmin)
    ent=book.O.astype(np.float32)[:,None]
    Rmax/=ent; Rmin/=ent
    return Rmax,Rmin,L

def gross_returns(book,k,tp,sl,scale=1.0,Rmax=None,Rmin=None,L=None):
    N=book.N; ar=np.arange(N)
    exit_open=np.where(k>=0,book.O[np.clip(k,0,N-1)],np.nan)
    time_ret=exit_open/book.O-1.0
    g=time_ret.copy()
    if tp is None and sl is None:
        return np.where(k>=0,g,np.nan)
    W=Rmax.shape[1]
    if tp is not None:
        itp=(Rmax<np.float32(1.0+tp)).sum(axis=1); tp_ok=itp<L
    else:
        itp=np.full(N,W+1); tp_ok=np.zeros(N,bool)
    if sl is not None:
        isl=(Rmin>np.float32(1.0+sl)).sum(axis=1); sl_ok=isl<L
    else:
        isl=np.full(N,W+1); sl_ok=np.zeros(N,bool)
    sl_first=sl_ok&((~tp_ok)|(isl<=itp))
    tp_first=tp_ok&((~sl_ok)|(itp<isl))
    if sl is not None: g=np.where(sl_first,sl,g)
    if tp is not None:
        if scale>=1.0:
            g=np.where(tp_first,tp,g)
        else:
            rem=np.where(sl_ok&(isl>itp),(sl if sl is not None else 0.0),time_ret)
            g=np.where(tp_first,scale*tp+(1.0-scale)*rem,g)
    return np.where(k>=0,g,np.nan)

def netify(g,k,toll,drop,cap=None):
    """cap winsorises the GROSS gain (feed glitches produce +600x one-minute bars).
    Capping only the right tail can never manufacture a positive result."""
    dv=(1.0+drop)*(1.0-toll)-1.0 if drop>-1.0 else -1.0
    gg=g if cap is None else np.minimum(g,cap)
    return np.where(k>=0,(1.0+gg)*(1.0-toll)-1.0,dv)

class Runner:
    """no-overlap greedy + mint-equal aggregation"""
    def __init__(self,book):
        self.MID=book.MID; self.ends=book.ends; self.book=book
    def select(self,mask,k,off=1):
        sig=np.flatnonzero(mask)
        if sig.size==0: return np.empty(0,dtype=np.int64)
        MID=self.MID; ends=self.ends
        taken=[];cur=-1;nxt=-1
        for i in sig:
            m=MID[i]
            if m!=cur: cur=m;nxt=-1
            if i<nxt: continue
            j=i+off
            if j>=ends[m]: continue
            kk=k[j]
            taken.append(j)
            nxt = kk if kk>=0 else ends[m]+2
        return np.array(taken,dtype=np.int64)
    def stats(self,js,net,k=None):
        if js.size==0: return None
        r=net[js];mid=self.MID[js]
        u,inv=np.unique(mid,return_inverse=True)
        pm=np.bincount(inv,weights=r)/np.bincount(inv)
        out=dict(n=int(js.size),clusters=int(u.size),mean=float(pm.mean()),
                 median=float(np.median(pm)),pm=pm)
        if k is not None: out['res']=float((k[js]>=0).mean())
        return out

def boot_lo(pm,B=2000,seed=11):
    if pm.size<4: return float('nan')
    rng=np.random.default_rng(seed)
    idx=rng.integers(0,pm.size,size=(B,pm.size))
    return float(np.percentile(pm[idx].mean(axis=1),2.5))
