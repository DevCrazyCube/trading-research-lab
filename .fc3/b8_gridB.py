import sys,time,json; sys.path.insert(0,'/home/anont/meme/.fc3')
import numpy as np
from lib2 import *
t0=time.time(); N=len(F)
def band(c,lo,hi):
    v=F[:,c]; return (v>=lo)&(v<hi)
ONE=np.ones(N,bool)
# v0 terciles from TRAIN mints only
trmask=np.isin(mi,TRAIN)
v0m=[]
for m in TRAIN:
    s,e=starts[m],ends[m]
    if e>s: v0m.append(F[s,V0])
q1,q2=np.quantile(v0m,[1/3,2/3])
AX={}
AX['agef']=[('any',ONE),('0-1',band(AGE,-1e9,1)),('1-3',band(AGE,1,3)),('3-6',band(AGE,3,6)),('6-10',band(AGE,6,10)),
            ('10-20',band(AGE,10,20)),('20-30',band(AGE,20,30)),('30-60',band(AGE,30,60)),('60+',band(AGE,60,1e18))]
AX['pri']=[('any',ONE),('0',band(PRI,-1,0.5)),('1-5',band(PRI,0.5,5.5)),('6+',band(PRI,5.5,1e9))]
AX['prig']=[('any',ONE),('0',band(PRIG,-1,0.5)),('1+',band(PRIG,0.5,1e9))]
AX['v0']=[('any',ONE),('lo',band(V0,-1e9,q1)),('mid',band(V0,q1,q2)),('hi',band(V0,q2,1e18))]
AX['dd']=[('any',ONE),('.9-1',band(DD,0.9,1e18)),('<.1',band(DD,-1e9,0.1))]
out=[];ncomb=0
for an,am in AX['agef']:
    for pn,pm_ in AX['pri']:
        m1=am&pm_
        if m1.sum()<40: continue
        for gn,gm in AX['prig']:
            m2=m1&gm
            if m2.sum()<40: continue
            for vn,vm in AX['v0']:
                m3=m2&vm
                if m3.sum()<40: continue
                for dn,dm in AX['dd']:
                    m4=m3&dm
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
                            out.append([an,pn,gn,vn,dn,H,tp,sl,mode,r['mean'],r['median_trade'],r['n'],r['k'],r['res'],lo])
json.dump(dict(ncomb=ncomb,rows=out,q1=float(q1),q2=float(q2)),open(SP+'/gridB.json','w'))
o2=[r for r in out if r[14]>0]
L=['gridB combos=%d posmean=%d cilo>0=%d time=%.1fs v0 terciles %.3g %.3g'%(ncomb,len(out),len(o2),time.time()-t0,q1,q2)]
o2.sort(key=lambda r:-r[14])
for r in o2[:30]:
    L.append('age=%-6s pri=%-4s prig=%-4s v0=%-4s dd=%-5s H=%-3d tp=%-5s sl=%-5s %-5s n=%4d k=%3d mean=%+.4f med=%+.4f cilo=%+.4f'%(
        r[0],r[1],r[2],r[3],r[4],r[5],str(r[6]),str(r[7]),r[8],r[11],r[12],r[9],r[10],r[14]))
open(SP+'/b8.log','w').write('\n'.join(L))
