"""Independent robustness axis: split the SAME h in (1,2) data by wall-clock time instead of
by mint hash, and re-test the four cells that survived the mint-hash splits."""
import numpy as np, json, sqlite3
OUT='/home/anont/meme/.combo2way_scratch'
d=np.load(OUT+'/matrix2.npz',allow_pickle=True)
F=d['F']; MINT=d['mint'].astype(np.int64); HV=d['hv']; POS=d['pos'].astype(np.int64)
GROSS=d['gross']; EXIT=d['exitpos'].astype(np.int64); CLEAN=d['clean']
FEATS=[str(x) for x in d['feats']]; NF=len(FEATS); NM=int(MINT.max())+1
mints=json.load(open(OUT+'/mints2.json'))
CAP=3.0; RES=np.isfinite(GROSS)
g=np.where(RES,np.minimum(GROSS,CAP),0.0)
NET=np.where(RES,(1+g)*(1-0.0114)-1,-0.30)
MINT_l=MINT.tolist(); POS_l=POS.tolist(); EXIT_l=EXIT.tolist()
# recover wall-clock ts of the entry bar
con=sqlite3.connect('file:/home/anont/meme/research/midcap/grad_ohlcv.sqlite?mode=ro',uri=True)
bt={}
TS=np.zeros(len(MINT),dtype=np.int64)
for i in range(len(MINT)):
    m=mints[MINT_l[i]]
    if m not in bt:
        b=sorted(json.loads(con.execute('select bars_json from ohlcv where mint=?',(m,)).fetchone()[0]),key=lambda z:z[0])
        b=[x for x in b if x[1]>0 and x[4]>0 and x[2]>0 and x[3]>0]
        bt[m]=np.array([x[0] for x in b],dtype=np.int64)
    TS[i]=bt[m][POS_l[i]]
cut=int(np.median(TS))
print('time cut',cut,'early rows',int((TS<cut).sum()),'late rows',int((TS>=cut).sum()))
IDX=np.where(CLEAN==1)[0]
EARLY=IDX[TS[IDX]<cut]; LATE=IDX[TS[IDX]>=cut]
ALL=IDX
def take(rows):
    out=[];lm=-1;le=-1
    for r in rows:
        m=MINT_l[r]
        if m!=lm: lm=m; le=-1
        if le>=0 and POS_l[r]<=le: continue
        out.append(r); x=EXIT_l[r]; le=x if x>=0 else 1<<30
    return out
def stat(t):
    if not t: return None
    t=np.asarray(t)
    s=np.bincount(MINT[t],weights=NET[t],minlength=NM); c=np.bincount(MINT[t],minlength=NM)
    sel=c>0; pm=s[sel]/c[sel]
    return dict(mean=float(pm.mean()),median=float(np.median(pm)),n=int(len(t)),
                clusters=int(sel.sum()),pm=pm,posfrac=float((pm>0).mean()))
SCH={'Q5':[0,20,40,60,80,100],'R8':[0,20,30,40,50,60,70,80,100],'M10':[0,10,25,35,45,50,55,65,75,90,100]}
def bins(pcts,fit):
    B=np.full((len(MINT),NF),-1,dtype=np.int8)
    for f in range(NF):
        col=F[:,f]; tr=col[fit]; tr=tr[np.isfinite(tr)]
        if len(tr)<400: continue
        e=np.unique(np.percentile(tr,pcts))
        if len(e)<3: continue
        e[0]=-np.inf; e[-1]=np.inf
        B[:,f]=np.clip(np.searchsorted(e,col,side='right')-1,0,len(e)-2).astype(np.int8)
        B[~np.isfinite(col),f]=-1
    return B
rng=np.random.default_rng(3)
def boot(pm,reps=2000):
    b=np.array([pm[rng.integers(0,len(pm),len(pm))].mean() for _ in range(reps)])
    return float(np.percentile(b,2.5)),float(np.percentile(b,97.5))
def ctrl(split,k,reps=300):
    ms=[stat(take(np.sort(rng.choice(split,size=min(k,len(split)),replace=False)).tolist()))['mean'] for _ in range(reps)]
    ms=np.array(ms); return float(ms.mean()),float(np.percentile(ms,97.5))
CAND=[('R8','up_min',3,'density15',1,'fwd#1'),('M10','ret1',3,'barrange',6,'fwd#2'),
      ('M10','cumvol',1,None,None,'rev#1'),('M10','barrange',3,'cumvol',1,'rev#2')]
# bins fit on the EARLY half only (so LATE is out of sample on the time axis)
BE={s:bins(p,EARLY) for s,p in SCH.items()}
for name,rows in (('EARLY',EARLY),('LATE',LATE),('ALL',ALL)):
    st=stat(take(np.sort(rows).tolist()))
    print('ALLBARS %-6s mean=%+.4f med=%+.4f n=%d k=%d posfrac=%.3f'%(name,st['mean'],st['median'],st['n'],st['clusters'],st['posfrac']))
print()
for sch,fa,ba,fb,bb,tag in CAND:
    B=BE[sch]; ia=FEATS.index(fa)
    for name,rows in (('EARLY',EARLY),('LATE',LATE)):
        sel=(B[rows,ia]==ba)
        if fb: sel=sel&(B[rows,FEATS.index(fb)]==bb)
        rw=rows[sel]
        st=stat(take(np.sort(rw).tolist()))
        if not st or st['clusters']<5:
            print('%-9s %-34s %-6s  n/a (k=%s)'%(tag,'%s[%s=%s%s]'%(sch,fa,ba,(' & %s=%s'%(fb,bb)) if fb else ''),name,st['clusters'] if st else 0)); continue
        lo,hi=boot(st['pm']); cm,ch=ctrl(rows,st['n'])
        print('%-9s %-34s %-6s mean=%+.4f med=%+.4f n=%4d k=%3d posfrac=%.2f CI=[%+.4f,%+.4f] ctrl=%+.4f(hi%+.4f) %s'%(
            tag,'%s[%s=%s%s]'%(sch,fa,ba,(' & %s=%s'%(fb,bb)) if fb else ''),name,
            st['mean'],st['median'],st['n'],st['clusters'],st['posfrac'],lo,hi,cm,ch,
            'HOLDS' if lo>0 and st['mean']>ch else 'fails'))
