import sys,gc
import numpy as np
sys.path.insert(0,'/home/anont/meme/research/midcap/featvol2')
from core import *
from feats import build_features
CAP=3.0
def log(*a): print(*a,flush=True)
mints,data,nres=load(); book=Book(mints,data); F=build_features(book); N=book.N
BH=book.hh[book.MID]; TRAIN=book.valid_sig&(BH==1); VAL=book.valid_sig&(BH==2)
R=Runner(book)
def q(f,p):
    v=F[f][TRAIN]; v=v[np.isfinite(v)]; return float(np.quantile(v,p))
def mkexit(Hm,tp=None,sl=None,sc=1.0):
    k=build_exit(book,Hm)
    if tp is None and sl is None: g=gross_returns(book,k,None,None)
    else:
        span=np.where(k>=0,k-np.arange(N),0); mw=int(min(max(3,span.max()+1),200))
        Rmax,Rmin,L=path_extremes(book,k,mw); g=gross_returns(book,k,tp,sl,sc,Rmax,Rmin,L)
        del Rmax,Rmin,L; gc.collect()
    return dict(k=k,net=netify(g,k,0.0114,-0.30,CAP),hard=netify(g,k,0.025,-1.00,CAP),
                d50=netify(g,k,0.0114,-0.50,CAP),d100=netify(g,k,0.0114,-1.00,CAP),
                t250=netify(g,k,0.025,-0.30,CAP),raw=netify(g,k,0.0114,-0.30,None))
def perm(mask,e,split,reps=400,seed=9):
    rng=np.random.default_rng(seed); net=e['net']
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
def show(tag,mask,e,off=1):
    for lab,sp in (('TR',TRAIN),('VA',VAL)):
        js=R.select(mask&sp,e['k'],off)
        if js.size<15: log("  %-44s %s n=%d TOO SMALL"%(tag,lab,js.size)); continue
        st=R.stats(js,e['net'],e['k'])
        log("  %-44s %s n=%3d k=%2d mean=%+.4f med=%+.4f cilo=%+.4f d50=%+.4f d100=%+.4f t250=%+.4f hard=%+.4f uncapped=%+.4f res=%.2f fpos=%.2f"%(
            tag,lab,st['n'],st['clusters'],st['mean'],st['median'],boot_lo(st['pm'],B=6000),
            R.stats(js,e['d50'])['mean'],R.stats(js,e['d100'])['mean'],R.stats(js,e['t250'])['mean'],
            R.stats(js,e['hard'])['mean'],R.stats(js,e['raw'])['mean'],st['res'],float((st['pm']>0).mean())))
mB=(F['vacc']>=q('vacc',0.90))&(F['vacc']<=q('vacc',0.99))&(F['vwapdev']>q('vwapdev',0.90))&(F['vrel5']>q('vrel5',0.90))
mB&=np.isfinite(F['vacc'])&np.isfinite(F['vwapdev'])&np.isfinite(F['vrel5'])
e5=mkexit(5,0.60)
log("=== H5 / tp+60%% : full cost & dropout sensitivity ===")
show("exact corner",mB,e5)
log("=== entry-delay (extra real bars of latency) ===")
for off in (1,2,3):
    show("off=%d"%off,mB,e5,off=off)
log("=== threshold plateau AT H5/tp60 (validate is the row that matters) ===")
for pa1,pa2,pw,pv in ((0.90,0.99,0.90,0.90),(0.88,0.99,0.88,0.88),(0.92,0.99,0.92,0.92),
                      (0.90,1.00,0.90,0.90),(0.90,0.98,0.90,0.90),(0.85,0.99,0.90,0.90),
                      (0.90,0.99,0.85,0.90),(0.90,0.99,0.90,0.85),(0.95,1.00,0.95,0.95)):
    m=(F['vacc']>=q('vacc',pa1))&(F['vwapdev']>q('vwapdev',pw))&(F['vrel5']>q('vrel5',pv))
    if pa2<1.0: m&=(F['vacc']<=q('vacc',pa2))
    m&=np.isfinite(F['vacc'])&np.isfinite(F['vwapdev'])&np.isfinite(F['vrel5'])
    show("vacc[q%d,q%d] vwap>q%d vrel5>q%d"%(pa1*100,pa2*100,pw*100,pv*100),m,e5)
log("=== TP sweep at H5 (is +60%% special?) ===")
for tp in (0.20,0.40,0.60,0.80,1.20,None):
    ee=mkexit(5,tp); show("H5 tp=%s"%tp,mB,ee); del ee; gc.collect()
log("=== permutation p-values (400 within-mint reshuffles) at H5/tp60 ===")
for lab,sp in (('TRAIN',TRAIN),('VALIDATE',VAL)):
    js=R.select(mB&sp,e5['k']); st=R.stats(js,e5['net'])
    mus,mds=perm(mB&sp,e5,sp,reps=400,seed=77)
    log("  %-9s mean=%+.4f ctrl=%+.4f p=%.3f | med=%+.4f ctrl=%+.4f p=%.3f"%(
        lab,st['mean'],mus.mean(),float((mus>=st['mean']).mean()),
        st['median'],mds.mean(),float((mds>=st['median']).mean())))
log("FINAL DONE")
