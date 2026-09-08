import sys, statistics, math
sys.path.insert(0,'/home/anont/meme/.scratch_hv')
from engine import load
O=open('/home/anont/meme/.scratch_hv/units.txt','w')
def p(*a): O.write(' '.join(str(x) for x in a)+'\n')
data=load({1,2})
p('mints h12',len(data))
px=[];vl=[]
for m,b in data:
    px.append(statistics.median(x[4] for x in b))
    vl.append(statistics.median(x[5] for x in b) or 1e-9)
lp=[math.log(x) for x in px]; lv=[math.log(x) for x in vl]
mp=statistics.mean(lp); mv=statistics.mean(lv)
num=sum((a-mp)*(b-mv) for a,b in zip(lp,lv))
den=math.sqrt(sum((a-mp)**2 for a in lp)*sum((b-mv)**2 for b in lv))
p('corr(log median price, log median volume) =', num/den)
p('median price range', min(px), max(px))
p('median vol range', min(vl), max(vl))
# per mint sum of volume vs sum of price*volume
sv=[sum(x[5] for x in b) for m,b in data]
sn=[sum(x[4]*x[5] for x in b) for m,b in data]
p('median sum(vol) per mint', statistics.median(sv))
p('median sum(px*vol) per mint', statistics.median(sn))
O.close()
