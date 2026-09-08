import numpy as np, sys, pickle, time
sys.path.insert(0,'/home/anont/meme/_fv0')
import engine
from engine import *

FI={n:i for i,n in enumerate(FEATNAMES)}
def parse(lbl):
    ms=[]
    for tok in lbl.split(' & '):
        if '<=' in tok: f,t=tok.split('<='); op='<='
        else: f,t=tok.split('>'); op='>'
        ms.append((f,op,float(t)))
    return ms
def maskof(conds):
    m=np.ones(NE,bool)
    for f,op,t in conds:
        c=FEAT[:,FI[f]]
        m &= (c>t) if op=='>' else (c<=t)
    return m

TR=(E_h==1); VA=(E_h==2); IDX=np.arange(NE)
D=pickle.load(open('/home/anont/meme/_fv0/stage2.pkl','rb'))
hits=D['hits']
print('train hits',len(hits),'combos so far',D['combos'])

CTRL={}
def ctrl(ex,split):
    k=(ex,split)
    if k not in CTRL:
        CTRL[k]=evaluate((IDX[TR] if split=='tr' else IDX[VA]).tolist(),*ex,full=True)
    return CTRL[k]

def matched_random(rule_idx_by_mint, ex, split, reps=200, seed=11):
    """C2: same mints, same trade-count per mint, random entry bars -> mean/trim distribution"""
    rng=np.random.default_rng(seed)
    A=exit_arrays(*ex)
    pool=IDX[(TR if split=='tr' else VA)]
    bym={}
    for i in pool: bym.setdefault(engine._EM_l[i],[]).append(i)
    means=[];trims=[];meds=[]
    for _ in range(reps):
        sel=[]
        for m,cnt in rule_idx_by_mint.items():
            p=bym.get(m)
            if not p: continue
            take=rng.choice(len(p),size=min(cnt,len(p)),replace=False)
            cand=sorted(p[j] for j in take)
            # apply non-overlap on the sampled set
            cur=-1
            for k in cand:
                if engine._EB_l[k]>cur:
                    sel.append(k); cur=A['eb_l'][k]
        if len(sel)<5: continue
        sel=np.array(sel,dtype=np.int64)
        mm=stats(sel,A)
        means.append(mm.mean()); trims.append(trimmed(mm)); meds.append(np.median(mm))
    return np.array(means),np.array(trims),np.array(meds)

seen=set(); rows=[]
for r in hits:
    key=(r['label'],tuple(r['ex']))
    if key in seen: continue
    seen.add(key)
    rows.append(r)
print('unique rule x exit',len(rows))

out=[]
t0=time.time()
for r in rows:
    conds=parse(r['label']); m=maskof(conds); ex=tuple(r['ex'])
    iv=IDX[m&VA]
    if len(iv)<40: continue
    rv=evaluate(iv.tolist(),*ex,full=True)
    if rv is None or rv['k']<20 or rv['n']<40: continue
    cv=ctrl(ex,'va')
    rec=dict(label=r['label'],ex=ex,
             tr_mean=r['mean'],tr_trim=r['trim'],tr_med=r['med'],tr_k=r['k'],tr_n=r['n'],
             va_mean=rv['mean'],va_trim=rv['trim'],va_med=rv['med'],va_k=rv['k'],va_n=rv['n'],
             va_res=rv['res'],va_fpos=rv['fpos'],
             va_dmean=rv['mean']-cv['mean'],va_dtrim=rv['trim']-cv['trim'],va_dmed=rv['med']-cv['med'],
             va_mean_b=rv['mean_b'],va_mean_c=rv['mean_c'],va_mean_d=rv['mean_d'],va_mean_e=rv['mean_e'],
             va_med_c=rv['med_c'],va_trim_c=rv['trim_c'],mm=rv['mm'])
    lo,hi=boot_ci(rv['mm']); rec['va_ci']=(lo,hi)
    out.append(rec)
print('validated',len(out),'t',time.time()-t0)

surv=[r for r in out if r['va_mean']>0 and r['va_trim']>0]
print('\n=== survive validate (mean>0 AND trim5>0) ===',len(surv))
surv.sort(key=lambda r:-r['va_trim'])
for r in surv[:80]:
    ex=r['ex']
    print(f"{r['label']:50s} H={HOR[ex[0]]:3d} tp={ex[1]} sl={ex[2]} pa={ex[3]} | TR mean={r['tr_mean']*100:8.2f} trim={r['tr_trim']*100:7.2f} k={r['tr_k']:3d} || VA mean={r['va_mean']*100:8.2f} trim={r['va_trim']*100:7.2f} med={r['va_med']*100:7.2f} CI=[{r['va_ci'][0]*100:.1f},{r['va_ci'][1]*100:.1f}] dmean={r['va_dmean']*100:7.2f} k={r['va_k']:3d} n={r['va_n']:4d} res={r['va_res']*100:.1f}")

strict=[r for r in surv if r['va_ci'][0]>0]
print('\n=== ALSO bootstrap CI-low > 0 on validate ===',len(strict))
for r in strict:
    ex=r['ex']
    print(f"{r['label']:50s} H={HOR[ex[0]]:3d} tp={ex[1]} sl={ex[2]} pa={ex[3]} VA mean={r['va_mean']*100:8.2f} CIlo={r['va_ci'][0]*100:.2f} trim={r['va_trim']*100:7.2f} k={r['va_k']} n={r['va_n']}")

pickle.dump([{k:v for k,v in r.items() if k!='mm'} for r in out],open('/home/anont/meme/_fv0/valid.pkl','wb'))

# deep dive on the strongest few
print('\n=== DEEP DIVE (matched random control C2, validate) ===')
cand=sorted(surv,key=lambda r:-(r['va_ci'][0] if r['va_ci'][0]==r['va_ci'][0] else -9))[:12]
VN=FEATNAMES.index('vol_now'); NN=FEATNAMES.index('notional20')
for r in cand:
    conds=parse(r['label']); m=maskof(conds); ex=r['ex']
    iv=IDX[m&VA]
    rv=evaluate(iv.tolist(),*ex,full=True)
    sel=rv['sel']; cnts={}
    for k in sel: cnts[engine._EM_l[k]]=cnts.get(engine._EM_l[k],0)+1
    mn,tm,md=matched_random(cnts,ex,'va',reps=150)
    mm=np.sort(rv['mm'])
    print(f"\n{r['label']} | H={HOR[ex[0]]} tp={ex[1]} sl={ex[2]} pa={ex[3]}")
    print(f"  VA mean={rv['mean']*100:.2f} trim={rv['trim']*100:.2f} med={rv['med']*100:.2f} k={rv['k']} n={rv['n']} res={rv['res']*100:.1f} CI={[round(x*100,1) for x in r['va_ci']]}")
    print(f"  top5 mint means: {[round(x*100,1) for x in mm[-5:]]}  bot3: {[round(x*100,1) for x in mm[:3]]}")
    print(f"  C2 matched-random mean: {mn.mean()*100:.2f} (p5={np.percentile(mn,5)*100:.1f} p95={np.percentile(mn,95)*100:.1f}) -> edge={(rv['mean']-mn.mean())*100:.2f}, pctile={(rv['mean']>mn).mean()*100:.0f}%")
    print(f"  C2 matched-random trim: {tm.mean()*100:.2f} -> edge={(rv['trim']-tm.mean())*100:.2f}, pctile={(rv['trim']>tm).mean()*100:.0f}%")
    print(f"  dropout -50%: {r['va_mean_b']*100:.2f}  -100%: {r['va_mean_c']*100:.2f}  toll2.5%/-30%: {r['va_mean_d']*100:.2f}  toll2.5%/-100%: {r['va_mean_e']*100:.2f}")
    vn=FEAT[sel-1,VN]; nn=FEAT[sel-1,NN]
    print(f"  CAPACITY: vol_now at signal median={np.nanmedian(vn):.2f} p90={np.nanpercentile(vn,90):.1f} | notional20 median={np.nanmedian(nn):.2f} p90={np.nanpercentile(nn,90):.1f} (USD/min)")
    ent=E_P[sel]; print(f"  entry-gap minutes median={np.median([0]) if False else 0}")
