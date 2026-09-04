import sys,os,json,time,math,pickle,collections
sys.path.insert(0,'/home/anont/meme/research/midcap/fv3')
import numpy as np
import fvh, common

W='/home/anont/meme/research/midcap/fv3/'
OUT=open(W+'log3.txt','w',buffering=1)
def P(*a): OUT.write(' '.join(str(x) for x in a)+'\n')

T0=time.time()
E=common.build(log=P)
greedy,ev=common.make_eval(E)
b=E.b; TRi=E.TRi; VAi=E.VAi; SN=E.SN; FN=E.FN
PRIMARY=common.PRIMARY; TOLL=common.TOLL; TOLL2=common.TOLL2

B=pickle.load(open(W+'stageB.pkl','rb'))
CONDS=B['CONDS']; keepB=B['keep']; combos=B['combos']
P('stageB: %d train-positive rows, combos so far %d'%(len(keepB),combos))

def mk(ci,idxs):
    fi,lo,hi,lab=CONDS[ci]
    v=E.Fm[fi][idxs]
    return (v>=lo)&(v<hi)
CTR={}; CVA={}
def ctr(ci):
    if ci not in CTR: CTR[ci]=mk(ci,TRi)
    return CTR[ci]
def cva(ci):
    if ci not in CVA: CVA[ci]=mk(ci,VAi)
    return CVA[ci]

BASE={}
for s in SN:
    BASE[(s,'tr')]=ev(TRi,s,boot=2000); BASE[(s,'va')]=ev(VAi,s,boot=2000)

MINCL=25; MINN=60; MARGIN=0.03
def train_gate(r,s):
    if r is None or r['clusters']<MINCL or r['n']<MINN: return None
    if not (r['mean']>0 and r['mean']>BASE[(s,'tr')]['mean']+MARGIN): return None
    lo=fvh.boot_lo(r['pm'],B=1500)
    return lo if lo>0 else None

# ---------- STAGE C1: expand unique train-positive entries over ALL 60 structures ----------
uniq=sorted(set(tuple(r[0]) for r in keepB))
P('\nSTAGE C1: %d unique train-positive entry conditions x %d structures = %d evals'%(len(uniq),len(SN),len(uniq)*len(SN)))
c1=[]
for cc in uniq:
    m=ctr(cc[0])
    for c in cc[1:]: m=m&ctr(c)
    sig=TRi[m]
    if sig.size<MINN:
        combos+=len(SN); continue
    for s in SN:
        combos+=1
        r=ev(sig,s)
        lo=train_gate(r,s)
        if lo is not None:
            c1.append((cc,s,r['mean'],r['median'],r['n'],r['clusters'],lo))
P('  C1 train-positive=%d  combos=%d  %.1fs'%(len(c1),combos,time.time()-T0))

# ---------- STAGE C2: 3-way = top C1 entries x metadata conditions ----------
METAF=set(['age','mcap','dd','ret5','ret10'])
meta_ci=[i for i,(fi,lo,hi,lab) in enumerate(CONDS) if FN[fi] in METAF]
c1s=sorted(c1,key=lambda x:-x[6])
seen=set(); topent=[]
for r in c1s:
    if r[0] in seen: continue
    seen.add(r[0]); topent.append(r[0])
    if len(topent)>=250: break
SCREEN=B.get('SCREEN',SN[:5])
P('\nSTAGE C2: %d top entries x %d meta conds x %d structures = %d evals'%(
    len(topent),len(meta_ci),len(SCREEN),len(topent)*len(meta_ci)*len(SCREEN)))
c2=[]
for cc in topent:
    m0=ctr(cc[0])
    for c in cc[1:]: m0=m0&ctr(c)
    for mc in meta_ci:
        if any(CONDS[c][0]==CONDS[mc][0] for c in cc):
            combos+=len(SCREEN); continue
        m=m0&ctr(mc)
        sig=TRi[m]
        if sig.size<MINN:
            combos+=len(SCREEN); continue
        cc3=tuple(sorted(cc+(mc,)))
        for s in SCREEN:
            combos+=1
            r=ev(sig,s)
            lo=train_gate(r,s)
            if lo is not None:
                c2.append((cc3,s,r['mean'],r['median'],r['n'],r['clusters'],lo))
P('  C2 train-positive=%d  combos=%d  %.1fs'%(len(c2),combos,time.time()-T0))

ALLTR=c1+c2
P('\nTOTAL train-positive rules: %d   TOTAL combos swept: %d'%(len(ALLTR),combos))
pickle.dump(dict(ALLTR=ALLTR,combos=combos,CONDS=CONDS),open(W+'stageC.pkl','wb'))

# ---------- VALIDATE ----------
def lbl(cc): return ' & '.join(CONDS[c][3] for c in cc)
P('\n=== VALIDATE (mints with md5%%3==2, never used to pick) ===')
surv=[]
ALLTR.sort(key=lambda x:-x[6])
nval=0
for cc,s,trm,trmd,trn,trk,trlo in ALLTR:
    m=cva(cc[0])
    for c in cc[1:]: m=m&cva(c)
    sig=VAi[m]
    nval+=1
    if sig.size<40: continue
    r=ev(sig,s,boot=2000)
    if r is None or r['clusters']<20 or r['n']<40: continue
    passed = (r['mean']>0) and (r['mean']>BASE[(s,'va')]['mean']+MARGIN) and (r['lo']>0)
    if passed:
        surv.append((cc,s,trm,r))
P('validated %d train-positive rules; %d passed validate'%(nval,len(surv)))
rng=np.random.default_rng(4242)
def rand_control(nsig,s,reps=200):
    """same structure, same number of signal bars, drawn uniformly from validate-eligible bars."""
    ms=[]
    pool=VAi
    for _ in range(reps):
        pick=np.sort(rng.choice(pool,size=min(nsig,pool.size),replace=False))
        r=ev(pick,s)
        if r: ms.append(r['mean'])
    return float(np.mean(ms)) if ms else float('nan')

for cc,s,trm,r in surv:
    P('  V %-70s %-22s tr=%+.4f | va mean=%+.4f lo=%+.4f med=%+.4f n=%d k=%d res=%.3f'%(
        lbl(cc),s,trm,r['mean'],r['lo'],r['median'],r['n'],r['clusters'],r['res']))
    nsigs=int(len(np.flatnonzero(np.ones(1))))  # placeholder
    m=cva(cc[0])
    for c in cc[1:]: m=m&cva(c)
    nsig=int(m.sum())
    rc=rand_control(nsig,s)
    P('      random-entry control (same structure, n=%d signal bars, 200 draws): %+.4f  -> edge %+.4f'%(nsig,rc,r['mean']-rc))
    for key,name in [((-0.30,TOLL),'drop-30 toll1.14'),((-0.50,TOLL),'drop-50 toll1.14'),
                     ((-1.00,TOLL),'drop-100 toll1.14'),((-0.30,TOLL2),'drop-30 toll2.50')]:
        rr=ev(VAi[m],s,key=key,boot=1500)
        P('      %-20s va mean=%+.4f lo=%+.4f med=%+.4f'%(name,rr['mean'],rr['lo'],rr['median']))

# top validate performers even if failing gate (diagnostic on surface shape)
diag=[]
for cc,s,trm,trmd,trn,trk,trlo in ALLTR[:400]:
    m=cva(cc[0])
    for c in cc[1:]: m=m&cva(c)
    sig=VAi[m]
    if sig.size<40: continue
    r=ev(sig,s)
    if r is None or r['clusters']<15: continue
    diag.append((cc,s,trm,r['mean'],r['median'],r['n'],r['clusters']))
diag.sort(key=lambda x:-x[3])
P('\ntrain->validate carryover, top 30 by validate mean (diagnostic, NOT survivors):')
for cc,s,trm,vam,vamd,n,k in diag[:30]:
    P('  D %-70s %-22s tr=%+.4f va=%+.4f vamed=%+.4f n=%d k=%d'%(lbl(cc),s,trm,vam,vamd,n,k))
tr_arr=np.array([d[2] for d in diag]); va_arr=np.array([d[3] for d in diag])
if tr_arr.size>3:
    P('\ncarryover stats over %d train-positive rules: mean(train)=%+.4f mean(validate)=%+.4f  frac va>0 = %.3f  corr=%.3f'%(
        tr_arr.size,tr_arr.mean(),va_arr.mean(),float((va_arr>0).mean()),
        float(np.corrcoef(tr_arr,va_arr)[0,1]) if tr_arr.size>3 else float('nan')))
pickle.dump(dict(surv=surv,diag=diag,combos=combos,CONDS=CONDS),open(W+'stageD.pkl','wb'))
P('STAGE_C_DONE %.1fs'%(time.time()-T0))
OUT.close()
