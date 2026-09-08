#!/usr/bin/env python3
"""Daily OHLCV panel from research/data/orphanflush_cache/vol1d (+vol1d_pick2)."""
import os, zipfile
import numpy as np
from multiprocessing import Pool

BASE = '/home/anont/meme/research/data/orphanflush_cache'
OUT = '/home/anont/meme/research/data/oi0824_cache'
os.makedirs(OUT + '/kl', exist_ok=True)


def do(sym):
    rows = {}
    for sub in ('vol1d', 'vol1d_pick2'):
        d = os.path.join(BASE, sub, sym)
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if not fn.endswith('.zip'):
                continue
            try:
                z = zipfile.ZipFile(os.path.join(d, fn))
                raw = z.read(z.namelist()[0]).decode('utf-8', 'ignore')
            except Exception:
                continue
            for ln in raw.splitlines():
                p = ln.split(',')
                if len(p) < 9 or not p[0].isdigit():
                    continue
                try:
                    t = int(p[0]) // 86400000
                    rows[t] = (t, float(p[1]), float(p[2]), float(p[3]), float(p[4]),
                               float(p[7]), float(p[8]), float(p[10]))
                except ValueError:
                    continue
    if not rows:
        return sym, 0
    A = np.asarray([rows[k] for k in sorted(rows)], np.float64)
    np.savez_compressed(os.path.join(OUT, 'kl', sym + '.npz'), a=A.astype(np.float64))
    return sym, A.shape[0]


if __name__ == '__main__':
    syms = sorted(set(os.listdir(os.path.join(BASE, 'vol1d'))) |
                  set(os.listdir(os.path.join(BASE, 'vol1d_pick2'))))
    with Pool(10) as p:
        r = list(p.imap_unordered(do, syms, chunksize=4))
    print('done', len(r), sum(1 for _, n in r if n > 0))
