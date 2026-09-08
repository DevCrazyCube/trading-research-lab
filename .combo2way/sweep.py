import sys, json, itertools, time
import numpy as np
sys.path.insert(0, '/home/anont/meme/.combo2way')
from engine import *

t0 = time.time()
NF = len(FEAT)
Xtr, Xva = X[SIG_TR], X[SIG_VA]

# ---- bin edges from TRAIN ONLY, applied to both splits ----
SCHEMES = {'half': 2, 'ter': 3, 'quin': 5}
CODES = {}
EDGES = {}
for name, q in SCHEMES.items():
    ctr = np.full((len(SIG_TR), NF), -1, np.int8)
    cva = np.full((len(SIG_VA), NF), -1, np.int8)
    ed = {}
    for f in range(NF):
        col = Xtr[:, f]
        fin = np.isfinite(col)
        if fin.sum() < 500:
            continue
        e = np.unique(np.quantile(col[fin], np.linspace(0, 1, q + 1)[1:-1]))
        ed[FEAT[f]] = [float(v) for v in e]
        if len(e) == 0:
            continue
        a = Xtr[:, f]; b = Xva[:, f]
        ctr[:, f] = np.where(np.isfinite(a), np.searchsorted(e, a, side='right'), -1)
        cva[:, f] = np.where(np.isfinite(b), np.searchsorted(e, b, side='right'), -1)
    CODES[name] = (ctr, cva)
    EDGES[name] = ed

# ---- controls (same split, same structure, ALL bars = random-entry control) ----
CTRL = {}
for sp, sel in (('train', SIG_TR), ('val', SIG_VA)):
    s = ev(sel)
    CTRL[sp] = dict(mean=s['mean'], median=s['median'], n=s['n'], k=s['k'], res=s['res'])
print('control train %+.3f%% (n=%d k=%d) | val %+.3f%% (n=%d k=%d)' % (
    100 * CTRL['train']['mean'], CTRL['train']['n'], CTRL['train']['k'],
    100 * CTRL['val']['mean'], CTRL['val']['n'], CTRL['val']['k']), flush=True)

MIN_N, MIN_K = 30, 12
rows = []
swept = 0

def run(sel, need_pm=False):
    a = greedy(sel)
    return score(a)

for name, q in SCHEMES.items():
    ctr, cva = CODES[name]
    # ---- 1-way ----
    for f in range(NF):
        for i in range(q):
            swept += 1
            sel = SIG_TR[ctr[:, f] == i]
            if len(sel) < MIN_N:
                continue
            st = run(sel)
            if st is None or st['n'] < MIN_N or st['k'] < MIN_K:
                continue
            rows.append(dict(kind='1w', sch=name, a=FEAT[f], ai=i, b=None, bi=None,
                             tr_mean=st['mean'], tr_med=st['median'], tr_n=st['n'],
                             tr_k=st['k'], tr_res=st['res']))
    # ---- 2-way ----
    for fa, fb in itertools.combinations(range(NF), 2):
        ca_t, cb_t = ctr[:, fa], ctr[:, fb]
        for i in range(q):
            mi = ca_t == i
            if mi.sum() < MIN_N:
                swept += q
                continue
            for jj in range(q):
                swept += 1
                sel = SIG_TR[mi & (cb_t == jj)]
                if len(sel) < MIN_N:
                    continue
                st = run(sel)
                if st is None or st['n'] < MIN_N or st['k'] < MIN_K:
                    continue
                rows.append(dict(kind='2w', sch=name, a=FEAT[fa], ai=i,
                                 b=FEAT[fb], bi=jj,
                                 tr_mean=st['mean'], tr_med=st['median'],
                                 tr_n=st['n'], tr_k=st['k'], tr_res=st['res']))
    print('%s done: swept=%d rows=%d  %.0fs' % (name, swept, len(rows), time.time() - t0), flush=True)

json.dump(dict(swept=swept, ctrl=CTRL, edges=EDGES, rows=rows),
          open('/home/anont/meme/.combo2way/train_sweep.json', 'w'))

tm = np.array([r['tr_mean'] for r in rows])
print('TRAIN sweep: cells_swept=%d cells_evaluable=%d' % (swept, len(rows)))
print('train-mean distribution across cells: p05=%+.2f%% p25=%+.2f%% p50=%+.2f%% p75=%+.2f%% p95=%+.2f%% max=%+.2f%%'
      % tuple(100 * np.percentile(tm, [5, 25, 50, 75, 95, 100])))
print('cells with tr_mean>0: %d (%.1f%%)' % ((tm > 0).sum(), 100 * (tm > 0).mean()))
print('cells beating train control by >5pp: %d' % ((tm > CTRL['train']['mean'] + 0.05).sum()))
print('elapsed %.0fs' % (time.time() - t0))
