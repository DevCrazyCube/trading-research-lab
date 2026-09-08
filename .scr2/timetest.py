import time, sys
sys.path.insert(0, '/home/anont/meme/.scr2')
import engine as E
o=[]
t=time.time()
cnt=0
for tname,timing in E.TIMINGS:
    for hold in (15,480):
        for mname,mod in (E.MODS[0],E.MODS[3]):
            per={}
            for m in E.MINTS:
                r=E.sim_mint(m,timing,E.POSITIONS[0][1],hold,mod)
                if r: per[m]=r
            cnt+=1
            if cnt==1:
                tot=sum(len(v[0])+v[1] for v in per.values())
                nd=sum(v[1] for v in per.values())
                o.append("first sim: mints=%d trades=%d drops=%d"%(len(per),tot,nd))
el=time.time()-t
o.append("sims=%d elapsed=%.2f -> per sim %.3fs -> full 3120 sims %.1f min"%(cnt,el,el/cnt,el/cnt*3120/60))
# sanity: unconditional allbars 15m plain
per={}
for m in E.MINTS:
    r=E.sim_mint(m,('all',0),E.POSITIONS[0][1],15,{})
    if r: per[m]=r
import statistics
v30=[E.agg(per[m],E.TOLL_A,-0.30) for m in per]
v50=[E.agg(per[m],E.TOLL_A,-0.50) for m in per]
v100=[E.agg(per[m],E.TOLL_A,-1.00) for m in per]
tr=sum(len(per[m][0])+per[m][1] for m in per); rs=sum(len(per[m][0]) for m in per)
o.append("UNCOND allbars/single/15m/plain: k=%d n=%d res=%.3f mean30=%.4f mean50=%.4f mean100=%.4f median30=%.4f"%(
    len(per),tr,rs/tr,statistics.mean(v30),statistics.mean(v50),statistics.mean(v100),statistics.median(v30)))
open('/home/anont/meme/.scr2/timetest.out','w').write("\n".join(o))
