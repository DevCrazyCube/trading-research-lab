"""Decisive test: the 4 remaining survivors all use `flowrev`, which observes a bucket's
net flow and fills at THAT SAME bucket's close. Rebuild it with a strict one-bucket lag
(observe bucket j, fill at close of bucket j+1) -- contract A applied to the exit."""
import pickle, time, numpy as np
W='/home/anont/meme/.scratch_feat_flow2'
out=open(W+'/lagflow.txt','w')
def p(*a): print(*a,file=out); out.flush()

d=pickle.load(open(W+'/tapes.pkl','rb')); T=d['T']
Z=np.load(W+'/feats.npz',allow_pickle=True)
X=Z['X']; DM=Z['DM'].astype(np.int64); DK=Z['DK']; hv=Z['hv']; FEATS=list(Z['FEATS']); mints=list(Z['mints'])
O=np.load(W+'/outcomes_pess.npz',allow_pickle=True)
CENS=O['CENS']; TE=O['TE']; HOR=list(O['HORIZ'])
NDP=len(DM); NM=len(mints); GLOBAL_END=1785861735
HORIZ=[(60,5),(180,5),(600,15),(1800,30),(5400,60)]
POS=['P0','P1avgin','P2halfout25']
LAGS=[0,1,2]        # 0 = same bucket (as before), 1 and 2 = strictly lagged fills
NS=len(HORIZ)*len(POS)*len(LAGS)
RET=np.zeros((NS,NDP),dtype=np.float32); EOFF=np.zeros((NS,NDP),dtype=np.int32)
FROZ=np.zeros((len(HORIZ),NDP),dtype=bool)
names=[]; sidx={}; si=0
for hi_,(H,r) in enumerate(HORIZ):
    for li,lag in enumerate(LAGS):
        for pi,pn in enumerate(POS):
            sidx[(hi_,li,pi)]=si; names.append(f'H{H}|flowrev.lag{lag}|{pn}'); si+=1

bounds={}; cur=DM[0]; st=0
for i in range(1,NDP):
    if DM[i]!=cur: bounds[cur]=(st,i); cur=DM[i]; st=i
bounds[cur]=(st,NDP)

t0=time.time()
for mi,(lo_i,hi_i) in bounds.items():
    D=T[mints[mi]]
    bt=D['bt']; vs=D['vs']; vt=D['vt']; sol=D['sol']/1e9; isb=D['isb'].astype(np.float64)
    price=(vs/vt).astype(np.float64); n=len(bt); bt0=bt[0]
    ks=DK[lo_i:hi_i]; te=bt[ks+1].astype(np.int64); pe=price[ks+1]
    signed=sol*(2*isb-1); AR=np.arange(len(ks))
    for hi_,(H,r) in enumerate(HORIZ):
        nb=int(H//r); span=int(bt[-1]-bt0)+H+2*r; B=span//r+2
        bidx=((bt-bt0)//r).astype(np.int64)
        clB=np.full(B,np.nan); flowB=np.zeros(B)
        clB[bidx]=price; np.add.at(flowB,bidx,signed)
        m0=np.isnan(clB)
        if m0[0]: clB[0]=price[0]; m0[0]=False
        idxf=np.where(~m0,np.arange(B),0); np.maximum.accumulate(idxf,out=idxf); clB=clB[idxf]
        wf=max(1,int(60//r)); cf=np.concatenate([[0.],np.cumsum(flowB)])
        flow60=cf[np.arange(B)+1]-cf[np.maximum(np.arange(B)+1-wf,0)]
        traded=np.zeros(B,bool); traded[bidx]=True
        be=((te-bt0)//r).astype(np.int64)
        cols=be[:,None]+1+np.arange(nb)[None,:]
        valid=cols<B; colsC=np.clip(cols,0,B-1)
        PC=np.where(valid,clB[colsC],np.nan); PF=flow60[colsC]
        PT=np.where(valid,traded[colsC],False); frozen=~PT.any(axis=1)
        FROZ[hi_,lo_i:hi_i]=frozen
        lastcol=np.where(valid.any(axis=1),valid.sum(axis=1)-1,0)
        endclose=np.where(np.isnan(PC[AR,lastcol]),pe,PC[AR,lastcol]); endoff=(lastcol+1)*r
        p1entry=np.where(np.isnan(PC[:,0]),pe,PC[:,0])
        mask=(PF<0)&valid
        any_=mask.any(axis=1); first=np.where(any_,mask.argmax(axis=1),nb-1)
        for li,lag in enumerate(LAGS):
            f=np.minimum(first+lag,nb-1)
            v=PC[AR,f]; px=np.where(any_&np.isfinite(v),v,endclose)
            off=np.where(any_,(f+1)*r,endoff)
            g0=np.where(frozen,0.0,px/pe-1.0)
            RET[sidx[(hi_,li,0)],lo_i:hi_i]=g0; EOFF[sidx[(hi_,li,0)],lo_i:hi_i]=off
            g1=np.where(frozen,0.0,0.5*g0+0.5*(px/p1entry-1.0))
            RET[sidx[(hi_,li,1)],lo_i:hi_i]=g1; EOFF[sidx[(hi_,li,1)],lo_i:hi_i]=off
            # half out at +25% (pessimistic: fill at close of the bucket that touched it)
            hiB=np.full(B,-np.inf); np.maximum.at(hiB,bidx,price)
            hiB=np.where(np.isfinite(hiB),hiB,clB)
            PH=np.where(valid,hiB[colsC],-np.inf)
            L=pe*1.25; h2=(PH>=L[:,None]); a2=h2.any(axis=1); f2=np.where(a2,h2.argmax(axis=1),0)
            v2=PC[AR,np.minimum(f2+lag,nb-1)]
            gh=np.where(np.isfinite(v2),v2,endclose)/pe-1.0
            g2=np.where(frozen,0.0,np.where(a2,0.5*gh+0.5*g0,g0))
            RET[sidx[(hi_,li,2)],lo_i:hi_i]=g2; EOFF[sidx[(hi_,li,2)],lo_i:hi_i]=off
RET=np.nan_to_num(RET,nan=0.0,posinf=0.0,neginf=0.0)
p('built %d structures %.0fs'%(NS,time.time()-t0))

hdp=hv[DM]; TR=(hdp==1); VA=(hdp==2); TOLL=0.0114; TOLL2=0.025
struct_h=np.array([HOR.index(int(nm.split('|')[0][1:])) for nm in names])
TEl=TE.tolist(); DMl=DM.tolist(); EOFFl=[EOFF[s].tolist() for s in range(NS)]
rng=np.random.default_rng(99)
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
    return dict(n=len(keep),clusters=int(nz.sum()),mean=float(mu.mean()),median=float(np.median(mu)),mu=mu)
def boot(mu,B=4000):
    k=len(mu); idx=rng.integers(0,k,size=(B,k)); bs=mu[idx].mean(axis=1)
    return float(np.percentile(bs,2.5)),float(np.percentile(bs,97.5)),float((bs<=0).mean())

PCT=[1,5,10,25,75,90,95,99]; cells=[]
for fi,fn in enumerate(FEATS):
    col=X[:,fi]; tr=col[TR]; tr=tr[np.isfinite(tr)]
    for pi,q in zip(PCT,np.percentile(tr,PCT)):
        nm=f'{fn}<=p{pi}' if pi<=25 else f'{fn}>=p{pi}'
        cells.append((nm,((col<=q) if pi<=25 else (col>=q))&np.isfinite(col)))
RATES=[0.005,0.01,0.05,0.10,0.25]
def rb(f): return min(RATES,key=lambda r:abs(r-f))
def ctrls(split):
    base=np.flatnonzero(split); C={}
    for s in range(NS):
        b=base[(~CENS[struct_h[s]])[base]]
        for rt in RATES:
            v=[stats(greedy(b[rng.random(len(b))<rt].tolist(),s),s) for _ in range(3)]
            v=[x['mean'] for x in v if x]; C[(s,rt)]=float(np.mean(v)) if v else 0.0
    return C
CTR=ctrls(TR); CVA=ctrls(VA)
p('controls: same-bucket(lag0) vs lagged random-entry means, H180|P2halfout25 @rate .25:')
for li,lag in enumerate(LAGS):
    s=sidx[(1,li,2)]; p('  lag%d train_ctrl=%.4f  validate_ctrl=%.4f'%(lag,CTR[(s,0.25)],CVA[(s,0.25)]))

p('')
p('%-26s %-30s %8s %8s %8s %8s %8s %6s %5s %8s %8s'%('cell','struct','trmean','vmean','vmed','vCIlo','vCIhi','n','k','ctrl','edge'))
rows=[]
combos=0
for cname,cm in cells:
    for s in range(NS):
        combos+=1
        sel=np.flatnonzero(cm & TR & (~CENS[struct_h[s]]))
        if len(sel)<60: continue
        r=stats(greedy(sel.tolist(),s),s)
        if r is None or r['clusters']<30: continue
        frac=len(sel)/max(1,int((TR&(~CENS[struct_h[s]])).sum()))
        if r['mean']<=0 or r['mean']-CTR[(s,rb(frac))]<=0: continue
        selv=np.flatnonzero(cm & VA & (~CENS[struct_h[s]]))
        if len(selv)<40: continue
        kv=greedy(selv.tolist(),s); rv=stats(kv,s)
        if rv is None or rv['clusters']<20: continue
        lo,hi,pv=boot(rv['mu'])
        fracv=len(selv)/max(1,int((VA&(~CENS[struct_h[s]])).sum()))
        c=CVA[(s,rb(fracv))]
        rows.append(dict(cell=cname,struct=names[s],tr=r['mean'],vm=rv['mean'],vmed=rv['median'],
                         lo=lo,hi=hi,p=pv,n=rv['n'],k=rv['clusters'],ctrl=c,edge=rv['mean']-c,
                         m50=stats(kv,s,-0.50)['mean'],t25=stats(kv,s,None,TOLL2)['mean']))
p('combos swept (lag family): %d ; train-positive+beat-control that reached validate: %d'%(combos,len(rows)))
surv=[r for r in rows if r['vm']>0 and r['lo']>0 and r['edge']>0 and r['m50']>0]
p('SURVIVORS: %d'%len(surv))
for r in sorted(surv,key=lambda r:-r['vm']):
    p('%-26s %-30s %8.4f %8.4f %8.4f %8.4f %8.4f %6d %5d %8.4f %8.4f'%(
      r['cell'],r['struct'],r['tr'],r['vm'],r['vmed'],r['lo'],r['hi'],r['n'],r['k'],r['ctrl'],r['edge']))
p('')
p('--- the 4 stage-A/B survivors, re-run at each lag (H180, P2halfout25) ---')
for cname,cm in cells:
    if cname not in ('ubgrow_120>=p75','ubgrow_600>=p75','ub_120>=p75','bvol_600>=p75'): continue
    for li,lag in enumerate(LAGS):
        s=sidx[(1,li,2)]
        selv=np.flatnonzero(cm & VA & (~CENS[struct_h[s]]))
        kv=greedy(selv.tolist(),s); rv=stats(kv,s)
        if rv is None: continue
        lo,hi,pv=boot(rv['mu'])
        selt=np.flatnonzero(cm & TR & (~CENS[struct_h[s]])); rt=stats(greedy(selt.tolist(),s),s)
        p('%-20s lag%d  train=%7.4f  validate=%7.4f med=%7.4f CI=[%.4f,%.4f] n=%4d k=%3d ctrl=%7.4f'%(
          cname,lag,rt['mean'],rv['mean'],rv['median'],lo,hi,rv['n'],rv['clusters'],CVA[(s,0.25)]))
out.close()
