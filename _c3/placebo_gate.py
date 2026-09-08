"""Apply the EXACT final gate (both splits >0, BH, bootstrap CI-lo>0, tradable at
$600 and positive on both splits there) to the placebo survivors, so the real
arm's survivor count can be read against the funnel's own chance rate."""
import numpy as np, json, sys
sys.path.insert(0,'/home/anont/meme/_c3')
from engine import load, net_array, evaluate
OUT='/home/anont/meme/_c3'
seed=int(sys.argv[1]); src=sys.argv[2]
LG=open(OUT+'/placebo_gate_%d.log'%seed,'w')
def p(*a): LG.write(' '.join(str(x) for x in a)+'\n'); LG.flush()
P=load(); N=len(P['TS']); FN=P['FEATNAMES']
CN=[c[0] for c in P['COMBOS']]
rng=np.random.default_rng(seed)
mid=P['mint_id']; nm=P['nm']
starts=np.searchsorted(mid,np.arange(nm),'left'); ends=np.searchsorted(mid,np.arange(nm),'right')
F=P['FEAT'].copy()
for m in range(nm):
    a,b=starts[m],ends[m]; n=b-a
    if n>2: F[a:b]=np.roll(P['FEAT'][a:b],int(rng.integers(1,n)),axis=0)
perm=rng.permutation(nm)
M=P['META'][starts[perm][mid]]
P['FEAT']=F; P['META']=M
TR=P['bar_h']==1
NET=[net_array(ci) for ci in range(len(CN))]
ENTVOL=np.nan_to_num(np.load(OUT+'/entvol.npy'),nan=0.0)
def buckets(v,q):
    x=v[TR]; x=x[np.isfinite(x)]
    e=np.unique(np.quantile(x,np.linspace(0,1,q+1)[1:-1]))
    return np.searchsorted(e,v,'right').astype(np.int8), len(e)+1
B4={f:buckets(P['FEAT'][:,FN.index(f)],4) for f in FN}
mv=P['META']
MF={'m_ttg':buckets(mv[:,0],3),'m_hour':(((mv[:,1].astype(int))//6).astype(np.int8),4),
    'm_creator_prior':(np.clip(mv[:,2],0,2).astype(np.int8),3),
    'm_cohort10':buckets(mv[:,3],3),'m_px0':buckets(mv[:,4],3),'m_v0':buckets(mv[:,5],3)}
def mask_of(desc):
    m=np.ones(N,bool)
    for d in desc:
        k,v=d.split('=')
        if k in MF: b,_=MF[k]; m&=(b==int(v))
        else: b,_=B4[k]; m&=(b==int(v[1:]))
    return m
D=json.load(open(OUT+'/'+src))
res=D['res']
pv=np.array([float(x['va_p']) if x['va_p']==x['va_p'] else 1.0 for x in res])
o=np.argsort(pv); mt=len(pv); k=0
for r,i in enumerate(o,1):
    if pv[i]<=0.10*r/mt: k=r
S=set(o[:k].tolist())
cand=[x for i,x in enumerate(res) if i in S and float(x['va_mean'])>0 and float(x['tr_mean'])>0]
p("placebo seed %d: both-splits-positive BH survivors = %d"%(seed,len(cand)))
rb=np.random.default_rng(99)
full=0; rows=[]
for x in cand:
    desc=[str(y) for y in x['desc']]; ci=int(x['ci']); m=mask_of(desc)
    v=evaluate(m,ci,NET[ci],hsel=2)
    if v is None: continue
    pm=v['permint']; K=len(pm)
    bs=np.array([pm[rb.integers(0,K,K)].mean() for _ in range(2000)])
    lo=float(np.quantile(bs,0.025))
    mm=m&(ENTVOL>=600)
    r1=evaluate(mm,ci,NET[ci],hsel=1); r2=evaluate(mm,ci,NET[ci],hsel=2)
    ok = lo>0 and r1 is not None and r2 is not None and r1['mean']>0 and r2['mean']>0
    if ok:
        full+=1
        rows.append("   %s | %s TR %+7.4f VA %+7.4f liq600 TR %+7.4f VA %+7.4f (n%d k%d) bootlo %+7.4f"%(
            '|'.join(desc),CN[ci],float(x['tr_mean']),float(x['va_mean']),r1['mean'],r2['mean'],r2['n'],r2['k'],lo))
p("placebo seed %d: cells clearing the FULL gate = %d"%(seed,full))
for r in rows: p(r)
LG.close()
