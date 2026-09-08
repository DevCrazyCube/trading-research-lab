import sys,time,json; sys.path.insert(0,'/home/anont/meme/.fc3')
import numpy as np
from lib2 import *
t0=time.time()
N=len(F)
def band(col,lo,hi):
    v=F[:,col]; return (v>=lo)&(v<hi)
AXES={}
AXES['age']=[('any',np.ones(N,bool)),('0-3',band(AGE,-1e9,3)),('3-10',band(AGE,3,10)),('10-30',band(AGE,10,30)),
             ('30-120',band(AGE,30,120)),('120-480',band(AGE,120,480)),('480+',band(AGE,480,1e18))]
AXES['dd']=[('any',np.ones(N,bool)),('.9-1',band(DD,0.9,1e18)),('.6-.9',band(DD,0.6,0.9)),('.3-.6',band(DD,0.3,0.6)),
            ('.1-.3',band(DD,0.1,0.3)),('<.1',band(DD,-1e9,0.1))]
AXES['lvl']=[('any',np.ones(N,bool)),('<.3',band(LVL,-1e9,0.3)),('.3-1',band(LVL,0.3,1.0)),('1-3',band(LVL,1.0,3.0)),('3+',band(LVL,3.0,1e18))]
AXES['rv']=[('any',np.ones(N,bool)),('<.02',band(RELV,-1e9,0.02)),('.02-.2',band(RELV,0.02,0.2)),('.2-.7',band(RELV,0.2,0.7)),('.7+',band(RELV,0.7,1e18))]

res=[]
ncomb=0
for an,am in AXES['age']:
    for dn,dm in AXES['dd']:
        m2=am&dm
        if m2.sum()<30: continue
        for ln,lm in AXES['lvl']:
            m3=m2&lm
            if m3.sum()<30: continue
            for rn,rm in AXES['rv']:
                m4=m3&rm
                if m4.sum()<30: continue
                pr=prep(m4,'train')
                if len(pr)<10: continue
                for hidx,H in enumerate(HS):
                    k=hidx*12
                    for mode in ('all','first'):
                        r=run(pr,k,mode)
                        ncomb+=1
                        if r is None or r['k']<12 or r['n']<25: continue
                        res.append(dict(age=an,dd=dn,lvl=ln,rv=rn,H=H,mode=mode,tp=None,sl=None,
                                        mean=r['mean'],med=r['median_trade'],n=r['n'],k=r['k'],res=r['res']))
json.dump(dict(ncomb=ncomb,res=res),open(SP+'/grid1.json','w'))
res.sort(key=lambda d:-d['mean'])
L=['stage1 combos=%d kept=%d  time=%.1fs'%(ncomb,len(res),time.time()-t0)]
L.append('--- top 40 by train mean (mint-equal, cap +900%, toll 1.14%, dropout -30%) ---')
for d in res[:40]:
    L.append('age=%-8s dd=%-5s lvl=%-5s rv=%-6s H=%-3d %-5s n=%4d k=%3d res=%.2f mean=%+.4f med=%+.4f'%(
        d['age'],d['dd'],d['lvl'],d['rv'],d['H'],d['mode'],d['n'],d['k'],d['res'],d['mean'],d['med']))
L.append('--- unconditional control on same split ---')
pr=prep(np.ones(N,bool),'train')
for hidx,H in enumerate(HS):
    r=run(pr,hidx*12,'all'); r2=run(pr,hidx*12,'first')
    L.append('H=%-3d all: n=%5d k=%3d mean=%+.4f med=%+.4f | first: n=%4d k=%3d mean=%+.4f med=%+.4f'%(
        H,r['n'],r['k'],r['mean'],r['median_trade'],r2['n'],r2['k'],r2['mean'],r2['median_trade']))
open(SP+'/b5.log','w').write('\n'.join(L))
