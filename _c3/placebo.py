"""PLACEBO. Identical 3-way grid + identical train/validate/BH/gate funnel, but the
features are decoupled from the forward returns by a per-mint CIRCULAR SHIFT
(preserves each feature's within-mint autocorrelation and marginal distribution,
destroys its alignment with the forward return) and mint metadata is reassigned
to a different mint. Any survivor count here is the chance rate of the funnel."""
import numpy as np, json, time, sys, itertools, math
sys.path.insert(0,'/home/anont/meme/_c3')
import engine
from engine import load, net_array, evaluate, welch, base_sel
OUT='/home/anont/meme/_c3'
LG=open(OUT+'/placebo.log','w')
def p(*a): LG.write(' '.join(str(x) for x in a)+'\n'); LG.flush()
T0=time.time()
P=load(); N=len(P['TS']); FN=P['FEATNAMES']
CN=[c[0] for c in P['COMBOS']]
rng=np.random.default_rng(int(sys.argv[1]) if len(sys.argv)>1 else 2024)

# ---- build the placebo feature panel ----
mid=P['mint_id']; nm=P['nm']
starts=np.searchsorted(mid,np.arange(nm),'left'); ends=np.searchsorted(mid,np.arange(nm),'right')
F=P['FEAT'].copy()
for m in range(nm):
    a,b=starts[m],ends[m]
    n=b-a
    if n>2: F[a:b]=np.roll(P['FEAT'][a:b],int(rng.integers(1,n)),axis=0)
perm=rng.permutation(nm)
M=P['META'][starts[perm][mid]]          # mint m gets mint perm[m]'s metadata
P['FEAT']=F; P['META']=M
p("placebo panel built: FEAT circular-shifted per mint, META reassigned across mints")

TR=P['bar_h']==1
NET=[net_array(ci) for ci in range(len(CN))]
BASE={ci:evaluate(np.ones(N,bool),ci,NET[ci],hsel=1) for ci in range(len(CN))}
BASEV={ci:evaluate(np.ones(N,bool),ci,NET[ci],hsel=2) for ci in range(len(CN))}
def buckets(v,q):
    x=v[TR]; x=x[np.isfinite(x)]
    e=np.unique(np.quantile(x,np.linspace(0,1,q+1)[1:-1]))
    return np.searchsorted(e,v,'right').astype(np.int8), len(e)+1
B4={f:buckets(P['FEAT'][:,FN.index(f)],4) for f in FN}
mv=P['META']
MF={'m_ttg':buckets(mv[:,0],3),'m_hour':(((mv[:,1].astype(int))//6).astype(np.int8),4),
    'm_creator_prior':(np.clip(mv[:,2],0,2).astype(np.int8),3),
    'm_cohort10':buckets(mv[:,3],3),'m_px0':buckets(mv[:,4],3),'m_v0':buckets(mv[:,5],3)}
MK=list(MF)
BARF=json.load(open(OUT+'/phaseC.json'))['barf']
p("bar features:",BARF)
EXC=[CN.index(x) for x in ['t5','t15','t30','t60','t120','t30tp50','t60tr35','t30sl30',
                           't15h25','t60h50','t15_pyr','t30_avg','t60_pyr','t30tp50_avg']]
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
    return dict(desc=desc,ci=ci,tr_mean=r['mean'],tr_med=r['median'],tr_n=r['n'],tr_k=r['k'],
                base=b['mean'],edge=r['mean']-b['mean'],t=t,p=pv,mask=None)
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
                        d=('%s=q%d'%(a,i),'%s=q%d'%(b_,j),'%s=%d'%(mk,l))
                        r=cell(m,ci,d,sl)
                        if r: PC.append(r)
p("C1 done kept=%d swept=%d t=%.1f"%(len(PC),nsweep,time.time()-T0))
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
                        d=('%s=q%d'%(a,i),'%s=%d'%(mk1,u),'%s=%d'%(mk2,v))
                        r=cell(m,ci,d,sl)
                        if r: PC.append(r)
p("C2 done kept=%d swept=%d t=%.1f"%(len(PC),nsweep,time.time()-T0))

def mask_of(desc):
    m=np.ones(N,bool)
    for d in desc:
        k,v=d.split('=')
        if k in MF: b,_=MF[k]; m&=(b==int(v))
        else: b,_=B4[k]; m&=(b==int(v[1:]))
    return m
PRE=[r for r in PC if r['edge']>0 and r['p']==r['p'] and r['p']<0.05]
p("carried to validate: %d"%len(PRE))
res=[]
for r in PRE:
    m=mask_of(r['desc']); ci=r['ci']
    v=evaluate(m,ci,NET[ci],hsel=2)
    if v is None or v['n']<60 or v['k']<12: continue
    bv=BASEV[ci]; t,pv=welch(v['permint'],bv['permint'])
    res.append(dict(desc=r['desc'],ci=ci,tr_mean=r['tr_mean'],tr_med=r['tr_med'],
                    va_mean=v['mean'],va_med=v['median'],va_n=v['n'],va_k=v['k'],va_p=pv))
p("validated: %d t=%.1f"%(len(res),time.time()-T0))
pv=np.array([x['va_p'] if x['va_p']==x['va_p'] else 1.0 for x in res]) if res else np.array([1.0])
order=np.argsort(pv); mtot=len(pv); kmax=0
for rk,i in enumerate(order,1):
    if pv[i]<=0.10*rk/mtot: kmax=rk
S=set(order[:kmax].tolist())
for i,x in enumerate(res): x['bh']= i in S
p("\n=== PLACEBO FUNNEL (3-way arm only) ===")
p("  combos swept                      : %d"%nsweep)
p("  validated                         : %d"%len(res))
p("  BH-pass                           : %d"%sum(1 for x in res if x['bh']))
p("  BH-pass AND va>0                  : %d"%sum(1 for x in res if x['bh'] and x['va_mean']>0))
p("  BH-pass AND va>0 AND tr>0         : %d"%sum(1 for x in res if x['bh'] and x['va_mean']>0 and x['tr_mean']>0))
p("  BH AND va>0 AND tr>0 AND both med>0: %d"%sum(1 for x in res if x['bh'] and x['va_mean']>0 and x['tr_mean']>0 and x['va_med']>0 and x['tr_med']>0))
best=sorted([x for x in res if x['bh'] and x['va_mean']>0 and x['tr_mean']>0],key=lambda x:-min(x['tr_mean'],x['va_mean']))[:12]
for x in best:
    p("   %s | %s TR %+7.4f VA %+7.4f n%5d k%3d"%('|'.join(x['desc']),CN[x['ci']],x['tr_mean'],x['va_mean'],x['va_n'],x['va_k']))
json.dump(dict(nsweep=nsweep,res=[{k:v for k,v in x.items()} for x in res]),open(OUT+'/placebo.json','w'),default=str)
p("t=%.1f"%(time.time()-T0))
