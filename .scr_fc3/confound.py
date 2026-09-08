import sys, collections
sys.path.insert(0, '/home/anont/meme/.scr_fc3')
import numpy as np
from engine import build_hold, evaluate, CFS, CF_TRAIN, CF_VALID, TRAIN, VALID, FEATS, MINTS

rng = np.random.default_rng(11)
T0 = min(FEATS[m]['t_create'] for m in MINTS)
T1 = max(FEATS[m]['t_create'] for m in MINTS)
print('create window hours', (T1 - T0) / 3600.0)

npv = np.array([FEATS[m]['n_prior'] for m in MINTS])
tcr = np.array([(FEATS[m]['t_create'] - T0) / 3600.0 for m in MINTS])
print('corr(n_prior>0, hours_into_window) = %.3f' % np.corrcoef((npv > 0).astype(float), tcr)[0, 1])
for lo, hi in ((0, 6), (6, 12), (12, 18), (18, 24)):
    sel = (tcr >= lo) & (tcr < hi)
    print('  hours %2d-%2d : n=%3d  frac np0=%.3f' % (lo, hi, sel.sum(), (npv[sel] == 0).mean()))

for H in (15, 60):
    STR, CAND = build_hold(H)
    st = STR[('time', 'flat')]
    pm = {}
    for m in MINTS:
        r = evaluate(st, CAND, [m], 'all')
        if r and r['n'] >= 2:
            pm[m] = (r['mean'], r['res'], r['n'])
    ms = [m for m in pm]
    print('\n--- H=%d time flat, mints=%d ---' % (H, len(ms)))
    # calendar effect on its own
    print('  by creation hour:')
    for lo, hi in ((0, 6), (6, 12), (12, 18), (18, 24)):
        sel = [m for m in ms if lo <= (FEATS[m]['t_create'] - T0) / 3600.0 < hi]
        if len(sel) >= 8:
            print('    hours %2d-%2d n=%3d mean=%+.4f  frac np0=%.3f'
                  % (lo, hi, len(sel), np.mean([pm[m][0] for m in sel]),
                     np.mean([FEATS[m]['n_prior'] == 0 for m in sel])))
    # np0 effect WITHIN creation-hour strata (calendar-controlled)
    print('  np0 minus np1p, stratified by creation hour (validate mints only):')
    tot_d, tot_w = 0.0, 0.0
    for lo, hi in ((0, 4), (4, 8), (8, 12), (12, 16), (16, 20), (20, 24)):
        sel = [m for m in ms if m in set(VALID) and lo <= (FEATS[m]['t_create'] - T0) / 3600.0 < hi]
        a = [pm[m][0] for m in sel if FEATS[m]['n_prior'] == 0]
        b = [pm[m][0] for m in sel if FEATS[m]['n_prior'] > 0]
        if len(a) >= 4 and len(b) >= 4:
            d = np.mean(a) - np.mean(b)
            w = min(len(a), len(b))
            tot_d += d * w; tot_w += w
            print('    hours %2d-%2d  k0=%2d k1=%2d  np0=%+.4f np1p=%+.4f  delta=%+.4f'
                  % (lo, hi, len(a), len(b), np.mean(a), np.mean(b), d))
    if tot_w:
        print('    stratified weighted delta (VALIDATE) = %+.4f' % (tot_d / tot_w))
    # same for train
    tot_d, tot_w = 0.0, 0.0
    for lo, hi in ((0, 4), (4, 8), (8, 12), (12, 16), (16, 20), (20, 24)):
        sel = [m for m in ms if m in set(TRAIN) and lo <= (FEATS[m]['t_create'] - T0) / 3600.0 < hi]
        a = [pm[m][0] for m in sel if FEATS[m]['n_prior'] == 0]
        b = [pm[m][0] for m in sel if FEATS[m]['n_prior'] > 0]
        if len(a) >= 4 and len(b) >= 4:
            d = np.mean(a) - np.mean(b)
            w = min(len(a), len(b))
            tot_d += d * w; tot_w += w
    if tot_w:
        print('    stratified weighted delta (TRAIN)    = %+.4f' % (tot_d / tot_w))
    # loss tail / rug rate
    for grp, nm in ((TRAIN, 'TRAIN'), (VALID, 'VALID')):
        s = set(grp)
        a0 = [m for m in ms if m in s and FEATS[m]['n_prior'] == 0]
        a1 = [m for m in ms if m in s and FEATS[m]['n_prior'] > 0]
        print('  %s np0 k=%3d res=%.3f mean=%+.4f | np1p k=%3d res=%.3f mean=%+.4f'
              % (nm, len(a0), np.mean([pm[m][1] for m in a0]), np.mean([pm[m][0] for m in a0]),
                 len(a1), np.mean([pm[m][1] for m in a1]), np.mean([pm[m][0] for m in a1])))
