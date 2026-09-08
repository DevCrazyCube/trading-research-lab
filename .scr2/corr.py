"""Continuous read: does ANY deployer feature rank-correlate with per-mint
outcome?  More powerful than binary filters at these sample sizes."""
import sys, statistics, collections, math, random, pickle
sys.path.insert(0,'/home/anont/meme/.scr2')
import engine as E, sweep as SW
SCR='/home/anont/meme/.scr2'
random.seed(7)
o=[]
def p(*a): o.append(" ".join(str(x) for x in a))

FEATS=['nprior','prior_grad','prior_gradrate','prior_grad_lag','burst300','burst600',
       'burst1800','burst3600','burst7200','gap','age_creator','rate_per_h']

def spearman(x,y):
    n=len(x)
    if n<8: return None
    def rank(v):
        idx=sorted(range(n),key=lambda i:v[i]); r=[0.0]*n; i=0
        while i<n:
            j=i
            while j+1<n and v[idx[j+1]]==v[idx[i]]: j+=1
            avg=(i+j)/2.0+1
            for k in range(i,j+1): r[idx[k]]=avg
            i=j+1
        return r
    rx=rank(x); ry=rank(y)
    mx=sum(rx)/n; my=sum(ry)/n
    sxy=sum((rx[i]-mx)*(ry[i]-my) for i in range(n))
    sxx=math.sqrt(sum((rx[i]-mx)**2 for i in range(n)))
    syy=math.sqrt(sum((ry[i]-my)**2 for i in range(n)))
    if sxx==0 or syy==0: return None
    return sxy/(sxx*syy)

STRUCTS=[('first','p_single',15,'m_plain'),('first','p_single',60,'m_plain'),
         ('first','p_single',480,'m_plain'),('first','p_single',1440,'m_plain'),
         ('allbars','p_single',15,'m_plain'),('allbars','p_single',60,'m_plain'),
         ('allbars','p_single',180,'m_plain'),('age60','p_single',60,'m_plain'),
         ('allbars','p_single',60,'m_tp100'),('allbars','p_single',60,'m_sl35'),
         ('allbars','p_single',60,'m_tr40'),('allbars','p_50_50_15',60,'m_plain')]
TIM=dict(E.TIMINGS); POS=dict(E.POSITIONS); MOD=dict(E.MODS)
acc=collections.defaultdict(lambda: [[],[]])
for tn,pn,h,mn in STRUCTS:
    per={}
    for m in E.MINTS:
        r=E.sim_mint(m,TIM[tn],POS[pn],h,MOD[mn])
        if r is not None: per[m]=r
    vals={m:SW.mint_stat(per[m],E.TOLL_A,-0.30,SW.CAP) for m in per}
    line=["%-10s/%-11s/h%-5d/%-9s"%(tn,pn,h,mn)]
    for f in FEATS:
        for sp,name in ((SW.TRAIN,'tr'),(SW.VALID,'va')):
            ms=[m for m in sp if m in vals and m in E.FEAT]
            rho=spearman([E.FEAT[m][f] for m in ms],[vals[m] for m in ms])
            acc[(f,name)][0].append(rho if rho is not None else 0.0)
    p("done "+line[0])
p("")
p("=== SPEARMAN rho(feature, per-mint net return) over %d representative structures ==="%len(STRUCTS))
p("%-16s %10s %10s %10s %10s"%("feature","TRAIN mean","TRAIN +%","VALID mean","VALID +%"))
for f in FEATS:
    t=acc[(f,'tr')][0]; v=acc[(f,'va')][0]
    p("%-16s %+10.4f %10.2f %+10.4f %10.2f"%(f,statistics.mean(t),sum(1 for x in t if x>0)/len(t),
                                             statistics.mean(v),sum(1 for x in v if x>0)/len(v)))
# rough significance: |rho| needed at n=175 / n=207 for p=0.05 two-sided ~ 1.96/sqrt(n-1)
p("")
p("noise floor |rho| at p=.05: train(n=%d)=%.3f  valid(n=%d)=%.3f"%(
    len(SW.TRAIN),1.96/math.sqrt(len(SW.TRAIN)-1),len(SW.VALID),1.96/math.sqrt(len(SW.VALID)-1)))
open(SCR+'/corr.out','w').write("\n".join(o))
