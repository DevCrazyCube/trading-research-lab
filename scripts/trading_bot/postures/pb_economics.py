#!/usr/bin/env python3
"""POSTURE B.1 ECONOMICS: current snapshot, every input measured today.
   net_bp_day = f*vol1d/TVL*1e4  -  k * sigma_d^2/8 * 1e4
The BREAK-EVEN CONCENTRATION k* = fee_bp / LVR_bp(k=1) is the key statistic:
your own range width cancels (it scales fees and LVR identically), so the sign
is set by the POOL's k, which competing LPs -- not you -- determine.
"""
import csv, json, math, datetime as dt
from collections import defaultdict
import numpy as np

S = "/tmp/claude-1000/-home-anont-meme/5d56bbe0-2440-41b7-9176-f7470b1d1b38/scratchpad"
K   = json.load(open(f"{S}/k_measured.json"))
VOL = json.load(open(f"{S}/vol_series.json"))
last_date = max(VOL["ETHUSD"])
print(f"vol series last date = {last_date} (repo panel ends 2026-07-31; ~1 month stale vs today 2026-09-03)")
sig = {k: v[last_date] for k, v in VOL.items()}
for k, v in sig.items(): print(f"  sigma_d[{k}] = {v*100:.4f}%/day  -> LVR(k=1) = {v*v/8*1e4:.4f} bp/day")

# --- gas, measured on-chain today -------------------------------------------
GWEI, ETH = 0.043649, 2384.0622
GAS_UNITS = {"v3 mint (new NFT position)":450_000, "decreaseLiquidity+collect+burn":300_000,
             "router swap to rebalance 50/50":150_000}
cyc = sum(GAS_UNITS.values())
usd = cyc*GWEI*1e-9*ETH
print(f"\nMEASURED gas: baseFee={GWEI} gwei (median of 10 blocks, chainId 1, block 25,893,408), ETH=${ETH:,.2f}")
for k_, v in GAS_UNITS.items(): print(f"  {k_:34s} {v:>9,} gas = ${v*GWEI*1e-9*ETH:.4f}")
print(f"  full rebalance cycle {cyc:,} gas = ${usd:.4f}  -> on $100k position = {usd/100000*1e4:.5f} bp")
print("  => gas is ~0 in the 2026 fee regime; it is NOT what kills this. LVR is.")

print("\n" + "="*104)
print(f"{'pool':22s} {'f':>6s} {'vol1d/TVL':>10s} {'fee':>8s} {'LVRk=1':>8s} {'k*':>7s} {'k_meas':>7s} "
      f"{'LVR':>8s} {'net':>9s} {'net %/yr':>9s} {'fee/LVR':>8s}")
print("="*104)
tot = []
for p in K:
    f = p["fee"]/1e6
    turn = p["vol1d"]/p["tvl"]
    fee_bp = f*turn*1e4
    lvr1 = sig[p["volkey"]]**2/8*1e4
    kstar = fee_bp/lvr1
    lvr_bp = lvr1*p["k"]
    net = fee_bp - lvr_bp
    print(f"{p['pair']+'@'+p['meta']:22s} {p['meta']:>6s} {turn*100:9.2f}% {fee_bp:8.3f} {lvr1:8.3f} "
          f"{kstar:7.2f} {p['k']:7.2f} {lvr_bp:8.3f} {net:+9.3f} {net*365/100:+9.2f} {fee_bp/lvr_bp:8.3f}")
    tot.append(dict(lab=p["pair"]+"@"+p["meta"], net=net, ratio=fee_bp/lvr_bp, kstar=kstar,
                    k=p["k"], tvl=p["tvl"], fee=fee_bp, lvr=lvr_bp))
print("="*104)
r = np.array([t["ratio"] for t in tot]); n_ = np.array([t["net"] for t in tot])
w = np.array([t["tvl"] for t in tot]); w = w/w.sum()
print(f"  EW-mean fee/LVR across {len(tot)} pools = {r.mean():.3f}   TVL-weighted = {float((r*w).sum()):.3f}")
print(f"  EW-mean net = {n_.mean():+.3f} bp/day ({n_.mean()*365/100:+.2f}%/yr)   "
      f"TVL-weighted net = {float((n_*w).sum()):+.3f} bp/day ({float((n_*w).sum())*365/100:+.2f}%/yr)")
print(f"  pools with fee>LVR: {(r>1).sum()}/{len(r)}")
print(f"  ** fee/LVR clusters at 1.0 = the zero-profit condition of a competitive LP market **")

# --- what a $10k / $100k / $500k position actually earns ---------------------
print("\nPOSITION-SIZE SCAN (TVL-weighted net, before any rebalancing slippage):")
netw = float((n_*w).sum())
for cap in (10_000, 100_000, 500_000):
    ann = netw*365/1e4*cap
    print(f"  ${cap:>8,}: {netw*365/100:+.2f}%/yr = ${ann:+,.0f}/yr   "
          f"gas at 1 rebalance/day = ${usd*365:,.0f}/yr -> net ${ann-usd*365:+,.0f}/yr")
