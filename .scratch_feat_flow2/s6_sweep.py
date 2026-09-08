import numpy as np, time, json, sys
W='/home/anont/meme/.scratch_feat_flow2'
out=open(W+'/sweep.txt','w')
def p(*a): print(*a,file=out); out.flush()

Z=np.load(W+'/feats.npz',allow_pickle=True)
X=Z['X']; DM=Z['DM'].astype(np.int64); hv=Z['hv']; FEATS=list(Z['FEATS']); mints=list(Z['mints'])
O=np.load(W+'/outcomes.npz',allow_pickle=True)
RET=O['RET']; EOFF=O['EOFF']; FROZEN=O['FROZEN']; CENS=O['CENS']; names=list(O['names']); TE=O['TE']
HOR=list(O['HORIZ'])
NS,NDP=RET.shape
p('NS',NS,'NDP',NDP)

hdp=hv[DM]
TR=(hdp==1); VA=(hdp==2)
p('train dp',int(TR.sum()),'validate dp',int(VA.sum()))
NM=len(mints)

TOLL=0.0114; TOLL2=0.025
struct_h=np.array([HOR.index(int(nm.split('|')[0][1:])) for nm in names])

TEl=TE.tolist(); DMl=DM.tolist()
EOFFl=[EOFF[s].tolist() for s in range(NS)]

def evaluate(sel, s, split_mask, frozen_charge):
    """sel: ascending global dp indices already restricted to split & uncensored."""
    hidx=struct_h[s]
    eo=EOFFl[s]
    keep=[]
    curm=-1; free=-1
    for i in sel:
        m=DMl[i]
        if m!=curm:
            curm=m; free=-1
        t=TEl[i]
        if t>=free:
            keep.append(i)
            free=t+eo[i]
    if not keep: return None
    ki=np.asarray(keep)
    g=RET[s][ki].astype(np.float64)
    fz=FROZEN[hidx][ki]
    if frozen_charge is not None:
        g=np.where(fz,frozen_charge,g)
    net=(1.0+g)*(1.0-TOLL)-1.0
    net2=(1.0+g)*(1.0-TOLL2)-1.0
    mm=DM[ki]
    cnt=np.bincount(mm,minlength=NM)
    s1=np.bincount(mm,weights=net,minlength=NM)
    s2=np.bincount(mm,weights=net2,minlength=NM)
    nz=cnt>0
    mu=s1[nz]/cnt[nz]; mu2=s2[nz]/cnt[nz]
    return dict(n=len(keep),clusters=int(nz.sum()),mean=float(mu.mean()),median=float(np.median(mu)),
                mean25=float(mu2.mean()),frozen=float(fz.mean()),mu=mu)

# ---------- entry cells: thresholds fit on TRAIN ONLY ----------
PCT=[1,5,10,25,75,90,95,99]
cells=[]
for fi,fn in enumerate(FEATS):
    col=X[:,fi]
    tr=col[TR]
    tr=tr[np.isfinite(tr)]
    qs=np.percentile(tr,PCT)
    for pi,q in zip(PCT,qs):
        if pi<=25: cells.append((f'{fn}<=p{pi}', fi, 'lo', float(q)))
        else:      cells.append((f'{fn}>=p{pi}', fi, 'hi', float(q)))
p('n entry cells',len(cells))
p('n structures',NS)
p('STAGE-A combos',len(cells)*NS)

def cellmask(fi,dirn,q):
    col=X[:,fi]
    m=(col<=q) if dirn=='lo' else (col>=q)
    return m & np.isfinite(col)

# ---------- random controls, per structure & selection-rate ----------
rng=np.random.default_rng(20260904)
RATES=[0.01,0.05,0.10,0.25]
ctrl={}
t0=time.time()
base_tr=np.flatnonzero(TR)
for s in range(NS):
    hidx=struct_h[s]
    ok=~CENS[hidx]
    b=base_tr[ok[base_tr]]
    for rt in RATES:
        vals=[]
        for rep in range(3):
            pick=b[rng.random(len(b))<rt]
            r=evaluate(pick.tolist(),s,TR,None)
            if r: vals.append(r['mean'])
        ctrl[(s,rt)]=float(np.mean(vals)) if vals else 0.0
p('controls done %.1fs'%(time.time()-t0))
np.save(W+'/ctrl.npy',np.array([[ctrl[(s,rt)] for rt in RATES] for s in range(NS)]))

def rate_bucket(frac):
    return min(RATES,key=lambda r:abs(r-frac))

# ---------- STAGE A: full sweep on TRAIN ----------
t0=time.time()
res=[]
for ci,(cname,fi,dirn,q) in enumerate(cells):
    cm=cellmask(fi,dirn,q)
    for s in range(NS):
        hidx=struct_h[s]
        m=cm & TR & (~CENS[hidx])
        sel=np.flatnonzero(m)
        if len(sel)<60: continue
        r=evaluate(sel.tolist(),s,TR,None)
        if r is None or r['clusters']<30 or r['n']<60: continue
        rs=evaluate(sel.tolist(),s,TR,-0.50)
        frac=len(sel)/max(1,int((TR&(~CENS[hidx])).sum()))
        c=ctrl[(s,rate_bucket(frac))]
        res.append((cname,s,r['mean'],r['median'],r['mean25'],rs['mean'],r['n'],r['clusters'],c,r['mean']-c,r['frozen']))
    if ci%40==0: p('cell %d/%d  %.0fs  kept=%d'%(ci,len(cells),time.time()-t0,len(res)))
p('STAGE-A done %.1fs  evaluated rows=%d'%(time.time()-t0,len(res)))

import pickle
pickle.dump(res,open(W+'/stageA.pkl','wb'))
arr=sorted(res,key=lambda z:-z[2])
p('--- top 40 TRAIN by mint-equal mean net (toll 1.14) ---')
p('%-26s %-34s %8s %8s %8s %8s %6s %5s %8s %8s'%('cell','struct','mean','median','mean2.5','fz-50','n','k','ctrl','edge'))
for z in arr[:40]:
    p('%-26s %-34s %8.4f %8.4f %8.4f %8.4f %6d %5d %8.4f %8.4f'%(z[0],names[z[1]],z[2],z[3],z[4],z[5],z[6],z[7],z[8],z[9]))
pos=[z for z in arr if z[2]>0]
p('rows with train mean>0:',len(pos),'of',len(res))
strict=[z for z in arr if z[2]>0 and z[5]>0 and z[9]>0]
p('rows train mean>0 AND frozen@-50>0 AND beats random control:',len(strict))
pickle.dump(strict,open(W+'/stageA_strict.pkl','wb'))
out.close()
