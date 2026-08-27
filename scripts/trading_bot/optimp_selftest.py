#!/usr/bin/env python3
"""Harness self-test for the options-implied sweep.

A null result is worth nothing unless the machine that produced it can find an
edge that is really there.  Four probes:

  1. BUY AND HOLD SPY  -- must come back near the known ~0.9 design-window Sharpe.
  2. PLANTED EDGE      -- a signal that is literally next-day's sign, scaled down.
                          Must score enormous at the lag it was planted for.
  3. LAG SENSITIVITY   -- the planted edge must DIE when the entry lag moves off
                          the lag it was planted for.  This is the lag-kill test
                          testing itself.
  4. RANDOM-WALK NULL  -- pure noise signals must produce |t| distributed like the
                          expected-max bar, not systematically above or below it.
"""
from __future__ import annotations

import math
import sys

import numpy as np

sys.path.insert(0, "/home/anont/meme/scripts")
from trading_bot.optimp_sweep import (DESIGN, build_panel, evaluate, stats,
                                      wclip, zc)

dates, IV, PX = build_panel()
n = len(dates)
dt = np.array(dates)
des = ((dt >= DESIGN[0]) & (dt <= DESIGN[1])).astype(float)
ret = np.full(n, np.nan)
ret[1:] = PX["SPY"][1:] / PX["SPY"][:-1] - 1.0
rets = {"SPY": ret}

print(f"panel {n} rows {dates[0]}..{dates[-1]}  design days={int(des.sum())}\n")

# 1. buy and hold
bh = evaluate({"SPY": np.ones(n)}, rets, ["SPY"], 1, np.ones(n))
s = stats(bh, des)
print(f"1. BUY+HOLD SPY design Sharpe={s['sharpe']:.2f} annret={s['ann_ret']:.3f}"
      f"  -> expect ~0.8-1.1")

# 2/3. planted edge at lag 2, read at lags 1..4
#    signal known at close t must predict ret[t+2]; so plant sig[t] = ret[t+2]
plant = np.zeros(n)
plant[:n - 2] = np.sign(np.nan_to_num(ret[2:]))
noise = np.random.default_rng(7).normal(0, 1, n)
sig = 0.25 * plant + noise          # 25% signal, 75% noise
w = {"SPY": wclip(zc(sig))}
print("\n2/3. PLANTED EDGE (planted for lag 2), read at each lag:")
for lag in (1, 2, 3, 4):
    st = stats(evaluate(w, rets, ["SPY"], lag, np.ones(n)), des)
    tag = "  <-- planted here" if lag == 2 else ""
    print(f"    L={lag}  Sharpe={st['sharpe']:7.2f}  t={st['t']:7.2f}{tag}")

# 4. random-walk null: 60 pure-noise signals, same pipeline
rng = np.random.default_rng(11)
ts = []
for _ in range(60):
    z = zc(np.cumsum(rng.normal(0, 1, n)))     # random walk, like a vol index
    ts.append(stats(evaluate({"SPY": wclip(z)}, rets, ["SPY"], 2, np.ones(n)),
                    des)["t"])
ts = np.array(ts)
bar = math.sqrt(2 * math.log(60))
print(f"\n4. RANDOM-WALK NULL, 60 signals, lag 2:")
print(f"    max |t| = {np.abs(ts).max():.2f}   bar sqrt(2 ln 60) = {bar:.2f}")
print(f"    mean t = {ts.mean():.2f}  sd t = {ts.std():.2f}  "
      f"(sd near 1.0 means the t-scale is honest)")
print(f"    n above bar = {(np.abs(ts) > bar).sum()} / 60")
