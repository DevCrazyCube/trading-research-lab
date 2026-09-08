"""Map the response surface: 1-way marginals for every feature x horizon,
computed with the full harness, on TRAIN and VALIDATE separately."""
import numpy as np, sys, json
sys.path.insert(0,'/home/anont/meme/_c3')
from engine import load, net_array, evaluate
OUT='/home/anont/meme/_c3'
LG=open(OUT+'/surface.log','w')
def p(*a): LG.write(' '.join(str(x) for x in a)+'\n'); LG.flush()
P=load(); N=len(P['TS']); FN=P['FEATNAMES']
CN=[c[0] for c in P['COMBOS']]
TR=P['bar_h']==1
NET={ci:net_array(ci) for ci in range(len(CN))}
def buckets(v,q):
    x=v[TR]; x=x[np.isfinite(x)]
    e=np.unique(np.quantile(x,np.linspace(0,1,q+1)[1:-1]))
    return np.searchsorted(e,v,'right').astype(np.int8), len(e)+1, e
HOR=['t5','t15','t30','t60','t120']
p("=== 1-way marginal surface: mint-equal mean net (cap +300%, drop -30%, toll 1.14%) ===")
p("rows = feature quintile, cols = %s ; TR|VA"%HOR)
for f in FN:
    b,nb,e=buckets(P['FEAT'][:,FN.index(f)],5)
    p("\n%s  edges=%s"%(f,np.round(e,4)))
    for k in range(nb):
        m=(b==k); row=[]
        for hn in HOR:
            ci=CN.index(hn)
            rt=evaluate(m,ci,NET[ci],hsel=1); rv=evaluate(m,ci,NET[ci],hsel=2)
            row.append("%s|%s"%("%+.3f"%rt['mean'] if rt else "  n/a","%+.3f"%rv['mean'] if rv else "  n/a"))
        n_=int(m.sum())
        p("  q%d n=%5d  %s"%(k,n_,'  '.join(row)))
mv=P['META']
MF={}
MF['m_ttg']=buckets(mv[:,0],3)[:2]
MF['m_hour']=(((mv[:,1].astype(int))//6).astype(np.int8),4)
MF['m_creator_prior']=(np.clip(mv[:,2],0,2).astype(np.int8),3)
MF['m_cohort10']=buckets(mv[:,3],3)[:2]
MF['m_px0']=buckets(mv[:,4],3)[:2]
MF['m_v0']=buckets(mv[:,5],3)[:2]
p("\n=== METADATA marginals ===")
for k,(b,nb) in MF.items():
    p("\n%s"%k)
    for j in range(nb):
        m=(b==j); row=[]
        for hn in HOR:
            ci=CN.index(hn)
            rt=evaluate(m,ci,NET[ci],hsel=1); rv=evaluate(m,ci,NET[ci],hsel=2)
            row.append("%s|%s"%("%+.3f"%rt['mean'] if rt else "  n/a","%+.3f"%rv['mean'] if rv else "  n/a"))
        p("  b%d n=%5d  %s"%(j,int(m.sum()),'  '.join(row)))
p("\n=== EXIT-STRUCTURE surface on ALL bars (the random-entry control) ===")
for ci,nm in enumerate(CN):
    rt=evaluate(np.ones(N,bool),ci,NET[ci],hsel=1); rv=evaluate(np.ones(N,bool),ci,NET[ci],hsel=2)
    p("  %-20s TR %+7.4f (med %+7.4f) | VA %+7.4f (med %+7.4f)  n %5d/%5d res %.3f/%.3f"%(
        nm,rt['mean'],rt['median'],rv['mean'],rv['median'],rt['n'],rv['n'],rt['res'],rv['res']))
LG.close()
