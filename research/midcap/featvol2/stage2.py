import sys,time,csv,pickle,gc,json
import numpy as np
sys.path.insert(0,'/home/anont/meme/research/midcap/featvol2')
from core import *
from feats import build_features

D='/home/anont/meme/research/midcap/featvol2/'
t0=time.time()
mints,data,nres=load()
book=Book(mints,data)
F=build_features(book)
N=book.N
BH=book.hh[book.MID]
TRAIN=book.valid_sig&(BH==1); VAL=book.valid_sig&(BH==2)
TH=pickle.load(open(D+'thresholds.pkl','rb'))

def cond_mask(nm):
    if '@' in nm:
        f,rest=nm.split('@'); a,b=rest.split('-')
        qa=int(a[1:])/100.0; qb=int(b)/100.0
        x=F[f];fin=np.isfinite(x)
        return fin&(x>=TH[f][qa])&(x<=TH[f][qb])
    if '>' in nm:
        f,q=nm.split('>'); x=F[f]
        return np.isfinite(x)&(x>TH[f][int(q[1:])/100.0])
    f,q=nm.split('<'); x=F[f]
    return np.isfinite(x)&(x<TH[f][int(q[1:])/100.0])

# ---------------- exit / position grid (stage 2) ----------------
EXITS=[]
for Hm in (5,10,15,20,30,45,60,90,120,180):
    EXITS.append(('H%d'%Hm,Hm,None,None,1.0))
for Hm in (15,30,60,120):
    for tp in (0.15,0.30,0.60,1.00):
        EXITS.append(('H%dtp%d'%(Hm,int(tp*100)),Hm,tp,None,1.0))
    for sl in (-0.20,-0.35,-0.50):
        EXITS.append(('H%dsl%d'%(Hm,int(-sl*100)),Hm,None,sl,1.0))
    for tp in (0.30,0.60):
        for sl in (-0.20,-0.35):
            EXITS.append(('H%dtp%dsl%d'%(Hm,int(tp*100),int(-sl*100)),Hm,tp,sl,1.0))
    for tp in (0.25,0.50):
        EXITS.append(('H%dscale50tp%d'%(Hm,int(tp*100)),Hm,tp,None,0.5))
        EXITS.append(('H%dscale50tp%dsl35'%(Hm,int(tp*100)),Hm,tp,-0.35,0.5))
print("exit structures=%d"%len(EXITS),flush=True)

EX={}
for nm,Hm,tp,sl,sc in EXITS:
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
                nets={(t,d):netify(g,k,t,d) for t in (0.0114,0.025) for d in (-0.30,-0.50,-1.00)})
print("exits built t=%.1f"%(time.time()-t0),flush=True)

R=Runner(book)
MIN_N=60;MIN_K=25

def ev(mask,exn,toll=0.0114,drop=-0.30):
    e=EX[exn]; js=R.select(mask,e['k'])
    if js.size<MIN_N: return None
    st=R.stats(js,e['nets'][(toll,drop)],e['k'])
    if st['clusters']<MIN_K: return None
    st['js']=js
    return st

def perm_control(mask,exn,split,reps=40,seed=5,toll=0.0114,drop=-0.30):
    """within-mint permutation of the signal mask: preserves per-mint signal COUNT,
    destroys the timing information. Same greedy + same exit structure."""
    rng=np.random.default_rng(seed)
    e=EX[exn]; net=e['nets'][(toll,drop)]
    pool=np.flatnonzero(split)
    mid=book.MID[pool]; sel=mask[pool]
    order=np.argsort(mid,kind='stable')
    mid_s=mid[order]; pool_s=pool[order]; sel_s=sel[order]
    bnds=np.flatnonzero(np.diff(mid_s))+1
    segs=np.split(np.arange(pool_s.size),bnds)
    cnts=[int(sel_s[s].sum()) for s in segs]
    means=[];meds=[]
    for r in range(reps):
        m=np.zeros(N,bool)
        for s,c in zip(segs,cnts):
            if c<=0: continue
            pick=rng.choice(s.size,size=c,replace=False)
            m[pool_s[s[pick]]]=True
        js=R.select(m,e['k'])
        if js.size<5: continue
        st=R.stats(js,net)
        means.append(st['mean']);meds.append(st['median'])
    if not means: return None
    return dict(mean=float(np.mean(means)),median=float(np.mean(meds)),
                sd=float(np.std(means)),reps=len(means))

if __name__=='__main__':
    # -------- pick train candidates --------
    cand=[]
    with open(D+'train_rows.csv') as fh:
        for r in csv.DictReader(fh):
            cand.append((r['c1'],r['c2'],float(r['mean']),float(r['median']),int(r['n']),int(r['k'])))
    # unique entry conditions ranked by best train mean over the stage-1 exits
    best={}
    for c1,c2,mu,md,n,kk in cand:
        key=(c1,c2)
        if key not in best or mu>best[key][0]: best[key]=(mu,md,n,kk)
    ranked=sorted(best.items(),key=lambda kv:-kv[1][0])
    TOPK=int(sys.argv[1]) if len(sys.argv)>1 else 400
    top=[k for k,v in ranked[:TOPK]]
    print("entry conditions carried to stage2: %d (of %d)"%(len(top),len(ranked)),flush=True)

    masks={}
    for c1,c2 in top:
        m=cond_mask(c1)
        if c2: m=m&cond_mask(c2)
        masks[(c1,c2)]=m

    combos=0; out=[]
    for key in top:
        m=masks[key]
        mt=m&TRAIN
        if mt.sum()<MIN_N: continue
        for exn in EX:
            combos+=1
            st=ev(mt,exn)
            if st is None: continue
            if st['mean']<=0: continue
            st2=ev(mt,exn,0.025,-1.00)
            out.append(dict(c1=key[0],c2=key[1],exit=exn,tr_n=st['n'],tr_k=st['clusters'],
                            tr_mean=st['mean'],tr_med=st['median'],tr_res=st['res'],
                            tr_mean_hard=(st2['mean'] if st2 else float('nan'))))
    print("stage2 train combos=%d positive=%d t=%.1f"%(combos,len(out),time.time()-t0),flush=True)
    json.dump(dict(rows=out,combos=combos),open(D+'stage2_train.json','w'))
