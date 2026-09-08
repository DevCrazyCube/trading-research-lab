"""Decisive test: is the burst-deployer 'edge' drift, or just higher variance
being monetised by an upside truncation?

Control 1: equal-size random subset of validate mints (already run).
Control 2: equal-size random subset MATCHED ON REALISED VOLATILITY decile.
           If the filtered mean sits inside this null, the deployer feature is
           only a volatility proxy and the take-profit is doing all the work.
Also: leave-out-top-k, to show how many coins the mean rests on.
"""
import sys, math, statistics, random, collections, pickle, json
sys.path.insert(0,'/home/anont/meme/.scr2')
import engine as E, sweep as SW
SCR='/home/anont/meme/.scr2'
random.seed(11)
o=[]
def p(*a): o.append(" ".join(str(x) for x in a))
TIM=dict(E.TIMINGS); POS=dict(E.POSITIONS); MOD=dict(E.MODS)

# realised per-bar volatility of each mint (whole life)
VOL={}
for m in E.MINTS:
    b=E.BARS[m]
    r=[]
    for i in range(1,len(b)):
        if b[i-1][4]>0 and b[i][4]>0:
            r.append(math.log(b[i][4]/b[i-1][4]))
    VOL[m]=statistics.pstdev(r) if len(r)>2 else 0.0

def decile_map(pool):
    v=sorted(pool,key=lambda m:VOL[m])
    d={}
    for i,m in enumerate(v): d[m]=min(9,int(10*i/len(v)))
    return d

CASES=[('burst300s>=2','first','p_single',60,'m_tp200'),
       ('burst300s>=2','first','p_single',60,'m_tp50'),
       ('burst600s>=2','first','p_single',60,'m_tp200'),
       ('burst600s>=2','first','p_single',60,'m_tp50'),
       ('burst600s>=2','first','p_single',180,'m_tp50'),
       ('burst1800s>=3','first','p_single',180,'m_tp200'),
       ('rate>=5/h','first','p_single',480,'m_tp200'),
       ('n>=3&gradrate>=0.05','first','p_single',15,'m_tp200')]

p("realised log-return vol by group (whole-life, per bar):")
for f in sorted(set(c[0] for c in CASES)):
    S=SW.FSET[f]
    for sp,nm in ((SW.TRAIN,'train'),(SW.VALID,'valid')):
        ins=[VOL[m] for m in sp if m in S]; out=[VOL[m] for m in sp if m not in S]
        p("  %-22s %-6s in: n=%3d med=%.4f    out: n=%3d med=%.4f"%(
            f,nm,len(ins),statistics.median(ins),len(out),statistics.median(out)))
p("")

for f,tn,pn,h,mn in CASES:
    per={}
    for m in E.MINTS:
        r=E.sim_mint(m,TIM[tn],POS[pn],h,MOD[mn])
        if r is not None: per[m]=r
    S=SW.FSET[f]
    for sp,nm in ((SW.TRAIN,'train'),(SW.VALID,'valid')):
        pool=[m for m in sp if m in per]
        sel=[m for m in pool if m in S]
        if len(sel)<10: continue
        vals={m:SW.mint_stat(per[m],E.TOLL_A,-0.30,SW.CAP) for m in pool}
        obs=statistics.mean(vals[m] for m in sel)
        base=statistics.mean(vals[m] for m in pool)
        # plain random-subset null
        rn=[]
        for _ in range(4000):
            s=random.sample(pool,len(sel)); rn.append(sum(vals[m] for m in s)/len(s))
        p1=sum(1 for x in rn if x>=obs)/len(rn)
        # vol-decile-matched null
        dm=decile_map(pool)
        want=collections.Counter(dm[m] for m in sel)
        bucket=collections.defaultdict(list)
        for m in pool: bucket[dm[m]].append(m)
        vn=[]
        for _ in range(4000):
            s=[]
            ok=True
            for d,c in want.items():
                if len(bucket[d])<c: ok=False; break
                s+=random.sample(bucket[d],c)
            if not ok: break
            vn.append(sum(vals[m] for m in s)/len(s))
        p2=(sum(1 for x in vn if x>=obs)/len(vn)) if vn else None
        # leave-out-top-k
        sv=sorted((vals[m] for m in sel),reverse=True)
        lo=[]
        for k in (1,2,3,5):
            if len(sv)>k: lo.append("drop%d=%+.3f"%(k,statistics.mean(sv[k:])))
        p("%-22s %-8s/%-9s/h%-5d/%-8s %-6s k=%3d obs=%+.4f base=%+.4f | p_rand=%.4f p_volmatched=%s | %s"%(
            f,tn,pn,h,mn,nm,len(sel),obs,base,p1,("%.4f"%p2 if p2 is not None else "n/a")," ".join(lo)))
    p("")
open(SCR+'/volmatch.out','w').write("\n".join(o))
