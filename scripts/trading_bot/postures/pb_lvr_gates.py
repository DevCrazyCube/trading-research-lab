#!/usr/bin/env python3
"""POSTURE B / CLM market making: GATES 1-3 + economics.

STRUCTURE OF THE TEST (declared before any effect is read)
----------------------------------------------------------
For a Uniswap v3 LP, per day, on DEPOSITED capital:
    net = apyBase_daily  -  k * sigma_d^2 / 8
where k = (CPMM-equivalent virtual value of active liquidity) / (deposited TVL)
is the concentration multiplier, and k >= 1 ALWAYS (concentrated liquidity is by
construction at least as dense as full-range).  Therefore

    net  <=  apyBase_daily - sigma_d^2/8            [k = 1 upper bound]

We test that UPPER BOUND.  It is generous to LPing in four separate ways:
  (1) k = 1 (real k > 1 -> real LVR is k times larger),
  (2) apyBase is the POOL-AVERAGE fee yield; a passive LP is crowded by active
      /JIT LPs and earns less (Fritsch & Canidio 2024, sec 3.3),
  (3) sigma^2/8 is the continuous-arbitrage LVR; we do NOT subtract gas,
      rebalancing, or position entry/exit cost here,
  (4) pools are selected on CURRENT TVL >= $20M, i.e. survivors.
If the UPPER BOUND fails, the family is dead a fortiori.  If it passes, that
only fails to kill: k must then be measured.

sigma_d is MEASURED per pair per day as trailing-30d realised vol of the PRICE
RATIO of the two pool assets, from this repo's survivorship-complete Binance
USD-M panel.  Nothing is assumed.
"""
import csv, json, math, os, subprocess, sys, datetime as dt
from collections import defaultdict
import numpy as np

SCRATCH = "/tmp/claude-1000/-home-anont-meme/5d56bbe0-2440-41b7-9176-f7470b1d1b38/scratchpad"
PANEL   = "/home/anont/meme/research/data/t23_cache/panel/perp_daily.csv"
SEED    = 20260903
VOL_WIN = 30

# ---------------- GATE 1: COVERAGE MINIMA, DECLARED BEFORE COUNTING ----------
MIN_POOLS      = 4      # distinct volatile Uniswap v3 Ethereum pools
MIN_DAYS_POOL  = 500    # daily apyBase obs per pool
MIN_DATES      = 700    # distinct dates in the merged panel
MIN_VOL_WIN    = VOL_WIN

# ---------------- GATE 2: POWER PARAMETERS, DECLARED BEFORE EFFECT ----------
ALPHA   = 0.05          # one-sided
POWER   = 0.80
ICC     = 0.30          # conservative, clustered by DATE
Z_A     = 1.6448536269514722   # Phi^-1(0.95)
Z_B     = 0.8416212335729143   # Phi^-1(0.80)

print("="*78)
print("POSTURE B.1  CONCENTRATED-LIQUIDITY MARKET MAKING  (Uniswap v3, Ethereum)")
print("="*78)
print(f"GATE 1 minima declared: >={MIN_POOLS} pools, >={MIN_DAYS_POOL} days/pool, "
      f">={MIN_DATES} dates, >={MIN_VOL_WIN}d vol window")
print(f"GATE 2 params declared: alpha={ALPHA} one-sided, power={POWER}, ICC={ICC} by DATE")
print(f"GATE 3: cluster bootstrap by DATE, 5000 draws, seed {SEED}")

# ---------------- measured volatility from our own panel --------------------
px = defaultdict(dict)
with open(PANEL) as f:
    for r in csv.DictReader(f):
        d = dt.datetime.fromtimestamp(int(r["day_ms"])/1000, dt.UTC).date().isoformat()
        px[r["symbol"]][d] = float(r["close"])
print(f"\npanel: {PANEL}  symbols={len(px)}  (repo's 919-symbol survivorship-complete set)")

def ratio_vol(num, den):
    """trailing-30d realised vol of price ratio num/den, per date. den=None -> USD."""
    if den is None:
        s = px[num]
    else:
        ks = set(px[num]) & set(px[den])
        s = {k: px[num][k]/px[den][k] for k in ks}
    dates = sorted(s)
    lr = {}
    for i in range(1, len(dates)):
        lr[dates[i]] = math.log(s[dates[i]]/s[dates[i-1]])
    ds = sorted(lr)
    out = {}
    for i in range(VOL_WIN, len(ds)):
        w = np.array([lr[d] for d in ds[i-VOL_WIN:i]])   # strictly trailing
        out[ds[i]] = float(np.std(w, ddof=1))
    return out

VOL = {
    "ETHUSD": ratio_vol("ETHUSDT", None),
    "BTCUSD": ratio_vol("BTCUSDT", None),
    "BTCETH": ratio_vol("BTCUSDT", "ETHUSDT"),
}
for k, v in VOL.items():
    print(f"  measured trailing-{VOL_WIN}d ratio vol {k}: n_dates={len(v)}  "
          f"{min(v)} -> {max(v)}  median sigma_d={np.median(list(v.values()))*100:.3f}%/day")
json.dump({k: v for k, v in VOL.items()}, open(f"{SCRATCH}/vol_series.json", "w"))
print(f"\nwrote {SCRATCH}/vol_series.json")
