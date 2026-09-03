#!/usr/bin/env python3
"""POSTURE B.1 STRESS: is the +5%/yr snapshot robust? Vary (a) volume window,
(b) which MEASURED volatility regime, and (c) run GATE 3 on the k-adjusted
historical daily series."""
import json, math
import numpy as np
S="/tmp/claude-1000/-home-anont-meme/5d56bbe0-2440-41b7-9176-f7470b1d1b38/scratchpad"
K=json.load(open(f"{S}/k_measured.json")); VOL=json.load(open(f"{S}/vol_series.json"))
LL={p['pool']:p for p in json.load(open(f"{S}/selected_pools.json"))}
raw=json.load(open(f"{S}/llama_pools.json"))['data']
V7={}
for p in raw:
    V7[p['pool']]=(p.get('volumeUsd1d'),p.get('volumeUsd7d'))

# map k_measured entries back to llama pool ids by (symbolset, meta)
def find(pair,meta):
    a,b=pair.split('-')
    for pid,p in LL.items():
        if set(p['symbol'].split('-'))=={a,b} and p['meta']==meta: return pid,p
    return None,None

# MEASURED vol regimes (trailing realised, from repo panel)
def regime(volkey,win):
    v=VOL[volkey]; ds=sorted(v)
    return float(np.median([v[d] for d in ds[-win:]]))
REG={w:{k:regime(k,w) for k in VOL} for w in (30,90,365,100000)}
names={30:'last-30d',90:'last-90d',365:'last-365d',100000:'full-sample'}

print("MEASURED sigma_d (median of trailing-30d realised vol over the window), %/day:")
for w in (30,90,365,100000):
    print(f"  {names[w]:12s} " + "  ".join(f"{k}={REG[w][k]*100:.3f}%" for k in REG[w]))

print(f"\n{'volume window':>14s} {'vol regime':>12s} {'EWfee/LVR':>10s} {'TVLw fee/LVR':>13s} {'TVLw net %/yr':>14s} {'pools fee>LVR':>14s}")
for vw,lab in ((0,'1d'),(1,'7d avg')):
    for w in (30,90,365,100000):
        rows=[]
        for p in K:
            pid,ll=find(p['pair'],p['meta'])
            v1,v7=V7[pid]
            vol = v1 if vw==0 else (v7/7.0)
            f=p['fee']/1e6
            fee=f*vol/p['tvl']*1e4
            lvr=REG[w][p['volkey']]**2/8*1e4*p['k']
            rows.append((fee/lvr, fee-lvr, p['tvl']))
        r=np.array([x[0] for x in rows]); n=np.array([x[1] for x in rows])
        tw=np.array([x[2] for x in rows]); tw=tw/tw.sum()
        print(f"{lab:>14s} {names[w]:>12s} {r.mean():10.3f} {float((r*tw).sum()):13.3f} "
              f"{float((n*tw).sum())*365/100:13.2f}% {int((r>1).sum()):>10d}/{len(r)}")

# ---------------- GATE 3 on k-adjusted historical daily series --------------
print("\n"+"="*78)
print("GATE 3 (k-adjusted)  net = apyBase_daily - k_measured * sigma_d^2/8")
print("  caveat: k is a TODAY snapshot applied across history (declared, not hidden)")
print("="*78)
rows=[]
for p in K:
    pid,ll=find(p['pair'],p['meta'])
    ch=json.load(open(f"{S}/charts/{pid}.json"))['data']; vs=VOL[p['volkey']]
    for r_ in ch:
        d=r_['timestamp'][:10]; ab=r_.get('apyBase')
        if ab is None or d not in vs: continue
        fee=(ab/100)/365*1e4; lvr=vs[d]**2/8*1e4*p['k']
        rows.append((d,fee-lvr))
net=np.array([x[1] for x in rows]); dts=np.array([x[0] for x in rows])
by={}
for i,d in enumerate(dts): by.setdefault(d,[]).append(i)
dl=list(by); idx=[np.array(by[d]) for d in dl]; nd=len(dl)
rng=np.random.default_rng(20260903); b=np.empty(5000)
for i in range(5000):
    pk=rng.integers(0,nd,nd); b[i]=net[np.concatenate([idx[j] for j in pk])].mean()
lo,hi=np.percentile(b,[2.5,97.5])
print(f"  n={len(net)} pool-days, {nd} date clusters")
print(f"  mean net = {net.mean():+.4f} bp/day 95%CI [{lo:+.4f},{hi:+.4f}]")
print(f"           = {net.mean()*365/100:+.2f}%/yr  CI [{lo*365/100:+.2f}%,{hi*365/100:+.2f}%]")
print(f"  P(mean<=0) = {(b<=0).mean():.4f}   share of pool-days net>0 = {(net>0).mean()*100:.1f}%")
print(f"  SD of daily net = {net.std(ddof=1):.3f} bp/day -> ann. vol of the fee-minus-LVR stream "
      f"= {net.std(ddof=1)*math.sqrt(365)*365/100/100:.1f}x ... ")
ann_mu = net.mean()*365/1e4; ann_sd = net.std(ddof=1)/1e4*math.sqrt(365)
print(f"  venue-income stream: mu={ann_mu*100:+.2f}%/yr  sigma={ann_sd*100:.2f}%/yr  "
      f"Sharpe(excess over 0)={ann_mu/ann_sd:.3f}")
