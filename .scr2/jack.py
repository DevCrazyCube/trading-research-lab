import sys, statistics, collections, random, math
sys.path.insert(0,'/home/anont/meme/.scr2')
import engine as E, sweep as SW
SCR='/home/anont/meme/.scr2'
o=[]
def p(*a): o.append(" ".join(str(x) for x in a))
TIM=dict(E.TIMINGS); POS=dict(E.POSITIONS); MOD=dict(E.MODS)
S=SW.FSET['rate>=5/h']
for h in (30,180,480):
    per={}
    for m in E.MINTS:
        r=E.sim_mint(m,TIM['first'],POS['p_single'],h,MOD['m_tp200'])
        if r is not None: per[m]=r
    p("=== rate>=5/h | first/p_single/h%d/m_tp200 ==="%h)
    for sp,nm in ((SW.TRAIN,'TRAIN'),(SW.VALID,'VALID')):
        sel=[m for m in sp if m in S and m in per]
        vals={m:SW.mint_stat(per[m],E.TOLL_A,-0.30,SW.CAP) for m in sel}
        bycre=collections.defaultdict(list)
        for m in sel: bycre[SW.CREATOR[m]].append(m)
        full=statistics.mean(vals.values())
        jk=[]
        for c in bycre:
            rest=[vals[m] for m in sel if SW.CREATOR[m]!=c]
            jk.append((statistics.mean(rest),c,len(bycre[c])))
        jk.sort()
        pos=sum(1 for v in vals.values() if v>0)
        p("  %s k=%d creators=%d  mean=%+.4f  median=%+.4f  frac_mint_positive=%.2f"%(
            nm,len(sel),len(bycre),full,statistics.median(vals.values()),pos/len(sel)))
        p("     leave-one-creator-out: worst=%+.4f (drop %s, %d coins)  best=%+.4f  all-LOO-positive=%s"%(
            jk[0][0],jk[0][1][:8],jk[0][2],jk[-1][0],all(x[0]>0 for x in jk)))
        p("     per-mint net returns sorted: %s"%(
            " ".join("%+.2f"%v for v in sorted(vals.values(),reverse=True))))
    p("")
open(SCR+'/jack.out','w').write("\n".join(o))
