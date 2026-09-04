"""Multiplicity calibration: how many SYNTHETIC (pure-noise) entry rules pass the
same train gate and then the same validate gate?  Same harness, same gates, same
grid shape -- only the features are noise with realistic within-mint autocorrelation."""
import sys,time,collections,pickle
sys.path.insert(0,'/home/anont/meme/research/midcap/fv3')
import numpy as np, fvh, common
W='/home/anont/meme/research/midcap/fv3/'
OUT=open(W+'logN.txt','w',buffering=1)
def P(*a): OUT.write(' '.join(str(x) for x in a)+'\n')
T0=time.time()
E=common.build(log=P); greedy,ev=common.make_eval(E)
b=E.b; TRi=E.TRi; VAi=E.VAi; SN=E.SN
BASE={}
for s in SN:
    BASE[(s,'tr')]=ev(TRi,s); BASE[(s,'va')]=ev(VAi,s)
SCREEN=['H5/tpNone/slNone/f1.0','H15/tpNone/slNone/f1.0','H30/tpNone/slNone/f1.0',
        'H15/tp0.3/sl-0.25/f1.0','H60/tp0.3/slNone/f1.0']
MINCL=25; MINN=60; MARGIN=0.03
rng=np.random.default_rng(20260904)
NF=25
NOISE=np.zeros((NF,b.N))
for f in range(NF):
    x=rng.standard_normal(b.N)
    y=np.empty(b.N)
    for i in range(b.nm):
        s0,e0=b.starts[i],b.ends[i]
        v=x[s0:e0]; a=0.0; o=np.empty(e0-s0)
        for t in range(e0-s0):
            a=0.75*a+v[t]; o[t]=a
        y[s0:e0]=o
    NOISE[f]=y
QC=[5,10,20,25,33,50,66,75,80,90,95]
CONDS=[]
for f in range(NF):
    v=NOISE[f][TRi]
    cuts=sorted(set(np.percentile(v,QC).tolist()))
    cand=[]
    for c in cuts:
        cand.append((-np.inf,c)); cand.append((c,np.inf))
    for a in range(len(cuts)):
        for z in range(a+1,len(cuts)): cand.append((cuts[a],cuts[z]))
    keep=[]
    for lo,hi in cand:
        m=(v>=lo)&(v<hi); cnt=int(m.sum()); frac=cnt/TRi.size
        if cnt<250 or frac>0.80: continue
        keep.append((lo,hi,frac))
    keep.sort(key=lambda x:x[2])
    if len(keep)>16:
        step=len(keep)/16.0; keep=[keep[int(j*step)] for j in range(16)]
    for lo,hi,fr in keep: CONDS.append((f,lo,hi))
nC=len(CONDS)
P('noise conditions: %d'%nC)
CTR=np.zeros((nC,TRi.size),bool); CVA=np.zeros((nC,VAi.size),bool)
for ci,(f,lo,hi) in enumerate(CONDS):
    CTR[ci]=(NOISE[f][TRi]>=lo)&(NOISE[f][TRi]<hi)
    CVA[ci]=(NOISE[f][VAi]>=lo)&(NOISE[f][VAi]<hi)
cfeat=np.array([c[0] for c in CONDS])

def train_gate(r,s):
    if r is None or r['clusters']<MINCL or r['n']<MINN: return None
    if not (r['mean']>0 and r['mean']>BASE[(s,'tr')]['mean']+MARGIN): return None
    lo=fvh.boot_lo(r['pm'],B=1500)
    return lo if lo>0 else None

combos=0; keep=[]
for ci in range(nC):
    sig=TRi[CTR[ci]]
    if sig.size<MINN:
        combos+=len(SCREEN); continue
    for s in SCREEN:
        combos+=1
        r=ev(sig,s); lo=train_gate(r,s)
        if lo is not None: keep.append(((ci,),s,r['mean'],lo))
P('1-way noise: combos=%d train-positive=%d  %.1fs'%(combos,len(keep),time.time()-T0))
# sample of 2-way pairs
allpairs=[(a,z) for a in range(nC) for z in range(a+1,nC) if cfeat[a]!=cfeat[z]]
rng2=np.random.default_rng(7)
sel=rng2.choice(len(allpairs),size=min(25000,len(allpairs)),replace=False)
for si in sel:
    a,z=allpairs[si]
    m=CTR[a]&CTR[z]
    if int(m.sum())<MINN:
        combos+=len(SCREEN); continue
    sig=TRi[m]
    for s in SCREEN:
        combos+=1
        r=ev(sig,s); lo=train_gate(r,s)
        if lo is not None: keep.append(((a,z),s,r['mean'],lo))
P('2-way noise (%d pairs sampled): combos=%d train-positive=%d  %.1fs'%(len(sel),combos,len(keep),time.time()-T0))
npass=0
for cc,s,trm,trlo in keep:
    m=CVA[cc[0]]
    for c in cc[1:]: m=m&CVA[c]
    sig=VAi[m]
    if sig.size<40: continue
    r=ev(sig,s,boot=2000)
    if r is None or r['clusters']<20 or r['n']<40: continue
    if r['mean']>0 and r['mean']>BASE[(s,'va')]['mean']+MARGIN and r['lo']>0:
        npass+=1
        P('  NOISE RULE PASSED BOTH GATES: cc=%s %s tr=%+.4f va=%+.4f lo=%+.4f n=%d k=%d'%(
            str(cc),s,trm,r['mean'],r['lo'],r['n'],r['clusters']))
P('NULL CALIBRATION: %d/%d noise rules passed train; %d passed train AND validate (of %d combos swept)'%(
    len(keep),combos,npass,combos))
P('NULL_DONE %.1fs'%(time.time()-T0))
OUT.close()
