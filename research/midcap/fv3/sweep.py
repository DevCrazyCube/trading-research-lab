import sys,os,json,time,itertools,math,pickle,collections
sys.path.insert(0,'/home/anont/meme/research/midcap/fv3')
import numpy as np
import fvh

W='/home/anont/meme/research/midcap/fv3/'
OUT=open(W+'log.txt','w',buffering=1)
def P(*a):
    OUT.write(' '.join(str(x) for x in a)+'\n')

T0=time.time()
mints,arrs,meta=fvh.load()
b=fvh.Book(mints,arrs,meta)
P('mints',b.nm,'bars',b.N,'load %.1f'%(time.time()-T0))
P('hash',dict(collections.Counter(b.hh.tolist())))
P('btime known',int(np.isfinite(b.btime).sum()))

eps=1e-300
N=b.N
rng_pc=(b.HI-b.LO)/np.maximum(b.C,eps)
typ=(b.HI+b.LO+b.C)/3.0

medV5  = fvh.roll_med(b.V,b,5,1)
medV20 = fvh.roll_med(b.V,b,20,1)
medV5_0= fvh.roll_med(b.V,b,5,0)
medV15_5=fvh.roll_med(b.V,b,15,5)
medR10 = fvh.roll_med(rng_pc,b,10,1)
sumV5  = fvh.roll_sum(b.V,b,5,0)
sumV20 = fvh.roll_sum(b.V,b,20,0)
sumTV5 = fvh.roll_sum(typ*b.V,b,5,0)
sumHL5 = fvh.roll_sum(b.HI-b.LO,b,5,0)
C1=fvh.lag(b.C,b,1); C5=fvh.lag(b.C,b,5)
TS1=fvh.lag(b.TS,b,1)
rmaxC=fvh.runmax(b.C,b)

F=collections.OrderedDict()
F['vrel5']  = b.V/np.maximum(medV5,eps)
F['vrel20'] = b.V/np.maximum(medV20,eps)
F['vacc']   = medV5_0/np.maximum(medV15_5,eps)
F['rngrel'] = rng_pc/np.maximum(medR10,eps)
F['dens10'] = fvh.density(b,10)
F['dens30'] = fvh.density(b,30)
F['gap']    = (b.TS-TS1)/60.0
F['eff5']   = np.abs(b.C-C5)/np.maximum(sumHL5,eps)
F['vwdev']  = b.C/np.maximum(sumTV5/np.maximum(sumV5,eps),eps)-1.0
F['hlcc']   = (b.HI-b.LO)/np.maximum(np.abs(b.C-C1),eps)
F['vsol5']  = sumV5
F['vshare'] = b.V/np.maximum(sumV20,eps)
F['age']    = (b.TS-b.btime[b.MID])/60.0
F['mcap']   = b.C*1e9
F['dd']     = b.C/np.maximum(rmaxC,eps)
F['ret5']   = b.C/np.maximum(C5,eps)-1.0

FN=list(F.keys()); nf=len(FN)
Fm=np.vstack([F[k] for k in FN])

elig=np.ones(N,bool)
elig &= (b.idx>=25)
elig &= (np.arange(N)+1) < b.ends[b.MID]
elig &= np.all(np.isfinite(Fm),axis=0)
P('eligible bars',int(elig.sum()),'of',N)

TR = elig & (b.mhh==1); VA = elig & (b.mhh==2)
P('train bars',int(TR.sum()),'mints',len(set(b.MID[TR].tolist())))
P('valid bars',int(VA.sum()),'mints',len(set(b.MID[VA].tolist())))

QP=[0,10,25,50,75,90,100]
TH=np.zeros((nf,len(QP)))
for i in range(nf):
    TH[i]=np.percentile(Fm[i][TR],QP); TH[i,0]=-np.inf; TH[i,-1]=np.inf
CONDS=[(0,1,'q00-10'),(0,2,'q00-25'),(2,3,'q25-50'),(3,4,'q50-75'),(4,6,'q75-100'),(5,6,'q90-100')]
nc=len(CONDS)
CM=np.zeros((nf,nc,N),bool)
for i in range(nf):
    for c,(a,z,_) in enumerate(CONDS):
        CM[i,c]=(Fm[i]>=TH[i,a])&(Fm[i]<TH[i,z])
P('\nfeature train quantiles (10/25/50/75/90):')
for i in range(nf):
    P('  %-8s'%FN[i], ' '.join('%.4g'%x for x in TH[i][1:6]))

MIDl=b.MID.tolist(); ENDl=b.ends.tolist()
def greedy_fast(sig,klist):
    taken=[]; cur=-1; nxt=-1
    for i in sig:
        m=MIDl[i]
        if m!=cur: cur=m; nxt=-1
        if i<nxt: continue
        j=i+1; e=ENDl[m]
        if j>=e: continue
        taken.append(j)
        kk=klist[j]
        nxt = kk if kk>=0 else e+1
    return taken

HOLDS=[5,15,30,60]
EXITS=[(None,None,1.0),(0.15,None,1.0),(0.30,None,1.0),(None,-0.25,1.0),
       (0.15,-0.25,1.0),(0.30,-0.40,1.0),(0.15,-0.25,0.5),(0.30,-0.25,0.5)]
TOLL=0.0114; TOLL2=0.025; DROPS=[-0.30,-0.50,-1.00]
PRIMARY=(-0.30,TOLL)
STRUCT=collections.OrderedDict()
for H in HOLDS:
    k=fvh.build_exit(b,H); mw=min(H+1,65)
    Rmax,Rmin,L=fvh.path_ext(b,k,mw); klist=k.tolist()
    for (tp,sl,fr) in EXITS:
        g=fvh.gross(b,k,Rmax,Rmin,L,tp=tp,sl=sl,tp_frac=fr)
        nm='H%d_tp%s_sl%s_f%s'%(H,tp,sl,fr)
        nets={}
        for d in DROPS: nets[(d,TOLL)]=fvh.netify(g,k,TOLL,d)
        nets[(-0.30,TOLL2)]=fvh.netify(g,k,TOLL2,-0.30)
        STRUCT[nm]=dict(k=klist,karr=k,nets=nets,H=H,tp=tp,sl=sl,fr=fr)
    del Rmax,Rmin,L
    P('  struct H=%d %.1fs'%(H,time.time()-T0))
SN=list(STRUCT.keys())

def evaluate(mask,sname,split,key=PRIMARY):
    st=STRUCT[sname]
    sig=np.flatnonzero(mask & (TR if split=='tr' else VA))
    if sig.size==0: return None
    js=greedy_fast(sig.tolist(),st['k'])
    if not js: return None
    js=np.asarray(js,dtype=np.int64)
    r=st['nets'][key][js]; mid=b.MID[js]
    u,inv=np.unique(mid,return_inverse=True)
    pm=np.bincount(inv,weights=r)/np.bincount(inv)
    return dict(n=int(js.size),clusters=int(u.size),mean=float(pm.mean()),
                median=float(np.median(pm)),pm=pm,res=float((st['karr'][js]>=0).mean()),js=js)

ALLM=np.ones(N,bool)
BASE={}
P('\n=== unconditional baselines (all eligible bars, no-overlap, mint-equal) ===')
for sname in SN:
    for split in ('tr','va'):
        r=evaluate(ALLM,sname,split); BASE[(sname,split)]=r
        if r: P('BASE %-26s %s n=%6d k=%3d mean=%+.4f med=%+.4f res=%.3f'%(sname,split,r['n'],r['clusters'],r['mean'],r['median'],r['res']))
P('baselines %.1fs'%(time.time()-T0))

# ---------- STAGE A ----------
SCREEN=['H15_tpNone_slNone_f1.0','H30_tpNone_slNone_f1.0','H5_tpNone_slNone_f1.0','H15_tp0.15_slNone_f1.0']
one=[((i,c),) for i in range(nf) for c in range(nc)]
two=[((i,ci),(j,cj)) for i in range(nf) for j in range(i+1,nf) for ci in range(nc) for cj in range(nc)]
ALL=one+two
P('\nentry conditions: %d (1w %d, 2w %d) x %d screen structures = %d evals'%(len(ALL),len(one),len(two),len(SCREEN),len(ALL)*len(SCREEN)))
combos=0; rows=[]
t=time.time()
for ec in ALL:
    m=CM[ec[0][0],ec[0][1]]
    for (fi,ci) in ec[1:]: m=m&CM[fi,ci]
    if int((m&TR).sum())<40:
        combos+=len(SCREEN); continue
    for sname in SCREEN:
        combos+=1
        r=evaluate(m,sname,'tr')
        if r is None or r['clusters']<12: continue
        base=BASE[(sname,'tr')]['mean']
        if r['mean']>0.0 and r['mean']>base+0.02:
            rows.append((ec,sname,r['mean'],r['median'],r['n'],r['clusters']))
P('STAGE A combos=%d survivors=%d %.1fs'%(combos,len(rows),time.time()-t))
rows.sort(key=lambda x:-x[2])
for r in rows[:60]:
    ec,sname,mn,md,n,k=r
    P('  A %-46s %-26s mean=%+.4f med=%+.4f n=%d k=%d'%('&'.join('%s:%s'%(FN[i],CONDS[c][2]) for i,c in ec),sname,mn,md,n,k))
pickle.dump(dict(rows=rows,FN=FN,CONDS=CONDS,combos=combos),open(W+'stageA.pkl','wb'))
P('STAGE_A_DONE %.1fs'%(time.time()-T0))
OUT.close()
