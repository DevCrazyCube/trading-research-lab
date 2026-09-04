import sys,os,json,time,itertools,math,pickle,collections
sys.path.insert(0,'/home/anont/meme/research/midcap/fv3')
import numpy as np
import fvh

W='/home/anont/meme/research/midcap/fv3/'
OUT=open(W+'log2.txt','w',buffering=1)
def P(*a):
    OUT.write(' '.join(str(x) for x in a)+'\n')

T0=time.time()
mints,arrs,meta=fvh.load(minbars=22)
b=fvh.Book(mints,arrs,meta)
P('mints',b.nm,'bars',b.N,'load %.1f'%(time.time()-T0))
P('hash',dict(collections.Counter(b.hh.tolist())))

eps=1e-300
N=b.N
rng_abs=b.HI-b.LO
rng_pc=rng_abs/np.maximum(b.C,eps)
typ=(b.HI+b.LO+b.C)/3.0
clv=np.where(rng_abs>0,(b.C-b.LO)/np.maximum(rng_abs,eps),0.5)

medV5  = fvh.roll_med(b.V,b,5,1)
medV20 = fvh.roll_med(b.V,b,20,1)
medV5_0= fvh.roll_med(b.V,b,5,0)
medV15_5=fvh.roll_med(b.V,b,15,5)
medR10 = fvh.roll_med(rng_pc,b,10,1)
sumV5  = fvh.roll_sum(b.V,b,5,0)
sumV20 = fvh.roll_sum(b.V,b,20,0)
sumTV5 = fvh.roll_sum(typ*b.V,b,5,0)
sumTV20= fvh.roll_sum(typ*b.V,b,20,0)
sumHL5 = fvh.roll_sum(rng_abs,b,5,0)
sumCLV5= fvh.roll_sum(clv,b,5,0)
C1=fvh.lag(b.C,b,1); C5=fvh.lag(b.C,b,5); C10=fvh.lag(b.C,b,10)
TS1=fvh.lag(b.TS,b,1)
gap1=(b.TS-TS1)/60.0
sumGAP5=fvh.roll_sum(np.nan_to_num(gap1,nan=1.0),b,5,0)
up=(b.C>C1).astype(float)
sumUP10=fvh.roll_sum(np.nan_to_num(up,nan=0.0),b,10,0)
absr=np.abs(b.C/np.maximum(C1,eps)-1.0)
sumABS5=fvh.roll_sum(np.nan_to_num(absr,nan=0.0),b,5,0)
rmaxC=fvh.runmax(b.C,b)

F=collections.OrderedDict()
F['vrel5']  = b.V/np.maximum(medV5,eps)
F['vrel20'] = b.V/np.maximum(medV20,eps)
F['vacc']   = medV5_0/np.maximum(medV15_5,eps)
F['vshare'] = b.V/np.maximum(sumV20,eps)
F['vsol5']  = sumV5
F['vsol1']  = b.V
F['rngrel'] = rng_pc/np.maximum(medR10,eps)
F['rngpc']  = rng_pc
F['dens10'] = fvh.density(b,10)
F['dens30'] = fvh.density(b,30)
F['gap']    = gap1
F['gapavg5']= sumGAP5/5.0
F['eff5']   = np.abs(b.C-C5)/np.maximum(sumHL5,eps)
F['hlcc']   = rng_abs/np.maximum(np.abs(b.C-C1),eps)
F['vwdev5'] = b.C/np.maximum(sumTV5/np.maximum(sumV5,eps),eps)-1.0
F['vwdev20']= b.C/np.maximum(sumTV20/np.maximum(sumV20,eps),eps)-1.0
F['clv']    = clv
F['clv5']   = sumCLV5/5.0
F['upfrac'] = sumUP10/10.0
F['illiq']  = sumABS5/np.maximum(sumV5,eps)
F['age']    = (b.TS-b.btime[b.MID])/60.0
F['mcap']   = b.C*1e9
F['dd']     = b.C/np.maximum(rmaxC,eps)
F['ret5']   = b.C/np.maximum(C5,eps)-1.0
F['ret10']  = b.C/np.maximum(C10,eps)-1.0

FN=list(F.keys()); nf=len(FN)
Fm=np.vstack([F[k] for k in FN])

elig=np.ones(N,bool)
elig &= (b.idx>=21)
elig &= (np.arange(N)+1) < b.ends[b.MID]
elig &= np.all(np.isfinite(Fm),axis=0)
TR = elig & (b.mhh==1); VA = elig & (b.mhh==2)
TRi=np.flatnonzero(TR); VAi=np.flatnonzero(VA)
P('eligible %d  train bars %d (%d mints)  valid bars %d (%d mints)'%(
    int(elig.sum()),TRi.size,len(set(b.MID[TRi].tolist())),VAi.size,len(set(b.MID[VAi].tolist()))))

QC=[5,10,20,25,33,50,66,75,80,90,95]
CONDS=[]
ntr=TRi.size
for i in range(nf):
    v=Fm[i][TRi]
    cuts=sorted(set(np.percentile(v,QC).tolist()))
    cand=[]
    for c in cuts:
        cand.append((-np.inf,c,'<%.4g'%c)); cand.append((c,np.inf,'>=%.4g'%c))
    for a in range(len(cuts)):
        for z in range(a+1,len(cuts)):
            cand.append((cuts[a],cuts[z],'[%.4g,%.4g)'%(cuts[a],cuts[z])))
    keep=[];seen=set()
    for lo,hi,lab in cand:
        m=(v>=lo)&(v<hi); cnt=int(m.sum()); frac=cnt/ntr
        if cnt<250 or frac>0.80: continue
        h=hash(m.tobytes())
        if h in seen: continue
        seen.add(h); keep.append((lo,hi,lab,frac))
    keep.sort(key=lambda x:x[3])
    if len(keep)>16:
        step=len(keep)/16.0
        keep=[keep[int(j*step)] for j in range(16)]
    for lo,hi,lab,frac in keep:
        CONDS.append((i,lo,hi,'%s%s'%(FN[i],lab)))
nC=len(CONDS)
P('conditions built: %d over %d features'%(nC,nf))
CTR=np.zeros((nC,TRi.size),bool); CVA=np.zeros((nC,VAi.size),bool)
for ci,(fi,lo,hi,lab) in enumerate(CONDS):
    CTR[ci]=(Fm[fi][TRi]>=lo)&(Fm[fi][TRi]<hi)
    CVA[ci]=(Fm[fi][VAi]>=lo)&(Fm[fi][VAi]<hi)
cfeat=np.array([c[0] for c in CONDS])

MIDl=b.MID.tolist(); ENDl=b.ends.tolist()
def greedy_fast(sig,klist):
    taken=[]; cur=-1; nxt=-1
    for i in sig:
        m=MIDl[i]
        if m!=cur: cur=m; nxt=-1
        if i<nxt: continue
        j=i+1; e=ENDl[m]
        if j>=e: continue
        taken.append(j)
        kk=klist[j]
        nxt = kk if kk>=0 else e+1
    return taken

HOLDS=[5,10,15,30,60]
EXITS=[(None,None,1.0),(0.15,None,1.0),(0.30,None,1.0),(0.60,None,1.0),(None,-0.25,1.0),
       (0.15,-0.25,1.0),(0.30,-0.25,1.0),(0.30,-0.40,1.0),(0.60,-0.40,1.0),
       (0.15,-0.25,0.5),(0.30,-0.25,0.5),(0.60,-0.30,0.5)]
TOLL=0.0114; TOLL2=0.025; DROPS=[-0.30,-0.50,-1.00]
PRIMARY=(-0.30,TOLL)
STRUCT=collections.OrderedDict()
for H in HOLDS:
    k=fvh.build_exit(b,H); mw=min(H+1,65)
    Rmax,Rmin,L=fvh.path_ext(b,k,mw); klist=k.tolist()
    for (tp,sl,fr) in EXITS:
        g=fvh.gross(b,k,Rmax,Rmin,L,tp=tp,sl=sl,tp_frac=fr)
        nm='H%d/tp%s/sl%s/f%s'%(H,tp,sl,fr)
        nets={}
        for d in DROPS: nets[(d,TOLL)]=fvh.netify(g,k,TOLL,d)
        nets[(-0.30,TOLL2)]=fvh.netify(g,k,TOLL2,-0.30)
        STRUCT[nm]=dict(k=klist,karr=k,nets=nets,H=H,tp=tp,sl=sl,fr=fr)
    del Rmax,Rmin,L
SN=list(STRUCT.keys())
P('structures: %d  (%.1fs)'%(len(SN),time.time()-T0))

MIDa=b.MID
def ev_idx(sig,sname,key=PRIMARY,boot=0):
    """sig: global bar indices, ascending."""
    st=STRUCT[sname]
    js=greedy_fast(sig.tolist() if hasattr(sig,'tolist') else sig,st['k'])
    if not js: return None
    js=np.asarray(js,dtype=np.int64)
    r=st['nets'][key][js]; mid=MIDa[js]
    u,inv=np.unique(mid,return_inverse=True)
    pm=np.bincount(inv,weights=r)/np.bincount(inv)
    d=dict(n=int(js.size),clusters=int(u.size),mean=float(pm.mean()),
           median=float(np.median(pm)),res=float((st['karr'][js]>=0).mean()),pm=pm)
    if boot: d['lo']=fvh.boot_lo(pm,B=boot)
    return d

BASE={}
for sname in SN:
    BASE[(sname,'tr')]=ev_idx(TRi,sname,boot=2000)
    BASE[(sname,'va')]=ev_idx(VAi,sname,boot=2000)
P('\n=== unconditional baselines (all eligible bars) ===')
for sname in SN:
    a=BASE[(sname,'tr')]; c=BASE[(sname,'va')]
    P('BASE %-22s tr mean=%+.4f med=%+.4f n=%5d k=%3d | va mean=%+.4f med=%+.4f n=%5d k=%3d res=%.3f'%(
        sname,a['mean'],a['median'],a['n'],a['clusters'],c['mean'],c['median'],c['n'],c['clusters'],c['res']))

SCREEN=['H5/tpNone/slNone/f1.0','H15/tpNone/slNone/f1.0','H30/tpNone/slNone/f1.0',
        'H15/tp0.3/sl-0.25/f1.0','H60/tp0.3/slNone/f1.0']
MINCL=25; MINN=60; MARGIN=0.03
combos=0; keep=[]
t=time.time()
for ci in range(nC):
    sig=TRi[CTR[ci]]
    if sig.size<MINN:
        combos+=len(SCREEN); continue
    for sname in SCREEN:
        combos+=1
        r=ev_idx(sig,sname)
        if r is None or r['clusters']<MINCL or r['n']<MINN: continue
        if r['mean']>0 and r['mean']>BASE[(sname,'tr')]['mean']+MARGIN:
            lo=fvh.boot_lo(r['pm'],B=1500)
            if lo>0: keep.append(((ci,),sname,r['mean'],r['median'],r['n'],r['clusters'],lo))
P('  1-way %d conds done %.1fs keep=%d'%(nC,time.time()-t,len(keep)))

t=time.time(); npair=0
for a in range(nC):
    ma=CTR[a]
    if ma.sum()<MINN: continue
    fa=cfeat[a]
    for z in range(a+1,nC):
        if cfeat[z]==fa: continue
        npair+=1
        m=ma&CTR[z]
        cnt=int(m.sum())
        if cnt<MINN:
            combos+=len(SCREEN); continue
        sig=TRi[m]
        for sname in SCREEN:
            combos+=1
            r=ev_idx(sig,sname)
            if r is None or r['clusters']<MINCL or r['n']<MINN: continue
            if r['mean']>0 and r['mean']>BASE[(sname,'tr')]['mean']+MARGIN:
                lo=fvh.boot_lo(r['pm'],B=1500)
                if lo>0: keep.append(((a,z),sname,r['mean'],r['median'],r['n'],r['clusters'],lo))
P('  2-way %d pairs done %.1fs  combos=%d  train-positive=%d'%(npair,time.time()-t,combos,len(keep)))

keep.sort(key=lambda x:-x[6])
P('\ntop 60 train survivors (by bootstrap CI-lo):')
for r in keep[:60]:
    cc,sname,mn,md,n,k,lo=r
    P('  B %-58s %-22s mean=%+.4f lo=%+.4f med=%+.4f n=%d k=%d'%(
        ' & '.join(CONDS[c][3] for c in cc),sname,mn,lo,md,n,k))
pickle.dump(dict(keep=keep,CONDS=CONDS,FN=FN,combos=combos,SCREEN=SCREEN),open(W+'stageB.pkl','wb'))
P('STAGE_B_DONE combos=%d  %.1fs'%(combos,time.time()-T0))
OUT.close()
