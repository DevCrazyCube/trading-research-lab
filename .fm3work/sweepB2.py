import pickle, numpy as np, itertools, json, sys, time
import panelB as P

d, f = pickle.load(open('/home/anont/meme/.fm3work/panelB.pkl', 'rb'))
d['_bnds'] = f['bnds']
mid = d['mid']; nm = len(d['mints']); n = len(d['ts'])
hs = np.array([d['mints'][m]['h'] for m in mid])
mcap = f['mcap_k']
ent = np.full(n, np.nan); ent[:-1] = mcap[1:]
FLOOR = 10.0
TOLL = 0.0114
SLACK = 3600
UNIV = (mcap >= FLOOR) & (ent >= FLOOR)

BANDS = {
    'age':  ('age_h',       [(0, 1), (1, 2), (2, 4), (4, 8), (8, 24), (24, 1e9)]),
    'mcap': ('mcap_k',      [(0, 30), (30, 60), (60, 100), (100, 300), (300, 1e9)]),
    'dd':   ('dd',          [(0, .2), (.2, .4), (.4, .6), (.6, .8), (.8, .95), (.95, 10)]),
    'tath': ('m_since_ath', [(0, 3), (3, 10), (10, 30), (30, 120), (120, 1e9)]),
    'gap':  ('gap',         [(0, 1.5), (1.5, 3.5), (3.5, 10), (10, 1e9)]),
    'vol':  ('vo',          [(0, 200), (200, 1000), (1000, 5000), (5000, 25000), (25000, 1e9)]),
    'pool': ('since_first', [(0, 15), (15, 60), (60, 240), (240, 1e9)]),
    'pcre': ('prior_c',     [(0, .5), (.5, 3), (3, 10), (10, 1e9)]),
    'pgrd': ('prior_g',     [(0, .5), (.5, 1e9)]),
}
FEATS = list(BANDS.keys())
MASKS = {k: [((f[c] >= lo) & (f[c] < hi)) for lo, hi in bs] for k, (c, bs) in BANDS.items()}

EXITS = {}


def get_exit(H):
    if H not in EXITS:
        EXITS[H] = P.exits(d, H, SLACK)
    return EXITS[H]


def sim(mask, H, drop=-0.30):
    g, r, b, eo = get_exit(H)
    return P.simulate(mask, g, r, b, mid, nm, TOLL, drop)


def boot_lo(pm, B=1500, seed=0):
    k = len(pm)
    if k < 5:
        return float('-inf')
    rng = np.random.default_rng(seed)
    s = pm[rng.integers(0, k, size=(B, k))].mean(axis=1)
    return float(np.percentile(s, 5.0))


def base_mask(H, split):
    g, r, b, eo = get_exit(H)
    return eo & UNIV & split


def sweep(H, split, maxway=3, min_n=30, min_k=10):
    bm = base_mask(H, split)
    bl = sim(bm, H)
    rows = []
    combos = 0
    for way in range(1, maxway + 1):
        for fs in itertools.combinations(FEATS, way):
            for bi in itertools.product(*[range(len(BANDS[x][1])) for x in fs]):
                m = bm
                for x, i in zip(fs, bi):
                    m = m & MASKS[x][i]
                combos += 1
                if m.sum() < min_n:
                    continue
                o = sim(m, H)
                if o is None or o['n'] < min_n or o['k'] < min_k:
                    continue
                rows.append((fs, bi, o))
    return bl, rows, combos


def cell_mask(H, split, fs, bi):
    m = base_mask(H, split)
    for x, i in zip(fs, bi):
        m = m & MASKS[x][i]
    return m


if __name__ == '__main__':
    tr = (hs == 1); va = (hs == 2)
    allres = {}
    total_combos = 0
    cands = []
    for H in (5, 15, 30, 60):
        t = time.time()
        bl, rows, combos = sweep(H, tr)
        total_combos += combos
        blo = boot_lo(bl['per_mint'])
        print('H=%2d TRAIN base mean=%+.4f med=%+.4f n=%d k=%d res=%.3f | combos=%d cells=%d %.0fs'
              % (H, bl['mint_mean'], bl['mint_median'], bl['n'], bl['k'], bl['res_rate'],
                 combos, len(rows), time.time() - t))
        keep = []
        for fs, bi, o in rows:
            if o['mint_mean'] <= bl['mint_mean']:
                continue
            if o['mint_median'] <= bl['mint_median']:
                continue
            lo = boot_lo(o['per_mint'], seed=hash((fs, bi)) % 10000)
            if lo <= bl['mint_mean']:
                continue
            keep.append((fs, bi, o, lo))
        keep.sort(key=lambda x: -x[3])
        print('   train-positive cells: %d' % len(keep))
        allres[H] = (bl, keep)
        for fs, bi, o, lo in keep[:60]:
            cands.append((H, fs, bi, o['mint_mean'], o['mint_median'], o['n'], o['k'], lo))
    print('TOTAL COMBOS SWEPT (panelB):', total_combos)
    pickle.dump((cands, total_combos), open('/home/anont/meme/.fm3work/candsB.pkl', 'wb'))

    print('\n=== VALIDATE (h==2) ===')
    for H in (5, 15, 30, 60):
        bmv = base_mask(H, va)
        blv = sim(bmv, H)
        print('H=%2d VALID base mean=%+.4f med=%+.4f n=%d k=%d' %
              (H, blv['mint_mean'], blv['mint_median'], blv['n'], blv['k']))
        sub = [c for c in cands if c[0] == H]
        surv = []
        for (_, fs, bi, tm, tmd, tn, tk, tlo) in sub:
            m = cell_mask(H, va, fs, bi)
            o = sim(m, H)
            if o is None or o['n'] < 20 or o['k'] < 8:
                continue
            lo = boot_lo(o['per_mint'], seed=1234)
            ok = (o['mint_mean'] > blv['mint_mean'] and o['mint_median'] > blv['mint_median']
                  and lo > blv['mint_mean'])
            if ok:
                surv.append((fs, bi, tm, o, lo))
        print('   validate survivors: %d / %d tested' % (len(surv), len(sub)))
        for fs, bi, tm, o, lo in surv[:20]:
            print('    %-28s train_mean=%+.4f | val mean=%+.4f med=%+.4f lo=%+.4f n=%d k=%d res=%.2f' %
                  ('|'.join('%s%d' % (a, c) for a, c in zip(fs, bi)), tm,
                   o['mint_mean'], o['mint_median'], lo, o['n'], o['k'], o['res_rate']))
