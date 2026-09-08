import sys, statistics, math, random, collections, pickle
sys.path.insert(0,'/home/anont/meme/.scr2')
import engine as E, sweep as SW
SCR='/home/anont/meme/.scr2'
o=[]
def p(*a): o.append(" ".join(str(x) for x in a))
TIM=dict(E.TIMINGS); POS=dict(E.POSITIONS); MOD=dict(E.MODS)
for tn,pn,h,mn in [('first','p_single',60,'m_plain'),('allbars','p_single',60,'m_plain'),
                   ('allbars','p_single',15,'m_plain'),('allbars','p_single',1440,'m_plain')]:
    per={}
    for m in E.MINTS:
        r=E.sim_mint(m,TIM[tn],POS[pn],h,MOD[mn])
        if r is not None: per[m]=r
    for sp,nm in ((SW.TRAIN,'train'),(SW.VALID,'valid')):
        v=[SW.mint_stat(per[m],E.TOLL_A,-0.30,SW.CAP) for m in sp if m in per]
        sd=statistics.pstdev(v)
        p("%-8s/h%-5d %-6s k=%3d mean=%+.4f med=%+.4f sd=%.3f  SE(k)=%.4f  SE(k=50)=%.4f SE(k=25)=%.4f"%(
            tn,h,nm,len(v),statistics.mean(v),statistics.median(v),sd,sd/math.sqrt(len(v)),sd/math.sqrt(50),sd/math.sqrt(25)))
# dev-buy region coverage
dev=pickle.load(open(SCR+'/devinfo.pkl','rb'))
bycre=collections.defaultdict(list)
for bc,v in dev.items(): bycre[v['creator']].append(v)
cnt=0; cnt_tr=0; cnt_va=0
for m in E.MINTS:
    mi=E.META.get(m)
    if not mi: continue
    pri=[v for v in bycre.get(mi['creator'],[]) if v['bt']<mi['bt']]
    if pri:
        cnt+=1
        if m in SW.TRAIN: cnt_tr+=1
        else: cnt_va+=1
p("")
p("dev-buy region: mints with >=1 b11a-covered PRIOR coin by the same creator: total=%d train=%d valid=%d"%(cnt,cnt_tr,cnt_va))
p("b11a block coverage: 3932 of 33866 window creates (11.6%%) -> dev-buy history is UNMEASURABLE at usable k")
open(SCR+'/power.out','w').write("\n".join(o))
