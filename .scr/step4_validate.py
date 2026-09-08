import numpy as np, sys, pickle, time, itertools
sys.path.insert(0,'/home/anont/meme/.scr')
from sim import *
rng=np.random.default_rng(7)
t0=time.time()
S=pickle.load(open(SCR+'sweep3.pkl','rb'))
res=S['res']; THR=S['THR']; PAIRS=S['PAIRS']
KI={n:i for i,n in enumerate(ALLF)}

def cond(m,p,li):
    k=KI[p[0]]; thr=THR[p][li]
    X=FM[m]; V=VALID[m]
    c=(X[:,k]>=thr) if p[1]=='ge' else (X[:,k]<=thr)
    return c & V[:,k]

# distinct entry conditions ranked by best train excess
best={}
for r in res:
    key=(r['trip'],r['lc'])
    if key not in best or r['exc']>best[key]: best[key]=r['exc']
ents=sorted(best.items(),key=lambda kv:-kv[1])
print('distinct positive train entry-conditions',len(ents))
ENTS=[k for k,_ in ents[:150]]

def sigs(mset,key):
    trip,lc=key; SIG={}
    for m in mset:
        c=cond(m,trip[0],lc[0])&cond(m,trip[1],lc[1])&cond(m,trip[2],lc[2])
        ix=np.flatnonzero(c)
        if ix.size: SIG[m]=ix
    return SIG

def run_idx(SIG,mset,ex,pos,toll=TOLL,drop=-0.50):
    permint=[];ntr=0;nres=0
    H=ex[-1] if ex[0]!='H' else ex[1]
    for m in mset:
        idx=SIG.get(m)
        if idx is None or idx.size==0: continue
        d=per[m]; n=len(d['ts']); ts=d['ts']
        rs=[];block=-1
        for s in idx:
            a=s+1
            if a>=n: break
            if a<=block: continue
            if ts[a]+H*60>gmax: break
            r,rr,ei=trade_ret(m,a,ex,pos,toll,drop)
            rs.append(r);ntr+=1
            if rr:nres+=1
            block= ei if ei>=0 else n
        if rs: permint.append(float(np.mean(rs)))
    if not permint: return None
    arr=np.array(permint)
    return dict(mean=float(arr.mean()),median=float(np.median(arr)),n=ntr,
                clusters=len(permint),res=nres/max(1,ntr),arr=arr)

def allmask(m): return np.ones(len(per[m]['ts']),dtype=bool)
ALLSIG={'T':{m:np.arange(len(per[m]['ts'])) for m in TRAIN},
        'V':{m:np.arange(len(per[m]['ts'])) for m in VALD}}
CTRL={}
for ex in EXITS:
    for pos in POS:
        for lbl,ms in (('T',TRAIN),('V',VALD)):
            r=run_idx(ALLSIG[lbl],ms,ex,('FULL',) if pos==('FULL',) else pos)
            CTRL[(lbl,str(ex),str(pos))]=(r['mean'],r['median'],r['n'],r['clusters'])
print('controls done',time.time()-t0,flush=True)
pickle.dump(CTRL,open(SCR+'ctrl_full.pkl','wb'))

# ---- TRAIN: full exit x position grid on the surviving entry conditions ----
trainres=[];nsw=0;REGION=[]
for ei,key in enumerate(ENTS):
    SIG=sigs(TRAIN,key)
    if len(SIG)<25: continue
    for ex in EXITS:
        for pos in POS:
            nsw+=1
            r=run_idx(SIG,TRAIN,ex,pos)
            if r is None or r['clusters']<25 or r['n']<60: continue
            c=CTRL[('T',str(ex),str(pos))][0]
            REGION.append((str(ex),str(pos),r['mean']-c,r['mean'],r['median'],r['n'],r['clusters'],
                           key[0][0][0],key[0][1][0],key[0][2][0],key[1]))
            if r['mean']>0 and r['mean']-c>0.05:
                trainres.append(dict(key=key,ex=ex,pos=pos,tmean=r['mean'],tmed=r['median'],
                                     n=r['n'],cl=r['clusters'],res=r['res'],texc=r['mean']-c))
    if ei%20==0: print('ent',ei,len(trainres),round(time.time()-t0,1),flush=True)
trainres.sort(key=lambda r:-r['texc'])
print('STAGE3B SWEPT',nsw,'train-positive',len(trainres),flush=True)

CAND=trainres[:400]
print('validating',len(CAND),flush=True)
out=[]
for i,r in enumerate(CAND):
    SIG=sigs(VALD,r['key'])
    if len(SIG)<15: continue
    v=run_idx(SIG,VALD,r['ex'],r['pos'])
    if v is None: continue
    cV=CTRL[('V',str(r['ex']),str(r['pos']))][0]
    # cluster bootstrap on validate per-mint means
    arr=v['arr']; B=4000
    bs=arr[rng.integers(0,len(arr),size=(B,len(arr)))].mean(axis=1)
    p_ctrl=float((bs<=cV).mean()); p_zero=float((bs<=0).mean())
    out.append(dict(**r,vmean=v['mean'],vmed=v['median'],vn=v['n'],vcl=v['clusters'],
                    vres=v['res'],vctrl=cV,vexc=v['mean']-cV,p_ctrl=p_ctrl,p_zero=p_zero,
                    varr=arr))
    if i%50==0: print('val',i,round(time.time()-t0,1),flush=True)
pickle.dump(dict(out=out,CTRL=CTRL,nsw=nsw,ntrain_ent=len(ents),REGION=REGION),open(SCR+'validated.pkl','wb'))

surv=[o for o in out if o['vmean']>0 and o['vexc']>0 and o['vcl']>=15]
print('\nSURVIVED BOTH SIGNS:',len(surv),'of',len(out))
surv.sort(key=lambda o:max(o['p_ctrl'],o['p_zero']))
# BH-FDR on p = max(p_ctrl,p_zero) over ALL validated candidates
allp=sorted([(max(o['p_ctrl'],o['p_zero']),o) for o in out],key=lambda x:x[0])
M=len(allp); q=0.10; kmax=0
for i,(p,o) in enumerate(allp,1):
    if p<=q*i/M: kmax=i
print('BH q=0.10 -> significant:',kmax,'of',M)
print()
for i,(p,o) in enumerate(allp[:35],1):
    tn='+'.join(f"{pp[0]}{pp[1]}{l}" for pp,l in zip(o['key'][0],o['key'][1]))
    print(f"p={p:.4f} {'*' if i<=kmax else ' '} {tn:40s} {str(o['ex']):20s} {str(o['pos']):12s} "
          f"T:{o['tmean']*100:+7.1f}(exc{o['texc']*100:+6.1f}) V:{o['vmean']*100:+7.1f}(exc{o['vexc']*100:+6.1f}) "
          f"Vmed={o['vmed']*100:+6.1f} n={o['vn']:4d} k={o['vcl']:3d} res={o['vres']*100:.0f}%")
