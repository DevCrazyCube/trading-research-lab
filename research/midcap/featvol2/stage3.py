import sys,time,json
import numpy as np
sys.path.insert(0,'/home/anont/meme/research/midcap/featvol2')
from stage2 import *   # book, F, TH, EX, R, TRAIN, VAL, ev, perm_control, cond_mask

D='/home/anont/meme/research/midcap/featvol2/'
rows=json.load(open(D+'stage2_train.json'))['rows']
combos_stage2=json.load(open(D+'stage2_train.json'))['combos']
print("stage2 positive rows:",len(rows),flush=True)

# ---- train-side filter (strict) ----
keep=[r for r in rows if r['tr_n']>=80 and r['tr_k']>=30 and r['tr_mean']>0 and r['tr_mean_hard']>0]
print("after train n/k/hard filter:",len(keep),flush=True)
keep.sort(key=lambda r:-r['tr_mean'])

# train permutation control, on the strongest ones only (cost)
LIM=int(sys.argv[1]) if len(sys.argv)>1 else 250
keep=keep[:LIM]
res=[]
for i,r in enumerate(keep):
    m=cond_mask(r['c1'])
    if r['c2']: m=m&cond_mask(r['c2'])
    ct=perm_control(m&TRAIN,r['exit'],TRAIN,reps=25,seed=101)
    if ct is None: continue
    r['tr_ctrl']=ct['mean']; r['tr_edge']=r['tr_mean']-ct['mean']
    res.append(r)
    if i%25==0: print("  ctrl %d/%d t=%.1f"%(i,len(keep),time.time()-t0),flush=True)
res=[r for r in res if r['tr_edge']>0]
print("survive train control:",len(res),flush=True)
res.sort(key=lambda r:-r['tr_edge'])
json.dump(res,open(D+'stage3_trainsurv.json','w'))

# ---- VALIDATE ----
final=[]
for i,r in enumerate(res):
    m=cond_mask(r['c1'])
    if r['c2']: m=m&cond_mask(r['c2'])
    mv=m&VAL
    st=ev(mv,r['exit'])
    if st is None: continue
    e=EX[r['exit']]; js=st['js']
    o=dict(r)
    o['va_n']=st['n']; o['va_k']=st['clusters']; o['va_mean']=st['mean']; o['va_med']=st['median']
    o['va_res']=st['res']
    for (t,d),lab in [((0.0114,-0.30),'t114_d30'),((0.0114,-0.50),'t114_d50'),((0.0114,-1.00),'t114_d100'),
                      ((0.025,-0.30),'t250_d30'),((0.025,-1.00),'t250_d100')]:
        s2=R.stats(js,e['nets'][(t,d)])
        o['va_mean_'+lab]=s2['mean']; o['va_med_'+lab]=s2['median']
    o['va_ci_lo']=boot_lo(st['pm'])
    ct=perm_control(mv,r['exit'],VAL,reps=40,seed=777)
    o['va_ctrl']=ct['mean'] if ct else float('nan')
    o['va_ctrl_med']=ct['median'] if ct else float('nan')
    o['va_edge']=o['va_mean']-o['va_ctrl'] if ct else float('nan')
    final.append(o)
    if i%25==0: print("  val %d/%d t=%.1f"%(i,len(res),time.time()-t0),flush=True)

json.dump(dict(final=final,combos_stage2=combos_stage2),open(D+'stage3_validate.json','w'))
surv=[o for o in final if o['va_mean']>0 and o['va_mean_t250_d100']>0 and o['va_ci_lo']>0 and o['va_edge']>0]
surv.sort(key=lambda o:-o['va_edge'])
print("VALIDATE SURVIVORS:",len(surv),flush=True)
for o in surv[:40]:
    print("  %s | %s | %s | trN=%d trK=%d trMean=%.4f | vaN=%d vaK=%d vaMean=%.4f vaMed=%.4f CIlo=%.4f ctrl=%.4f edge=%.4f hard=%.4f"%(
        o['c1'],o['c2'],o['exit'],o['tr_n'],o['tr_k'],o['tr_mean'],o['va_n'],o['va_k'],o['va_mean'],
        o['va_med'],o['va_ci_lo'],o['va_ctrl'],o['va_edge'],o['va_mean_t250_d100']),flush=True)
print("STAGE3 DONE",flush=True)
