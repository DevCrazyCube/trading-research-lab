import sys,time,collections
sys.path.insert(0,'/home/anont/meme/research/midcap/fv3')
import numpy as np, fvh, common
W='/home/anont/meme/research/midcap/fv3/'
OUT=open(W+'logO.txt','w',buffering=1)
def P(*a): OUT.write(' '.join(str(x) for x in a)+'\n')
E=common.build(log=P); greedy,ev=common.make_eval(E)
TRi=E.TRi; VAi=E.VAi
for s in ['H5/tpNone/slNone/f1.0','H15/tpNone/slNone/f1.0','H15/tp0.3/sl-0.25/f1.0']:
    for nm,idx in [('TRAIN',TRi),('VALID',VAi)]:
        r=ev(idx,s)
        pm=np.sort(r['pm'])[::-1]
        P('\n%s %s  n=%d k=%d mean=%+.4f median=%+.4f'%(s,nm,r['n'],r['clusters'],r['mean'],r['median']))
        P('   per-mint mean returns: top5 %s ... bottom5 %s'%(
            ' '.join('%+.2f'%x for x in pm[:5]),' '.join('%+.2f'%x for x in pm[-5:])))
        P('   pct of mints with positive mean: %.3f   mean excl. best mint: %+.4f   excl. best 3: %+.4f'%(
            float((r['pm']>0).mean()),float(pm[1:].mean()),float(pm[3:].mean())))
# how much of a hypothetical positive mean is one coin: sensitivity on best train cell
P('\n=== gross vs net decomposition, unconditional ===')
for s in ['H5/tpNone/slNone/f1.0','H15/tpNone/slNone/f1.0','H30/tpNone/slNone/f1.0','H60/tpNone/slNone/f1.0']:
    for nm,idx in [('TRAIN',TRi),('VALID',VAi)]:
        a=ev(idx,s,key=(-0.30,0.0114)); b2=ev(idx,s,key=(-0.30,0.025))
        c=ev(idx,s,key=(-0.50,0.0114)); d=ev(idx,s,key=(-1.00,0.0114))
        P('%-24s %s  toll1.14/drop30 %+.4f | toll2.50/drop30 %+.4f | drop50 %+.4f | drop100 %+.4f | res %.3f'%(
            s,nm,a['mean'],b2['mean'],c['mean'],d['mean'],a['res']))
P('OUT_DONE')
OUT.close()
