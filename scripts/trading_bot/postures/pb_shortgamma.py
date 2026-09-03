#!/usr/bin/env python3
"""Is LPing short gamma? Fees scale with VOLUME; LVR scales with sigma^2.
If volume does not rise as fast as sigma^2, the LP is short a straddle -- the
SAME structure the parent brief found in the cross-section."""
import json, math
import numpy as np
S="/tmp/claude-1000/-home-anont-meme/5d56bbe0-2440-41b7-9176-f7470b1d1b38/scratchpad"
K=json.load(open(f"{S}/k_measured.json")); VOL=json.load(open(f"{S}/vol_series.json"))
LL=json.load(open(f"{S}/selected_pools.json"))
def find(pair,meta):
    a,b=pair.split('-')
    for p in LL:
        if set(p['symbol'].split('-'))=={a,b} and p['meta']==meta: return p['pool']
rows=[]
per={}
for p in K:
    pid=find(p['pair'],p['meta'])
    ch=json.load(open(f"{S}/charts/{pid}.json"))['data']; vs=VOL[p['volkey']]
    lab=f"{p['pair']}@{p['meta']}"; per[lab]=[]
    for r in ch:
        d=r['timestamp'][:10]; ab=r.get('apyBase')
        if ab is None or d not in vs: continue
        fee=(ab/100)/365*1e4; lvr=vs[d]**2/8*1e4*p['k']
        rows.append((d,lab,vs[d],fee,lvr,fee-lvr)); per[lab].append((fee,lvr,fee-lvr))

sig=np.array([r[2] for r in rows]); fee=np.array([r[3] for r in rows])
lvr=np.array([r[4] for r in rows]); net=np.array([r[5] for r in rows])
qs=np.percentile(sig,[20,40,60,80])
print("DAILY NET BY MEASURED-VOLATILITY QUINTILE  (n=%d pool-days)"%len(net))
print(f"{'sigma_d quintile':>18s} {'n':>6s} {'sigma_d':>9s} {'fee bp':>8s} {'LVR bp':>8s} {'net bp':>9s} {'net %/yr':>9s}")
edges=[-1]+list(qs)+[9e9]
for i in range(5):
    m=(sig>edges[i])&(sig<=edges[i+1])
    print(f"{'Q'+str(i+1):>18s} {m.sum():6d} {sig[m].mean()*100:8.3f}% {fee[m].mean():8.3f} "
          f"{lvr[m].mean():8.3f} {net[m].mean():+9.3f} {net[m].mean()*365/100:+8.2f}%")
# how does fee income scale with vol? log-log slope
mask=(fee>0)&(sig>0)
A=np.vstack([np.log(sig[mask]),np.ones(mask.sum())]).T
b_fee=np.linalg.lstsq(A,np.log(fee[mask]),rcond=None)[0]
print(f"\n  log-log slope  d.log(fee)/d.log(sigma)   = {b_fee[0]:.3f}")
print(f"  log-log slope  d.log(LVR)/d.log(sigma)   = 2.000  (LVR = k*sigma^2/8, by construction)")
print(f"  => fee income grows like sigma^{b_fee[0]:.2f} while the cost grows like sigma^2.0")
print(f"     The LP is SHORT GAMMA with exponent gap {2-b_fee[0]:.2f}. Same structure as the")
print(f"     cross-sectional finding: wins the quiet median day, loses on the volatile tail.")

print("\nPER-POOL (k measured today, full history):")
print(f"{'pool':22s} {'k':>6s} {'fee bp':>8s} {'LVR bp':>8s} {'net bp':>9s} {'net %/yr':>9s} {'fee/LVR':>8s}")
for p in K:
    lab=f"{p['pair']}@{p['meta']}"; a=np.array(per[lab])
    print(f"{lab:22s} {p['k']:6.2f} {a[:,0].mean():8.3f} {a[:,1].mean():8.3f} {a[:,2].mean():+9.3f} "
          f"{a[:,2].mean()*365/100:+8.2f}% {a[:,0].mean()/a[:,1].mean():8.3f}")
print("\nCROSS-CHECK vs published direct measurement (Fritsch & Canidio 2024, arXiv:2404.05803):")
print("  they measured fees ~= 80% of arbitrage losses for WETH-USDC 5bp over 2022-2023 (fee/LVR=0.80)")
lab='USDC-WETH@0.05%'; a=np.array(per[lab])
print(f"  our independent estimate for the same pool, full history: fee/LVR = {a[:,0].mean()/a[:,1].mean():.3f}")
