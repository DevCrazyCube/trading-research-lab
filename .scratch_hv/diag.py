import sys, statistics
sys.path.insert(0,'/home/anont/meme/.scratch_hv')
from engine import load, simulate, net_ret
O=open('/home/anont/meme/.scratch_hv/diag.txt','w')
def p(*a): O.write(' '.join(str(x) for x in a)+'\n'); O.flush()
data=load({1,2})
rows=[]
per={}
for m,b in data:
    tr=[]; busy=-1
    for i in range(0,len(b)-1):
        j=i+1
        if j<=busy: continue
        r=simulate(b,j,hold_min=15,stop_mult=0.0,tp_mult=1e18)
        if r is None: continue
        k,acc,drop,res=r
        busy=k
        ret=net_ret(acc,drop,0.0114,-0.30)
        tr.append(ret); rows.append((ret,m,j,k,b[j][1],b[k][1]))
    if tr: per[m]=tr
rows.sort(reverse=True)
p('TOP 15 returns:')
for r in rows[:15]: p('  %.1f%% mint=%s j=%d k=%d entry=%.3e exit=%.3e'%(r[0]*100,r[1][:12],r[2],r[3],r[4],r[5]))
p('frac trades >100%%:', sum(1 for r in rows if r[0]>1)/len(rows))
p('frac trades >1000%%:', sum(1 for r in rows if r[0]>10)/len(rows))
mm=[(statistics.mean(v),m) for m,v in per.items()]
mm.sort(reverse=True)
p('TOP 10 mint means:')
for v,m in mm[:10]: p('  %.2f%% %s ntr=%d'%(v*100,m[:12],len(per[m])))
p('mean of mint means', statistics.mean(x[0] for x in mm))
tr=[statistics.mean(v) for m,v in per.items()]
p('trimmed(drop top5 mints) mean', statistics.mean(sorted(tr)[:-5]))
p('median mint mean', statistics.median(tr))
allr=[x[0] for x in rows]
p('pooled trade mean', statistics.mean(allr), 'median', statistics.median(allr))
O.close()
