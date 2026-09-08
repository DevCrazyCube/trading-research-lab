import numpy as np, sys, time
sys.path.insert(0,'/home/anont/meme/_fv0')
from engine import *

TR=np.where(E_h==1)[0]; VA=np.where(E_h==2)[0]
ALL=np.arange(NE)
print('train entries',len(TR),'validate',len(VA))
print('HOR',HOR,'TPS',TPS,'SLS',SLS)
print('FEATNAMES',FEATNAMES)

print('\n=== UNCONDITIONAL (every bar a signal, non-overlap) ===')
print('split hi H tpi sli  meanA medA k n res   meanB meanC  mean2.5%')
for name,idx in (('ALL',ALL),('TRAIN',TR),('VAL',VA)):
    for hi,H in enumerate(HOR):
        r=evaluate(idx.tolist(),hi,-1,-1)
        print(f'{name:6s} H={H:4d} noTP noSL  {r["a"][0]*100:7.2f} {r["a"][1]*100:7.2f} k={r["a"][2]:4d} n={r["n"]:6d} res={r["res"]*100:5.1f}  B={r["b"][0]*100:7.2f} C={r["c"][0]*100:7.2f} D={r["d"][0]*100:7.2f}')

print('\n=== TRUNCATION ARTIFACT CHECK: unconditional with TP/SL (H=15) ===')
hi=HOR.index(15)
for tpi in range(-1,len(TPS)):
    for sli in range(-1,len(SLS)):
        r=evaluate(ALL.tolist(),hi,tpi,sli)
        tp='none' if tpi<0 else f'{TPS[tpi]:.2f}'
        sl='none' if sli<0 else f'{SLS[sli]:.2f}'
        print(f'H=15 TP={tp:5s} SL={sl:5s} meanA={r["a"][0]*100:7.2f} medA={r["a"][1]*100:7.2f} k={r["a"][2]} n={r["n"]} res={r["res"]*100:5.1f}')
