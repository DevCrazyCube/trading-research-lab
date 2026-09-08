"""PHASE C-LIQ -- the identical 3-way grid, but restricted to entry bars where a
$60 order is <=10% of that minute's traded volume (entry-bar volume >= $600).
This is the only arm in which the rule could actually be filled."""
import numpy as np, json, time, sys, itertools, math
sys.path.insert(0,'/home/anont/meme/_c3')
from engine import load, net_array, evaluate, welch, base_sel

OUT='/home/anont/meme/_c3'
LG=open(OUT+'/sweepCliq.log','w')
def p(*a): LG.write(' '.join(str(x) for x in a)+'\n'); LG.flush()
T0=time.time()
P=load(); N=len(P['TS']); FN=P['FEATNAMES']
CN=[c[0] for c in P['COMBOS']]
TR=P['bar_h']==1
ENTVOL=np.load(OUT+'/entvol.npy')
LIQ=np.nan_to_num(ENTVOL,nan=0.0)>=600.0
p("tradable bars: %d of %d (%.1f%%)"%(LIQ.sum(),N,100*LIQ.mean()))
NET=[net_array(ci) for ci in range(len(CN))]
BASE={ci:evaluate(LIQ,ci,NET[ci],hsel=1) for ci in range(len(CN))}
BASEV={ci:evaluate(LIQ,ci,NET[ci],hsel=2) for ci in range(len(CN))}
for ci,nm in enumerate(CN):
    p("BASE-LIQ %-14s TR %+7.4f med %+7.4f n %5d k %3d | VA %+7.4f med %+7.4f n %5d k %3d"%(
        nm,BASE[ci]['mean'],BASE[ci]['median'],BASE[ci]['n'],BASE[ci]['k'],
        BASEV[ci]['mean'],BASEV[ci]['median'],BASEV[ci]['n'],BASEV[ci]['k']))

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
try:
    BARF=json.load(open(OUT+'/phaseC.json'))['barf']
except Exception:
    BARF=FN[:9]
p("bar features:",BARF)

MINN=60; MINK=12
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

for a,b_ in itertools.combinations(BARF,2):
    ba,na=B4[a]; bb,nb=B4[b_]
    for i in range(na):
        ma=LIQ&(ba==i)
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
    p("  L1 %s x %s kept=%d swept=%d t=%.1f"%(a,b_,len(PC),nsweep,time.time()-T0))
n1=nsweep
for a in BARF:
    ba,na=B4[a]
    for i in range(na):
        ma=LIQ&(ba==i)
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
    p("  L2 %s kept=%d swept=%d t=%.1f"%(a,len(PC),nsweep,time.time()-T0))
p("C-LIQ done kept=%d swept=%d (L1=%d L2=%d) t=%.1f"%(len(PC),nsweep,n1,nsweep-n1,time.time()-T0))

# ---- validate every train-positive tradable cell ----
def mask_of(desc):
    m=LIQ.copy()
    for d in desc:
        k,v=d.split('=')
        if k in MF: b,_=MF[k]; m&=(b==int(v))
        else: b,_=B4[k]; m&=(b==int(v[1:]))
    return m
PRE=[r for r in PC if r['p']==r['p'] and r['p']<0.05]
p("carried to validate: %d"%len(PRE))
out=[]
for r in PRE:
    m=mask_of([str(x) for x in r['desc']]); ci=r['ci']
    v=evaluate(m,ci,NET[ci],hsel=2)
    if v is None or v['n']<40 or v['k']<10: continue
    bv=BASEV[ci]; t,pv=welch(v['permint'],bv['permint'])
    out.append(dict(**{k:r[k] for k in ('desc','ci','combo','tr_mean','tr_med','tr_n','tr_k','base','edge','p')},
                    va_mean=v['mean'],va_med=v['median'],va_n=v['n'],va_k=v['k'],va_res=v['res'],
                    va_base=bv['mean'],va_edge=v['mean']-bv['mean'],va_t=t,va_p=pv))
pv=np.array([x['va_p'] if x['va_p']==x['va_p'] else 1.0 for x in out]) if out else np.array([1.0])
order=np.argsort(pv); mtot=len(pv); kmax=0
for rk,i in enumerate(order,1):
    if pv[i]<=0.10*rk/mtot: kmax=rk
for i,x in enumerate(out): x['bh_pass']=(i in set(order[:kmax].tolist()))
p("BH q=0.10 on the tradable arm: %d of %d"%(kmax,len(out)))
out.sort(key=lambda x:-(x['va_t'] if x['va_t']==x['va_t'] else -9))
for x in out[:60]:
    p("  L %-54s %-14s TR %+7.4f | VA %+7.4f (med %+7.4f) base %+7.4f edge %+7.4f n %4d k %3d p %.4f BH=%s"%(
        '|'.join(x['desc']),x['combo'],x['tr_mean'],x['va_mean'],x['va_med'],x['va_base'],x['va_edge'],x['va_n'],x['va_k'],x['va_p'],x['bh_pass']))
p("POSITIVE validate mean AND BH pass: %d"%sum(1 for x in out if x['bh_pass'] and x['va_mean']>0))
json.dump(dict(cells=PC,validated=out,nsweep=nsweep),open(OUT+'/phaseCliq.json','w'),default=str)
p("t=%.1f"%(time.time()-T0))
