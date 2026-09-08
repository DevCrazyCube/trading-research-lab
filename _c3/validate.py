import numpy as np, json, time, sys, math, itertools
sys.path.insert(0,'/home/anont/meme/_c3')
from engine import load, net_array, evaluate, welch

OUT='/home/anont/meme/_c3'
LG=open(OUT+'/validate.log','w')
def p(*a): LG.write(' '.join(str(x) for x in a)+'\n'); LG.flush()
T0=time.time()
P=load(); N=len(P['TS']); FN=P['FEATNAMES']
CN=[c[0] for c in P['COMBOS']]
TR=P['bar_h']==1
NET=[net_array(ci) for ci in range(len(CN))]
BASEV={ci:evaluate(np.ones(N,bool),ci,NET[ci],hsel=2) for ci in range(len(CN))}
BASET={ci:evaluate(np.ones(N,bool),ci,NET[ci],hsel=1) for ci in range(len(CN))}

def buckets(vals,q):
    v=vals[TR]; v=v[np.isfinite(v)]
    e=np.unique(np.quantile(v,np.linspace(0,1,q+1)[1:-1]))
    return np.searchsorted(e,vals,'right').astype(np.int8), len(e)+1
B4={f:buckets(P['FEAT'][:,FN.index(f)],4) for f in FN}
B6={f:buckets(P['FEAT'][:,FN.index(f)],6) for f in FN}
mv=P['META']
MF={}
MF['m_ttg']=buckets(mv[:,0],3)
MF['m_hour']=(((mv[:,1].astype(int))//6).astype(np.int8),4)
MF['m_creator_prior']=(np.clip(mv[:,2],0,2).astype(np.int8),3)
MF['m_cohort10']=buckets(mv[:,3],3)
MF['m_px0']=buckets(mv[:,4],3)
MF['m_v0']=buckets(mv[:,5],3)

def mask_of(desc):
    m=np.ones(N,bool)
    for d in desc:
        k,v=d.split('=')
        if k in MF:
            b,_=MF[k]; m &= (b==int(v))
        else:
            q=int(v[1:])
            if '/' in v:  # phaseA form qK/NB
                q=int(v[1:].split('/')[0])
            src = B6 if ('/' in v) else B4
            b,_=src[k]; m &= (b==q)
    return m

cells=[]
try:
    A=json.load(open(OUT+'/phaseA.json'))
    for r in A: r['phase']='A'; cells.append(r)
except Exception as e: p("noA",e)
try:
    B=json.load(open(OUT+'/phaseB.json'))
    for r in B: r['phase']='B'; cells.append(r)
except Exception as e: p("noB",e)
try:
    C=json.load(open(OUT+'/phaseC.json'))['cells']
    for r in C: r['phase']='C'; cells.append(r)
except Exception as e: p("noC",e)
p("total train-kept cells:",len(cells))

PRE=[r for r in cells if r['edge']>0 and r['p']==r['p'] and r['p']<0.05]
p("carried to validate (train edge>0 and train p<0.05):",len(PRE))

res=[]
for r in PRE:
    desc=[str(x) for x in r['desc']]
    try: m=mask_of(desc)
    except Exception as e:
        continue
    ci=r['ci']
    v=evaluate(m,ci,NET[ci],hsel=2)
    if v is None or v['n']<60 or v['k']<12: continue
    bv=BASEV[ci]
    t,pv=welch(v['permint'],bv['permint'])
    # mint-matched random control: all bars of the SAME validate mints, same exit
    mm=np.zeros(N,bool)
    keep=set(v['mintidx'].tolist())
    mm=np.isin(P['mint_id'],list(keep))
    cm=evaluate(mm,ci,NET[ci],hsel=2)
    res.append(dict(**{k:r[k] for k in ('desc','ci','combo','tr_mean','tr_med','tr_n','tr_k','tr_res','base','edge','p','phase')},
                    va_mean=v['mean'],va_med=v['median'],va_n=v['n'],va_k=v['k'],va_res=v['res'],
                    va_base=bv['mean'],va_edge=v['mean']-bv['mean'],va_t=t,va_p=pv,
                    va_matched=cm['mean'] if cm else float('nan'),
                    va_edge_matched=(v['mean']-cm['mean']) if cm else float('nan')))
p("validated cells evaluated:",len(res),"t=%.1f"%(time.time()-T0))

# ---- Benjamini-Hochberg on the validate p-values ----
pv=np.array([x['va_p'] if x['va_p']==x['va_p'] else 1.0 for x in res])
order=np.argsort(pv); mtot=len(pv)
kmax=0
for rk,i in enumerate(order,1):
    if pv[i] <= 0.10*rk/mtot: kmax=rk
surv=set(order[:kmax].tolist())
for i,x in enumerate(res):
    x['bh_pass']= (i in surv)
    x['bh_rank']= int(np.where(order==i)[0][0])+1
p("BH q=0.10: %d of %d survive"%(kmax,mtot))

res.sort(key=lambda x:-(x['va_t'] if x['va_t']==x['va_t'] else -9))
for x in res[:60]:
    p("  V %-58s %-14s TR %+7.4f | VA %+7.4f base %+7.4f edge %+7.4f matched %+7.4f n %5d k %3d res %.3f p %.4f BH=%s"%(
        '|'.join(x['desc']),x['combo'],x['tr_mean'],x['va_mean'],x['va_base'],x['va_edge'],
        x['va_edge_matched'],x['va_n'],x['va_k'],x['va_res'],x['va_p'],x['bh_pass']))
json.dump(res,open(OUT+'/validate.json','w'),default=str)

# ---- deep-dive on BH survivors: robustness ----
deep=[x for x in res if x['bh_pass'] and x['va_mean']>0]
p("\nBH survivors with POSITIVE validate mean: %d"%len(deep))
rng=np.random.default_rng(7)
for x in deep[:40]:
    m=mask_of([str(y) for y in x['desc']]); ci=x['ci']
    line=["  DEEP %s | %s"%('|'.join(x['desc']),x['combo'])]
    for d in (0.30,0.50,1.00):
        for tl in (0.0114,0.025):
            nn=net_array(ci,d,tl)
            v=evaluate(m,ci,nn,hsel=2); b=evaluate(np.ones(N,bool),ci,nn,hsel=2)
            line.append("    drop=%.2f toll=%.4f  va %+7.4f  base %+7.4f  edge %+7.4f"%(d,tl,v['mean'],b['mean'],v['mean']-b['mean']))
    v=evaluate(m,ci,NET[ci],hsel=2)
    pm=v['permint']; K=len(pm)
    bs=np.array([pm[rng.integers(0,K,K)].mean() for _ in range(4000)])
    line.append("    cluster-bootstrap mean CI95 [%+7.4f, %+7.4f]  k=%d"%(np.quantile(bs,0.025),np.quantile(bs,0.975),K))
    p('\n'.join(line))
json.dump(deep,open(OUT+'/survivors.json','w'),default=str)
p("t=%.1f"%(time.time()-T0))
