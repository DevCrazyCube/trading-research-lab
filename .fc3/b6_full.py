import sys,time,json,pickle; sys.path.insert(0,'/home/anont/meme/.fc3')
import numpy as np
from lib2 import *
t0=time.time(); N=len(F)
def band(c,lo,hi):
    v=F[:,c]; return (v>=lo)&(v<hi)
ONE=np.ones(N,bool)
AX_age=[('any',ONE),('0-3',band(AGE,-1e9,3)),('3-10',band(AGE,3,10)),('10-30',band(AGE,10,30)),
        ('30-120',band(AGE,30,120)),('120-480',band(AGE,120,480)),('480+',band(AGE,480,1e18))]
AX_dd=[('any',ONE),('.9-1',band(DD,0.9,1e18)),('.6-.9',band(DD,0.6,0.9)),('.3-.6',band(DD,0.3,0.6)),
       ('.1-.3',band(DD,0.1,0.3)),('<.1',band(DD,-1e9,0.1))]
AX_lvl=[('any',ONE),('<.3',band(LVL,-1e9,0.3)),('.3-1',band(LVL,0.3,1.0)),('1-3',band(LVL,1.0,3.0)),('3+',band(LVL,3.0,1e18))]
AX_rv=[('any',ONE),('<.02',band(RELV,-1e9,0.02)),('.02-.2',band(RELV,0.02,0.2)),('.2-.7',band(RELV,0.2,0.7)),('.7+',band(RELV,0.7,1e18))]
out=[]; ncomb=0
for an,am in AX_age:
    for dn,dm in AX_dd:
        m2=am&dm
        if m2.sum()<40: continue
        for ln,lm in AX_lvl:
            m3=m2&lm
            if m3.sum()<40: continue
            for rn,rm in AX_rv:
                m4=m3&rm
                if m4.sum()<40: continue
                pr=prep(m4,'train')
                if len(pr)<15: continue
                for k in range(len(EX)):
                    H,tp,sl=EX[k]
                    for mode in ('all','first'):
                        r=run(pr,k,mode); ncomb+=1
                        if r is None or r['k']<15 or r['n']<40: continue
                        if r['mean']<=0: continue
                        lo=boot_lo(r['pm'],B=600,seed=1)
                        out.append([an,dn,ln,rn,H,tp,sl,mode,r['mean'],r['median_trade'],r['n'],r['k'],r['res'],lo])
json.dump(dict(ncomb=ncomb,rows=out,t=time.time()-t0),open(SP+'/grid_full.json','w'))
L=['full-train combos=%d positive-mean kept=%d time=%.1fs'%(ncomb,len(out),time.time()-t0)]
o2=[r for r in out if r[13]>0]
L.append('with bootstrap CI-lo>0: %d'%len(o2))
o2.sort(key=lambda r:-r[13])
L.append('--- top 45 by train CI-lo ---')
for r in o2[:45]:
    L.append('age=%-8s dd=%-5s lvl=%-5s rv=%-6s H=%-3d tp=%-5s sl=%-5s %-5s n=%4d k=%3d res=%.2f mean=%+.4f med=%+.4f cilo=%+.4f'%(
        r[0],r[1],r[2],r[3],r[4],str(r[5]),str(r[6]),r[7],r[10],r[11],r[12],r[8],r[9],r[13]))
open(SP+'/b6.log','w').write('\n'.join(L))
