import sys
sys.path.insert(0,'/home/anont/meme/.ff3')
import numpy as np
from sweep import *
rng=np.random.default_rng(31337)
o=open('/home/anont/meme/.ff3/grad_out.txt','w',buffering=1)
TRAIN=(h==1); VAL=(h==2); TOLL=0.025; MI=0
NSW=[0]
def boot(per,B=4000):
    n=len(per)
    if n<5: return (float('nan'),float('nan'))
    idx=rng.integers(0,n,size=(B,n)); s=per[idx].mean(axis=1)
    return float(np.percentile(s,2.5)),float(np.percentile(s,97.5))
FN=[str(x) for x in names]
o.write("thr | H | struct | TRAIN mean/med/n/k | VAL mean/med/n/k | ci | randctrl | gradfrac | g-30 g-50 g-100\n")
rowsout=[]
for f in ['netsol_150','netsol_450','netsol_900','rate_450','uniqbuy_450']:
    fi=FN.index(f); col=FEAT[:,fi]
    for p in [90,95,97,98,99]:
        q=float(np.percentile(col[TRAIN],p)); m=col>=q
        for hi,H in enumerate(HORS):
            for st in [('hold',None,None),('tp',1,None),('sl',None,1),('brk',1,1),('scale',1,None)]:
                a=evaluate(MI,hi,m&TRAIN,st,TOLL); b=evaluate(MI,hi,m&VAL,st,TOLL); NSW[0]+=2
                if a is None or b is None: continue
                if a['k']<10 or b['k']<10: continue
                lo,hh=boot(b['permint'])
                rate=float((m&VAL).sum())/float(VAL.sum())
                ms=[]
                for _ in range(20):
                    rr=evaluate(MI,hi,(rng.random(NR)<rate)&VAL,st,TOLL)
                    if rr: ms.append(rr['mean'])
                rc=float(np.mean(ms))
                g={}
                for gc in (-0.30,-0.50,-1.00):
                    rg=evaluate(MI,hi,m&VAL,st,TOLL,gradcharge=gc); g[gc]=rg['mean']
                line="%s>=q%-2d H=%4d %-18s | TR %+.4f/%+.4f n%4d k%4d | VA %+.4f/%+.4f n%4d k%4d | ci[%+.4f,%+.4f] rand %+.4f | gf %.3f | %+.4f %+.4f %+.4f"%(
                    f,p,H,str(st),a['mean'],a['median'],a['n'],a['k'],b['mean'],b['median'],b['n'],b['k'],lo,hh,rc,b['gradfrac'],g[-0.30],g[-0.50],g[-1.00])
                rowsout.append((a['mean']>0 and b['mean']>0,b['mean'],line))
rowsout.sort(key=lambda x:(-x[0],-x[1]))
for ok,v,l in rowsout:
    o.write(("BOTH+ " if ok else "      ")+l+"\n")
o.write("swept %d\n"%NSW[0])
o.close()
