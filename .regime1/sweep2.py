"""Sweep 2: finer regime resolution (deciles + 2-way interactions), non-truncating
time exits (no fill assumption) plus realistically-slipped trailing exits."""
import json, numpy as np, time, itertools
W='/home/anont/meme/.regime1/'
LOG=open(W+'sweep2.txt','w')
def P(*a): print(*a,file=LOG); LOG.flush()
rng=np.random.default_rng(11)
z=np.load(W+'feats.npz'); meta=json.load(open(W+'meta.json'))
mint_slice={int(k):tuple(v) for k,v in meta['mint_slice'].items()}
mid=z['mid']; ts=z['ts']; op=z['op']; hi=z['hi']; lo=z['lo']; minute_idx=z['minute_idx']
last_of_mint=z['last_of_mint']; mint_h=z['mint_h']
N=len(ts); M=len(mint_h)
valid=~last_of_mint; E0=np.where(valid, op[np.minimum(np.arange(N)+1,N-1)], np.nan)
add_ok=np.zeros(N,dtype=bool); E1=np.full(N,np.nan)
for mi in range(M):
    s,e=mint_slice[mi]
    for r in range(s,e-2): add_ok[r]=True; E1[r]=op[r+2]

def hrow(H):
    hr=np.full(N,-1,dtype=np.int64)
    for mi in range(M):
        s,e=mint_slice[mi]; t=ts[s:e]
        j=np.searchsorted(t,t+H*60,side='left'); hr[s:e]=np.where(j<(e-s), j+s, -1)
    return hr
HORIZ=[5,10,15,30,60,120]; HR={H:hrow(H) for H in HORIZ}

EXN=[]; EPX=[]; EROW=[]
for H in HORIZ:
    hr=HR[H]; e0=np.arange(N)+1
    j=np.where(valid, hr[np.minimum(e0,N-1)], -1)
    px=np.where(j>=0, op[np.maximum(j,0)], np.nan)
    EXN.append('T%d'%H); EPX.append(np.where(valid,px,np.nan)); EROW.append(j)
def build_trail(H,TR,slip):
    hr=HR[H]; epx=np.full(N,np.nan); er=np.full(N,-1,dtype=np.int64)
    for r in range(N):
        if last_of_mint[r]: continue
        e0=r+1; E=op[e0]; j=hr[e0]; stop=j if j>=0 else mint_slice[mid[r]][1]
        peak=E; px=None; xr=-1
        for k in range(e0,stop):
            trig=peak*(1-TR)
            if lo[k]<=trig: px=trig*(1-slip); xr=k; break
            if hi[k]>peak: peak=hi[k]
        if px is None and j>=0: px=op[j]; xr=j
        if px is not None: epx[r]=px; er[r]=xr
    return epx,er
for H,TR in ((60,0.25),(120,0.35)):
    a,b=build_trail(H,TR,0.15); EXN.append('T%d_TR%d_slip15'%(H,TR*100)); EPX.append(a); EROW.append(b)
EPX=np.array(EPX); EROW=np.array(EROW); NEX=len(EXN)
P('exits', EXN)

GROSS=np.full((NEX,3,N),np.nan); DEPLOY=np.zeros((NEX,3,N)); DROP=np.zeros((NEX,N),dtype=bool)
for ei in range(NEX):
    X=EPX[ei]; er=EROW[ei]; ok=valid&np.isfinite(E0)
    DROP[ei]=ok&~np.isfinite(X); res=ok&np.isfinite(X); addr=np.arange(N)+2
    can_add=add_ok&((~res)|(addr<=np.where(er>=0,er,N))); up=can_add&np.isfinite(E1)&(E1>E0)
    for pi in range(3):
        if pi==0: DEPLOY[ei,pi]=np.where(ok,1.,0.); GROSS[ei,pi]=np.where(res,X/E0-1.,np.nan)
        else:
            a=(can_add&np.isfinite(E1)) if pi==1 else up
            DEPLOY[ei,pi]=np.where(ok,np.where(a,1.,.5),0.)
            GROSS[ei,pi]=np.where(res,np.where(a,0.5*X/E0+0.5*X/E1-1.,0.5*X/E0-0.5),np.nan)

train_row=(mint_h[mid]==1); val_row=(mint_h[mid]==2); base_ok=valid&np.isfinite(E0)
regnames=['LAUNCH60','COHVOL15','ACTCNT','FRACUP','MEDRET15','MEDRET60','YOUNGFRAC','NEWL60']
cov=z['CREATE_COV'][minute_idx]
rowreg={k:z[k][minute_idx] for k in regnames}
CELLS=[('ALL',np.ones(N,dtype=bool))]
EDGES={}
for k in regnames:
    v=rowreg[k]; sel=base_ok&train_row&np.isfinite(v)
    if k=='LAUNCH60': sel=sel&cov
    qs=np.unique(np.quantile(v[sel],[i/10 for i in range(1,10)]))
    edges=[-np.inf]+list(qs)+[np.inf]; EDGES[k]=edges
    for b in range(len(edges)-1):
        m=np.isfinite(v)&(v>edges[b])&(v<=edges[b+1])
        if k=='LAUNCH60': m=m&cov
        CELLS.append(('%s_d%d'%(k,b+1),m))
hh=z['HOUR'][minute_idx]
for b in range(12): CELLS.append(('HOUR2_%d'%b,(hh>=b*2)&(hh<(b+1)*2)))
NCELL1=len(CELLS)
# 2-way tercile interactions
TERC={}
for k in regnames:
    v=rowreg[k]; sel=base_ok&train_row&np.isfinite(v)
    if k=='LAUNCH60': sel=sel&cov
    q=np.quantile(v[sel],[1/3,2/3])
    ms=[]
    for b,(a1,b1) in enumerate([(-np.inf,q[0]),(q[0],q[1]),(q[1],np.inf)]):
        m=np.isfinite(v)&(v>a1)&(v<=b1)
        if k=='LAUNCH60': m=m&cov
        ms.append(m)
    TERC[k]=ms
PAIRCELLS=[]
for k1,k2 in itertools.combinations(regnames,2):
    for i in range(3):
        for j in range(3):
            PAIRCELLS.append(('%s_t%d__%s_t%d'%(k1,i+1,k2,j+1), TERC[k1][i]&TERC[k2][j]))
P('cells stage1', NCELL1, 'paircells', len(PAIRCELLS))

ret5=z['ret5']; ret15=z['ret15']; dd=z['dd']; vsopen=z['vsopen']; agem=z['agem']
ENTRIES=[('ANY',np.ones(N,dtype=bool)),('R5UP',np.isfinite(ret5)&(ret5>0)),('R5DN',np.isfinite(ret5)&(ret5<=0)),
 ('R15UP10',np.isfinite(ret15)&(ret15>0.10)),('R15DN10',np.isfinite(ret15)&(ret15<-0.10)),
 ('DD30',np.isfinite(dd)&(dd<-0.30)),('NEARHI',np.isfinite(dd)&(dd>-0.10)),
 ('ABOVEOPEN',np.isfinite(vsopen)&(vsopen>0)),('BELOWOPEN',np.isfinite(vsopen)&(vsopen<=0)),
 ('YOUNG30',np.isfinite(agem)&(agem<30)),('OLD30',np.isfinite(agem)&(agem>=30))]
TOLL=0.0114; DC=-0.30
def simulate(rows,ei,pi):
    er=EROW[ei]; dr=DROP[ei]; g=GROSS[ei,pi]; dep=DEPLOY[ei,pi]
    per={}; cur=-1; block=-1; dead=False
    for r in rows:
        m=mid[r]
        if m!=cur: cur=m; block=-1; dead=False
        if dead or r<block: continue
        d=dep[r]
        if d<=0: continue
        if dr[r]: per.setdefault(m,[]).append(DC*d-TOLL*d); dead=True; continue
        gg=g[r]
        if not np.isfinite(gg): continue
        per.setdefault(m,[]).append(gg-TOLL*d); block=er[r]
    return per
def stats(per):
    if not per: return None
    ks=list(per.keys()); mm=np.array([np.mean(per[k]) for k in ks])
    return mm,float(mm.mean()),float(np.median(mm)),int(sum(len(per[k]) for k in ks)),len(ks)

ctrl={}
for tag,rm in (('tr',train_row),('va',val_row)):
    sel=np.flatnonzero(base_ok&rm)
    for ei in range(NEX):
        for pi in range(3): ctrl[(tag,ei,pi)]=stats(simulate(sel,ei,pi))
P('=== CONTROLS (ANY x ALL, P1) ===')
for ei in range(NEX):
    a=ctrl[('tr',ei,0)]; b=ctrl[('va',ei,0)]
    P(' %-18s train mean %.4f med %.4f n%d | val mean %.4f med %.4f n%d'%(EXN[ei],a[1],a[2],a[3],b[1],b[2],b[3]))

combos=0; trainpos=[]
t0=time.time()
def run(cells, exits, poss, tag):
    global combos
    for cname,cm in cells:
        for ename,em in ENTRIES:
            sel=np.flatnonzero(base_ok&train_row&cm&em)
            if len(sel)<40:
                combos+=len(exits)*len(poss); continue
            for ei in exits:
                for pi in poss:
                    combos+=1
                    s=stats(simulate(sel,ei,pi))
                    if s is None: continue
                    mm,mean,med,n,k=s
                    if n<40 or k<15: continue
                    c=ctrl[('tr',ei,pi)]
                    if mean>0 and mean>c[1]: trainpos.append((tag,cname,ename,ei,pi,mean,med,n,k))
run(CELLS, range(NEX), range(3), 'A')
P('stage A done combos %d trainpos %d  %.0fs'%(combos,len(trainpos),time.time()-t0))
run(PAIRCELLS, range(6), [0], 'B')
P('stage B done combos %d trainpos %d  %.0fs'%(combos,len(trainpos),time.time()-t0))

# ---- validate ----
CELLMAP=dict(CELLS); CELLMAP.update(dict(PAIRCELLS)); ENTMAP=dict(ENTRIES)
surv=[]
for tag,cname,ename,ei,pi,trm,trmed,trn,trk in trainpos:
    sel=np.flatnonzero(base_ok&val_row&CELLMAP[cname]&ENTMAP[ename])
    if len(sel)<40: continue
    s=stats(simulate(sel,ei,pi))
    if s is None: continue
    mm,mean,med,n,k=s
    if n<40 or k<15: continue
    c=ctrl[('va',ei,pi)]
    if mean<=0 or mean<=c[1]: continue
    if float(np.sort(mm)[:-1].mean())<=0: continue
    B=2000; bs=mm[rng.integers(0,len(mm),size=(B,len(mm)))].mean(axis=1)
    lo_=float(np.quantile(bs,0.05)); pg=float((bs>c[1]).mean())
    surv.append((tag,cname,ename,EXN[ei],pi+1,trm,trmed,trn,trk,mean,med,n,k,c[1],float(np.sort(mm)[:-1].mean()),lo_,pg))
P('validate survivors (mean>0, >ctrl, jackknife>0): %d'%len(surv))
surv.sort(key=lambda x:-x[15])
for s in surv[:50]:
    P('SURV2 %s %s | %s | %s | P%d || TR %.4f/%.4f n%d k%d || VA %.4f/%.4f n%d k%d || ctrl %.4f jack %.4f bootlo %.4f p %.3f'%s)
hard=[s for s in surv if s[15]>0 and s[15]>s[13] and s[16]>0.95]
P('HARD2: %d'%len(hard))
for s in hard[:40]:
    P('HARD2 %s %s | %s | %s | P%d va %.4f bootlo %.4f ctrl %.4f'%(s[0],s[1],s[2],s[3],s[4],s[9],s[15],s[13]))
P('TOTAL COMBOS SWEEP2 %d'%combos)
json.dump({'combos':combos,'trainpos':len(trainpos),'surv':len(surv),'hard':len(hard)},open(W+'sweep2_summary.json','w'))
LOG.close()
