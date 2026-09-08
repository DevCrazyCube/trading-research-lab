"""Regime-conditioned exhaustive sweep. Harness contract A-G enforced.
Stage 1: build per-row features (mint-level + universe regime state) and per-row
exit outcomes for every exit structure. Cached to npz.
"""
import json, math, os, sys
import numpy as np

W='/home/anont/meme/.regime1/'
LOG=open(W+'engine.txt','w')
def P(*a):
    print(*a, file=LOG); LOG.flush()

bars=json.load(open(W+'bars.json'))
creates=np.array(json.load(open(W+'creates.json')), dtype=np.int64)

mint_names=sorted(bars.keys())
M=len(mint_names)
P('mints', M)

# ---- flatten ----
rows_mint=[]; rows_ts=[]; rows_o=[]; rows_h=[]; rows_l=[]; rows_c=[]; rows_v=[]
mint_slice={}
for mi,m in enumerate(mint_names):
    hh,b=bars[m]
    s=len(rows_ts)
    for r in b:
        rows_mint.append(mi); rows_ts.append(int(r[0])); rows_o.append(r[1]); rows_h.append(r[2]); rows_l.append(r[3]); rows_c.append(r[4]); rows_v.append(r[5])
    mint_slice[mi]=(s,len(rows_ts))
mid=np.array(rows_mint,dtype=np.int32); ts=np.array(rows_ts,dtype=np.int64)
op=np.array(rows_o); hi=np.array(rows_h); lo=np.array(rows_l); cl=np.array(rows_c); vol=np.array(rows_v)
N=len(ts)
mint_h=np.array([bars[m][0] for m in mint_names],dtype=np.int8)
P('rows', N)

T0=int(ts.min()); T1=int(ts.max())
NM=(T1-T0)//60+1
P('minutes', NM)

# ================= UNIVERSE REGIME FEATURES (per minute) =================
minute_idx=((ts-T0)//60).astype(np.int64)
# close matrix forward-filled per mint over minute grid, plus activity
C=np.full((M,NM), np.nan)
ACTMIN=np.zeros((M,NM), dtype=bool)   # had a bar exactly this minute
firstopen=np.zeros(M); firstts=np.zeros(M,dtype=np.int64); lastts=np.zeros(M,dtype=np.int64)
for mi in range(M):
    s,e=mint_slice[mi]
    mi_idx=minute_idx[s:e]
    C[mi, mi_idx]=cl[s:e]
    ACTMIN[mi, mi_idx]=True
    firstopen[mi]=op[s]; firstts[mi]=ts[s]; lastts[mi]=ts[e-1]
# forward fill
for j in range(1,NM):
    m_nan=np.isnan(C[:,j])
    C[m_nan,j]=C[m_nan,j-1]
# volume per minute per mint
VOLM=np.zeros((M,NM))
np.add.at(VOLM,(mid,minute_idx),vol)

def rollsum(A,k):
    """sum over trailing k minutes inclusive, axis=1"""
    cs=np.cumsum(A,axis=1)
    out=cs.copy()
    out[:,k:]=cs[:,k:]-cs[:,:-k]
    return out

ACT15 = rollsum(ACTMIN.astype(np.float64),15) > 0          # M x NM
COHVOL15 = rollsum(VOLM,15).sum(axis=0)
ACTCNT = ACT15.sum(axis=0)
# fraction up vs own first open
UPMAT = (C > firstopen[:,None])
FRACUP = np.where(ACTCNT>0, (UPMAT & ACT15).sum(axis=0)/np.maximum(ACTCNT,1), np.nan)
# cohort median return 15m / 60m among active
def medret(lag):
    R=np.full((M,NM), np.nan)
    R[:,lag:]=C[:,lag:]/C[:,:-lag]-1.0
    R[~ACT15]=np.nan
    return np.nanmedian(np.where(np.isfinite(R),R,np.nan),axis=0)
import warnings
warnings.filterwarnings('ignore')
MEDRET15=medret(15)
MEDRET60=medret(60)
# young fraction: first bar within 60m
agemin_mat = (np.arange(NM)[None,:] - ((firstts-T0)//60)[:,None])
YOUNG = (agemin_mat>=0)&(agemin_mat<60)
YOUNGFRAC=np.where(ACTCNT>0,(YOUNG&ACT15).sum(axis=0)/np.maximum(ACTCNT,1),np.nan)
# new listings in last 60m
NEWL=np.zeros(NM)
fm=((firstts-T0)//60)
np.add.at(NEWL, fm, 1.0)
NEWL60=np.convolve(NEWL, np.ones(60), mode='full')[:NM]
NEWL60=np.array([NEWL[max(0,j-59):j+1].sum() for j in range(NM)])
# creates in last 60m (coverage limited)
cm=((creates-T0)//60)
cm=cm[(cm>=0)&(cm<NM)]
CR=np.zeros(NM); np.add.at(CR, cm, 1.0)
CRcs=np.cumsum(CR)
LAUNCH60=CRcs.copy(); LAUNCH60[60:]=CRcs[60:]-CRcs[:-60]
CREATE_COV = (np.arange(NM)*60+T0) <= int(creates.max())
HOUR=(((np.arange(NM)*60+T0)//3600)%24).astype(np.float64)

REG={'LAUNCH60':LAUNCH60,'COHVOL15':COHVOL15,'ACTCNT':ACTCNT.astype(float),
     'FRACUP':FRACUP,'MEDRET15':MEDRET15,'MEDRET60':MEDRET60,
     'YOUNGFRAC':YOUNGFRAC,'NEWL60':NEWL60,'HOUR':HOUR}
for k,v in REG.items():
    fin=np.isfinite(v)
    P('regime',k,'finite',int(fin.sum()),'min',float(np.nanmin(v)),'med',float(np.nanmedian(v)),'max',float(np.nanmax(v)))
P('create coverage minutes', int(CREATE_COV.sum()), 'of', NM)

# ================= PER-ROW MINT FEATURES =================
ret5=np.full(N,np.nan); ret15=np.full(N,np.nan); ret60=np.full(N,np.nan)
dd=np.full(N,np.nan); vsopen=np.full(N,np.nan); agem=np.full(N,np.nan); relvol=np.full(N,np.nan)
for mi in range(M):
    s,e=mint_slice[mi]
    t=ts[s:e]; c=cl[s:e]; hh=hi[s:e]; v=vol[s:e]
    n=e-s
    for lag,arr in ((300,ret5),(900,ret15),(3600,ret60)):
        j=np.searchsorted(t, t-lag, side='right')-1
        ok=j>=0
        a=np.full(n,np.nan)
        a[ok]=c[ok]/c[j[ok]]-1.0
        arr[s:e]=a
    rh=np.maximum.accumulate(hh)
    dd[s:e]=c/rh-1.0
    vsopen[s:e]=c/op[s]-1.0
    agem[s:e]=(t-t[0])/60.0
    cv=np.cumsum(v); mean_so_far=cv/np.arange(1,n+1)
    j5=np.searchsorted(t, t-300, side='left')
    v5=cv-np.where(j5>0,cv[np.maximum(j5-1,0)],0.0)
    relvol[s:e]=v5/np.maximum(mean_so_far,1e-12)

# ================= EXIT STRUCTURES =================
HORIZ=[5,10,15,30,60,120]
# next-bar index for entry: signal row r -> entry row r+1 (same mint)
last_of_mint=np.zeros(N,dtype=bool)
for mi in range(M):
    s,e=mint_slice[mi]; last_of_mint[e-1]=True
entry_row=np.arange(N)+1
valid_sig=~last_of_mint

# horizon row: first row (same mint) with ts >= entry_ts + H*60 ; -1 if none
HROW={}
for H in HORIZ:
    hr=np.full(N,-1,dtype=np.int64)
    for mi in range(M):
        s,e=mint_slice[mi]
        t=ts[s:e]
        tgt=t+H*60
        j=np.searchsorted(t,tgt,side='left')
        j=np.where(j<(e-s), j+s, -1)
        hr[s:e]=j
    HROW[H]=hr
P('horizon rows built')

EXITS=[]
def addexit(name,kind,**kw):
    EXITS.append(dict(name=name,kind=kind,**kw))
for H in HORIZ: addexit('T%d'%H,'time',H=H)
for H,TP in ((15,0.15),(15,0.30),(60,0.30),(60,0.50)):
    addexit('T%d_TP%d'%(H,TP*100),'tp',H=H,TP=TP)
for H,TP,SL in ((60,0.30,0.20),(60,0.50,0.30),(60,0.20,0.15),(15,0.20,0.15)):
    addexit('T%d_TP%d_SL%d'%(H,TP*100,SL*100),'brk',H=H,TP=TP,SL=SL)
for H,TR in ((60,0.25),(120,0.35)):
    addexit('T%d_TR%d'%(H,TR*100),'trail',H=H,TR=TR)
P('n exit structures', len(EXITS))

def compute_exit(ex):
    """returns exit_price array (nan=dropout) and exit_row array (-1 dropout) indexed by SIGNAL row."""
    H=ex['H']; hr=HROW[H]
    epx=np.full(N,np.nan); erow=np.full(N,-1,dtype=np.int64)
    kind=ex['kind']
    er=entry_row
    for r in range(N):
        if last_of_mint[r]: continue
        e0=er[r]
        E=op[e0]
        j=hr[e0]
        if kind=='time':
            if j<0: continue
            epx[r]=op[j]; erow[r]=j; continue
        end = j if j>=0 else -1
        # scan bars e0..end-1 (bars fully inside horizon)
        stop = end if end>=0 else (mint_slice[mid[r]][1])
        px=None; xr=-1
        if kind=='tp':
            lvl=E*(1+ex['TP'])
            for k in range(e0,stop):
                if hi[k]>=lvl:
                    px=lvl; xr=k; break
        elif kind=='brk':
            up=E*(1+ex['TP']); dn=E*(1-ex['SL'])
            for k in range(e0,stop):
                if lo[k]<=dn:
                    px=dn; xr=k; break
                if hi[k]>=up:
                    px=up; xr=k; break
        elif kind=='trail':
            peak=E; tr=ex['TR']
            for k in range(e0,stop):
                if lo[k]<=peak*(1-tr):
                    px=peak*(1-tr); xr=k; break
                if hi[k]>peak: peak=hi[k]
        if px is not None:
            epx[r]=px; erow[r]=xr
        else:
            if end>=0:
                epx[r]=op[end]; erow[r]=end
            # else dropout
    return epx,erow

cache=W+'exits.npz'
if os.path.exists(cache):
    z=np.load(cache)
    EPX=z['EPX']; EROW=z['EROW']
else:
    EPX=np.full((len(EXITS),N),np.nan); EROW=np.full((len(EXITS),N),-1,dtype=np.int64)
    for ei,ex in enumerate(EXITS):
        a,b=compute_exit(ex)
        EPX[ei]=a; EROW[ei]=b
        P('exit built',ex['name'],'resolved',float(np.isfinite(a[valid_sig]).mean()))
    np.savez_compressed(cache,EPX=EPX,EROW=EROW)
P('exits done')

np.savez_compressed(W+'feats.npz', mid=mid, ts=ts, op=op, cl=cl, hi=hi, lo=lo, vol=vol,
    minute_idx=minute_idx, ret5=ret5, ret15=ret15, ret60=ret60, dd=dd, vsopen=vsopen,
    agem=agem, relvol=relvol, last_of_mint=last_of_mint, mint_h=mint_h,
    LAUNCH60=LAUNCH60, COHVOL15=COHVOL15, ACTCNT=ACTCNT.astype(float), FRACUP=FRACUP,
    MEDRET15=MEDRET15, MEDRET60=MEDRET60, YOUNGFRAC=YOUNGFRAC, NEWL60=NEWL60, HOUR=HOUR,
    CREATE_COV=CREATE_COV, T0=np.array([T0]))
json.dump([e for e in EXITS], open(W+'exits.json','w'))
json.dump({'mint_names':mint_names,'mint_slice':{str(k):v for k,v in mint_slice.items()}}, open(W+'meta.json','w'))
P('SAVED')
LOG.close()
