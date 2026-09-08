import pickle, numpy as np, itertools, sys, time
import panelB as P

d, f = pickle.load(open('/home/anont/meme/.fm3work/panelB.pkl', 'rb'))
d['_bnds'] = f['bnds']
mid = d['mid']; nm = len(d['mints']); n = len(d['ts'])
hs = np.array([d['mints'][m]['h'] for m in mid])
mcap = f['mcap_k']
ent = np.full(n, np.nan); ent[:-1] = mcap[1:]
FLOOR = float(sys.argv[2]) if len(sys.argv) > 2 else 10.0
TOLL = 0.0114
SLACK = 3600
DROP = -0.30
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

_E = {}


def E(H):
    if H not in _E:
        g, r, b, eo = P.exits(d, H, SLACK)
        rnet = np.where(r, g - TOLL, DROP - TOLL)
        base = eo & UNIV
        _E[H] = (g, r, b, eo, rnet, base)
    return _E[H]


def refmeans(H, split):
    """per-mint mean net return over ALL eligible bars = matched random-entry control"""
    g, r, b, eo, rnet, base = E(H)
    m = base & split
    s = np.bincount(mid[m], weights=rnet[m], minlength=nm)
    c = np.bincount(mid[m], minlength=nm)
    ref = np.full(nm, np.nan)
    ok = c > 0
    ref[ok] = s[ok] / c[ok]
    return ref, ok, m


def cellstat(mask, H, ref):
    """greedy non-overlap; returns mint-equal abs mean/median, within-mint excess, counts"""
    g, r, b, eo, rnet, base = E(H)
    idx = np.flatnonzero(mask)
    if len(idx) == 0:
        return None
    sums = np.zeros(nm); cnt = np.zeros(nm, dtype=np.int64)
    nf = -1; nres = 0; ntr = 0
    for p in idx:
        if p < nf:
            continue
        m_ = mid[p]
        sums[m_] += rnet[p]
        cnt[m_] += 1
        ntr += 1
        if r[p]:
            nres += 1
        nf = b[p]
    act = cnt > 0
    if act.sum() == 0:
        return None
    pm = sums[act] / cnt[act]
    rf = ref[act]
    good = ~np.isnan(rf)
    exc = pm[good] - rf[good]
    return dict(pm=pm, exc=exc, mean=float(pm.mean()), med=float(np.median(pm)),
                exc_mean=float(exc.mean()) if len(exc) else float('nan'),
                exc_med=float(np.median(exc)) if len(exc) else float('nan'),
                n=ntr, k=int(act.sum()), res=nres / ntr if ntr else 0.0,
                sel_ref=float(np.nanmean(rf)))


def bootlo(x, B=1500, seed=0, q=5.0):
    k = len(x)
    if k < 5:
        return float('-inf')
    rng = np.random.default_rng(seed)
    s = x[rng.integers(0, k, size=(B, k))].mean(axis=1)
    return float(np.percentile(s, q))


def sweep(H, split, maxway=3, min_n=30, min_k=10):
    ref, ok, bm = refmeans(H, split)
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
                o = cellstat(m, H, ref)
                if o is None or o['n'] < min_n or o['k'] < min_k:
                    continue
                rows.append((fs, bi, o))
    base = cellstat(bm, H, ref)
    return base, rows, combos, ref


def cmask(H, split, fs, bi):
    g, r, b, eo, rnet, base = E(H)
    m = base & split
    for x, i in zip(fs, bi):
        m = m & MASKS[x][i]
    return m


if __name__ == '__main__':
    tr = (hs == 1); va = (hs == 2)
    total = 0
    shortlist = []
    for H in (5, 15, 30, 60, 120):
        t = time.time()
        base, rows, combos, ref = sweep(H, tr)
        total += combos
        print('H=%3d TRAIN univ mean=%+.4f med=%+.4f n=%d k=%d res=%.3f | combos=%d cells=%d %.0fs'
              % (H, base['mean'], base['med'], base['n'], base['k'], base['res'],
                 combos, len(rows), time.time() - t))
        keep = []
        for fs, bi, o in rows:
            if o['mean'] <= 0:                 # must actually make money
                continue
            if o['exc_mean'] <= 0:             # must beat random entries in the SAME mints
                continue
            lo = bootlo(o['pm'], seed=abs(hash((fs, bi))) % 9999)
            elo = bootlo(o['exc'], seed=abs(hash((fs, bi))) % 9999 + 1)
            if lo <= 0 or elo <= 0:
                continue
            keep.append((fs, bi, o, lo, elo))
        keep.sort(key=lambda x: -x[4])
        print('   train cells with mean>0 AND excess>0 AND both boot-lo>0: %d' % len(keep))
        for fs, bi, o, lo, elo in keep[:15]:
            print('     %-30s mean=%+.4f(lo%+.4f) med=%+.4f exc=%+.4f(lo%+.4f) n=%d k=%d'
                  % ('|'.join('%s%d' % (a, c) for a, c in zip(fs, bi)), o['mean'], lo,
                     o['med'], o['exc_mean'], elo, o['n'], o['k']))
        for fs, bi, o, lo, elo in keep[:80]:
            shortlist.append((H, fs, bi, o['mean'], o['med'], o['exc_mean'], o['n'], o['k']))
    print('TOTAL COMBOS SWEPT:', total)

    print('\n=== VALIDATE h==2 ===')
    nsurv = 0
    for H in (5, 15, 30, 60, 120):
        refv, okv, bmv = refmeans(H, va)
        basev = cellstat(bmv, H, refv)
        sub = [s for s in shortlist if s[0] == H]
        if not sub:
            print('H=%3d: no train candidates' % H); continue
        print('H=%3d VALID univ mean=%+.4f med=%+.4f n=%d k=%d | testing %d'
              % (H, basev['mean'], basev['med'], basev['n'], basev['k'], len(sub)))
        for (_, fs, bi, tm, tmd, tex, tn, tk) in sub:
            m = cmask(H, va, fs, bi)
            o = cellstat(m, H, refv)
            if o is None or o['n'] < 20 or o['k'] < 8:
                continue
            lo = bootlo(o['pm'], seed=77)
            elo = bootlo(o['exc'], seed=78)
            ok = o['mean'] > 0 and o['exc_mean'] > 0 and lo > 0 and elo > 0
            if ok:
                nsurv += 1
                print('  SURVIVOR %-28s train mean=%+.4f exc=%+.4f | VAL mean=%+.4f(lo%+.4f) med=%+.4f exc=%+.4f(lo%+.4f) n=%d k=%d res=%.2f'
                      % ('|'.join('%s%d' % (a, c) for a, c in zip(fs, bi)), tm, tex,
                         o['mean'], lo, o['med'], o['exc_mean'], elo, o['n'], o['k'], o['res']))
    print('TOTAL VALIDATE SURVIVORS:', nsurv)
    pickle.dump(shortlist, open('/home/anont/meme/.fm3work/shortB.pkl', 'wb'))
