import json, numpy as np, time
W='/home/anont/meme/.regime1/'
LOG=open(W+'validate.txt','w')
def P(*a): print(*a,file=LOG); LOG.flush()
rng=np.random.default_rng(20260904)

z=np.load(W+'feats.npz'); EX=np.load(W+'exits.npz'); EPX=EX['EPX']; EROW=EX['EROW']
EXITS=json.load(open(W+'exits.json')); meta=json.load(open(W+'meta.json'))
mint_slice={int(k):tuple(v) for k,v in meta['mint_slice'].items()}
mid=z['mid']; ts=z['ts']; op=z['op']; minute_idx=z['minute_idx']
last_of_mint=z['last_of_mint']; mint_h=z['mint_h']
N=len(ts); M=len(mint_h); NEX=len(EXITS)
valid=~last_of_mint
entry_row=np.arange(N)+1
E0=np.where(valid, op[np.minimum(entry_row,N-1)], np.nan)
add_ok=np.zeros(N,dtype=bool); E1=np.full(N,np.nan)
for mi in range(M):
    s,e=mint_slice[mi]
    for r in range(s,e-2):
        add_ok[r]=True; E1[r]=op[r+2]
GROSS=np.full((NEX,3,N),np.nan); DEPLOY=np.zeros((NEX,3,N)); DROP=np.zeros((NEX,N),dtype=bool)
for ei in range(NEX):
    X=EPX[ei]; er=EROW[ei]
    ok=valid & np.isfinite(E0); isdrop=ok & ~np.isfinite(X); DROP[ei]=isdrop
    res=ok & np.isfinite(X); addr=entry_row+1
    can_add=add_ok & ((~res)|(addr<=np.where(er>=0,er,N)))
    up=can_add & np.isfinite(E1) & (E1>E0)
    for pi in range(3):
        if pi==0:
            DEPLOY[ei,pi]=np.where(ok,1.0,0.0); GROSS[ei,pi]=np.where(res,X/E0-1.0,np.nan)
        else:
            a=(can_add & np.isfinite(E1)) if pi==1 else up
            DEPLOY[ei,pi]=np.where(ok,np.where(a,1.0,0.5),0.0)
            GROSS[ei,pi]=np.where(res,np.where(a,0.5*X/E0+0.5*X/E1-1.0,0.5*X/E0-0.5),np.nan)

regnames=['LAUNCH60','COHVOL15','ACTCNT','FRACUP','MEDRET15','MEDRET60','YOUNGFRAC','NEWL60']
rowreg={k:z[k][minute_idx] for k in regnames}
rowhour=z['HOUR'][minute_idx]; rowcov=z['CREATE_COV'][minute_idx]
train_row=(mint_h[mid]==1); val_row=(mint_h[mid]==2); base_ok=valid & np.isfinite(E0)
CELLS={'ALL':np.ones(N,dtype=bool)}
CDESC={'ALL':'no regime condition'}
NBIN=5
for k in regnames:
    v=rowreg[k]; sel=base_ok & train_row & np.isfinite(v)
    if k=='LAUNCH60': sel=sel & rowcov
    qs=np.unique(np.quantile(v[sel],[i/NBIN for i in range(1,NBIN)]))
    edges=[-np.inf]+list(qs)+[np.inf]
    for b in range(len(edges)-1):
        m=np.isfinite(v)&(v>edges[b])&(v<=edges[b+1])
        if k=='LAUNCH60': m=m&rowcov
        CELLS['%s_q%d'%(k,b+1)]=m
        CDESC['%s_q%d'%(k,b+1)]='%s in (%.4g, %.4g]'%(k,edges[b],edges[b+1])
for b in range(6):
    CELLS['HOUR_b%d'%b]=(rowhour>=b*4)&(rowhour<(b+1)*4)
    CDESC['HOUR_b%d'%b]='UTC hour in [%d,%d)'%(b*4,(b+1)*4)
ret5=z['ret5']; ret15=z['ret15']; dd=z['dd']; vsopen=z['vsopen']; agem=z['agem']
ENT={'ANY':np.ones(N,dtype=bool),'R5UP':np.isfinite(ret5)&(ret5>0),'R5DN':np.isfinite(ret5)&(ret5<=0),
 'R15UP10':np.isfinite(ret15)&(ret15>0.10),'R15DN10':np.isfinite(ret15)&(ret15<-0.10),
 'DD30':np.isfinite(dd)&(dd<-0.30),'NEARHI':np.isfinite(dd)&(dd>-0.10),
 'ABOVEOPEN':np.isfinite(vsopen)&(vsopen>0),'BELOWOPEN':np.isfinite(vsopen)&(vsopen<=0),
 'YOUNG30':np.isfinite(agem)&(agem<30),'OLD30':np.isfinite(agem)&(agem>=30)}
EDESC={'ANY':'any bar','R5UP':'prior 5m return > 0','R5DN':'prior 5m return <= 0',
 'R15UP10':'prior 15m return > +10%','R15DN10':'prior 15m return < -10%',
 'DD30':'>=30% below running high','NEARHI':'within 10% of running high',
 'ABOVEOPEN':'close > first-bar open','BELOWOPEN':'close <= first-bar open',
 'YOUNG30':'mint age < 30 min','OLD30':'mint age >= 30 min'}

TOLL=0.0114
def simulate(rows, ei, pi, dropcharge=-0.30, toll=TOLL, ret_rows=False):
    er=EROW[ei]; dr=DROP[ei]; g=GROSS[ei,pi]; dep=DEPLOY[ei,pi]
    per={}; rr={}
    cur=-1; block=-1; dead=False
    for r in rows:
        m=mid[r]
        if m!=cur: cur=m; block=-1; dead=False
        if dead or r<block: continue
        d=dep[r]
        if d<=0: continue
        if dr[r]:
            per.setdefault(m,[]).append(dropcharge*d-toll*d); rr.setdefault(m,[]).append(r); dead=True; continue
        gg=g[r]
        if not np.isfinite(gg): continue
        per.setdefault(m,[]).append(gg-toll*d); rr.setdefault(m,[]).append(r); block=er[r]
    return (per,rr) if ret_rows else per

def stats(per):
    if not per: return None
    ks=list(per.keys()); mm=np.array([np.mean(per[k]) for k in ks])
    return dict(mean=float(mm.mean()), median=float(np.median(mm)), n=int(sum(len(per[k]) for k in ks)),
                k=len(ks), mm=mm, ks=ks)

def resolution(rows, ei):
    dr=DROP[ei]; tot=0; res=0
    for r in rows:
        tot+=1; res+= 0 if dr[r] else 1
    return res/max(tot,1)

# controls
ctrl={}
for tag,rm in (('tr',train_row),('va',val_row)):
    sel=np.flatnonzero(base_ok & rm)
    for ei in range(NEX):
        for pi in range(3):
            ctrl[(tag,ei,pi)]=stats(simulate(sel,ei,pi))

trainpos=json.load(open(W+'trainpos.json'))
P('train positives to validate', len(trainpos))
tmid=(ts.min()+ts.max())//2

surv=[]
t0=time.time()
for idx,(cname,ename,ei,pi,trmean,trmed,trn,trk,trctrl) in enumerate(trainpos):
    cm=CELLS[cname]; em=ENT[ename]
    sel=np.flatnonzero(base_ok & val_row & cm & em)
    if len(sel)<40: continue
    per,rws=simulate(sel,ei,pi,ret_rows=True)
    s=stats(per)
    if s is None or s['n']<40 or s['k']<15: continue
    c=ctrl[('va',ei,pi)]
    if s['mean']<=0: continue
    if s['mean']<=c['mean']: continue
    mm=s['mm']
    # jackknife: drop best mint
    if len(mm)>1 and float(np.sort(mm)[:-1].mean())<=0: continue
    # cluster bootstrap over mints
    B=2000
    bi=rng.integers(0,len(mm),size=(B,len(mm)))
    bs=mm[bi].mean(axis=1)
    lo=float(np.quantile(bs,0.05))
    p_gt_ctrl=float((bs>c['mean']).mean())
    surv.append(dict(cell=cname,ent=ename,ei=ei,pi=pi,tr_mean=trmean,tr_med=trmed,tr_n=trn,tr_k=trk,
        va_mean=s['mean'],va_med=s['median'],va_n=s['n'],va_k=s['k'],ctrl=c['mean'],ctrl_med=c['median'],
        jack=float(np.sort(mm)[:-1].mean()),boot_lo=lo,p_gt_ctrl=p_gt_ctrl,
        res=resolution(sel,ei),rows=rws))
P('passed mean>0, mean>ctrl, jackknife: %d  (%.1fs)'%(len(surv),time.time()-t0))

surv.sort(key=lambda d:-d['boot_lo'])
for d in surv[:80]:
    P('SURV %s | %s | %s | P%d || TR mean %.4f med %.4f n%d k%d || VA mean %.4f med %.4f n%d k%d || ctrl %.4f/%.4f jack %.4f bootlo %.4f p %.3f res %.3f'%(
        d['cell'],d['ent'],EXITS[d['ei']]['name'],d['pi']+1,d['tr_mean'],d['tr_med'],d['tr_n'],d['tr_k'],
        d['va_mean'],d['va_med'],d['va_n'],d['va_k'],d['ctrl'],d['ctrl_med'],d['jack'],d['boot_lo'],d['p_gt_ctrl'],d['res']))

# hard gate
hard=[d for d in surv if d['boot_lo']>d['ctrl'] and d['boot_lo']>0 and d['p_gt_ctrl']>0.95]
P('HARD GATE (boot 5th pct > 0 and > control, p>0.95):', len(hard))
for d in hard:
    P('HARD %s | %s | %s | P%d va_mean %.4f bootlo %.4f ctrl %.4f'%(d['cell'],d['ent'],EXITS[d['ei']]['name'],d['pi']+1,d['va_mean'],d['boot_lo'],d['ctrl']))

# time-stability for the hard set (and top 20 soft)
def timesplit(d):
    out=[]
    for half in (0,1):
        per={}
        for m,rs in d['rows'].items():
            keep=[r for r in rs if (ts[r]<tmid)==(half==0)]
            if keep: per[m]=[None]*0
        # recompute properly
        sel=np.flatnonzero(base_ok & val_row & CELLS[d['cell']] & ENT[d['ent']] & ((ts<tmid) if half==0 else (ts>=tmid)))
        s=stats(simulate(sel,d['ei'],d['pi']))
        out.append(s)
    return out
for d in (hard if hard else surv[:15]):
    a,b=timesplit(d)
    P('TIMESPLIT %s|%s|%s|P%d  h1 %s  h2 %s'%(d['cell'],d['ent'],EXITS[d['ei']]['name'],d['pi']+1,
        ('mean %.4f n%d k%d'%(a['mean'],a['n'],a['k'])) if a else 'none',
        ('mean %.4f n%d k%d'%(b['mean'],b['n'],b['k'])) if b else 'none'))

json.dump([{k:v for k,v in d.items() if k!='rows'} for d in surv], open(W+'surv.json','w'), default=float)
json.dump({'hard':[{k:v for k,v in d.items() if k!='rows'} for d in hard]}, open(W+'hard.json','w'), default=float)
# dropout sensitivity + toll sensitivity for hard set
for d in (hard if hard else surv[:10]):
    sel=np.flatnonzero(base_ok & val_row & CELLS[d['cell']] & ENT[d['ent']])
    line=[]
    for dc in (-0.30,-0.50,-1.00):
        for tl in (0.0114,0.025):
            s=stats(simulate(sel,d['ei'],d['pi'],dropcharge=dc,toll=tl))
            line.append('drop%.0f toll%.3f mean %.4f med %.4f'%(dc*100,tl,s['mean'],s['median']))
    P('SENS %s|%s|%s|P%d :: %s'%(d['cell'],d['ent'],EXITS[d['ei']]['name'],d['pi']+1,' | '.join(line)))
LOG.close()
