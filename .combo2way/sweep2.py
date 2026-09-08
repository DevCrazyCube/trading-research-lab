import sys, json, itertools, time
import numpy as np
sys.path.insert(0, '/home/anont/meme/.combo2way')
from engine import *

t0 = time.time()
NF = len(FEAT)
Xtr, Xva = X[SIG_TR], X[SIG_VA]

# ---------- bin codes from TRAIN quantiles only ----------
SCHEMES = {'half': 2, 'ter': 3, 'quart': 4, 'quin': 5}
CODES, EDGES = {}, {}
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
        if len(e) == 0:
            continue
        ed[FEAT[f]] = [float(v) for v in e]
        a, b = Xtr[:, f], Xva[:, f]
        ctr[:, f] = np.where(np.isfinite(a), np.searchsorted(e, a, side='right'), -1)
        cva[:, f] = np.where(np.isfinite(b), np.searchsorted(e, b, side='right'), -1)
    CODES[name] = (ctr, cva)
    EDGES[name] = ed

# ---------- threshold (WIDE half-plane) family ----------
QS = [0.2, 0.4, 0.6, 0.8]
THR = {}
Ttr = np.zeros((len(SIG_TR), NF, 8), bool)
Tva = np.zeros((len(SIG_VA), NF, 8), bool)
THR_LBL = []
for qi, qv in enumerate(QS):
    THR_LBL.append(('<=', qv)); THR_LBL.append(('>', qv))
for f in range(NF):
    col = Xtr[:, f]; fin = np.isfinite(col)
    if fin.sum() < 500:
        continue
    cuts = np.quantile(col[fin], QS)
    THR[FEAT[f]] = [float(v) for v in cuts]
    a, b = Xtr[:, f], Xva[:, f]
    fa, fb = np.isfinite(a), np.isfinite(b)
    for qi, cv in enumerate(cuts):
        Ttr[:, f, 2 * qi] = fa & (a <= cv);   Ttr[:, f, 2 * qi + 1] = fa & (a > cv)
        Tva[:, f, 2 * qi] = fb & (b <= cv);   Tva[:, f, 2 * qi + 1] = fb & (b > cv)

CTRL = {}
for sp, sel in (('train', SIG_TR), ('val', SIG_VA)):
    s = ev(sel)
    CTRL[sp] = dict(mean=s['mean'], median=s['median'], n=s['n'], k=s['k'], res=s['res'])
print('CONTROL train %+.3f%% med %+.2f%% | val %+.3f%% med %+.2f%%' % (
    100 * CTRL['train']['mean'], 100 * CTRL['train']['median'],
    100 * CTRL['val']['mean'], 100 * CTRL['val']['median']), flush=True)

MIN_N, MIN_K = 30, 12
rows = []
swept = 0

def cell(sel_tr, sel_va, rec):
    global swept
    swept += 1
    if len(sel_tr) < MIN_N:
        return
    st = score(greedy(sel_tr))
    if st is None or st['n'] < MIN_N or st['k'] < MIN_K:
        return
    sv = score(greedy(sel_va))
    rec.update(tr_mean=st['mean'], tr_med=st['median'], tr_n=st['n'], tr_k=st['k'],
               tr_res=st['res'])
    if sv is None:
        rec.update(va_mean=None)
    else:
        rec.update(va_mean=sv['mean'], va_med=sv['median'], va_n=sv['n'],
                   va_k=sv['k'], va_res=sv['res'])
    rows.append(rec)

# ---- quantile-cell families ----
for name, q in SCHEMES.items():
    ctr, cva = CODES[name]
    for f in range(NF):
        for i in range(q):
            cell(SIG_TR[ctr[:, f] == i], SIG_VA[cva[:, f] == i],
                 dict(kind='1w', sch=name, a=FEAT[f], ai=i, b=None, bi=None))
    for fa, fb in itertools.combinations(range(NF), 2):
        at, bt = ctr[:, fa], ctr[:, fb]
        av, bv = cva[:, fa], cva[:, fb]
        for i in range(q):
            mi_t, mi_v = at == i, av == i
            if mi_t.sum() < MIN_N:
                swept += q
                continue
            for jj in range(q):
                cell(SIG_TR[mi_t & (bt == jj)], SIG_VA[mi_v & (bv == jj)],
                     dict(kind='2w', sch=name, a=FEAT[fa], ai=i, b=FEAT[fb], bi=jj))
    print('%s done swept=%d rows=%d %.0fs' % (name, swept, len(rows), time.time() - t0), flush=True)

# ---- threshold half-plane family (widest regions) ----
for fa, fb in itertools.combinations(range(NF), 2):
    if FEAT[fa] not in THR or FEAT[fb] not in THR:
        continue
    for u in range(8):
        mt, mv = Ttr[:, fa, u], Tva[:, fa, u]
        if mt.sum() < MIN_N:
            swept += 8
            continue
        for w in range(8):
            cell(SIG_TR[mt & Ttr[:, fb, w]], SIG_VA[mv & Tva[:, fb, w]],
                 dict(kind='thr', sch='thr', a=FEAT[fa], ai=u, b=FEAT[fb], bi=w))
print('thr done swept=%d rows=%d %.0fs' % (swept, len(rows), time.time() - t0), flush=True)

json.dump(dict(swept=swept, ctrl=CTRL, edges=EDGES, thr=THR, thr_lbl=THR_LBL, rows=rows),
          open('/home/anont/meme/.combo2way/sweep_all.json', 'w'))

tm = np.array([r['tr_mean'] for r in rows])
vm = np.array([r['va_mean'] if r.get('va_mean') is not None else np.nan for r in rows])
print('=== SWEPT %d cells, %d evaluable on train ===' % (swept, len(rows)))
print('train-mean pct: p05=%+.1f p25=%+.1f p50=%+.1f p75=%+.1f p95=%+.1f max=%+.1f'
      % tuple(100 * np.percentile(tm, [5, 25, 50, 75, 95, 100])))
ok = np.isfinite(vm)
print('val-mean pct  : p05=%+.1f p25=%+.1f p50=%+.1f p75=%+.1f p95=%+.1f max=%+.1f'
      % tuple(100 * np.percentile(vm[ok], [5, 25, 50, 75, 95, 100])))
print('corr(train_mean, val_mean) over all cells = %.4f' % np.corrcoef(tm[ok], vm[ok])[0, 1])
tmed = np.array([r['tr_med'] for r in rows])
vmed = np.array([r.get('va_med', np.nan) for r in rows], dtype=float)
ok2 = np.isfinite(vmed)
print('corr(train_med, val_med) = %.4f' % np.corrcoef(tmed[ok2], vmed[ok2])[0, 1])
print('elapsed %.0fs' % (time.time() - t0))
