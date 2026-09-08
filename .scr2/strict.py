"""Strict test of the one surviving family, across its whole plateau.
Bar (all must hold): train mean>0 & >base, validate mean>0 & >base,
train random-subset p<.05, validate random-subset p<.05, vol-matched
validate p<.05, validate survives dropping its top 3 mints, robust to
toll 2.5% and dropout charged at -100%."""
import sys, math, statistics, random, collections, pickle
sys.path.insert(0,'/home/anont/meme/.scr2')
import engine as E, sweep as SW
SCR='/home/anont/meme/.scr2'
random.seed(101)
o=[]
def p(*a): o.append(" ".join(str(x) for x in a))
TIM=dict(E.TIMINGS); POS=dict(E.POSITIONS); MOD=dict(E.MODS)
VOL={}
for m in E.MINTS:
    b=E.BARS[m]; r=[]
    for i in range(1,len(b)):
        if b[i-1][4]>0 and b[i][4]>0: r.append(math.log(b[i][4]/b[i-1][4]))
    VOL[m]=statistics.pstdev(r) if len(r)>2 else 0.0

def nulls(vals,pool,sel,reps=4000):
    obs=statistics.mean(vals[m] for m in sel)
    rn=[statistics.mean(vals[m] for m in random.sample(pool,len(sel))) for _ in range(reps)]
    p1=sum(1 for x in rn if x>=obs)/reps
    v=sorted(pool,key=lambda m:VOL[m]); dm={m:min(9,int(10*i/len(v))) for i,m in enumerate(v)}
    want=collections.Counter(dm[m] for m in sel); buck=collections.defaultdict(list)
    for m in pool: buck[dm[m]].append(m)
    vn=[]
    for _ in range(reps):
        s=[]
        for d,c in want.items(): s+=random.sample(buck[d],c)
        vn.append(statistics.mean(vals[m] for m in s))
    return obs,p1,sum(1 for x in vn if x>=obs)/reps

FILT='rate>=5/h'
p("FILTER: %s   (creator prior-launch cadence >= 5 coins/hour, measured from the"%FILT)
p("        creator's first in-window launch to this launch; requires >=1 prior launch)")
p("timing=first (signal bar 0 -> enter at OPEN of bar 1), pos=p_single")
p("")
p("%-9s %-5s | %-38s | %-38s | %s"%("mod","hold","TRAIN obs/base p_rand p_vol drop3","VALID obs/base p_rand p_vol drop3","VALID m100 m25 med k kc res  PASS"))
S=SW.FSET[FILT]
npass=0; ntot=0
for mn in ('m_plain','m_tp50','m_tp100','m_tp200','m_tp400'):
    for h in (5,15,30,60,180,480,1440):
        per={}
        for m in E.MINTS:
            r=E.sim_mint(m,TIM['first'],POS['p_single'],h,MOD[mn])
            if r is not None: per[m]=r
        line="%-9s %-5d |"%(mn,h)
        res={}
        for sp,nm in ((SW.TRAIN,'tr'),(SW.VALID,'va')):
            pool=[m for m in sp if m in per]; sel=[m for m in pool if m in S]
            vals={m:SW.mint_stat(per[m],E.TOLL_A,-0.30,SW.CAP) for m in pool}
            obs,p1,p2=nulls(vals,pool,sel)
            base=statistics.mean(vals[m] for m in pool)
            sv=sorted((vals[m] for m in sel),reverse=True)
            d3=statistics.mean(sv[3:])
            res[nm]=(obs,base,p1,p2,d3,len(sel))
            line+=" %+.3f/%+.3f p=%.3f/%.3f d3=%+.3f |"%(obs,base,p1,p2,d3)
        c=SW.cell(per,[m for m in SW.VALID if m in S])
        ok=(res['tr'][0]>0 and res['tr'][0]>res['tr'][1] and res['va'][0]>0 and res['va'][0]>res['va'][1]
            and res['tr'][2]<0.05 and res['va'][2]<0.05 and res['va'][3]<0.05
            and res['va'][4]>0 and c['mean100']>0 and c['mean25']>0)
        ntot+=1; npass+=1 if ok else 0
        line+=" %+.3f %+.3f %+.3f k=%d kc=%d r=%.2f  %s"%(c['mean100'],c['mean25'],c['med'],c['k'],c['kc'],c['res'],"PASS" if ok else "fail")
        p(line)
p("")
p("cells passing the strict bar: %d of %d"%(npass,ntot))
open(SCR+'/strict.out','w').write("\n".join(o))
