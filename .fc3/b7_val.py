import sys,time,json; sys.path.insert(0,'/home/anont/meme/.fc3')
import numpy as np
from lib2 import *
N=len(F)
def band(c,lo,hi):
    v=F[:,c]; return (v>=lo)&(v<hi)
ONE=np.ones(N,bool)
AXd={}
AXd['age']={'any':ONE,'0-3':band(AGE,-1e9,3),'3-10':band(AGE,3,10),'10-30':band(AGE,10,30),
        '30-120':band(AGE,30,120),'120-480':band(AGE,120,480),'480+':band(AGE,480,1e18)}
AXd['dd']={'any':ONE,'.9-1':band(DD,0.9,1e18),'.6-.9':band(DD,0.6,0.9),'.3-.6':band(DD,0.3,0.6),
       '.1-.3':band(DD,0.1,0.3),'<.1':band(DD,-1e9,0.1)}
AXd['lvl']={'any':ONE,'<.3':band(LVL,-1e9,0.3),'.3-1':band(LVL,0.3,1.0),'1-3':band(LVL,1.0,3.0),'3+':band(LVL,3.0,1e18)}
AXd['rv']={'any':ONE,'<.02':band(RELV,-1e9,0.02),'.02-.2':band(RELV,0.02,0.2),'.2-.7':band(RELV,0.2,0.7),'.7+':band(RELV,0.7,1e18)}

def cellmask(a,d,l,r): return AXd['age'][a]&AXd['dd'][d]&AXd['lvl'][l]&AXd['rv'][r]

def matched_random(pr,k,mode,ndraw=20,seed=7):
    """same mints, same #selected rows per mint, random rows from that mint."""
    rng=np.random.default_rng(seed); vals=[]
    # need mint id for each pr entry
    for _ in range(ndraw):
        prr=[]
        for idx in pr:
            m=mi[idx[0]]; s,e=starts[m],ends[m]
            cnt=min(len(idx),e-s)
            sel=np.sort(rng.choice(np.arange(s,e),size=cnt,replace=False))
            prr.append(sel)
        r=run(prr,k,mode)
        if r: vals.append(r['mean'])
    return float(np.mean(vals)),float(np.std(vals))

g=json.load(open(SP+'/grid_full.json'))
rows=[r for r in g['rows'] if r[13]>0]
res=[]
for r in rows:
    a,d,l,rv,H,tp,sl,mode,tmean,tmed,tn,tk,tres,tlo=r
    k=EX.index((H,tp,sl))
    msk=cellmask(a,d,l,rv)
    prv=prep(msk,'validate')
    if len(prv)<5: continue
    v=run(prv,k,mode)
    if v is None: continue
    vlo=boot_lo(v['pm'],B=2000,seed=3)
    # controls on validate
    cm,cs=matched_random(prv,k,mode)
    pru=prep(ONE,'validate'); u=run(pru,k,mode)
    res.append(dict(age=a,dd=d,lvl=l,rv=rv,H=H,tp=tp,sl=sl,mode=mode,
        train_mean=tmean,train_med=tmed,train_n=tn,train_k=tk,train_cilo=tlo,
        v_mean=v['mean'],v_med=v['median_trade'],v_medmint=v['median_mint'],v_n=v['n'],v_k=v['k'],v_res=v['res'],
        v_cilo=vlo,ctrl_matched=cm,ctrl_sd=cs,ctrl_uncond=u['mean'] if u else None))
json.dump(res,open(SP+'/val.json','w'))
res.sort(key=lambda d:-d['v_cilo'])
L=['validated %d train-survivors (train mean>0 AND train CI-lo>0)'%len(res)]
L.append('SURVIVORS on validate (v_mean>0 and v_cilo>0 and beats matched random):')
ok=[d for d in res if d['v_mean']>0 and d['v_cilo']>0 and d['v_mean']>d['ctrl_matched']]
L.append('count=%d'%len(ok))
for d in ok:
    L.append('age=%-8s dd=%-5s lvl=%-5s rv=%-6s H=%-3d tp=%-5s sl=%-5s %-5s | TR mean=%+.4f n=%3d k=%3d | VA mean=%+.4f med=%+.4f cilo=%+.4f n=%3d k=%3d res=%.2f | ctrl_match=%+.4f(sd %.3f) ctrl_uncond=%+.4f'%(
        d['age'],d['dd'],d['lvl'],d['rv'],d['H'],str(d['tp']),str(d['sl']),d['mode'],
        d['train_mean'],d['train_n'],d['train_k'],d['v_mean'],d['v_med'],d['v_cilo'],d['v_n'],d['v_k'],d['v_res'],
        d['ctrl_matched'],d['ctrl_sd'],d['ctrl_uncond']))
L.append('')
L.append('--- all %d, sorted by validate CI-lo (top 25) ---'%len(res))
for d in res[:25]:
    L.append('age=%-8s dd=%-5s lvl=%-5s rv=%-6s H=%-3d tp=%-5s sl=%-5s %-5s TRm=%+.4f VAm=%+.4f VAlo=%+.4f VAn=%3d VAk=%3d ctrl=%+.4f'%(
        d['age'],d['dd'],d['lvl'],d['rv'],d['H'],str(d['tp']),str(d['sl']),d['mode'],
        d['train_mean'],d['v_mean'],d['v_cilo'],d['v_n'],d['v_k'],d['ctrl_matched']))
open(SP+'/b7.log','w').write('\n'.join(L))
