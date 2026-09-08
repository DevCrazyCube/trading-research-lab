"""Full sweep: creator ENTRY FILTER x TIMING x POSITION x EXIT.

Aggregation contract:
  C. mint-equal weighting  -> per-mint mean trade return, then mean/median across mints
  D. dropouts charged at -30 / -50 / -100 %
  E. toll 1.14% (headline) and 2.5%
  F. simple returns
  WINSOR: single-trade gross return capped at +300%.  One dust-price bounce
  (+1,038,572% on a 1e-10 price coin) otherwise sets the mint-equal mean of the
  WHOLE universe to +231%.  The cap is applied identically to every cell and to
  every control, so all comparisons are like-for-like.  Uncapped numbers are
  also carried for the finalists.
"""
import sys, os, time, math, statistics, pickle, random, json, collections
sys.path.insert(0, '/home/anont/meme/.scr2')
import engine as E

SCR = '/home/anont/meme/.scr2'
CAP = 3.0
MINTS = E.MINTS
FEAT = E.FEAT
META = E.META
import hashlib
def Hh(m): return int(hashlib.md5(m.encode()).hexdigest(), 16) % 3
SPLIT = {m: Hh(m) for m in MINTS}
TRAIN = [m for m in MINTS if SPLIT[m] == 1]
VALID = [m for m in MINTS if SPLIT[m] == 2]
CREATOR = {m: META[m]['creator'] for m in MINTS if m in META}

# ---------------- creator entry filters ----------------
def build_filters():
    F = []
    def add(name, fn): F.append((name, fn))
    add('ALL', lambda f: True)
    # --- prior launch count, incl. extremes/tails (replicate 2 bias) ---
    for k in (1, 2, 3, 5, 8, 12, 20, 30, 45, 60):
        add('nprior>=%d' % k, lambda f, k=k: f['nprior'] >= k)
    add('nprior==0', lambda f: f['nprior'] == 0)
    add('nprior<=1', lambda f: f['nprior'] <= 1)
    add('nprior in[1,3]', lambda f: 1 <= f['nprior'] <= 3)
    add('nprior in[4,12]', lambda f: 4 <= f['nprior'] <= 12)
    add('nprior in[13,40]', lambda f: 13 <= f['nprior'] <= 40)
    # --- graduation history of prior coins ---
    add('priorgrad==0', lambda f: f['prior_grad'] == 0)
    for k in (1, 2, 3, 5):
        add('priorgrad>=%d' % k, lambda f, k=k: f['prior_grad'] >= k)
    for k in (1, 2):
        add('priorgradLAG>=%d' % k, lambda f, k=k: f['prior_grad_lag'] >= k)
    for n0 in (3, 8):
        for g in (0.02, 0.05, 0.12, 0.30):
            add('n>=%d&gradrate>=%.2f' % (n0, g),
                lambda f, n0=n0, g=g: f['nprior'] >= n0 and f['prior_gradrate'] >= g)
            add('n>=%d&gradrate<%.2f' % (n0, g),
                lambda f, n0=n0, g=g: f['nprior'] >= n0 and 0 <= f['prior_gradrate'] < g)
    add('n>=5&gradrate==0', lambda f: f['nprior'] >= 5 and f['prior_gradrate'] == 0)
    add('n>=20&gradrate==0', lambda f: f['nprior'] >= 20 and f['prior_gradrate'] == 0)
    # --- launch burst / spam rate (tails) ---
    for w, k in ((300, 1), (300, 2), (300, 4), (600, 2), (600, 5), (1800, 3),
                 (1800, 8), (3600, 5), (3600, 15), (7200, 10), (7200, 30)):
        add('burst%ds>=%d' % (w, k), lambda f, w=w, k=k: f['burst%d' % w] >= k)
    add('burst300s==0&nprior>=3', lambda f: f['burst300'] == 0 and f['nprior'] >= 3)
    add('burst3600s==0&nprior>=3', lambda f: f['burst3600'] == 0 and f['nprior'] >= 3)
    # --- gap since the creator's previous launch (both tails) ---
    for g in (60, 180, 600, 1800):
        add('gap<=%ds' % g, lambda f, g=g: f['gap'] <= g)
    for g in (3600, 14400, 43200):
        add('gap>=%ds&nprior>=1' % g, lambda f, g=g: f['nprior'] >= 1 and f['gap'] >= g)
    # --- creator tenure / cadence ---
    add('tenure>=6h', lambda f: f['age_creator'] >= 21600)
    add('tenure<=30m&nprior>=2', lambda f: f['nprior'] >= 2 and f['age_creator'] <= 1800)
    for r in (1.0, 5.0, 20.0):
        add('rate>=%.0f/h' % r, lambda f, r=r: f['rate_per_h'] >= r)
        add('rate<%.0f/h&nprior>=2' % r, lambda f, r=r: f['nprior'] >= 2 and f['rate_per_h'] < r)
    # --- prior coins' realised outcomes (h1/h2 prior coins only, resolved before t) ---
    for tag in ('o15', 'o60'):
        add('%s_hot' % tag, lambda f, t=tag: f['n_' + t] >= 1 and f['mean_' + t] is not None and f['mean_' + t] > 0.0)
        add('%s_cold' % tag, lambda f, t=tag: f['n_' + t] >= 1 and f['mean_' + t] is not None and f['mean_' + t] <= 0.0)
        add('%s_veryhot' % tag, lambda f, t=tag: f['n_' + t] >= 1 and f['max_' + t] is not None and f['max_' + t] > 0.50)
        add('%s_dead' % tag, lambda f, t=tag: f['n_' + t] >= 2 and f['max_' + t] is not None and f['max_' + t] <= 0.0)
    # --- crosses ---
    add('n>=8&gap<=600', lambda f: f['nprior'] >= 8 and f['gap'] <= 600)
    add('n>=8&gap>=3600', lambda f: f['nprior'] >= 8 and f['gap'] >= 3600)
    add('n>=8&priorgrad>=1', lambda f: f['nprior'] >= 8 and f['prior_grad'] >= 1)
    add('n>=8&priorgrad==0', lambda f: f['nprior'] >= 8 and f['prior_grad'] == 0)
    add('n>=20&priorgrad>=2', lambda f: f['nprior'] >= 20 and f['prior_grad'] >= 2)
    add('n>=20&burst3600>=10', lambda f: f['nprior'] >= 20 and f['burst3600'] >= 10)
    add('n<=2&priorgrad>=1', lambda f: f['nprior'] <= 2 and f['prior_grad'] >= 1)
    return F

FILTERS = build_filters()
FSET = {}
for fname, fn in FILTERS:
    FSET[fname] = set(m for m in MINTS if m in FEAT and fn(FEAT[m]))

# ---------------- aggregation ----------------
def mint_stat(res, toll, drop, cap):
    rets, nd = res
    s = 0.0
    for g in rets:
        if cap is not None and g > cap: g = cap
        s += (1.0 + g) * (1.0 - toll) - 1.0
    s += nd * drop
    return s / (len(rets) + nd)

def cell(per, mints):
    """per: mint -> sim result.  mints: subset.  Mint-equal aggregation."""
    v30 = []; v50 = []; v100 = []; v25 = []; vraw = []
    nt = 0; nr = 0
    crs = set()
    for m in mints:
        r = per.get(m)
        if r is None: continue
        v30.append(mint_stat(r, E.TOLL_A, -0.30, CAP))
        v50.append(mint_stat(r, E.TOLL_A, -0.50, CAP))
        v100.append(mint_stat(r, E.TOLL_A, -1.00, CAP))
        v25.append(mint_stat(r, E.TOLL_B, -0.30, CAP))
        vraw.append(mint_stat(r, E.TOLL_A, -0.30, None))
        nt += len(r[0]) + r[1]; nr += len(r[0])
        c = CREATOR.get(m)
        if c: crs.add(c)
    k = len(v30)
    if k == 0: return None
    return dict(k=k, kc=len(crs), n=nt, res=(nr / nt if nt else 0.0),
                mean=statistics.mean(v30), med=statistics.median(v30),
                mean50=statistics.mean(v50), mean100=statistics.mean(v100),
                mean25=statistics.mean(v25), mean_raw=statistics.mean(vraw),
                vals=v30)

MIN_K = 20
MIN_KC = 8

def main():
    t0 = time.time()
    rows = []
    surface = []
    ncomb = 0
    total_struct = len(E.TIMINGS) * len(E.POSITIONS) * len(E.HOLDS) * len(E.MODS)
    done = 0
    for tname, timing in E.TIMINGS:
        for pname, position in E.POSITIONS:
            for hold in E.HOLDS:
                for mname, mod in E.MODS:
                    per = {}
                    for m in MINTS:
                        r = E.sim_mint(m, timing, position, hold, mod)
                        if r is not None: per[m] = r
                    base_tr = cell(per, TRAIN)
                    base_va = cell(per, VALID)
                    if base_tr is None or base_va is None:
                        done += 1; continue
                    surface.append((tname, pname, hold, mname,
                                    base_tr['mean'], base_va['mean'],
                                    base_tr['k'], base_va['k'], base_va['res']))
                    for fname, _ in FILTERS:
                        S = FSET[fname]
                        ncomb += 1
                        ctr = cell(per, [m for m in TRAIN if m in S])
                        if ctr is None or ctr['k'] < MIN_K or ctr['kc'] < MIN_KC: continue
                        if ctr['mean'] <= 0: continue
                        if ctr['mean'] <= base_tr['mean']: continue
                        cva = cell(per, [m for m in VALID if m in S])
                        if cva is None: continue
                        rows.append(dict(
                            timing=tname, pos=pname, hold=hold, mod=mname, filt=fname,
                            tr=dict((kk, ctr[kk]) for kk in ctr if kk != 'vals'),
                            va=dict((kk, cva[kk]) for kk in cva if kk != 'vals'),
                            btr=dict((kk, base_tr[kk]) for kk in base_tr if kk != 'vals'),
                            bva=dict((kk, base_va[kk]) for kk in base_va if kk != 'vals'),
                        ))
                    done += 1
                    if done % 200 == 0:
                        open(SCR + '/sweep.progress', 'w').write(
                            "%d/%d combos=%d kept=%d %.0fs\n" % (done, total_struct, ncomb, len(rows), time.time() - t0))
    out = dict(rows=rows, surface=surface, ncomb=ncomb,
               n_struct=total_struct, n_filters=len(FILTERS),
               elapsed=time.time() - t0,
               ntrain=len(TRAIN), nvalid=len(VALID),
               fsizes={f: (len([m for m in TRAIN if m in FSET[f]]),
                           len([m for m in VALID if m in FSET[f]])) for f, _ in FILTERS})
    with open(SCR + '/sweep.pkl', 'wb') as fh:
        pickle.dump(out, fh, protocol=4)
    open(SCR + '/sweep.out', 'w').write(json.dumps(dict(
        ncomb=ncomb, n_struct=total_struct, n_filters=len(FILTERS),
        kept=len(rows), elapsed=out['elapsed'],
        ntrain=len(TRAIN), nvalid=len(VALID)), indent=1))

if __name__ == '__main__':
    main()
