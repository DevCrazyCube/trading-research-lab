"""Full 3-way sweep restricted to FILLABLE bars: trailing-15m volume >= $3000 AND
signal-bar volume >= $100 (both causal, known at signal time). A $60 order is then
<= ~2% of the trailing 15m tape."""
import numpy as np, sys, pickle, itertools, time, collections
sys.path.insert(0,'/home/anont/meme/.scr')
from sim import *
t0=time.time(); rng=np.random.default_rng(5)
KI={n:i for i,n in enumerate(ALLF)}
LV=KI['lvol']; V15=KI['vol15']

GATE={}
for m in MINTS:
    g=(FM[m][:,V15]>=3000.0)&(FM[m][:,LV]>=np.log10(101.0))
    GATE[m]=g
ng=sum(int(g.sum()) for g in GATE.values()); nb=sum(len(GATE[m]) for m in MINTS)
print(f'fillable bars {ng}/{nb} = {ng/nb*100:.1f}%')

PAIRS=[('r5','le'),('r15','le'),('r60','le'),('dd','le'),('hi60','le'),('pxrel','le'),
       ('lmcap','le'),('lmcap','ge'),('volz','ge'),('volz','le'),('rng','ge'),('vol15','ge'),
       ('rv15','ge'),('r1','le'),('r1','ge'),('body','le'),('wickup','ge'),('gap','ge'),
       ('age','le'),('upfrac','ge'),('pgrad','ge'),('pcreate','le'),('lret15','le'),('nb15','ge')]
LEVQ={'le':[0.25,0.10,0.02],'ge':[0.75,0.90,0.98]}
gs=np.vstack([FM[m][GATE[m]] for m in TRAIN]); gv=np.vstack([VALID[m][GATE[m]] for m in TRAIN])
THR={}
for name,op in PAIRS:
    k=KI[name]; col=gs[:,k][gv[:,k]]
    THR[(name,op)]=[float(np.quantile(col,q)) for q in LEVQ[op]]
del gs,gv
CACHE={}
for m in MINTS:
    CACHE[m]={}
    for p in PAIRS:
        k=KI[p[0]]
        for li in range(3):
            thr=THR[p][li]
            c=(FM[m][:,k]>=thr) if p[1]=='ge' else (FM[m][:,k]<=thr)
            CACHE[m][(p,li)]=c&VALID[m][:,k]&GATE[m]
print('cache',time.time()-t0,flush=True)

def run_idx(SIG,mset,ex,pos,toll=TOLL,drop=-0.50):
    permint=[];ntr=0;nres=0
    H=ex[-1] if ex[0]!='H' else ex[1]
    for m in mset:
        idx=SIG.get(m)
        if idx is None or len(idx)==0: continue
        d=per[m]; n=len(d['ts']); ts=d['ts']
        rs=[];block=-1
        for s in idx:
            a=s+1
            if a>=n: break
            if a<=block: continue
            if ts[a]+H*60>gmax: break
            r,rr,ei=trade_ret(m,a,ex,pos,toll,drop)
            rs.append(r);ntr+=1
            if rr:nres+=1
            block= ei if ei>=0 else n
        if rs: permint.append(float(np.mean(rs)))
    if not permint: return None
    arr=np.array(permint)
    return dict(mean=float(arr.mean()),median=float(np.median(arr)),n=ntr,clusters=len(permint),
                res=nres/max(1,ntr),arr=arr)

GSIG={'T':{m:np.flatnonzero(GATE[m]) for m in TRAIN},'V':{m:np.flatnonzero(GATE[m]) for m in VALD}}
EX1=[('H',5),('H',15),('H',60),('TP',0.25,15),('TR',0.15,60),('TR',0.35,60),('BR',0.50,0.35,60)]
CTRL={}
print('\n=== GATED CONTROLS (all fillable bars) ===')
for ex in EX1:
    for lbl,ms in (('T',TRAIN),('V',VALD)):
        r=run_idx(GSIG[lbl],ms,ex,('FULL',))
        CTRL[(lbl,str(ex))]=r['mean']
        print(f"  {lbl} {str(ex):20s} mean={r['mean']*100:+7.2f}% med={r['median']*100:+7.2f}% n={r['n']:5d} k={r['clusters']:3d} res={r['res']*100:.0f}%")

TRIP=list(itertools.combinations(range(len(PAIRS)),3))
LEVCOMBO=[(0,0,0),(1,1,1),(2,2,2),(2,0,0),(0,2,0),(0,0,2)]
print('\ntriples',len(TRIP),flush=True)
res=[];nsw=0
for ti,(i,j,k) in enumerate(TRIP):
    pi,pj,pk=PAIRS[i],PAIRS[j],PAIRS[k]
    if pi[0]==pj[0] or pi[0]==pk[0] or pj[0]==pk[0]: continue
    for lc in LEVCOMBO:
        SIG={};tot=0
        for m in TRAIN:
            c=CACHE[m][(pi,lc[0])]&CACHE[m][(pj,lc[1])]&CACHE[m][(pk,lc[2])]
            ix=np.flatnonzero(c)
            if ix.size: SIG[m]=ix; tot+=ix.size
        if len(SIG)<25 or tot<60: nsw+=len(EX1); continue
        for ex in EX1:
            nsw+=1
            r=run_idx(SIG,TRAIN,ex,('FULL',))
            if r is None or r['clusters']<25 or r['n']<60: continue
            exc=r['mean']-CTRL[('T',str(ex))]
            if exc>0.05 and r['mean']>0:
                res.append(dict(key=((pi,pj,pk),lc),ex=ex,tmean=r['mean'],tmed=r['median'],
                                n=r['n'],cl=r['clusters'],texc=exc))
    if ti%200==0: print('trip',ti,len(res),round(time.time()-t0,1),flush=True)
print('GATED SWEPT',nsw,'train-positive',len(res),flush=True)
res.sort(key=lambda r:-r['texc'])

print('\n=== VALIDATE the top 250 gated train-positive cells ===')
out=[]
for r in res[:250]:
    trip,lc=r['key']; SIG={}
    for m in VALD:
        c=CACHE[m][(trip[0],lc[0])]&CACHE[m][(trip[1],lc[1])]&CACHE[m][(trip[2],lc[2])]
        ix=np.flatnonzero(c)
        if ix.size: SIG[m]=ix
    if len(SIG)<15: continue
    v=run_idx(SIG,VALD,r['ex'],('FULL',))
    if v is None or v['clusters']<15 or v['n']<30: continue
    cV=CTRL[('V',str(r['ex']))]
    arr=v['arr']; B=4000
    bs=arr[rng.integers(0,len(arr),size=(B,len(arr)))].mean(axis=1)
    p=max(float((bs<=cV).mean()),float((bs<=0).mean()))
    out.append(dict(**r,vmean=v['mean'],vmed=v['median'],vn=v['n'],vcl=v['clusters'],
                    vres=v['res'],vexc=v['mean']-cV,p=p,varr=arr))
out.sort(key=lambda o:o['p'])
M=len(out); kmax=0
for i,o in enumerate(out,1):
    if o['p']<=0.10*i/M: kmax=i
print(f'validated {M} cells; validate mean>0 {np.mean([o["vmean"]>0 for o in out])*100:.0f}%; '
      f'validate excess>0 {np.mean([o["vexc"]>0 for o in out])*100:.0f}%; '
      f'validate MEDIAN>0 {np.mean([o["vmed"]>0 for o in out])*100:.0f}%')
if M: print('corr(train excess, validate excess) =',round(float(np.corrcoef([o["texc"] for o in out],[o["vexc"] for o in out])[0,1]),3))
print('BH q=0.10 significant:',kmax,'of',M)
for o in out[:25]:
    tn='+'.join(f"{p[0]}{p[1]}{l}" for p,l in zip(o['key'][0],o['key'][1]))
    a=np.sort(o['varr'])[::-1]
    print(f"  p={o['p']:.4f} {tn:40s} {str(o['ex']):18s} T:{o['tmean']*100:+7.1f}(exc{o['texc']*100:+6.1f}) "
          f"V:{o['vmean']*100:+7.1f}(exc{o['vexc']*100:+6.1f}) Vmed={o['vmed']*100:+6.1f} n={o['vn']:4d} k={o['vcl']:3d} drop1={a[1:].mean()*100:+6.1f}%")
pickle.dump(dict(out=out,res=res,nsw=nsw,CTRL=CTRL,THR=THR),open(SCR+'gated.pkl','wb'))
