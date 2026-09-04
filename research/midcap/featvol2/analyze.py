import sys,json,gc,random
import numpy as np
sys.path.insert(0,'/home/anont/meme/research/midcap/featvol2')
from core import *
from feats import build_features
D='/home/anont/meme/research/midcap/featvol2/'
CAP=3.0
def log(*a): print(*a,flush=True)

# ---------- (a) how did the 300 validate candidates fail? ----------
V=json.load(open(D+'s3_validate.json'))['final']
log("validated candidates: %d"%len(V))
crit=dict(mean=0,med=0,hard=0,cilo=0,edgem=0,edgemd=0)
for r in V:
    if r.get('va_mean',-9)>0: crit['mean']+=1
    if r.get('va_med',-9)>0: crit['med']+=1
    if r.get('va_mean_hard',-9)>0: crit['hard']+=1
    if r.get('va_ci_lo',-9)>0: crit['cilo']+=1
    if r.get('va_edge_mean',-9)>0: crit['edgem']+=1
    if r.get('va_edge_med',-9)>0: crit['edgemd']+=1
log("passing each validate criterion individually (of %d): %s"%(len(V),crit))
V2=[r for r in V if 'va_mean' in r]
vm=np.array([r['va_mean'] for r in V2]); vd=np.array([r['va_med'] for r in V2])
tm=np.array([r['tr_mean'] for r in V2]); td=np.array([r['tr_med'] for r in V2])
ve=np.array([r['va_edge_mean'] for r in V2])
log("train mean: median=%+.4f  validate mean: median=%+.4f  best=%+.4f"%(np.median(tm),np.median(vm),vm.max()))
log("train med : median=%+.4f  validate med : median=%+.4f  best=%+.4f"%(np.median(td),np.median(vd),vd.max()))
log("validate edge-vs-permutation-control: median=%+.4f best=%+.4f frac>0=%.3f"%(np.median(ve),ve.max(),(ve>0).mean()))
if len(tm)>3:
    log("corr(train mean, validate mean) = %+.3f ; corr(train med, validate med) = %+.3f"%(
        np.corrcoef(tm,vm)[0,1],np.corrcoef(td,vd)[0,1]))
V2.sort(key=lambda r:-r['va_mean'])
log("TOP 12 BY VALIDATE MEAN:")
for r in V2[:12]:
    log("  %s & %s & %s | %s | tr(n=%d k=%d mean=%+.4f med=%+.4f) va(n=%d k=%d mean=%+.4f med=%+.4f ci_lo=%+.4f ctrl=%+.4f edge=%+.4f hard=%+.4f lag2=%+.4f)"%(
        r['c1'],r['c2'],r['c3'],r['exit'],r['tr_n'],r['tr_k'],r['tr_mean'],r['tr_med'],
        r['va_n'],r['va_k'],r['va_mean'],r['va_med'],r['va_ci_lo'],r['va_ctrl_mean'],
        r['va_edge_mean'],r['va_mean_hard'],r['va_mean_lag2']))

# ---------- (b) unbiased train<->validate consistency ----------
mints,data,nres=load(); book=Book(mints,data); F=build_features(book); N=book.N
BH=book.hh[book.MID]; TRAIN=book.valid_sig&(BH==1); VAL=book.valid_sig&(BH==2)
R=Runner(book)
FEATS=['vrel5','vrel20','vacc','rng','rngrel','dens10','dens30','gap','chop',
       'vwapdev','clspos','body','dvol','vshare','ret1','ret5','vzs','rngz','illiq','tickdir']
QS=[0.01,0.02,0.05,0.10,0.20,0.35,0.50,0.65,0.80,0.90,0.95,0.98,0.99]
CONDS=[('>',0.90),('>',0.95),('>',0.98),('>',0.99),('<',0.10),('<',0.05),('<',0.02),('<',0.01),
       ('in',(0.80,0.95)),('in',(0.05,0.20)),('in',(0.35,0.65)),('in',(0.90,0.99)),('in',(0.01,0.10))]
TH={f:{q:float(np.quantile(F[f][TRAIN][np.isfinite(F[f][TRAIN])],q)) for q in QS} for f in FEATS}
CB={};CN=[];COF={}
for f in FEATS:
    x=F[f];fin=np.isfinite(x)
    for op,arg in CONDS:
        if op=='>': m=fin&(x>TH[f][arg]); nm="%s>q%02d"%(f,int(arg*100))
        elif op=='<': m=fin&(x<TH[f][arg]); nm="%s<q%02d"%(f,int(arg*100))
        else:
            a,b=arg; m=fin&(x>=TH[f][a])&(x<=TH[f][b]); nm="%s@q%02d-%02d"%(f,int(a*100),int(b*100))
        CB[nm]=m;CN.append(nm);COF[nm]=f
SPECS=[('H5',5,None,None,1.0),('H15',15,None,None,1.0),('H30',30,None,None,1.0),
       ('H60',60,None,None,1.0),('H15tp30',15,0.30,None,1.0),('H30tp60sl40',30,0.60,-0.40,1.0)]
EX={}
for nm,Hm,tp,sl,sc in SPECS:
    k=build_exit(book,Hm)
    if tp is None and sl is None: g=gross_returns(book,k,None,None)
    else:
        span=np.where(k>=0,k-np.arange(N),0); mw=int(min(max(3,span.max()+1),200))
        Rmax,Rmin,L=path_extremes(book,k,mw); g=gross_returns(book,k,tp,sl,sc,Rmax,Rmin,L)
        del Rmax,Rmin,L; gc.collect()
    EX[nm]=dict(k=k,net=netify(g,k,0.0114,-0.30,CAP))

rng=random.Random(3)
cells=[(c,'') for c in CN]
pairs=[]
for _ in range(4000):
    a=rng.choice(CN); b=rng.choice(CN)
    if COF[a]==COF[b]: continue
    pairs.append((a,b))
pairs=list(dict.fromkeys(pairs))[:2500]
cells+=pairs
log("\nUNBIASED CONSISTENCY TEST on %d entry cells x %d exits (no pre-selection)"%(len(cells),len(EX)))
for exn,e in EX.items():
    xs=[];ys=[];xm=[];ym=[]
    for c1,c2 in cells:
        m=CB[c1]&(CB[c2] if c2 else True)
        jt=R.select(m&TRAIN,e['k']); jv=R.select(m&VAL,e['k'])
        if jt.size<50 or jv.size<50: continue
        st=R.stats(jt,e['net']); sv=R.stats(jv,e['net'])
        if st['clusters']<20 or sv['clusters']<20: continue
        xs.append(st['mean']);ys.append(sv['mean']);xm.append(st['median']);ym.append(sv['median'])
    if len(xs)<30: continue
    xs=np.array(xs);ys=np.array(ys);xm=np.array(xm);ym=np.array(ym)
    def sp(a,b):
        ra=np.argsort(np.argsort(a)).astype(float); rb=np.argsort(np.argsort(b)).astype(float)
        return float(np.corrcoef(ra,rb)[0,1])
    sl=float(np.polyfit(xs,ys,1)[0]); slm=float(np.polyfit(xm,ym,1)[0])
    # of the top-decile-on-train cells, what is the mean validate value?
    o=np.argsort(xs)[::-1]; topi=o[:max(5,len(o)//10)]
    log("  %-12s cells=%4d | MEAN  rho=%+.3f slope=%+.3f  trainTop10%%->validate mean=%+.4f (all cells validate mean=%+.4f)"%(
        exn,len(xs),sp(xs,ys),sl,ys[topi].mean(),ys.mean()))
    om=np.argsort(xm)[::-1]; topm=om[:max(5,len(om)//10)]
    log("  %-12s              | MEDIAN rho=%+.3f slope=%+.3f  trainTop10%%->validate med =%+.4f (all cells validate med =%+.4f)"%(
        exn,sp(xm,ym),slm,ym[topm].mean(),ym.mean()))

# ---------- (c) decile surface ----------
log("\nDECILE SURFACE (H15, capped net, mint-equal MEDIAN across mints; TRAIN | VALIDATE)")
e=EX['H15']
for f in FEATS:
    x=F[f]; q=np.quantile(x[TRAIN&np.isfinite(x)],np.linspace(0,1,11))
    tr=[];va=[]
    for d in range(10):
        m=np.isfinite(x)&(x>=q[d])&((x<=q[10]) if d==9 else (x<q[d+1]))
        for lab,msk,acc in (('T',TRAIN,tr),('V',VAL,va)):
            js=R.select(m&msk,e['k'])
            acc.append(R.stats(js,e['net'])['median'] if js.size>=25 else float('nan'))
    log("  %-8s T "%f+" ".join(("%+.2f"%v if v==v else "  na") for v in tr)+
        "   V "+" ".join(("%+.2f"%v if v==v else "  na") for v in va))
log("ANALYZE DONE")
