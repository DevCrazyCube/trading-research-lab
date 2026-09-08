import sys, pickle, time, collections
sys.path.insert(0, '/home/anont/meme/.scr_fc3')
import numpy as np
from engine import (build_hold, evaluate, CF_TRAIN, CF_VALID, CFS, GATES,
                    HOLDS, VARIANTS, POSITIONS, boot_lo, MIN_CLUSTERS, MIN_TRADES,
                    VALID, TRAIN)

D = pickle.load(open('/home/anont/meme/.scr_fc3/train_hits.pkl', 'rb'))
hits = D['hits']
print('train hits', len(hits), 'of', D['combos'], 'combos')
byH = collections.defaultdict(list)
for r in hits:
    byH[r['H']].append(r)

rng = np.random.default_rng(12345)
out = []
t0 = time.time()
for H in sorted(byH):
    STR, CAND = build_hold(H)
    # per-mint arrays for random-mint permutation controls, per (v,p,g)
    permint_cache = {}
    for r in byH[H]:
        key = (r['v'], r['p'], r['g'])
        st = STR[(r['v'], r['p'])]
        if key not in permint_cache:
            b = evaluate(st, CAND, CF_VALID['all'], r['g'], want_per=True)
            bt = evaluate(st, CAND, CF_TRAIN['all'], r['g'], want_per=True)
            # per-mint values over the whole validate legal universe, for permutation
            pm = {}
            for m in VALID:
                rr = evaluate(st, CAND, [m], r['g'])
                if rr:
                    pm[m] = rr['mean']
            permint_cache[key] = (b, bt, pm)
        b, bt, pm = permint_cache[key]
        vm = CF_VALID[r['cf']]
        rv = evaluate(st, CAND, vm, r['g'], want_per=True)
        if not rv or rv['cl'] < MIN_CLUSTERS or rv['n'] < MIN_TRADES:
            continue
        if rv['mean'] <= 0:
            continue
        lo = boot_lo(rv['per'])
        ctrl_v = rv['mean'] - (b['mean'] if b else 0.0)
        ctrl_t = r['mean'] - (bt['mean'] if bt else 0.0)
        # permutation over random mint subsets of the same size
        vals = np.array([pm[m] for m in pm])
        k = rv['cl']
        if len(vals) >= k and k > 0:
            draws = np.array([rng.choice(vals, size=k, replace=False).mean() for _ in range(2000)])
            pperm = float((draws >= rv['mean']).mean())
        else:
            pperm = 1.0
        # stress: worst dropout charge + high toll
        rs = evaluate(st, CAND, vm, r['g'], toll=0.025, charge=1.00)
        out.append(dict(**{k2: r[k2] for k2 in ('H', 'v', 'p', 'g', 'cf')},
                        tmean=r['mean'], tmed=r['med'], tn=r['n'], tcl=r['cl'],
                        vmean=rv['mean'], vmed=rv['med'], vn=rv['n'], vcl=rv['cl'],
                        vres=rv['res'], vlo=lo, ctrl_v=ctrl_v, ctrl_t=ctrl_t,
                        pperm=pperm, smean=rs['mean'] if rs else None,
                        bmean=b['mean'] if b else None))
    print('H=%d done, survivors so far %d, t=%.1f' % (H, len(out), time.time() - t0), flush=True)

print('VALIDATE-POSITIVE', len(out))
pickle.dump(out, open('/home/anont/meme/.scr_fc3/valid_out.pkl', 'wb'))

strict = [o for o in out if o['vlo'] > 0 and o['ctrl_v'] > 0 and o['ctrl_t'] > 0
          and o['pperm'] < 0.05 and o['smean'] is not None and o['smean'] > 0]
print('STRICT SURVIVORS', len(strict))
strict.sort(key=lambda o: -o['vmean'])
for o in strict[:60]:
    print(' V%+.4f(med%+.4f lo%+.4f) T%+.4f | ctrlV%+.4f ctrlT%+.4f pperm=%.4f stress%+.4f '
          'vn=%d vk=%d res=%.3f | H=%d %s %s %s %s'
          % (o['vmean'], o['vmed'], o['vlo'], o['tmean'], o['ctrl_v'], o['ctrl_t'],
             o['pperm'], o['smean'], o['vn'], o['vcl'], o['vres'],
             o['H'], o['v'], o['p'], o['g'], o['cf']))

print('--- loose (validate mean>0 only), top 40 by validate mean ---')
out.sort(key=lambda o: -o['vmean'])
for o in out[:40]:
    print(' V%+.4f(med%+.4f lo%+.4f) T%+.4f | ctrlV%+.4f pperm=%.4f stress%+.4f vn=%d vk=%d | H=%d %s %s %s %s'
          % (o['vmean'], o['vmed'], o['vlo'], o['tmean'], o['ctrl_v'], o['pperm'],
             o['smean'], o['vn'], o['vcl'], o['H'], o['v'], o['p'], o['g'], o['cf']))
print('elapsed', time.time() - t0)
