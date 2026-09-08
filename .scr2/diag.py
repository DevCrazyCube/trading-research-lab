import sys, statistics, pickle
sys.path.insert(0,'/home/anont/meme/.scr2')
import engine as E
o=[]
per={}
for m in E.MINTS:
    r=E.sim_mint(m,('all',0),E.POSITIONS[0][1],15,{})
    if r: per[m]=r
vals=sorted(((E.agg(per[m],E.TOLL_A,-0.30),m) for m in per), reverse=True)
o.append("top 15 per-mint means:")
for v,m in vals[:15]:
    rets,nd=per[m]
    o.append("  %.3f %s ntr=%d nd=%d maxret=%.2f minret=%.2f nbars=%d"%(v,m,len(rets),nd,max(rets) if rets else 0,min(rets) if rets else 0,len(E.BARS[m])))
o.append("bottom 5:")
for v,m in vals[-5:]:
    o.append("  %.3f %s"%(v,m))
o.append("quantiles: "+str([round(statistics.quantiles([v for v,_ in vals],n=20)[i],4) for i in range(19)]))
# look at the worst offender bars
worst=vals[0][1]
b=E.BARS[worst]
o.append("mint %s first 5 bars %s"%(worst,b[:5]))
allr=[]
for m in per: allr+=per[m][0]
allr.sort()
o.append("trade-level gross: n=%d mean=%.4f median=%.4f p99=%.3f max=%.1f min=%.3f"%(len(allr),statistics.mean(allr),statistics.median(allr),allr[int(.99*len(allr))],allr[-1],allr[0]))
o.append("count gross>5: %d  >20: %d >100: %d"%(sum(1 for x in allr if x>5),sum(1 for x in allr if x>20),sum(1 for x in allr if x>100)))
# examine a huge trade
big=[(x) for x in allr if x>50]
o.append("huge trades: %s"%(big[:20],))
open('/home/anont/meme/.scr2/diag.out','w').write("\n".join(o))
