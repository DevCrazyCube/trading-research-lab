"""Robustness autopsy of the surviving cells: per-mint contribution, leave-one-mint-out,
and a resolution-matched control (the survivors all have res=1.00, so match on that)."""
import numpy as np, json, itertools
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
def take(rows):
    out=[];lm=-1;le=-1
    for r in rows:
        m=MINT_l[r]
        if m!=lm: lm=m; le=-1
        if le>=0 and POS_l[r]<=le: continue
        out.append(r); x=EXIT_l[r]; le=x if x>=0 else 1<<30
    return out
def permint(t):
    t=np.asarray(t)
    s=np.bincount(MINT[t],weights=NET[t],minlength=NM); c=np.bincount(MINT[t],minlength=NM)
    sel=np.where(c>0)[0]
    return sel,s[sel]/c[sel],c[sel]
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
BS={s:bins(p,TR) for s,p in SCH.items()}
CANDS=[('R8','up_min',3,'density15',1),('M10','ret1',3,'barrange',6)]
rng=np.random.default_rng(11)
# resolution-matched control: random cells restricted to rows whose trade resolves
RESROWS=VA[RES[VA]]
for sch,fa,ba,fb,bb in CANDS:
    B=BS[sch]; ia=FEATS.index(fa); ib=FEATS.index(fb)
    sel=(B[VA,ia]==ba)&(B[VA,ib]==bb)
    tk=take(np.sort(VA[sel]).tolist())
    ms,pm,cnt=permint(tk)
    order=np.argsort(-pm)
    print('\n=== %s[%s=%d & %s=%d]  VAL n=%d k=%d mean=%+.4f med=%+.4f res=%.3f'%(
        sch,fa,ba,fb,bb,len(tk),len(pm),pm.mean(),np.median(pm),RES[np.asarray(tk)].mean()))
    print('  top mints by per-mint mean:')
    for j in order[:6]:
        print('    %-46s trades=%d mean=%+.4f'%(mints[ms[j]][:44],cnt[j],pm[j]))
    print('  bottom:')
    for j in order[-4:]:
        print('    %-46s trades=%d mean=%+.4f'%(mints[ms[j]][:44],cnt[j],pm[j]))
    loo=np.array([np.delete(pm,j).mean() for j in range(len(pm))])
    print('  leave-one-mint-out mean: min=%+.4f max=%+.4f  (drop worst-case mint -> %+.4f)'%(
        loo.min(),loo.max(),loo.min()))
    print('  fraction of mints with positive mean: %.3f (%d/%d)'%((pm>0).mean(),(pm>0).sum(),len(pm)))
    print('  share of total from top mint: %.3f'%((pm.max()-pm.mean())/abs(pm.sum()/len(pm))if pm.mean() else float('nan')))
    # resolution-matched random control
    ms_=[]
    for _ in range(400):
        s=np.sort(rng.choice(RESROWS,size=min(len(tk),len(RESROWS)),replace=False))
        t2=take(s.tolist())
        _,p2,_=permint(t2); ms_.append(p2.mean())
    ms_=np.array(ms_)
    print('  resolution-MATCHED random control: mean=%+.4f  p97.5=%+.4f  -> cell above control hi? %s'%(
        ms_.mean(),np.percentile(ms_,97.5),pm.mean()>np.percentile(ms_,97.5)))
    # train-side same cell, per-mint
    selt=(B[TR,ia]==ba)&(B[TR,ib]==bb)
    tkt=take(np.sort(TR[selt]).tolist()); _,pmt,_=permint(tkt)
    print('  TRAIN same cell: n=%d k=%d mean=%+.4f med=%+.4f posfrac=%.3f'%(
        len(tkt),len(pmt),pmt.mean(),np.median(pmt),(pmt>0).mean()))
