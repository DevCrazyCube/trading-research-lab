import pickle, os, json, math, random
import numpy as np
from collections import deque

OUT = '/home/anont/meme/_r0'
log = open(OUT + '/sweep2.log', 'w')
def L(*a):
    log.write(' '.join(str(x) for x in a) + '\n'); log.flush()

D = pickle.load(open(OUT + '/cache.pkl', 'rb'))
mints = D['mints']; REG = D['REG']; REGNAMES = D['REGNAMES']

TOLL = 0.0114
DROP = -0.30
TSPLIT = None

EX = [
    ('H5',    5,   None, None),
    ('H15',   15,  None, None),
    ('H30',   30,  None, None),
    ('H60',   60,  None, None),
    ('H120',  120, None, None),
    ('H240',  240, None, None),
    ('H60_TP20',      60,  0.20, None),
    ('H60_TP20_SL30', 60,  0.20, 0.30),
    ('H60_TP50_SL30', 60,  0.50, 0.30),
    ('H240_TP50_SL30',240, 0.50, 0.30),
    ('H240_TP100_SL50',240,1.00, 0.50),
    ('H15_TP20_SL10', 15,  0.20, 0.10),
]

def build_outcomes(m, H, tp, sl):
    ts = m['ts']; o = m['o']; hi = m['hi']; lo = m['lo']
    n = len(ts)
    tgt = np.searchsorted(ts, ts + H*60, 'left')
    exit_idx = np.full(n, -1, dtype=np.int64)
    rfull = np.zeros(n); rpyr = np.zeros(n); rptp = np.zeros(n)
    ol = o.tolist(); hil = hi.tolist(); lol = lo.tolist(); tgl = tgt.tolist()
    if tp is None and sl is None:
        dqmax = deque(); right = 0
        for e in range(n):
            te = tgl[e]
            if te >= n: continue
            if right < e+1: right = e+1
            while right <= te:
                while dqmax and hil[dqmax[-1]] <= hil[right]: dqmax.pop()
                dqmax.append(right); right += 1
            while dqmax and dqmax[0] < e+1: dqmax.popleft()
            wmax = hil[dqmax[0]] if dqmax else -1.0
            px = ol[e]
            if px <= 0: continue
            xpx = ol[te]; rf = xpx/px - 1.0
            exit_idx[e] = te; rfull[e] = rf
            rpyr[e] = 0.5*rf + 0.5*(xpx/(px*1.2) - 1.0) if wmax >= px*1.2 else rf
            rptp[e] = 0.5*0.30 + 0.5*rf if wmax >= px*1.3 else rf
        return exit_idx, rfull, rpyr, rptp
    for e in range(n):
        te = tgl[e]
        if te >= n: continue
        px = ol[e]
        if px <= 0: continue
        tpl = px*(1+tp) if tp is not None else None
        sll = px*(1-sl) if sl is not None else None
        pyl = px*1.2; p3l = px*1.3
        hp = False; h3 = False; xi = te; xpx = ol[te]
        for k in range(e, te+1):
            if sll is not None and lol[k] <= sll:
                xi = k; xpx = sll; break
            if k > e:
                if hil[k] >= pyl: hp = True
                if hil[k] >= p3l: h3 = True
                if tpl is not None and hil[k] >= tpl:
                    xi = k; xpx = tpl; break
        rf = xpx/px - 1.0
        exit_idx[e] = xi; rfull[e] = rf
        rpyr[e] = 0.5*rf + 0.5*(xpx/pyl - 1.0) if hp else rf
        rptp[e] = 0.5*0.30 + 0.5*rf if h3 else rf
    return exit_idx, rfull, rpyr, rptp

for si, (nm, H, tp, sl) in enumerate(EX):
    for m in mints:
        m.setdefault('OUT', {})[si] = build_outcomes(m, H, tp, sl)
L('outcomes built')

ENAMES = ['ALL','AGE_LT60','AGE_60_360','AGE_GE360','R15_UP','R15_DN','R15_GT20','R15_LT-20',
          'RELVOL_GT2','RELVOL_LE1']
def entry_masks(m):
    n = len(m['ts']); age = m['age']; r15 = m['r15']; rv = m['relvol']
    return {'ALL': np.ones(n, bool), 'AGE_LT60': age < 60,
            'AGE_60_360': (age >= 60) & (age < 360), 'AGE_GE360': age >= 360,
            'R15_UP': r15 > 0, 'R15_DN': r15 < 0, 'R15_GT20': r15 > 0.20,
            'R15_LT-20': r15 < -0.20, 'RELVOL_GT2': rv > 2.0, 'RELVOL_LE1': rv <= 1.0}
for m in mints: m['EM'] = entry_masks(m)

TR = [m for m in mints if m['h'] == 1]
VA = [m for m in mints if m['h'] == 2]
L('train %d validate %d mints' % (len(TR), len(VA)))

train_reg = np.concatenate([REG[m['gi']] for m in TR])
THR = {}
for k, nm in enumerate(REGNAMES):
    if nm == 'HOUR': continue
    col = train_reg[:, k]; col = col[~np.isnan(col)]
    THR[nm] = {q: float(np.percentile(col, q)) for q in (20, 25, 33.3333, 50, 66.6667, 75, 80)}
L('THR', json.dumps(THR))

# time split for stability check (median entry ts)
ALLTS = np.concatenate([m['ts'] for m in mints])
TSPLIT = float(np.median(ALLTS))
L('TSPLIT', TSPLIT)

def regime_masks(m):
    rv = REG[m['gi']]; n = rv.shape[0]
    out = {'REG_ALL': np.ones(n, bool)}
    for k, nm in enumerate(REGNAMES):
        col = rv[:, k]
        if nm == 'HOUR':
            for b in range(4): out['HOUR_Q%d' % (b+1)] = (col >= b*6) & (col < (b+1)*6)
            out['HOUR_LO'] = col < 12; out['HOUR_HI'] = col >= 12
            for b in range(3): out['HOUR_T%d' % (b+1)] = (col >= b*8) & (col < (b+1)*8)
            out['HOUR_BOT20'] = col < 5; out['HOUR_TOP20'] = col >= 19
        else:
            t = THR[nm]
            out['%s_Q1' % nm] = col <= t[25]
            out['%s_Q2' % nm] = (col > t[25]) & (col <= t[50])
            out['%s_Q3' % nm] = (col > t[50]) & (col <= t[75])
            out['%s_Q4' % nm] = col > t[75]
            out['%s_LO' % nm] = col <= t[50]
            out['%s_HI' % nm] = col > t[50]
            out['%s_T1' % nm] = col <= t[33.3333]
            out['%s_T2' % nm] = (col > t[33.3333]) & (col <= t[66.6667])
            out['%s_T3' % nm] = col > t[66.6667]
            out['%s_BOT20' % nm] = col <= t[20]
            out['%s_TOP20' % nm] = col > t[80]
    return out
for m in mints: m['RM'] = regime_masks(m)
RNAMES = ['REG_ALL'] + [k for k in sorted(mints[0]['RM'].keys()) if k != 'REG_ALL']
L('regime cells', len(RNAMES))

POS = ['full', 'pyramid', 'partial_tp']

def run(group, ename, rname, si, dropv=DROP, toll=TOLL):
    per = {p: [] for p in POS}; allr = {p: [] for p in POS}
    ntr = 0; nres = 0; blocks = set()
    hA = {p: [] for p in POS}; hB = {p: [] for p in POS}
    for m in group:
        ex, rf, rp, rt = m['OUT'][si]
        mask = m['EM'][ename] & m['RM'][rname]
        S = np.nonzero(mask)[0]
        if len(S) == 0: continue
        n = len(m['ts']); tsl = m['ts']
        exl = ex.tolist(); rfl = rf.tolist(); rpl = rp.tolist(); rtl = rt.tolist()
        cur = -1; tr = {p: [] for p in POS}; trA = {p: [] for p in POS}; trB = {p: [] for p in POS}
        for i in S.tolist():
            e = i + 1
            if e >= n: break
            if e <= cur: continue
            te = int(tsl[e]); half = trA if te <= TSPLIT else trB
            blocks.add(te // 21600)
            x = exl[e]
            if x < 0:
                for p in POS: tr[p].append(dropv); half[p].append(dropv)
                ntr += 1; cur = n; break
            g = {'full': rfl[e], 'pyramid': rpl[e], 'partial_tp': rtl[e]}
            for p in POS:
                val = (1.0 + g[p]) * (1.0 - toll) - 1.0
                tr[p].append(val); half[p].append(val)
            ntr += 1; nres += 1; cur = x
        if not tr['full']: continue
        for p in POS:
            per[p].append(float(np.mean(tr[p]))); allr[p].extend(tr[p])
            if trA[p]: hA[p].append(float(np.mean(trA[p])))
            if trB[p]: hB[p].append(float(np.mean(trB[p])))
    res = {}
    for p in POS:
        if not per[p]: res[p] = None; continue
        v = sorted(per[p])
        res[p] = dict(mean=float(np.mean(per[p])), median=float(np.median(allr[p])),
                      mmedian=float(np.median(per[p])),
                      trim1=float(np.mean(v[:-1])) if len(v) > 1 else float('nan'),
                      trim3=float(np.mean(v[3:-3])) if len(v) > 8 else float('nan'),
                      winfrac=float(np.mean([x > 0 for x in allr[p]])),
                      n=len(allr[p]), clusters=len(per[p]), blocks=len(blocks),
                      res_rate=(nres/ntr if ntr else 0.0),
                      hA=float(np.mean(hA[p])) if hA[p] else float('nan'),
                      hB=float(np.mean(hB[p])) if hB[p] else float('nan'),
                      kA=len(hA[p]), kB=len(hB[p]), permint=per[p])
    return res

L('sweeping %d combos' % (len(EX)*len(ENAMES)*len(RNAMES)*len(POS)))
results = {}
for si in range(len(EX)):
    for ename in ENAMES:
        for rname in RNAMES:
            results[(si, ename, rname)] = run(TR, ename, rname, si)
    L('  exit done', EX[si][0])
NCOMBO = len(EX)*len(ENAMES)*len(RNAMES)*len(POS)
L('TRAIN combos', NCOMBO)

ctrl_tr = {si: results[(si, 'ALL', 'REG_ALL')] for si in range(len(EX))}
rows = []
for (si, ename, rname), rt in results.items():
    for p in POS:
        r = rt.get(p)
        if r is None: continue
        c = ctrl_tr[si][p]
        rows.append(dict(si=si, exitn=EX[si][0], entry=ename, regime=rname, pos=p,
                         mean=r['mean'], trim1=r['trim1'], trim3=r['trim3'],
                         median=r['median'], mmedian=r['mmedian'], n=r['n'],
                         clusters=r['clusters'], blocks=r['blocks'], res=r['res_rate'],
                         hA=r['hA'], hB=r['hB'],
                         ctrl=c['mean'], ctrl_trim3=c['trim3'], ctrl_mmed=c['mmedian'],
                         edge=r['mean']-c['mean'], edge3=r['trim3']-c['trim3']))
rows.sort(key=lambda d: -(d['trim3'] if d['trim3'] == d['trim3'] else -9))
L('TRAIN top 30 by trim3 (mean of per-mint means, 3 highest+3 lowest mints removed):')
for d in rows[:30]:
    L('  trim3 %+.4f (ctrl %+.4f) mean %+.4f mmed %+.4f n=%d k=%d blk=%d hA%+.3f hB%+.3f | %s|%s|%s|%s' % (
        d['trim3'], d['ctrl_trim3'], d['mean'], d['mmedian'], d['n'], d['clusters'], d['blocks'],
        d['hA'], d['hB'], d['exitn'], d['entry'], d['regime'], d['pos']))

# ---- candidate selection on TRAIN: must be positive on BOTH the raw mean and the
#      tail-trimmed mean, beat the same-structure control on both, be spread over time.
cand = [d for d in rows if d['mean'] > 0 and d['trim3'] == d['trim3'] and d['trim3'] > 0
        and d['edge'] > 0.005 and d['edge3'] > 0.005 and d['clusters'] >= 25
        and d['blocks'] >= 3 and d['hA'] > 0 and d['hB'] > 0]
L('TRAIN candidates (mean>0 AND trim3>0 AND both beat control AND k>=25 AND >=3 time blocks AND both halves>0):', len(cand))
for d in cand[:60]:
    L('   %s|%s|%s|%s trim3 %+.4f mean %+.4f' % (d['exitn'], d['entry'], d['regime'], d['pos'], d['trim3'], d['mean']))

def boot(permint, B=3000, seed=11):
    rng = random.Random(seed); k = len(permint)
    if k < 5: return (float('nan'), float('nan'))
    ms = []
    for _ in range(B):
        ms.append(sum(permint[rng.randrange(k)] for _ in range(k))/k)
    ms.sort(); return (ms[int(0.05*B)], ms[int(0.95*B)])

ctrl_va = {si: run(VA, 'ALL', 'REG_ALL', si) for si in range(len(EX))}
surv = []; seen = {}
for d in cand:
    key = (d['si'], d['entry'], d['regime'])
    if key not in seen: seen[key] = run(VA, d['entry'], d['regime'], d['si'])
    rv = seen[key].get(d['pos'])
    if rv is None: continue
    cv = ctrl_va[d['si']][d['pos']]
    lo, hi = boot(rv['permint'])
    rec = dict(d); rec.update(v_mean=rv['mean'], v_trim1=rv['trim1'], v_trim3=rv['trim3'],
                              v_median=rv['median'], v_mmedian=rv['mmedian'], v_n=rv['n'],
                              v_clusters=rv['clusters'], v_blocks=rv['blocks'], v_res=rv['res_rate'],
                              v_hA=rv['hA'], v_hB=rv['hB'], v_ctrl=cv['mean'], v_ctrl3=cv['trim3'],
                              v_edge=rv['mean']-cv['mean'], v_edge3=rv['trim3']-cv['trim3'],
                              v_lo=lo, v_hi=hi, v_winfrac=rv['winfrac'])
    surv.append(rec)
surv.sort(key=lambda d: -d['v_mean'])
json.dump(surv, open(OUT+'/validate2.json','w'), indent=0, default=float)
L('VALIDATE for %d train candidates:' % len(surv))
for d in surv[:60]:
    L('  va mean %+.4f trim3 %+.4f (ctrl3 %+.4f) ci %.3f..%.3f mmed %+.4f n=%d k=%d blk=%d hA%+.3f hB%+.3f | %s|%s|%s|%s' % (
        d['v_mean'], d['v_trim3'], d['v_ctrl3'], d['v_lo'], d['v_hi'], d['v_mmedian'],
        d['v_n'], d['v_clusters'], d['v_blocks'], d['v_hA'], d['v_hB'],
        d['exitn'], d['entry'], d['regime'], d['pos']))

hard = [d for d in surv if d['v_mean'] > 0 and d['v_trim3'] > 0 and d['v_edge'] > 0
        and d['v_edge3'] > 0 and d['v_clusters'] >= 25 and d['v_lo'] > 0
        and d['v_blocks'] >= 3 and d['v_hA'] > 0 and d['v_hB'] > 0]
L('SURVIVORS:', len(hard))
for d in hard: L('  ** ' + json.dumps(d, default=float))
json.dump(dict(n_combos=NCOMBO, survivors=hard), open(OUT+'/survivors2.json','w'), indent=1, default=float)

# soft survivors (drop the bootstrap-CI requirement) for the notes
soft = [d for d in surv if d['v_mean'] > 0 and d['v_trim3'] > 0 and d['v_edge3'] > 0 and d['v_clusters'] >= 25]
L('SOFT survivors (positive+beat control on trimmed mean, no CI gate):', len(soft))
for d in soft[:25]:
    L('  ~~ %s|%s|%s|%s tr_trim3 %+.4f va_trim3 %+.4f va_mean %+.4f ci %.3f..%.3f k=%d' % (
        d['exitn'], d['entry'], d['regime'], d['pos'], d['trim3'], d['v_trim3'], d['v_mean'],
        d['v_lo'], d['v_hi'], d['v_clusters']))

# ---- response surface, coarse halves, entry=ALL, pos=full
L('RESPONSE SURFACE (entry=ALL, pos=full): train trim3 / validate trim3 by coarse regime half')
for si in [1, 3, 5, 8]:
    c = ctrl_tr[si]['full']; cv = ctrl_va[si]['full']
    L(' %s  ctrl train trim3 %+.4f  validate trim3 %+.4f' % (EX[si][0], c['trim3'], cv['trim3']))
    for rn in RNAMES:
        if not (rn.endswith('_LO') or rn.endswith('_HI') or rn.endswith('_TOP20') or rn.endswith('_BOT20')):
            continue
        rt = results[(si, 'ALL', rn)]['full']
        vv = run(VA, 'ALL', rn, si)['full']
        if rt and vv:
            L('   %-24s TR trim3 %+.4f mean %+.4f k=%d | VA trim3 %+.4f mean %+.4f k=%d' % (
                rn, rt['trim3'], rt['mean'], rt['clusters'], vv['trim3'], vv['mean'], vv['clusters']))
L('DONE')
log.close()
