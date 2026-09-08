import numpy as np, sys, pickle, collections
sys.path.insert(0,'/home/anont/meme/.scr')
from sim import *
V=pickle.load(open(SCR+'validated.pkl','rb'))
out=V['out']; REGION=V['REGION']; CTRL=V['CTRL']
rng=np.random.default_rng(11)

print('=== RESPONSE SURFACE: TRAIN excess by EXIT family (all %d cells of stage-3b grid) ==='%len(REGION))
agg=collections.defaultdict(list)
for ex,pos,exc,mean,med,n,cl,f1,f2,f3,lc in REGION:
    fam=ex.split("'")[1]; H=ex.rstrip(')').split(',')[-1].strip()
    agg[(fam,H)].append((exc,mean,med))
for k in sorted(agg):
    a=np.array(agg[k])
    print(f"  exit={str(k):18s} cells={len(a):5d} medianTexc={np.median(a[:,0])*100:+7.2f}pp  frac>0={np.mean(a[:,0]>0)*100:5.1f}%  medianTmedian={np.median(a[:,2])*100:+7.2f}%")
print()
print('=== TRAIN excess by POSITION structure ===')
agg=collections.defaultdict(list)
for ex,pos,exc,mean,med,n,cl,f1,f2,f3,lc in REGION: agg[pos].append(exc)
for k in sorted(agg): print(f"  {k:16s} cells={len(agg[k]):5d} medianTexc={np.median(agg[k])*100:+7.2f}pp frac>0={np.mean(np.array(agg[k])>0)*100:5.1f}%")
print()
print('=== TRAIN excess by FEATURE appearing in the triple ===')
agg=collections.defaultdict(list)
for ex,pos,exc,mean,med,n,cl,f1,f2,f3,lc in REGION:
    for f in (f1,f2,f3): agg[f].append(exc)
for k,v in sorted(agg.items(),key=lambda kv:-np.median(kv[1])):
    print(f"  {k:12s} cells={len(v):6d} medianTexc={np.median(v)*100:+7.2f}pp")
print()
print('=== VALIDATE: sign agreement of the 400 train-best cells ===')
vm=np.array([o['vmean'] for o in out]); ve=np.array([o['vexc'] for o in out])
vmed=np.array([o['vmed'] for o in out])
print(f"  validate mean>0 : {np.mean(vm>0)*100:.1f}%   validate excess>0 : {np.mean(ve>0)*100:.1f}%   validate MEDIAN>0 : {np.mean(vmed>0)*100:.1f}%")
print(f"  median validate mean {np.median(vm)*100:+.2f}%  median validate excess {np.median(ve)*100:+.2f}pp  median validate median {np.median(vmed)*100:+.2f}%")
print(f"  corr(train excess, validate excess) = {np.corrcoef([o['texc'] for o in out],ve)[0,1]:+.3f}")
print()
print('=== VALIDATE excess by exit family (the 400) ===')
agg=collections.defaultdict(list)
for o in out: agg[o['ex'][0]].append(o['vexc'])
for k,v in agg.items(): print(f"  {k:4s} n={len(v):4d} medianVexc={np.median(v)*100:+7.2f}pp frac>0={np.mean(np.array(v)>0)*100:5.1f}%")
print()
print('=== CONCENTRATION STRESS TEST on top-20 by p (drop single best mint) ===')
allp=sorted(out,key=lambda o:max(o['p_ctrl'],o['p_zero']))
for o in allp[:20]:
    a=np.sort(o['varr'])[::-1]
    m_all=a.mean(); m_drop1=a[1:].mean() if len(a)>1 else float('nan'); m_drop2=a[2:].mean() if len(a)>2 else float('nan')
    tn='+'.join(f"{p[0]}{p[1]}{l}" for p,l in zip(o['key'][0],o['key'][1]))
    share=a[0]/ (a.sum()) if a.sum()!=0 else float('nan')
    print(f"  {tn:36s} {str(o['ex']):18s} {str(o['pos']):12s} k={o['vcl']:3d} V={m_all*100:+7.1f}% drop1={m_drop1*100:+7.1f}% drop2={m_drop2*100:+7.1f}% ctrl={o['vctrl']*100:+6.1f}% top1share={share*100:5.1f}%")
print()
print('=== SAME STRESS on the ALL-BARS control (random entries) for reference ===')
def allsig(mset): return {m:np.arange(len(per[m]['ts'])) for m in mset}
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
            r,rr,ei=trade_ret(m,a,ex,pos,toll,drop)
            rs.append(r);ntr+=1
            if rr:nres+=1
            block= ei if ei>=0 else n
        if rs: permint.append(float(np.mean(rs)))
    arr=np.array(permint)
    return arr,ntr,nres
AS=allsig(VALD)
for ex in [('TR',0.15,60),('TR',0.35,60),('H',5),('H',15)]:
    arr,ntr,nres=run_idx(AS,VALD,ex,('FULL',))
    a=np.sort(arr)[::-1]
    print(f"  ctrl {str(ex):18s} k={len(a)} mean={a.mean()*100:+7.1f}% drop1={a[1:].mean()*100:+7.1f}% drop2={a[2:].mean()*100:+7.1f}% median={np.median(a)*100:+6.1f}% top1share={a[0]/a.sum()*100:5.1f}%")
print()
print('=== ROBUSTNESS of top-8: toll 2.5%, dropout -30/-100, and MEDIAN ===')
def sigs(mset,key):
    KI={n:i for i,n in enumerate(ALLF)}
    S=pickle.load(open(SCR+'sweep3.pkl','rb')); THR=S['THR']
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
for o in allp[:8]:
    S=sigs(VALD,o['key'])
    tn='+'.join(f"{p[0]}{p[1]}{l}" for p,l in zip(o['key'][0],o['key'][1]))
    line=[]
    for toll,drop in ((0.0114,-0.30),(0.0114,-1.00),(0.025,-0.50)):
        arr,ntr,nres=run_idx(S,VALD,o['ex'],o['pos'],toll=toll,drop=drop)
        line.append(f"toll{toll*100:.2f}/drop{drop:+.2f}: {arr.mean()*100:+7.1f}%")
    print(f"  {tn:34s} {str(o['ex']):16s} "+'  '.join(line))
