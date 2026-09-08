import sys, pickle, time, collections, os
sys.path.insert(0, '/home/anont/meme/.scr_fc3')
import numpy as np
from engine import (build_hold, evaluate, CFS, CF_TRAIN, CF_VALID, GATES, HOLDS,
                    VARIANTS, POSITIONS, MIN_CLUSTERS, MIN_TRADES, boot_lo, MIN_MCAP)

t0 = time.time()
rows = []
for H in HOLDS:
    STR, CAND = build_hold(H)
    for v in VARIANTS:
        for p in POSITIONS:
            st = STR[(v, p)]
            for g in GATES:
                bt = evaluate(st, CAND, CF_TRAIN['all'], g)
                bv = evaluate(st, CAND, CF_VALID['all'], g)
                for cf in CFS:
                    rt = evaluate(st, CAND, CF_TRAIN[cf], g)
                    if not rt or rt['cl'] < MIN_CLUSTERS or rt['n'] < MIN_TRADES:
                        continue
                    rv = evaluate(st, CAND, CF_VALID[cf], g)
                    if not rv or rv['cl'] < MIN_CLUSTERS or rv['n'] < MIN_TRADES:
                        continue
                    rows.append((H, v, p, g, cf, rt['mean'], rt['med'], rt['n'], rt['cl'],
                                 rv['mean'], rv['med'], rv['n'], rv['cl'], rv['res'],
                                 bt['mean'] if bt else np.nan, bv['mean'] if bv else np.nan))
    print('H=%d rows=%d t=%.1f' % (H, len(rows), time.time() - t0), flush=True)
pickle.dump(rows, open('/home/anont/meme/.scr_fc3/joint_%d.pkl' % int(MIN_MCAP), 'wb'))

tm = np.array([r[5] for r in rows]); vm = np.array([r[9] for r in rows])
print('\ncells with both sides eligible: %d   MIN_MCAP=%g' % (len(rows), MIN_MCAP))
print('train mean of cell means %+.4f | validate %+.4f' % (tm.mean(), vm.mean()))
print('frac train>0 %.4f | frac validate>0 %.4f | frac BOTH>0 %.4f'
      % ((tm > 0).mean(), (vm > 0).mean(), ((tm > 0) & (vm > 0)).mean()))
print('best validate mean overall %+.4f | best train %+.4f' % (vm.max(), tm.max()))
print('corr(train,validate) across cells = %.3f' % np.corrcoef(tm, vm)[0, 1])
both = [r for r in rows if r[5] > 0 and r[9] > 0]
print('cells positive on BOTH: %d' % len(both))
for r in sorted(both, key=lambda r: -r[9])[:25]:
    print('  T%+.4f V%+.4f(med%+.4f) vn=%d vk=%d ctrlT%+.4f ctrlV%+.4f | H=%d %s %s %s %s'
          % (r[5], r[9], r[10], r[11], r[12], r[5] - r[14], r[9] - r[15], r[0], r[1], r[2], r[3], r[4]))
# top validate cells regardless of train (upper bound on the surface, selection-contaminated)
print('\ntop validate cells irrespective of train sign:')
for r in sorted(rows, key=lambda r: -r[9])[:15]:
    print('  T%+.4f V%+.4f vn=%d vk=%d | H=%d %s %s %s %s' % (r[5], r[9], r[11], r[12], r[0], r[1], r[2], r[3], r[4]))
print('elapsed', time.time() - t0)
