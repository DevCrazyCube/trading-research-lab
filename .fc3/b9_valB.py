import sys,time,json; sys.path.insert(0,'/home/anont/meme/.fc3')
import numpy as np
from lib2 import *
N=len(F)
def band(c,lo,hi):
    v=F[:,c]; return (v>=lo)&(v<hi)
ONE=np.ones(N,bool)
g=json.load(open(SP+'/gridB.json'))
q1,q2=g['q1'],g['q2']
AX={}
AX['agef']={'any':ONE,'0-1':band(AGE,-1e9,1),'1-3':band(AGE,1,3),'3-6':band(AGE,3,6),'6-10':band(AGE,6,10),
            '10-20':band(AGE,10,20),'20-30':band(AGE,20,30),'30-60':band(AGE,30,60),'60+':band(AGE,60,1e18)}
AX['pri']={'any':ONE,'0':band(PRI,-1,0.5),'1-5':band(PRI,0.5,5.5),'6+':band(PRI,5.5,1e9)}
AX['prig']={'any':ONE,'0':band(PRIG,-1,0.5),'1+':band(PRIG,0.5,1e9)}
AX['v0']={'any':ONE,'lo':band(V0,-1e9,q1),'mid':band(V0,q1,q2),'hi':band(V0,q2,1e18)}
AX['dd']={'any':ONE,'.9-1':band(DD,0.9,1e18),'<.1':band(DD,-1e9,0.1)}
def cm(a,p,pg,v,d): return AX['agef'][a]&AX['pri'][p]&AX['prig'][pg]&AX['v0'][v]&AX['dd'][d]
def matched_random(pr,k,mode,ndraw=15,seed=7):
    rng=np.random.default_rng(seed); vals=[]
    for _ in range(ndraw):
        prr=[]
        for idx in pr:
            m=mi[idx[0]]; s,e=starts[m],ends[m]
            cnt=min(len(idx),e-s)
            prr.append(np.sort(rng.choice(np.arange(s,e),size=cnt,replace=False)))
        r=run(prr,k,mode)
        if r: vals.append(r['mean'])
    return float(np.mean(vals))
rows=[r for r in g['rows'] if r[14]>0]
res=[]
for r in rows:
    a,p,pg,v,d,H,tp,sl,mode,tmean,tmed,tn,tk,tres,tlo=r
    k=EX.index((H,tp,sl)); msk=cm(a,p,pg,v,d)
    prv=prep(msk,'validate')
    if len(prv)<5: continue
    vv=run(prv,k,mode)
    if vv is None or vv['k']<10 or vv['n']<25: continue
    vlo=boot_lo(vv['pm'],B=2000,seed=3)
    ctrl=matched_random(prv,k,mode) if vlo>0 and vv['mean']>0 else None
    res.append(dict(grid='B',age=a,pri=p,prig=pg,v0=v,dd=d,H=H,tp=tp,sl=sl,mode=mode,
        train_mean=tmean,train_n=tn,train_k=tk,train_cilo=tlo,
        v_mean=vv['mean'],v_med=vv['median_trade'],v_n=vv['n'],v_k=vv['k'],v_res=vv['res'],v_cilo=vlo,
        ctrl_matched=ctrl))
json.dump(res,open(SP+'/valB.json','w'))
ok=[d for d in res if d['v_mean']>0 and d['v_cilo']>0 and d['ctrl_matched'] is not None and d['v_mean']>d['ctrl_matched']]
ok.sort(key=lambda d:-d['v_cilo'])
L=['gridB: tested %d train-survivors on validate; %d pass (v_mean>0, v_cilo>0, > matched random)'%(len(res),len(ok))]
for d in ok[:40]:
    L.append('age=%-6s pri=%-4s prig=%-4s v0=%-4s dd=%-5s H=%-3d tp=%-5s sl=%-5s %-5s | TR m=%+.4f n=%3d k=%3d | VA m=%+.4f med=%+.4f lo=%+.4f n=%3d k=%3d res=%.2f | ctrl=%+.4f'%(
        d['age'],d['pri'],d['prig'],d['v0'],d['dd'],d['H'],str(d['tp']),str(d['sl']),d['mode'],
        d['train_mean'],d['train_n'],d['train_k'],d['v_mean'],d['v_med'],d['v_cilo'],d['v_n'],d['v_k'],d['v_res'],d['ctrl_matched']))
open(SP+'/b9.log','w').write('\n'.join(L))
