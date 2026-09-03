#!/usr/bin/env python3
import numpy as np, judge_panel as J
syms, days, close, qv, fund = J.load()
lr, med, cnt = J.market_control(close)
S, D = close.shape; lclose = np.log(close)
medf=np.where(np.isfinite(med),med,0.0); cmed=np.concatenate([[0.0],np.cumsum(medf)])
elig=(qv>=1e6)&np.isfinite(fund)&np.isfinite(close); formable=elig.sum(axis=0)>=30
bot=np.zeros((S,D),bool)
for d in range(D):
    if not formable[d]: continue
    idx=np.where(elig[:,d])[0]; k=max(1,int(round(len(idx)*0.10)))
    bot[idx[np.argsort(fund[idx,d],kind="stable")[:k]],d]=True
h=3; ct=cmed[1+h:D+1]-cmed[1:D+1-h]
exc=np.full((S,D),np.nan); exc[:,:D-h]=((lclose[:,h:]-lclose[:,:D-h])-ct[None,:])*100.0
r,c=np.where(bot); k=(c<D-h)&np.isfinite(exc[r,c]); v=exc[r[k],c[k]]; c=c[k]
b=J.boot_cluster(v,c)
p_long_leg = 1.0-(b>0).mean()
print(f"funding LONG leg h=3 (post-hoc): n={len(v)} mean={v.mean():+.4f}pp one-sided p={p_long_leg:.6f}")

# ---- HOLM over every comparison whose effect was actually READ
comps = [
 ("S1 funding fade POOLED h=1",              1.0000, "prereg"),
 ("S1 funding fade POOLED h=3 (PRIMARY)",    1.0000, "prereg"),
 ("S1 funding fade POOLED h=7",              1.0000, "prereg"),
 ("S1 funding SHORT leg h=3",                1.0000, "post-hoc"),
 ("S1 funding LONG leg h=3",       max(p_long_leg,1/5000), "post-hoc"),
 ("S5 volspike UP h=1",                      0.0002, "prereg"),
 ("S5 volspike UP h=3 (PRIMARY)",            0.3112, "prereg"),
 ("S5 volspike UP h=7",                      0.9932, "prereg"),
 ("S5 volspike DOWN h=1",                    0.1842, "prereg"),
 ("S5 volspike DOWN h=3",                    0.0816, "prereg"),
 ("S5 volspike DOWN h=7",                    0.7146, "prereg"),
]
m=len(comps); order=sorted(range(m), key=lambda i: comps[i][1])
print(f"\nHOLM-BONFERRONI, m = {m} comparisons actually read, alpha=0.05 one-sided")
print(f"{'#':<3}{'comparison':<40}{'raw p':>10}{'thresh':>10}{'Holm adj p':>12}  verdict")
prev=0.0; still=True
for rank,i in enumerate(order):
    nm,p,kind=comps[i]; thr=0.05/(m-rank); adj=min(1.0,max(prev,p*(m-rank))); prev=adj
    if still and p<=thr: vd="SURVIVES"
    else: still=False; vd="rejected"
    print(f"{rank+1:<3}{nm:<40}{p:>10.4f}{thr:>10.5f}{adj:>12.5f}  {vd}  [{kind}]")
print("\nBattery-level selection denominator: 6 hypotheses attempted; 4 died at gates 1-2")
print("and contributed 0 effect statistics, so they consume no alpha but DO widen the")
print("'how many ideas did we try' denominator to 6 (and ~60 across the repo's history).")
