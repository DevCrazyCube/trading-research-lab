import pickle, os, json, random, itertools
import numpy as np
exec(open('/home/anont/meme/_r0_sweep2.py').read().split("L('sweeping %d combos'")[0].replace(
    "log = open(OUT + '/sweep2.log', 'w')", "log = open(OUT + '/sweep3.log', 'w')"))

# --- 2-way coarse regime interactions ---
PAIRVARS = REGNAMES
pairs = []
for a, b in itertools.combinations(PAIRVARS, 2):
    for sa in ('LO', 'HI'):
        for sb in ('LO', 'HI'):
            pairs.append(('%s_%s' % (a, sa), '%s_%s' % (b, sb)))
L('regime pairs', len(pairs))
for m in mints:
    for pa, pb in pairs:
        m['RM'][pa + '&' + pb] = m['RM'][pa] & m['RM'][pb]
PNAMES = [pa + '&' + pb for pa, pb in pairs]

SIS = [0, 1, 3, 8]   # H5, H15, H60, H60_TP50_SL30
NC = len(SIS)*len(ENAMES)*len(PNAMES)*len(POS)
L('sweeping %d interaction combos' % NC)
res3 = {}
for si in SIS:
    for ename in ENAMES:
        for rn in PNAMES:
            res3[(si, ename, rn)] = run(TR, ename, rn, si)
    L('  done', EX[si][0])
ctrl_tr = {si: run(TR, 'ALL', 'REG_ALL', si) for si in SIS}
ctrl_va = {si: run(VA, 'ALL', 'REG_ALL', si) for si in SIS}

rows = []
for (si, ename, rn), rt in res3.items():
    for p in POS:
        r = rt.get(p)
        if r is None or r['trim3'] != r['trim3']: continue
        c = ctrl_tr[si][p]
        rows.append(dict(si=si, exitn=EX[si][0], entry=ename, regime=rn, pos=p,
                         mean=r['mean'], trim3=r['trim3'], mmedian=r['mmedian'], n=r['n'],
                         clusters=r['clusters'], blocks=r['blocks'], hA=r['hA'], hB=r['hB'],
                         ctrl=c['mean'], ctrl3=c['trim3'],
                         edge=r['mean']-c['mean'], edge3=r['trim3']-c['trim3']))
rows.sort(key=lambda d: -d['trim3'])
L('TRAIN top 20 interactions by trim3:')
for d in rows[:20]:
    L('  trim3 %+.4f (ctrl %+.4f) mean %+.4f k=%d blk=%d hA%+.3f hB%+.3f | %s|%s|%s|%s' % (
        d['trim3'], d['ctrl3'], d['mean'], d['clusters'], d['blocks'], d['hA'], d['hB'],
        d['exitn'], d['entry'], d['regime'], d['pos']))
L('count with trim3>0 :', sum(1 for d in rows if d['trim3'] > 0))
L('count with mean>0  :', sum(1 for d in rows if d['mean'] > 0))
L('count with trim3>0 AND mean>0 AND k>=25:',
  sum(1 for d in rows if d['trim3'] > 0 and d['mean'] > 0 and d['clusters'] >= 25))

cand = [d for d in rows if d['mean'] > 0 and d['trim3'] > 0 and d['edge'] > 0.005
        and d['edge3'] > 0.005 and d['clusters'] >= 25 and d['blocks'] >= 3
        and d['hA'] > 0 and d['hB'] > 0]
L('TRAIN interaction candidates:', len(cand))

def boot(pm, B=3000, seed=11):
    rng = random.Random(seed); k = len(pm)
    if k < 5: return (float('nan'), float('nan'))
    ms = [sum(pm[rng.randrange(k)] for _ in range(k))/k for _ in range(B)]
    ms.sort(); return (ms[int(0.05*B)], ms[int(0.95*B)])

surv = []; seen = {}
for d in cand:
    key = (d['si'], d['entry'], d['regime'])
    if key not in seen: seen[key] = run(VA, d['entry'], d['regime'], d['si'])
    rv = seen[key].get(d['pos'])
    if rv is None: continue
    cv = ctrl_va[d['si']][d['pos']]
    lo, hi = boot(rv['permint'])
    rec = dict(d); rec.update(v_mean=rv['mean'], v_trim3=rv['trim3'], v_mmedian=rv['mmedian'],
                              v_median=rv['median'], v_n=rv['n'], v_clusters=rv['clusters'],
                              v_blocks=rv['blocks'], v_hA=rv['hA'], v_hB=rv['hB'],
                              v_ctrl=cv['mean'], v_ctrl3=cv['trim3'], v_lo=lo, v_hi=hi,
                              v_edge=rv['mean']-cv['mean'], v_edge3=rv['trim3']-cv['trim3'],
                              v_res=rv['res_rate'])
    surv.append(rec)
surv.sort(key=lambda d: -d['v_trim3'])
L('VALIDATE for %d interaction candidates:' % len(surv))
for d in surv[:40]:
    L('  va trim3 %+.4f (ctrl3 %+.4f) mean %+.4f ci %.3f..%.3f k=%d blk=%d | %s|%s|%s|%s' % (
        d['v_trim3'], d['v_ctrl3'], d['v_mean'], d['v_lo'], d['v_hi'], d['v_clusters'],
        d['v_blocks'], d['exitn'], d['entry'], d['regime'], d['pos']))
hard = [d for d in surv if d['v_mean'] > 0 and d['v_trim3'] > 0 and d['v_edge'] > 0
        and d['v_edge3'] > 0 and d['v_clusters'] >= 25 and d['v_lo'] > 0
        and d['v_blocks'] >= 3 and d['v_hA'] > 0 and d['v_hB'] > 0]
L('INTERACTION SURVIVORS:', len(hard))
for d in hard: L('  ** ' + json.dumps(d, default=float))
json.dump(dict(n_combos=NC, survivors=hard), open(OUT+'/survivors3.json','w'), indent=1, default=float)

# --- absolute best cell anywhere, on validate, regardless of train ---
L('BEST VALIDATE trim3 across all interaction cells actually re-run:',
  max([d['v_trim3'] for d in surv], default=None))

# --- harness cross-check vs quoted benchmark: trade-pooled stats of the control ---
L('CONTROL cross-check (entry ALL, regime ALL, pos full):')
for si in SIS:
    c = ctrl_tr[si]['full']; v = ctrl_va[si]['full']
    L('  %-16s TRAIN mint-mean %+.4f trim3 %+.4f mint-median %+.4f pooled-median %+.4f res %.3f n=%d k=%d' % (
        EX[si][0], c['mean'], c['trim3'], c['mmedian'], c['median'], c['res_rate'], c['n'], c['clusters']))
    L('  %-16s VALID mint-mean %+.4f trim3 %+.4f mint-median %+.4f pooled-median %+.4f res %.3f n=%d k=%d' % (
        '', v['mean'], v['trim3'], v['mmedian'], v['median'], v['res_rate'], v['n'], v['clusters']))
# dropout sensitivity on the control
for dv in (-0.30, -0.50, -1.00):
    c = run(TR+VA, 'ALL', 'REG_ALL', 1, dropv=dv)['full']
    L('  H15 all-mints dropout=%.2f  mint-mean %+.4f trim3 %+.4f pooled-median %+.4f' % (
        dv, c['mean'], c['trim3'], c['median']))
for tl in (0.0114, 0.025):
    c = run(TR+VA, 'ALL', 'REG_ALL', 1, toll=tl)['full']
    L('  H15 all-mints toll=%.4f  mint-mean %+.4f trim3 %+.4f pooled-median %+.4f' % (
        tl, c['mean'], c['trim3'], c['median']))
L('DONE')
log.close()
