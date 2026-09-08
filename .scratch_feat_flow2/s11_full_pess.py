import numpy as np, pickle, time, itertools, json
W='/home/anont/meme/.scratch_feat_flow2'
out=open(W+'/pess_full.txt','w')
def p(*a): print(*a,file=out); out.flush()

Z=np.load(W+'/feats.npz',allow_pickle=True)
X=Z['X']; DM=Z['DM'].astype(np.int64); hv=Z['hv']; FEATS=list(Z['FEATS']); mints=list(Z['mints'])
O=np.load(W+'/outcomes_pess.npz',allow_pickle=True)
RET=O['RET']; EOFF=O['EOFF']; FROZEN=O['FROZEN']; CENS=O['CENS']; names=list(O['names']); TE=O['TE']
HOR=list(O['HORIZ']); NS,NDP=RET.shape; NM=len(mints)
hdp=hv[DM]; TR=(hdp==1); VA=(hdp==2)
TOLL=0.0114; TOLL2=0.025
struct_h=np.array([HOR.index(int(nm.split('|')[0][1:])) for nm in names])
TEl=TE.tolist(); DMl=DM.tolist(); EOFFl=[EOFF[s].tolist() for s in range(NS)]
rng=np.random.default_rng(1234)
p('PESSIMISTIC-FILL ENGINE. NS=%d NDP=%d train=%d validate=%d'%(NS,NDP,TR.sum(),VA.sum()))

def greedy(sel,s):
    eo=EOFFl[s]; keep=[]; curm=-1; free=-1
    for i in sel:
        m=DMl[i]
        if m!=curm: curm=m; free=-1
        t=TEl[i]
        if t>=free:
            keep.append(i); free=t+eo[i]
    return keep
def stats(keep,s,fc=None,toll=TOLL):
    if not keep: return None
    ki=np.asarray(keep); hidx=struct_h[s]
    g=RET[s][ki].astype(np.float64); fz=FROZEN[hidx][ki]
    if fc is not None: g=np.where(fz,fc,g)
    net=(1.0+g)*(1.0-toll)-1.0
    mm=DM[ki]; cnt=np.bincount(mm,minlength=NM); sm=np.bincount(mm,weights=net,minlength=NM)
    nz=cnt>0; mu=sm[nz]/cnt[nz]
    return dict(n=len(keep),clusters=int(nz.sum()),mean=float(mu.mean()),
                median=float(np.median(mu)),mu=mu,frozen=float(fz.mean()))
def boot(mu,B=4000):
    k=len(mu); idx=rng.integers(0,k,size=(B,k)); bs=mu[idx].mean(axis=1)
    return float(np.percentile(bs,2.5)),float(np.percentile(bs,97.5)),float((bs<=0).mean())

PCT=[1,5,10,25,75,90,95,99]
cells=[]
for fi,fn in enumerate(FEATS):
    col=X[:,fi]; tr=col[TR]; tr=tr[np.isfinite(tr)]
    qs=np.percentile(tr,PCT)
    for pi,q in zip(PCT,qs):
        cells.append((f'{fn}<=p{pi}' if pi<=25 else f'{fn}>=p{pi}', fi, 'lo' if pi<=25 else 'hi', float(q)))
def cmask(fi,dirn,q):
    col=X[:,fi]; return ((col<=q) if dirn=='lo' else (col>=q)) & np.isfinite(col)
CM={c[0]:cmask(c[1],c[2],c[3]) for c in cells}
p('entry cells',len(cells),'STAGE-A combos',len(cells)*NS)

RATES=[0.005,0.01,0.05,0.10,0.25]
def rb(f): return min(RATES,key=lambda r:abs(r-f))
def controls(split):
    base=np.flatnonzero(split); C={}
    for s in range(NS):
        ok=~CENS[struct_h[s]]; b=base[ok[base]]
        for rt in RATES:
            v=[]
            for _ in range(3):
                pick=b[rng.random(len(b))<rt]
                r=stats(greedy(pick.tolist(),s),s)
                if r: v.append(r['mean'])
            C[(s,rt)]=float(np.mean(v)) if v else 0.0
    return C
t0=time.time(); CTR=controls(TR); p('train controls %.0fs'%(time.time()-t0))
t0=time.time(); CVA=controls(VA); p('validate controls %.0fs'%(time.time()-t0))

def sweep(maskdict, split, C, minn=60, mink=30):
    res=[]; tot=int(split.sum())
    for cname,cm in maskdict.items():
        for s in range(NS):
            hidx=struct_h[s]
            sel=np.flatnonzero(cm & split & (~CENS[hidx]))
            if len(sel)<minn: continue
            r=stats(greedy(sel.tolist(),s),s)
            if r is None or r['clusters']<mink or r['n']<minn: continue
            rs=stats(greedy(sel.tolist(),s),s,-0.50)
            frac=len(sel)/max(1,int((split&(~CENS[hidx])).sum()))
            c=C[(s,rb(frac))]
            res.append(dict(cell=cname,s=int(s),mean=r['mean'],med=r['median'],
                            fz50=rs['mean'],n=r['n'],k=r['clusters'],ctrl=c,edge=r['mean']-c,
                            frozen=r['frozen']))
    return res

t0=time.time()
A=sweep(CM,TR,CTR)
p('STAGE-A(pess) rows=%d  %.0fs'%(len(A),time.time()-t0))
posA=[z for z in A if z['mean']>0]
strictA=[z for z in A if z['mean']>0 and z['fz50']>0 and z['edge']>0]
p('train mean>0: %d   strict(train>0,fz50>0,beats control): %d'%(len(posA),len(strictA)))
pickle.dump(A,open(W+'/pessA.pkl','wb'))

def validate(cands, maskdict):
    rows=[]
    for z in cands:
        s=z['s']; cm=maskdict[z['cell']]
        sel=np.flatnonzero(cm & VA & (~CENS[struct_h[s]]))
        if len(sel)<40: continue
        keep=greedy(sel.tolist(),s); r=stats(keep,s)
        if r is None or r['clusters']<20: continue
        lo,hi,pv=boot(r['mu'])
        frac=len(sel)/max(1,int((VA&(~CENS[struct_h[s]])).sum()))
        c=CVA[(s,rb(frac))]
        rows.append(dict(cell=z['cell'],s=s,struct=names[s],tr_mean=z['mean'],tr_med=z['med'],tr_n=z['n'],tr_k=z['k'],
            v_mean=r['mean'],v_med=r['median'],v_lo=lo,v_hi=hi,p=pv,v_n=r['n'],v_k=r['clusters'],
            v_fz=r['frozen'],
            v_m30=stats(keep,s,-0.30)['mean'],v_m50=stats(keep,s,-0.50)['mean'],
            v_m100=stats(keep,s,-1.00)['mean'],v_t25=stats(keep,s,None,TOLL2)['mean'],
            ctrl=c,edge=r['mean']-c))
    return rows

t0=time.time(); V=validate(strictA,CM); p('validated %d  %.0fs'%(len(V),time.time()-t0))
if V:
    pv=np.array([r['p'] for r in V]); o=np.argsort(pv); m=len(pv)
    ok=pv[o]<=(np.arange(1,m+1)/m)*0.10
    bh=np.zeros(m,bool)
    if ok.any(): bh[o[:np.max(np.flatnonzero(ok))+1]]=True
    for i,r in enumerate(V): r['bh10']=bool(bh[i])
    p('BH(q=.10) passers %d / %d'%(int(bh.sum()),m))
SURV=[r for r in V if r['v_mean']>0 and r['v_lo']>0 and r['edge']>0 and r['v_m50']>0]
p('=== STAGE-A/B SURVIVORS (pessimistic fills): %d ==='%len(SURV))
hdr='%-26s %-30s %8s %8s %8s %8s %8s %6s %5s %8s %8s %8s %6s'%('cell','struct','trmean','vmean','vmed','vCIlo','vCIhi','n','k','ctrl','edge','t2.5%','BH')
p(hdr)
for r in sorted(SURV,key=lambda r:-r['v_mean'])[:50]:
    p('%-26s %-30s %8.4f %8.4f %8.4f %8.4f %8.4f %6d %5d %8.4f %8.4f %8.4f %6s'%(
      r['cell'],r['struct'],r['tr_mean'],r['v_mean'],r['v_med'],r['v_lo'],r['v_hi'],r['v_n'],r['v_k'],
      r['ctrl'],r['edge'],r['v_t25'],r.get('bh10')))
pickle.dump(V,open(W+'/pessV.pkl','wb'))

# breakdown of the response surface under pessimistic fills
from collections import defaultdict
agg=defaultdict(list)
for z in A:
    nm=names[z['s']].split('|')
    agg[('H',nm[0])].append(z['mean']); agg[('exit',nm[1])].append(z['mean']); agg[('pos',nm[2])].append(z['mean'])
    agg[('feat',z['cell'].split('<=')[0].split('>=')[0])].append(z['mean'])
p('')
p('--- pessimistic TRAIN surface by axis ---')
for k in sorted(agg,key=lambda k:(k[0],-np.mean(agg[k]))):
    v=np.array(agg[k]); p('%-5s %-20s n=%5d mean=%7.4f med=%7.4f frac>0=%.3f'%(k[0],k[1],len(v),v.mean(),np.median(v),(v>0).mean()))

# ---------------- STAGE C: 2-way conjunctions on the best marginals ----------------
featscore=defaultdict(list)
for z in A: featscore[z['cell']].append(z['mean'])
best=sorted(featscore, key=lambda c:-np.mean(featscore[c]))[:26]
p('')
p('STAGE-C base cells (top-26 marginals):'); p(', '.join(best))
strs=sorted(range(NS), key=lambda s:-np.mean([z['mean'] for z in A if z['s']==s] or [-9]))[:45]
CJ={}
for a,b in itertools.combinations(best,2):
    fa=a.split('<=')[0].split('>=')[0]; fb=b.split('<=')[0].split('>=')[0]
    if fa==fb: continue
    CJ[a+' & '+b]=CM[a]&CM[b]
p('STAGE-C conjunction cells %d  x structures %d = %d combos'%(len(CJ),len(strs),len(CJ)*len(strs)))
t0=time.time()
Ac=[]
tot=int(TR.sum())
for cname,cm in CJ.items():
    for s in strs:
        hidx=struct_h[s]
        sel=np.flatnonzero(cm & TR & (~CENS[hidx]))
        if len(sel)<60: continue
        r=stats(greedy(sel.tolist(),s),s)
        if r is None or r['clusters']<30 or r['n']<60: continue
        rs=stats(greedy(sel.tolist(),s),s,-0.50)
        frac=len(sel)/max(1,int((TR&(~CENS[hidx])).sum()))
        c=CTR[(s,rb(frac))]
        Ac.append(dict(cell=cname,s=int(s),mean=r['mean'],med=r['median'],fz50=rs['mean'],
                       n=r['n'],k=r['clusters'],ctrl=c,edge=r['mean']-c,frozen=r['frozen']))
p('STAGE-C train rows %d %.0fs'%(len(Ac),time.time()-t0))
strictC=[z for z in Ac if z['mean']>0 and z['fz50']>0 and z['edge']>0]
p('STAGE-C strict train survivors',len(strictC))
Vc=validate(strictC,CJ)
if Vc:
    pv=np.array([r['p'] for r in Vc]); o=np.argsort(pv); m=len(pv)
    ok=pv[o]<=(np.arange(1,m+1)/m)*0.10
    bh=np.zeros(m,bool)
    if ok.any(): bh[o[:np.max(np.flatnonzero(ok))+1]]=True
    for i,r in enumerate(Vc): r['bh10']=bool(bh[i])
SURVC=[r for r in Vc if r['v_mean']>0 and r['v_lo']>0 and r['edge']>0 and r['v_m50']>0]
p('=== STAGE-C SURVIVORS: %d of %d validated ==='%(len(SURVC),len(Vc)))
p(hdr)
for r in sorted(SURVC,key=lambda r:-r['v_mean'])[:40]:
    p('%-26s %-30s %8.4f %8.4f %8.4f %8.4f %8.4f %6d %5d %8.4f %8.4f %8.4f %6s'%(
      r['cell'][:26],r['struct'],r['tr_mean'],r['v_mean'],r['v_med'],r['v_lo'],r['v_hi'],r['v_n'],r['v_k'],
      r['ctrl'],r['edge'],r['v_t25'],r.get('bh10')))
pickle.dump(Vc,open(W+'/pessVc.pkl','wb'))
p('')
p('TOTAL COMBOS SWEPT (pessimistic): stageA=%d stageC=%d  (plus optimistic-fill stageA=%d)'%(
   len(cells)*NS, len(CJ)*len(strs), len(cells)*NS))
out.close()
