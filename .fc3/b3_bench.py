import sys; sys.path.insert(0,'/home/anont/meme/.fc3')
import numpy as np
from lib import *
out=[]
ones=np.ones(len(F),dtype=bool)
out.append('=== UNCONDITIONAL BENCHMARK (all bars, non-overlap, mint-equal) ===')
for split in ('train','validate','both'):
    for hidx,H in enumerate(HS):
        k=hidx*12
        r=evaluate(ones,k,'all',-0.30,0.0114,split)
        r50=evaluate(ones,k,'all',-0.50,0.0114,split)
        r100=evaluate(ones,k,'all',-1.00,0.0114,split)
        r25=evaluate(ones,k,'all',-0.30,0.025,split)
        out.append('%-8s H=%3d n=%5d k=%3d res=%.3f  mean30=%+.4f mean50=%+.4f mean100=%+.4f mean@2.5%%toll=%+.4f medtrade=%+.4f'%(
            split,H,r['n'],r['k'],r['res'],r['mean'],r50['mean'],r100['mean'],r25['mean'],r['median_trade']))
out.append('')
out.append('=== TP/SL TRUNCATION CONTROL on ALL bars (artifact reference) ===')
for hidx,H in enumerate([15,60]):
    hh_=HS.index(H)
    for tpi,tp in enumerate(TPS):
        for sli,sl in enumerate(SLS):
            k=hh_*12+tpi*3+sli
            r=evaluate(ones,k,'all',-0.30,0.0114,'train')
            out.append('H=%3d TP=%-5s SL=%-5s n=%5d k=%3d mean=%+.4f medtrade=%+.4f'%(H,tp,sl,r['n'],r['k'],r['mean'],r['median_trade']))
out.append('')
out.append('=== feature distributions (train rows) ===')
tr=np.isin(mi,np.nonzero(MTRAIN)[0])
for nm,c in [('age_min',AGE),('bar_idx',BIDX),('dd',DD),('lvl',LVL),('relvol',RELV),('gap_prev',GAP),('entry_gap',EGAP),('pri',PRI),('prig',PRIG)]:
    v=np.sort(F[tr,c]); n=len(v)
    out.append('%-9s q: %s'%(nm,['%.4g'%v[int(q*(n-1))] for q in (0,.1,.25,.5,.75,.9,.99,1)]))
open(SP+'/b3.log','w').write('\n'.join(out))
