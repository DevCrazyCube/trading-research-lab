import numpy as np, sys, pickle, json
sys.path.insert(0,'/home/anont/meme/.scr')
from sim import *

QS=[('ge',0.90),('ge',0.95),('ge',0.99),('le',0.10),('le',0.05),('le',0.01)]
CORE=[('H',5),('H',15),('H',60),('H',240),
      ('TP',0.25,15),('TP',0.50,60),('TP',1.00,240),
      ('BR',0.50,0.35,60),('BR',1.00,0.60,240),('TR',0.35,60)]

# thresholds from TRAIN bars only
stack=np.vstack([FM[m][VALID[m][:,0]] if False else FM[m] for m in TRAIN])
vstack=np.vstack([VALID[m] for m in TRAIN])
THR={}
for k,name in enumerate(ALLF):
    col=stack[:,k][vstack[:,k]]
    THR[name]={q:float(np.quantile(col,q)) for _,q in QS}

def mk(k,op,thr):
    def f(m):
        X=FM[m]; V=VALID[m]
        c = (X[:,k]>=thr) if op=='ge' else (X[:,k]<=thr)
        return c & V[:,k]
    return f
def allmask(m): return np.ones(len(per[m]['ts']),dtype=bool)

CTRL={}
for ex in CORE:
    for lbl,mset in (('T',TRAIN),('V',VALD)):
        r=run(allmask,mset,ex,('FULL',),drop=-0.50)
        CTRL[(lbl,str(ex))]=r['mean']
print('CONTROLS (all-bars, FULL, drop -50%, toll 1.14%)')
for k,v in CTRL.items(): print('  ',k,f'{v*100:+.2f}%')
print()

rows=[]
nsweep=0
for k,name in enumerate(ALLF):
    for op,q in QS:
        thr=THR[name][q]
        f=mk(k,op,thr)
        for ex in CORE:
            nsweep+=1
            rT=run(f,TRAIN,ex,('FULL',),drop=-0.50)
            if rT is None or rT['clusters']<25 or rT['n']<60: continue
            exc=rT['mean']-CTRL[('T',str(ex))]
            rows.append(dict(feat=name,k=k,op=op,q=q,thr=thr,ex=ex,
                             tmean=rT['mean'],tmed=rT['median'],n=rT['n'],cl=rT['clusters'],
                             res=rT['res'],exc=exc))
rows.sort(key=lambda r:-r['exc'])
print('swept',nsweep,'kept',len(rows))
print('\nTOP 45 by TRAIN excess vs structure-matched control')
for r in rows[:45]:
    print(f"{r['feat']:12s} {r['op']} q{r['q']:.2f} thr={r['thr']:+.4g} {str(r['ex']):22s} "
          f"exc={r['exc']*100:+7.2f}pp mean={r['tmean']*100:+8.2f}% med={r['tmed']*100:+7.2f}% n={r['n']:5d} k={r['cl']:3d}")
print('\nBOTTOM 15')
for r in rows[-15:]:
    print(f"{r['feat']:12s} {r['op']} q{r['q']:.2f} {str(r['ex']):22s} exc={r['exc']*100:+7.2f}pp n={r['n']:5d} k={r['cl']:3d}")

# per-feature best excess (max over thresholds/exits) and mean excess
print('\nPER-FEATURE summary (max excess, mean excess over all cells)')
agg={}
for r in rows: agg.setdefault((r['feat'],r['op']),[]).append(r['exc'])
out=[]
for (f,op),v in agg.items():
    out.append((max(v),float(np.mean(v)),len(v),f,op))
out.sort(reverse=True)
for mx,mn,c,f,op in out:
    print(f"  {f:12s} {op}  max={mx*100:+7.2f}pp  mean={mn*100:+7.2f}pp  cells={c}")
pickle.dump(dict(rows=rows,THR=THR,CTRL=CTRL,nsweep=nsweep),open(SCR+'screen1.pkl','wb'))
