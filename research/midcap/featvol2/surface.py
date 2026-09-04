"""Response-surface map: for every microstructure feature, decile-by-decile net
outcome on TRAIN and VALIDATE, at three horizons. Mint-equal, no-overlap, capped."""
import sys,gc,json
import numpy as np
sys.path.insert(0,'/home/anont/meme/research/midcap/featvol2')
from core import *
from feats import build_features
D='/home/anont/meme/research/midcap/featvol2/'
CAP=3.0
mints,data,nres=load(); book=Book(mints,data); F=build_features(book); N=book.N
BH=book.hh[book.MID]; TRAIN=book.valid_sig&(BH==1); VAL=book.valid_sig&(BH==2)
R=Runner(book)
FEATS=['vrel5','vrel20','vacc','rng','rngrel','dens10','dens30','gap','chop',
       'vwapdev','clspos','body','dvol','vshare','ret1','ret5','vzs','rngz','illiq','tickdir']
out={}
for Hm in (5,15,60):
    k=build_exit(book,Hm); g=gross_returns(book,k,None,None)
    net=netify(g,k,0.0114,-0.30,CAP)
    for lab,msk in (('TR',TRAIN),('VA',VAL)):
        js=R.select(msk,k); st=R.stats(js,net,k)
        print("BASE H%-3d %s n=%5d k=%3d mean=%+.4f med=%+.4f"%(Hm,lab,st['n'],st['clusters'],st['mean'],st['median']),flush=True)
    for f in FEATS:
        x=F[f]
        qs=np.quantile(x[TRAIN&np.isfinite(x)],[0,.1,.2,.3,.4,.5,.6,.7,.8,.9,1.])
        line=[]
        for d in range(10):
            lo,hi=qs[d],qs[d+1]
            m=np.isfinite(x)&(x>=lo)&(x<=hi if d==9 else x<hi)
            cell=[]
            for lab,msk in (('TR',TRAIN),('VA',VAL)):
                js=R.select(m&msk,k)
                if js.size<25: cell.append((0,0.0,0.0)); continue
                st=R.stats(js,net)
                cell.append((st['n'],st['mean'],st['median']))
            line.append(cell)
        out['H%d_%s'%(Hm,f)]=line
        print("H%-3d %-8s TRmed "%(Hm,f)+" ".join("%+.3f"%c[0][2] for c in line)+
              "   VAmed "+" ".join("%+.3f"%c[1][2] for c in line),flush=True)
    del k,g,net; gc.collect()
json.dump(out,open(D+'surface.json','w'))
print("SURFACE DONE",flush=True)
