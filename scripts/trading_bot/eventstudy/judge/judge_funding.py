#!/usr/bin/env python3
"""JUDGE re-derivation of the funding-extreme study + attack on its post-hoc leg."""
import numpy as np, judge_panel as J

syms, days, close, qv, fund = J.load()
lr, med, cnt = J.market_control(close)
S, D = close.shape
MINQV, MINX, DEC = 1e6, 30, 0.10
RT_PP = 0.241

medf = np.where(np.isfinite(med), med, 0.0)
cmed = np.concatenate([[0.0], np.cumsum(medf)])          # cum control
lclose = np.log(close)

def excess(h):
    """market-controlled cum log return from close t to close t+h, in pp."""
    out = np.full((S, D), np.nan)
    out[:, :D-h] = (lclose[:, h:] - lclose[:, :D-h]) - (cmed[1+h:D+1-0][:D-h] - cmed[1:D+1-h])[None, :]
    return out * 100.0

elig = (qv >= MINQV) & np.isfinite(fund) & np.isfinite(close)
nelig = elig.sum(axis=0)
formable = nelig >= MINX
print("days with formable funding cross-section:", int(formable.sum()))

res = {}
for h in (1, 3, 7):
    ex = excess(h)
    v_all, c_all, s_all, leg_all = [], [], [], []
    for d in range(D):
        if not formable[d] or not np.isfinite(med[d]): continue
        idx = np.where(elig[:, d])[0]
        f = fund[idx, d]
        k = max(1, int(round(len(idx) * DEC)))
        o = np.argsort(f, kind="stable")
        bot, top = idx[o[:k]], idx[o[-k:]]
        for grp, sign in ((top, -1.0), (bot, +1.0)):
            e = ex[grp, d]
            m = np.isfinite(e)
            v_all.append(sign * e[m]); c_all.append(np.full(m.sum(), d))
            s_all.append(grp[m]); leg_all.append(np.full(m.sum(), sign))
    v = np.concatenate(v_all); c = np.concatenate(c_all)
    ssym = np.concatenate(s_all); leg = np.concatenate(leg_all)
    K = len(np.unique(c)); mbar = len(v) / K
    sd = v.std(ddof=1); deff = 1 + (mbar - 1) * 0.30
    mde = (1.6449 + 0.8416) * sd / np.sqrt(len(v) / deff)
    bs = J.boot_cluster(v, c)
    print(f"\nh={h}: n={len(v)} clusters={K} sd={sd:.3f}pp MDE={mde:.3f}pp")
    print(f"   POOLED FADE mean={v.mean():+.4f}pp median={np.median(v):+.4f}pp "
          f"CI=[{np.percentile(bs,2.5):+.4f},{np.percentile(bs,97.5):+.4f}] P(>0)={(bs>0).mean():.4f}")
    for sg, nm in ((-1.0, "SHORT leg (fade crowded longs)"), (1.0, "LONG leg (fade crowded shorts)")):
        m = leg == sg
        bl = J.boot_cluster(v[m], c[m])
        print(f"   {nm}: n={m.sum()} mean={v[m].mean():+.4f}pp med={np.median(v[m]):+.4f}pp "
              f"CI=[{np.percentile(bl,2.5):+.4f},{np.percentile(bl,97.5):+.4f}]")
    res[h] = (v, c, ssym, leg)

# ---- ATTACK: the post-hoc "survivor" = MOMENTUM on the top-funding decile (long it),
#      i.e. the sign flip of the short leg at h=3 (+0.8086 pp claimed = 3.4x cost).
v, c, ssym, leg = res[3]
m = leg == -1.0
pnl = -v[m]                      # flip sign: LONG the crowded-long (momentum)
sy = ssym[m]; cl = c[m]
print("\n" + "=" * 74)
print("ATTACK ON THE POST-HOC SURVIVOR: momentum-long the TOP funding decile, h=3")
print("=" * 74)
bs = J.boot_cluster(pnl, cl)
print(f"n={len(pnl)} clusters={len(np.unique(cl))} mean={pnl.mean():+.4f}pp med={np.median(pnl):+.4f}pp "
      f"CI=[{np.percentile(bs,2.5):+.4f},{np.percentile(bs,97.5):+.4f}] P(>0)={(bs>0).mean():.4f}")
print(f"NET of {RT_PP}pp round trip = {pnl.mean()-RT_PP:+.4f}pp | edge/cost = {pnl.mean()/RT_PP:.2f}x")

# concentration: top-3 symbol share of total P&L (the check that killed the last survivor)
tot = pnl.sum()
uq, inv = np.unique(sy, return_inverse=True)
per = np.bincount(inv, weights=pnl)
cntper = np.bincount(inv)
o = np.argsort(per)[::-1]
print(f"\nTotal P&L = {tot:.1f} pp across {len(uq)} symbols")
print("TOP 10 SYMBOLS BY CONTRIBUTED P&L:")
for i in o[:10]:
    print(f"   {syms[uq[i]]:<16} n={int(cntper[i]):<5} sumP&L={per[i]:+9.1f}pp  share={per[i]/tot*100:5.1f}%")
print(f"\n>>> TOP-3 SYMBOL SHARE OF TOTAL P&L = {per[o[:3]].sum()/tot*100:.1f}%")
print(f">>> TOP-10 SYMBOL SHARE            = {per[o[:10]].sum()/tot*100:.1f}%")
# drop top 3 and re-read
keep = ~np.isin(sy, uq[o[:3]])
bs2 = J.boot_cluster(pnl[keep], cl[keep])
print(f"\nEX-TOP-3 SYMBOLS: n={keep.sum()} mean={pnl[keep].mean():+.4f}pp "
      f"CI=[{np.percentile(bs2,2.5):+.4f},{np.percentile(bs2,97.5):+.4f}] "
      f"NET={pnl[keep].mean()-RT_PP:+.4f}pp ratio={pnl[keep].mean()/RT_PP:.2f}x")
# date concentration
uc, cinv = np.unique(cl, return_inverse=True)
dper = np.bincount(cinv, weights=pnl)
do = np.argsort(dper)[::-1]
print(f"TOP-3 DATE SHARE OF TOTAL P&L      = {dper[do[:3]].sum()/tot*100:.1f}%")
# time split: is it stable?
half = np.median(cl)
for nm, msk in (("first half", cl <= half), ("second half", cl > half)):
    b = J.boot_cluster(pnl[msk], cl[msk])
    print(f"{nm}: n={msk.sum()} mean={pnl[msk].mean():+.4f}pp CI=[{np.percentile(b,2.5):+.4f},{np.percentile(b,97.5):+.4f}] net={pnl[msk].mean()-RT_PP:+.4f}pp")
