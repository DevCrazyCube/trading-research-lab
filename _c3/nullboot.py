"""Per-candidate matched random-entry null, on VALIDATE mints only.
For each candidate: keep the SAME mints and the SAME number of positions per mint,
but choose the entry bars AT RANDOM inside those mints (same exit structure, same
non-overlap rule, same toll/dropout). This isolates whether the entry CONDITION
picks better moments than random moments in the same coins -- and it applies the
identical truncation (TP/trailing/pyramid), so any truncation artifact cancels."""
import numpy as np, json, sys
sys.path.insert(0,'/home/anont/meme/_c3')
from engine import load, net_array, evaluate, welch
OUT='/home/anont/meme/_c3'
LG=open(OUT+'/nullboot.log','w')
def p(*a): LG.write(' '.join(str(x) for x in a)+'\n'); LG.flush()
P=load(); N=len(P['TS']); FN=P['FEATNAMES']
CN=[c[0] for c in P['COMBOS']]
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

mid=P['mint_id']; nm=P['nm']
starts=np.searchsorted(mid,np.arange(nm),'left'); ends=np.searchsorted(mid,np.arange(nm),'right')
ENT=P['ENTTS']; rng=np.random.default_rng(5)

def greedy_mean(idx_by_mint, ci, net):
    ex=P['EXTS'][ci]; st=P['STATE'][ci]
    tot=[]
    for m,idxs in idx_by_mint.items():
        free=-1e18; s=0.0; c=0
        for k in sorted(idxs):
            if st[k]==0: continue
            if ENT[k]<free: continue
            free=ex[k]; s+=net[k]; c+=1
        if c: tot.append(s/c)
    return (np.mean(tot) if tot else np.nan), len(tot)

CAND=json.load(open(OUT+'/final.json'))
p("candidates stress-tested: %d"%len(CAND))
out=[]
for cand in CAND[:20]:
    desc=cand['desc']; ci=CN.index(cand['combo']); m=mask_of(desc); net=NET[ci]
    v=evaluate(m,ci,net,hsel=2)
    sel=np.flatnonzero(m & (P['bar_h']==2) & (P['STATE'][ci]!=0))
    # observed positions per mint after non-overlap
    per={}
    free=-1e18; cur=-1
    for k in sel:
        mm=mid[k]
        if mm!=cur: cur=mm; free=-1e18
        if ENT[k]<free: continue
        free=P['EXTS'][ci][k]; per[mm]=per.get(mm,0)+1
    B=3000; draws=np.empty(B)
    for b in range(B):
        d={}
        for mm,cnt in per.items():
            a,e=starts[mm],ends[mm]
            pool=np.arange(a,e)
            pool=pool[P['STATE'][ci][pool]!=0]
            if len(pool)==0: continue
            take=min(cnt*3,len(pool))
            d[mm]=rng.choice(pool,size=take,replace=False)
        draws[b],_=greedy_mean(d,ci,net)
    draws=draws[np.isfinite(draws)]
    obs=v['mean']
    pct=float((draws<obs).mean())
    out.append(dict(desc=desc,combo=cand['combo'],obs=obs,null_mean=float(draws.mean()),
                    null_p95=float(np.quantile(draws,0.95)),null_p999=float(np.quantile(draws,0.999)),
                    pctile=pct,k=v['k'],n=v['n']))
    p("  %-52s %-12s VA %+7.4f  matched-random-entry null: mean %+7.4f p95 %+7.4f p99.9 %+7.4f -> percentile %.4f (k=%d n=%d)"%(
        '|'.join(desc),cand['combo'],obs,draws.mean(),np.quantile(draws,0.95),np.quantile(draws,0.999),pct,v['k'],v['n']))
json.dump(out,open(OUT+'/nullboot.json','w'),default=str)
LG.close()
