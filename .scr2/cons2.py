"""Does anything in the deployer-cadence family make money WITHOUT relying on a
take-profit filling inside the entry bar?  Conservative rule: TP/SL/trail can
only trigger from the bar AFTER the entry bar."""
import sys, bisect, statistics, collections, random, math
sys.path.insert(0,'/home/anont/meme/.scr2')
import engine as E, sweep as SW
SCR='/home/anont/meme/.scr2'
random.seed(5)
o=[]
def p(*a): o.append(" ".join(str(x) for x in a))

def sim_cons(m, tkind, targ, hold, tp):
    ts,op,hi,lo,cl,n=E.PK[m]
    t0=ts[0]
    if tkind=='first': sig=[0]
    elif tkind=='age':
        i=bisect.bisect_left(ts,t0+targ)
        if i>=n: return None
        sig=[i]
    else:
        sig=range(bisect.bisect_left(ts,t0+targ) if targ else 0, n)
    rets=[]; nd=0; busy=-1
    for i in sig:
        j=i+1
        if j>=n: break
        te=ts[j]
        if te<busy: continue
        epx=op[j]; tpx=epx*(1+tp) if tp else None
        eidx=bisect.bisect_left(ts,te+hold*60,j)
        last=eidx if eidx<n else n-1
        ex=None; exb=None
        for b in range(j+1,last+1):          # <-- entry bar excluded
            if tpx is not None and hi[b]>=tpx:
                ex=max(tpx,op[b]); exb=b; break
        if ex is None:
            if eidx<n: ex=op[eidx]; exb=eidx
            else:
                nd+=1; busy=float('inf'); break
        rets.append(ex/epx-1.0); busy=ts[exb]
    if not rets and nd==0: return None
    return (rets,nd)

FILTS=['rate>=5/h','burst600s>=2','burst1800s>=3','burst300s>=2','nprior in[4,12]']
TIMS=[('first',('first',0)),('age15',('age',900)),('age60',('age',3600)),
      ('age240',('age',14400)),('allbars',('all',0))]
p("CONSERVATIVE FILLS (take-profit cannot trigger inside the entry bar)")
p("mint-equal mean net, toll 1.14%%, dropout -30%%, winsor +300%%.  base = same structure, all mints.")
p("")
p("%-16s %-8s %-5s %-8s | %-24s | %-24s"%("filter","timing","hold","tp","TRAIN mean/base (k)","VALID mean/base (k)"))
best=[]
for f in FILTS:
    S=SW.FSET[f]
    for tn,tspec in TIMS:
        for hold in (30,180,480):
            for tp in (None,0.5,1.0,2.0):
                per={}
                for m in E.MINTS:
                    r=sim_cons(m,tspec[0],tspec[1],hold,tp)
                    if r is not None: per[m]=r
                row=[]
                for sp in (SW.TRAIN,SW.VALID):
                    pool=[m for m in sp if m in per]; sel=[m for m in pool if m in S]
                    if len(sel)<20: row.append(None); continue
                    vals={m:SW.mint_stat(per[m],E.TOLL_A,-0.30,SW.CAP) for m in pool}
                    row.append((statistics.mean(vals[m] for m in sel),
                                statistics.mean(vals.values()),len(sel),
                                statistics.median([vals[m] for m in sel])))
                if None in row: continue
                (tm,tb,tk,tmed),(vm,vb,vk,vmed)=row
                if tm>0 and vm>0 and tm>tb and vm>vb:
                    best.append((f,tn,hold,tp,tm,tb,tk,vm,vb,vk,vmed))
                    p("%-16s %-8s %-5d %-8s | %+.4f/%+.4f (%d) | %+.4f/%+.4f (%d) med=%+.4f  <== both-positive"%(
                        f,tn,hold,str(tp),tm,tb,tk,vm,vb,vk,vmed))
p("")
p("cells positive in ABSOLUTE terms on BOTH splits under conservative fills: %d"%len(best))
open(SCR+'/cons2.out','w').write("\n".join(o))
