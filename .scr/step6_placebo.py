import numpy as np, sys, pickle, collections
sys.path.insert(0,'/home/anont/meme/.scr')
from sim import *
V=pickle.load(open(SCR+'validated.pkl','rb')); out=V['out']
S=pickle.load(open(SCR+'sweep3.pkl','rb')); THR=S['THR']
KI={n:i for i,n in enumerate(ALLF)}
rng=np.random.default_rng(2024)

def sigs(mset,key):
    trip,lc=key; SIG={}
    for m in mset:
        c=None
        for p,li in zip(trip,lc):
            k=KI[p[0]]; thr=THR[p][li]
            cc=(FM[m][:,k]>=thr) if p[1]=='ge' else (FM[m][:,k]<=thr)
            cc=cc&VALID[m][:,k]
            c=cc if c is None else (c&cc)
        ix=np.flatnonzero(c)
        if ix.size: SIG[m]=ix
    return SIG

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
    arr=np.array(permint)
    return arr,ntr,nres

allp=sorted(out,key=lambda o:max(o['p_ctrl'],o['p_zero']))
print('MATCHED RANDOM-ENTRY PLACEBO (same mints, same #signal bars per mint, same exit+position, VALIDATE fold)')
print('B=400 draws\n')
for o in allp[:10]:
    key=o['key']; ex=o['ex']; pos=o['pos']
    SIG=sigs(VALD,key)
    real,ntr,nres=run_idx(SIG,VALD,ex,pos)
    B=400; nulls=np.empty(B); nullmed=np.empty(B)
    for b in range(B):
        RS={}
        for m,ix in SIG.items():
            n=len(per[m]['ts'])
            RS[m]=np.sort(rng.choice(n,size=min(len(ix),n),replace=False))
        a,_,_=run_idx(RS,VALD,ex,pos)
        nulls[b]=a.mean(); nullmed[b]=np.median(a)
    p=float((nulls>=real.mean()).mean())
    tn='+'.join(f"{pp[0]}{pp[1]}{l}" for pp,l in zip(key[0],key[1]))
    print(f"{tn:34s} {str(ex):18s} {str(pos):12s} k={len(real):3d} n={ntr}")
    print(f"    REAL  mean={real.mean()*100:+7.2f}%  median={np.median(real)*100:+7.2f}%")
    print(f"    NULL  mean={nulls.mean()*100:+7.2f}% (sd {nulls.std()*100:.2f})  median={np.median(nullmed)*100:+7.2f}%")
    print(f"    edge over matched random = {(real.mean()-nulls.mean())*100:+7.2f}pp   placebo p = {p:.3f}")
