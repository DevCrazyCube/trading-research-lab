"""Kill-attempt on the one survivor: ubgrow_120 >= p75 -> flow-reversal exit, H180."""
import pickle, numpy as np
W='/home/anont/meme/.scratch_feat_flow2'
out=open(W+'/kill.txt','w')
def p(*a): print(*a,file=out); out.flush()

d=pickle.load(open(W+'/tapes.pkl','rb')); T=d['T']
Z=np.load(W+'/feats.npz',allow_pickle=True)
X=Z['X']; DM=Z['DM'].astype(np.int64); DK=Z['DK']; hv=Z['hv']; FEATS=list(Z['FEATS']); mints=list(Z['mints'])
O=np.load(W+'/outcomes_pess.npz',allow_pickle=True)
CENS=O['CENS']; TE=O['TE']; HOR=list(O['HORIZ']); RETp=O['RET']; EOFFp=O['EOFF']; FROZp=O['FROZEN']
namesp=list(O['names'])
NDP=len(DM); NM=len(mints)
hdp=hv[DM]; TR=(hdp==1); VA=(hdp==2); TOLL=0.0114
FI={f:i for i,f in enumerate(FEATS)}
meta=pickle.load(open(W+'/meta.pkl','rb'))
fullh=np.array([meta[m]['fullhist'] for m in mints])
priorc=np.array([meta[m]['prior_creates'] for m in mints])

# rebuild the lag-1 flowrev structures for H in {60,180,600}, P0 and P2
HORIZ=[(60,5),(180,5),(600,15)]
POS=['P0','P2halfout25']
NS=len(HORIZ)*len(POS)
RET=np.zeros((NS,NDP),dtype=np.float32); EOFF=np.zeros((NS,NDP),dtype=np.int32)
FROZ=np.zeros((len(HORIZ),NDP),dtype=bool)
snames=[]; sidx={}; si=0
for hi_,(H,r) in enumerate(HORIZ):
    for pi,pn in enumerate(POS):
        sidx[(hi_,pi)]=si; snames.append(f'H{H}|flowrev.lag1|{pn}'); si+=1
bounds={}; cur=DM[0]; st=0
for i in range(1,NDP):
    if DM[i]!=cur: bounds[cur]=(st,i); cur=DM[i]; st=i
bounds[cur]=(st,NDP)
for mi,(lo_i,hi_i) in bounds.items():
    D=T[mints[mi]]
    bt=D['bt']; vs=D['vs']; vt=D['vt']; sol=D['sol']/1e9; isb=D['isb'].astype(np.float64)
    price=(vs/vt).astype(np.float64); n=len(bt); bt0=bt[0]
    ks=DK[lo_i:hi_i]; te=bt[ks+1].astype(np.int64); pe=price[ks+1]
    signed=sol*(2*isb-1); AR=np.arange(len(ks))
    for hi_,(H,r) in enumerate(HORIZ):
        nb=int(H//r); span=int(bt[-1]-bt0)+H+2*r; B=span//r+2
        bidx=((bt-bt0)//r).astype(np.int64)
        clB=np.full(B,np.nan); flowB=np.zeros(B); hiB=np.full(B,-np.inf)
        clB[bidx]=price; np.add.at(flowB,bidx,signed); np.maximum.at(hiB,bidx,price)
        m0=np.isnan(clB)
        if m0[0]: clB[0]=price[0]; m0[0]=False
        idxf=np.where(~m0,np.arange(B),0); np.maximum.accumulate(idxf,out=idxf); clB=clB[idxf]
        hiB=np.where(np.isfinite(hiB),hiB,clB)
        wf=max(1,int(60//r)); cf=np.concatenate([[0.],np.cumsum(flowB)])
        flow60=cf[np.arange(B)+1]-cf[np.maximum(np.arange(B)+1-wf,0)]
        traded=np.zeros(B,bool); traded[bidx]=True
        be=((te-bt0)//r).astype(np.int64)
        cols=be[:,None]+1+np.arange(nb)[None,:]; valid=cols<B; colsC=np.clip(cols,0,B-1)
        PC=np.where(valid,clB[colsC],np.nan); PF=flow60[colsC]; PH=np.where(valid,hiB[colsC],-np.inf)
        frozen=~np.where(valid,traded[colsC],False).any(axis=1); FROZ[hi_,lo_i:hi_i]=frozen
        lastcol=np.where(valid.any(axis=1),valid.sum(axis=1)-1,0)
        endclose=np.where(np.isnan(PC[AR,lastcol]),pe,PC[AR,lastcol]); endoff=(lastcol+1)*r
        mask=(PF<0)&valid; any_=mask.any(axis=1)
        f=np.minimum(np.where(any_,mask.argmax(axis=1),nb-1)+1,nb-1)
        v=PC[AR,f]; px=np.where(any_&np.isfinite(v),v,endclose); off=np.where(any_,(f+1)*r,endoff)
        g0=np.where(frozen,0.0,px/pe-1.0)
        RET[sidx[(hi_,0)],lo_i:hi_i]=g0; EOFF[sidx[(hi_,0)],lo_i:hi_i]=off
        L=pe*1.25; h2=(PH>=L[:,None]); a2=h2.any(axis=1); f2=np.minimum(np.where(a2,h2.argmax(axis=1),0)+1,nb-1)
        v2=PC[AR,f2]; gh=np.where(np.isfinite(v2),v2,endclose)/pe-1.0
        g2=np.where(frozen,0.0,np.where(a2,0.5*gh+0.5*g0,g0))
        RET[sidx[(hi_,1)],lo_i:hi_i]=g2; EOFF[sidx[(hi_,1)],lo_i:hi_i]=off
RET=np.nan_to_num(RET,nan=0.,posinf=0.,neginf=0.)
struct_h=[0,0,1,1,2,2]
TEl=TE.tolist(); DMl=DM.tolist(); EOFFl=[EOFF[s].tolist() for s in range(NS)]
rng=np.random.default_rng(5)
def greedy(sel,s):
    eo=EOFFl[s]; keep=[]; curm=-1; free=-1
    for i in sel:
        m=DMl[i]
        if m!=curm: curm=m; free=-1
        t=TEl[i]
        if t>=free: keep.append(i); free=t+eo[i]
    return keep
def stats(keep,s,fc=None,toll=TOLL):
    if not keep: return None
    ki=np.asarray(keep); g=RET[s][ki].astype(np.float64); fz=FROZ[struct_h[s]][ki]
    if fc is not None: g=np.where(fz,fc,g)
    net=(1.0+g)*(1.0-toll)-1.0
    mm=DM[ki]; cnt=np.bincount(mm,minlength=NM); sm=np.bincount(mm,weights=net,minlength=NM)
    nz=cnt>0; mu=sm[nz]/cnt[nz]
    return dict(n=len(keep),k=int(nz.sum()),mean=float(mu.mean()),med=float(np.median(mu)),mu=mu,
                mids=np.flatnonzero(nz),net=net,keep=ki)
def boot(mu,B=6000):
    k=len(mu); idx=rng.integers(0,k,size=(B,k)); bs=mu[idx].mean(axis=1)
    return float(np.percentile(bs,2.5)),float(np.percentile(bs,97.5))

ug=X[:,FI['ubgrow_120']]
q75=float(np.percentile(ug[TR][np.isfinite(ug[TR])],75))
p('ubgrow_120 p75 threshold fit on TRAIN = %.4f'%q75)
base=(ug>=q75)&np.isfinite(ug)
S=sidx[(1,1)]   # H180 P2halfout25
def rep(tag,mask,s=S,fc=None,toll=TOLL):
    for split,nm in ((TR,'train'),(VA,'valid')):
        sel=np.flatnonzero(mask&split&(~CENS[struct_h[s]]))
        if len(sel)<20: p('%-46s %-6s n/a'%(tag,nm)); continue
        r=stats(greedy(sel.tolist(),s),s,fc,toll)
        if r is None: continue
        lo,hi=boot(r['mu'])
        p('%-46s %-6s mean=%7.4f med=%7.4f CI=[%7.4f,%7.4f] n=%5d k=%4d'%(tag,nm,r['mean'],r['med'],lo,hi,r['n'],r['k']))

p('')
p('=== BASELINE (H180 | flowrev.lag1 | P2halfout25) ===')
rep('ubgrow_120>=p75  [baseline]',base)
rep('RANDOM 25% entries [control]',np.isin(np.arange(NDP),rng.choice(NDP,int(NDP*0.25),replace=False)))
p('')
p('=== T1 LEFT-TRUNCATION: is the signal just "our data starts here"? ===')
fh=fullh[DM]==1
rep('ubgrow>=p75 & FULL-HISTORY mints only',base&fh)
rep('ubgrow>=p75 & TRUNCATED-history mints',base&(~fh))
p('')
p('=== T2 AGE: a genuine previous 120s window must exist ===')
age=X[:,FI['age']]
for amin in [0,120,240,600,1800]:
    rep('ubgrow>=p75 & age>=%ds'%amin, base&(age>=amin))
p('')
p('=== T3 THRESHOLD SENSITIVITY (train-fit percentiles) ===')
for pc in [25,50,60,75,90,95,99]:
    q=float(np.percentile(ug[TR][np.isfinite(ug[TR])],pc))
    rep('ubgrow_120>=p%d (=%.2f)'%(pc,q), (ug>=q)&np.isfinite(ug))
p('')
p('=== T4 EXIT STRUCTURE: is the flow-reversal exit load-bearing? ===')
for nmp,sname in [(namesp.index('H180|time|P0'),'H180|time|P0'),
                  (namesp.index('H180|time|P2halfout25'),'H180|time|P2halfout25'),
                  (namesp.index('H600|time|P0'),'H600|time|P0'),
                  (namesp.index('H1800|time|P0'),'H1800|time|P0')]:
    for split,tag in ((TR,'train'),(VA,'valid')):
        sel=np.flatnonzero(base&split&(~CENS[HOR.index(int(sname.split('|')[0][1:]))]))
        eo=EOFFp[nmp].tolist(); keep=[]; curm=-1; free=-1
        for i in sel:
            m=DMl[i]
            if m!=curm: curm=m; free=-1
            if TEl[i]>=free: keep.append(i); free=TEl[i]+eo[i]
        ki=np.asarray(keep); g=RETp[nmp][ki].astype(np.float64)
        net=(1+g)*(1-TOLL)-1
        cnt=np.bincount(DM[ki],minlength=NM); sm=np.bincount(DM[ki],weights=net,minlength=NM)
        nz=cnt>0; mu=sm[nz]/cnt[nz]; lo,hi=boot(mu)
        p('%-46s %-6s mean=%7.4f med=%7.4f CI=[%7.4f,%7.4f] n=%5d k=%4d'%(
          'ubgrow>=p75 -> '+sname,tag,mu.mean(),np.median(mu),lo,hi,len(keep),int(nz.sum())))
p('')
p('=== T5 HORIZON of the flow-reversal cap ===')
for hi_,(H,r) in enumerate(HORIZ):
    for pi,pn in enumerate(POS):
        rep('ubgrow>=p75 -> H%d|flowrev.lag1|%s'%(H,pn), base, sidx[(hi_,pi)])
p('')
p('=== T6 COST + DROPOUT STRESS (validate) ===')
for tag,fc,tl in [('toll 1.14%%, frozen=0',None,0.0114),('toll 2.5%%, frozen=0',None,0.025),
                  ('toll 1.14%%, frozen=-30%%',-0.30,0.0114),('toll 1.14%%, frozen=-50%%',-0.50,0.0114),
                  ('toll 1.14%%, frozen=-100%%',-1.00,0.0114),('toll 2.5%%, frozen=-100%%',-1.00,0.025)]:
    sel=np.flatnonzero(base&VA&(~CENS[1]))
    r=stats(greedy(sel.tolist(),S),S,fc,tl); lo,hi=boot(r['mu'])
    p('%-46s %-6s mean=%7.4f med=%7.4f CI=[%7.4f,%7.4f]'%(tag,'valid',r['mean'],r['med'],lo,hi))
p('')
p('=== T7 CONCENTRATION: drop the top-contributing mints (validate) ===')
sel=np.flatnonzero(base&VA&(~CENS[1])); r=stats(greedy(sel.tolist(),S),S)
mu=r['mu']; o=np.argsort(-mu)
for k in [0,1,2,3,5,10,20]:
    keepm=np.ones(len(mu),bool); keepm[o[:k]]=False
    p('drop top-%2d mints: mean=%7.4f  med=%7.4f  k=%d'%(k,mu[keepm].mean(),np.median(mu[keepm]),keepm.sum()))
p('per-trade net: best=%.3f  p99=%.3f  p50=%.3f  frac>0=%.3f'%(
   r['net'].max(),np.percentile(r['net'],99),np.percentile(r['net'],50),(r['net']>0).mean()))
p('')
p('=== T8 TIME STABILITY: split the 8-day window in half (validate) ===')
tmid=(TE[TE>0].min()+TE.max())//2
p('window midpoint ts=%d'%tmid)
rep('ubgrow>=p75 first half of window', base&(TE<tmid))
rep('ubgrow>=p75 second half of window',base&(TE>=tmid))
p('')
p('=== T9 what does the rule actually select? (validate, selected trades) ===')
ki=r['keep']
for f in ['age','ntot','ub_120','ubgrow_120','prog','rate_120','vimb_120','solincurve']:
    v=X[ki,FI[f]]
    p('  %-12s p10=%9.3g p50=%9.3g p90=%9.3g'%(f,*np.percentile(v,[10,50,90])))
p('  trades per selected mint: median=%.1f'%np.median(np.bincount(DM[ki])[np.bincount(DM[ki])>0]))
out.close()
