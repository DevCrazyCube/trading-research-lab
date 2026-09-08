import sqlite3, json, hashlib, os, sys, time
import numpy as np

DB='/home/anont/meme/research/midcap/grad_ohlcv.sqlite'
OUT='/home/anont/meme/_fv0/cache.npz'

HORIZONS=[3,5,10,15,20,30,45,60,90,120]
TPS=[0.10,0.20,0.35,0.60,1.00]
SLS=[0.15,0.30,0.50,0.75]
HMAX=max(HORIZONS)

t0=time.time()
con=sqlite3.connect(DB)
rows=con.execute("select mint,bars_json,status from ohlcv").fetchall()
print('rows',len(rows))

mints=[]; mint_h=[]
feat_rows=[]      # list of per-mint dict of arrays
E_mint=[]; E_bar=[]; E_h=[]; E_ts=[]; E_P=[]
TPIDX=[]; SLIDX=[]; HIDX=[]
FEAT=[]

W=20
FEATNAMES=['volrel20','volrel5','volaccel','rangerel20','density20','gap_prev','eff20',
           'rvol20','vwapdev20','clsloc','ret5','ret15','notional20','age_min','volshare20',
           'maxgap20','upvolfrac10','vol_now','range_now','ret1']

nmint=0
for mint,bj,status in rows:
    if status!='ok' or not bj: continue
    h=int(hashlib.md5(mint.encode()).hexdigest(),16)%3
    if h==0:  # RESERVED HOLDOUT - never touched
        continue
    b=json.loads(bj)
    if len(b)<8: continue
    b.sort(key=lambda x:x[0])
    a=np.array(b,dtype=np.float64)
    ts=a[:,0]; o=a[:,1]; hi=a[:,2]; lo=a[:,3]; cl=a[:,4]; vol=a[:,5]
    n=len(ts)
    if n<8: continue
    # sanity
    if not np.all(np.isfinite(a)): continue
    if np.any(cl<=0) or np.any(o<=0): continue

    rng=(hi-lo)/np.maximum(cl,1e-30)
    # rolling helpers (simple loops, n is small)
    med_v20=np.full(n,np.nan); med_v5=np.full(n,np.nan); med_rng20=np.full(n,np.nan)
    sum_v20=np.full(n,np.nan); sum_v3=np.full(n,np.nan); sum_v7prev=np.full(n,np.nan)
    vwap20=np.full(n,np.nan); eff20=np.full(n,np.nan); rvol20=np.full(n,np.nan)
    dens20=np.full(n,np.nan); maxgap20=np.full(n,np.nan); upfrac10=np.full(n,np.nan)
    for i in range(n):
        s=max(0,i-19)
        if i>=5:
            vv=vol[s:i+1]; rr=rng[s:i+1]
            med_v20[i]=np.median(vv); med_rng20[i]=np.median(rr)
            sum_v20[i]=vv.sum()
            pv=(cl[s:i+1]*vol[s:i+1]).sum(); vs=vv.sum()
            vwap20[i]=pv/vs if vs>0 else cl[i]
            lr=np.diff(np.log(cl[s:i+1]))
            rvol20[i]=np.sqrt(np.mean(lr*lr)) if len(lr)>0 else 0.0
            tot=np.abs(np.diff(cl[s:i+1])).sum()
            eff20[i]=abs(cl[i]-cl[s])/tot if tot>0 else 0.0
            # density: bars present in last 20 wall-clock minutes
            lo_t=ts[i]-20*60
            k=np.searchsorted(ts,lo_t,'left')
            dens20[i]=(i-k+1)/20.0
            g=np.diff(ts[s:i+1])/60.0
            maxgap20[i]=g.max() if len(g)>0 else 0.0
        if i>=4:
            med_v5[i]=np.median(vol[i-4:i+1])
        if i>=5:
            a0=max(0,i-9)
            vv=vol[a0:i+1]; up=(cl[a0:i+1]>o[a0:i+1])
            s10=vv.sum()
            upfrac10[i]=vv[up].sum()/s10 if s10>0 else 0.5
            sum_v3[i]=vol[max(0,i-2):i+1].sum()/min(3,i+1)*3.0
            b0=max(0,i-9); b1=max(1,i-2)
            sum_v7prev[i]=vol[b0:b1].sum()/max(1,(b1-b0))*7.0

    eps=1e-30
    f={}
    f['volrel20']=vol/np.maximum(med_v20,eps)
    f['volrel5']=vol/np.maximum(med_v5,eps)
    f['volaccel']=(sum_v3/3.0)/np.maximum(sum_v7prev/7.0,eps)
    f['rangerel20']=rng/np.maximum(med_rng20,eps)
    f['density20']=dens20
    gp=np.full(n,np.nan); gp[1:]=(ts[1:]-ts[:-1])/60.0
    f['gap_prev']=gp
    f['eff20']=eff20
    f['rvol20']=rvol20
    f['vwapdev20']=cl/np.maximum(vwap20,eps)-1.0
    denom=np.maximum(hi-lo,eps)
    f['clsloc']=(cl-lo)/denom
    r5=np.full(n,np.nan); r5[5:]=cl[5:]/np.maximum(cl[:-5],eps)-1.0
    f['ret5']=r5
    r15=np.full(n,np.nan); r15[15:]=cl[15:]/np.maximum(cl[:-15],eps)-1.0
    f['ret15']=r15
    f['notional20']=med_v20
    f['age_min']=(ts-ts[0])/60.0
    f['volshare20']=vol/np.maximum(sum_v20,eps)
    f['maxgap20']=maxgap20
    f['upvolfrac10']=upfrac10
    f['vol_now']=vol
    f['range_now']=rng
    r1=np.full(n,np.nan); r1[1:]=cl[1:]/np.maximum(cl[:-1],eps)-1.0
    f['ret1']=r1

    F=np.stack([f[k] for k in FEATNAMES],axis=1)

    # ---- exit precompute for entry bar e (signal bar i=e-1) ----
    ntp=len(TPS); nsl=len(SLS); nh=len(HORIZONS)
    BIG=10**9
    for e in range(6, n):          # signal bar i=e-1 needs >=5 bars history
        P=o[e]
        if P<=0: continue
        tgt_max=ts[e]+HMAX*60
        end=int(np.searchsorted(ts,tgt_max,'left'))
        end=max(end,e+1)
        cmax=np.maximum.accumulate(hi[e:end])
        cmin=np.minimum.accumulate(lo[e:end])
        tpi=np.empty(ntp,dtype=np.int64); sli=np.empty(nsl,dtype=np.int64)
        for k,p in enumerate(TPS):
            lev=P*(1.0+p)
            j=int(np.searchsorted(cmax,lev,'left'))
            tpi[k]= e+j if j<len(cmax) else BIG
        negc=-cmin
        for k,s in enumerate(SLS):
            lev=-(P*(1.0-s))
            j=int(np.searchsorted(negc,lev,'left'))
            sli[k]= e+j if j<len(negc) else BIG
        hidx=np.empty(nh,dtype=np.int64)
        for k,H in enumerate(HORIZONS):
            j=int(np.searchsorted(ts,ts[e]+H*60,'left'))
            hidx[k]= j if j<n else -1
        E_mint.append(nmint); E_bar.append(e); E_h.append(h); E_ts.append(ts[e]); E_P.append(P)
        TPIDX.append(tpi); SLIDX.append(sli); HIDX.append(hidx)
        FEAT.append(F[e-1])
    mints.append(mint); mint_h.append(h)
    # store open/close arrays for exit pricing
    feat_rows.append((o,cl,n))
    nmint+=1

print('mints',nmint,'entries',len(E_mint),'t',time.time()-t0)

E_mint=np.array(E_mint,dtype=np.int32); E_bar=np.array(E_bar,dtype=np.int32)
E_h=np.array(E_h,dtype=np.int8); E_ts=np.array(E_ts,dtype=np.float64); E_P=np.array(E_P)
TPIDX=np.array(TPIDX,dtype=np.int64); SLIDX=np.array(SLIDX,dtype=np.int64); HIDX=np.array(HIDX,dtype=np.int64)
FEAT=np.array(FEAT,dtype=np.float64)

# flat open/close lookup: build offset table
offs=np.zeros(nmint+1,dtype=np.int64)
for k,(o,cl,n) in enumerate(feat_rows): offs[k+1]=offs[k]+n
OPEN=np.concatenate([x[0] for x in feat_rows])
CLOSE=np.concatenate([x[1] for x in feat_rows])
NBAR=np.array([x[2] for x in feat_rows],dtype=np.int64)

np.savez_compressed(OUT, E_mint=E_mint,E_bar=E_bar,E_h=E_h,E_ts=E_ts,E_P=E_P,
    TPIDX=TPIDX,SLIDX=SLIDX,HIDX=HIDX,FEAT=FEAT,OPEN=OPEN,CLOSE=CLOSE,offs=offs,NBAR=NBAR,
    featnames=np.array(FEATNAMES),horizons=np.array(HORIZONS),tps=np.array(TPS),sls=np.array(SLS),
    mints=np.array(mints),mint_h=np.array(mint_h,dtype=np.int8))
print('saved',OUT,'t',time.time()-t0)
print('h1 mints',int((np.array(mint_h)==1).sum()),'h2 mints',int((np.array(mint_h)==2).sum()))
print('h1 entries',int((E_h==1).sum()),'h2 entries',int((E_h==2).sum()))
