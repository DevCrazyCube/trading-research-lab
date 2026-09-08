import json, numpy as np
W='/home/anont/meme/.regime1/'
LOG=open(W+'final.txt','w')
def P(*a): print(*a,file=LOG); LOG.flush()
rng=np.random.default_rng(3)
z=np.load(W+'feats.npz'); meta=json.load(open(W+'meta.json'))
mint_slice={int(k):tuple(v) for k,v in meta['mint_slice'].items()}
mid=z['mid']; ts=z['ts']; op=z['op']; hi=z['hi']; lo=z['lo']
last_of_mint=z['last_of_mint']; mint_h=z['mint_h']; minute_idx=z['minute_idx']
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
        j=np.searchsorted(t,t+H*60,side='left'); hr[s:e]=np.where(j<(e-s), j+s,-1)
    return hr
HORIZ=[5,10,15,30,60,120]; HR={H:hrow(H) for H in HORIZ}
TOLL=0.0114
def sim_time(rows,H,DC=-0.30,toll=TOLL):
    hr=HR[H]; per={}; cur=-1; block=-1; dead=False
    for r in rows:
        m=mid[r]
        if m!=cur: cur=m; block=-1; dead=False
        if dead or r<block: continue
        j=hr[r+1]
        if j<0: per.setdefault(m,[]).append(DC-toll); dead=True; continue
        per.setdefault(m,[]).append(op[j]/E0[r]-1.0-toll); block=j
    return per
def st(per):
    ks=list(per.keys()); mm=np.array([np.mean(per[k]) for k in ks])
    return mm,float(mm.mean()),float(np.median(mm)),int(sum(len(per[k]) for k in ks)),len(ks)
agem=z['agem']
base_ok=valid&np.isfinite(E0); tr=(mint_h[mid]==1); va=(mint_h[mid]==2)
Y=np.isfinite(agem)&(agem<30); O=np.isfinite(agem)&(agem>=30); A=np.ones(N,dtype=bool)
P('=== TIME-ONLY EXITS (no fill assumption at all), mint-equal, drop -30%%, toll 1.14%% ===')
P('%-6s %-9s %-38s %s'%('exit','entry','TRAIN mean/med/jack-3 n k','VALIDATE mean/med/jack-3 n k'))
for H in HORIZ:
    for nm,em in (('ANY',A),('YOUNG30',Y),('OLD30',O)):
        out=[]
        for rm in (tr,va):
            mm,me,md,n,k=st(sim_time(np.flatnonzero(base_ok&rm&em),H))
            j=float(np.sort(mm)[:-3].mean())
            out.append('%.4f / %.4f / %.4f  n%-5d k%-4d'%(me,md,j,n,k))
        P('T%-5d %-9s %s   %s'%(H,nm,out[0],out[1]))
P('')
P('=== best-of-sweep2 rule under every trailing fill model (VALIDATE, P3 half+add-on-strength) ===')
def build_trail(H,TR,fill):
    hrr=HR[H]; epx=np.full(N,np.nan); er=np.full(N,-1,dtype=np.int64)
    for r in range(N):
        if last_of_mint[r]: continue
        e0=r+1; E=op[e0]; j=hrr[e0]; stop=j if j>=0 else mint_slice[mid[r]][1]
        peak=E; px=None; xr=-1
        for k in range(e0,stop):
            t_=peak*(1-TR)
            if lo[k]<=t_:
                px = t_ if fill=='trigger' else (t_*(1-fill) if isinstance(fill,float) else lo[k]); xr=k; break
            if hi[k]>peak: peak=hi[k]
        if px is None and j>=0: px=op[j]; xr=j
        if px is not None: epx[r]=px; er[r]=xr
    return epx,er
def sim_p3(rows,epx,er,DC=-0.30,toll=TOLL):
    per={}; cur=-1; block=-1; dead=False
    for r in rows:
        m=mid[r]
        if m!=cur: cur=m; block=-1; dead=False
        if dead or r<block: continue
        a = add_ok[r] and np.isfinite(E1[r]) and (E1[r]>E0[r]) and ((not np.isfinite(epx[r])) or (r+2)<=er[r])
        dep=1.0 if a else 0.5
        if not np.isfinite(epx[r]):
            per.setdefault(m,[]).append(DC*dep-toll*dep); dead=True; continue
        X=epx[r]
        g=(0.5*X/E0[r]+0.5*X/E1[r]-1.0) if a else (0.5*X/E0[r]-0.5)
        per.setdefault(m,[]).append(g-toll*dep); block=er[r]
    return per
for fill in ('trigger',0.05,0.15,0.30,'low'):
    epx,er=build_trail(60,0.25,fill)
    row=[]
    for nm,em in (('ANY',A),('YOUNG30',Y)):
        mm,me,md,n,k=st(sim_p3(np.flatnonzero(base_ok&va&em),epx,er))
        row.append('%s mean %.4f med %.4f jack-3 %.4f'%(nm,me,md,float(np.sort(mm)[:-3].mean())))
    P('  fill=%-8s %s | %s'%(str(fill),row[0],row[1]))
P('')
P('=== the one hard-gate survivor, full sensitivity (ALL x YOUNG30 x T60_TR25_slip15 x P3) ===')
epx,er=build_trail(60,0.25,0.15)
for DC in (-0.30,-0.50,-1.00):
    for tl in (0.0114,0.025):
        mm,me,md,n,k=st(sim_p3(np.flatnonzero(base_ok&va&Y),epx,er,DC=DC,toll=tl))
        B=4000; bs=mm[rng.integers(0,len(mm),size=(B,len(mm)))].mean(axis=1)
        P('  drop %.0f%% toll %.2f%%: mean %.4f med %.4f boot5%% %.4f n%d k%d'%(DC*100,tl*100,me,md,float(np.quantile(bs,0.05)),n,k))
LOG.close()
