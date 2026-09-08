import json, math, os, sys, time
import numpy as np
W='/home/anont/meme/.regime1/'
LOG=open(W+'sweep.txt','w')
def P(*a):
    print(*a,file=LOG); LOG.flush()

z=np.load(W+'feats.npz')
EX=np.load(W+'exits.npz'); EPX=EX['EPX']; EROW=EX['EROW']
EXITS=json.load(open(W+'exits.json'))
meta=json.load(open(W+'meta.json'))
mint_slice={int(k):tuple(v) for k,v in meta['mint_slice'].items()}
mid=z['mid']; ts=z['ts']; op=z['op']; minute_idx=z['minute_idx']
last_of_mint=z['last_of_mint']; mint_h=z['mint_h']
N=len(ts); M=len(mint_h)
NEX=len(EXITS)

# ---------- position structures: GROSS + DEPLOY per (exit, pos, row) ----------
entry_row=np.arange(N)+1
valid=~last_of_mint
E0=np.where(valid, op[np.minimum(entry_row,N-1)], np.nan)
# add-row (second half) exists?
add_ok=np.zeros(N,dtype=bool); E1=np.full(N,np.nan)
for mi in range(M):
    s,e=mint_slice[mi]
    for r in range(s,e-2):
        add_ok[r]=True; E1[r]=op[r+2]
P('rows',N,'mints',M,'valid signals',int(valid.sum()))

GROSS=np.full((NEX,3,N),np.nan); DEPLOY=np.zeros((NEX,3,N)); DROP=np.zeros((NEX,N),dtype=bool)
for ei in range(NEX):
    X=EPX[ei]; er=EROW[ei]
    ok=valid & np.isfinite(E0)
    isdrop = ok & ~np.isfinite(X)
    DROP[ei]=isdrop
    res = ok & np.isfinite(X)
    # add happens only if add row <= exit row (or on dropout, if it exists)
    addr=entry_row+1
    can_add = add_ok & ((~res) | (addr<=np.where(er>=0,er,N)))
    up = can_add & np.isfinite(E1) & (E1>E0)
    for pi in range(3):
        if pi==0:
            dep=np.where(ok,1.0,0.0)
            g=np.where(res, X/E0-1.0, np.nan)
        elif pi==1:
            a=can_add & np.isfinite(E1)
            dep=np.where(ok, np.where(a,1.0,0.5),0.0)
            g=np.where(res, np.where(a, 0.5*X/E0+0.5*X/E1-1.0, 0.5*X/E0-0.5), np.nan)
        else:
            a=up
            dep=np.where(ok, np.where(a,1.0,0.5),0.0)
            g=np.where(res, np.where(a, 0.5*X/E0+0.5*X/E1-1.0, 0.5*X/E0-0.5), np.nan)
        DEPLOY[ei,pi]=dep; GROSS[ei,pi]=g
P('position arrays built')

# ---------- regime cells ----------
T0=int(z['T0'][0])
regnames=['LAUNCH60','COHVOL15','ACTCNT','FRACUP','MEDRET15','MEDRET60','YOUNGFRAC','NEWL60']
regvals={k:z[k] for k in regnames}
HOURm=z['HOUR']; CREATE_COV=z['CREATE_COV']
train_mint = mint_h==1; val_mint = mint_h==2
train_row = train_mint[mid]; val_row = val_mint[mid]
base_ok = valid & np.isfinite(E0)

rowreg={k:v[minute_idx] for k,v in regvals.items()}
rowhour=HOURm[minute_idx]; rowcov=CREATE_COV[minute_idx]

CELLS=[('ALL', np.ones(N,dtype=bool), 'no regime condition')]
NBIN=5
for k in regnames:
    v=rowreg[k]
    sel = base_ok & train_row & np.isfinite(v)
    if k=='LAUNCH60': sel = sel & rowcov
    qs=np.quantile(v[sel], [i/NBIN for i in range(1,NBIN)])
    qs=np.unique(qs)
    edges=[-np.inf]+list(qs)+[np.inf]
    for b in range(len(edges)-1):
        m=np.isfinite(v)&(v>edges[b])&(v<=edges[b+1])
        if k=='LAUNCH60': m=m&rowcov
        CELLS.append(('%s_q%d'%(k,b+1), m, '%s in (%.4g,%.4g]'%(k,edges[b],edges[b+1])))
for b in range(6):
    m=(rowhour>=b*4)&(rowhour<(b+1)*4)
    CELLS.append(('HOUR_b%d'%b, m, 'UTC hour in [%d,%d)'%(b*4,(b+1)*4)))
P('regime cells', len(CELLS))

# ---------- entry conditions ----------
ret5=z['ret5']; ret15=z['ret15']; dd=z['dd']; vsopen=z['vsopen']; agem=z['agem']; relvol=z['relvol']
ENTRIES=[
 ('ANY', np.ones(N,dtype=bool), 'any bar'),
 ('R5UP', np.isfinite(ret5)&(ret5>0), 'prior 5m return > 0'),
 ('R5DN', np.isfinite(ret5)&(ret5<=0), 'prior 5m return <= 0'),
 ('R15UP10', np.isfinite(ret15)&(ret15>0.10), 'prior 15m return > +10%'),
 ('R15DN10', np.isfinite(ret15)&(ret15<-0.10), 'prior 15m return < -10%'),
 ('DD30', np.isfinite(dd)&(dd<-0.30), '>=30% below running high'),
 ('NEARHI', np.isfinite(dd)&(dd>-0.10), 'within 10% of running high'),
 ('ABOVEOPEN', np.isfinite(vsopen)&(vsopen>0), 'close above first bar open'),
 ('BELOWOPEN', np.isfinite(vsopen)&(vsopen<=0), 'close at/below first bar open'),
 ('YOUNG30', np.isfinite(agem)&(agem<30), 'mint age < 30 min'),
 ('OLD30', np.isfinite(agem)&(agem>=30), 'mint age >= 30 min'),
]
P('entries', len(ENTRIES))

# ---------- simulator ----------
mint_of_row=mid
def simulate(rows_sorted, ei, pi, dropcharge, toll):
    """rows_sorted: np array of signal row indices ascending (grouped by mint since rows are contiguous per mint)."""
    er=EROW[ei]; dr=DROP[ei]; g=GROSS[ei,pi]; dep=DEPLOY[ei,pi]
    per={}
    cur_mint=-1; block=-1; dead=False
    for r in rows_sorted:
        m=mint_of_row[r]
        if m!=cur_mint:
            cur_mint=m; block=-1; dead=False
        if dead: continue
        if r<block: continue
        d=dep[r]
        if d<=0: continue
        if dr[r]:
            ret=dropcharge*d - toll*d
            per.setdefault(m,[]).append(ret)
            dead=True
            continue
        gg=g[r]
        if not np.isfinite(gg): continue
        ret=gg - toll*d
        per.setdefault(m,[]).append(ret)
        block=er[r]
    return per

def stats(per):
    if not per: return None
    mm=[float(np.mean(v)) for v in per.values()]
    n=sum(len(v) for v in per.values())
    mm_s=sorted(mm)
    k=len(mm)
    return dict(mean=float(np.mean(mm)), median=float(mm_s[k//2]), n=n, k=k)

DROPC=-0.30; TOLL=0.0114

# ---------- controls: unconditional (ANY x ALL) per exit/pos ----------
ctrl={}
for tag,rowmask in (('tr',train_row),('va',val_row)):
    sel=np.flatnonzero(base_ok & rowmask)
    for ei in range(NEX):
        for pi in range(3):
            s=stats(simulate(sel,ei,pi,DROPC,TOLL))
            ctrl[(tag,ei,pi)]=s
P('controls done')
for ei in range(NEX):
    s=ctrl[('tr',ei,0)]; v=ctrl[('va',ei,0)]
    P('CTRL',EXITS[ei]['name'],'P1 train mean %.4f med %.4f n %d k %d | val mean %.4f med %.4f n %d k %d'%(
        s['mean'],s['median'],s['n'],s['k'],v['mean'],v['median'],v['n'],v['k']))

# ---------- sweep ----------
t0=time.time()
results=[]
combos=0
MINN=40; MINK=15
for ci,(cname,cmask,cdesc) in enumerate(CELLS):
    for eni,(ename,emask,edesc) in enumerate(ENTRIES):
        sel_tr=np.flatnonzero(base_ok & train_row & cmask & emask)
        if len(sel_tr)<MINN:
            combos+=NEX*3
            continue
        for ei in range(NEX):
            for pi in range(3):
                combos+=1
                s=stats(simulate(sel_tr,ei,pi,DROPC,TOLL))
                if s is None: continue
                if s['n']<MINN or s['k']<MINK: continue
                c=ctrl[('tr',ei,pi)]
                if s['mean']>0 and s['mean']>c['mean']:
                    results.append((cname,ename,ei,pi,s['mean'],s['median'],s['n'],s['k'],c['mean']))
    if ci%10==0: P('cell',ci,cname,'elapsed %.1f'%(time.time()-t0),'hits',len(results))
P('SWEEP DONE combos',combos,'train positives',len(results),'elapsed %.1f'%(time.time()-t0))
results.sort(key=lambda x:-x[4])
for r in results[:60]:
    P('TRAINPOS %s | %s | %s | P%d | mean %.4f med %.4f n %d k %d ctrl %.4f'%(
        r[0],r[1],EXITS[r[2]]['name'],r[3]+1,r[4],r[5],r[6],r[7],r[8]))
json.dump([[r[0],r[1],int(r[2]),int(r[3]),r[4],r[5],int(r[6]),int(r[7]),r[8]] for r in results], open(W+'trainpos.json','w'))
json.dump({'combos':combos}, open(W+'combos.json','w'))
LOG.close()
