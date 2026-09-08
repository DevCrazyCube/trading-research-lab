import numpy as np, sys, pickle, time
sys.path.insert(0,'/home/anont/meme/_fv0')
import engine
from engine import *

FI={n:i for i,n in enumerate(FEATNAMES)}
NN=FI['notional20']
TR=(E_h==1); VA=(E_h==2); IDX=np.arange(NE)
D=pickle.load(open('/home/anont/meme/_fv0/stage3.pkl','rb'))
FLOOR=D['floor']; FEAS=FEAT[:,NN]>=FLOOR
print('stage3 combos',D['combos'],'train-positive rules',len(D['pos']),'floor',FLOOR)

def parse(lbl):
    out=[]
    for tok in lbl.split(' & '):
        if '<=' in tok: f,t=tok.split('<='); op='<='
        else: f,t=tok.split('>'); op='>'
        out.append((f,op,float(t)))
    return out
def maskof(lbl):
    m=np.ones(NE,bool)
    for f,op,t in parse(lbl):
        c=FEAT[:,FI[f]]
        m &= (c>t) if op=='>' else (c<=t)
    return m

CTRL={}
def ctrl(ex,split):
    k=(ex,split)
    if k not in CTRL:
        CTRL[k]=evaluate(IDX[FEAS&(TR if split=='tr' else VA)].tolist(),*ex,full=True)
    return CTRL[k]

def matched_random(cnts, ex, split, reps=300, seed=11):
    rng=np.random.default_rng(seed)
    A=exit_arrays(*ex)
    pool=IDX[FEAS&(TR if split=='tr' else VA)]
    bym={}
    for i in pool: bym.setdefault(engine._EM_l[i],[]).append(i)
    means=[];trims=[];meds=[]
    for _ in range(reps):
        sel=[]
        for m,cnt in cnts.items():
            p=bym.get(m)
            if not p: continue
            take=rng.choice(len(p),size=min(cnt,len(p)),replace=False)
            cur=-1
            for k in sorted(p[j] for j in take):
                if engine._EB_l[k]>cur: sel.append(k); cur=A['eb_l'][k]
        if len(sel)<5: continue
        sel=np.array(sel,dtype=np.int64); mm=stats(sel,A)
        means.append(mm.mean()); trims.append(trimmed(mm)); meds.append(np.median(mm))
    return np.array(means),np.array(trims),np.array(meds)

seen=set(); rows=[]
for r in D['pos']:
    k=(r['label'],tuple(r['ex']))
    if k in seen: continue
    seen.add(k); rows.append(r)
print('unique rule x exit',len(rows))

out=[]; t0=time.time()
for r in rows:
    ex=tuple(r['ex']); m=maskof(r['label'])
    iv=IDX[m&FEAS&VA]
    if len(iv)<50: continue
    rv=evaluate(iv.tolist(),*ex,full=True)
    if rv is None or rv['k']<20 or rv['n']<50: continue
    cv=ctrl(ex,'va')
    lo,hi=boot_ci(rv['mm'])
    out.append(dict(label=r['label'],ex=ex,tr_mean=r['mean'],tr_trim=r['trim'],tr_med=r['med'],
        tr_k=r['k'],tr_n=r['n'],va_mean=rv['mean'],va_trim=rv['trim'],va_med=rv['med'],
        va_k=rv['k'],va_n=rv['n'],va_res=rv['res'],va_fpos=rv['fpos'],va_ci=(lo,hi),
        dmean=rv['mean']-cv['mean'],dtrim=rv['trim']-cv['trim'],dmed=rv['med']-cv['med'],
        mb=rv['mean_b'],mc=rv['mean_c'],md=rv['mean_d'],me=rv['mean_e']))
print('validated',len(out),'t',round(time.time()-t0,1))

surv=[r for r in out if r['va_mean']>0 and r['va_trim']>0 and r['va_med']>-0.02]
print('\n=== VALIDATE survivors (mean>0, trim>0, med>-2%) ===',len(surv))
surv.sort(key=lambda r:-r['va_trim'])
for r in surv[:40]:
    ex=r['ex']
    print(f"{r['label']:58s} H={HOR[ex[0]]:3d} tp={ex[1]} sl={ex[2]} pa={ex[3]} | TR mean={r['tr_mean']*100:7.2f} trim={r['tr_trim']*100:6.2f} k={r['tr_k']:3d} || VA mean={r['va_mean']*100:7.2f} trim={r['va_trim']*100:6.2f} med={r['va_med']*100:7.2f} CI=[{r['va_ci'][0]*100:.1f},{r['va_ci'][1]*100:.1f}] k={r['va_k']:3d} n={r['va_n']:4d} res={r['va_res']*100:.0f} dmean={r['dmean']*100:6.2f}")

strict=[r for r in surv if r['va_ci'][0]>0]
print('\n=== plus bootstrap CI-low>0 ===',len(strict))
for r in strict:
    ex=r['ex']
    print(f"{r['label']:58s} H={HOR[ex[0]]:3d} tp={ex[1]} sl={ex[2]} pa={ex[3]} VA mean={r['va_mean']*100:7.2f} CIlo={r['va_ci'][0]*100:6.2f} trim={r['va_trim']*100:6.2f} med={r['va_med']*100:6.2f} k={r['va_k']} n={r['va_n']}")

print('\n=== C2 MATCHED-RANDOM DEEP DIVE (validate, feasible universe) ===')
cand=(strict if len(strict)>=3 else sorted(surv,key=lambda r:-r['va_ci'][0])[:12])[:14]
final=[]
for r in cand:
    ex=r['ex']; m=maskof(r['label']); iv=IDX[m&FEAS&VA]
    rv=evaluate(iv.tolist(),*ex,full=True)
    cnts={}
    for k in rv['sel']: cnts[engine._EM_l[k]]=cnts.get(engine._EM_l[k],0)+1
    mn,tm,md=matched_random(cnts,ex,'va')
    # also train C2
    mt=maskof(r['label']); it=IDX[mt&FEAS&TR]
    rt=evaluate(it.tolist(),*ex,full=True)
    cnts_t={}
    for k in rt['sel']: cnts_t[engine._EM_l[k]]=cnts_t.get(engine._EM_l[k],0)+1
    mn_t,tm_t,md_t=matched_random(cnts_t,ex,'tr')
    mm=np.sort(rv['mm']); sel=rv['sel']
    nn=FEAT[sel-1,NN]
    rec=dict(r); rec['c2_mean']=float(mn.mean()); rec['c2_trim']=float(tm.mean()); rec['c2_med']=float(md.mean())
    rec['c2_p']=float((rv['mean']>mn).mean()); rec['c2_pt']=float((rv['trim']>tm).mean())
    rec['c2_pmed']=float((rv['med']>md).mean())
    rec['c2_tr_p']=float((rt['mean']>mn_t).mean()); rec['c2_tr_edge']=float(rt['mean']-mn_t.mean())
    rec['notional_med']=float(np.nanmedian(nn))
    final.append(rec)
    print(f"\n{r['label']} | H={HOR[ex[0]]} tp={ex[1]} sl={ex[2]} pa={ex[3]}")
    print(f"  VA mean={rv['mean']*100:.2f} trim={rv['trim']*100:.2f} med={rv['med']*100:.2f} fpos={rv['fpos']*100:.0f}% k={rv['k']} n={rv['n']} res={rv['res']*100:.1f} CI={[round(x*100,1) for x in r['va_ci']]}")
    print(f"  top5 mint means {[round(x*100,1) for x in mm[-5:]]} bot3 {[round(x*100,1) for x in mm[:3]]}")
    print(f"  C2(val)  mean {mn.mean()*100:7.2f} -> edge {(rv['mean']-mn.mean())*100:7.2f} pct={rec['c2_p']*100:.0f}% | trim {tm.mean()*100:7.2f} -> edge {(rv['trim']-tm.mean())*100:6.2f} pct={rec['c2_pt']*100:.0f}% | med {md.mean()*100:6.2f} -> edge {(rv['med']-md.mean())*100:6.2f} pct={rec['c2_pmed']*100:.0f}%")
    print(f"  C2(train) mean edge {rec['c2_tr_edge']*100:7.2f} pct={rec['c2_tr_p']*100:.0f}%")
    print(f"  robustness: drop-50%={r['mb']*100:.2f} drop-100%={r['mc']*100:.2f} toll2.5%={r['md']*100:.2f} toll2.5%+drop100={r['me']*100:.2f}")
    print(f"  capacity: notional20 median ${rec['notional_med']:.0f}/min")
pickle.dump(final,open('/home/anont/meme/_fv0/final3.pkl','wb'))
