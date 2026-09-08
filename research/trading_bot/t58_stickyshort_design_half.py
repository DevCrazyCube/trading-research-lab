import numpy as np, json
d=np.load('research/data/newterr_shortint/panels.npz',allow_pickle=True)
sym=d['symbols']; dates=d['dates']; op=d['open']; cl=d['close']; vol=d['vol']
si=d['si_pos']; settle=d['si_settle']; avail=d['si_avail_idx']; sv=d['sv_short']; isetf=d['is_etf']
sadv=d['si_adv']
nS,nT=si.shape; nD=len(dates)
settle_idx=np.searchsorted(dates,settle)   # session index of each settlement date
DESIGN_END=103   # settlement dates 1..103 -> python idx 0..102

rows=[]
def period(t):
    """returns dict for settlement index t (needs t-1 for window, t+1 for exit)"""
    if t<1 or t+1>=nT: return None
    a,b=settle_idx[t-1], settle_idx[t]          # flow window (a, b]
    if b<=a: return None
    e0=avail[t]+1; e1=avail[t+1]+1              # entry/exit session
    if e1>=nD or e0>=nD or e1<=e0: return None
    w_sv=sv[:,a+1:b+1]
    cum=np.nansum(w_sv,axis=1)
    nz=np.sum(np.isfinite(w_sv),axis=1)
    dsi=si[:,t]-si[:,t-1]
    px=cl[:,avail[t]]
    dv=np.nanmedian((cl[:,a+1:b+1]*vol[:,a+1:b+1]),axis=1)
    ok=(~isetf)&(cum>1e5)&(nz>=5)&(px>=5.0)&np.isfinite(px)&(dv>=1e6)&(dsi>0)&np.isfinite(dsi)
    r=op[:,e1]/op[:,e0]-1.0
    ok&=np.isfinite(r)&np.isfinite(op[:,e0])&(op[:,e0]>0)
    idx=np.where(ok)[0]
    if len(idx)<300: return {'t':t,'N':int(len(idx)),'skip':'K1'}
    str_=dsi[idx]/cum[idx]
    q=np.quantile(str_,[0.2,0.8])
    lo=idx[str_<=q[0]]; hi=idx[str_>=q[1]]
    if len(lo)<10 or len(hi)<10: return {'t':t,'N':int(len(idx)),'skip':'K1'}
    # subsumption proxy: days-to-cover (SI/ADV) sort on same universe
    dtc=(si[:,t]/np.maximum(sadv[:,t],1.0))[idx]
    qd=np.quantile(dtc,[0.2,0.8])
    dlo=idx[dtc<=qd[0]]; dhi=idx[dtc>=qd[1]]
    return {'t':t,'N':int(len(idx)),'date':str(settle[t]),
            'entry':str(dates[e0]),'exit':str(dates[e1]),
            'r_long':float(np.mean(r[lo])),'r_short':float(np.mean(r[hi])),
            'gross':float(np.mean(r[lo])-np.mean(r[hi])),
            'dtc_gross':float(np.mean(r[dhi])-np.mean(r[dlo])),  # published: short high-SI, long low-SI
            'lo':lo,'hi':hi,'nlo':len(lo),'nhi':len(hi)}

per=[period(t) for t in range(1,DESIGN_END)]
per=[p for p in per if p]
live=[p for p in per if 'skip' not in p]
skipped=[p for p in per if 'skip' in p]
print('design settlement periods attempted:',len(per),' usable:',len(live),' K1-breadth-skipped:',len(skipped))
if live: print('first usable:',live[0]['date'],' last:',live[-1]['date'])

# turnover-based costs
prev=None; nets=[]; turns=[]
for p in live:
    w={}
    for i in p['lo']: w[i]=0.5/p['nlo']
    for i in p['hi']: w[i]=w.get(i,0)-0.5/p['nhi']
    if prev is None:
        to=sum(abs(v) for v in w.values())
    else:
        keys=set(w)|set(prev)
        to=sum(abs(w.get(k,0)-prev.get(k,0)) for k in keys)
    prev=w
    cost=0.0010*to
    turns.append(to); nets.append(p['gross']-cost)
nets=np.array(nets); gross=np.array([p['gross'] for p in live]); dtcg=np.array([p['dtc_gross'] for p in live])
PY=26.0
def ann(x): return float(np.mean(x)*PY)
def boot(x,n=20000,seed=7):
    rng=np.random.default_rng(seed); m=[]
    for _ in range(n): m.append(np.mean(rng.choice(x,len(x),replace=True)))
    return float(np.percentile(m,5)),float(np.percentile(m,95))
res={
 'n_obs':int(len(nets)),
 'mean_turnover_per_period':float(np.mean(turns)),
 'gross_mean_per_period':float(np.mean(gross)),'gross_annualized':ann(gross),
 'net_mean_per_period':float(np.mean(nets)),'net_annualized':ann(nets),
 'net_sharpe_per_obs':float(np.mean(nets)/np.std(nets,ddof=1)) if len(nets)>1 else None,
 'net_sharpe_annualized':float(np.mean(nets)/np.std(nets,ddof=1)*np.sqrt(PY)) if len(nets)>1 else None,
 'net_ci90_per_period':boot(nets),
 'net_ci90_annualized':[boot(nets)[0]*PY,boot(nets)[1]*PY],
 'dtc_control_gross_annualized':ann(dtcg),
 'median_N':float(np.median([p['N'] for p in live])),
 'frac_periods_positive':float(np.mean(nets>0)),
}
print(json.dumps(res,indent=2))
json.dump({'summary':res,'periods':[{k:v for k,v in p.items() if k not in('lo','hi')} for p in live],
           'k1_skipped':[{'t':p['t'],'N':p['N']} for p in skipped]},
          open('research/trading_bot/T58_STICKYSHORT_DESIGN_HALF.json','w'),indent=1)
