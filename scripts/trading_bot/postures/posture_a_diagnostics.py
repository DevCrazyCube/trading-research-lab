#!/usr/bin/env python3
"""POSTURE A diagnostics: outlier influence, per-year stability, paired overlay bootstrap,
vol-drag decomposition, BTC sanity. New file. Reuses the engine from posture_a_own_the_basket."""
import math, time, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from posture_a_own_the_basket import (load_panel, load_funding, run_basket, metrics, dstr,
                                      QV_MIN, RT_BP, LEG_BP, SEED, NBOOT)

dayvals, symnames, close, qvm = load_panel()
nd, ns = close.shape
F, H, _ = load_funding(dayvals, symnames)
have = ~np.isnan(close)
elig = have & (np.nan_to_num(qvm, nan=0.0) >= QV_MIN)

print("=== BTC SANITY ===")
b = symnames.index('BTCUSDT')
idx = np.where(have[:, b])[0]
print(f"BTCUSDT first {dstr(dayvals[idx[0]])} close={close[idx[0],b]:.1f} | "
      f"last {dstr(dayvals[idx[-1]])} close={close[idx[-1],b]:.1f} | "
      f"x{close[idx[-1],b]/close[idx[0],b]:.2f} over {len(idx)} days")

ew = run_basket(close, qvm, F, H, elig, 1)
ew_m = run_basket(close, qvm, F, H, elig, 28)
btc = run_basket(close, qvm, F, H, (lambda m: m)(np.stack([have[:,b] if i==b else np.zeros(nd,bool) for i in range(ns)],axis=1)), 1)
net = ew['net']; gross = ew['gross']

print("\n=== VOL DRAG DECOMPOSITION (EW liquid, net) ===")
mu, sd = net.mean(), net.std(ddof=1)
print(f"arithmetic mean  {mu*365*100:7.2f}%/yr   variance drag -sigma^2/2 = {-(sd*math.sqrt(365))**2/2*100:7.2f}%/yr"
      f"   => geometric ~{(mu*365 - (sd*math.sqrt(365))**2/2)*100:7.2f}%/yr  (measured CAGR {metrics(net)['cagr']*100:.2f}%)")

print("\n=== OUTLIER INFLUENCE (EW liquid, NET daily series) ===")
srt = np.sort(net)[::-1]
o = np.argsort(net)[::-1]
print("top 5 basket days:", ", ".join(f"{dstr(dayvals[i+1])} {net[i]*100:+.1f}%" for i in o[:5]))
print("worst 5 basket days:", ", ".join(f"{dstr(dayvals[i+1])} {net[i]*100:+.1f}%" for i in o[-5:]))
for k in [1,5,10,20,50]:
    m2 = net.copy(); m2[o[:k]] = 0.0
    mm = metrics(m2)
    print(f"  drop best {k:3d} days -> CAGR={mm['cagr']*100:8.2f}%  Sharpe={mm['sharpe']:6.3f}  total={mm['total']*100:+9.1f}%")
print(f"  (baseline CAGR={metrics(net)['cagr']*100:.2f}% total={metrics(net)['total']*100:+.1f}%)")

print("\n=== PER-CALENDAR-YEAR (net) ===")
yrs = np.array([int(time.strftime('%Y', time.gmtime(d/1000))) for d in dayvals[1:]])
print(f"{'yr':<6}{'EWdaily':>10}{'EWmonthly':>11}{'BTC':>10}{'n':>6}")
for y in sorted(set(yrs)):
    m = yrs == y
    f = lambda s: (np.prod(1+s[m])-1)*100
    print(f"{y:<6}{f(net):>9.1f}%{f(ew_m['net']):>10.1f}%{f(btc['net']):>9.1f}%{int(m.sum()):>6}")

print("\n=== PAIRED CLUSTER BOOTSTRAP: overlay minus base (dates resampled jointly) ===")
def overlay(s, lb):
    eq = np.cumprod(1.0+s); pos = np.ones(len(s))
    for t in range(len(s)):
        pos[t] = 1.0 if t < lb else (1.0 if eq[t-1] >= eq[t-lb:t].mean() else 0.0)
    sw = np.abs(np.diff(np.concatenate([[1.0], pos])))
    return s*pos - sw*(LEG_BP/1e4), pos
ov, pos = overlay(net, 100)
d = ov - net
rng = np.random.default_rng(SEED)
n = len(net); I = rng.integers(0, n, size=(NBOOT, n))
dm = d[I].mean(axis=1)
a, bb = net[I], ov[I]
sh = lambda x: x.mean(axis=1)/x.std(axis=1,ddof=1)*math.sqrt(365)
dsh = sh(bb) - sh(a)
print(f"mean daily diff = {d.mean()*1e4:+.2f} bp  95%CI=[{np.percentile(dm,2.5)*1e4:+.2f},{np.percentile(dm,97.5)*1e4:+.2f}] "
      f" P(diff<=0)={float((dm<=0).mean()):.3f}")
print(f"Sharpe diff     = {sh(ov[None,:])[0]-sh(net[None,:])[0]:+.3f}  95%CI=[{np.percentile(dsh,2.5):+.3f},{np.percentile(dsh,97.5):+.3f}] "
      f" P(dSharpe<=0)={float((dsh<=0).mean()):.3f}")
mo = metrics(ov)
print(f"overlay: CAGR={mo['cagr']*100:.2f}% Sharpe={mo['sharpe']:.3f} maxDD={mo['mdd']*100:.1f}% in-market={pos.mean()*100:.1f}%")

print("\n=== WALK-FORWARD HONESTY: overlay lookback picked on first half, applied to second half ===")
h = n//2
best_lb, best_s = None, -9
for lb in [20,30,50,60,80,100,120,150,180,200]:
    o,_ = overlay(net[:h], lb); s = metrics(o)['sharpe']
    if s > best_s: best_s, best_lb = s, lb
o_full,_ = overlay(net, best_lb)
m1 = metrics(o_full[h:]); m0 = metrics(net[h:])
print(f"best in-sample lookback = {best_lb} (IS Sharpe {best_s:.3f}); OUT-OF-SAMPLE 2nd half: "
      f"overlay Sharpe={m1['sharpe']:.3f} CAGR={m1['cagr']*100:.2f}% maxDD={m1['mdd']*100:.1f}%  vs "
      f"base Sharpe={m0['sharpe']:.3f} CAGR={m0['cagr']*100:.2f}% maxDD={m0['mdd']*100:.1f}%")

print("\n=== FUNDING PAID vs EARNED, EW liquid ===")
print(f"mean funding drag {ew['fund'].mean()*1e4:.2f} bp/day = {ew['fund'].mean()*365*100:.1f}%/yr; "
      f"days where longs were PAID: {(ew['fund']<0).mean()*100:.1f}%")

print("\n=== TURNOVER DETAIL ===")
for k,nm in [(1,'daily'),(7,'weekly'),(28,'monthly')]:
    rr = run_basket(close, qvm, F, H, elig, k)
    t = rr['turn']; t = t[t>0]
    print(f"{nm:<8s} rebalance-day one-way turnover mean={t.mean()*100:6.2f}% median={np.median(t)*100:6.2f}% "
          f"p95={np.percentile(t,95)*100:6.2f}%  annualised one-way turnover={rr['turn'].sum()/ (len(rr['turn'])/365):.1f}x/yr "
          f"annual cost={rr['turn'].mean()*RT_BP*365/100:.2f}%/yr")
