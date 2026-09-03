#!/usr/bin/env python3
"""CONTROL SENSITIVITY: is the 'edge' bigger than the disagreement between four
equally defensible benchmarks? Applied to both post-hoc survivors."""
import numpy as np, judge_panel as J

syms, days, close, qv, fund = J.load()
lr, med, cnt = J.market_control(close)
S, D = close.shape
lclose = np.log(close)
RT = 0.241
liq = (qv >= 1e6) & np.isfinite(lr)
allf = np.isfinite(lr)

def series(mask, how):
    m = np.where(mask, lr, np.nan)
    with np.errstate(invalid="ignore"):
        s = np.nanmedian(m, axis=0) if how == "median" else np.nanmean(m, axis=0)
    s[mask.sum(axis=0) < 30] = np.nan
    return s

CTRL = {
  "median / ALL live (their choice)": series(allf, "median"),
  "median / LIQUID (qv>=$1M)":       series(liq, "median"),
  "mean   / ALL live":               series(allf, "mean"),
  "mean   / LIQUID (tradeable EW)":  series(liq, "mean"),
}

# rebuild the two event sets
lv = np.log(np.where(np.isfinite(qv) & (qv > 0), qv, np.nan))
ok = np.isfinite(lv).astype(float); x = np.where(np.isfinite(lv), lv, 0.0)
c1 = np.concatenate([np.zeros((S,1)), np.cumsum(x,1)],1); c2 = np.concatenate([np.zeros((S,1)), np.cumsum(x*x,1)],1)
cn = np.concatenate([np.zeros((S,1)), np.cumsum(ok,1)],1)
W=30; z=np.full((S,D),np.nan); tmed=np.full((S,D),np.nan)
for d in range(W,D):
    n=cn[:,d]-cn[:,d-W]; s=c1[:,d]-c1[:,d-W]; ss=c2[:,d]-c2[:,d-W]
    m=n>=25; mu=np.where(m,s/np.maximum(n,1),np.nan)
    sd=np.sqrt(np.maximum(np.where(m,ss/np.maximum(n,1)-mu**2,np.nan),1e-12))
    z[:,d]=(lv[:,d]-mu)/sd
    with np.errstate(invalid="ignore"):
        tmed[:,d]=np.nanmedian(qv[:,d-W:d],axis=1)
spike_up = (z>=3.0)&(tmed>=1e6)&np.isfinite(lr)&(lr>0)

elig=(qv>=1e6)&np.isfinite(fund)&np.isfinite(close)
formable=elig.sum(axis=0)>=30
topdec=np.zeros((S,D),bool)
for d in range(D):
    if not formable[d]: continue
    idx=np.where(elig[:,d])[0]; k=max(1,int(round(len(idx)*0.10)))
    topdec[idx[np.argsort(fund[idx,d],kind="stable")[-k:]],d]=True

def evaluate(mask, sign, h, ctrl):
    cf=np.where(np.isfinite(ctrl),ctrl,0.0); cc=np.concatenate([[0.0],np.cumsum(cf)])
    good=np.isfinite(ctrl)
    win=np.array([good[i+1:i+1+h].all() if i+h<D else False for i in range(D)])
    ct=cc[1+h:D+1]-cc[1:D+1-h]
    exc=np.full((S,D),np.nan)
    exc[:,:D-h]=((lclose[:,h:]-lclose[:,:D-h])-ct[None,:])*100.0
    r,c=np.where(mask&win[None,:])
    k=np.isfinite(exc[r,c]); r,c=r[k],c[k]
    v=sign*exc[r,c]
    bs=J.boot_cluster(v,c)
    return v,c,r,bs

for nm, mask, sign, lab in (
    ("SURVIVOR A: LONG top-funding decile (post-hoc momentum flip), h=3", topdec, +1.0, "A"),
    ("SURVIVOR B: SHORT volume-spike UP day (post-hoc control swap), h=3", spike_up, -1.0, "B")):
    print("\n" + "=" * 78); print(nm); print("=" * 78)
    print(f"{'control':<34} {'n':>7} {'gross pp':>9} {'net pp':>8} {'ratio':>6} {'95% CI':>22}")
    for cname, cs in CTRL.items():
        v,c,r,bs=evaluate(mask,sign,3,cs)
        g=v.mean()
        print(f"{cname:<34} {len(v):>7} {g:>+9.4f} {g-RT:>+8.4f} {g/RT:>6.2f}x "
              f"[{np.percentile(bs,2.5):>+8.4f},{np.percentile(bs,97.5):>+8.4f}]")
    vals=[evaluate(mask,sign,3,cs)[0].mean() for cs in CTRL.values()]
    print(f"  >>> SPREAD ACROSS CONTROLS = {max(vals)-min(vals):.4f}pp "
          f"= {(max(vals)-min(vals))/RT:.2f}x the round trip; sign flips: "
          f"{'YES' if min(vals)<0<max(vals) else 'no'}")
