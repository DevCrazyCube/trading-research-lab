import numpy as np, sys
sys.path.insert(0,'/home/anont/meme/.scr')
from sim import *

def allmask(m): return np.ones(len(per[m]['ts']),dtype=bool)

print('=== BASELINE: all bars, non-overlap, mint-equal, FULL, toll 1.14% ===')
for lbl,mset in (('ALL(h12)',MINTS),('TRAIN(h1)',TRAIN),('VAL(h2)',VALD)):
    for H in (5,15,60,240):
        line=[]
        for drop in (-0.30,-0.50,-1.00):
            r=run(allmask,mset,('H',H),('FULL',),drop=drop)
            line.append(f"{drop:+.2f}->{r['mean']*100:+.2f}%")
        print(f"{lbl:10s} H={H:4d} n={r['n']:6d} k={r['clusters']:4d} res={r['res']*100:.1f}% med={r['median']*100:+.2f}% "+' '.join(line))
print()
print('=== BASELINE at toll 2.5% ===')
for H in (5,15,60,240):
    r=run(allmask,MINTS,('H',H),('FULL',),toll=0.025,drop=-0.50)
    print(f"H={H:4d} mean={r['mean']*100:+.2f}% med={r['median']*100:+.2f}% n={r['n']}")
print()
print('=== TRUNCATION CONTROL: random(all) bars with take-profit structures ===')
for ex in [('H',15),('TP',0.10,15),('TP',0.25,15),('TP',0.50,15),('H',60),('TP',0.25,60),
           ('BR',0.50,0.35,60),('TR',0.35,60),('SC',0.30,0.5,60),('TP',1.00,240),('BR',1.00,0.60,240)]:
    r=run(allmask,MINTS,ex,('FULL',),drop=-0.50)
    print(f"{str(ex):26s} mean={r['mean']*100:+.2f}% med={r['median']*100:+.2f}% n={r['n']} k={r['clusters']} res={r['res']*100:.0f}%")
