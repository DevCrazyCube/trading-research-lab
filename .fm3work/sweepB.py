import pickle, numpy as np, itertools, json, sys, time
import panelB as P

d, f = pickle.load(open('/home/anont/meme/.fm3work/panelB.pkl', 'rb'))
d['_bnds'] = f['bnds']
mid = d['mid']; nm = len(d['mints'])
n = len(d['ts'])
hsplit = np.array([d['mints'][m]['h'] for m in mid])

MCAP_FLOOR_K = 10.0          # tradeable-universe floor, applied to the ENTRY bar
TOLL = 0.0114
SLACK = 3600

mcap = f['mcap_k']
ent_mcap = np.full(n, np.nan); ent_mcap[:-1] = mcap[1:]

BANDS = {
    'age':  ('age_h',       [(0, 1), (1, 2), (2, 4), (4, 8), (8, 24), (24, 1e9)]),
    'mcap': ('mcap_k',      [(0, 10), (10, 30), (30, 60), (60, 100), (100, 300), (300, 1e9)]),
    'dd':   ('dd',          [(0, .2), (.2, .4), (.4, .6), (.6, .8), (.8, .95), (.95, 10)]),
    'tath': ('m_since_ath', [(0, 3), (3, 10), (10, 30), (30, 120), (120, 1e9)]),
    'gap':  ('gap',         [(0, 1.5), (1.5, 3.5), (3.5, 10), (10, 1e9)]),
    'vol':  ('vo',          [(0, 200), (200, 1000), (1000, 5000), (5000, 25000), (25000, 1e9)]),
    'pool': ('since_first', [(0, 15), (15, 60), (60, 240), (240, 1e9)]),
    'pcre': ('prior_c',     [(0, .5), (.5, 3), (3, 10), (10, 1e9)]),
    'pgrd': ('prior_g',     [(0, .5), (.5, 1e9)]),
}
FEATS = list(BANDS.keys())
MASKS = {}
for k, (col, bs) in BANDS.items():
    v = f[col]
    MASKS[k] = [((v >= lo) & (v < hi)) for lo, hi in bs]


def run(H, drop, split_mask, base_extra=None):
    g, r, b, eo = P.exits(d, H, SLACK)
    base = eo & (ent_mcap >= MCAP_FLOOR_K) & split_mask
    if base_extra is not None:
        base = base & base_extra
    return g, r, b, base


def sim(mask, g, r, b, drop):
    return P.simulate(mask, g, r, b, mid, nm, TOLL, drop)


def boot(pm, B=2000, seed=0):
    rng = np.random.default_rng(seed)
    k = len(pm)
    if k < 3:
        return (float('nan'), float('nan'))
    s = pm[rng.integers(0, k, size=(B, k))].mean(axis=1)
    return float(np.percentile(s, 2.5)), float(np.percentile(s, 97.5))


def sweep(H, drop, split_mask, maxway=3):
    g, r, b, base = run(H, drop, split_mask)
    baseline = sim(base, g, r, b, drop)
    out = []
    combos = 0
    for way in range(1, maxway + 1):
        for fs in itertools.combinations(FEATS, way):
            for bi in itertools.product(*[range(len(BANDS[x][1])) for x in fs]):
                m = base
                for x, i in zip(fs, bi):
                    m = m & MASKS[x][i]
                combos += 1
                cnt = int(m.sum())
                if cnt < 40:
                    continue
                o = sim(m, g, r, b, drop)
                if o is None or o['k'] < 8 or o['n'] < 25:
                    continue
                out.append(dict(feats=fs, bands=bi, **{kk: o[kk] for kk in
                                ('mint_mean', 'mint_median', 'n', 'k', 'res_rate')},
                                per_mint=o['per_mint']))
    return baseline, out, combos


if __name__ == '__main__':
    H = int(sys.argv[1]) if len(sys.argv) > 1 else 15
    drop = -0.30
    tr = (hsplit == 1); va = (hsplit == 2)
    print('train bars %d mints %d | validate bars %d mints %d' %
          (tr.sum(), len(set(mid[tr].tolist())), va.sum(), len(set(mid[va].tolist()))))
    t = time.time()
    bl, res, combos = sweep(H, drop, tr)
    print('TRAIN baseline H=%d: mean=%+.4f med=%+.4f n=%d k=%d res=%.3f' %
          (H, bl['mint_mean'], bl['mint_median'], bl['n'], bl['k'], bl['res_rate']))
    print('combos=%d survivors_with_n=%d  %.1fs' % (combos, len(res), time.time() - t))
    res.sort(key=lambda x: -x['mint_mean'])
    for x in res[:25]:
        print('  %-30s mean=%+.4f med=%+.4f n=%4d k=%3d' %
              ('|'.join('%s%d' % (a, c) for a, c in zip(x['feats'], x['bands'])),
               x['mint_mean'], x['mint_median'], x['n'], x['k']))
    pickle.dump((bl, [{kk: v for kk, v in x.items() if kk != 'per_mint'} for x in res], combos),
                open('/home/anont/meme/.fm3work/trainB_H%d.pkl' % H, 'wb'))
