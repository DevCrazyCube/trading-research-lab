import numpy as np, sys, pickle, itertools, time
sys.path.insert(0,'/home/anont/meme/.scr')
from sim import *

t0=time.time()
PAIRS=[('r5','le'),('r15','le'),('r60','le'),('dd','le'),('hi60','le'),('pxrel','le'),
       ('lmcap','le'),('volz','le'),('rng','le'),('vol15','le'),('lvol','le'),
       ('rv15','ge'),('r1','le'),('body','le'),('wickup','ge'),('gap','ge'),('age','le'),
       ('pgrad','ge'),('pcreate','le'),('lret15','le')]
LEV={'le':[0.25,0.10,0.02],'ge':[0.75,0.90,0.98]}
KI={n:i for i,n in enumerate(ALLF)}

# thresholds on TRAIN bars only
stack=np.vstack([FM[m] for m in TRAIN]); vst=np.vstack([VALID[m] for m in TRAIN])
THR={}
for name,op in PAIRS:
    k=KI[name]; col=stack[:,k][vst[:,k]]
    THR[(name,op)]=[float(np.quantile(col,q)) for q in LEV[op]]
del stack,vst

def cond_arr(m,name,op,li):
    k=KI[name]; thr=THR[(name,op)][li]
    X=FM[m]; V=VALID[m]
    c=(X[:,k]>=thr) if op=='ge' else (X[:,k]<=thr)
    return c & V[:,k]

# precompute per-mint per-pair per-level boolean arrays (memory ok: 20*3 bool arrays per mint)
CACHE={}
for m in MINTS:
    CACHE[m]={}
    for p in PAIRS:
        for li in range(3):
            CACHE[m][(p,li)]=cond_arr(m,p[0],p[1],li)
print('cache built',time.time()-t0)

EX1=[('H',5),('H',15),('H',60),('TP',0.25,15),('TR',0.35,60),('BR',0.50,0.35,60)]
def allmask(m): return np.ones(len(per[m]['ts']),dtype=bool)
CTRL={}
for ex in EX1:
    for lbl,ms in (('T',TRAIN),('V',VALD)):
        CTRL[(lbl,str(ex))]=run(allmask,ms,ex,('FULL',),drop=-0.50)['mean']

def run_idx(SIG,mset,ex,pos,toll=TOLL,drop=-0.50):
    permint=[];ntr=0;nres=0
    H=ex[-1] if ex[0]!='H' else ex[1]
    for m in mset:
        idx=SIG.get(m)
        if idx is None or idx.size==0: continue
        d=per[m]; n=len(d['ts']); ts=d['ts']
        rs=[];block=-1
        for s in idx:
            a=s+1
            if a>=n: break
            if a<=block: continue
            if ts[a]+H*60>gmax: break
            r,res,ei=trade_ret(m,a,ex,pos,toll,drop)
            rs.append(r);ntr+=1
            if res:nres+=1
            block= ei if ei>=0 else n
        if rs: permint.append(float(np.mean(rs)))
    if not permint: return None
    arr=np.array(permint)
    return dict(mean=float(arr.mean()),median=float(np.median(arr)),n=ntr,
                clusters=len(permint),res=nres/max(1,ntr),arr=arr)

TRIPLES=list(itertools.combinations(range(len(PAIRS)),3))
LEVCOMBO=[(0,0,0),(1,1,1),(2,2,2),(2,0,0),(0,2,0),(0,0,2)]
print('triples',len(TRIPLES),'levcombos',len(LEVCOMBO))

res=[];nsweep=0
for ti,(i,j,k) in enumerate(TRIPLES):
    pi,pj,pk=PAIRS[i],PAIRS[j],PAIRS[k]
    for lc in LEVCOMBO:
        SIG={}
        tot=0
        for m in TRAIN:
            c=CACHE[m][(pi,lc[0])]&CACHE[m][(pj,lc[1])]&CACHE[m][(pk,lc[2])]
            ix=np.flatnonzero(c)
            if ix.size: SIG[m]=ix; tot+=ix.size
        if len(SIG)<25 or tot<60:
            nsweep+=len(EX1); continue
        for ex in EX1:
            nsweep+=1
            r=run_idx(SIG,TRAIN,ex,('FULL',))
            if r is None or r['clusters']<25 or r['n']<60: continue
            exc=r['mean']-CTRL[('T',str(ex))]
            if exc>0.05 and r['mean']>0:
                res.append(dict(trip=(pi,pj,pk),lc=lc,ex=ex,tmean=r['mean'],tmed=r['median'],
                                n=r['n'],cl=r['clusters'],res=r['res'],exc=exc))
    if ti%100==0: print('trip',ti,len(res),round(time.time()-t0,1),flush=True)

res.sort(key=lambda r:-r['exc'])
print('SWEPT',nsweep,'POSITIVE-ON-TRAIN',len(res),'elapsed',time.time()-t0)
pickle.dump(dict(res=res,THR=THR,PAIRS=PAIRS,LEV=LEV,LEVCOMBO=LEVCOMBO,CTRL=CTRL,nsweep=nsweep),
            open(SCR+'sweep3.pkl','wb'))
for r in res[:40]:
    tn='+'.join(f"{p[0]}{p[1]}{l}" for p,l in zip(r['trip'],r['lc']))
    print(f"{tn:44s} {str(r['ex']):22s} exc={r['exc']*100:+7.2f} mean={r['tmean']*100:+8.2f} med={r['tmed']*100:+7.2f} n={r['n']:5d} k={r['cl']:3d}")
