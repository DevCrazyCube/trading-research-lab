import numpy as np, sys
sys.path.insert(0,'/home/anont/meme/_fv0')
from engine import *
ALL=np.arange(NE)
hi=HOR.index(15)
r=evaluate(ALL.tolist(),hi,-1,-1,want_extra=True)
mm=r['mint_means']
mm=np.sort(mm)
print('n mints',len(mm))
print('top10 mint means',[round(x*100,1) for x in mm[-10:]])
print('bot10',[round(x*100,1) for x in mm[:10]])
for q in [1,5,10,25,50,75,90,95,99]:
    print('p%d'%q, round(float(np.percentile(mm,q))*100,2))
print('mean',round(mm.mean()*100,2),'trimmed10%',round(float(mm[int(.05*len(mm)):int(.95*len(mm))].mean())*100,2))
lo,hihi=boot_ci(mm)
print('boot CI mean', round(lo*100,2), round(hihi*100,2))
# what fraction of mints have positive mean
print('frac mints >0', round(float((mm>0).mean())*100,1))
