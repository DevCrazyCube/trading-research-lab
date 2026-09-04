import sqlite3,json,hashlib,math,os,sys
import numpy as np

ROOT='/home/anont/meme'
DB=ROOT+'/research/midcap/grad_ohlcv.sqlite'
WL=ROOT+'/research/b11a/window_labels.sqlite'

def h_of(m): return int(hashlib.md5(m.encode()).hexdigest(),16)%3

def load(minbars=30):
    c=sqlite3.connect('file:%s?mode=ro'%DB,uri=True)
    rows=c.execute("select mint,bars_json from ohlcv where bars_json is not null").fetchall()
    c.close()
    w=sqlite3.connect('file:%s?mode=ro'%WL,uri=True)
    wl={m:(cr,bt) for m,cr,bt in w.execute("select mint,creator,block_time from window_label")}
    w.close()
    mints=[];arrs=[];meta=[]
    for mint,bj in rows:
        hh=h_of(mint)
        if hh==0: continue           # RESERVED HOLDOUT - never touched
        try: b=json.loads(bj)
        except Exception: continue
        if not b or len(b)<minbars: continue
        b=sorted(b,key=lambda x:x[0])
        out=[];seen=set()
        for r in b:
            if r[0] in seen: continue
            seen.add(r[0]); out.append(r)
        if len(out)<minbars: continue
        a=np.asarray(out,dtype=np.float64)
        if not np.all(np.isfinite(a)): continue
        if np.any(a[:,1:5]<=0): continue
        cr,bt=wl.get(mint,(None,None))
        mints.append(mint); arrs.append(a); meta.append((hh,cr,bt))
    return mints,arrs,meta

class Book:
    def __init__(self,mints,arrs,meta):
        self.mints=mints
        self.hh=np.array([m[0] for m in meta],dtype=np.int64)
        self.creator=[m[1] for m in meta]
        self.btime=np.array([(m[2] if m[2] else np.nan) for m in meta],dtype=np.float64)
        st=[];en=[];off=0
        cols=[[] for _ in range(6)]; MID=[]
        for i,a in enumerate(arrs):
            n=a.shape[0]; st.append(off); en.append(off+n); off+=n
            for j in range(6): cols[j].append(a[:,j])
            MID.append(np.full(n,i,dtype=np.int64))
        self.TS,self.O,self.HI,self.LO,self.C,self.V=[np.concatenate(x) for x in cols]
        self.MID=np.concatenate(MID)
        self.starts=np.array(st); self.ends=np.array(en); self.N=off; self.nm=len(mints)
        self.HI=np.maximum(self.HI,np.maximum(self.O,self.C))
        self.LO=np.minimum(self.LO,np.minimum(self.O,self.C))
        self.idx=np.arange(self.N)-self.starts[self.MID]
        self.mhh=self.hh[self.MID]

def roll_med(x,book,w,shift=1):
    N=book.N; out=np.full(N,np.nan)
    for i in range(book.nm):
        s,e=book.starts[i],book.ends[i]; v=x[s:e]; n=e-s
        if n<w+shift: continue
        sw=np.lib.stride_tricks.sliding_window_view(v,w)
        med=np.median(sw,axis=1)
        for_t=np.full(n,np.nan); for_t[w-1:]=med
        res=np.full(n,np.nan)
        if shift>0: res[shift:]=for_t[:-shift]
        else: res=for_t
        out[s:e]=res
    return out

def roll_sum(x,book,w,shift=0):
    N=book.N; out=np.full(N,np.nan)
    for i in range(book.nm):
        s,e=book.starts[i],book.ends[i]; v=x[s:e]; n=e-s
        if n<w+shift: continue
        cs=np.concatenate([[0.0],np.cumsum(v)])
        r=np.full(n,np.nan); r[w-1:]=cs[w:]-cs[:n-w+1]
        res=np.full(n,np.nan)
        if shift>0: res[shift:]=r[:-shift]
        else: res=r
        out[s:e]=res
    return out

def lag(x,book,k):
    N=book.N; out=np.full(N,np.nan)
    for i in range(book.nm):
        s,e=book.starts[i],book.ends[i]
        if e-s<=k: continue
        out[s+k:e]=x[s:e-k]
    return out

def runmax(x,book):
    out=np.empty(book.N)
    for i in range(book.nm):
        s,e=book.starts[i],book.ends[i]
        out[s:e]=np.maximum.accumulate(x[s:e])
    return out

def density(book,W):
    out=np.full(book.N,np.nan)
    for i in range(book.nm):
        s,e=book.starts[i],book.ends[i]; ts=book.TS[s:e]
        j=np.searchsorted(ts,ts-W*60.0,side='right')
        out[s:e]=(np.arange(e-s)-j+1)/float(W)
    return out

def build_exit(book,H_min):
    N=book.N; k=np.full(N,-1,dtype=np.int64)
    tgt=book.TS+H_min*60.0
    for i in range(book.nm):
        s,e=book.starts[i],book.ends[i]
        ts=book.TS[s:e]
        idx=np.searchsorted(ts,tgt[s:e],side='left')
        k[s:e]=np.where(idx<(e-s),idx+s,-1)
    return k

def path_ext(book,k,maxwin):
    N=book.N
    L=np.where(k>=0,k-np.arange(N),0); L=np.clip(L,0,maxwin)
    Rmax=np.full((N,maxwin),-np.inf); Rmin=np.full((N,maxwin),np.inf)
    ar=np.arange(N)
    for m in range(maxwin):
        src=np.clip(ar+m,0,N-1); ok=(m<L)
        Rmax[ok,m]=book.HI[src][ok]; Rmin[ok,m]=book.LO[src][ok]
    ent=book.O
    Rmax=np.maximum.accumulate(Rmax,axis=1)/ent[:,None]
    Rmin=np.minimum.accumulate(Rmin,axis=1)/ent[:,None]
    return Rmax,Rmin,L

def gross(book,k,Rmax,Rmin,L,tp=None,sl=None,tp_frac=1.0):
    N=book.N; W=Rmax.shape[1]
    ex=np.where(k>=0,book.O[np.clip(k,0,N-1)],np.nan)
    tret=ex/book.O-1.0
    g=tret.copy()
    if tp is not None:
        itp=(Rmax<(1.0+tp)).sum(axis=1); tp_ok=itp<L
    else: itp=np.full(N,W+2); tp_ok=np.zeros(N,bool)
    if sl is not None:
        isl=(Rmin>(1.0+sl)).sum(axis=1); sl_ok=isl<L
    else: isl=np.full(N,W+2); sl_ok=np.zeros(N,bool)
    sl_first=sl_ok&((~tp_ok)|(isl<=itp))
    tp_first=tp_ok&((~sl_ok)|(itp<isl))
    if sl is not None: g=np.where(sl_first,sl,g)
    if tp is not None:
        if tp_frac>=1.0: g=np.where(tp_first,tp,g)
        else:
            rem=np.where(sl_ok&(isl>itp),sl,tret)
            g=np.where(tp_first,tp_frac*tp+(1.0-tp_frac)*rem,g)
    return np.where(k>=0,g,np.nan)

def netify(g,k,toll,drop):
    dv=-1.0 if drop<=-1.0 else (1.0+drop)*(1.0-toll)-1.0
    return np.where(k>=0,(1.0+g)*(1.0-toll)-1.0,dv)

def boot_lo(pm,B=2000,seed=11,pct=2.5):
    n=pm.size
    if n<5: return float('nan')
    rng=np.random.default_rng(seed)
    return float(np.percentile(pm[rng.integers(0,n,size=(B,n))].mean(axis=1),pct))
