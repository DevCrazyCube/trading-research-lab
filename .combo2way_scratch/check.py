"""Apples-to-apples: use the EXACT forward-sweep bin edges (fit on h1 train) and evaluate the two
survivors over (a) h1 only, (b) h2 only, (c) all h in (1,2), (d) early time half, (e) late half."""
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
IDX=np.where(CLEAN==1)[0]; TR=IDX[HV[IDX]==1]; VA=IDX[HV[IDX]==2]
con=sqlite3.connect('file:/home/anont/meme/research/midcap/grad_ohlcv.sqlite?mode=ro',uri=True)
bt={}; TS=np.zeros(len(MINT),dtype=np.int64)
for i in range(len(MINT)):
    m=mints[MINT_l[i]]
    if m not in bt:
        b=sorted(json.loads(con.execute('select bars_json from ohlcv where mint=?',(m,)).fetchone()[0]),key=lambda z:z[0])
        b=[x for x in b if x[1]>0 and x[4]>0 and x[2]>0 and x[3]>0]
        bt[m]=np.array([x[0] for x in b],dtype=np.int64)
    TS[i]=bt[m][POS_l[i]]
cut=int(np.median(TS[IDX]))
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
                clusters=int(sel.sum()),pm=pm,posfrac=float((pm>0).mean()),res=float(RES[t].mean()))
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
    return B,{f:[float(x) for x in np.unique(np.percentile(F[:,f][fit][np.isfinite(F[:,f][fit])],pcts))] for f in range(NF) if np.isfinite(F[:,f][fit]).sum()>=400}
BS={}
for s,p in SCH.items(): BS[s]=bins(p,TR)[0]
rng=np.random.default_rng(5)
def boot(pm,reps=3000):
    b=np.array([pm[rng.integers(0,len(pm),len(pm))].mean() for _ in range(reps)])
    return float(np.percentile(b,2.5)),float(np.percentile(b,97.5))
def ctrl(split,k,reps=300):
    return float(np.mean([stat(take(np.sort(rng.choice(split,size=min(k,len(split)),replace=False)).tolist()))['mean'] for _ in range(reps)]))
CAND=[('R8','up_min',3,'density15',1),('M10','ret1',3,'barrange',6)]
ALL=IDX
SPLITS=[('h1 (train)',TR),('h2 (validate)',VA),('h1+h2 pooled',ALL),
        ('EARLY(all mints)',ALL[TS[ALL]<cut]),('LATE(all mints)',ALL[TS[ALL]>=cut]),
        ('h2 EARLY',VA[TS[VA]<cut]),('h2 LATE',VA[TS[VA]>=cut])]
for sch,fa,ba,fb,bb in CAND:
    B=BS[sch]; ia=FEATS.index(fa); ib=FEATS.index(fb)
    print('\n=== %s[%s=%d & %s=%d]  (bin edges fit on h1 train, as in the forward sweep)'%(sch,fa,ba,fb,bb))
    for nm,rows in SPLITS:
        sel=(B[rows,ia]==ba)&(B[rows,ib]==bb)
        rw=rows[sel]
        st=stat(take(np.sort(rw).tolist()))
        if not st: print('  %-18s n/a'%nm); continue
        lo,hi=boot(st['pm']) if st['clusters']>=4 else (float('nan'),float('nan'))
        c=ctrl(rows,st['n'])
        print('  %-18s mean=%+.4f med=%+.4f n=%4d k=%3d posfrac=%.2f res=%.2f CI=[%+.4f,%+.4f] ctrl=%+.4f'%(
            nm,st['mean'],st['median'],st['n'],st['clusters'],st['posfrac'],st['res'],lo,hi,c))
