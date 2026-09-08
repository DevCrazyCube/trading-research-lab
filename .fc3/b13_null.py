import sys,json,pickle,time; sys.path.insert(0,'/home/anont/meme/.fc3')
import numpy as np
exec(open('/home/anont/meme/.fc3/b10_stress.py').read().split("CAND={")[0])
t0=time.time()
# real values
V0={m:D[m]['vo'][0] for m in mints}; PRI={m:D[m]['pri'] for m in mints}
TRm=[m for m in mints if D[m]['h']==1]; VAm=[m for m in mints if D[m]['h']==2]
def setattrs(v0map,primap):
    for m in mints:
        D[m]['_v0']=v0map[m]; D[m]['_pri']=primap[m]
def cond_factory(a0,a1,v0t):
    return lambda f,i,d: (a0<=f['age'][i]<a1) and d['_v0']>=v0t and d['_pri']==0
def run_cell(a0,a1,v0t,H,sl):
    out={}
    for sp in ('train','validate'):
        r=backtest(cond_factory(a0,a1,v0t),H,None,sl,'all',sp,fill='close')
        out[sp]=r
    return out
setattrs(V0,PRI)
real=run_cell(30,60,5040,30,-0.25)
L=['REAL cell (fill=close): train mean=%+.4f n=%d k=%d | validate mean=%+.4f cilo=%+.4f n=%d k=%d'%(
    real['train']['mean'],real['train']['n'],real['train']['k'],
    real['validate']['mean'],blo(real['validate']['pm']),real['validate']['n'],real['validate']['k'])]
rng=np.random.default_rng(2026)
NDRAW=120
res=[]
for s in range(NDRAW):
    # permute mint-level attributes WITHIN each split (keeps split marginals)
    v0m=dict(V0); prm=dict(PRI)
    for grp in (TRm,VAm):
        vals=[V0[m] for m in grp]; pvals=[PRI[m] for m in grp]
        rng.shuffle(vals); rng.shuffle(pvals)
        for m,a,b in zip(grp,vals,pvals): v0m[m]=a; prm[m]=b
    setattrs(v0m,prm)
    a0=float(rng.integers(0,451)); a1=a0+30.0
    H=int(rng.choice([15,30,60])); sl=rng.choice([None,-0.25,-0.40])
    o=run_cell(a0,a1,5040,H,sl)
    if o['train'] is None or o['validate'] is None: continue
    tr=o['train']; va=o['validate']
    if tr['k']<12 or va['k']<12 or tr['n']<25 or va['n']<25: continue
    res.append((tr['mean'],va['mean'],blo(va['pm']),a0,H,str(sl),tr['k'],va['k']))
setattrs(V0,PRI)
sel=[r for r in res if r[0]>0 and r[1]>0 and r[2]>0]
big=[r for r in res if r[0]>=0.11 and r[1]>=0.18]
L.append('NULL N2 (permuted mint attrs + random 30-min age window + random H/SL): usable draws=%d'%len(res))
L.append('  draws meeting my selection rule (train>0, val>0, val CI-lo>0): %d (%.1f%%)'%(len(sel),100*len(sel)/max(len(res),1)))
L.append('  draws as good as the real cell (train>=+11%%, val>=+18%%): %d (%.1f%%)'%(len(big),100*len(big)/max(len(res),1)))
if res:
    tm=np.array([r[0] for r in res]); vm=np.array([r[1] for r in res])
    L.append('  null train mean dist: p10=%+.3f p50=%+.3f p90=%+.3f max=%+.3f'%(*np.quantile(tm,[.1,.5,.9]),tm.max()))
    L.append('  null valid mean dist: p10=%+.3f p50=%+.3f p90=%+.3f max=%+.3f'%(*np.quantile(vm,[.1,.5,.9]),vm.max()))
# NULL N1: keep the real age window/H/SL, permute only the mint attributes
res1=[]
for s in range(NDRAW):
    v0m=dict(V0); prm=dict(PRI)
    for grp in (TRm,VAm):
        vals=[V0[m] for m in grp]; pvals=[PRI[m] for m in grp]
        rng.shuffle(vals); rng.shuffle(pvals)
        for m,a,b in zip(grp,vals,pvals): v0m[m]=a; prm[m]=b
    setattrs(v0m,prm)
    o=run_cell(30,60,5040,30,-0.25)
    if o['train'] is None or o['validate'] is None: continue
    if o['train']['k']<10 or o['validate']['k']<10: continue
    res1.append((o['train']['mean'],o['validate']['mean']))
setattrs(V0,PRI)
if res1:
    tm=np.array([r[0] for r in res1]); vm=np.array([r[1] for r in res1])
    L.append('NULL N1 (attrs permuted, same window/H/SL): draws=%d'%len(res1))
    L.append('  P(train>=real)=%.3f  P(val>=real)=%.3f  P(both)=%.3f'%(
        (tm>=real['train']['mean']).mean(),(vm>=real['validate']['mean']).mean(),
        ((tm>=real['train']['mean'])&(vm>=real['validate']['mean'])).mean()))
    L.append('  null train p50=%+.3f p90=%+.3f | null val p50=%+.3f p90=%+.3f'%(
        np.median(tm),np.quantile(tm,.9),np.median(vm),np.quantile(vm,.9)))
L.append('elapsed %.0fs'%(time.time()-t0))
open(SP+'/b13.log','w').write('\n'.join(L))
