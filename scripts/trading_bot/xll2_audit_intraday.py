#!/usr/bin/env python3
"""Automated LOOKAHEAD AUDIT for the XLL-2 intraday block.

Everything past 65% of the sample is replaced with reversed, rescaled prices. Any config whose
weights on the surviving PREFIX change at all is reading the future. Same test that caught the
N1 bug in the first XLL sweep.

Fingerprint = every 100th bar of the prefix weight matrix (dense enough that no real change
could hide, small enough to hold 49 configs in RAM).
"""
from __future__ import annotations
import importlib.util, json
import numpy as np

SRC = "/home/anont/meme/scripts/trading_bot/xll2_sweep_intraday.py"
OUT = "/home/anont/meme/research/trading_bot/SWEEP_xll_leadlag_v2_lookahead_audit.json"
FRAC = 0.65


def load():
    spec = importlib.util.spec_from_file_location("xll2", SRC)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def fingerprints(m, truncate):
    c = m.build_ctx(truncate_frac=truncate)
    cut = int(c.r.shape[1] * FRAC)
    fp = {}
    for name, desc, fn, hold in m.make_configs(c):
        W = fn(c)
        _, Wn = m.score(c, W, hold)
        fp[name] = np.ascontiguousarray(Wn[:, :cut:100]).astype(np.float32)
        del W, Wn
    del c
    return fp


def main():
    m = load()
    print("clean pass...", flush=True)
    a = fingerprints(m, None)
    print("corrupted-tail pass...", flush=True)
    b = fingerprints(m, FRAC)
    rows = []
    for k in a:
        d = float(np.max(np.abs(a[k] - b[k]))) if k in b else float("nan")
        scale = float(np.max(np.abs(a[k]))) or 1.0
        rows.append(dict(name=k, max_abs_diff=d, rel=d / scale, clean=(d <= 1e-9)))
        print(f"  {k:26s} max|dW|={d:.3e} {'CLEAN' if d <= 1e-9 else 'LOOKAHEAD'}", flush=True)
    n_bad = sum(1 for r in rows if not r["clean"])
    json.dump(dict(truncate_frac=FRAC, n_configs=len(rows), n_lookahead=n_bad, rows=rows),
              open(OUT, "w"), indent=1)
    print(f"{len(rows)-n_bad}/{len(rows)} CLEAN -> {OUT}")


if __name__ == "__main__":
    main()
