import sys,json,pickle; sys.path.insert(0,'/home/anont/meme/.fc3')
import numpy as np
SP='/home/anont/meme/.fc3'
D=pickle.load(open(SP+'/mm.pkl','rb')); mints=sorted(D.keys())
CAP=9.0

def features(d):
    ts=d['ts']; o=d['o']; hi=d['hi']; lo=d['lo']; cl=d['cl']; vo=d['vo']
    n=len(ts); rm=np.maximum.accumulate(hi); cv=np.cumsum(vo)
    age=(ts-d['create_t'])/60.0
    dd=cl/np.maximum(rm,1e-300); lvl=cl/max(o[0],1e-300)
    mv=cv/np.arange(1,n+1); rv=vo/np.maximum(mv,1e-300)
    return dict(age=age,dd=dd,lvl=lvl,rv=rv,pri=d['pri'],prig=d['prig'],v0=vo[0])

def backtest(cond,H,tp,sl,mode='all',split='validate',toll=0.0114,charge=-0.30,
             fill='base',entry_slip=0.0,cap=CAP,exclude=None):
    permint=[]; ntr=0; nres=0; contrib=[]
    for m in mints:
        d=D[m]
        if split=='train' and d['h']!=1: continue
        if split=='validate' and d['h']!=2: continue
        if exclude and m==exclude: continue
        ts=d['ts']; o=d['o']; hi=d['hi']; lo=d['lo']; cl=d['cl']
        n=len(ts)
        if n<3: continue
        f=features(d)
        free=-1; tr=[]
        for i in range(1,n-1):
            if not cond(f,i,d): continue
            e=i+1
            if ts[e]<free: continue
            ep=o[e]*(1.0+entry_slip)
            if not np.isfinite(ep) or ep<=0: continue
            jj=int(np.searchsorted(ts,ts[e]+H*60,'left'))
            if jj<=e: jj=e+1
            has=jj<n
            wend=jj if has else n
            tp_px=ep*(1+tp) if tp is not None else None
            sl_px=ep*(1+sl) if sl is not None else None
            exit_px=None; exit_t=None
            for b in range(e,wend):
                hit_sl = sl_px is not None and lo[b]<=sl_px
                hit_tp = tp_px is not None and hi[b]>=tp_px
                if hit_sl:
                    if fill=='base': px=sl_px
                    elif fill=='close': px=min(sl_px, cl[b])
                    elif fill=='low': px=lo[b]
                    elif fill=='slip5': px=min(sl_px*0.95, o[b] if o[b]<sl_px else sl_px*0.95)
                    else: px=sl_px
                    exit_px=px; exit_t=ts[b]; break
                if hit_tp:
                    px=tp_px*(0.97 if fill=='slip5' else 1.0)
                    exit_px=px; exit_t=ts[b]; break
            if exit_px is None:
                if has:
                    exit_px=o[jj]; exit_t=ts[jj]
                else:
                    exit_px=None; exit_t=ts[-1]
            if exit_px is None:
                net=(1+charge)*(1-toll)-1
            else:
                g=exit_px/ep-1.0
                if cap is not None and g>cap: g=cap
                net=(1+g)*(1-toll)-1; nres+=1
            ntr+=1; tr.append(net); free=exit_t
            if mode=='first': break
        if tr:
            permint.append((m,float(np.mean(tr))))
    if not permint: return None
    pm=np.array([x[1] for x in permint])
    o_=np.argsort(pm)[::-1]
    return dict(mean=float(pm.mean()),med_mint=float(np.median(pm)),k=len(pm),n=ntr,
                res=nres/max(ntr,1),pm=pm,top=permint[o_[0]][0],
                mean_ex1=float(pm[o_[1:]].mean()) if len(pm)>1 else None,
                frac_pos=float((pm>0).mean()))
def blo(pm,B=2000,seed=5,q=0.05):
    rng=np.random.default_rng(seed); n=len(pm)
    return float(np.quantile(pm[rng.integers(0,n,size=(B,n))].mean(axis=1),q))

CAND={
 'A_lvl3_atATH_lowrv':   (lambda f,i,d: f['dd'][i]>=0.9 and f['lvl'][i]>=3 and 0.02<=f['rv'][i]<0.2, 30, 0.40,-0.25,'all'),
 'B_lvl3_lowrv_H120':    (lambda f,i,d: f['lvl'][i]>=3 and 0.02<=f['rv'][i]<0.2, 120, 0.40,-0.25,'all'),
 'C_age3_10_atATH':      (lambda f,i,d: 3<=f['age'][i]<10 and f['dd'][i]>=0.9, 60, 1.00,-0.25,'all'),
 'D_age10_20_stoponly':  (lambda f,i,d: 10<=f['age'][i]<20, 15, None,-0.25,'all'),
 'E_age30_60_v0hi_new':  (lambda f,i,d: 30<=f['age'][i]<60 and f['v0']>=5040 and f['pri']==0, 30, None,-0.25,'all'),
 'F_age6_10_v0hi':       (lambda f,i,d: 6<=f['age'][i]<10 and f['v0']>=5040 and f['prig']==0, 60, 1.00,-0.25,'all'),
 'G_age1_3_v0hi_tp15':   (lambda f,i,d: 1<=f['age'][i]<3 and f['v0']>=5040 and f['prig']==0, 60, 0.15,-0.25,'all'),
 'H_age10_20_v0hi_tp100':(lambda f,i,d: 10<=f['age'][i]<20 and f['v0']>=5040 and f['pri']==0, 60, 1.00,-0.25,'all'),
}
L=[]
for name,(cond,H,tp,sl,mode) in CAND.items():
    L.append('=== %s  H=%d tp=%s sl=%s %s ==='%(name,H,tp,sl,mode))
    for split in ('train','validate'):
        r=backtest(cond,H,tp,sl,mode,split)
        if r is None: L.append('  %s: none'%split); continue
        L.append('  %-8s base      mean=%+.4f cilo=%+.4f medmint=%+.4f n=%4d k=%3d res=%.2f fracpos=%.2f ex-top1=%+.4f'%(
            split,r['mean'],blo(r['pm']),r['med_mint'],r['n'],r['k'],r['res'],r['frac_pos'],r['mean_ex1']))
    for fill in ('close','low','slip5'):
        r=backtest(cond,H,tp,sl,mode,'validate',fill=fill)
        if r: L.append('  validate fill=%-6s mean=%+.4f cilo=%+.4f n=%4d k=%3d'%(fill,r['mean'],blo(r['pm']),r['n'],r['k']))
    r=backtest(cond,H,tp,sl,mode,'validate',fill='slip5',entry_slip=0.02,toll=0.025,charge=-0.50)
    if r: L.append('  validate WORST(entry+2%%,slip5,toll2.5%%,drop-50%%) mean=%+.4f cilo=%+.4f n=%4d k=%3d'%(r['mean'],blo(r['pm']),r['n'],r['k']))
    r=backtest(cond,H,tp,sl,mode,'validate',charge=-1.00)
    if r: L.append('  validate drop=-100%%  mean=%+.4f'%r['mean'])
    r=backtest(cond,H,tp,sl,mode,'validate',cap=1.0)
    if r: L.append('  validate cap=+100%%   mean=%+.4f cilo=%+.4f'%(r['mean'],blo(r['pm'])))
open(SP+'/b10.log','w').write('\n'.join(L))
