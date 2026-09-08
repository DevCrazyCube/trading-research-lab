import numpy as np, sys
sys.path.insert(0,'/home/anont/meme/_fv0')
import engine2 as engine
from engine2 import *
FI={n:i for i,n in enumerate(FEATNAMES)}
NN=FI['notional20']; RV=FI['rvol20']; EF=FI['eff20']; VA_=FI['volaccel']
TR=(E_h==1); VA=(E_h==2); IDX=np.arange(NE)
FEAS=FEAT[:,NN]>=300.0

def c2(cnts,ex,split,feas,reps=500,seed=5):
    rng=np.random.default_rng(seed); A=exit_arrays(*ex)
    pool=IDX[feas&(TR if split=='tr' else VA)]
    bym={}
    for i in pool: bym.setdefault(engine._EM_l[i],[]).append(i)
    mn=[];md=[]
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
        mm=stats(np.array(sel,dtype=np.int64),A); mn.append(mm.mean()); md.append(np.median(mm))
    return np.array(mn),np.array(md)

def report(name,mask,ex,feas=FEAS):
    print(f'\n##### {name}')
    print(f'   exit: H={HOR[ex[0]]}m  TP={"none" if ex[1]<0 else TPS[ex[1]]}  SL={"none" if ex[2]<0 else SLS[ex[2]]}  scaleout={"half at TP" if ex[3] else "full"}')
    for split in ('tr','va'):
        idx=IDX[mask&feas&(TR if split=='tr' else VA)]
        r=evaluate(idx.tolist(),*ex,full=True)
        cnts={}
        for k in r['sel']: cnts[engine._EM_l[k]]=cnts.get(engine._EM_l[k],0)+1
        mn,md=c2(cnts,ex,split,feas)
        lo,hi=boot_ci(r['mm']); mlo,mhi=boot_ci_med(r['mm'])
        tag='TRAIN(h=1)' if split=='tr' else 'VALID(h=2)'
        print(f"  {tag} mean={r['mean']*100:6.2f} [CI {lo*100:.2f},{hi*100:.2f}]  median={r['med']*100:6.2f} [CI {mlo*100:.2f},{mhi*100:.2f}]  trim5={r['trim']*100:6.2f}  fpos={r['fpos']*100:.0f}%  k={r['k']}  n={r['n']}  res={r['res']*100:.1f}%")
        print(f"             C2 random-entry same-structure mean={mn.mean()*100:6.2f} -> EDGE={(r['mean']-mn.mean())*100:5.2f}pp (pct {(r['mean']>mn).mean()*100:.0f}%) | C2 median={md.mean()*100:6.2f} -> edge={(r['med']-md.mean())*100:5.2f}pp")
        if split=='va':
            print(f"             robustness: drop-50%={r['mean_b']*100:.2f} drop-100%={r['mean_c']*100:.2f} toll2.5%={r['mean_d']*100:.2f} toll2.5%+drop100%={r['mean_e']*100:.2f}")
            nn=FEAT[r['sel']-1,NN]
            print(f"             capacity notional20: median ${np.nanmedian(nn):.0f}/min  p10 ${np.nanpercentile(nn,10):.0f}/min")
            print(f"             VA_MEAN={r['mean']:.6f} VA_MED={r['med']:.6f} K={r['k']} N={r['n']}")
        else:
            print(f"             TR_MEAN={r['mean']:.6f}")

rv05=FEAT[:,RV]<=0.05
rv02=FEAT[:,RV]<=0.02
report('A  rvol20<=0.05 | H=60 TP+0.20 half-out SL-0.15', rv05,(HOR.index(60),TPS.index(0.20),SLS.index(0.15),1))
report('B  rvol20<=0.05 | H=60 TP+0.20 half-out SL-0.12', rv05,(HOR.index(60),TPS.index(0.20),SLS.index(0.12),1))
report('C  rvol20<=0.05 | H=45 TP+0.20 half-out SL-0.12', rv05,(HOR.index(45),TPS.index(0.20),SLS.index(0.12),1))
report('D  rvol20<=0.05 | H=60 no TP  SL-0.15 (pure stop)', rv05,(HOR.index(60),-1,SLS.index(0.15),0))
report('E  rvol20<=0.02 & eff20>0.5 | H=10 TP+0.10 SL-0.15', rv02&(FEAT[:,EF]>0.5),(HOR.index(10),TPS.index(0.10),SLS.index(0.15),0))
report('F  rvol20<=0.02 & volaccel<=1 | H=10 TP+0.10 SL-0.15', rv02&(FEAT[:,VA_]<=1.0),(HOR.index(10),TPS.index(0.10),SLS.index(0.15),0))
