import pickle, numpy as np, json, sqlite3, hashlib, itertools
import panelA as A
from collections import Counter, defaultdict

P = pickle.load(open('/home/anont/meme/.fm3work/panelA.pkl', 'rb'))
M, NC = P['M'], P['NC']; h = P['h']
out = open('/home/anont/meme/.fm3work/extra_out.txt', 'w')
pr = lambda *a: print(*a, file=out)

# ---- 1. are the curve reserve fields alive at all?
res = defaultdict(Counter)
nrow = 0
hh = lambda m: int(hashlib.md5(m.encode()).hexdigest(), 16) % 3
for line in open('/home/anont/meme/research/midcap/fresh_snapshots.jsonl'):
    try:
        d = json.loads(line)
    except Exception:
        continue
    if 'mint' not in d or hh(d['mint']) == 0:
        continue
    nrow += 1
    for k in ('vsol', 'rsol', 'vtok', 'rtok'):
        res[(k, bool(d['complete']))][d[k]] += 1
pr('=== curve-reserve field liveness (non-holdout rows=%d) ===' % nrow)
for (k, cmp_), c in sorted(res.items()):
    tot = sum(c.values())
    top = c.most_common(3)
    pr('  %-5s complete=%-5s distinct=%-4d top: %s' %
       (k, cmp_, len(c), ', '.join('%.4g x%d(%.0f%%)' % (v, n, 100 * n / tot) for v, n in top)))

# ---- 2. creator overlap with window_labels (deployer history for panel A mints)
w = sqlite3.connect('file:/home/anont/meme/research/b11a/window_labels.sqlite?mode=ro', uri=True)
hist = Counter()
grads = Counter()
for cr, co in w.execute('select creator,complete from window_label'):
    if cr:
        hist[cr] += 1
        grads[cr] += 1 if co else 0
cre = P['creator']
known = sum(1 for c in cre if c in hist)
pr('\n=== deployer history join ===')
pr('  panel-A non-holdout mints=%d, creators found in window_labels=%d (%.1f%%)'
   % (M, known, 100.0 * known / M))
pr('  -> window_labels covers an EARLIER chain window; deployer-history features are')
pr('     unavailable for the snapshot cohort, so that axis is untestable on panel A.')

# ---- 3. hand composite of the sign-consistent marginals (LEAKY: labelled as such)
def bandmask(arr, bs):
    return [((arr >= lo) & (arr < hi)) for lo, hi in bs]


BM = {}
BM['X'] = [np.tile(~P['X'][:, None], (1, NC)), np.tile(P['X'][:, None], (1, NC))]
nsoc = P['X'].astype(int) + P['TG'].astype(int) + P['WEB'].astype(int)
BM['nsoc0'] = np.tile((nsoc == 0)[:, None], (1, NC))
BM['mcap'] = bandmask(P['mcap'], [(0, 3e5), (3e5, 1e6), (1e6, 3e6), (3e6, 1e7), (1e7, 3e7), (3e7, 1e12)])
BM['mar'] = bandmask(P['mar'], [(0, .5), (.5, .8), (.8, .95), (.95, .995), (.995, 10)])
BM['stale'] = bandmask(P['stale'], [(-1e9, 0), (0, 30), (30, 120), (120, 1e9)])
BM['age'] = bandmask(P['age_h'], [(0, 1), (1, 3), (3, 6), (6, 12), (12, 24), (24, 1e9)])
SPL = {1: np.tile((h == 1)[:, None], (1, NC)), 2: np.tile((h == 2)[:, None], (1, NC))}

MCAP_OK = BM['mcap'][2] | BM['mcap'][3] | BM['mcap'][4]
MAR_OK = BM['mar'][3] | BM['mar'][4]
STALE_OK = BM['stale'][1] | BM['stale'][2] | BM['stale'][3]
AGE_OK = BM['age'][1] | BM['age'][2] | BM['age'][3] | BM['age'][4] | BM['age'][5]

COMPS = {
    'mcap>=1M': MCAP_OK,
    'mcap>=1M & mcap/ath>=0.95': MCAP_OK & MAR_OK,
    'mcap>=1M & mar>=0.95 & traded_last_2min': MCAP_OK & MAR_OK & STALE_OK,
    'FULL (+ age>=1h)': MCAP_OK & MAR_OK & STALE_OK & AGE_OK,
    'FULL + zero socials': MCAP_OK & MAR_OK & STALE_OK & AGE_OK & BM['nsoc0'],
    'INVERSE screen (what to AVOID)': (~MCAP_OK) | (~MAR_OK),
}
pr('\n=== hand composite of sign-consistent marginals ===')
pr('  NOTE: components were picked BY LOOKING AT BOTH SPLITS, so these numbers are')
pr('  in-sample twice over and are reported for shape only, NOT as validated candidates.')
for Hc, hl in [(5, '15m'), (10, '30m'), (20, '60m')]:
    for name, mk in COMPS.items():
        line = '  %-4s %-34s' % (hl, name)
        for sp, lb in [(1, 'TR'), (2, 'VA')]:
            g, r, fl, b, el = A.exits(P, Hc)
            net = A.netarr(g, r, 0.0114, -0.30)
            base = el & SPL[sp]
            ref = A.refmeans(base, net)
            o = A.cellstat(base & mk, net, r, b, base, ref)
            u = A.cellstat(base, net, r, b, base, ref)
            if o is None:
                line += ' %s thin' % lb; continue
            line += ' | %s mean=%+.4f med=%+.4f (univ %+.4f) n=%d k=%d' % (
                lb, o['mean'], o['med'], u['mean'], o['n'], o['k'])
        pr(line)
out.close()
print('done')
