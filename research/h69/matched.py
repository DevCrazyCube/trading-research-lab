"""Density-matched control for the frozen cell, on pump.fun graduates.

The cell fires only on bars that have a REAL bar exactly 5 min earlier -- i.e. inside dense,
actively-trading stretches. A uniformly-random bar does not. So cell-vs-random-bar confounds
"modest momentum" with "coin is still actively trading".

Matched control = the SAME eligibility (real bar at t-5min, real next bar) but 5-min return
OUTSIDE the [+4.8%,+9.5%] band. If the band is a behavioural regularity, the cell should beat
this. If it is an activity artifact, it should not.
"""
import sqlite3, json, random, statistics as st, sys
sys.path.insert(0, '/home/anont/meme/research/h69')
from cell import med, pct

TOLL = 0.0114
HOLD = 15

c = sqlite3.connect('file:/home/anont/meme/research/midcap/grad_ohlcv.sqlite?mode=ro', uri=True)
rows = [(m, sorted(json.loads(bj), key=lambda x: x[0]))
        for m, bj in c.execute("select mint,bars_json from ohlcv where status='ok' and bars_json is not null")]

def eligible(bars):
    """yield (i, prior5_return) for every bar with a REAL bar exactly 5 min earlier"""
    ts = {x[0]: k for k, x in enumerate(bars)}
    for i, x in enumerate(bars):
        j = ts.get(x[0] - 300)
        if j is None: continue
        c0, c1 = bars[j][4], x[4]
        if c0 <= 0 or c1 <= 0: continue
        yield i, c1 / c0 - 1.0

def trade(bars, i):
    if i + 1 >= len(bars): return None
    e = bars[i + 1]
    if e[0] <= bars[i][0] or e[1] <= 0: return None
    want = e[0] + 60 * HOLD
    for k in bars[i + 2:]:
        if k[0] >= want: return k[1] / e[1] - 1.0
    return 'unres'

BANDS = [('<-10%', -9e9, -0.10), ('-10..-4.8%', -0.10, -0.048), ('-4.8..0%', -0.048, 0.0),
         ('0..+4.8%', 0.0, 0.048), ('CELL +4.8..+9.5%', 0.048, 0.095),
         ('+9.5..+20%', 0.095, 0.20), ('+20..+50%', 0.20, 0.50), ('>+50%', 0.50, 9e9)]

per = {}   # mint -> band -> list of raw rets / 'unres'
for m, bars in rows:
    d = {}
    for i, r in eligible(bars):
        t = trade(bars, i)
        if t is None: continue
        for name, lo, hi in BANDS:
            if lo <= r < hi:
                d.setdefault(name, []).append(t); break
    if d: per[m] = d

def boot(bandsel, ch, draws=600, seed=7):
    mints = [m for m in per if any(b in per[m] for b in bandsel)]
    arr = {m: [(x - TOLL) if x != 'unres' else ch for b in bandsel for x in per[m].get(b, [])] for m in mints}
    rnd = random.Random(seed); out = []
    for _ in range(draws):
        v = []
        for _ in mints: v += arr[mints[rnd.randrange(len(mints))]]
        if v: out.append(st.mean(v))
    out.sort(); return out

print('pump.fun graduates: %d mints, DENSITY-MATCHED bars only (real bar exactly 5 min earlier)\n' % len(per))
for ch in (-0.50,):
    print('--- unresolved charged at %d%% ---' % (100 * ch))
    for name, lo, hi in BANDS:
        vals = [(x - TOLL) if x != 'unres' else ch for m in per for x in per[m].get(name, [])]
        if len(vals) < 30:
            print('  %-18s n=%5d  (too few)' % (name, len(vals))); continue
        nres = sum(1 for m in per for x in per[m].get(name, []) if x != 'unres')
        cl = sum(1 for m in per if name in per[m])
        b = boot([name], ch)
        print('  %-18s n=%5d clusters=%3d res=%5.1f%% mean=%+7.2f%% MED=%+7.2f%% meanCI95[%+7.2f,%+7.2f]'
              % (name, len(vals), cl, 100 * nres / len(vals), 100 * st.mean(vals), 100 * med(vals),
                 100 * pct(b, .025), 100 * pct(b, .975)))
    # cell minus all-other-eligible
    others = [n for n, _, _ in BANDS if n != 'CELL +4.8..+9.5%']
    A = {m: [(x - TOLL) if x != 'unres' else ch for x in per[m].get('CELL +4.8..+9.5%', [])] for m in per}
    B = {m: [(x - TOLL) if x != 'unres' else ch for b in others for x in per[m].get(b, [])] for m in per}
    mints = [m for m in per if A[m] and B[m]]
    rnd = random.Random(99); diffs = []
    for _ in range(600):
        a = []; bb = []
        for _ in mints:
            mm = mints[rnd.randrange(len(mints))]; a += A[mm]; bb += B[mm]
        diffs.append(st.mean(a) - st.mean(bb))
    diffs.sort()
    aa = [x for m in mints for x in A[m]]; bbb = [x for m in mints for x in B[m]]
    print('  >> CELL - (all other density-matched bars): mean diff %+.2fpp  median diff %+.2fpp  CI95[%+.2f,%+.2f] clusters=%d'
          % (100 * (st.mean(aa) - st.mean(bbb)), 100 * (med(aa) - med(bbb)),
             100 * pct(diffs, .025), 100 * pct(diffs, .975), len(mints)))
    print()
