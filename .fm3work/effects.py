import pickle, numpy as np
import panelA as A

P = pickle.load(open('/home/anont/meme/.fm3work/panelA.pkl', 'rb'))
M, NC = P['M'], P['NC']; h = P['h']
out = open('/home/anont/meme/.fm3work/effects_out.txt', 'w')
pr = lambda *a: print(*a, file=out)
SPL = {1: np.tile((h == 1)[:, None], (1, NC)), 2: np.tile((h == 2)[:, None], (1, NC))}
nsoc = P['X'].astype(int) + P['TG'].astype(int) + P['WEB'].astype(int)

SPLITS = {
    'mcap >= $1M  vs  < $1M': (P['mcap'] >= 1e6),
    'mcap/ath >= 0.95  vs  < 0.95': (P['mar'] >= 0.95),
    'age >= 1h  vs  < 1h': (P['age_h'] >= 1.0),
    'zero socials  vs  >=1 social': np.tile((nsoc == 0)[:, None], (1, NC)),
    'no twitter  vs  has twitter': np.tile((~P['X'])[:, None], (1, NC)),
    'last trade 0-120s  vs  clock-skew bucket': ((P['stale'] >= 0) & (P['stale'] < 120)),
    'graduated  vs  on-curve': P['cmp'],
}


def paired(Hc, split, mk, B=4000, seed=3):
    """per-mint DIFFERENCE (side A minus side B) where a mint has trades on both sides;
       plus unpaired group means. cluster bootstrap over mints."""
    g, r, fl, b, el = A.exits(P, Hc)
    net = A.netarr(g, r, 0.0114, -0.30)
    base = el & SPL[split]
    ref = A.refmeans(base, net)
    oa = A.cellstat(base & mk, net, r, b, base, ref)
    ob = A.cellstat(base & ~mk, net, r, b, base, ref)
    if oa is None or ob is None:
        return None
    da = dict(zip(oa['mints'].tolist(), oa['pm'].tolist()))
    db = dict(zip(ob['mints'].tolist(), ob['pm'].tolist()))
    both = sorted(set(da) & set(db))
    diffs = np.array([da[i] - db[i] for i in both])
    rng = np.random.default_rng(seed)
    if len(diffs) >= 5:
        s = diffs[rng.integers(0, len(diffs), size=(B, len(diffs)))].mean(axis=1)
        lo, hi = np.percentile(s, [2.5, 97.5])
    else:
        lo = hi = float('nan')
    return oa, ob, diffs, lo, hi


pr('PANEL A metadata effects on the forward-return distribution')
pr('mint-equal, non-overlap, entry at NEXT snapshot, toll 1.14%, dropouts charged -30%')
pr('"paired" = per-mint (side A mean - side B mean) for mints that traded on BOTH sides,')
pr('with a 95% cluster bootstrap over mints. TRAIN = md5%%3==1, VALIDATE = md5%%3==2.')
for Hc, hl in [(5, '15m'), (20, '60m')]:
    pr('\n================= %s hold =================' % hl)
    for name, mk in SPLITS.items():
        pr('  %s' % name)
        for sp, lb in [(1, 'TRAIN'), (2, 'VALID')]:
            q = paired(Hc, sp, mk)
            if q is None:
                pr('    %s  thin' % lb); continue
            oa, ob, diffs, lo, hi = q
            pr('    %-6s A: mean=%+.4f med=%+.4f n=%4d k=%3d | B: mean=%+.4f med=%+.4f n=%4d k=%3d'
               % (lb, oa['mean'], oa['med'], oa['n'], oa['k'], ob['mean'], ob['med'], ob['n'], ob['k']))
            pr('           paired A-B = %+.4f  95%%CI [%+.4f, %+.4f]  (k_paired=%d)'
               % (diffs.mean() if len(diffs) else float('nan'), lo, hi, len(diffs)))
out.close()
print('done')
