#!/usr/bin/env python3
"""Re-derive the volume-spike study, then re-benchmark it against a MATCHED control."""
import numpy as np, judge_panel as J

syms, days, close, qv, fund = J.load()
lr, med, cnt = J.market_control(close)
S, D = close.shape
lclose = np.log(close)
RT = 0.241

# --- trailing 30d causal log-volume z, window t-30..t-1, >=25 obs
lv = np.log(np.where(np.isfinite(qv) & (qv > 0), qv, np.nan))
ok = np.isfinite(lv).astype(float)
x = np.where(np.isfinite(lv), lv, 0.0)
c1 = np.concatenate([np.zeros((S, 1)), np.cumsum(x, axis=1)], axis=1)
c2 = np.concatenate([np.zeros((S, 1)), np.cumsum(x * x, axis=1)], axis=1)
cn = np.concatenate([np.zeros((S, 1)), np.cumsum(ok, axis=1)], axis=1)
W = 30
z = np.full((S, D), np.nan)
for d in range(W, D):
    n = cn[:, d] - cn[:, d - W]
    s = c1[:, d] - c1[:, d - W]
    ss = c2[:, d] - c2[:, d - W]
    m = n >= 25
    mu = np.where(m, s / np.maximum(n, 1), np.nan)
    var = np.where(m, ss / np.maximum(n, 1) - mu ** 2, np.nan)
    sd = np.sqrt(np.maximum(var, 1e-12))
    z[:, d] = (lv[:, d] - mu) / sd
# trailing median quote volume >= $1M (causal, t-30..t-1)
tmed = np.full((S, D), np.nan)
for d in range(W, D):
    w = qv[:, d - W:d]
    with np.errstate(invalid="ignore"):
        tmed[:, d] = np.nanmedian(w, axis=1)

medf = np.where(np.isfinite(med), med, 0.0)
cmed = np.concatenate([[0.0], np.cumsum(medf)])
# matched control: same-day cross-sectional MEAN of the LIQUID (qv>=$1M) universe
liq = (qv >= 1e6) & np.isfinite(lr)
with np.errstate(invalid="ignore"):
    lm = np.where(liq, lr, np.nan)
    meanliq = np.nanmean(lm, axis=0)
nliq = liq.sum(axis=0)
meanliq[nliq < 30] = np.nan
mlf = np.where(np.isfinite(meanliq), meanliq, 0.0)
cmean = np.concatenate([[0.0], np.cumsum(mlf)])

ev = (z >= 3.0) & (tmed >= 1e6) & np.isfinite(lr) & np.isfinite(med) & np.isfinite(meanliq)
up = ev & (lr > 0)
print("raw events:", int(ev.sum()), " UP:", int(up.sum()), " DOWN:", int((ev & (lr < 0)).sum()))

def run(h, mask, ctrl_cum, label):
    ctrl = ctrl_cum[1+h:D+1] - ctrl_cum[1:D+1-h]
    exc = np.full((S, D), np.nan)
    exc[:, :D-h] = ((lclose[:, h:] - lclose[:, :D-h]) - ctrl[None, :]) * 100.0
    r, c = np.where(mask)
    keep = (c < D - h) & np.isfinite(exc[r, c])
    r, c = r[keep], c[keep]
    v = exc[r, c]
    bs = J.boot_cluster(v, c)
    print(f"  {label} h={h}: n={len(v)} clusters={len(np.unique(c))} mean={v.mean():+.4f}pp "
          f"med={np.median(v):+.4f}pp CI=[{np.percentile(bs,2.5):+.4f},{np.percentile(bs,97.5):+.4f}] "
          f"P(<0)={(bs<0).mean():.4f}")
    return v, c, r

print("\n--- A) THEIR CONTROL (cross-sectional MEDIAN of all live names) ---")
for h in (1, 3, 7):
    run(h, up, cmed, "UP")
print("\n--- B) MATCHED CONTROL (cross-sectional MEAN of the LIQUID universe we could trade) ---")
out = {}
for h in (1, 3, 7):
    out[h] = run(h, up, cmean, "UP")

print("\n" + "=" * 78)
print("ATTACK: the UP/3d short under the MATCHED control (short spike, gross = -mean)")
print("=" * 78)
v, c, r = out[3]
pnl = -v
print(f"gross short edge = {pnl.mean():+.4f}pp  net of {RT}pp = {pnl.mean()-RT:+.4f}pp  "
      f"ratio={pnl.mean()/RT:.2f}x")
tot = pnl.sum()
uq, inv = np.unique(r, return_inverse=True)
per = np.bincount(inv, weights=pnl); cn2 = np.bincount(inv)
o = np.argsort(per)[::-1]
print(f"total P&L {tot:.1f}pp over {len(uq)} symbols; TOP-3 SYMBOL SHARE = {per[o[:3]].sum()/tot*100:.1f}%")
for i in o[:5]:
    print(f"   {syms[uq[i]]:<16} n={int(cn2[i]):<4} {per[i]:+8.1f}pp  {per[i]/tot*100:4.1f}%")
uc, ci = np.unique(c, return_inverse=True)
dp = np.bincount(ci, weights=pnl); dо = np.argsort(dp)[::-1]
print(f"TOP-3 DATE SHARE = {dp[dо[:3]].sum()/tot*100:.1f}%  (worst date {dp[dо[-1]]:+.0f}pp)")
hm = np.median(c)
for nm, m in (("first half", c <= hm), ("second half", c > hm)):
    b = J.boot_cluster(pnl[m], c[m])
    print(f"{nm}: n={m.sum()} mean={pnl[m].mean():+.4f}pp CI=[{np.percentile(b,2.5):+.4f},{np.percentile(b,97.5):+.4f}] net={pnl[m].mean()-RT:+.4f}pp")
