import sys, json
import numpy as np
sys.path.insert(0, '/home/anont/meme/.combo2way')
from engine import *

D = json.load(open('/home/anont/meme/.combo2way/sweep_all.json'))
rows = [r for r in D['rows'] if r.get('va_mean') is not None]
C = D['ctrl']
ctr_m, cva_m = C['train']['mean'], C['val']['mean']
ctr_d, cva_d = C['train']['median'], C['val']['median']

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

tm = np.array([r['tr_mean'] for r in rows]); vm = np.array([r['va_mean'] for r in rows])
td = np.array([r['tr_med'] for r in rows]);  vd = np.array([r['va_med'] for r in rows])
vk = np.array([r['va_k'] for r in rows]);    vn = np.array([r['va_n'] for r in rows])
tk = np.array([r['tr_k'] for r in rows]);    tn = np.array([r['tr_n'] for r in rows])

print('=== FULL CONJUNCTION: mean AND median beat control on BOTH splits ===')
cond = ((tm > ctr_m) & (vm > cva_m) & (td > ctr_d) & (vd > cva_d) &
        (tn >= 40) & (vn >= 40) & (tk >= 20) & (vk >= 20))
sel = np.flatnonzero(cond)
base = (((vm > cva_m) & (vd > cva_d) & (vn >= 40) & (vk >= 20)).mean())
print('survivors = %d of %d   | validate-side base rate alone = %.3f' % (len(sel), len(rows), base))

print('\n%-6s %-10s %-3s %-10s %-3s %8s %8s %8s %8s %5s %5s %6s %6s %6s' %
      ('sch', 'A', 'ai', 'B', 'bi', 'trMean', 'vaMean', 'trMed', 'vaMed', 'n', 'k',
       'boot95lo', 'p0', 'pEdge'))
res = []
for ix in sel[np.argsort(-vm[sel])]:
    r = rows[ix]
    s = score(greedy(rebuild(r, 'val')))
    if s is None:
        continue
    lo, p0 = boot_lo(s['per_mint'], B=4000, seed=int(ix) % 9999)
    rng = np.random.default_rng(999 + int(ix) % 9999)
    pm = s['per_mint']; k = len(pm)
    bm = pm[rng.integers(0, k, size=(4000, k))].mean(axis=1)
    p_edge = float((bm <= cva_m).mean())
    res.append((r, s, lo, p0, p_edge))
    print('%-6s %-10s %-3s %-10s %-3s %+7.1f%% %+7.1f%% %+7.1f%% %+7.1f%% %5d %5d %+6.1f%% %6.3f %6.3f'
          % (r['sch'], r['a'], r['ai'], str(r['b']), str(r['bi']), 100 * r['tr_mean'],
             100 * s['mean'], 100 * r['tr_med'], 100 * s['median'], s['n'], s['k'],
             100 * lo, p0, p_edge))

if res:
    ps = np.array([z[4] for z in res])
    mfam = int(((tm > ctr_m) & (td > ctr_d)).sum())
    order = np.argsort(ps)
    thr = 0.10 * np.arange(1, len(ps) + 1) / max(1, mfam)
    passed = ps[order] <= thr
    npass = (np.max(np.flatnonzero(passed)) + 1) if passed.any() else 0
    print('\nBH-FDR q=0.10 over the %d-cell train-stage family: %d survive' % (mfam, npass))
    print('smallest p_edge = %.3f ; Bonferroni threshold = %.2e' % (ps.min(), 0.05 / mfam))

    # robustness of the single best candidate
    best = res[int(np.argmin(ps))]
    r, s = best[0], best[1]
    print('\n--- robustness of best conjunction cell: %s %s[%s] x %s[%s] ---'
          % (r['sch'], r['a'], r['ai'], r['b'], r['bi']))
    for toll in (0.0114, 0.025):
        for dc in (-0.30, -0.50, -1.00):
            sv = score(greedy(rebuild(r, 'val')), toll=toll, dropcharge=dc)
            st = score(greedy(rebuild(r, 'train')), toll=toll, dropcharge=dc)
            cv = ev(SIG_VA, toll=toll, dropcharge=dc)
            print('toll=%.4f drop=%.2f  train %+7.1f%%  val %+7.1f%% (control %+7.1f%%)  vaMed %+6.1f%% res=%.3f'
                  % (toll, dc, 100 * st['mean'], 100 * sv['mean'], 100 * cv['mean'],
                     100 * sv['median'], sv['res']))
else:
    print('\nNo cell satisfies the full conjunction.')

# ---- how big is the split-to-split noise floor on the MEAN? ----
print('\n=== NOISE FLOOR: random 50/50 mint re-splits of the SAME unconditional strategy ===')
rng = np.random.default_rng(3)
allm = np.arange(NM)
diffs = []
acc_all = greedy(SIG)
g = GROSS[acc_all]
r_all = np.where(np.isnan(g), -0.30, (1 + g) * (1 - 0.0114) - 1)
m_all = MID[acc_all]
cnt = np.bincount(m_all, minlength=NM).astype(float)
tot = np.bincount(m_all, weights=r_all, minlength=NM)
live = np.flatnonzero(cnt > 0)
pm_all = tot[live] / cnt[live]
for _ in range(2000):
    p = rng.permutation(len(live))
    h = len(live) // 2
    diffs.append(pm_all[p[:h]].mean() - pm_all[p[h:]].mean())
diffs = np.array(diffs)
print('|half-vs-half mean difference| on the SAME strategy: p50=%.1fpp p90=%.1fpp p99=%.1fpp'
      % tuple(100 * np.percentile(np.abs(diffs), [50, 90, 99])))
print('observed train-vs-validate control gap = %.1fpp' % (100 * abs(cva_m - ctr_m)))
