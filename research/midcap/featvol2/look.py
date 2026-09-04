import sys,csv,json,gc
import numpy as np
sys.path.insert(0,'/home/anont/meme/research/midcap/featvol2')
from core import *
from feats import build_features
D='/home/anont/meme/research/midcap/featvol2/'
mints,data,nres=load()
book=Book(mints,data); F=build_features(book)
BH=book.hh[book.MID]; TRAIN=book.valid_sig&(BH==1); VAL=book.valid_sig&(BH==2)
R=Runner(book)
print("VALIDATE BASELINES (all-bar non-overlap tiling, mint-equal)")
for Hm in (5,15,30,60,120):
    k=build_exit(book,Hm); g=gross_returns(book,k,None,None)
    for drop in (-0.30,-1.00):
        net=netify(g,k,0.0114,drop)
        for lab,msk in (('TR',TRAIN),('VA',VAL)):
            js=R.select(msk,k); st=R.stats(js,net,k)
            pos=float((st['pm']>0).mean())
            tm=float(np.mean(np.sort(st['pm'])[int(.05*st['clusters']):st['clusters']-int(.05*st['clusters'])]))
            print("  H%-4d %s drop%.2f n=%5d k=%3d mean=%+.4f med=%+.4f trim5=%+.4f frac_pos_mint=%.3f res=%.3f"%(
                Hm,lab,drop,st['n'],st['clusters'],st['mean'],st['median'],tm,pos,st['res']))
    del k,g; gc.collect()
print()
rows=list(csv.DictReader(open(D+'train_rows.csv')))
print("train rows:",len(rows))
for r in rows: r['mean']=float(r['mean']); r['median']=float(r['median']); r['n']=int(r['n']); r['k']=int(r['k'])
rows.sort(key=lambda r:-r['mean'])
print("TOP 25 TRAIN BY MEAN")
for r in rows[:25]:
    print("  %-28s %-28s %-12s n=%4d k=%3d mean=%+.4f med=%+.4f"%(r['c1'],r['c2'],r['exit'],r['n'],r['k'],r['mean'],r['median']))
rows.sort(key=lambda r:-r['median'])
print("TOP 25 TRAIN BY MEDIAN")
for r in rows[:25]:
    print("  %-28s %-28s %-12s n=%4d k=%3d mean=%+.4f med=%+.4f"%(r['c1'],r['c2'],r['exit'],r['n'],r['k'],r['mean'],r['median']))
# feature-level marginal: mean over all rows containing a condition
from collections import defaultdict
agg=defaultdict(list)
for r in rows:
    agg[r['c1']].append(r['median']);
    if r['c2']: agg[r['c2']].append(r['median'])
mm=sorted(((np.mean(v),len(v),kk) for kk,v in agg.items() if len(v)>=30),reverse=True)
print("\nCONDITION MARGINALS (mean of train MEDIAN across all rows containing it), top 20 / bottom 20")
for x in mm[:20]: print("  %+.4f n=%4d %s"%x)
print("  ...")
for x in mm[-20:]: print("  %+.4f n=%4d %s"%x)
