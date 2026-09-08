import sys, pickle, collections
sys.path.insert(0, '/home/anont/meme/.scr_fc3')
import numpy as np
from engine import (build_hold, evaluate, CFS, CF_TRAIN, CF_VALID, TRAIN, VALID,
                    GATES, VARIANTS, POSITIONS, FEATS, MINTS)

rng = np.random.default_rng(7)

# ---- 1. distribution of ALL eligible cell means (shape of the surface) ----
D = pickle.load(open('/home/anont/meme/.scr_fc3/train_hits.pkl', 'rb'))
means = np.array([r['mean'] for r in D['allrows']])
print('eligible cells %d  mean=%.4f med=%.4f  frac>0=%.4f' %
      (len(means), means.mean(), np.median(means), (means > 0).mean()))
print('cell-mean pctiles', ' '.join('%+.3f' % x for x in np.percentile(means, [1, 5, 25, 50, 75, 95, 99])))
byv = collections.defaultdict(list)
for r in D['allrows']:
    byv[r['v']].append(r['mean'])
for v in VARIANTS:
    a = np.array(byv[v])
    print('  variant %-11s n=%5d mean=%+.4f med=%+.4f frac>0=%.4f' % (v, len(a), a.mean(), np.median(a), (a > 0).mean()))
byg = collections.defaultdict(list)
for r in D['allrows']:
    byg[r['g']].append(r['mean'])
for g in GATES:
    a = np.array(byg[g])
    if len(a):
        print('  gate    %-12s n=%5d mean=%+.4f med=%+.4f frac>0=%.4f' % (g, len(a), a.mean(), np.median(a), (a > 0).mean()))
byc = collections.defaultdict(list)
for r in D['allrows']:
    byc[r['cf']].append(r['mean'])
print('  --- creator filters, mean over all their eligible cells (TRAIN) ---')
for cf in sorted(byc, key=lambda k: -np.mean(byc[k])):
    a = np.array(byc[cf])
    print('  cf %-12s ncells=%5d mean=%+.4f med=%+.4f frac>0=%.4f' % (cf, len(a), a.mean(), np.median(a), (a > 0).mean()))

# ---- 2. structure-free creator test on canonical cells ----
print('\n=== canonical per-mint outcomes, creator filters, train vs validate ===')
CANON = [(15, 'time', 'flat'), (60, 'time', 'flat'), (240, 'time', 'flat'),
         (15, 'tp50_sl30', 'flat'), (60, 'tp100_sl40', 'flat')]
permint = {}
for H in sorted(set(c[0] for c in CANON)):
    STR, CAND = build_hold(H)
    for (h2, v, p) in CANON:
        if h2 != H:
            continue
        st = STR[(v, p)]
        pm = {}
        for m in MINTS:
            r = evaluate(st, CAND, [m], 'all')
            if r and r['n'] >= 2:
                pm[m] = r['mean']
        permint[(H, v, p)] = pm
        print('cell H=%d %s %s : mints with >=2 trades = %d' % (H, v, p, len(pm)))

rows = []
for cf in CFS:
    if cf == 'all':
        continue
    line = {'cf': cf}
    ok = True
    for key in CANON:
        pm = permint[key]
        tr = [pm[m] for m in CF_TRAIN[cf] if m in pm]
        va = [pm[m] for m in CF_VALID[cf] if m in pm]
        allt = [pm[m] for m in TRAIN if m in pm]
        allv = [pm[m] for m in VALID if m in pm]
        if len(tr) < 10 or len(va) < 10:
            ok = False
            break
        line[key] = (np.mean(tr) - np.mean(allt), np.mean(va) - np.mean(allv), len(tr), len(va))
    if ok:
        rows.append(line)

print('\n%-12s %5s %5s | %s' % ('filter', 'ktr', 'kva', '  '.join('%s%d/%s' % ('H', k[0], k[1][:6]) for k in CANON)))
for line in rows:
    k0 = CANON[0]
    dts = [line[k][0] for k in CANON]
    dvs = [line[k][1] for k in CANON]
    agree = sum(1 for a, b in zip(dts, dvs) if a > 0 and b > 0)
    print('%-12s %5d %5d | %s  | trainpos=%d validpos=%d BOTH=%d' %
          (line['cf'], line[k0][2], line[k0][3],
           '  '.join('%+.3f/%+.3f' % (line[k][0], line[k][1]) for k in CANON),
           sum(1 for x in dts if x > 0), sum(1 for x in dvs if x > 0), agree))

# ---- 3. permutation p-values on validate for filters that agree in >=4 of 5 cells ----
print('\n=== validate permutation tests (mint-level, 5000 draws) ===')
for line in rows:
    dts = [line[k][0] for k in CANON]
    dvs = [line[k][1] for k in CANON]
    agree = sum(1 for a, b in zip(dts, dvs) if a > 0 and b > 0)
    if agree < 4:
        continue
    for key in CANON:
        pm = permint[key]
        va = np.array([pm[m] for m in CF_VALID[line['cf']] if m in pm])
        pool = np.array([pm[m] for m in VALID if m in pm])
        k = len(va)
        draws = np.array([rng.choice(pool, size=k, replace=False).mean() for _ in range(5000)])
        p = float((draws >= va.mean()).mean())
        print('  %-12s %-16s k=%3d  vmean=%+.4f pool=%+.4f  p=%.4f' %
              (line['cf'], 'H%d/%s' % (key[0], key[1]), k, va.mean(), pool.mean(), p))
