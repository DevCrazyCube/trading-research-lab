#!/usr/bin/env python3
"""What the operator ACTUALLY books: outright P&L, no cross-sectional benchmark.
Plus the Holm-relevant p-values and UP/1d control sensitivity."""
import numpy as np, judge_panel as J

syms, days, close, qv, fund = J.load()
lr, med, cnt = J.market_control(close)
S, D = close.shape
lclose = np.log(close); RT = 0.241
liq = (qv >= 1e6) & np.isfinite(lr); allf = np.isfinite(lr)

def series(mask, how):
    m = np.where(mask, lr, np.nan)
    with np.errstate(invalid="ignore"):
        s = np.nanmedian(m, axis=0) if how=="median" else np.nanmean(m, axis=0)
    s[mask.sum(axis=0) < 30] = np.nan; return s
CTRL = {"median/ALL (theirs)": series(allf,"median"), "median/LIQ": series(liq,"median"),
        "mean/ALL": series(allf,"mean"), "mean/LIQ": series(liq,"mean"),
        "NONE (outright)": np.zeros(D)}

lv=np.log(np.where(np.isfinite(qv)&(qv>0),qv,np.nan)); ok=np.isfinite(lv).astype(float)
x=np.where(np.isfinite(lv),lv,0.0)
c1=np.concatenate([np.zeros((S,1)),np.cumsum(x,1)],1); c2=np.concatenate([np.zeros((S,1)),np.cumsum(x*x,1)],1)
cn=np.concatenate([np.zeros((S,1)),np.cumsum(ok,1)],1); W=30
z=np.full((S,D),np.nan); tmed=np.full((S,D),np.nan)
for d in range(W,D):
    n=cn[:,d]-cn[:,d-W]; s=c1[:,d]-c1[:,d-W]; ss=c2[:,d]-c2[:,d-W]; m=n>=25
    mu=np.where(m,s/np.maximum(n,1),np.nan)
    z[:,d]=(lv[:,d]-mu)/np.sqrt(np.maximum(np.where(m,ss/np.maximum(n,1)-mu**2,np.nan),1e-12))
    with np.errstate(invalid="ignore"): tmed[:,d]=np.nanmedian(qv[:,d-W:d],axis=1)
spike_up=(z>=3.0)&(tmed>=1e6)&np.isfinite(lr)&(lr>0)
elig=(qv>=1e6)&np.isfinite(fund)&np.isfinite(close); formable=elig.sum(axis=0)>=30
topdec=np.zeros((S,D),bool); botdec=np.zeros((S,D),bool)
for d in range(D):
    if not formable[d]: continue
    idx=np.where(elig[:,d])[0]; k=max(1,int(round(len(idx)*0.10)))
    o=np.argsort(fund[idx,d],kind="stable"); topdec[idx[o[-k:]],d]=True; botdec[idx[o[:k]],d]=True

def ev(mask,sign,h,ctrl):
    cf=np.where(np.isfinite(ctrl),ctrl,0.0); cc=np.concatenate([[0.0],np.cumsum(cf)])
    ct=cc[1+h:D+1]-cc[1:D+1-h]
    exc=np.full((S,D),np.nan); exc[:,:D-h]=((lclose[:,h:]-lclose[:,:D-h])-ct[None,:])*100.0
    r,c=np.where(mask); k=(c<D-h)&np.isfinite(exc[r,c]); r,c=r[k],c[k]
    return sign*exc[r,c], c, r

print("="*80); print("OUTRIGHT P&L (no benchmark) -- what actually hits the account"); print("="*80)
for nm,mask,sign in (("LONG top-funding decile",topdec,+1.0),
                     ("LONG bottom-funding decile",botdec,+1.0),
                     ("SHORT volume-spike UP",spike_up,-1.0)):
    print(f"\n{nm}:")
    for h in (1,3,7):
        v,c,r=ev(mask,sign,h,CTRL["NONE (outright)"])
        b=J.boot_cluster(v,c)
        print(f"   h={h}: n={len(v):>6} gross={v.mean():+.4f}pp net={v.mean()-RT:+.4f}pp "
              f"ratio={v.mean()/RT:>5.2f}x CI=[{np.percentile(b,2.5):+.4f},{np.percentile(b,97.5):+.4f}]"
              f" P(>0)={(b>0).mean():.4f}")

print("\n" + "="*80)
print("UP/1d -- the ONLY arm that survives Holm. Control sensitivity + outright:")
print("="*80)
for cname,cs in CTRL.items():
    v,c,r=ev(spike_up,-1.0,1,cs); b=J.boot_cluster(v,c)
    print(f"  {cname:<22} gross={v.mean():+.4f}pp net={v.mean()-RT:+.4f}pp ratio={v.mean()/RT:>5.2f}x"
          f" CI=[{np.percentile(b,2.5):+.4f},{np.percentile(b,97.5):+.4f}]")
v,c,r=ev(spike_up,-1.0,1,CTRL["median/ALL (theirs)"])
tot=v.sum(); uq,inv=np.unique(r,return_inverse=True); per=np.bincount(inv,weights=v)
o=np.argsort(per)[::-1]
print(f"  TOP-3 SYMBOL SHARE of UP/1d P&L = {per[o[:3]].sum()/tot*100:.1f}%  "
      f"(worst single event {v.min():+.1f}pp, best {v.max():+.1f}pp)")
print(f"  1d turnover: {len(v)} events / {len(np.unique(c))} dates = {len(v)/len(np.unique(c)):.1f} trades/day,"
      f" each paying 24.1bp -> annual toll {len(v)/len(np.unique(c))*0.241*365:.0f}pp of gross notional")

print("\n" + "="*80); print("EXIT-SIDE REALITY: what does the short's loss tail look like?"); print("="*80)
for h in (1,3):
    v,c,r=ev(spike_up,-1.0,h,CTRL["median/ALL (theirs)"])
    q=np.percentile(v,[0.1,1,5,50,95,99,99.9])
    print(f"  h={h} short P&L pct [0.1,1,5,50,95,99,99.9] = {np.round(q,2)}")
    print(f"       worst 1% of events contribute {v[v<=np.percentile(v,1)].sum()/len(v):+.4f}pp to the mean "
          f"({abs(v[v<=np.percentile(v,1)].sum()/len(v)/v.mean()) if v.mean()!=0 else 0:.1f}x the mean)")
