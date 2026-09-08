"""Neighbourhood robustness for the one cell that clears every gate, plus the best
3-way cells. A rule that only works at exactly one quartile edge is fragile."""
import numpy as np, json, sys, itertools
sys.path.insert(0,'/home/anont/meme/_c3')
from engine import load, net_array, evaluate
OUT='/home/anont/meme/_c3'
LG=open(OUT+'/robust.log','w')
def p(*a): LG.write(' '.join(str(x) for x in a)+'\n'); LG.flush()
P=load(); N=len(P['TS']); FN=P['FEATNAMES']
CN=[c[0] for c in P['COMBOS']]
TR=P['bar_h']==1
NET=[net_array(ci) for ci in range(len(CN))]
ENTVOL=np.nan_to_num(np.load(OUT+'/entvol.npy'),nan=0.0)
def edges(f,q):
    v=P['FEAT'][:,FN.index(f)][TR]; v=v[np.isfinite(v)]
    return np.quantile(v,np.linspace(0,1,q+1))
rv=P['FEAT'][:,FN.index('rvol10')]; cv=P['FEAT'][:,FN.index('cumvol_log')]
am=P['FEAT'][:,FN.index('age_min')]; va=P['FEAT'][:,FN.index('volaccel')]
p("rvol10 quartile edges     %s"%np.round(edges('rvol10',4),5))
p("cumvol_log quartile edges %s"%np.round(edges('cumvol_log',4),4))
p("age_min quartile edges    %s"%np.round(edges('age_min',4),1))
p("volaccel quartile edges   %s"%np.round(edges('volaccel',4),3))

def report(tag,mask,ci):
    r1=evaluate(mask,ci,NET[ci],hsel=1); r2=evaluate(mask,ci,NET[ci],hsel=2)
    l=mask&(ENTVOL>=600)
    q1=evaluate(l,ci,NET[ci],hsel=1); q2=evaluate(l,ci,NET[ci],hsel=2)
    p("   %-46s TR %s VA %s | liq600 TR %s VA %s (n%s k%s)"%(tag,
      ("%+7.4f(n%4d k%3d)"%(r1['mean'],r1['n'],r1['k'])) if r1 else "      n/a",
      ("%+7.4f(n%4d k%3d)"%(r2['mean'],r2['n'],r2['k'])) if r2 else "      n/a",
      ("%+7.4f"%q1['mean']) if q1 else "  n/a", ("%+7.4f"%q2['mean']) if q2 else "  n/a",
      q2['n'] if q2 else 0, q2['k'] if q2 else 0))

p("\n=== CANDIDATE 1: rvol10 in band x cumvol_log in band, t15_pyr (and neighbours) ===")
re_=edges('rvol10',4); ce=edges('cumvol_log',4)
for ci_name in ('t15_pyr','t15','t5','t30','t15h25','t30sl30'):
    ci=CN.index(ci_name)
    p("  exit %s"%ci_name)
    for lo,hi in ((re_[1],re_[2]),(re_[1]*0.7,re_[2]*1.3),(re_[0],re_[2]),(re_[1],re_[3])):
        for clo,chi in ((ce[2],ce[3]),(ce[2]*0.97,ce[3]*1.03),(ce[1],ce[3]),(ce[2],ce[4])):
            m=(rv>=lo)&(rv<hi)&(cv>=clo)&(cv<chi)
            report("rvol[%.4f,%.4f) cumvol[%.3f,%.3f)"%(lo,hi,clo,chi),m,ci)

p("\n=== CANDIDATE 2 (3-way): age_min=q0 & m_px0=1 & m_v0=1..2, t30sl30 (and neighbours) ===")
mv=P['META']
def terc(x):
    v=x[TR]; v=v[np.isfinite(v)]
    e=np.unique(np.quantile(v,[1/3,2/3])); return np.searchsorted(e,x,'right')
px0=terc(mv[:,4]); v0=terc(mv[:,5])
ae=edges('age_min',4)
for ci_name in ('t30sl30','t30','t15','t60sl30','t5'):
    ci=CN.index(ci_name)
    p("  exit %s"%ci_name)
    for ahi in (ae[1],ae[1]*1.5,ae[2]):
        for pxs in ((1,),(1,2),(0,1,2)):
            for v0s in ((2,),(1,2),(0,1,2)):
                m=(am<ahi)&np.isin(px0,pxs)&np.isin(v0,v0s)
                report("age<%.0fm px0in%s v0in%s"%(ahi,pxs,v0s),m,ci)

p("\n=== CANDIDATE 3 (3-way): volaccel=q3 & age_min=q0 & m_v0=2, t30sl30 ===")
ve=edges('volaccel',4)
for ci_name in ('t30sl30','t30','t15'):
    ci=CN.index(ci_name)
    p("  exit %s"%ci_name)
    for vlo in (ve[3],ve[2],ve[1]):
        for ahi in (ae[1],ae[1]*1.5,ae[2]):
            for v0s in ((2,),(1,2)):
                m=(va>=vlo)&(am<ahi)&np.isin(v0,v0s)
                report("volaccel>=%.2f age<%.0fm v0in%s"%(vlo,ahi,v0s),m,ci)
LG.close()
