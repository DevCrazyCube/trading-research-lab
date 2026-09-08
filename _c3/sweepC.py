"""PHASE C -- the assigned slice: systematic 3-WAY combinations,
biased toward interactions between bar features and MINT METADATA."""
import numpy as np, json, time, sys, itertools, math
sys.path.insert(0,'/home/anont/meme/_c3')
from engine import load, net_array, evaluate, welch, base_sel

OUT='/home/anont/meme/_c3'
LG=open(OUT+'/sweepC.log','w')
def p(*a): LG.write(' '.join(str(x) for x in a)+'\n'); LG.flush()
T0=time.time()
P=load(); N=len(P['TS']); FN=P['FEATNAMES']
CN=[c[0] for c in P['COMBOS']]
TR=P['bar_h']==1
NET=[net_array(ci) for ci in range(len(CN))]
BASE={ci:evaluate(np.ones(N,bool),ci,NET[ci],hsel=1) for ci in range(len(CN))}

def buckets(vals,q):
    v=vals[TR]; v=v[np.isfinite(v)]
    e=np.unique(np.quantile(v,np.linspace(0,1,q+1)[1:-1]))
    return np.searchsorted(e,vals,'right').astype(np.int8), len(e)+1

# rank features by the STRONGEST 2-way evidence they participate in (phase B t-stat),
# not by their index order.
PB=json.load(open(OUT+'/phaseB.json'))
best={}
for r in PB:
    t=r['t']
    if t!=t: continue
    for d in r['desc']:
        f=d.split('=')[0]
        if f in FN: best[f]=max(best.get(f,-9),t)
BARF=[f for f,_ in sorted(best.items(),key=lambda x:-x[1])][:10]
if len(BARF)<3: BARF=FN[:10]
p("2-way strength ranking:",sorted(best.items(),key=lambda x:-x[1]))
p("3-way bar features:",BARF)

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

MINN=100; MINK=15
nsweep=0; PC=[]
def cell(mask,ci,desc,sel):
    global nsweep
    nsweep+=1
    r=evaluate(mask,ci,NET[ci],hsel=1,sel=sel)
    if r is None or r['n']<MINN or r['k']<MINK: return None
    b=BASE[ci]
    if r['mean']<=b['mean']: return None
    t,pv=welch(r['permint'],b['permint'])
    return dict(desc=desc,ci=ci,combo=CN[ci],tr_mean=r['mean'],tr_med=r['median'],
                tr_n=r['n'],tr_k=r['k'],tr_res=r['res'],base=b['mean'],
                edge=r['mean']-b['mean'],t=t,p=pv)

EXC=[CN.index(x) for x in ['t5','t15','t30','t60','t120','t30tp50','t60tr35','t30sl30',
                           't15h25','t60h50','t15_pyr','t30_avg','t60_pyr','t30tp50_avg']]

# ---- C1: bar x bar x meta ----
for a,b_ in itertools.combinations(BARF,2):
    ba,na=B4[a]; bb,nb=B4[b_]
    for i in range(na):
        ma=(ba==i)
        for j in range(nb):
            mab=ma&(bb==j)
            if mab.sum()<MINN: continue
            for mk in MK:
                bm,nmv=MF[mk]
                for l in range(nmv):
                    m=mab&(bm==l)
                    sl=base_sel(m,1)
                    if len(sl)<MINN: continue
                    for ci in EXC:
                        r=cell(m,ci,('%s=q%d'%(a,i),'%s=q%d'%(b_,j),'%s=%d'%(mk,l)),sl)
                        if r: PC.append(r)
    p("  C1 %s x %s kept=%d swept=%d t=%.1f"%(a,b_,len(PC),nsweep,time.time()-T0))
p("C1 done kept=%d swept=%d t=%.1f"%(len(PC),nsweep,time.time()-T0))
n1=nsweep

# ---- C2: bar x meta x meta ----
for a in BARF:
    ba,na=B4[a]
    for i in range(na):
        ma=(ba==i)
        for mk1,mk2 in itertools.combinations(MK,2):
            b1,q1=MF[mk1]; b2,q2=MF[mk2]
            for u in range(q1):
                mu=ma&(b1==u)
                if mu.sum()<MINN: continue
                for v in range(q2):
                    m=mu&(b2==v)
                    sl=base_sel(m,1)
                    if len(sl)<MINN: continue
                    for ci in EXC:
                        r=cell(m,ci,('%s=q%d'%(a,i),'%s=%d'%(mk1,u),'%s=%d'%(mk2,v)),sl)
                        if r: PC.append(r)
    p("  C2 %s kept=%d swept=%d t=%.1f"%(a,len(PC),nsweep,time.time()-T0))
p("C2 done kept=%d swept=%d (C1=%d C2=%d) t=%.1f"%(len(PC),nsweep,n1,nsweep-n1,time.time()-T0))

PC.sort(key=lambda x:-(x['t'] if x['t']==x['t'] else -9))
for r in PC[:80]:
    p("  C %-52s %-14s tr %+7.4f med %+7.4f base %+7.4f edge %+7.4f n %5d k %3d p %.4f"%(
        '|'.join(r['desc']),r['combo'],r['tr_mean'],r['tr_med'],r['base'],r['edge'],r['tr_n'],r['tr_k'],r['p']))
json.dump(dict(cells=PC,nsweep=nsweep,barf=BARF),open(OUT+'/phaseC.json','w'),default=str)
p("t=%.1f"%(time.time()-T0))
