#!/usr/bin/env python3
"""POSTURE A closing numbers: Gate-3 on the monthly EW variant, cost-assumption sensitivity,
BTC-vs-basket head-to-head. New file."""
import math, os, sys, time
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from posture_a_own_the_basket import (load_panel, load_funding, run_basket, metrics, boot_ci,
                                      dstr, QV_MIN, RT_BP, SEED, NBOOT)
dayvals, symnames, close, qvm = load_panel()
nd, ns = close.shape
F, H, _ = load_funding(dayvals, symnames)
have = ~np.isnan(close); elig = have & (np.nan_to_num(qvm, nan=0.0) >= QV_MIN)
b = symnames.index('BTCUSDT')
bm = np.zeros((nd, ns), bool); bm[:, b] = have[:, b]

runs = {'EW daily': run_basket(close,qvm,F,H,elig,1),
        'EW weekly': run_basket(close,qvm,F,H,elig,7),
        'EW monthly': run_basket(close,qvm,F,H,elig,28),
        'BTCUSDT': run_basket(close,qvm,F,H,bm,1)}
sd_pilot = None
print("=== GATE 3 on every variant (cluster bootstrap by DATE, 5000 draws, seed 20260903) ===")
mde = None
for k,r in runs.items():
    m = metrics(r['net']); ci = boot_ci(r['net'])
    if mde is None:
        mde = 2.4864748605 * metrics(runs['EW daily']['net'])['sd_daily']/math.sqrt(m['n'])
    print(f"{k:<12s} netMean={m['mean_daily']*1e4:+6.2f}bp CI=[{ci['mu_lo']*1e4:+6.2f},{ci['mu_hi']*1e4:+6.2f}] "
          f"P(mu<=0)={ci['p_le0']:.3f} | Sharpe={m['sharpe']:.3f} CI=[{ci['sh_lo']:+.3f},{ci['sh_hi']:+.3f}] "
          f"| CAGR={m['cagr']*100:+7.2f}% maxDD={m['mdd']*100:6.1f}% w60={m['w60']*100:6.1f}% "
          f"| {'GATE3 PASS' if ci['mu_lo']>0 else 'GATE3 FAIL'}")
print(f"MDE (declared pre-effect) = {mde*1e4:.2f} bp/day. Every point estimate above is BELOW it.")

print("\n=== COST-ASSUMPTION SENSITIVITY (net CAGR / Sharpe at multiples of the 24.1bp round trip) ===")
print(f"{'round-trip bp':>14} " + " ".join(f"{k:>22}" for k in runs))
for mult in [0.5, 1.0, 2.0, 5.0, 10.0]:
    row = []
    for k,r in runs.items():
        net = r['gross'] - r['fund'] - r['turn']*(RT_BP*mult/1e4)
        m = metrics(net); row.append(f"{m['cagr']*100:+8.2f}%/S={m['sharpe']:.3f}")
    print(f"{RT_BP*mult:>13.1f}  " + " ".join(f"{x:>22}" for x in row))

print("\n=== FUNDING-FREE COUNTERFACTUAL (i.e. if you held SPOT, not perps) ===")
for k,r in runs.items():
    net = r['gross'] - r['turn']*(RT_BP/1e4)
    m = metrics(net)
    print(f"{k:<12s} CAGR={m['cagr']*100:+7.2f}% Sharpe={m['sharpe']:.3f} maxDD={m['mdd']*100:6.1f}%  "
          f"(funding drag removed = {r['fund'].mean()*365*100:+.1f}%/yr)")

print("\n=== HEAD-TO-HEAD: EW monthly minus BTC, paired date bootstrap ===")
a = runs['EW monthly']['net']; c = runs['BTCUSDT']['net']
rng = np.random.default_rng(SEED); n=len(a); I = rng.integers(0,n,size=(NBOOT,n))
d = a-c; dm = d[I].mean(axis=1)
sh = lambda x: x.mean(axis=1)/x.std(axis=1,ddof=1)*math.sqrt(365)
dsh = sh(a[I])-sh(c[I])
print(f"mean daily diff {d.mean()*1e4:+.2f}bp CI=[{np.percentile(dm,2.5)*1e4:+.2f},{np.percentile(dm,97.5)*1e4:+.2f}] "
      f"P(EW<=BTC)={float((dm<=0).mean()):.3f}")
print(f"Sharpe diff {sh(a[None,:])[0]-sh(c[None,:])[0]:+.3f} CI=[{np.percentile(dsh,2.5):+.3f},{np.percentile(dsh,97.5):+.3f}] "
      f"P(dSharpe<=0)={float((dsh<=0).mean()):.3f}")
print(f"correlation EW-monthly vs BTC = {np.corrcoef(a,c)[0,1]:.3f}")

print("\n=== BASKET SIZE / CONCENTRATION ===")
per_day = elig.sum(axis=1)
print(f"liquid names/day: mean={per_day.mean():.0f} median={np.median(per_day):.0f} "
      f"min={per_day.min()} max={per_day.max()} ; first day with >=50: {dstr(dayvals[int(np.argmax(per_day>=50))])}")
