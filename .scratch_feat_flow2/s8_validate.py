import numpy as np, pickle, time, json
W='/home/anont/meme/.scratch_feat_flow2'
out=open(W+'/validate.txt','w')
def p(*a): print(*a,file=out); out.flush()

Z=np.load(W+'/feats.npz',allow_pickle=True)
X=Z['X']; DM=Z['DM'].astype(np.int64); hv=Z['hv']; FEATS=list(Z['FEATS']); mints=list(Z['mints'])
O=np.load(W+'/outcomes.npz',allow_pickle=True)
RET=O['RET']; EOFF=O['EOFF']; FROZEN=O['FROZEN']; CENS=O['CENS']; names=list(O['names']); TE=O['TE']
HOR=list(O['HORIZ']); NS,NDP=RET.shape; NM=len(mints)
hdp=hv[DM]; TR=(hdp==1); VA=(hdp==2)
TOLL=0.0114; TOLL2=0.025
struct_h=np.array([HOR.index(int(nm.split('|')[0][1:])) for nm in names])
TEl=TE.tolist(); DMl=DM.tolist(); EOFFl=[EOFF[s].tolist() for s in range(NS)]
rng=np.random.default_rng(7)

def greedy(sel,s):
    eo=EOFFl[s]; keep=[]; curm=-1; free=-1
    for i in sel:
        m=DMl[i]
        if m!=curm: curm=m; free=-1
        t=TEl[i]
        if t>=free:
            keep.append(i); free=t+eo[i]
    return keep

def stats(keep,s,frozen_charge=None,toll=TOLL):
    if not keep: return None
    ki=np.asarray(keep); hidx=struct_h[s]
    g=RET[s][ki].astype(np.float64); fz=FROZEN[hidx][ki]
    if frozen_charge is not None: g=np.where(fz,frozen_charge,g)
    net=(1.0+g)*(1.0-toll)-1.0
    mm=DM[ki]; cnt=np.bincount(mm,minlength=NM); sm=np.bincount(mm,weights=net,minlength=NM)
    nz=cnt>0; mu=sm[nz]/cnt[nz]
    return dict(n=len(keep),clusters=int(nz.sum()),mean=float(mu.mean()),
                median=float(np.median(mu)),mu=mu,frozen=float(fz.mean()))

def boot(mu,B=4000):
    k=len(mu)
    idx=rng.integers(0,k,size=(B,k))
    bs=mu[idx].mean(axis=1)
    return float(np.percentile(bs,2.5)),float(np.percentile(bs,97.5)),float((bs<=0).mean())

PCT=[1,5,10,25,75,90,95,99]
cells=[]
for fi,fn in enumerate(FEATS):
    col=X[:,fi]; tr=col[TR]; tr=tr[np.isfinite(tr)]
    qs=np.percentile(tr,PCT)
    for pi,q in zip(PCT,qs):
        cells.append((f'{fn}<=p{pi}' if pi<=25 else f'{fn}>=p{pi}', fi, 'lo' if pi<=25 else 'hi', float(q)))
cellmap={c[0]:c for c in cells}
def cellmask(fi,dirn,q):
    col=X[:,fi]; return ((col<=q) if dirn=='lo' else (col>=q)) & np.isfinite(col)

strict=pickle.load(open(W+'/stageA_strict.pkl','rb'))
p('stage-A strict survivors (train-positive, frozen@-50 positive, beat random):',len(strict))

# ---- validate random controls ----
RATES=[0.01,0.05,0.10,0.25]
base_va=np.flatnonzero(VA)
ctrlV={}
t0=time.time()
need=sorted(set(z[1] for z in strict))
p('structures needing validate control:',len(need))
for s in need:
    ok=~CENS[struct_h[s]]; b=base_va[ok[base_va]]
    for rt in RATES:
        vals=[]
        for rep in range(3):
            pick=b[rng.random(len(b))<rt]
            r=stats(greedy(pick.tolist(),s),s)
            if r: vals.append(r['mean'])
        ctrlV[(s,rt)]=float(np.mean(vals)) if vals else 0.0
p('validate controls %.0fs'%(time.time()-t0))
def rb(f): return min(RATES,key=lambda r:abs(r-f))

rowsV=[]
t0=time.time()
for j,z in enumerate(strict):
    cname,s = z[0],z[1]
    _,fi,dirn,q = cellmap[cname]
    m = cellmask(fi,dirn,q) & VA & (~CENS[struct_h[s]])
    sel=np.flatnonzero(m)
    if len(sel)<40: continue
    keep=greedy(sel.tolist(),s)
    r=stats(keep,s)
    if r is None or r['clusters']<20: continue
    lo,hi,pv=boot(r['mu'])
    r30=stats(keep,s,-0.30); r50=stats(keep,s,-0.50); r100=stats(keep,s,-1.00)
    r25=stats(keep,s,None,TOLL2)
    frac=len(sel)/max(1,int((VA&(~CENS[struct_h[s]])).sum()))
    c=ctrlV[(s,rb(frac))]
    rowsV.append(dict(cell=cname,s=int(s),struct=names[s],
        train_mean=z[2],train_med=z[3],
        v_mean=r['mean'],v_med=r['median'],v_lo=lo,v_hi=hi,p=pv,
        v_n=r['n'],v_k=r['clusters'],v_frozen=r['frozen'],
        v_m30=r30['mean'],v_m50=r50['mean'],v_m100=r100['mean'],v_toll25=r25['mean'],
        ctrl=c,edge=r['mean']-c))
    if j%200==0: p('validated %d/%d %.0fs'%(j,len(strict),time.time()-t0))
p('validate evaluated',len(rowsV),'%.0fs'%(time.time()-t0))

# Benjamini-Hochberg over all validated candidates
if rowsV:
    pv=np.array([r['p'] for r in rowsV]); order=np.argsort(pv); mtot=len(pv)
    thr=np.zeros(mtot,dtype=bool); crit=0.10
    sortedp=pv[order]; ok=sortedp<= (np.arange(1,mtot+1)/mtot)*crit
    if ok.any():
        kmax=np.max(np.flatnonzero(ok)); thr[order[:kmax+1]]=True
    for i,r in enumerate(rowsV): r['bh10']=bool(thr[i])
    p('BH(q=0.10) passers:',int(thr.sum()),'of',mtot)

surv=[r for r in rowsV if r['v_mean']>0 and r['v_lo']>0 and r['edge']>0 and r['v_m50']>0]
p('SURVIVORS (validate mean>0, boot CI-lo>0, beats validate random control, frozen@-50 positive):',len(surv))
surv=sorted(surv,key=lambda r:-r['v_mean'])
p('%-26s %-32s %8s %8s %8s %8s %8s %6s %5s %8s %8s %5s'%(
   'cell','struct','trmean','vmean','vmed','vCIlo','vCIhi','n','k','ctrl','edge','BH'))
for r in surv[:60]:
    p('%-26s %-32s %8.4f %8.4f %8.4f %8.4f %8.4f %6d %5d %8.4f %8.4f %5s'%(
      r['cell'],r['struct'],r['train_mean'],r['v_mean'],r['v_med'],r['v_lo'],r['v_hi'],
      r['v_n'],r['v_k'],r['ctrl'],r['edge'],r.get('bh10')))
pickle.dump(rowsV,open(W+'/validated.pkl','wb'))
p('--- all validated rows saved ---')
p('validate-positive count (mean>0 only):',sum(1 for r in rowsV if r['v_mean']>0),'of',len(rowsV))
out.close()
