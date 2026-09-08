import sys, os
sys.path.insert(0, '/home/anont/meme/.scr_fc3')
import numpy as np
from engine import (build_hold, evaluate, CF_TRAIN, CF_VALID, boot_lo, MIN_MCAP,
                    STOP_FILL, TRAIN, VALID, MINTS, FEATS)

print('MIN_MCAP=%g STOP_FILL=%s' % (MIN_MCAP, STOP_FILL))
rng = np.random.default_rng(99)

CANDS = [(240, 'tp25', 'add_dn25', 'ath_ge90', 'b60_3p'),
         (5, 'tp25', 'add_dn25', 'ath_ge90', 'b60_3p')]
for (H, v, p, g, cf) in CANDS:
    STR, CAND = build_hold(H)
    st = STR[(v, p)]
    print('\n### H=%d %s %s gate=%s cf=%s' % (H, v, p, g, cf))
    for nm, mm in (('TRAIN', CF_TRAIN[cf]), ('VALID', CF_VALID[cf])):
        for toll in (0.0114, 0.025):
            for chg in (0.30, 0.50, 1.00):
                r = evaluate(st, CAND, mm, g, toll=toll, charge=chg, want_per=True)
                if not r:
                    continue
                print('  %s toll=%.4f chg=%.2f mean=%+.4f med=%+.4f n=%d k=%d res=%.3f lo5=%+.4f'
                      % (nm, toll, chg, r['mean'], r['med'], r['n'], r['cl'], r['res'], boot_lo(r['per'])))
    # same structure on ALL mints (the truncation control)
    for nm, mm in (('TRAIN', CF_TRAIN['all']), ('VALID', CF_VALID['all'])):
        r = evaluate(st, CAND, mm, g)
        print('  CONTROL(all mints, same structure+gate) %s mean=%+.4f med=%+.4f n=%d k=%d'
              % (nm, r['mean'], r['med'], r['n'], r['cl']))

# --- np0 screen at this mcap floor ---
print('\n=== np0 (first-time deployer) screen ===')
for H in (15, 60, 240):
    STR, CAND = build_hold(H)
    st = STR[('time', 'flat')]
    for nm, grp in (('TRAIN', TRAIN), ('VALID', VALID)):
        s = set(grp)
        m0 = [m for m in s if FEATS[m]['n_prior'] == 0]
        m1 = [m for m in s if FEATS[m]['n_prior'] > 0]
        r0 = evaluate(st, CAND, m0, 'all', want_per=True)
        r1 = evaluate(st, CAND, m1, 'all', want_per=True)
        ra = evaluate(st, CAND, list(s), 'all')
        if r0 and r1:
            print('  H=%3d %s  np0 mean=%+.4f (k=%d res=%.3f lo5=%+.4f) | np1p mean=%+.4f (k=%d) | all=%+.4f'
                  % (H, nm, r0['mean'], r0['cl'], r0['res'], boot_lo(r0['per']),
                     r1['mean'], r1['cl'], ra['mean']))
