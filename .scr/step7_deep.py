import numpy as np, sys, pickle
sys.path.insert(0,'/home/anont/meme/.scr')
from sim import *
S=pickle.load(open(SCR+'sweep3.pkl','rb')); THR=S['THR']
KI={n:i for i,n in enumerate(ALLF)}
rng=np.random.default_rng(99)
KEY=((('r5','le'),('lvol','le'),('wickup','ge')),(2,0,0))
EX=('TR',0.15,60); POSN=('FULL',)
print('thresholds:', [(p, THR[p][l]) for p,l in zip(KEY[0],KEY[1])])

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

def run_idx(SIG,mset,ex,pos,toll=TOLL,drop=-0.50,detail=False):
    permint=[];ntr=0;nres=0;det=[]
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
            if detail: det.append((m,a,r,10**float(FM[m][a,14])-1,10**float(FM[m][s,14])-1,float(d['cl'][a])))
            block= ei if ei>=0 else n
        if rs: permint.append(float(np.mean(rs)))
    return np.array(permint),ntr,nres,det

for lbl,ms in (('TRAIN',TRAIN),('VALIDATE',VALD)):
    SIG=sigs(ms,KEY)
    arr,ntr,nres,det=run_idx(SIG,ms,EX,POSN,detail=True)
    print(f"\n--- {lbl} --- k={len(arr)} n={ntr} res={nres/max(1,ntr)*100:.0f}% mean={arr.mean()*100:+.2f}% median={np.median(arr)*100:+.2f}%")
    tr=np.array([d[2] for d in det])
    print(f"  trade-level: mean={tr.mean()*100:+.2f}% median={np.median(tr)*100:+.2f}% winrate={np.mean(tr>0)*100:.1f}% max={tr.max()*100:+.1f}% min={tr.min()*100:+.1f}%")
    ev=np.array([d[3] for d in det]); sv=np.array([d[4] for d in det])
    print(f"  ENTRY-BAR volume (USD): median={np.median(ev):.1f} p25={np.percentile(ev,25):.1f} p75={np.percentile(ev,75):.1f}  frac<$100={np.mean(ev<100)*100:.0f}% frac<$500={np.mean(ev<500)*100:.0f}%")
    print(f"  SIGNAL-BAR volume (USD): median={np.median(sv):.1f}")
    a=np.sort(arr)[::-1]
    print(f"  concentration: top1={a[0]*100:+.1f}% share={a[0]/a.sum()*100:.0f}%  mean_drop1={a[1:].mean()*100:+.1f}% mean_drop3={a[3:].mean()*100:+.1f}%")
    # matched placebo
    B=400; nulls=np.empty(B)
    for b in range(B):
        RS={}
        for m,ix in SIG.items():
            n=len(per[m]['ts']); RS[m]=np.sort(rng.choice(n,size=min(len(ix),n),replace=False))
        na,_,_,_=run_idx(RS,ms,EX,POSN)
        nulls[b]=na.mean()
    print(f"  matched-random null mean={nulls.mean()*100:+.2f}% sd={nulls.std()*100:.2f}  placebo p={float((nulls>=arr.mean()).mean()):.4f}")

# universe volume reference
allv=np.concatenate([10**FM[m][:,14]-1 for m in MINTS])
print(f"\nUNIVERSE bar volume (USD): median={np.median(allv):.1f} p25={np.percentile(allv,25):.1f} frac<$100={np.mean(allv<100)*100:.0f}%")

# slippage sensitivity: extra cost per side as function of assumed impact
print("\nSLIPPAGE SENSITIVITY on VALIDATE (extra round-trip cost beyond the 1.14% toll):")
SIG=sigs(VALD,KEY)
for extra in (0.0,0.05,0.10,0.20,0.30,0.50):
    arr,ntr,nres,det=run_idx(SIG,VALD,EX,POSN,toll=TOLL+extra)
    print(f"  extra={extra*100:4.0f}%  mean={arr.mean()*100:+7.2f}%  median={np.median(arr)*100:+7.2f}%")
