import sys,json,pickle; sys.path.insert(0,'/home/anont/meme/.fc3')
import numpy as np
exec(open('/home/anont/meme/.fc3/b10_stress.py').read().split("CAND={")[0])
L=[]
def mk(a0,a1,v0t,pri0=True):
    return lambda f,i,d: (a0<=f['age'][i]<a1) and f['v0']>=v0t and (f['pri']==0 if pri0 else True)
def matched_random(cond,H,tp,sl,split,ndraw=25,seed=11,fill='base'):
    """same mints, same #entries per mint, random bars."""
    rng=np.random.default_rng(seed)
    # count entries per mint under cond
    cnt={}
    for m in mints:
        d=D[m]
        if split=='train' and d['h']!=1: continue
        if split=='validate' and d['h']!=2: continue
        n=len(d['ts'])
        if n<3: continue
        f=features(d)
        c=sum(1 for i in range(1,n-1) if cond(f,i,d))
        if c: cnt[m]=c
    vals=[]
    for s in range(ndraw):
        picks={}
        for m,c in cnt.items():
            n=len(D[m]['ts'])
            picks[m]=set(rng.choice(np.arange(1,n-1),size=min(c,n-2),replace=False).tolist())
        cnd=lambda f,i,d,_p=picks: i in _p.get(d['_m'],())
        for m in cnt: D[m]['_m']=m
        for m in mints: D[m]['_m']=m
        r=backtest(cnd,H,tp,sl,'all',split,fill=fill)
        if r: vals.append(r['mean'])
    return float(np.mean(vals)),float(np.std(vals)),len(vals)

CANDS=[
 ('E_sel   age30-60 v0>=5040 pri=0  H=30 SL=-25%', mk(30,60,5040), 30, None, -0.25),
 ('E_nostop age30-60 v0>=5040 pri=0 H=30 no-exit-truncation', mk(30,60,5040), 30, None, None),
 ('E_wide  age20-60 v0>=5040 pri=0  H=30 no-trunc', mk(20,60,5040), 30, None, None),
 ('E_early age0-30  v0>=5040 pri=0  H=60 no-trunc', mk(0,30,5040), 60, None, None),
 ('E_noPri age30-60 v0>=5040 anycre H=30 no-trunc', mk(30,60,5040,False), 30, None, None),
 ('E_allv0 age30-60 anyv0   pri=0  H=30 no-trunc', mk(30,60,0), 30, None, None),
]
for name,cond,H,tp,sl in CANDS:
    L.append('=== %s ==='%name)
    for split in ('train','validate'):
        for fill in (['base'] if sl is None else ['base','close','low']):
            r=backtest(cond,H,tp,sl,'all',split,fill=fill)
            if r is None: L.append('  %s %s: none'%(split,fill)); continue
            L.append('  %-8s fill=%-5s mean=%+.4f cilo5=%+.4f cilo10=%+.4f medmint=%+.4f fracpos=%.2f ex-top1=%+.4f n=%4d k=%3d res=%.2f'%(
                split,fill,r['mean'],blo(r['pm']),blo(r['pm'],q=0.10),r['med_mint'],r['frac_pos'],r['mean_ex1'],r['n'],r['k'],r['res']))
    r=backtest(cond,H,tp,sl,'all','validate',toll=0.025)
    if r: L.append('  validate toll=2.5%%          mean=%+.4f'%r['mean'])
    for ch in (-0.50,-1.00):
        r=backtest(cond,H,tp,sl,'all','validate',charge=ch)
        if r: L.append('  validate dropcharge=%-5.2f    mean=%+.4f'%(ch,r['mean']))
    r=backtest(cond,H,tp,sl,'all','validate',cap=1.0)
    if r: L.append('  validate cap=+100%%           mean=%+.4f cilo=%+.4f'%(r['mean'],blo(r['pm'])))
    r=backtest(cond,H,tp,sl,'all','validate',cap=0.5)
    if r: L.append('  validate cap=+50%%            mean=%+.4f cilo=%+.4f'%(r['mean'],blo(r['pm'])))
    cm,cs,nd=matched_random(cond,H,tp,sl,'validate')
    L.append('  MATCHED-RANDOM validate      mean=%+.4f (sd %.4f, %d draws)'%(cm,cs,nd))
    cmt,cst,_=matched_random(cond,H,tp,sl,'train')
    L.append('  MATCHED-RANDOM train         mean=%+.4f (sd %.4f)'%(cmt,cst))
open(SP+'/b12.log','w').write('\n'.join(L))
