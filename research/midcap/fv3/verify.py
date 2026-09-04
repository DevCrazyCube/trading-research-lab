import sys,sqlite3,hashlib,json,collections
sys.path.insert(0,'/home/anont/meme/research/midcap/fv3')
import numpy as np, fvh, common
W='/home/anont/meme/research/midcap/fv3/'
O=open(W+'logV.txt','w',buffering=1)
def P(*a): O.write(' '.join(str(x) for x in a)+'\n')
mints,arrs,meta=fvh.load(minbars=22)
hs=[fvh.h_of(m) for m in mints]
P('HOLDOUT CHECK: loaded %d mints; hash dist %s ; any h==0 loaded? %s'%(
    len(mints),dict(collections.Counter(hs)),any(h==0 for h in hs)))
E=common.build(log=P); greedy,ev=common.make_eval(E)
# the one replicated structure: absolute 1-min SOL volume -> forward return, both splits
P('\n=== the one replicated (negative) structure: absolute traded volume level ===')
for s in ['H5/tpNone/slNone/f1.0','H15/tpNone/slNone/f1.0','H30/tpNone/slNone/f1.0']:
    for fname in ['vsol1','vsol5','illiq','gapavg5']:
        i=E.FN.index(fname); v=E.Fm[i]
        cut=np.percentile(v[E.TRi],[20,80])
        rows=[]
        for nm,idx in [('TR',E.TRi),('VA',E.VAi)]:
            lowr=ev(idx[v[idx]<cut[0]],s); hir=ev(idx[v[idx]>=cut[1]],s)
            rows.append('%s low20%%=%+.4f(k=%d) high20%%=%+.4f(k=%d)'%(nm,lowr['mean'],lowr['clusters'],hir['mean'],hir['clusters']))
        P('%-24s %-8s %s | %s'%(s,fname,rows[0],rows[1]))
P('VERIFY_DONE')
O.close()
