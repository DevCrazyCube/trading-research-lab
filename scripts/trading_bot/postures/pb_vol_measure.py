#!/usr/bin/env python3
"""POSTURE B / step 1: MEASURE realized volatility from the repo's own
survivorship-complete Binance USD-M panel. Nothing here is assumed.

LVR (Milionis-Moallemi-Roughgarden-Zhang 2022, arXiv:2208.06046) for a
constant-product AMM is  sigma^2 / 8  per unit time, on the CPMM-equivalent
(virtual) position value.  We need sigma; we measure it.
"""
import csv, math, sys
from collections import defaultdict
import numpy as np

PANEL = "/home/anont/meme/research/data/t23_cache/panel/perp_daily.csv"
SYMS = ["ETHUSDT", "BTCUSDT", "SOLUSDT"]

rows = defaultdict(list)
with open(PANEL) as f:
    for r in csv.DictReader(f):
        if r["symbol"] in SYMS:
            rows[r["symbol"]].append((int(r["day_ms"]), float(r["close"]), float(r["quote_volume"])))

print(f"panel: {PANEL}")
out = {}
for s in SYMS:
    d = sorted(rows[s])
    if not d:
        print(f"  {s}: ABSENT"); continue
    ms = np.array([x[0] for x in d]); px = np.array([x[1] for x in d])
    lr = np.diff(np.log(px))
    n = len(lr)
    def ann(x):
        sd = float(np.std(x, ddof=1))
        return sd, sd*math.sqrt(365.0)
    sd_all, ann_all = ann(lr)
    sd_365, ann_365 = ann(lr[-365:])
    sd_90,  ann_90  = ann(lr[-90:])
    import datetime as dt
    t0 = dt.datetime.utcfromtimestamp(ms[0]/1000).date()
    t1 = dt.datetime.utcfromtimestamp(ms[-1]/1000).date()
    print(f"\n  {s}: n_days={n+1} returns={n}  {t0} -> {t1}")
    print(f"    full   sigma_d={sd_all*100:.4f}%/day  ann={ann_all*100:.2f}%   LVR=sigma^2/8 -> {sd_all**2/8*1e4:.4f} bp/day = {sd_all**2/8*365*100:.2f} %/yr")
    print(f"    last365 sigma_d={sd_365*100:.4f}%/day  ann={ann_365*100:.2f}%   LVR -> {sd_365**2/8*1e4:.4f} bp/day = {sd_365**2/8*365*100:.2f} %/yr")
    print(f"    last90  sigma_d={sd_90*100:.4f}%/day  ann={ann_90*100:.2f}%   LVR -> {sd_90**2/8*1e4:.4f} bp/day = {sd_90**2/8*365*100:.2f} %/yr")
    out[s] = dict(n=n, sd_all=sd_all, sd_365=sd_365, sd_90=sd_90)

# verify the LVR engine against the published worked example:
# "5% daily vol, 30bp fee -> LVR 3.125 bp/day, break-even daily volume 10.4% of pool"
sd = 0.05; f = 0.003
lvr = sd**2/8
print(f"\nENGINE CHECK vs published example (5%/day vol, 30bp fee):")
print(f"  LVR = {lvr*1e4:.4f} bp/day (published: 3.125 bp/day)")
print(f"  break-even daily volume/V = {lvr/f*100:.2f}% (published: 10.4%)")
print(f"  annualised LVR = {lvr*365*100:.2f}%/yr (published: ~11%)")
