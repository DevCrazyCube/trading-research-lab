#!/usr/bin/env python3
"""LOOKAHEAD AUDIT for the XLL equity sweep.

Builds the context twice on a reduced universe -- once on the real panel, once with everything
from 65% of the sample onward replaced by reversed, rescaled prices -- and checks that every
config's weights on the surviving PREFIX are bit-identical. A config that fails is reading the
future. This is the check that caught N1's contemporaneous leader basket.
"""
import numpy as np, sys
sys.path.insert(0, "/home/anont/meme/scripts/trading_bot")
import xll_sweep_equity as X

CUT_FRAC = 0.65
SUB = 500

a = X.build_ctx(subsample=SUB)
b = X.build_ctx(subsample=SUB, truncate_frac=CUT_FRAC)
cut = int(a.rcc.shape[1] * CUT_FRAC) - 260          # beta lookback is 250d; stay clear of the seam
print(f"universe={a.rcc.shape[0]} T={a.rcc.shape[1]} prefix compared = [0,{cut})", flush=True)

fails = []
for name, desc, fn, which in X.make_configs(a):
    Wa = np.nan_to_num(fn(a))[:, :cut]
    Wb = np.nan_to_num(fn(b))[:, :cut]
    d = np.abs(Wa - Wb).max()
    scale = max(np.abs(Wa).max(), 1e-12)
    rel = float(d / scale)
    tag = "OK  " if rel < 1e-6 else "LEAK"
    if rel >= 1e-6:
        fails.append((name, rel))
    print(f"  {tag} {name:24s} max_rel_weight_change={rel:.2e}", flush=True)
print("\nAUDIT:", "CLEAN" if not fails else f"{len(fails)} LEAKING: {fails}")
