import sys, time
sys.path.insert(0, '/home/anont/meme/.scr_fc3')
import numpy as np
from engine import (build_hold, evaluate, MINTS, TRAIN, VALID, GATES, boot_lo)

t0 = time.time()
for H in (15, 60):
    STR, CAND = build_hold(H)
    st = STR[('time', 'flat')]
    for chg in (0.30, 0.50, 1.00):
        for toll in (0.0114, 0.025):
            r = evaluate(st, CAND, MINTS, 'all', toll=toll, charge=chg, want_per=True)
            print('H=%3d ALL  toll=%.4f chg=%.2f  mean=%+.4f med=%+.4f n=%d k=%d res=%.3f lo5=%+.4f'
                  % (H, toll, chg, r['mean'], r['med'], r['n'], r['cl'], r['res'], boot_lo(r['per'])))
    for grp, nm in ((TRAIN, 'TRAIN'), (VALID, 'VALID')):
        r = evaluate(st, CAND, grp, 'all', want_per=True)
        print('H=%3d %s mean=%+.4f med=%+.4f n=%d k=%d res=%.3f' % (H, nm, r['mean'], r['med'], r['n'], r['cl'], r['res']))
    # per-gate baselines
    for g in GATES:
        r = evaluate(st, CAND, MINTS, g)
        if r:
            print('   H=%3d gate=%-12s mean=%+.4f med=%+.4f n=%d k=%d res=%.3f' % (H, g, r['mean'], r['med'], r['n'], r['cl'], r['res']))
    # truncation demo: tp25 on all bars
    for v in ('tp25', 'tp50', 'trail30', 'half_tp50'):
        r = evaluate(STR[(v, 'flat')], CAND, MINTS, 'all')
        print('   H=%3d var=%-10s ALL mean=%+.4f med=%+.4f n=%d k=%d res=%.3f' % (H, v, r['mean'], r['med'], r['n'], r['cl'], r['res']))
print('elapsed', time.time() - t0)
