import pickle, numpy as np, itertools, time, sys
import panelA as A

P = pickle.load(open('/home/anont/meme/.fm3work/panelA.pkl', 'rb'))
M, NC = P['M'], P['NC']
h = P['h']
TOLL = float(sys.argv[1]) if len(sys.argv) > 1 else 0.0114
DROP = float(sys.argv[2]) if len(sys.argv) > 2 else -0.30
MAXWAY = int(sys.argv[3]) if len(sys.argv) > 3 else 3

col = lambda a: a


def bandmask(arr, bs):
    return [((arr >= lo) & (arr < hi)) for lo, hi in bs]


BM = {}
BM['X'] = [np.tile(~P['X'][:, None], (1, NC)), np.tile(P['X'][:, None], (1, NC))]
BM['TG'] = [np.tile(~P['TG'][:, None], (1, NC)), np.tile(P['TG'][:, None], (1, NC))]
BM['WEB'] = [np.tile(~P['WEB'][:, None], (1, NC)), np.tile(P['WEB'][:, None], (1, NC))]
BM['cmp'] = [~P['cmp'], P['cmp']]
BM['age'] = bandmask(P['age_h'], [(0, 1), (1, 3), (3, 6), (6, 12), (12, 24), (24, 1e9)])
BM['mcap'] = bandmask(P['mcap'], [(0, 3e5), (3e5, 1e6), (1e6, 3e6), (3e6, 1e7), (1e7, 3e7), (3e7, 1e12)])
BM['mar'] = bandmask(P['mar'], [(0, .5), (.5, .8), (.8, .95), (.95, .995), (.995, 10)])
BM['tath'] = bandmask(P['tath'], [(-1e9, 2), (2, 10), (10, 60), (60, 300), (300, 1e9)])
BM['stale'] = bandmask(P['stale'], [(-1e9, 0), (0, 30), (30, 120), (120, 1e9)])
FEATS = ['X', 'TG', 'WEB', 'cmp', 'age', 'mcap', 'mar', 'tath', 'stale']

SPL = {1: np.tile((h == 1)[:, None], (1, NC)), 2: np.tile((h == 2)[:, None], (1, NC))}


def bootlo(x, B=1500, seed=0, q=5.0):
    k = len(x)
    if k < 5:
        return float('-inf')
    rng = np.random.default_rng(seed)
    return float(np.percentile(x[rng.integers(0, k, size=(B, k))].mean(axis=1), q))


CACHE = {}


def prep(Hc, split):
    key = (Hc, split)
    if key in CACHE:
        return CACHE[key]
    g, r, fl, b, el = A.exits(P, Hc)
    net = A.netarr(g, r, TOLL, DROP)
    base = el & SPL[split]
    ref = A.refmeans(base, net)
    univ = A.cellstat(base, net, r, b, base, ref)
    CACHE[key] = (net, r, b, base, ref, univ)
    return CACHE[key]


def evalcell(fs, bi, Hc, split):
    net, r, b, base, ref, univ = prep(Hc, split)
    m = base
    for x, i in zip(fs, bi):
        m = m & BM[x][i]
    if m.sum() < 20:
        return None, univ, ref
    o = A.cellstat(m, net, r, b, base, ref)
    return o, univ, ref


if __name__ == '__main__':
    print('toll=%.4f drop=%.2f maxway=%d' % (TOLL, DROP, MAXWAY))
    total = 0
    short = []
    for Hc, lbl in [(5, '15m'), (10, '30m'), (20, '60m')]:
        t0 = time.time()
        net, r, b, base, ref, univ = prep(Hc, 1)
        print('H=%s TRAIN univ mean=%+.4f med=%+.4f n=%d k=%d res=%.3f'
              % (lbl, univ['mean'], univ['med'], univ['n'], univ['k'], univ['res']))
        keep = []
        cnt = 0
        for way in range(1, MAXWAY + 1):
            for fs in itertools.combinations(FEATS, way):
                for bi in itertools.product(*[range(len(BM[x])) for x in fs]):
                    cnt += 1
                    m = base
                    for x, i in zip(fs, bi):
                        m = m & BM[x][i]
                    if m.sum() < 25:
                        continue
                    o = A.cellstat(m, net, r, b, base, ref)
                    if o is None or o['n'] < 25 or o['k'] < 8:
                        continue
                    if o['mean'] <= 0:
                        continue
                    lo = bootlo(o['pm'], seed=abs(hash((fs, bi))) % 9999)
                    if lo <= 0:
                        continue
                    ctrl = float(np.nanmean(ref[o['mints']]))   # same mints, random timing
                    keep.append((fs, bi, o, lo, ctrl))
        total += cnt
        keep.sort(key=lambda x: -x[3])
        print('   combos=%d  train cells mean>0 & bootlo>0: %d  (%.0fs)' % (cnt, len(keep), time.time() - t0))
        for fs, bi, o, lo, ctrl in keep[:15]:
            print('     %-32s mean=%+.4f(lo%+.4f) med=%+.4f ctrl=%+.4f exc=%+.4f n=%d k=%d res=%.2f'
                  % ('|'.join('%s%d' % (a, c) for a, c in zip(fs, bi)), o['mean'], lo,
                     o['med'], ctrl, o['mean'] - ctrl, o['n'], o['k'], o['res']))
        for fs, bi, o, lo, ctrl in keep[:120]:
            short.append((Hc, lbl, fs, bi, o['mean'], o['med'], lo, ctrl, o['n'], o['k']))
    print('TOTAL COMBOS SWEPT (panelA):', total)
    pickle.dump(short, open('/home/anont/meme/.fm3work/shortA_%s.pkl' % str(TOLL), 'wb'))

    print('\n=== VALIDATE h==2 ===')
    nsurv = 0
    for Hc, lbl in [(5, '15m'), (10, '30m'), (20, '60m')]:
        netv, rv, bv, basev, refv, univv = prep(Hc, 2)
        sub = [s for s in short if s[0] == Hc]
        print('H=%s VALID univ mean=%+.4f med=%+.4f n=%d k=%d | testing %d'
              % (lbl, univv['mean'], univv['med'], univv['n'], univv['k'], len(sub)))
        for (_, _, fs, bi, tm, tmd, tlo, tctrl, tn, tk) in sub:
            m = basev
            for x, i in zip(fs, bi):
                m = m & BM[x][i]
            if m.sum() < 20:
                continue
            o = A.cellstat(m, netv, rv, bv, basev, refv)
            if o is None or o['n'] < 20 or o['k'] < 8:
                continue
            lo = bootlo(o['pm'], seed=4242)
            ctrl = float(np.nanmean(refv[o['mints']]))
            if o['mean'] > 0 and lo > 0 and o['mean'] > ctrl:
                nsurv += 1
                print('  SURVIVOR %-30s tr_mean=%+.4f | VAL mean=%+.4f(lo%+.4f) med=%+.4f ctrl=%+.4f exc=%+.4f n=%d k=%d res=%.2f'
                      % ('|'.join('%s%d' % (a, c) for a, c in zip(fs, bi)), tm,
                         o['mean'], lo, o['med'], ctrl, o['mean'] - ctrl, o['n'], o['k'], o['res']))
    print('TOTAL VALIDATE SURVIVORS:', nsurv)
