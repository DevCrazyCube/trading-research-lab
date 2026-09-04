"""feat-vol#2 : exhaustive entry(volume/microstructure) x exit x position sweep.
Holdout: md5(mint)%3==0 NEVER loaded.  TRAIN=%3==1, VALIDATE=%3==2.
Headline returns are mint-equal, no-overlap, entry at open of NEXT real bar,
dropouts charged, toll applied, GROSS gains winsorised at +300% (feed glitches
produce +600x one-minute bars in this snapshot; capping the right tail is
conservative and cannot manufacture a positive result)."""
import sys,time,csv,json,gc,pickle
import numpy as np
sys.path.insert(0,'/home/anont/meme/research/midcap/featvol2')
from core import *
from feats import build_features

D='/home/anont/meme/research/midcap/featvol2/'
CAP=3.0
t0=time.time()
def log(*a): print(*a,flush=True)

mints,data,nres=load()
book=Book(mints,data); F=build_features(book); N=book.N
BH=book.hh[book.MID]
TRAIN=book.valid_sig&(BH==1); VAL=book.valid_sig&(BH==2)
R=Runner(book)
log("bars=%d mints=%d trainM=%d valM=%d reservedSkipped=%d"%(N,book.nm,int((book.hh==1).sum()),int((book.hh==2).sum()),nres))

FEATS=['vrel5','vrel20','vacc','rng','rngrel','dens10','dens30','gap','chop',
       'vwapdev','clspos','body','dvol','vshare','ret1','ret5','vzs','rngz','illiq','tickdir']
QS=[0.01,0.02,0.05,0.10,0.20,0.35,0.50,0.65,0.80,0.90,0.95,0.98,0.99]
CONDS=[('>',0.90),('>',0.95),('>',0.98),('>',0.99),('<',0.10),('<',0.05),('<',0.02),('<',0.01),
       ('in',(0.80,0.95)),('in',(0.05,0.20)),('in',(0.35,0.65)),('in',(0.90,0.99)),('in',(0.01,0.10))]
TH={}
for f in FEATS:
    v=F[f][TRAIN]; v=v[np.isfinite(v)]
    TH[f]={q:float(np.quantile(v,q)) for q in QS}
CB={};CN=[];COF={}
for f in FEATS:
    x=F[f];fin=np.isfinite(x)
    for op,arg in CONDS:
        if op=='>': m=fin&(x>TH[f][arg]); nm="%s>q%02d"%(f,int(arg*100))
        elif op=='<': m=fin&(x<TH[f][arg]); nm="%s<q%02d"%(f,int(arg*100))
        else:
            a,b=arg; m=fin&(x>=TH[f][a])&(x<=TH[f][b]); nm="%s@q%02d-%02d"%(f,int(a*100),int(b*100))
        CB[nm]=m;CN.append(nm);COF[nm]=f
log("conditions=%d"%len(CN))
pickle.dump(TH,open(D+'thresholds.pkl','wb'))

def mkexits(specs):
    EX={}
    for nm,Hm,tp,sl,sc in specs:
        k=build_exit(book,Hm)
        if tp is None and sl is None:
            g=gross_returns(book,k,None,None)
        else:
            span=np.where(k>=0,k-np.arange(N),0)
            mw=int(min(max(3,span.max()+1),200))
            Rmax,Rmin,L=path_extremes(book,k,mw)
            g=gross_returns(book,k,tp,sl,sc,Rmax,Rmin,L)
            del Rmax,Rmin,L; gc.collect()
        EX[nm]=dict(k=k,g=g,H=Hm,tp=tp,sl=sl,sc=sc,
                    net=netify(g,k,0.0114,-0.30,CAP),
                    net_raw=netify(g,k,0.0114,-0.30,None),
                    net_hard=netify(g,k,0.0250,-1.00,CAP))
    return EX

S1=[('H5',5,None,None,1.0),('H15',15,None,None,1.0),('H30',30,None,None,1.0),
    ('H60',60,None,None,1.0),('H120',120,None,None,1.0),
    ('H15tp30',15,0.30,None,1.0),('H60tp60sl30',60,0.60,-0.30,1.0),('H30sl35',30,None,-0.35,1.0)]
EX1=mkexits(S1)
log("stage1 exits built t=%.1f"%(time.time()-t0))

MIN_N=60;MIN_K=25
def ev(mask,e,net_key='net',off=1):
    js=R.select(mask,e['k'],off)
    if js.size<MIN_N: return None
    st=R.stats(js,e[net_key],e['k'])
    if st['clusters']<MIN_K: return None
    st['js']=js
    return st

# ---------- STAGE 1: singles + pairs ----------
rows=[];combos=0
def push(c1,c2,c3,exn,st,e):
    st2=R.stats(st['js'],e['net_hard']); st3=R.stats(st['js'],e['net_raw'])
    rows.append(dict(c1=c1,c2=c2,c3=c3,exit=exn,n=st['n'],k=st['clusters'],
        mean=st['mean'],med=st['median'],res=st['res'],
        mean_hard=st2['mean'],med_hard=st2['median'],mean_raw=st3['mean']))
for nm in CN:
    m=CB[nm]&TRAIN
    if m.sum()<MIN_N: continue
    for exn,e in EX1.items():
        combos+=1
        st=ev(m,e)
        if st: push(nm,'','',exn,st,e)
log("singles combos=%d rows=%d t=%.1f"%(combos,len(rows),time.time()-t0))
nc=len(CN)
pairkeep=[]
for a in range(nc):
    ma=CB[CN[a]]&TRAIN
    if ma.sum()<MIN_N: continue
    for b in range(a+1,nc):
        if COF[CN[b]]==COF[CN[a]]: continue
        m=ma&CB[CN[b]]
        if m.sum()<MIN_N: continue
        best=-9
        for exn,e in EX1.items():
            combos+=1
            st=ev(m,e)
            if st:
                push(CN[a],CN[b],'',exn,st,e)
                if st['mean']>best: best=st['mean']
        if best>-9: pairkeep.append((best,CN[a],CN[b]))
    if a%40==0: log("  pairs a=%d/%d combos=%d rows=%d t=%.1f"%(a,nc,combos,len(rows),time.time()-t0))
log("pairs combos=%d rows=%d t=%.1f"%(combos,len(rows),time.time()-t0))

# ---------- STAGE 1b: 3-way on the best pairs ----------
pairkeep.sort(reverse=True)
TOPP=[(c1,c2) for _,c1,c2 in pairkeep[:90]]
for c1,c2 in TOPP:
    base=CB[c1]&CB[c2]&TRAIN
    for c3 in CN:
        if COF[c3] in (COF[c1],COF[c2]): continue
        m=base&CB[c3]
        if m.sum()<MIN_N: continue
        for exn,e in EX1.items():
            combos+=1
            st=ev(m,e)
            if st: push(c1,c2,c3,exn,st,e)
log("with 3-way combos=%d rows=%d t=%.1f"%(combos,len(rows),time.time()-t0))
json.dump(dict(rows=rows,combos=combos),open(D+'s1.json','w'))

# ---------- baselines ----------
base={}
for exn,e in EX1.items():
    for lab,msk in (('TR',TRAIN),('VA',VAL)):
        js=R.select(msk,e['k']); st=R.stats(js,e['net'],e['k'])
        st2=R.stats(js,e['net_hard'])
        base['%s_%s'%(exn,lab)]=dict(n=st['n'],k=st['clusters'],mean=st['mean'],med=st['median'],
                                     res=st['res'],mean_hard=st2['mean'],med_hard=st2['median'])
        log("BASE %-12s %s n=%5d k=%3d mean=%+.4f med=%+.4f hard=%+.4f res=%.3f"%(
            exn,lab,st['n'],st['clusters'],st['mean'],st['median'],st2['mean'],st['res']))
json.dump(base,open(D+'baselines.json','w'))

# ---------- STAGE 2: carry positives into the full exit/position grid ----------
cands={}
for r in rows:
    if r['n']<MIN_N or r['k']<MIN_K: continue
    if r['mean']>0 or r['med']>0:
        key=(r['c1'],r['c2'],r['c3'])
        sc=max(r['mean'],r['med'])
        if key not in cands or sc>cands[key]: cands[key]=sc
carry=sorted(cands.items(),key=lambda kv:-kv[1])[:500]
log("entry conditions with a positive stage-1 cell: %d ; carried: %d"%(len(cands),len(carry)))

S2=[]
for Hm in (3,5,10,15,20,30,45,60,90,120,180):
    S2.append(('H%d'%Hm,Hm,None,None,1.0))
for Hm in (10,15,30,60,120):
    for tp in (0.15,0.30,0.60,1.00,2.00):
        S2.append(('H%dtp%d'%(Hm,int(tp*100)),Hm,tp,None,1.0))
    for sl in (-0.15,-0.25,-0.40,-0.60):
        S2.append(('H%dsl%d'%(Hm,int(-sl*100)),Hm,None,sl,1.0))
    for tp in (0.30,0.60,1.00):
        for sl in (-0.20,-0.40):
            S2.append(('H%dtp%dsl%d'%(Hm,int(tp*100),int(-sl*100)),Hm,tp,sl,1.0))
    for tp in (0.25,0.50,1.00):
        S2.append(('H%dsc50tp%d'%(Hm,int(tp*100)),Hm,tp,None,0.5))
        S2.append(('H%dsc50tp%dsl40'%(Hm,int(tp*100)),Hm,tp,-0.40,0.5))
        S2.append(('H%dsc33tp%d'%(Hm,int(tp*100)),Hm,tp,None,0.34))
log("stage2 exit/position structures=%d"%len(S2))
EX2=mkexits(S2)
log("stage2 exits built t=%.1f"%(time.time()-t0))

def cmask(key):
    m=CB[key[0]].copy()
    if key[1]: m&=CB[key[1]]
    if key[2]: m&=CB[key[2]]
    return m

s2rows=[];combos2=0
for key,_ in carry:
    mt=cmask(key)&TRAIN
    if mt.sum()<MIN_N: continue
    for exn,e in EX2.items():
        combos2+=1
        st=ev(mt,e)
        if st is None: continue
        if not (st['mean']>0 and st['median']>0): continue
        sh=R.stats(st['js'],e['net_hard'])
        if sh['mean']<=0: continue
        s2rows.append(dict(c1=key[0],c2=key[1],c3=key[2],exit=exn,tr_n=st['n'],tr_k=st['clusters'],
                           tr_mean=st['mean'],tr_med=st['median'],tr_res=st['res'],
                           tr_mean_hard=sh['mean'],tr_med_hard=sh['median']))
log("stage2 combos=%d survivors(train mean>0 & med>0 & hard>0)=%d t=%.1f"%(combos2,len(s2rows),time.time()-t0))
json.dump(dict(rows=s2rows,combos=combos2),open(D+'s2.json','w'))

TOTAL=combos+combos2
log("TOTAL COMBOS SWEPT = %d"%TOTAL)

# ---------- STAGE 3: train permutation control, then VALIDATE ----------
def perm_control(mask,e,split,reps=30,seed=5,net_key='net'):
    rng=np.random.default_rng(seed); net=e[net_key]
    pool=np.flatnonzero(split); mid=book.MID[pool]; sel=mask[pool]
    order=np.argsort(mid,kind='stable')
    pool_s=pool[order]; mid_s=mid[order]; sel_s=sel[order]
    bnds=np.flatnonzero(np.diff(mid_s))+1
    segs=np.split(np.arange(pool_s.size),bnds)
    cnts=[int(sel_s[s].sum()) for s in segs]
    mus=[];mds=[]
    for _ in range(reps):
        m=np.zeros(N,bool)
        for s,c in zip(segs,cnts):
            if c<=0: continue
            m[pool_s[s[rng.choice(s.size,size=c,replace=False)]]]=True
        js=R.select(m,e['k'])
        if js.size<5: continue
        st=R.stats(js,net); mus.append(st['mean']); mds.append(st['median'])
    if not mus: return None
    return float(np.mean(mus)),float(np.mean(mds))

s2rows.sort(key=lambda r:-min(r['tr_mean'],r['tr_med']))
s2rows=s2rows[:300]
tr_surv=[]
for i,r in enumerate(s2rows):
    e=EX2[r['exit']]; m=cmask((r['c1'],r['c2'],r['c3']))
    pc=perm_control(m&TRAIN,e,TRAIN,reps=25,seed=101)
    if pc is None: continue
    r['tr_ctrl_mean'],r['tr_ctrl_med']=pc
    if r['tr_mean']>pc[0] and r['tr_med']>pc[1]:
        tr_surv.append(r)
    if i%50==0: log("  trainctrl %d/%d t=%.1f"%(i,len(s2rows),time.time()-t0))
log("survive TRAIN permutation control: %d"%len(tr_surv))
json.dump(tr_surv,open(D+'s3_trainsurv.json','w'))

final=[]
for i,r in enumerate(tr_surv):
    e=EX2[r['exit']]; m=cmask((r['c1'],r['c2'],r['c3']))
    st=ev(m&VAL,e)
    if st is None:
        r['va_fail']='too_small'; final.append(r); continue
    js=st['js']
    r['va_n']=st['n']; r['va_k']=st['clusters']; r['va_mean']=st['mean']; r['va_med']=st['median']; r['va_res']=st['res']
    sh=R.stats(js,e['net_hard']); r['va_mean_hard']=sh['mean']; r['va_med_hard']=sh['median']
    sr=R.stats(js,e['net_raw']); r['va_mean_uncapped']=sr['mean']
    r['va_ci_lo']=boot_lo(st['pm'])
    r['va_frac_pos_mint']=float((st['pm']>0).mean())
    pc=perm_control(m&VAL,e,VAL,reps=40,seed=777)
    r['va_ctrl_mean'],r['va_ctrl_med']=(pc if pc else (float('nan'),float('nan')))
    r['va_edge_mean']=r['va_mean']-r['va_ctrl_mean']; r['va_edge_med']=r['va_med']-r['va_ctrl_med']
    # lag robustness: enter one further real bar later
    st2=ev(m&VAL,e,off=2)
    r['va_mean_lag2']=st2['mean'] if st2 else float('nan')
    r['va_med_lag2']=st2['median'] if st2 else float('nan')
    final.append(r)
    if i%25==0: log("  validate %d/%d t=%.1f"%(i,len(tr_surv),time.time()-t0))
json.dump(dict(final=final,total_combos=TOTAL),open(D+'s3_validate.json','w'))

surv=[r for r in final if r.get('va_mean',-9)>0 and r.get('va_med',-9)>0
      and r.get('va_mean_hard',-9)>0 and r.get('va_ci_lo',-9)>0
      and r.get('va_edge_mean',-9)>0 and r.get('va_edge_med',-9)>0]
surv.sort(key=lambda r:-r['va_edge_mean'])
log("=== VALIDATE SURVIVORS: %d ==="%len(surv))
for r in surv[:50]:
    log("  %s & %s & %s | %s | tr n=%d k=%d mean=%+.4f med=%+.4f | va n=%d k=%d mean=%+.4f med=%+.4f CIlo=%+.4f ctrl(%+.4f,%+.4f) hard=%+.4f lag2=%+.4f fracpos=%.2f"%(
        r['c1'],r['c2'],r['c3'],r['exit'],r['tr_n'],r['tr_k'],r['tr_mean'],r['tr_med'],
        r['va_n'],r['va_k'],r['va_mean'],r['va_med'],r['va_ci_lo'],r['va_ctrl_mean'],r['va_ctrl_med'],
        r['va_mean_hard'],r['va_mean_lag2'],r['va_frac_pos_mint']))
log("DONE t=%.1f TOTAL_COMBOS=%d"%(time.time()-t0,TOTAL))
