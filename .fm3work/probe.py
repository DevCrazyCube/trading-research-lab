import pickle, numpy as np, itertools
import panelA as A

P = pickle.load(open('/home/anont/meme/.fm3work/panelA.pkl', 'rb'))
M, NC = P['M'], P['NC']; h = P['h']
out = open('/home/anont/meme/.fm3work/probe_out.txt', 'w')
pr = lambda *a: print(*a, file=out)


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
SPL = {1: np.tile((h == 1)[:, None], (1, NC)), 2: np.tile((h == 2)[:, None], (1, NC)),
       0: np.ones((M, NC), bool)}


def run(Hc, split, toll, drop, cell=None):
    g, r, fl, b, el = A.exits(P, Hc)
    net = A.netarr(g, r, toll, drop)
    base = el & SPL[split]
    ref = A.refmeans(base, net)
    m = base
    if cell:
        for x, i in cell:
            m = m & BM[x][i]
    o = A.cellstat(m, net, r, b, base, ref)
    u = A.cellstat(base, net, r, b, base, ref)
    return o, u, ref, net, r, b, base


CELL = [('X', 1), ('mar', 3), ('stale', 1)]
pr('=== SURVIVOR: has_x=1 & mcap/ath in [0.95,0.995) & 0<=sec_since_last_trade<30 ; 60m hold ===')
for split, lbl in [(1, 'TRAIN'), (2, 'VALID'), (0, 'BOTH(1+2)')]:
    for toll in (0.0114, 0.025):
        for drop in (-0.30, -0.50, -1.00):
            o, u, ref, *_ = run(20, split, toll, drop, CELL)
            if o is None:
                pr('%s toll%.4f drop%.2f  EMPTY' % (lbl, toll, drop)); continue
            ctrl = float(np.nanmean(ref[o['mints']]))
            pr('%-9s toll%.4f drop%+.2f  mean=%+.4f med=%+.4f ctrl(same-mints-random-timing)=%+.4f univ=%+.4f n=%d k=%d res=%.2f'
               % (lbl, toll, drop, o['mean'], o['med'], ctrl, u['mean'], o['n'], o['k'], o['res']))

pr('\n--- per-mint contribution on VALIDATE (toll 1.14%, drop -30%) ---')
o, u, ref, net, r, b, base = run(20, 2, 0.0114, -0.30, CELL)
order = np.argsort(-o['pm'])
for i in order:
    pr('   mint %-46s permean=%+.4f ref=%+.4f' % (P['mints'][o['mints'][i]], o['pm'][i], ref[o['mints'][i]]))
pr('   mean without top mint: %+.4f' % np.mean(np.delete(o['pm'], order[0])))
pr('   mean without top 2:    %+.4f' % np.mean(np.delete(o['pm'], order[:2])))

pr('\n--- horizon sensitivity of the same cell (VALIDATE, toll 1.14%, drop -30%) ---')
for Hc, lbl in [(2, '6m'), (3, '9m'), (5, '15m'), (7, '21m'), (10, '30m'), (15, '45m'), (20, '60m'), (30, '90m')]:
    o, u, ref, *_ = run(Hc, 2, 0.0114, -0.30, CELL)
    if o is None:
        pr('   %s EMPTY' % lbl); continue
    pr('   %-4s mean=%+.4f med=%+.4f univ=%+.4f n=%d k=%d' % (lbl, o['mean'], o['med'], u['mean'], o['n'], o['k']))

pr('\n--- band-neighbour sensitivity (VALIDATE, 60m) : is the mar/stale cut a cliff? ---')
for mi in range(5):
    for si in range(4):
        o, u, ref, *_ = run(20, 2, 0.0114, -0.30, [('X', 1), ('mar', mi), ('stale', si)])
        if o is None or o['n'] < 8:
            pr('   mar%d stale%d  (thin)' % (mi, si)); continue
        pr('   mar%d stale%d  mean=%+.4f med=%+.4f n=%d k=%d' % (mi, si, o['mean'], o['med'], o['n'], o['k']))

pr('\n=== MULTIPLICITY NULL: max-statistic permutation ===')
pr('shuffle the mint->(X,TG,WEB) label assignment 300x, re-run the SAME 3-way grid on VALIDATE,')
pr('count how often SOME cell reaches the survivor mean with mean>0 & bootlo>0.')
out.flush()

FEATS = ['X', 'TG', 'WEB', 'cmp', 'age', 'mcap', 'mar', 'tath', 'stale']


def bootlo(x, B=600, seed=0, q=5.0):
    if len(x) < 5:
        return -np.inf
    rng = np.random.default_rng(seed)
    return float(np.percentile(x[rng.integers(0, len(x), size=(B, len(x)))].mean(axis=1), q))


g, r, fl, b, el = A.exits(P, 20)
net = A.netarr(g, r, 0.0114, -0.30)
base2 = el & SPL[2]
ref2 = A.refmeans(base2, net)
rng = np.random.default_rng(7)
target = 0.1071
hits = 0; NSIM = 200
maxes = []
for s in range(NSIM):
    perm = rng.permutation(M)
    BM['X'] = [np.tile(~P['X'][perm][:, None], (1, NC)), np.tile(P['X'][perm][:, None], (1, NC))]
    BM['TG'] = [np.tile(~P['TG'][perm][:, None], (1, NC)), np.tile(P['TG'][perm][:, None], (1, NC))]
    BM['WEB'] = [np.tile(~P['WEB'][perm][:, None], (1, NC)), np.tile(P['WEB'][perm][:, None], (1, NC))]
    best = -9
    for way in (1, 2, 3):
        for fs in itertools.combinations(FEATS, way):
            if not any(x in ('X', 'TG', 'WEB') for x in fs):
                continue
            for bi in itertools.product(*[range(len(BM[x])) for x in fs]):
                m = base2
                for x, i in zip(fs, bi):
                    m = m & BM[x][i]
                if m.sum() < 25:
                    continue
                o = A.cellstat(m, net, r, b, base2, ref2)
                if o is None or o['n'] < 20 or o['k'] < 8 or o['mean'] <= 0:
                    continue
                if bootlo(o['pm'], seed=1) <= 0:
                    continue
                if o['mean'] > best:
                    best = o['mean']
    maxes.append(best)
    if best >= target:
        hits += 1
mx = np.array([x for x in maxes if x > -9])
pr('null max-stat over %d social-label permutations: hits>=%.4f : %d/%d  (p=%.3f)'
   % (NSIM, target, hits, NSIM, hits / NSIM))
if len(mx):
    pr('null max distribution: med %+.4f p90 %+.4f p95 %+.4f max %+.4f (n_nonempty=%d)'
       % (np.median(mx), np.percentile(mx, 90), np.percentile(mx, 95), mx.max(), len(mx)))
out.close()
