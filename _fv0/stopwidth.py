import numpy as np, sys
sys.path.insert(0,'/home/anont/meme/_fv0')
import engine2 as engine
from engine2 import *

FI={n:i for i,n in enumerate(FEATNAMES)}
NN=FI['notional20']; RV=FI['rvol20']
TR=(E_h==1); VA=(E_h==2); IDX=np.arange(NE)
FEAS=FEAT[:,NN]>=300.0
print('SLS',SLS,'TPS',TPS,'entries',NE)

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
        mn.append(stats(np.array(sel,dtype=np.int64),A).mean())
    return np.array(mn)

def go(mask,ex,split,feas=FEAS):
    idx=IDX[mask&feas&(TR if split=='tr' else VA)]
    if len(idx)<30: return None
    r=evaluate(idx.tolist(),*ex,full=True)
    if r is None or r['k']<15: return None
    cnts={}
    for k in r['sel']: cnts[engine._EM_l[k]]=cnts.get(engine._EM_l[k],0)+1
    mn=c2(cnts,ex,split,feas)
    if len(mn)<20: return None
    r['edge']=r['mean']-mn.mean(); r['pct']=float((r['mean']>mn).mean()); r['c2m']=float(mn.mean())
    return r

m=FEAT[:,RV]<=0.05
print('\n=== STOP-WIDTH PLATEAU: rvol20<=0.05, liquid>=$300, H=60, no TP (pure stop) ===')
print(f"{'SL':>6s} | {'TRmean':>7s} {'TRedge':>7s} {'TRpct':>5s} | {'VAmean':>7s} {'VAedge':>7s} {'VApct':>5s} {'VAmed':>7s} {'n':>4s} {'k':>3s} {'res':>5s}")
for sli,sl in enumerate(SLS):
    ex=(HOR.index(60),-1,sli,0)
    a=go(m,ex,'tr'); b=go(m,ex,'va')
    if a is None or b is None: continue
    print(f"{sl:6.2f} | {a['mean']*100:7.2f} {a['edge']*100:7.2f} {a['pct']*100:5.0f} | {b['mean']*100:7.2f} {b['edge']*100:7.2f} {b['pct']*100:5.0f} {b['med']*100:7.2f} {b['n']:4d} {b['k']:3d} {b['res']*100:5.1f}")

print('\n=== same, WITH half-out at +20% ===')
tp1=TPS.index(0.20)
for sli,sl in enumerate(SLS):
    ex=(HOR.index(60),tp1,sli,1)
    a=go(m,ex,'tr'); b=go(m,ex,'va')
    if a is None or b is None: continue
    print(f"{sl:6.2f} | {a['mean']*100:7.2f} {a['edge']*100:7.2f} {a['pct']*100:5.0f} | {b['mean']*100:7.2f} {b['edge']*100:7.2f} {b['pct']*100:5.0f} {b['med']*100:7.2f} {b['n']:4d} {b['k']:3d} {b['res']*100:5.1f}")

print('\n=== HORIZON x STOP (validate mean / edge), rvol<=0.05, no TP ===')
print('      ' + ''.join(f'{s:>14.2f}' for s in SLS[:8]))
for H in (15,30,45,60,90,120):
    row=f'H={H:4d}'
    for sli in range(8):
        b=go(m,(HOR.index(H),-1,sli,0),'va')
        row+= f'{b["mean"]*100:7.2f}/{b["edge"]*100:5.1f}' if b else '           -  '
    print(row)

print('\n=== TIME STABILITY (validate, rvol<=0.05 H=60 SL=0.15 no TP) ===')
sl15=SLS.index(0.15); ex=(HOR.index(60),-1,sl15,0)
mid=np.median(C['E_ts'][FEAS&VA])
for lab,tm in (('early',C['E_ts']<=mid),('late',C['E_ts']>mid)):
    idx=IDX[m&FEAS&VA&tm]
    if len(idx)<30: print(lab,'thin'); continue
    r=evaluate(idx.tolist(),*ex,full=True)
    print(f"{lab:6s} mean={r['mean']*100:7.2f} med={r['med']*100:6.2f} trim={r['trim']*100:6.2f} k={r['k']} n={r['n']}")
idx=IDX[m&FEAS&VA]; r=evaluate(idx.tolist(),*ex,full=True)
lo,hi=boot_ci(r['mm'])
print(f"FULL   mean={r['mean']*100:7.2f} med={r['med']*100:6.2f} trim={r['trim']*100:6.2f} fpos={r['fpos']*100:.0f}% k={r['k']} n={r['n']} res={r['res']*100:.1f} CI=[{lo*100:.2f},{hi*100:.2f}]")
print(f"  drop-50={r['mean_b']*100:.2f} drop-100={r['mean_c']*100:.2f} toll2.5={r['mean_d']*100:.2f} toll2.5+drop100={r['mean_e']*100:.2f}")
