import sqlite3, json, hashlib, math, pickle, os, sys, time
import numpy as np

R='/home/anont/meme/research/'
D='/home/anont/meme/.tmp_combo3/'
LOG=open(D+'build_log.txt','w')
def p(*a):
    print(*a, file=LOG); LOG.flush()

t0=time.time()
HS=[5,10,15,20,30,45,60]
TPS=[0.10,0.20,0.30]
SLS=[-0.15,-0.25,-0.35]
TRS=[0.20,0.30]
MAXW=60*60  # seconds forward window

def h3(m): return int(hashlib.md5(m.encode()).hexdigest(),16)%3

# ---------------- bars ----------------
db=sqlite3.connect(R+'midcap/grad_ohlcv.sqlite')
raw={}
for m,bj in db.execute('select mint,bars_json from ohlcv where n_bars>0'):
    k=h3(m)
    if k==0: continue
    b=json.loads(bj)
    b.sort(key=lambda x:x[0])
    if len(b)<3: continue
    raw[m]=(k,b)
p('mints loaded',len(raw),'bars',sum(len(v[1]) for v in raw.values()))

# ---------------- window_labels metadata ----------------
db2=sqlite3.connect(R+'b11a/window_labels.sqlite')
wl={}
creator_slots={}
for bc,mint,creator,cslot,bt,comp in db2.execute('select bonding_curve,mint,creator,create_slot,block_time,complete from window_label'):
    wl[mint]=(bc,creator,cslot,bt,comp)
    creator_slots.setdefault(creator,[]).append(cslot)
for c in creator_slots: creator_slots[c].sort()
p('wl',len(wl))

# ---------------- pre-graduation bonding-curve flow ----------------
bcmap={}
for m in raw:
    if m in wl: bcmap[wl[m][0]]=m
db3=sqlite3.connect(R+'b11a/b11a_bodies.sqlite')
flow={}
cur=db3.execute('select bonding_curve,slot,virtual_quote_before,virtual_quote_after from reserve_observation')
acc={}
for bc,slot,qb,qa in cur:
    m=bcmap.get(bc)
    if m is None: continue
    if qb is None or qa is None: continue
    acc.setdefault(m,[]).append((slot,qa-qb))
p('flow mints',len(acc),'t',time.time()-t0)
for m,rows in acc.items():
    rows.sort()
    slots=[r[0] for r in rows]; dq=[r[1] for r in rows]
    n=len(rows)
    buy=[d for d in dq if d>0]; sell=[-d for d in dq if d<0]
    bv=float(sum(buy)); sv=float(sum(sell))
    span=max(1,slots[-1]-slots[0])
    cut=slots[0]+0.8*span
    late=float(sum(d for s,d in rows if d>0 and s>=cut))
    flow[m]=dict(
        n=n,
        bv=bv, sv=sv,
        imb=(bv-sv)/(bv+sv) if (bv+sv)>0 else 0.0,
        maxbuy=float(max(buy)) if buy else 0.0,
        maxshare=(float(max(buy))/bv) if buy and bv>0 else 0.0,
        sellfrac=len(sell)/n if n else 0.0,
        lateshare=(late/bv) if bv>0 else 0.0,
        span=span,
        speed=n/float(span),
    )
del acc
p('flow built t',time.time()-t0)

# ---------------- per-mint panel ----------------
panel={}
for m,(k,b) in raw.items():
    n=len(b)
    ts=np.array([x[0] for x in b],dtype=np.int64)
    op=np.array([x[1] for x in b],dtype=np.float64)
    hi=np.array([x[2] for x in b],dtype=np.float64)
    lo=np.array([x[3] for x in b],dtype=np.float64)
    cl=np.array([x[4] for x in b],dtype=np.float64)
    vo=np.array([x[5] for x in b],dtype=np.float64)
    if not np.all(op>0) or not np.all(cl>0) or not np.all(lo>0): continue
    panel[m]=dict(k=k,ts=ts,op=op,hi=hi,lo=lo,cl=cl,vo=vo,n=n)
p('panel',len(panel))

# ---------------- features ----------------
FEATS=['r5','r15','r60','act15','volr','dd60','rng15','age','vlvl','pxr','upfr','gapm',
       'f_n','f_imb','f_maxshare','f_sellfrac','f_lateshare','f_speed','gradlag','cprior','hour']

def build_feats(m,P):
    ts=P['ts']; op=P['op']; hi=P['hi']; lo=P['lo']; cl=P['cl']; vo=P['vo']; n=P['n']
    idx5 =np.searchsorted(ts, ts-300, side='left')
    idx15=np.searchsorted(ts, ts-900, side='left')
    idx60=np.searchsorted(ts, ts-3600,side='left')
    idx30=np.searchsorted(ts, ts-1800,side='left')
    F={}
    F['r5'] =cl/cl[idx5]-1.0
    F['r15']=cl/cl[idx15]-1.0
    F['r60']=cl/cl[idx60]-1.0
    F['act15']=(np.arange(n)-idx15+1).astype(np.float64)
    cvol=np.concatenate(([0.0],np.cumsum(vo)))
    v5=cvol[np.arange(n)+1]-cvol[idx5]
    v30=cvol[np.arange(n)+1]-cvol[idx30]
    nb5=(np.arange(n)-idx5+1).astype(np.float64)
    nb30=(np.arange(n)-idx30+1).astype(np.float64)
    F['volr']=np.log1p((v5/np.maximum(nb5,1))/np.maximum(v30/np.maximum(nb30,1),1e-12))
    F['vlvl']=np.log10(np.maximum(v15:=(cvol[np.arange(n)+1]-cvol[idx15]),1e-9))
    runhi=np.empty(n)
    for i in range(n):
        runhi[i]=hi[idx60[i]:i+1].max()
    F['dd60']=cl/runhi-1.0
    rr=(hi-lo)/cl
    crr=np.concatenate(([0.0],np.cumsum(rr)))
    F['rng15']=(crr[np.arange(n)+1]-crr[idx15])/np.maximum(np.arange(n)-idx15+1,1)
    F['age']=(ts-ts[0])/60.0
    F['pxr']=cl/op[0]-1.0
    up=(cl>op).astype(np.float64)
    cup=np.concatenate(([0.0],np.cumsum(up)))
    F['upfr']=(cup[np.arange(n)+1]-cup[idx15])/np.maximum(np.arange(n)-idx15+1,1)
    g=np.empty(n); g[0]=0.0; g[1:]=(ts[1:]-ts[:-1])/60.0
    F['gapm']=g
    fl=flow.get(m)
    def cst(v): return np.full(n,float(v))
    if fl:
        F['f_n']=cst(math.log1p(fl['n'])); F['f_imb']=cst(fl['imb'])
        F['f_maxshare']=cst(fl['maxshare']); F['f_sellfrac']=cst(fl['sellfrac'])
        F['f_lateshare']=cst(fl['lateshare']); F['f_speed']=cst(math.log1p(fl['speed']*1000))
    else:
        for kk in ['f_n','f_imb','f_maxshare','f_sellfrac','f_lateshare','f_speed']: F[kk]=cst(np.nan)
    w=wl.get(m)
    if w:
        bt=w[3]; cs=w[2]; cr=w[1]
        F['gradlag']=cst(math.log1p(max(0,ts[0]-bt)))
        sl=creator_slots.get(cr,[])
        prior=int(np.searchsorted(np.array(sl),cs,side='left'))
        F['cprior']=cst(math.log1p(prior))
        F['hour']=cst((bt//3600)%24)
    else:
        F['gradlag']=cst(np.nan); F['cprior']=cst(np.nan); F['hour']=cst(np.nan)
    return F

# ---------------- path precompute ----------------
def build_paths(P):
    ts=P['ts']; op=P['op']; hi=P['hi']; lo=P['lo']; n=P['n']
    T={}
    for H in HS:
        T[H]=np.searchsorted(ts, ts+H*60, side='left')
    for H in HS:
        T[H]=np.where(T[H]>=n,-1,T[H])
    p3=np.searchsorted(ts, ts+180, side='left'); p3=np.where(p3>=n,-1,p3)
    end=np.searchsorted(ts, ts+MAXW, side='right')  # exclusive bound
    BIG=1<<30
    ftp={t:np.full(n,BIG,dtype=np.int64) for t in TPS}
    fsl={s:np.full(n,BIG,dtype=np.int64) for s in SLS}
    ftr={r:np.full(n,BIG,dtype=np.int64) for r in TRS}
    ptr={r:np.zeros(n,dtype=np.float64) for r in TRS}
    for j in range(n):
        ent=op[j]; e=end[j]
        tps=[(ent*(1.0+t),t) for t in TPS]
        sls=[(ent*(1.0+s),s) for s in SLS]
        rem_t=list(tps); rem_s=list(sls)
        rem_r=list(TRS)
        rmax=hi[j]
        k=j
        while k<e and (rem_t or rem_s or rem_r):
            hk=hi[k]; lk=lo[k]
            if hk>rmax: rmax=hk
            if rem_s:
                nn=[]
                for lvl,s in rem_s:
                    if lk<=lvl: fsl[s][j]=k
                    else: nn.append((lvl,s))
                rem_s=nn
            if rem_t:
                nn=[]
                for lvl,t in rem_t:
                    if hk>=lvl: ftp[t][j]=k
                    else: nn.append((lvl,t))
                rem_t=nn
            if rem_r:
                nn=[]
                for r in rem_r:
                    lvl=rmax*(1.0-r)
                    if lk<=lvl: ftr[r][j]=k; ptr[r][j]=lvl
                    else: nn.append(r)
                rem_r=nn
            k+=1
    return dict(T=T,p3=p3,ftp=ftp,fsl=fsl,ftr=ftr,ptr=ptr)

FEAT_ARR={}; PATH={}
cnt=0
for m,P in panel.items():
    FEAT_ARR[m]=build_feats(m,P)
    PATH[m]=build_paths(P)
    cnt+=1
    if cnt%50==0: p('built',cnt,'t=%.1f'%(time.time()-t0))
p('all built t=%.1f'%(time.time()-t0))

# eligible signal bars: i>=1, i+1<n, age>=5min
ELIG={}
for m,P in panel.items():
    n=P['n']; ts=P['ts']
    ii=np.arange(n-1)
    ok=(ts[ii]-ts[0])>=300
    ELIG[m]=ii[ok]
p('elig bars total',sum(len(v) for v in ELIG.values()))
tr=sum(len(ELIG[m]) for m in panel if panel[m]['k']==1)
va=sum(len(ELIG[m]) for m in panel if panel[m]['k']==2)
p('elig train(k=1)',tr,'validate(k=2)',va)
p('mints train',sum(1 for m in panel if panel[m]['k']==1 and len(ELIG[m])>0),
  'validate',sum(1 for m in panel if panel[m]['k']==2 and len(ELIG[m])>0))

with open(D+'panel.pkl','wb') as f:
    pickle.dump(dict(panel=panel,FEAT=FEAT_ARR,PATH=PATH,ELIG=ELIG,FEATS=FEATS,
                     HS=HS,TPS=TPS,SLS=SLS,TRS=TRS),f,protocol=4)
p('saved t=%.1f'%(time.time()-t0))
LOG.close()
