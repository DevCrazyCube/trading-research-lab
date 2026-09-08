import json, numpy as np, time
W='/home/anont/meme/.regime1/'
LOG=open(W+'focus.txt','w')
def P(*a): print(*a,file=LOG); LOG.flush()
rng=np.random.default_rng(7)
z=np.load(W+'feats.npz'); meta=json.load(open(W+'meta.json'))
mint_slice={int(k):tuple(v) for k,v in meta['mint_slice'].items()}
names=meta['mint_names']
mid=z['mid']; ts=z['ts']; op=z['op']; hi=z['hi']; lo=z['lo']; cl=z['cl']; minute_idx=z['minute_idx']
last_of_mint=z['last_of_mint']; mint_h=z['mint_h']
N=len(ts); M=len(mint_h)
valid=~last_of_mint; entry_row=np.arange(N)+1
E0=np.where(valid, op[np.minimum(entry_row,N-1)], np.nan)

# horizon rows
def hrow(H):
    hr=np.full(N,-1,dtype=np.int64)
    for mi in range(M):
        s,e=mint_slice[mi]; t=ts[s:e]
        j=np.searchsorted(t,t+H*60,side='left')
        hr[s:e]=np.where(j<(e-s), j+s, -1)
    return hr
HR={60:hrow(60),120:hrow(120)}

def build_trail(H,TR,fill):
    """fill: 'trigger' | 'slip5' | 'slip15' | 'low' (fill at the triggering bar's low)"""
    hr=HR[H]; epx=np.full(N,np.nan); er=np.full(N,-1,dtype=np.int64)
    for r in range(N):
        if last_of_mint[r]: continue
        e0=r+1; E=op[e0]; j=hr[e0]
        stop = j if j>=0 else mint_slice[mid[r]][1]
        peak=E; px=None; xr=-1
        for k in range(e0,stop):
            trig=peak*(1-TR)
            if lo[k]<=trig:
                if fill=='trigger': px=trig
                elif fill=='slip5': px=trig*0.95
                elif fill=='slip15': px=trig*0.85
                else: px=lo[k]
                xr=k; break
            if hi[k]>peak: peak=hi[k]
        if px is None and j>=0:
            px=op[j]; xr=j
        if px is not None: epx[r]=px; er[r]=xr
    return epx,er

TOLL=0.0114
def sim(rows, epx, er, dropcharge=-0.30, toll=TOLL):
    per={}; cur=-1; block=-1; dead=False
    for r in rows:
        m=mid[r]
        if m!=cur: cur=m; block=-1; dead=False
        if dead or r<block: continue
        if not np.isfinite(epx[r]):
            per.setdefault(m,[]).append(dropcharge-toll); dead=True; continue
        per.setdefault(m,[]).append(epx[r]/E0[r]-1.0-toll); block=er[r]
    return per
def mstat(per):
    if not per: return None,None,0,0
    ks=list(per.keys()); mm=np.array([np.mean(per[k]) for k in ks])
    return mm, ks, int(sum(len(per[k]) for k in ks)), len(ks)

train_row=(mint_h[mid]==1); val_row=(mint_h[mid]==2); base_ok=valid & np.isfinite(E0)
agem=z['agem']; dd=z['dd']
YOUNG30=np.isfinite(agem)&(agem<30); OLD30=np.isfinite(agem)&(agem>=30)
ANY=np.ones(N,dtype=bool)

P('=== 1. TRAILING FILL REALISM (validate, YOUNG30 vs ANY vs OLD30) ===')
STRUCTS={}
for H,TR in ((60,0.25),(120,0.35)):
    for fill in ('trigger','slip5','slip15','low'):
        epx,er=build_trail(H,TR,fill)
        STRUCTS[(H,TR,fill)]=(epx,er)
        line=[]
        for nm,em in (('ANY',ANY),('YOUNG30',YOUNG30),('OLD30',OLD30)):
            rows=np.flatnonzero(base_ok & val_row & em)
            mm,ks,n,k=mstat(sim(rows,epx,er))
            jack=float(np.sort(mm)[:-3].mean()) if k>3 else float('nan')
            line.append('%s mean %.4f med %.4f jack-3 %.4f n%d k%d'%(nm,mm.mean(),np.median(mm),jack,n,k))
        P('T%d_TR%d fill=%-7s :: %s'%(H,TR*100,fill,' | '.join(line)))

P('')
P('=== 2. YOUNG30 minus ANY, paired cluster bootstrap over mints (validate, trigger fill) ===')
for H,TR in ((60,0.25),(120,0.35)):
    epx,er=STRUCTS[(H,TR,'trigger')]
    pa=sim(np.flatnonzero(base_ok & val_row & ANY),epx,er)
    py=sim(np.flatnonzero(base_ok & val_row & YOUNG30),epx,er)
    common=sorted(set(pa)&set(py))
    da=np.array([np.mean(py[m])-np.mean(pa[m]) for m in common])
    B=5000; bi=rng.integers(0,len(da),size=(B,len(da))); bs=da[bi].mean(axis=1)
    P('T%d_TR%d paired delta mean %.4f  boot5%% %.4f  boot95%% %.4f  p(delta>0) %.3f  k=%d'%(
        H,TR*100,da.mean(),np.quantile(bs,0.05),np.quantile(bs,0.95),(bs>0).mean(),len(da)))
    P('   delta median %.4f ; delta mean excl top3 %.4f'%(np.median(da), np.sort(da)[:-3].mean()))

P('')
P('=== 3. REGIME MARGINAL VALUE: circular-rotation null ===')
P('Baseline = YOUNG30 x ALL x exit, validate. For each regime cell we rotate the')
P('per-minute regime series circularly (preserving its autocorrelation and cell size)')
P('and ask how often a rotated cell beats the observed cell mean.')
regnames=['LAUNCH60','COHVOL15','ACTCNT','FRACUP','MEDRET15','MEDRET60','YOUNGFRAC','NEWL60']
NMIN=len(z['LAUNCH60'])
rowmin=minute_idx
cov=z['CREATE_COV']
# rebuild train-quantile cells at minute resolution
cellmin={}
for k in regnames:
    v=z[k]; rv=v[rowmin]
    sel=base_ok & train_row & np.isfinite(rv)
    if k=='LAUNCH60': sel=sel & cov[rowmin]
    qs=np.unique(np.quantile(rv[sel],[0.2,0.4,0.6,0.8]))
    edges=[-np.inf]+list(qs)+[np.inf]
    for b in range(len(edges)-1):
        m=np.isfinite(v)&(v>edges[b])&(v<=edges[b+1])
        if k=='LAUNCH60': m=m&cov
        cellmin['%s_q%d'%(k,b+1)]=m
for b in range(6):
    hh=z['HOUR']; cellmin['HOUR_b%d'%b]=(hh>=b*4)&(hh<(b+1)*4)

NROT=400
for H,TR in ((60,0.25),(120,0.35)):
    epx,er=STRUCTS[(H,TR,'trigger')]
    base_rows=np.flatnonzero(base_ok & val_row & YOUNG30)
    mm,ks,n,k=mstat(sim(base_rows,epx,er))
    basemean=mm.mean()
    P('--- T%d_TR%d baseline YOUNG30xALL validate mean %.4f n%d k%d'%(H,TR*100,basemean,n,k))
    res=[]
    for cname,cm in cellmin.items():
        rows=np.flatnonzero(base_ok & val_row & YOUNG30 & cm[rowmin])
        if len(rows)<40: continue
        mm2,_,n2,k2=mstat(sim(rows,epx,er))
        if mm2 is None or k2<15: continue
        obs=mm2.mean()
        # rotation null
        null=[]
        for _ in range(NROT):
            off=int(rng.integers(1,NMIN))
            cmr=np.roll(cm,off)
            rr=np.flatnonzero(base_ok & val_row & YOUNG30 & cmr[rowmin])
            if len(rr)<40: continue
            m3,_,_,k3=mstat(sim(rr,epx,er))
            if m3 is None or k3<15: continue
            null.append(m3.mean())
        null=np.array(null)
        p=float((null>=obs).mean()) if len(null)>20 else float('nan')
        res.append((p,cname,obs,n2,k2,float(np.median(null)),len(null)))
    res.sort()
    for p,cname,obs,n2,k2,nm_,ln in res:
        P('  %-16s obs %.4f  n%d k%d  rot-null median %.4f  p_rot %.3f (%d rots)'%(cname,obs,n2,k2,nm_,p,ln))
LOG.close()
