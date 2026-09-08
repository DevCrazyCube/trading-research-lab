import sys,json; sys.path.insert(0,'/home/anont/meme/.fc3')
import numpy as np
from lib2 import *
N=len(F)
def band(c,lo,hi):
    v=F[:,c]; return (v>=lo)&(v<hi)
ONE=np.ones(N,bool)
gB=json.load(open(SP+'/gridB.json')); q1,q2=gB['q1'],gB['q2']
A={'age':{'any':ONE,'0-3':band(AGE,-1e9,3),'3-10':band(AGE,3,10),'10-30':band(AGE,10,30),'30-120':band(AGE,30,120),
          '120-480':band(AGE,120,480),'480+':band(AGE,480,1e18)},
   'dd':{'any':ONE,'.9-1':band(DD,0.9,1e18),'.6-.9':band(DD,0.6,0.9),'.3-.6':band(DD,0.3,0.6),'.1-.3':band(DD,0.1,0.3),'<.1':band(DD,-1e9,0.1)},
   'lvl':{'any':ONE,'<.3':band(LVL,-1e9,0.3),'.3-1':band(LVL,0.3,1.0),'1-3':band(LVL,1.0,3.0),'3+':band(LVL,3.0,1e18)},
   'rv':{'any':ONE,'<.02':band(RELV,-1e9,0.02),'.02-.2':band(RELV,0.02,0.2),'.2-.7':band(RELV,0.2,0.7),'.7+':band(RELV,0.7,1e18)},
   'agef':{'any':ONE,'0-1':band(AGE,-1e9,1),'1-3':band(AGE,1,3),'3-6':band(AGE,3,6),'6-10':band(AGE,6,10),
           '10-20':band(AGE,10,20),'20-30':band(AGE,20,30),'30-60':band(AGE,30,60),'60+':band(AGE,60,1e18)},
   'pri':{'any':ONE,'0':band(PRI,-1,0.5),'1-5':band(PRI,0.5,5.5),'6+':band(PRI,5.5,1e9)},
   'prig':{'any':ONE,'0':band(PRIG,-1,0.5),'1+':band(PRIG,0.5,1e9)},
   'v0':{'any':ONE,'lo':band(V0,-1e9,q1),'mid':band(V0,q1,q2),'hi':band(V0,q2,1e18)}}
def ex1(r):
    pm=r['pm']
    if len(pm)<3: return None
    return float(np.sort(pm)[:-1].mean())
rows=[]
for d in json.load(open(SP+'/val.json')):
    if not(d['v_mean']>0 and d['v_cilo']>0 and d['v_mean']>d['ctrl_matched']): continue
    m=A['age'][d['age']]&A['dd'][d['dd']]&A['lvl'][d['lvl']]&A['rv'][d['rv']]
    rows.append(('A',d,m))
for d in json.load(open(SP+'/valB.json')):
    if not(d['v_mean']>0 and d['v_cilo']>0 and d['ctrl_matched'] is not None and d['v_mean']>d['ctrl_matched']): continue
    m=A['agef'][d['age']]&A['pri'][d['pri']]&A['prig'][d['prig']]&A['v0'][d['v0']]&A['dd'][d['dd']]
    rows.append(('B',d,m))
L=['checking %d validated survivors for single-mint dependence'%len(rows)]
keep=[]
for g,d,m in rows:
    k=EX.index((d['H'],d['tp'],d['sl']))
    rt=run(prep(m,'train'),k,d['mode']); rv=run(prep(m,'validate'),k,d['mode'])
    if rt is None or rv is None: continue
    et,ev=ex1(rt),ex1(rv)
    if et is None or ev is None: continue
    tag='%s %s'%(g,{kk:vv for kk,vv in d.items() if kk in ('age','dd','lvl','rv','pri','prig','v0','H','tp','sl','mode')})
    if et>0.03 and ev>0.03: keep.append((et,ev,tag,rt['mean'],rv['mean'],rt['k'],rv['k']))
L.append('survivors whose train AND validate mean stay > +3%% after dropping their single best mint: %d'%len(keep))
keep.sort(key=lambda x:-min(x[0],x[1]))
for et,ev,tag,tm,vm,tk,vk in keep[:20]:
    L.append('  TRm=%+.4f->%+.4f (k=%d) | VAm=%+.4f->%+.4f (k=%d) | %s'%(tm,et,tk,vm,ev,vk,tag))
open(SP+'/b15.log','w').write('\n'.join(L))
