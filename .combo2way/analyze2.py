import sys, json, itertools
import numpy as np
sys.path.insert(0, '/home/anont/meme/.combo2way')
from engine import *

D = json.load(open('/home/anont/meme/.combo2way/sweep_all.json'))
rows = [r for r in D['rows'] if r.get('va_mean') is not None]
C = D['ctrl']
ctr_m, cva_m = C['train']['mean'], C['val']['mean']
ctr_d, cva_d = C['train']['median'], C['val']['median']
NFEAT = FEAT

def rebuild(r, split):
    sigs = SIG_TR if split == 'train' else SIG_VA
    Xs = X[sigs]
    m = np.ones(len(sigs), bool)
    for fname, code in ((r['a'], r['ai']), (r['b'], r['bi'])):
        if fname is None:
            continue
        f = FEAT.index(fname)
        col = Xs[:, f]
        fin = np.isfinite(col)
        if r['sch'] == 'thr':
            cv = D['thr'][fname][code // 2]
            mm = fin & ((col <= cv) if code % 2 == 0 else (col > cv))
        else:
            e = np.array(D['edges'][r['sch']][fname])
            mm = fin & (np.searchsorted(e, np.where(fin, col, 0.0), side='right') == code)
        m &= mm
    return sigs[m]

td = np.array([r['tr_med'] for r in rows])
vd = np.array([r['va_med'] for r in rows])
tm = np.array([r['tr_mean'] for r in rows])
vm = np.array([r['va_mean'] for r in rows])
vk = np.array([r['va_k'] for r in rows])
vn = np.array([r['va_n'] for r in rows])
tk = np.array([r['tr_k'] for r in rows])

print('=== MEDIAN TRACK: cells with train_med>0 AND val_med>0 ===')
sel = np.flatnonzero((td > 0) & (vd > 0) & (vn >= 40) & (vk >= 15) & (tk >= 15))
print('count = %d (of %d evaluable)' % (len(sel), len(rows)))
print('%-6s %-10s %-3s %-10s %-3s %8s %8s %8s %8s %5s %5s' %
      ('sch', 'A', 'ai', 'B', 'bi', 'trMed', 'vaMed', 'trMean', 'vaMean', 'n', 'k'))
for ix in sel[np.argsort(-vd[sel])][:30]:
    r = rows[ix]
    print('%-6s %-10s %-3s %-10s %-3s %+7.1f%% %+7.1f%% %+7.1f%% %+7.1f%% %5d %5d' %
          (r['sch'], r['a'], r['ai'], str(r['b']), str(r['bi']),
           100 * r['tr_med'], 100 * r['va_med'], 100 * r['tr_mean'],
           100 * r['va_mean'], r['va_n'], r['va_k']))

print('\n=== best validate MEDIAN cells overall (any train sign) ===')
o = np.argsort(-vd)[:15]
for ix in o:
    r = rows[ix]
    print('%-6s %-10s %-3s %-10s %-3s trMed %+7.1f%% vaMed %+7.1f%% vaMean %+8.1f%% n=%d k=%d' %
          (r['sch'], r['a'], r['ai'], str(r['b']), str(r['bi']),
           100 * r['tr_med'], 100 * r['va_med'], 100 * r['va_mean'], r['va_n'], r['va_k']))

# ---------- 1-way quintile response surface (the reusable map) ----------
print('\n=== 1-WAY QUINTILE SURFACE (mint-equal, toll 1.14%%, dropout -30%%) ===')
print('feature    q  trMean  vaMean  trMed   vaMed   vaN  vaK')
Xtr, Xva = X[SIG_TR], X[SIG_VA]
for f, fn in enumerate(FEAT):
    if fn not in D['edges']['quin']:
        continue
    e = np.array(D['edges']['quin'][fn])
    for q in range(len(e) + 1):
        a, b = Xtr[:, f], Xva[:, f]
        fa, fb = np.isfinite(a), np.isfinite(b)
        mt = fa & (np.searchsorted(e, np.where(fa, a, 0.0), side='right') == q)
        mv = fb & (np.searchsorted(e, np.where(fb, b, 0.0), side='right') == q)
        st = score(greedy(SIG_TR[mt])); sv = score(greedy(SIG_VA[mv]))
        if st is None or sv is None:
            continue
        print('%-10s %d %+6.1f%% %+6.1f%% %+6.1f%% %+6.1f%% %4d %4d' %
              (fn, q, 100 * st['mean'], 100 * sv['mean'], 100 * st['median'],
               100 * sv['median'], sv['n'], sv['k']))

# ---------- top mean cells vs count-matched RANDOM entries on validate ----------
print('\n=== top-10 mean cells vs COUNT-MATCHED RANDOM entries (validate) ===')
surv = json.load(open('/home/anont/meme/.combo2way/survivors.json'))
rng = np.random.default_rng(7)
for z in surv[:10]:
    r = z['r']
    acc = greedy(rebuild(r, 'val'))
    s = score(acc)
    per_mint_n = np.bincount(MID[acc], minlength=NM)
    sims = []
    for b in range(200):
        pick = []
        for m in np.flatnonzero(per_mint_n):
            pool = SIG_VA[MID[SIG_VA] == m]
            if len(pool) == 0:
                continue
            take = min(len(pool), per_mint_n[m] * 3)
            pick.append(rng.choice(pool, size=take, replace=False))
        if not pick:
            continue
        sel2 = np.sort(np.concatenate(pick))
        ss = score(greedy(sel2))
        if ss:
            sims.append(ss['mean'])
    sims = np.array(sims)
    print('%-6s %-9s %-2s %-9s %-2s cell=%+8.1f%%  matched-random mean=%+7.1f%% (p95=%+7.1f%%)  pct-rank=%.3f'
          % (r['sch'], r['a'], r['ai'], str(r['b']), str(r['bi']), 100 * s['mean'],
             100 * sims.mean(), 100 * np.percentile(sims, 95),
             float((sims < s['mean']).mean())))
