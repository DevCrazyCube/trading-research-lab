import numpy as np, json, time, sys, itertools, math
sys.path.insert(0,'/home/anont/meme/_c3')
from engine import load, net_array, evaluate, welch

OUT='/home/anont/meme/_c3'
LG=open(OUT+'/sweep.log','w')
def p(*a): LG.write(' '.join(str(x) for x in a)+'\n'); LG.flush()
T0=time.time()
P=load()
N=len(P['TS']); FN=P['FEATNAMES']; MN=P['MNAMES']
CN=[c[0] for c in P['COMBOS']]
p("bars",N,"mints",P['nm'],"combos",len(CN),CN)
TR = P['bar_h']==1; VA = P['bar_h']==2
p("train bars",int(TR.sum()),"validate bars",int(VA.sum()))
p("train mints",int((P['h']==1).sum()),"validate mints",int((P['h']==2).sum()))

NET=[net_array(ci) for ci in range(len(CN))]

# ---------- baselines: ALL bars (= random-entry control) per combo ----------
BASE={}
for ci,nm in enumerate(CN):
    for hh,tag in ((1,'tr'),(2,'va')):
        r=evaluate(np.ones(N,bool),ci,NET[ci],hsel=hh)
        BASE[(ci,tag)]=r
        if tag=='tr': p("BASE tr %-14s mean %+7.4f med %+7.4f n %6d k %3d res %.3f"%(nm,r['mean'],r['median'],r['n'],r['k'],r['res']))
for ci,nm in enumerate(CN):
    r=BASE[(ci,'va')]
    p("BASE va %-14s mean %+7.4f med %+7.4f n %6d k %3d res %.3f"%(nm,r['mean'],r['median'],r['n'],r['k'],r['res']))

# cap sensitivity on the plain 15m baseline
for cp in (None,10.0,3.0,1.0):
    for hh in (1,2):
        r=evaluate(np.ones(N,bool),CN.index('t15'),net_array(CN.index('t15'),0.30,0.0114,cp),hsel=hh)
        p("CAPSENS t15 h=%d cap=%s mean %+9.4f med %+7.4f n %d k %d"%(hh,cp,r['mean'],r['median'],r['n'],r['k']))
# dropout sensitivity + toll sensitivity on the plain 15m baseline (harness sanity check)
for d in (0.30,0.50,1.00):
    for tl in (0.0114,0.025):
        r=evaluate(np.ones(N,bool),CN.index('t15'),net_array(CN.index('t15'),d,tl),hsel=1)
        p("SANITY t15 train drop=%.2f toll=%.4f mean %+7.4f med %+7.4f n %d k %d res %.4f"%(d,tl,r['mean'],r['median'],r['n'],r['k'],r['res']))
        r=evaluate(np.ones(N,bool),CN.index('t15'),net_array(CN.index('t15'),d,tl),hsel=2)
        p("SANITY t15 valid drop=%.2f toll=%.4f mean %+7.4f med %+7.4f n %d k %d res %.4f"%(d,tl,r['mean'],r['median'],r['n'],r['k'],r['res']))

# ---------- bucketing (edges from TRAIN bars only) ----------
def buckets(vals, tr, q):
    v=vals[tr]; v=v[np.isfinite(v)]
    edges=np.unique(np.quantile(v,np.linspace(0,1,q+1)[1:-1]))
    b=np.searchsorted(edges, vals, 'right').astype(np.int8)
    return b, len(edges)+1

BFEAT={}; BQ={}
for fi,f in enumerate(FN):
    for q in (4,6):
        b,nb=buckets(P['FEAT'][:,fi],TR,q)
        BFEAT[(f,q)]=b; BQ[(f,q)]=nb

MFEAT={}
mv=P['META']
# m_ttg_log terciles, m_hour 4 blocks, creator_prior 0/1/2+, cohort10 terciles, px0 terciles, v0 terciles
def terc(x):
    b,nb=buckets(x,TR,3); return b,nb
MFEAT['m_ttg']=terc(mv[:,0])
h=mv[:,1].astype(int); MFEAT['m_hour']=((h//6).astype(np.int8),4)
cp=mv[:,2]; MFEAT['m_creator_prior']=(np.clip(cp,0,2).astype(np.int8),3)
MFEAT['m_cohort10']=terc(mv[:,3])
MFEAT['m_px0']=terc(mv[:,4])
MFEAT['m_v0']=terc(mv[:,5])
MKEYS=list(MFEAT)
p("meta bucket sizes", {k:int(MFEAT[k][1]) for k in MKEYS})

MINN=150; MINK=25
results=[]
nsweep=0

def cell(mask, ci, tag, desc):
    global nsweep
    nsweep+=1
    r=evaluate(mask,ci,NET[ci],hsel=1)
    if r is None or r['n']<MINN or r['k']<MINK: return None
    b=BASE[(ci,'tr')]
    t,pv=welch(r['permint'], b['permint'])
    return dict(desc=desc,ci=ci,combo=CN[ci],tr_mean=r['mean'],tr_med=r['median'],
                tr_n=r['n'],tr_k=r['k'],tr_res=r['res'],base=b['mean'],edge=r['mean']-b['mean'],t=t,p=pv)

# ================= PHASE A : 1-way screen, all 32 exits =================
PA=[]
for fi,f in enumerate(FN):
    b=BFEAT[(f,6)]; nb=BQ[(f,6)]
    for k in range(nb):
        m=(b==k)
        for ci in range(len(CN)):
            r=cell(m,ci,'A',('%s=q%d/%d'%(f,k,nb),))
            if r: PA.append(r)
for mk in MKEYS:
    b,nb=MFEAT[mk]
    for k in range(nb):
        m=(b==k)
        for ci in range(len(CN)):
            r=cell(m,ci,'A',('%s=%d/%d'%(mk,k,nb),))
            if r: PA.append(r)
p("PHASE A done: %d cells kept, swept %d, t=%.1f"%(len(PA),nsweep,time.time()-T0))
PA.sort(key=lambda x:-x['edge'])
for r in PA[:40]:
    p("  A %-26s %-14s tr %+7.4f base %+7.4f edge %+7.4f n %5d k %3d p %.4f"%(r['desc'][0],r['combo'],r['tr_mean'],r['base'],r['edge'],r['tr_n'],r['tr_k'],r['p']))
json.dump([{k:v for k,v in r.items() if k!='permint'} for r in PA], open(OUT+'/phaseA.json','w'), default=str)

# feature-level signal score: max positive edge with p<0.2 achieved by any bucket/exit
score={}
for r in PA:
    f=r['desc'][0].split('=')[0]
    score[f]=max(score.get(f,-9), r['edge'] if r['p']<0.25 else -9)
p("feature scores", sorted(score.items(), key=lambda x:-x[1]))
BARSEL=[f for f in FN if score.get(f,-9)>0]
p("bar features carrying ANY 1-way signal:", BARSEL)
json.dump(dict(score={k:float(v) for k,v in score.items()}, barsel=BARSEL, nsweep=nsweep), open(OUT+'/scores.json','w'))
p("t=%.1f"%(time.time()-T0))
