import sys, json
import numpy as np
sys.path.insert(0, '/home/anont/meme/.combo2way')
from engine import *

D = json.load(open('/home/anont/meme/.combo2way/sweep_all.json'))
rows = [r for r in D['rows'] if r.get('va_mean') is not None]
vm = np.array([r['va_mean'] for r in rows]); vd = np.array([r['va_med'] for r in rows])
tm = np.array([r['tr_mean'] for r in rows]); td = np.array([r['tr_med'] for r in rows])
print('cells: %d' % len(rows))
print('corr(mean, median) within validate  = %.3f' % np.corrcoef(vm, vd)[0, 1])
print('corr(mean, median) within train     = %.3f' % np.corrcoef(tm, td)[0, 1])
print('corr(train_mean, val_mean)          = %.3f' % np.corrcoef(tm, vm)[0, 1])
print('corr(train_med , val_med )          = %.3f' % np.corrcoef(td, vd)[0, 1])

# how much of the validate mean sits in the single best mint per cell?
print('\n=== tail dominance of the unconditional strategy (validate) ===')
acc = greedy(SIG_VA)
g = GROSS[acc]
r = np.where(np.isnan(g), -0.30, (1 + g) * (1 - 0.0114) - 1)
m = MID[acc]
cnt = np.bincount(m, minlength=NM).astype(float)
tot = np.bincount(m, weights=r, minlength=NM)
live = np.flatnonzero(cnt > 0)
pm = tot[live] / cnt[live]
s = np.sort(pm)[::-1]
tot_mean = pm.mean()
print('k=%d mints, mean=%+.1f%%, median=%+.1f%%' % (len(pm), 100 * tot_mean, 100 * np.median(pm)))
for d in (1, 2, 3, 5, 10):
    print('  drop top %2d mint(s): mean -> %+.1f%%' % (d, 100 * np.sort(pm)[::-1][d:].mean()))
print('  top mint contributes %.0f%% of the total per-mint return sum' % (100 * s[0] / s.sum()))
print('  share of mints with a positive net 15m result: %.3f' % (pm > 0).mean())

# minimum detectable effect on the mean, given the observed dispersion
sd = pm.std(ddof=1)
print('\nper-mint sd = %.1f%%  -> se at k=%d is %.1fpp; MDE(80%%,two-sided) = %.0fpp'
      % (100 * sd, len(pm), 100 * sd / np.sqrt(len(pm)), 100 * 2.8 * sd / np.sqrt(len(pm))))
for k in (30, 50, 100, 200, 400, 1000, 5000):
    print('  k=%5d mints -> MDE on the mean = %6.0fpp' % (k, 100 * 2.8 * sd / np.sqrt(k)))
