import numpy as np, sys, pickle
sys.path.insert(0,'/home/anont/meme/_fv0')
import engine
from engine import *

FI={n:i for i,n in enumerate(FEATNAMES)}
NN=FI['notional20']; RV=FI['rvol20']
TR=(E_h==1); VA=(E_h==2); IDX=np.arange(NE)

def c2(cnts,ex,split,feas,reps=300,seed=5):
    rng=np.random.default_rng(seed); A=exit_arrays(*ex)
    pool=IDX[feas&(TR if split=='tr' else VA)]
    bym={}
    for i in pool: bym.setdefault(engine._EM_l[i],[]).append(i)
    mn=[]
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
        sel=np.array(sel,dtype=np.int64); mn.append(stats(sel,A).mean())
    return np.array(mn)

def go(mask,ex,split,feas):
    idx=IDX[mask&feas&(TR if split=='tr' else VA)]
    if len(idx)<30: return None
    r=evaluate(idx.tolist(),*ex,full=True)
    if r is None or r['k']<15: return None
    cnts={}
    for k in r['sel']: cnts[engine._EM_l[k]]=cnts.get(engine._EM_l[k],0)+1
    mn=c2(cnts,ex,split,feas)
    if len(mn)<20: return None
    r['edge']=r['mean']-mn.mean(); r['pct']=float((r['mean']>mn).mean())
    return r

print('=== PLATEAU MAP: rvol20<=X, liquid floor $300, TP=0.20/SL=0.15/scale-out-half ===')
print('exit structure fixed = (H, tp=0.20 half-out, sl=0.15). rows: rvol threshold, cols: H')
FEAS=FEAT[:,NN]>=300.0
tp1=TPS.index(0.20); sl0=SLS.index(0.15)
print(f"{'rvolTh':>8s} {'H':>4s} | {'TRmean':>7s} {'TRedge':>7s} {'TRpct':>5s} {'TRn':>4s} | {'VAmean':>7s} {'VAedge':>7s} {'VApct':>5s} {'VAn':>4s} {'VAk':>4s}")
for th in (0.005,0.01,0.02,0.03,0.05,0.08,0.12,0.20):
    m=FEAT[:,RV]<=th
    for H in (10,15,30,45,60,90):
        ex=(HOR.index(H),tp1,sl0,1)
        a=go(m,ex,'tr',FEAS); b=go(m,ex,'va',FEAS)
        if a is None or b is None:
            print(f'{th:8.3f} {H:4d} |  (insufficient support)'); continue
        print(f"{th:8.3f} {H:4d} | {a['mean']*100:7.2f} {a['edge']*100:7.2f} {a['pct']*100:5.0f} {a['n']:4d} | {b['mean']*100:7.2f} {b['edge']*100:7.2f} {b['pct']*100:5.0f} {b['n']:4d} {b['k']:4d}")

print('\n=== TP/SL sensitivity at rvol<=0.05, H=60 ===')
m=FEAT[:,RV]<=0.05
for tpi in (-1,0,1,2,3):
    for sli in (-1,0,1,2):
        for pa in (0,1):
            if pa==1 and tpi<0: continue
            ex=(HOR.index(60),tpi,sli,pa)
            a=go(m,ex,'tr',FEAS); b=go(m,ex,'va',FEAS)
            if a is None or b is None: continue
            tp='-' if tpi<0 else f'{TPS[tpi]:.2f}'; sl='-' if sli<0 else f'{SLS[sli]:.2f}'
            print(f"TP={tp:5s} SL={sl:5s} pa={pa} | TR mean={a['mean']*100:7.2f} edge={a['edge']*100:6.2f} pct={a['pct']*100:3.0f} | VA mean={b['mean']*100:7.2f} edge={b['edge']*100:6.2f} pct={b['pct']*100:3.0f} n={b['n']} k={b['k']}")

print('\n=== LIQUIDITY FLOOR sensitivity (rvol<=0.05, H=60, TP0.20 half-out, SL0.15) ===')
ex=(HOR.index(60),tp1,sl0,1)
for fl in (0,100,300,1000,3000):
    fe=FEAT[:,NN]>=fl
    a=go(m,ex,'tr',fe); b=go(m,ex,'va',fe)
    if a is None or b is None: print(fl,'insufficient'); continue
    print(f"floor=${fl:5d} | TR mean={a['mean']*100:7.2f} edge={a['edge']*100:6.2f} pct={a['pct']*100:3.0f} k={a['k']:3d} | VA mean={b['mean']*100:7.2f} edge={b['edge']*100:6.2f} pct={b['pct']*100:3.0f} k={b['k']:3d} n={b['n']}")

print('\n=== PLACEBO: shuffle rvol20 within each mint (destroys timing, keeps mint mix) ===')
rng=np.random.default_rng(99)
shuf=FEAT[:,RV].copy()
for mid in range(int(E_mint.max())+1):
    sl_=np.where(E_mint==mid)[0]
    if len(sl_)>1: shuf[sl_]=rng.permutation(shuf[sl_])
for th,H in ((0.05,60),(0.02,10),(0.02,30)):
    mm=shuf<=th
    ex=(HOR.index(H),tp1,sl0,1)
    a=go(mm,ex,'tr',FEAS); b=go(mm,ex,'va',FEAS)
    r=' '.join(f'{x}' for x in [])
    if a and b:
        print(f"placebo rvol<={th} H={H} | TR mean={a['mean']*100:7.2f} edge={a['edge']*100:6.2f} | VA mean={b['mean']*100:7.2f} edge={b['edge']*100:6.2f} k={b['k']}")

print('\n=== TIME STABILITY (validate, rvol<=0.05 H=60 TP0.20 half SL0.15): split by entry ts median ===')
mid=np.median(E_ts[FEAS&VA])
for lab,tm in (('early',E_ts<=mid),('late',E_ts>mid)):
    idx=IDX[m&FEAS&VA&tm]
    if len(idx)<30: print(lab,'thin'); continue
    r=evaluate(idx.tolist(),*ex,full=True)
    print(f"{lab:6s} mean={r['mean']*100:7.2f} med={r['med']*100:6.2f} k={r['k']} n={r['n']}")
