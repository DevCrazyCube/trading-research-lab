import numpy as np, json, time, sys, itertools, math, pickle
sys.path.insert(0,'/home/anont/meme/_c3')
from engine import load, net_array, evaluate, welch, base_sel

OUT='/home/anont/meme/_c3'
LG=open(OUT+'/sweepBC.log','w')
def p(*a): LG.write(' '.join(str(x) for x in a)+'\n'); LG.flush()
T0=time.time()
P=load(); N=len(P['TS']); FN=P['FEATNAMES']
CN=[c[0] for c in P['COMBOS']]
TR=P['bar_h']==1
NET=[net_array(ci) for ci in range(len(CN))]
BASE={}
for ci in range(len(CN)):
    for hh,tag in ((1,'tr'),(2,'va')):
        BASE[(ci,tag)]=evaluate(np.ones(N,bool),ci,NET[ci],hsel=hh)

def buckets(vals,q):
    v=vals[TR]; v=v[np.isfinite(v)]
    e=np.unique(np.quantile(v,np.linspace(0,1,q+1)[1:-1]))
    return np.searchsorted(e,vals,'right').astype(np.int8), len(e)+1

B4={f:buckets(P['FEAT'][:,FN.index(f)],4) for f in FN}
mv=P['META']
MF={}
MF['m_ttg']=buckets(mv[:,0],3)
MF['m_hour']=(((mv[:,1].astype(int))//6).astype(np.int8),4)
MF['m_creator_prior']=(np.clip(mv[:,2],0,2).astype(np.int8),3)
MF['m_cohort10']=buckets(mv[:,3],3)
MF['m_px0']=buckets(mv[:,4],3)
MF['m_v0']=buckets(mv[:,5],3)
MK=list(MF)

MINN=120; MINK=20
nsweep=0
def cell(mask,ci,desc,sel):
    global nsweep
    nsweep+=1
    r=evaluate(mask,ci,NET[ci],hsel=1,sel=sel)
    if r is None or r['n']<MINN or r['k']<MINK: return None
    b=BASE[(ci,'tr')]
    if r['mean']<=b['mean']: return None
    t,pv=welch(r['permint'],b['permint'])
    return dict(desc=desc,ci=ci,combo=CN[ci],tr_mean=r['mean'],tr_med=r['median'],
                tr_n=r['n'],tr_k=r['k'],tr_res=r['res'],base=b['mean'],
                edge=r['mean']-b['mean'],t=t,p=pv)

EX_MAIN=[CN.index(x) for x in ['t5','t15','t30','t60','t120','t30tp50','t60tr35','t30sl30',
                               't15h25','t60h50','t15_pyr','t30_avg']]

# ---------------- PHASE B : 2-way (bar x bar, and bar x meta) ----------------
PB=[]
for a,b_ in itertools.combinations(FN,2):
    ba,na=B4[a]; bb,nb=B4[b_]
    for i in range(na):
        ma=(ba==i)
        for j in range(nb):
            m=ma&(bb==j)
            sl=base_sel(m,1)
            if len(sl)<MINN: continue
            for ci in EX_MAIN:
                r=cell(m,ci,('%s=q%d'%(a,i),'%s=q%d'%(b_,j)),sl)
                if r: PB.append(r)
p("B bar x bar done kept=%d swept=%d t=%.1f"%(len(PB),nsweep,time.time()-T0))
for a in FN:
    ba,na=B4[a]
    for i in range(na):
        ma=(ba==i)
        for mk in MK:
            bm,nmv=MF[mk]
            for l in range(nmv):
                m=ma&(bm==l)
                sl=base_sel(m,1)
                if len(sl)<MINN: continue
                for ci in EX_MAIN:
                    r=cell(m,ci,('%s=q%d'%(a,i),'%s=%d'%(mk,l)),sl)
                    if r: PB.append(r)
p("PHASE B: kept %d, swept %d, t=%.1f"%(len(PB),nsweep,time.time()-T0))
PB.sort(key=lambda x:-(x['t'] if x['t']==x['t'] else -9))
for r in PB[:60]:
    p("  B %-38s %-12s tr %+7.4f med %+7.4f base %+7.4f edge %+7.4f n %5d k %3d p %.4f"%(
        '|'.join(r['desc']),r['combo'],r['tr_mean'],r['tr_med'],r['base'],r['edge'],r['tr_n'],r['tr_k'],r['p']))
json.dump(PB,open(OUT+'/phaseB.json','w'),default=str)

sig=set()
for r in PB:
    if r['p']<0.20:
        for d in r['desc']: sig.add(d.split('=')[0])
sig=[f for f in FN if f in sig]
p("features with ANY 2-way signal:",sig)
json.dump(dict(sig=sig,nsweepB=nsweep),open(OUT+'/sigB.json','w'))
p("t=%.1f"%(time.time()-T0))
