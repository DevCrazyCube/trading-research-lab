import pickle, numpy as np, itertools
import panelA as A

P = pickle.load(open('/home/anont/meme/.fm3work/panelA.pkl', 'rb'))
M, NC = P['M'], P['NC']; h = P['h']
out = open('/home/anont/meme/.fm3work/marg_out.txt', 'w')
pr = lambda *a: print(*a, file=out)


def bandmask(arr, bs):
    return [((arr >= lo) & (arr < hi)) for lo, hi in bs]


LAB = {}
BM = {}
BM['X'] = [np.tile(~P['X'][:, None], (1, NC)), np.tile(P['X'][:, None], (1, NC))]
LAB['X'] = ['no_twitter', 'has_twitter']
BM['TG'] = [np.tile(~P['TG'][:, None], (1, NC)), np.tile(P['TG'][:, None], (1, NC))]
LAB['TG'] = ['no_tg', 'has_tg']
BM['WEB'] = [np.tile(~P['WEB'][:, None], (1, NC)), np.tile(P['WEB'][:, None], (1, NC))]
LAB['WEB'] = ['no_web', 'has_web']
nsoc = P['X'].astype(int) + P['TG'].astype(int) + P['WEB'].astype(int)
BM['nsoc'] = [np.tile((nsoc == k)[:, None], (1, NC)) for k in (0, 1, 2, 3)]
LAB['nsoc'] = ['0 socials', '1 social', '2 socials', '3 socials']
BM['cmp'] = [~P['cmp'], P['cmp']]
LAB['cmp'] = ['on_curve', 'graduated']
BM['age'] = bandmask(P['age_h'], [(0, 1), (1, 3), (3, 6), (6, 12), (12, 24), (24, 1e9)])
LAB['age'] = ['<1h', '1-3h', '3-6h', '6-12h', '12-24h', '>24h']
BM['mcap'] = bandmask(P['mcap'], [(0, 3e5), (3e5, 1e6), (1e6, 3e6), (3e6, 1e7), (1e7, 3e7), (3e7, 1e12)])
LAB['mcap'] = ['<300k', '300k-1M', '1-3M', '3-10M', '10-30M', '>30M']
BM['mar'] = bandmask(P['mar'], [(0, .5), (.5, .8), (.8, .95), (.95, .995), (.995, 10)])
LAB['mar'] = ['mcap/ath<0.5', '0.5-0.8', '0.8-0.95', '0.95-0.995', '>=0.995 (at ATH)']
BM['tath'] = bandmask(P['tath'], [(-1e9, 2), (2, 10), (10, 60), (60, 300), (300, 1e9)])
LAB['tath'] = ['ath<2m ago', '2-10m', '10-60m', '1-5h', '>5h']
BM['stale'] = bandmask(P['stale'], [(-1e9, 0), (0, 30), (30, 120), (120, 1e9)])
LAB['stale'] = ['trade<0s(skew)', '0-30s', '30-120s', '>120s']
SPL = {1: np.tile((h == 1)[:, None], (1, NC)), 2: np.tile((h == 2)[:, None], (1, NC))}


def prep(Hc, split, toll=0.0114, drop=-0.30):
    g, r, fl, b, el = A.exits(P, Hc)
    net = A.netarr(g, r, toll, drop)
    base = el & SPL[split]
    ref = A.refmeans(base, net)
    return net, r, b, base, ref


pr('PANEL A (fresh_snapshots metadata, 186 non-holdout mints, 178 x 3-min cycles, 8.85h window)')
pr('15m hold, enter at NEXT snapshot, non-overlap, mint-equal, toll 1.14%%, dropouts charged -30%%')
pr('')
for Hc, hl in [(5, '15m'), (20, '60m')]:
    pr('================ HORIZON %s ================' % hl)
    T = prep(Hc, 1); V = prep(Hc, 2)
    ut = A.cellstat(T[3], T[0], T[1], T[2], T[3], T[4])
    uv = A.cellstat(V[3], V[0], V[1], V[2], V[3], V[4])
    pr('UNIVERSE   train mean=%+.4f med=%+.4f n=%d k=%d res=%.3f | valid mean=%+.4f med=%+.4f n=%d k=%d res=%.3f'
       % (ut['mean'], ut['med'], ut['n'], ut['k'], ut['res'], uv['mean'], uv['med'], uv['n'], uv['k'], uv['res']))
    for feat in ['X', 'TG', 'WEB', 'nsoc', 'cmp', 'age', 'mcap', 'mar', 'tath', 'stale']:
        pr('  -- %s' % feat)
        for i, lb in enumerate(LAB[feat]):
            rowt = A.cellstat(T[3] & BM[feat][i], T[0], T[1], T[2], T[3], T[4])
            rowv = A.cellstat(V[3] & BM[feat][i], V[0], V[1], V[2], V[3], V[4])
            def fmt(o, u):
                if o is None or o['n'] < 10:
                    return '     thin      '
                return 'mean=%+.4f med=%+.4f d=%+.4f n=%4d k=%3d' % (o['mean'], o['med'], o['mean'] - u['mean'], o['n'], o['k'])
            pr('     %-18s TR %s | VA %s' % (lb, fmt(rowt, ut), fmt(rowv, uv)))
out.close()
print('done')
