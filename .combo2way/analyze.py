import sys, json
import numpy as np
sys.path.insert(0, '/home/anont/meme/.combo2way')
from engine import *

D = json.load(open('/home/anont/meme/.combo2way/sweep_all.json'))
rows = [r for r in D['rows'] if r.get('va_mean') is not None]
C = D['ctrl']
ctr_m, cva_m = C['train']['mean'], C['val']['mean']
ctr_d, cva_d = C['train']['median'], C['val']['median']
print('cells swept=%d  evaluable_both=%d' % (D['swept'], len(rows)))
print('controls: train mean %+.3f med %+.3f | val mean %+.3f med %+.3f'
      % (ctr_m, ctr_d, cva_m, cva_d))

tm = np.array([r['tr_mean'] for r in rows])
vm = np.array([r['va_mean'] for r in rows])
td = np.array([r['tr_med'] for r in rows])
vd = np.array([r['va_med'] for r in rows])
vk = np.array([r['va_k'] for r in rows])
vn = np.array([r['va_n'] for r in rows])

# ---------- BASE RATES: does a train-positive cell validate more often than any cell? ----------
base_pos = (vm > cva_m + 0.05).mean()
s1 = (tm > ctr_m + 0.05)
cond_pos = (vm[s1] > cva_m + 0.05).mean()
print('\n--- MEAN track ---')
print('P(val beats val-control by 5pp | any cell)        = %.3f  (n=%d)' % (base_pos, len(rows)))
print('P(val beats val-control by 5pp | train beat by 5pp)= %.3f  (n=%d)' % (cond_pos, s1.sum()))
s1b = tm > 0
print('P(val_mean>0 | any cell) = %.3f ; | train_mean>0 = %.3f (n=%d)'
      % ((vm > 0).mean(), (vm[s1b] > 0).mean(), s1b.sum()))

print('\n--- MEDIAN track ---')
print('best validate median across all cells: %+.2f%%' % (100 * vd.max()))
print('cells with va_med>0: %d ; with va_med > -5%%: %d ; > -10%%: %d'
      % ((vd > 0).sum(), (vd > -0.05).sum(), (vd > -0.10).sum()))
s1d = td > ctr_d + 0.10
print('P(va_med > ctrl+10pp | any) = %.3f ; | train also = %.3f (n=%d)'
      % ((vd > cva_d + 0.10).mean(), (vd[s1d] > cva_d + 0.10).mean(), s1d.sum()))

# ---------- shortlist: train-positive AND validate-positive, with bootstrap ----------
sel = np.flatnonzero(s1 & (vm > cva_m + 0.05) & (vn >= 40) & (vk >= 15))
print('\nstage1&2 survivors (mean track, n>=40 k>=15): %d of %d tested' % (len(sel), len(rows)))

def rebuild(r, split):
    """Rebuild the exact bar mask for a cell on a given split."""
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
            mm = fin & (np.searchsorted(e, np.where(fin, col, 0), side='right') == code)
        m &= mm
    return sigs[m]

out = []
for ix in sel:
    r = rows[ix]
    s = score(greedy(rebuild(r, 'val')))
    if s is None:
        continue
    lo, p0 = boot_lo(s['per_mint'], B=4000, seed=int(ix) % 9999)
    # p vs the val control (edge, not vs zero)
    rng = np.random.default_rng(1234 + int(ix) % 9999)
    pm = s['per_mint']; k = len(pm)
    bm = pm[rng.integers(0, k, size=(4000, k))].mean(axis=1)
    p_edge = float((bm <= cva_m).mean())
    out.append(dict(r=r, va=s, lo=lo, p0=p0, p_edge=p_edge))

out.sort(key=lambda z: z['p_edge'])
M = len(out)
print('\nbootstrapped %d survivors. Bonferroni alpha over %d stage-1 tests = %.2e'
      % (M, int(s1.sum()), 0.05 / max(1, int(s1.sum()))))
# Benjamini-Hochberg over the stage-1 tested family
ps = np.array([z['p_edge'] for z in out])
mfam = int(s1.sum())
bh = np.zeros(M, bool)
order = np.argsort(ps)
thresh = 0.10 * (np.arange(1, M + 1)) / mfam
passed = ps[order] <= thresh
if passed.any():
    kmax = np.max(np.flatnonzero(passed))
    bh[order[:kmax + 1]] = True
print('BH-FDR q=0.10 over the %d-test family: %d survive' % (mfam, bh.sum()))

print('\nTOP 25 by bootstrap p(edge<=control) on VALIDATE:')
print('%-4s %-6s %-10s %-2s %-10s %-2s %8s %8s %8s %8s %5s %5s %7s %7s' %
      ('#', 'sch', 'featA', 'ai', 'featB', 'bi', 'trMean', 'vaMean', 'vaMed', 'boot95lo',
       'n', 'k', 'p0', 'pEdge'))
for i, z in enumerate(out[:25]):
    r = z['r']; s = z['va']
    print('%-4d %-6s %-10s %-2s %-10s %-2s %+7.1f%% %+7.1f%% %+7.1f%% %+7.1f%% %5d %5d %7.3f %7.3f'
          % (i, r['sch'], r['a'], r['ai'], str(r['b']), str(r['bi']),
             100 * r['tr_mean'], 100 * s['mean'], 100 * s['median'], 100 * z['lo'],
             s['n'], s['k'], z['p0'], z['p_edge']))

json.dump([dict(r=z['r'], mean=z['va']['mean'], med=z['va']['median'],
                n=z['va']['n'], k=z['va']['k'], res=z['va']['res'],
                lo=z['lo'], p0=z['p0'], p_edge=z['p_edge']) for z in out],
          open('/home/anont/meme/.combo2way/survivors.json', 'w'))
