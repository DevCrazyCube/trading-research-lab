"""Deployer-identity slice: ENTRY x POSITION x EXIT grid precompute.
Harness contract A-G enforced. h==0 mints NEVER touched.
Entry bars are generated already sorted by (mint, ts).
"""
import pickle, json, bisect, time, math, os
import numpy as np
from collections import defaultdict
S='/home/anont/meme/.scratch_fc/'
CAP=float(os.environ.get('GCAP','1e18'))
TAG=os.environ.get('TAG','')
D=pickle.load(open(S+'data1.pkl','rb'))
FEAT=pickle.load(open(S+'feat.pkl','rb'))
bars=D['bars']; WL=D['WL']
OUT=open(S+'engine_log%s.txt'%TAG,'w')
def P(*a): print(*a,file=OUT); OUT.flush()
t0=time.time()
INF=float('inf')

MINTS=sorted(bars); MI={m:i for i,m in enumerate(MINTS)}; NM=len(MINTS)
bycre=defaultdict(list)
for bc,m,cr,slot,bt,comp in WL: bycre[cr].append(bt)
for v in bycre.values(): v.sort()

HORIZ=[5,15,30,60,120,240]
TPS=[0.20,0.40,0.80]
SLS=[0.25,0.45]
TRS=[0.30]
LEG=10                      # POS C second-leg delay minutes
MAXSCAN=245*60

E_mint=[]; E_ts=[]; E_px=[]
HZ_ix=[[] for _ in HORIZ]; HZ_px=[[] for _ in HORIZ]; HZ_ts=[[] for _ in HORIZ]; HZ_cut=[[] for _ in HORIZ]
TP_ts=[[] for _ in TPS]; TP_px=[[] for _ in TPS]
SL_ts=[[] for _ in SLS]; SL_px=[[] for _ in SLS]
TR_ts=[[] for _ in TRS]; TR_px=[[] for _ in TRS]
L2_ts=[]; L2_px=[]
BF_age=[]; BF_sib60=[]; BF_sib15=[]

for m in MINTS:
    B=bars[m]; n=len(B)
    ts=[r[0] for r in B]; op=[r[1] for r in B]; hi=[r[2] for r in B]; lo=[r[3] for r in B]
    bt=FEAT[m]['bt']; cl=bycre[FEAT[m]['cre']]; mi=MI[m]
    for j in range(1,n):
        e=op[j]
        if not e or e<=0: continue
        t=ts[j]; sig=ts[j-1]
        E_mint.append(mi); E_ts.append(float(t)); E_px.append(e)
        BF_age.append((sig-bt)/60.0)
        a1=bisect.bisect_left(cl,sig-3600); b1=bisect.bisect_right(cl,sig)
        BF_sib60.append(max(0,(b1-a1)-1))
        a2=bisect.bisect_left(cl,sig-900)
        BF_sib15.append(max(0,(b1-a2)-1))
        for hh,H in enumerate(HORIZ):
            cut=t+H*60
            k=bisect.bisect_left(ts,cut)
            if k<=j: k=j+1
            HZ_cut[hh].append(float(cut))
            if k<n: HZ_ix[hh].append(1); HZ_px[hh].append(op[k]); HZ_ts[hh].append(float(ts[k]))
            else:   HZ_ix[hh].append(0); HZ_px[hh].append(0.0); HZ_ts[hh].append(INF)
        k=bisect.bisect_left(ts,t+LEG*60)
        if k<=j: k=j+1
        if k<n: L2_ts.append(float(ts[k])); L2_px.append(op[k])
        else:   L2_ts.append(INF); L2_px.append(0.0)
        tpv=[e*(1+x) for x in TPS]; slv=[e*(1-x) for x in SLS]
        tpk=[-1]*len(TPS); slk=[-1]*len(SLS); trk=[-1]*len(TRS); trp=[0.0]*len(TRS)
        runmax=0.0; lim=t+MAXSCAN; k=j; need=len(TPS)+len(SLS)+len(TRS)
        while k<n and ts[k]<=lim and need>0:
            h_=hi[k]; l_=lo[k]
            if h_>runmax: runmax=h_
            for a in range(len(TPS)):
                if tpk[a]<0 and h_>=tpv[a]: tpk[a]=k; need-=1
            for a in range(len(SLS)):
                if slk[a]<0 and l_<=slv[a]: slk[a]=k; need-=1
            for a in range(len(TRS)):
                if trk[a]<0 and l_<=runmax*(1-TRS[a]):
                    trk[a]=k; trp[a]=min(runmax*(1-TRS[a]),op[k]); need-=1
            k+=1
        for a in range(len(TPS)):
            kk=tpk[a]; TP_ts[a].append(float(ts[kk]) if kk>=0 else INF); TP_px[a].append(tpv[a] if kk>=0 else 0.0)
        for a in range(len(SLS)):
            kk=slk[a]; SL_ts[a].append(float(ts[kk]) if kk>=0 else INF); SL_px[a].append(min(slv[a],op[kk]) if kk>=0 else 0.0)
        for a in range(len(TRS)):
            kk=trk[a]; TR_ts[a].append(float(ts[kk]) if kk>=0 else INF); TR_px[a].append(trp[a] if kk>=0 else 0.0)

N=len(E_mint)
P('entry bars',N,'elapsed',round(time.time()-t0,1))
npf=lambda x: np.array(x,dtype=np.float64)
E_ts_a=npf(E_ts); E_px_a=npf(E_px)
HZ_px=[npf(x) for x in HZ_px]; HZ_ts=[npf(x) for x in HZ_ts]; HZ_cut=[npf(x) for x in HZ_cut]
HZ_has=[np.array(x,dtype=bool) for x in HZ_ix]
TP_ts=[npf(x) for x in TP_ts]; TP_px=[npf(x) for x in TP_px]
SL_ts=[npf(x) for x in SL_ts]; SL_px=[npf(x) for x in SL_px]
TR_ts=[npf(x) for x in TR_ts]; TR_px=[npf(x) for x in TR_px]
L2_ts_a=npf(L2_ts); L2_px_a=npf(L2_px)
BF_age=npf(BF_age); BF_sib60=np.array(BF_sib60); BF_sib15=np.array(BF_sib15)

BFS=[('all',np.ones(N,dtype=bool)),
     ('age<20',BF_age<20),
     ('age<60',BF_age<60),
     ('age20_120',(BF_age>=20)&(BF_age<120)),
     ('age60_240',(BF_age>=60)&(BF_age<240)),
     ('age120_480',(BF_age>=120)&(BF_age<480)),
     ('age>=240',BF_age>=240),
     ('sib60>=1',BF_sib60>=1),
     ('sib60==0',BF_sib60==0),
     ('sib15>=1',BF_sib15>=1),
     ('sib60>=3',BF_sib60>=3)]
P('bar filters',[(a,int(b.sum())) for a,b in BFS])

def resolve(hh,tpi,sli,tri,pos):
    cut=HZ_cut[hh]; hzp=HZ_px[hh]; hzt=HZ_ts[hh]; hzh=HZ_has[hh]
    kinds=[]; evts=[]; evpx=[]
    if sli is not None: kinds.append(0); evts.append(np.where(SL_ts[sli]<=cut,SL_ts[sli],INF)); evpx.append(SL_px[sli])
    if tri is not None: kinds.append(1); evts.append(np.where(TR_ts[tri]<=cut,TR_ts[tri],INF)); evpx.append(TR_px[tri])
    if tpi is not None: kinds.append(2); evts.append(np.where(TP_ts[tpi]<=cut,TP_ts[tpi],INF)); evpx.append(TP_px[tpi])
    best_ts=np.full(N,INF); best_px=np.zeros(N); best_k=np.full(N,-1,dtype=np.int8)
    for a in range(len(evts)):
        take=evts[a]<best_ts
        best_ts=np.where(take,evts[a],best_ts); best_px=np.where(take,evpx[a],best_px)
        best_k=np.where(take,kinds[a],best_k)
    have_ev=np.isfinite(best_ts)
    resolved=have_ev|hzh
    ex_px=np.where(have_ev,best_px,hzp)
    ex_ts=np.where(have_ev,best_ts,hzt)
    with np.errstate(divide='ignore',invalid='ignore'):
        gross=ex_px/E_px_a-1.0
    if pos=='A':
        g=gross
    elif pos=='B':
        tp_first=have_ev&(best_k==2)
        with np.errstate(divide='ignore',invalid='ignore'):
            rem=hzp/E_px_a-1.0
        g=np.where(tp_first,0.5*gross+0.5*rem,gross)
        resolved=np.where(tp_first,hzh,resolved)
        ex_ts=np.where(tp_first,hzt,ex_ts)
    elif pos=='C':
        fills=(L2_ts_a<ex_ts)&(L2_px_a>0)
        with np.errstate(divide='ignore',invalid='ignore'):
            g2=ex_px/np.where(L2_px_a>0,L2_px_a,1.0)-1.0
        g=np.where(fills,0.5*gross+0.5*g2,0.5*gross)
    g=np.minimum(g,CAP)
    g=np.where(resolved,g,np.nan)
    blockto=np.where(resolved,ex_ts,cut)
    blockto=np.where(np.isfinite(blockto),blockto,cut)
    return g,blockto,resolved

MM=E_mint; TT=E_ts
BF_IDX=[np.nonzero(b)[0].tolist() for _,b in BFS]
P('bf sizes',[len(x) for x in BF_IDX],'total walk iters/struct',sum(len(x) for x in BF_IDX))

def walk(idxlist,g,bl,rs):
    n_res=[0]*NM; s_g=[0.0]*NM; n_do=[0]*NM
    free=-1.0; cur=-1
    for a in idxlist:
        mi=MM[a]
        if mi!=cur: cur=mi; free=-1.0
        t=TT[a]
        if t<free: continue
        if rs[a]:
            v=g[a]
            if v!=v: continue
            n_res[mi]+=1; s_g[mi]+=v
        else:
            n_do[mi]+=1
        free=bl[a]
    return n_res,s_g,n_do

STRUCTS=[]
for hh,H in enumerate(HORIZ):
    for tpi in [None]+list(range(len(TPS))):
        for sli in [None]+list(range(len(SLS))):
            for tri in [None]+list(range(len(TRS))):
                for pos in ['A','B','C']:
                    if pos=='B' and tpi is None: continue
                    STRUCTS.append((hh,tpi,sli,tri,pos))
P('structs',len(STRUCTS),'x barfilters',len(BFS),'=',len(STRUCTS)*len(BFS))

RES={}
for si,(hh,tpi,sli,tri,pos) in enumerate(STRUCTS):
    g,bl,rs=resolve(hh,tpi,sli,tri,pos)
    gl=g.tolist(); bll=bl.tolist(); rsl=rs.tolist()
    for bi,idxl in enumerate(BF_IDX):
        RES[(si,bi)]=walk(idxl,gl,bll,rsl)
    if si%25==0: P('struct',si,round(time.time()-t0,1))
P('done',round(time.time()-t0,1))
pickle.dump(dict(RES=RES,STRUCTS=STRUCTS,BFS=[b[0] for b in BFS],
                 HORIZ=HORIZ,TPS=TPS,SLS=SLS,TRS=TRS,LEG=LEG,MINTS=MINTS),
            open(S+'res%s.pkl'%TAG,'wb'),protocol=4)
P('saved',round(time.time()-t0,1))
OUT.close()
