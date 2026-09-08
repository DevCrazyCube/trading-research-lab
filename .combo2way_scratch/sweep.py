"""Exhaustive 2-way quintile-cell sweep, fixed 15m exit.
Train = h==1 mints, Validate = h==2 mints.  h==0 never loaded.
Harness: A entry at open of NEXT real bar, B no overlap per mint, C mint-equal weight,
D dropouts charged -30/-50/-100, E toll 1.14% and 2.5%, F simple returns, G no bar-count filter.
"""
import numpy as np, json, os, itertools, sys, math

OUT = '/home/anont/meme/.combo2way_scratch'
d = np.load(os.path.join(OUT, 'matrix.npz'), allow_pickle=True)
F = d['F']; MINT = d['mint']; HV = d['hv']; POS = d['pos']
GROSS = d['gross']; EXIT = d['exitpos']; FEATS = [str(x) for x in d['feats']]
NF = len(FEATS)
RES = np.isfinite(GROSS)
print('rows', len(MINT), 'train rows', int((HV == 1).sum()), 'val rows', int((HV == 2).sum()))

TR = np.where(HV == 1)[0]
VA = np.where(HV == 2)[0]

# ---- binning: edges from TRAIN only ----
SCHEMES = {
    'Q5': [0, 20, 40, 60, 80, 100],
    'R8': [0, 20, 30, 40, 50, 60, 70, 80, 100],   # finest resolution in the middle (shard hint)
}
BINS = {}
EDGES = {}
for sname, pcts in SCHEMES.items():
    nb = len(pcts) - 1
    B = np.full((len(MINT), NF), -1, dtype=np.int8)
    E = {}
    for f in range(NF):
        col = F[:, f]
        tr = col[TR]
        tr = tr[np.isfinite(tr)]
        if len(tr) < 500:
            continue
        e = np.percentile(tr, pcts)
        e[0] = -np.inf; e[-1] = np.inf
        # collapse duplicate edges -> feature unusable at this resolution
        if len(np.unique(e)) < len(e):
            keep = np.unique(e)
            if len(keep) < 3:
                continue
            e = keep
        idx = np.searchsorted(e, col, side='right') - 1
        idx = np.clip(idx, 0, len(e) - 2)
        idx[~np.isfinite(col)] = -1
        B[:, f] = idx.astype(np.int8)
        E[f] = e.tolist()
    BINS[sname] = B
    EDGES[sname] = E

TOLLS = {'t114': 0.0114, 't250': 0.025}
DROPS = {'d30': -0.30, 'd50': -0.50, 'd100': -1.00}


def simulate(rows):
    """rows: sorted global row indices. Returns per-mint lists of (resolved, gross)."""
    per = {}
    last_mint = -1
    last_exit = -1
    for r in rows:
        m = MINT[r]
        if m != last_mint:
            last_mint = m
            last_exit = -1
        p = POS[r]
        if last_exit >= 0 and p <= last_exit:
            continue
        g = GROSS[r]
        per.setdefault(m, []).append(g)
        xp = EXIT[r]
        last_exit = xp if xp >= 0 else 1 << 30
    return per


def agg(per, toll=0.0114, drop=-0.30):
    means = []
    n = 0; nres = 0
    for m, gs in per.items():
        vs = []
        for g in gs:
            n += 1
            if g == g:
                nres += 1
                vs.append((1.0 + g) * (1.0 - toll) - 1.0)
            else:
                vs.append(drop)
        means.append(sum(vs) / len(vs))
    if not means:
        return None
    means.sort()
    k = len(means)
    return dict(mean=sum(means) / k, median=means[k // 2], n=n, clusters=k,
                res=nres / n if n else 0.0)


def evaluate(rows):
    per = simulate(rows)
    if not per:
        return None
    out = {}
    for tn, tv in TOLLS.items():
        for dn, dv in DROPS.items():
            out[tn + '_' + dn] = agg(per, tv, dv)
    out['per'] = per
    return out


# ---- baselines: random entries, same structure ----
rng = np.random.default_rng(20260904)


def random_control(split_rows, k, reps=120):
    ms = []
    for _ in range(reps):
        sel = np.sort(rng.choice(split_rows, size=min(k, len(split_rows)), replace=False))
        a = agg(simulate(sel))
        if a:
            ms.append(a['mean'])
    ms.sort()
    return dict(mean=float(np.mean(ms)), lo=ms[int(.025 * len(ms))], hi=ms[int(.975 * len(ms))])


base = {}
for nm, rows in (('train', TR), ('val', VA)):
    a = evaluate(np.sort(rows))
    base[nm] = {k: v for k, v in a.items() if k != 'per'}
    print('ALLBARS', nm, json.dumps(base[nm]['t114_d30']))

# ---- the sweep ----
MIN_N = 40
MIN_CL = 12

results = []
swept = 0
for sname, B in BINS.items():
    nbmax = int(B.max()) + 1
    usable = [f for f in range(NF) if B[:, f].max() >= 1]
    # 1-way
    for f in usable:
        for b in range(int(B[:, f].max()) + 1):
            swept += 1
            rows = TR[B[TR, f] == b]
            if len(rows) < MIN_N:
                continue
            r = evaluate(np.sort(rows))
            if r is None:
                continue
            c = r['t114_d30']
            if c['mean'] > 0 and c['n'] >= MIN_N and c['clusters'] >= MIN_CL:
                results.append(dict(scheme=sname, kind='1w', fa=f, ba=b, fb=-1, bb=-1, train=c))
    # 2-way
    for fa, fb in itertools.combinations(usable, 2):
        na = int(B[:, fa].max()) + 1
        nb = int(B[:, fb].max()) + 1
        ca = B[TR, fa]; cb = B[TR, fb]
        for ba in range(na):
            ma = ca == ba
            if ma.sum() < MIN_N:
                swept += nb
                continue
            for bb in range(nb):
                swept += 1
                sel = ma & (cb == bb)
                if sel.sum() < MIN_N:
                    continue
                rows = TR[sel]
                r = evaluate(np.sort(rows))
                if r is None:
                    continue
                c = r['t114_d30']
                if c['mean'] > 0 and c['n'] >= MIN_N and c['clusters'] >= MIN_CL:
                    results.append(dict(scheme=sname, kind='2w', fa=fa, ba=ba, fb=fb, bb=bb, train=c))

print('cells swept on train:', swept)
print('train-positive candidates:', len(results))

# ---- validate ----
surv = []
for r in results:
    B = BINS[r['scheme']]
    sel = (B[VA, r['fa']] == r['ba'])
    if r['kind'] == '2w':
        sel &= (B[VA, r['fb']] == r['bb'])
    rows = VA[sel]
    if len(rows) < MIN_N:
        r['val'] = None
        continue
    ev = evaluate(np.sort(rows))
    if ev is None:
        r['val'] = None
        continue
    r['val'] = {k: v for k, v in ev.items() if k != 'per'}
    c = r['val']['t114_d30']
    if c['mean'] > 0 and c['n'] >= MIN_N and c['clusters'] >= MIN_CL:
        rc = random_control(VA, c['n'])
        r['rc'] = rc
        r['edge'] = c['mean'] - rc['mean']
        # cluster bootstrap on validate
        pm = []
        per = simulate(np.sort(rows))
        for m, gs in per.items():
            vs = [((1 + g) * (1 - .0114) - 1) if g == g else -0.30 for g in gs]
            pm.append(sum(vs) / len(vs))
        pm = np.array(pm)
        bs = np.array([np.mean(rng.choice(pm, len(pm), replace=True)) for _ in range(2000)])
        r['ci'] = [float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))]
        surv.append(r)

print('survived validate (mean>0):', len(surv))
surv.sort(key=lambda x: -x['val']['t114_d30']['mean'])


def nm(r):
    if r['kind'] == '1w':
        return '%s[%s=%d]' % (r['scheme'], FEATS[r['fa']], r['ba'])
    return '%s[%s=%d & %s=%d]' % (r['scheme'], FEATS[r['fa']], r['ba'], FEATS[r['fb']], r['bb'])


for r in surv[:60]:
    v = r['val']
    print('%-52s trainM=%+.4f (n=%d,k=%d) valM=%+.4f valMed=%+.4f n=%d k=%d res=%.2f CI=[%+.3f,%+.3f] rc=%+.4f edge=%+.4f d50=%+.4f d100=%+.4f t250=%+.4f' % (
        nm(r), r['train']['mean'], r['train']['n'], r['train']['clusters'],
        v['t114_d30']['mean'], v['t114_d30']['median'], v['t114_d30']['n'], v['t114_d30']['clusters'],
        v['t114_d30']['res'], r['ci'][0], r['ci'][1], r['rc']['mean'], r['edge'],
        v['t114_d50']['mean'], v['t114_d100']['mean'], v['t250_d30']['mean']))

json.dump(dict(base=base, swept=swept, n_trainpos=len(results),
               surv=[dict(name=nm(r), scheme=r['scheme'], kind=r['kind'],
                          fa=FEATS[r['fa']], ba=r['ba'],
                          fb=(FEATS[r['fb']] if r['fb'] >= 0 else None), bb=r['bb'],
                          train=r['train'], val=r['val'], rc=r['rc'], edge=r['edge'], ci=r['ci'])
                     for r in surv],
               edges={s: {FEATS[f]: e for f, e in E.items()} for s, E in EDGES.items()}),
          open(os.path.join(OUT, 'sweep_results.json'), 'w'), indent=1, default=float)
print('WROTE sweep_results.json')
