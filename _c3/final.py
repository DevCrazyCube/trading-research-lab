"""Final gate. A candidate must:
  (1) have a POSITIVE mint-equal net mean on TRAIN   (not merely beat a losing control)
  (2) have a POSITIVE mint-equal net mean on VALIDATE
  (3) survive Benjamini-Hochberg on the validate p-values
  (4) still be positive when a $60 order must be <=10% of the entry minute's volume
  (5) beat the SAME exit structure applied to random entries (truncation control)
"""
import numpy as np, json, sys, math
sys.path.insert(0,'/home/anont/meme/_c3')
from engine import load, net_array, evaluate, welch
OUT='/home/anont/meme/_c3'
LG=open(OUT+'/final.log','w')
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
B6={f:buckets(P['FEAT'][:,FN.index(f)],6) for f in FN}
mv=P['META']
MF={'m_ttg':buckets(mv[:,0],3),
    'm_hour':(((mv[:,1].astype(int))//6).astype(np.int8),4),
    'm_creator_prior':(np.clip(mv[:,2],0,2).astype(np.int8),3),
    'm_cohort10':buckets(mv[:,3],3),'m_px0':buckets(mv[:,4],3),'m_v0':buckets(mv[:,5],3)}
def mask_of(desc):
    m=np.ones(N,bool)
    for d in desc:
        k,v=d.split('=')
        if k in MF: b,_=MF[k]; m&=(b==int(v))
        else:
            src=B6 if '/' in v else B4
            q=int(v[1:].split('/')[0]); b,_=src[k]; m&=(b==q)
    return m

V=json.load(open(OUT+'/validate.json'))
p("validated cells: %d"%len(V))
p("  of which BH-pass                       : %d"%sum(1 for x in V if x['bh_pass']))
p("  of which BH-pass AND va_mean>0         : %d"%sum(1 for x in V if x['bh_pass'] and x['va_mean']>0))
p("  of which BH-pass AND va>0 AND tr>0     : %d"%sum(1 for x in V if x['bh_pass'] and x['va_mean']>0 and x['tr_mean']>0))
p("  of which BH-pass AND va>0 AND tr>0 AND both medians>0 : %d"%
  sum(1 for x in V if x['bh_pass'] and x['va_mean']>0 and x['tr_mean']>0 and x['va_med']>0 and x['tr_med']>0))

C=[x for x in V if x['bh_pass'] and x['va_mean']>0 and x['tr_mean']>0]
C.sort(key=lambda x:-min(x['tr_mean'],x['va_mean']))
p("\n=== cells positive on BOTH splits and BH-clean: %d ==="%len(C))
rng=np.random.default_rng(11)
keep=[]
for x in C[:60]:
    desc=[str(y) for y in x['desc']]; ci=x['ci']; m=mask_of(desc)
    row={'desc':desc,'combo':CN[ci],'tr_mean':x['tr_mean'],'va_mean':x['va_mean'],
         'tr_med':x['tr_med'],'va_med':x['va_med'],'va_n':x['va_n'],'va_k':x['va_k'],
         'tr_n':x['tr_n'],'tr_k':x['tr_k'],'va_base':x['va_base'],'va_edge':x['va_edge'],
         'va_p':x['va_p'],'res':x['va_res']}
    v=evaluate(m,ci,NET[ci],hsel=2); pm=v['permint']; K=len(pm)
    bs=np.array([pm[rng.integers(0,K,K)].mean() for _ in range(4000)])
    row['ci_lo'],row['ci_hi']=float(np.quantile(bs,0.025)),float(np.quantile(bs,0.975))
    # tradability
    for thr,tag in ((600,'liq600'),(2000,'liq2000')):
        mm=m&(ENTVOL>=thr)
        r1=evaluate(mm,ci,NET[ci],hsel=1); r2=evaluate(mm,ci,NET[ci],hsel=2)
        b2=evaluate(ENTVOL>=thr,ci,NET[ci],hsel=2)
        row[tag]=dict(tr=(r1['mean'] if r1 else None), va=(r2['mean'] if r2 else None),
                      n=(r2['n'] if r2 else 0), k=(r2['k'] if r2 else 0),
                      base=(b2['mean'] if b2 else None))
    # cap sensitivity (is the mean tail-driven?)
    for cp,tag in ((None,'uncapped'),(1.0,'cap100')):
        nn=net_array(ci,0.30,0.0114,cp)
        r2=evaluate(m,ci,nn,hsel=2); b2=evaluate(np.ones(N,bool),ci,nn,hsel=2)
        row[tag]=dict(va=r2['mean'],base=b2['mean'])
    keep.append(row)
    l6=row['liq600']; l2=row['liq2000']
    p("\n  %s | %s"%('|'.join(desc),CN[ci]))
    p("     TR %+7.4f (med %+7.4f n%5d k%3d)  VA %+7.4f (med %+7.4f n%5d k%3d) base %+7.4f  boot95 [%+7.4f,%+7.4f] res %.3f"%(
        x['tr_mean'],x['tr_med'],x['tr_n'],x['tr_k'],x['va_mean'],x['va_med'],x['va_n'],x['va_k'],x['va_base'],row['ci_lo'],row['ci_hi'],x['va_res']))
    p("     liq>=$600  TR %s VA %s (n%d k%d, control %s)"%(
        ("%+7.4f"%l6['tr']) if l6['tr'] is not None else "  n/a",
        ("%+7.4f"%l6['va']) if l6['va'] is not None else "  n/a", l6['n'],l6['k'],
        ("%+7.4f"%l6['base']) if l6['base'] is not None else "n/a"))
    p("     liq>=$2000 TR %s VA %s (n%d k%d, control %s)"%(
        ("%+7.4f"%l2['tr']) if l2['tr'] is not None else "  n/a",
        ("%+7.4f"%l2['va']) if l2['va'] is not None else "  n/a", l2['n'],l2['k'],
        ("%+7.4f"%l2['base']) if l2['base'] is not None else "n/a"))
    p("     uncapped VA %+9.4f (control %+9.4f) | cap+100%% VA %+7.4f (control %+7.4f)"%(
        row['uncapped']['va'],row['uncapped']['base'],row['cap100']['va'],row['cap100']['base']))
json.dump(keep,open(OUT+'/final.json','w'),default=str)

# how many clear EVERY gate
full=[r for r in keep if r['liq600']['tr'] is not None and r['liq600']['va'] is not None
      and r['liq600']['tr']>0 and r['liq600']['va']>0 and r['ci_lo']>0]
p("\n=== cells clearing EVERY gate (both splits >0, BH, bootstrap CI-lo>0, tradable at $600 on both splits): %d ==="%len(full))
for r in full:
    p("   %s | %s  TR %+7.4f VA %+7.4f liq600 TR %+7.4f VA %+7.4f"%(
        '|'.join(r['desc']),r['combo'],r['tr_mean'],r['va_mean'],r['liq600']['tr'],r['liq600']['va']))
json.dump(full,open(OUT+'/final_full.json','w'),default=str)
LG.close()
