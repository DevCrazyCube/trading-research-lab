import sys,json
sys.path.insert(0,'/home/anont/meme/.ff3')
import numpy as np
from sweep import *
rng=np.random.default_rng(4242)
o=open('/home/anont/meme/.ff3/tails_out.txt','w',buffering=1)
TRAIN=(h==1); VAL=(h==2); TOLL=0.025; MI=0
NSW=[0]
def boot(per,B=3000):
    n=len(per)
    if n<5: return (float('nan'),float('nan'))
    idx=rng.integers(0,n,size=(B,n)); s=per[idx].mean(axis=1)
    return float(np.percentile(s,2.5)),float(np.percentile(s,97.5))
CTRL={}
for hi in range(len(HORS)):
    for sp,sm in (('train',TRAIN),('val',VAL)):
        CTRL[(hi,sp)]=evaluate(MI,hi,sm,('hold',None,None),TOLL)['mean']

# ---- 1) EXTREME TAILS x all structures
o.write("=== 1) EXTREME TAILS (beyond q90 / below q10), all 37 structures, both splits ===\n")
HI=[91,93,95,97,98,99]; LO=[1,2,3,5,7,9]
best=[]
for fi in range(NFLOW):
    col=FEAT[:,fi]; nm=str(names[fi])
    for p in HI:
        q=float(np.percentile(col[TRAIN],p)); m=col>=q; lab='%s>=q%d'%(nm,p)
        for hi in range(len(HORS)):
            for st in STRUCTS:
                a=evaluate(MI,hi,m&TRAIN,st,TOLL); NSW[0]+=1
                if a is None or a['n']<120 or a['k']<30: continue
                b=evaluate(MI,hi,m&VAL,st,TOLL); NSW[0]+=1
                if b is None or b['n']<60 or b['k']<20: continue
                best.append((a['mean'],b['mean'],a['n'],b['n'],a['k'],b['k'],lab,HORS[hi],st,hi,m))
    for p in LO:
        q=float(np.percentile(col[TRAIN],p)); m=col<=q; lab='%s<=q%d'%(nm,p)
        for hi in range(len(HORS)):
            for st in STRUCTS:
                a=evaluate(MI,hi,m&TRAIN,st,TOLL); NSW[0]+=1
                if a is None or a['n']<120 or a['k']<30: continue
                b=evaluate(MI,hi,m&VAL,st,TOLL); NSW[0]+=1
                if b is None or b['n']<60 or b['k']<20: continue
                best.append((a['mean'],b['mean'],a['n'],b['n'],a['k'],b['k'],lab,HORS[hi],st,hi,m))
T=np.array([x[0] for x in best]); V=np.array([x[1] for x in best])
o.write("evaluated %d tail x structure combos; train>0 %d ; val>0 %d ; both>0 %d\n"%(len(best),int((T>0).sum()),int((V>0).sum()),int(((T>0)&(V>0)).sum())))
bp=[x for x in best if x[0]>0 and x[1]>0]
o.write("--- positive on BOTH splits (%d) ---\n"%len(bp))
for x in sorted(bp,key=lambda y:-y[1])[:40]:
    b=evaluate(MI,x[9],x[10]&VAL,x[8],TOLL)
    lo,hh=boot(b['permint'])
    ru=evaluate(MI,x[9],VAL,x[8],TOLL)
    ms=[]
    rate=float((x[10]&VAL).sum())/float(VAL.sum())
    for _ in range(20):
        rr=evaluate(MI,x[9],(rng.random(NR)<rate)&VAL,x[8],TOLL)
        if rr: ms.append(rr['mean'])
    o.write("  train %+.4f val %+.4f med %+.4f ci[%+.4f,%+.4f] ctrlSAMEstruct %+.4f randctrl %+.4f n %d k %d | %s H=%d %s\n"%(
       x[0],x[1],b['median'],lo,hh,ru['mean'],float(np.mean(ms)),x[3],x[5],x[6],x[7],x[8]))
o.write("swept %d\n"%NSW[0])

# ---- 2) GRADUATION TARGETING
o.write("\n=== 2) GRADUATION TARGETING: can flow predict completion? ===\n")
hi=3  # 30 min
base_tr=float(grad[MI,hi][TRAIN&valid[MI,hi]].mean()); base_va=float(grad[MI,hi][VAL&valid[MI,hi]].mean())
o.write("unconditional grad-within-30min rate: train %.4f val %.4f\n"%(base_tr,base_va))
gr=[]
for fi in range(NFLOW):
    col=FEAT[:,fi]; nm=str(names[fi])
    for p in [80,90,95,98,99]:
        q=float(np.percentile(col[TRAIN],p)); m=(col>=q)&valid[MI,hi]
        for lab,mm in (('%s>=q%d'%(nm,p),m),):
            a=mm&TRAIN; b=mm&VAL
            if a.sum()<150 or b.sum()<150: continue
            gt=float(grad[MI,hi][a].mean()); gv=float(grad[MI,hi][b].mean())
            NSW[0]+=1
            gr.append((gt,gv,lab,int(a.sum()),int(b.sum())))
gr.sort(key=lambda x:-x[0])
o.write("top 12 flow conditions by TRAIN grad rate -> validate grad rate:\n")
for g in gr[:12]: o.write("   train %.4f -> val %.4f (lift %.1fx) n_tr %d n_va %d  %s\n"%(g[0],g[1],g[1]/base_va,g[3],g[4],g[2]))
# return of the best grad-targeting cells, plus optimistic grad repricing
o.write("returns of the top-3 grad-targeting cells on VALIDATE (hold 30m):\n")
for g in gr[:3]:
    nm=g[2].split('>=')[0]; p=int(g[2].split('q')[-1])
    fi=[str(x) for x in names].index(nm); col=FEAT[:,fi]
    q=float(np.percentile(col[TRAIN],p)); m=col>=q
    b=evaluate(MI,hi,m&VAL,('hold',None,None),TOLL)
    lo,hh=boot(b['permint'])
    o.write("   %s: val %+.4f med %+.4f ci[%+.4f,%+.4f] n %d k %d gradfrac %.3f (ctrl %+.4f)\n"%(g[2],b['mean'],b['median'],lo,hh,b['n'],b['k'],b['gradfrac'],CTRL[(hi,'val')]))
    for bonus in (0.25,0.50,1.00):
        rows=b['rows']; r=struct_ret(MI,hi,rows,'hold',None,None).astype(np.float64)-TOLL
        gmask=grad[MI,hi][rows].astype(bool)
        r2=np.where(gmask,r+bonus,r)
        c=cid[rows]; u,inv=np.unique(c,return_inverse=True)
        per=np.bincount(inv,weights=r2)/np.bincount(inv)
        o.write("      if every graduating exit actually paid +%.0f%% more: val %+.4f\n"%(bonus*100,per.mean()))
o.write("TOTAL SWEPT %d\n"%NSW[0])
o.close()
