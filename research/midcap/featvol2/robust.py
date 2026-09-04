"""Focused robustness on the two best near-miss families.
A real edge is a PLATEAU in parameter space and survives entry delay.
Noise is a spike."""
import sys,gc,json
import numpy as np
sys.path.insert(0,'/home/anont/meme/research/midcap/featvol2')
from core import *
from feats import build_features
D='/home/anont/meme/research/midcap/featvol2/'
CAP=3.0
def log(*a): print(*a,flush=True)
mints,data,nres=load(); book=Book(mints,data); F=build_features(book); N=book.N
BH=book.hh[book.MID]; TRAIN=book.valid_sig&(BH==1); VAL=book.valid_sig&(BH==2)
R=Runner(book)
FEATS=list(F.keys())
def q(f,p):
    v=F[f][TRAIN]; v=v[np.isfinite(v)]; return float(np.quantile(v,p))

def mkexit(Hm,tp=None,sl=None,sc=1.0):
    k=build_exit(book,Hm)
    if tp is None and sl is None: g=gross_returns(book,k,None,None)
    else:
        span=np.where(k>=0,k-np.arange(N),0); mw=int(min(max(3,span.max()+1),200))
        Rmax,Rmin,L=path_extremes(book,k,mw); g=gross_returns(book,k,tp,sl,sc,Rmax,Rmin,L)
        del Rmax,Rmin,L; gc.collect()
    return dict(k=k,net=netify(g,k,0.0114,-0.30,CAP),hard=netify(g,k,0.025,-1.00,CAP))

def perm(mask,e,split,reps=200,seed=9,key='net'):
    rng=np.random.default_rng(seed); net=e[key]
    pool=np.flatnonzero(split); mid=book.MID[pool]; sel=mask[pool]
    o=np.argsort(mid,kind='stable'); pool_s=pool[o]; mid_s=mid[o]; sel_s=sel[o]
    segs=np.split(np.arange(pool_s.size),np.flatnonzero(np.diff(mid_s))+1)
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
    return np.array(mus),np.array(mds)

def report(tag,mask,e,off=1):
    out={}
    for lab,split in (('TR',TRAIN),('VA',VAL)):
        js=R.select(mask&split,e['k'],off)
        if js.size<20: log("  %-46s %s n=%d TOO SMALL"%(tag,lab,js.size)); out[lab]=None; continue
        st=R.stats(js,e['net'],e['k']); sh=R.stats(js,e['hard'])
        ci=boot_lo(st['pm'],B=4000)
        out[lab]=(st,sh,ci)
        log("  %-46s %s n=%4d k=%3d mean=%+.4f med=%+.4f cilo=%+.4f hard=%+.4f fracpos=%.2f"%(
            tag,lab,st['n'],st['clusters'],st['mean'],st['median'],ci,sh['mean'],float((st['pm']>0).mean())))
    return out

log("=== FAMILY A : volume-share + 1-min burst, short plain hold ===")
for Hm in (3,5,8,10,15):
    e=mkexit(Hm)
    for pv,pr in ((0.90,0.98),(0.85,0.95),(0.95,0.99),(0.80,0.90),(0.90,0.95)):
        m=(F['vshare']>q('vshare',pv))&(F['ret1']>q('ret1',pr))
        m&=np.isfinite(F['vshare'])&np.isfinite(F['ret1'])
        report("H%d vshare>q%d & ret1>q%d"%(Hm,pv*100,pr*100),m,e)
    del e; gc.collect()

log("\n=== FAMILY B : vol-accel + above-VWAP + vol>median, 10m cap, +60%% TP ===")
mB=(F['vacc']>=q('vacc',0.90))&(F['vacc']<=q('vacc',0.99))&(F['vwapdev']>q('vwapdev',0.90))&(F['vrel5']>q('vrel5',0.90))
mB&=np.isfinite(F['vacc'])&np.isfinite(F['vwapdev'])&np.isfinite(F['vrel5'])
log("mask bars: train=%d validate=%d"%(int((mB&TRAIN).sum()),int((mB&VAL).sum())))
for Hm,tp in ((10,0.60),(10,None),(10,0.30),(10,1.00),(5,0.60),(15,0.60),(20,0.60),(30,0.60)):
    e=mkexit(Hm,tp)
    report("H%s tp=%s  EXACT"%(Hm,tp),mB,e)
    del e; gc.collect()
log("-- threshold plateau at H10/tp60 --")
e=mkexit(10,0.60)
for pa,pw,pv in ((0.90,0.90,0.90),(0.85,0.85,0.85),(0.80,0.80,0.80),(0.95,0.95,0.95),
                 (0.90,0.80,0.90),(0.90,0.90,0.80),(0.80,0.90,0.90),(0.75,0.75,0.75)):
    m=(F['vacc']>q('vacc',pa))&(F['vwapdev']>q('vwapdev',pw))&(F['vrel5']>q('vrel5',pv))
    m&=np.isfinite(F['vacc'])&np.isfinite(F['vwapdev'])&np.isfinite(F['vrel5'])
    report("vacc>q%d vwapdev>q%d vrel5>q%d"%(pa*100,pw*100,pv*100),m,e)
log("-- entry-delay robustness (off=1 modelled, 2 and 3 = extra real bars of latency) --")
for off in (1,2,3):
    report("B exact off=%d"%off,mB,e,off=off)
log("-- permutation p-value on VALIDATE (200 within-mint reshuffles, same exit) --")
js=R.select(mB&VAL,e['k']); st=R.stats(js,e['net'])
mus,mds=perm(mB&VAL,e,VAL,reps=200,seed=31)
log("  observed validate mean=%+.4f  ctrl mean=%+.4f sd=%.4f  p(one-sided)=%.3f"%(
    st['mean'],mus.mean(),mus.std(),float((mus>=st['mean']).mean())))
log("  observed validate med =%+.4f  ctrl med =%+.4f sd=%.4f  p(one-sided)=%.3f"%(
    st['median'],mds.mean(),mds.std(),float((mds>=st['median']).mean())))
js=R.select(mB&TRAIN,e['k']); st=R.stats(js,e['net'])
mus,mds=perm(mB&TRAIN,e,TRAIN,reps=200,seed=32)
log("  observed TRAIN    mean=%+.4f  ctrl mean=%+.4f sd=%.4f  p(one-sided)=%.3f"%(
    st['mean'],mus.mean(),mus.std(),float((mus>=st['mean']).mean())))
log("ROBUST DONE")
