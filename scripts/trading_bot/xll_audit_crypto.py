#!/usr/bin/env python3
"""LOOKAHEAD AUDIT for the XLL crypto sweep -- same construction as the equity one.

Runs at a coarse frequency (1h and 4h) so two contexts fit in memory on a contended box; the
formulas are frequency-parameterised, so a leak in a 5m variant shows up in its 1h twin.
"""
import numpy as np, sys
sys.path.insert(0, "/home/anont/meme/scripts/trading_bot")
import xll_sweep_crypto as X

CUT = 0.65
for FREQ in (12, 48):
    a = X.build_ctx(FREQ)
    b = X.build_ctx(FREQ, truncate_frac=CUT)
    cut = int(a.r.shape[1] * CUT) - int(70 * 24 * 60 / (5 * FREQ))   # clear of the 60d beta seam
    print(f"[freq={FREQ}] T={a.r.shape[1]} prefix=[0,{cut})", flush=True)
    fails = []
    for name, f, desc, fn in X.make_configs():
        try:
            Wa = np.nan_to_num(fn(a))[:, :cut]; Wb = np.nan_to_num(fn(b))[:, :cut]
        except Exception as e:
            print(f"  SKIP {name}: {e}"); continue
        rel = float(np.abs(Wa - Wb).max() / max(np.abs(Wa).max(), 1e-12))
        if rel >= 1e-6: fails.append((name, rel))
        print(f"  {'OK  ' if rel < 1e-6 else 'LEAK'} {name:28s} max_rel={rel:.2e}", flush=True)
    print(f"[freq={FREQ}] AUDIT:", "CLEAN" if not fails else f"{len(fails)} LEAKING: {fails}", flush=True)
    del a, b
