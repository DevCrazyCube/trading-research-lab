import numpy as np, sys, pickle, time
sys.path.insert(0,'/home/anont/meme/_fv0')
import engine
from engine import *

FI={n:i for i,n in enumerate(FEATNAMES)}
NN=FI['notional20']
TR=(E_h==1); VA=(E_h==2); IDX=np.arange(NE)
FLOOR=300.0; FEAS=FEAT[:,NN]>=FLOOR

def parse(lbl):
    o=[]
    for tok in lbl.split(' & '):
        if '<=' in tok: f,t=tok.split('<='); op='<='
        else: f,t=tok.split('>'); op='>'
        o.append((f,op,float(t)))
    return o
def maskof(lbl):
    m=np.ones(NE,bool)
    for f,op,t in parse(lbl):
        c=FEAT[:,FI[f]]; m &= (c>t) if op=='>' else (c<=t)
    return m

def c2(cnts,ex,split,reps=400,seed=3):
    rng=np.random.default_rng(seed); A=exit_arrays(*ex)
    pool=IDX[FEAS&(TR if split=='tr' else VA)]
    bym={}
    for i in pool: bym.setdefault(engine._EM_l[i],[]).append(i)
    mn=[];tm=[];md=[]
    for _ in range(reps):
        sel=[]
        for m,cnt in cnts.items():
            p=bym.get(m)
            if not p: continue
            take=rng.choice(len(p),size=min(cnt,len(p)),replace=False)
            cur=-1
            for k in sorted(p[j] for j in take):
                if engine._EB_l[k]>cur: sel.append(k); cur=A['eb_l'][k]
        if len(sel)<5: continue
        sel=np.array(sel,dtype=np.int64); mm=stats(sel,A)
        mn.append(mm.mean()); tm.append(trimmed(mm)); md.append(np.median(mm))
    return np.array(mn),np.array(tm),np.array(md)

def run(lbl,ex,split):
    m=maskof(lbl); idx=IDX[m&FEAS&(TR if split=='tr' else VA)]
    if len(idx)<30: return None
    r=evaluate(idx.tolist(),*ex,full=True)
    if r is None: return None
    cnts={}
    for k in r['sel']: cnts[engine._EM_l[k]]=cnts.get(engine._EM_l[k],0)+1
    mn,tm,md=c2(cnts,ex,split)
    r['c2m']=float(mn.mean()); r['c2p']=float((r['mean']>mn).mean())
    r['c2t']=float(tm.mean()); r['c2tp']=float((r['trim']>tm).mean())
    r['c2med']=float(md.mean()); r['c2medp']=float((r['med']>md).mean())
    r['ci']=boot_ci(r['mm'])
    return r

D=pickle.load(open('/home/anont/meme/_fv0/valid.pkl','rb'))  # not used, placeholder
import itertools
V=pickle.load(open('/home/anont/meme/_fv0/final3.pkl','rb'))
# rebuild candidate list = all validate survivors with CI-lo>0 from valid3 run
import subprocess
cands=[]
seen=set()
S=pickle.load(open('/home/anont/meme/_fv0/stage3.pkl','rb'))
# recompute the CI-lo>0 set quickly
CTRL={}
for r in S['pos']:
    key=(r['label'],tuple(r['ex']))
    if key in seen: continue
    seen.add(key)
    m=maskof(r['label']); iv=IDX[m&FEAS&VA]
    if len(iv)<50: continue
    rv=evaluate(iv.tolist(),*tuple(r['ex']),full=True)
    if rv is None or rv['k']<20 or rv['n']<50: continue
    if not(rv['mean']>0 and rv['trim']>0 and rv['med']>-0.02): continue
    lo,hi=boot_ci(rv['mm'])
    if lo<=0: continue
    cands.append((r['label'],tuple(r['ex'])))
print('CI-lo>0 validate candidates:',len(cands))

print('\n=== JOINT GATE: C2 timing edge must be positive on BOTH train and validate ===')
print(f"{'rule':52s} {'exit':22s} {'TRmean':>8s} {'TRc2e':>7s} {'TRpct':>6s} {'VAmean':>8s} {'VAc2e':>7s} {'VApct':>6s} {'VAmed':>7s} {'k':>4s} {'n':>5s}")
passed=[]
for lbl,ex in cands:
    rt=run(lbl,ex,'tr'); rv=run(lbl,ex,'va')
    if rt is None or rv is None: continue
    et=rt['mean']-rt['c2m']; ev=rv['mean']-rv['c2m']
    exs=f"H={HOR[ex[0]]} tp={ex[1]} sl={ex[2]} pa={ex[3]}"
    ok = (et>0 and ev>0 and rt['c2p']>=0.85 and rv['c2p']>=0.85 and rt['mean']>0)
    mark='  <== PASS' if ok else ''
    print(f"{lbl:52s} {exs:22s} {rt['mean']*100:8.2f} {et*100:7.2f} {rt['c2p']*100:6.0f} {rv['mean']*100:8.2f} {ev*100:7.2f} {rv['c2p']*100:6.0f} {rv['med']*100:7.2f} {rv['k']:4d} {rv['n']:5d}{mark}")
    if ok: passed.append((lbl,ex,rt,rv))
print('\nPASSED JOINT GATE:',len(passed))
pickle.dump([(l,e) for l,e,_,_ in passed],open('/home/anont/meme/_fv0/passed.pkl','wb'))

for lbl,ex,rt,rv in passed:
    print(f"\n### {lbl} | H={HOR[ex[0]]} tp={ex[1]} sl={ex[2]} pa={ex[3]}")
    for tag,r in (('TRAIN',rt),('VALIDATE',rv)):
        print(f"  {tag:8s} mean={r['mean']*100:7.2f} trim={r['trim']*100:6.2f} med={r['med']*100:6.2f} fpos={r['fpos']*100:.0f}% k={r['k']:3d} n={r['n']:4d} res={r['res']*100:.1f} CI=[{r['ci'][0]*100:.2f},{r['ci'][1]*100:.2f}]")
        print(f"           C2 mean={r['c2m']*100:6.2f} edge={(r['mean']-r['c2m'])*100:6.2f} pct={r['c2p']*100:.0f}% | C2 med={r['c2med']*100:6.2f} edge={(r['med']-r['c2med'])*100:6.2f} pct={r['c2medp']*100:.0f}%")
        print(f"           drop-50={r['mean_b']*100:.2f} drop-100={r['mean_c']*100:.2f} toll2.5={r['mean_d']*100:.2f} toll2.5+drop100={r['mean_e']*100:.2f}")
    nn=FEAT[rv['sel']-1,NN]
    print(f"  capacity notional20 med=${np.nanmedian(nn):.0f}/min p10=${np.nanpercentile(nn,10):.0f}")
