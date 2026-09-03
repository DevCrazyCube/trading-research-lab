#!/usr/bin/env python3
"""The control they used is a MEDIAN LOG return of ALL live names -- a number no
portfolio earns. Build the benchmark an operator can actually hold."""
import numpy as np, judge_panel as J
syms, days, close, qv, fund = J.load()
lr, med, cnt = J.market_control(close)
S, D = close.shape
simple = np.expm1(lr)
liq = (qv >= 1e6) & np.isfinite(lr)
allf = np.isfinite(lr)

with np.errstate(invalid="ignore"):
    ew_liq  = np.nanmean(np.where(liq, simple, np.nan), axis=0)   # EW daily-rebalanced, tradeable
    ew_all  = np.nanmean(np.where(allf, simple, np.nan), axis=0)
    md_liq  = np.nanmedian(np.where(liq, lr, np.nan), axis=0)
    md_all  = np.nanmedian(np.where(allf, lr, np.nan), axis=0)
for a, n in ((ew_liq, liq), (ew_all, allf), (md_liq, liq), (md_all, allf)):
    a[n.sum(axis=0) < 30] = np.nan

v = np.isfinite(ew_liq) & np.isfinite(md_all)
nd = v.sum()
print(f"days with all benchmarks: {nd}")
print("\nPER-DAY benchmark returns (the thing being subtracted), in pp/day:")
print(f"  MEDIAN LOG of ALL live names   (THEIR CONTROL) = {np.nanmean(md_all[v])*100:+.4f} pp/day")
print(f"  MEDIAN LOG of LIQUID names                     = {np.nanmean(md_liq[v])*100:+.4f} pp/day")
print(f"  EW SIMPLE return, LIQUID names (HOLDABLE)      = {np.nanmean(ew_liq[v])*100:+.4f} pp/day")
print(f"  EW SIMPLE return, ALL live names               = {np.nanmean(ew_all[v])*100:+.4f} pp/day")
print(f"\n  >>> GAP between their control and a holdable EW basket = "
      f"{(np.nanmean(ew_liq[v])-np.nanmean(md_all[v]))*100:+.4f} pp/day "
      f"= {(np.nanmean(ew_liq[v])-np.nanmean(md_all[v]))*100*3:+.3f} pp per 3-day window")
print(f"      (round trip is 0.241 pp, so the control choice alone is worth "
      f"{abs((np.nanmean(ew_liq[v])-np.nanmean(md_all[v]))*100*3)/0.241:.1f}x the toll)")

# compounded: what did each 'benchmark' actually do over the sample?
print("\nCOMPOUNDED over the sample (what the benchmark would have returned):")
print(f"  holding the EW liquid basket : {(np.nanprod(1+ew_liq[v])-1)*100:,.0f}%")
print(f"  'holding' the median-log ctrl: {(np.exp(np.nansum(md_all[v]))-1)*100:,.2f}%   <- unholdable")
print("\nINTERPRETATION: their control implies the market fell "
      f"{(1-np.exp(np.nansum(md_all[v])))*100:.2f}% while a tradeable EW basket of the same")
print("market rose. Subtracting it hands every LONG free alpha and taxes every SHORT.")
