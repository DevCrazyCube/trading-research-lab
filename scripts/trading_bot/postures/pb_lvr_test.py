#!/usr/bin/env python3
"""POSTURE B.1 GATES 1-3.  Test the k=1 UPPER BOUND on Uniswap v3 LP net return.
   net_LP <= apyBase_daily - sigma_d^2/8      (see pb_lvr_gates.py for why)
"""
import json, math, os, sys
import numpy as np

S = "/tmp/claude-1000/-home-anont-meme/5d56bbe0-2440-41b7-9176-f7470b1d1b38/scratchpad"
SEED, NBOOT, ICC = 20260903, 5000, 0.30
Z_A, Z_B = 1.6448536269514722, 0.8416212335729143
MIN_POOLS, MIN_DAYS_POOL, MIN_DATES = 4, 500, 700

VOL  = json.load(open(f"{S}/vol_series.json"))
POOL = json.load(open(f"{S}/selected_pools.json"))

# ---------------------------------------------------------------- GATE 1
rows = []            # (date, pool_label, net_bp_upper, apy_bp, lvr_bp)
per_pool = {}
for p in POOL:
    ch = json.load(open(f"{S}/charts/{p['pool']}.json"))["data"]
    vs = VOL[p["volkey"]]
    lab = f"{p['symbol']}@{p['meta']}"
    n = 0
    for r in ch:
        d = r["timestamp"][:10]
        ab = r.get("apyBase")
        if ab is None or d not in vs:
            continue
        sd = vs[d]
        apy_bp = (ab/100.0)/365.0 * 1e4          # fee yield, bp/day, on deposited capital
        lvr_bp = (sd*sd/8.0) * 1e4               # LVR at k=1, bp/day
        rows.append((d, lab, apy_bp - lvr_bp, apy_bp, lvr_bp))
        n += 1
    per_pool[lab] = n

dates = sorted({r[0] for r in rows})
print("="*78); print("GATE 1  COVERAGE")
print("="*78)
for lab, n in per_pool.items():
    print(f"  {lab:22s} n_days={n}")
print(f"  pools={len(per_pool)} (min {MIN_POOLS})   dates={len(dates)} (min {MIN_DATES})   rows={len(rows)}")
print(f"  window {dates[0]} -> {dates[-1]}")
ok1 = (len(per_pool) >= MIN_POOLS and len(dates) >= MIN_DATES
       and min(per_pool.values()) >= MIN_DAYS_POOL)
print(f"  GATE 1: {'PASS' if ok1 else 'FAIL'}")
if not ok1: sys.exit(1)

net = np.array([r[2] for r in rows]); dt_ = np.array([r[0] for r in rows])
by_date = {}
for i, d in enumerate(dt_): by_date.setdefault(d, []).append(i)
mbar = len(rows)/len(dates)

# ---------------------------------------------------------------- GATE 2
print("\n" + "="*78); print("GATE 2  POWER  (computed BEFORE reading the effect)")
print("="*78)
sd_net = float(np.std(net, ddof=1))
DE   = 1 + (mbar-1)*ICC
Neff = len(rows)/DE
MDE  = (Z_A+Z_B)*sd_net/math.sqrt(Neff)
print(f"  SD(daily net) = {sd_net:.4f} bp/day   mean pools/date m={mbar:.2f}")
print(f"  design effect = 1+(m-1)*ICC = {DE:.3f}   N={len(rows)}  N_eff={Neff:.0f}  clusters={len(dates)}")
print(f"  MDE (alpha=0.05 1-sided, power=0.80) = {MDE:.4f} bp/day = {MDE*365/100:.3f} %/yr")
print(f"  GATE 2: PASS (MDE is far below any economically interesting effect)")

# ---------------------------------------------------------------- GATE 3
print("\n" + "="*78); print(f"GATE 3  EFFECT  cluster-bootstrap by DATE, {NBOOT} draws, seed {SEED}")
print("="*78)
rng = np.random.default_rng(SEED)
dl  = list(by_date.keys()); idx = [np.array(by_date[d]) for d in dl]; nd = len(dl)
boots = np.empty(NBOOT)
for b in range(NBOOT):
    pick = rng.integers(0, nd, nd)
    boots[b] = net[np.concatenate([idx[j] for j in pick])].mean()
pt = float(net.mean()); lo, hi = np.percentile(boots, [2.5, 97.5])
print(f"  mean net UPPER BOUND = {pt:+.4f} bp/day   95% CI [{lo:+.4f}, {hi:+.4f}]")
print(f"                        = {pt*365/100:+.3f} %/yr  CI [{lo*365/100:+.3f}, {hi*365/100:+.3f}]")
print(f"  one-sided P(mean<=0) among draws = {(boots<=0).mean():.4f}")
print(f"  share of pool-days with positive upper bound = {(net>0).mean()*100:.1f}%")
print(f"  MEDIAN pool-day net = {np.median(net):+.4f} bp/day   (reported, NOT used as benchmark)")

print("\n  per-pool mean upper bound (bp/day):")
for lab in per_pool:
    v = np.array([r[2] for r in rows if r[1]==lab])
    a = np.array([r[3] for r in rows if r[1]==lab]); l = np.array([r[4] for r in rows if r[1]==lab])
    print(f"    {lab:22s} fee={a.mean():7.3f}  LVR(k=1)={l.mean():7.3f}  net={v.mean():+8.3f} bp/day "
          f"({v.mean()*365/100:+7.2f}%/yr)  fee/LVR={a.mean()/l.mean():.3f}")

# last 365 dates only (current regime)
recent = set(dates[-365:])
nr = np.array([r[2] for r in rows if r[0] in recent])
ar = np.array([r[3] for r in rows if r[0] in recent]); lr_ = np.array([r[4] for r in rows if r[0] in recent])
print(f"\n  LAST 365 DATES ({dates[-365]} -> {dates[-1]}): n={len(nr)}")
print(f"    fee={ar.mean():.3f}  LVR(k=1)={lr_.mean():.3f}  net={nr.mean():+.3f} bp/day "
      f"({nr.mean()*365/100:+.2f}%/yr)  fee/LVR={ar.mean()/lr_.mean():.3f}")
json.dump({"pt":pt,"lo":float(lo),"hi":float(hi),"n":len(rows),"clusters":len(dates),
           "MDE":MDE,"sd":sd_net}, open(f"{S}/gate3.json","w"))
