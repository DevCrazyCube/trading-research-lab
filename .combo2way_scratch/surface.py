"""Full 1-way response surface + 2-way pair summary (no selection, both splits)."""
import numpy as np, json, itertools, os
OUT='/home/anont/meme/.combo2way_scratch'
d=np.load(OUT+'/matrix2.npz',allow_pickle=True)
F=d['F']; MINT=d['mint'].astype(np.int64); HV=d['hv']; POS=d['pos'].astype(np.int64)
GROSS=d['gross']; EXIT=d['exitpos'].astype(np.int64); CLEAN=d['clean']
FEATS=[str(x) for x in d['feats']]; NF=len(FEATS); NM=int(MINT.max())+1
CAP=3.0; RES=np.isfinite(GROSS)
g=np.where(RES,np.minimum(GROSS,CAP),0.0)
NET=np.where(RES,(1+g)*(1-0.0114)-1,-0.30)
RAW=np.where(RES,(1+np.where(RES,GROSS,0.0))*(1-0.0114)-1,-0.30)
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
def stat(t,net=NET):
    if not t: return None
    t=np.asarray(t)
    s=np.bincount(MINT[t],weights=net[t],minlength=NM); c=np.bincount(MINT[t],minlength=NM)
    sel=c>0; pm=s[sel]/c[sel]
    return dict(mean=float(pm.mean()),median=float(np.median(pm)),n=int(len(t)),clusters=int(sel.sum()))

pcts=[0,20,40,60,80,100]
B=np.full((len(MINT),NF),-1,dtype=np.int8)
for f in range(NF):
    col=F[:,f]; tr=col[TR]; tr=tr[np.isfinite(tr)]
    if len(tr)<400: continue
    e=np.unique(np.percentile(tr,pcts))
    if len(e)<3: continue
    e[0]=-np.inf; e[-1]=np.inf
    idx=np.clip(np.searchsorted(e,col,side='right')-1,0,len(e)-2)
    idx[~np.isfinite(col)]=-1
    B[:,f]=idx.astype(np.int8)

print('=== 1-WAY QUINTILE SURFACE (capped mean / median, mint-equal, 15m, toll 1.14%, drop -30%) ===')
print('%-14s %-3s | %-34s | %-34s'%('feature','q','TRAIN mean med n k','VALIDATE mean med n k'))
for f in range(NF):
    if B[:,f].max()<1:
        print('%-14s  -- unusable (coverage/ties)'%FEATS[f]); continue
    for b in range(int(B[:,f].max())+1):
        st=stat(take(np.sort(TR[B[TR,f]==b]).tolist()))
        sv=stat(take(np.sort(VA[B[VA,f]==b]).tolist()))
        fm=lambda s:('%+.4f %+.4f %5d %4d'%(s['mean'],s['median'],s['n'],s['clusters'])) if s else 'n/a'
        print('%-14s %-3d | %-34s | %-34s'%(FEATS[f],b,fm(st),fm(sv)))

print()
print('=== 2-WAY PAIR SUMMARY (25 cells per pair; how many are val-positive, best val mean) ===')
usable=[f for f in range(NF) if B[:,f].max()>=1]
rows=[]
for fa,fb in itertools.combinations(usable,2):
    pos=0; tot=0; best=-9; bestc=None; bestmed=-9
    for ba in range(int(B[:,fa].max())+1):
        ma=B[VA,fa]==ba
        for bb in range(int(B[:,fb].max())+1):
            sel=ma&(B[VA,fb]==bb)
            if sel.sum()<40: continue
            sv=stat(take(np.sort(VA[sel]).tolist()))
            if not sv or sv['clusters']<15: continue
            tot+=1
            if sv['mean']>0: pos+=1
            if sv['mean']>best: best=sv['mean']; bestc=(ba,bb)
            bestmed=max(bestmed,sv['median'])
    if tot: rows.append((pos/tot,pos,tot,best,bestmed,FEATS[fa],FEATS[fb],bestc))
rows.sort(reverse=True)
print('%-6s %-9s %-10s %-10s %s'%('posfrac','pos/tot','bestmean','bestmed','pair (best cell)'))
for r in rows[:40]:
    print('%.2f   %3d/%-4d  %+9.4f  %+9.4f  %s x %s %s'%(r[0],r[1],r[2],r[3],r[4],r[5],r[6],r[7]))
print('...')
for r in rows[-20:]:
    print('%.2f   %3d/%-4d  %+9.4f  %+9.4f  %s x %s %s'%(r[0],r[1],r[2],r[3],r[4],r[5],r[6],r[7]))
allpos=sum(r[1] for r in rows); alltot=sum(r[2] for r in rows)
print('OVERALL val-positive cells: %d/%d = %.3f'%(allpos,alltot,allpos/alltot))
