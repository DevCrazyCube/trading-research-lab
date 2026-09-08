import sys, numpy as np
sys.path.insert(0, '/home/anont/meme/.combo2way')
from engine import *

print('signal bars: all=%d train=%d validate=%d' % (len(SIG), len(SIG_TR), len(SIG_VA)))
print('mints: train=%d validate=%d' % (len(TRAIN_M), len(VAL_M)))

for nm, sel in (('ALL', SIG), ('TRAIN', SIG_TR), ('VALIDATE', SIG_VA)):
    for toll in (0.0114, 0.025):
        line = []
        for dc in (-0.30, -0.50, -1.00):
            s = ev(sel, toll=toll, dropcharge=dc)
            line.append('%+.2f%%' % (100 * s['mean']))
        s = ev(sel, toll=toll, dropcharge=-0.30)
        print('%-9s toll=%.4f  mean@[-30,-50,-100]= %s   median=%+.2f%%  n=%d k=%d res=%.3f'
              % (nm, toll, ' '.join(line), 100 * s['median'], s['n'], s['k'], s['res']))

# gross (no toll) drift for reference
s = ev(SIG, toll=0.0, dropcharge=-0.30)
print('ALL gross (toll=0, drop -30): mean=%+.2f%% median=%+.2f%%' % (100 * s['mean'], 100 * s['median']))

# per-mint spread on the unconditional benchmark
s = ev(SIG_VA, toll=0.0114, dropcharge=-0.30)
lo, p = boot_lo(s['per_mint'])
print('VALIDATE unconditional: mean=%+.3f%% boot95lo=%+.3f%% p(mean<=0)=%.3f'
      % (100 * s['mean'], 100 * lo, p))
