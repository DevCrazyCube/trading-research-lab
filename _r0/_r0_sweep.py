import pickle, os, json, math, random
import numpy as np
from collections import deque

OUT = '/home/anont/meme/_r0'
log = open(OUT + '/sweep.log', 'w')
def L(*a):
    log.write(' '.join(str(x) for x in a) + '\n'); log.flush()

D = pickle.load(open(OUT + '/cache.pkl', 'rb'))
mints = D['mints']; REG = D['REG']; REGNAMES = D['REGNAMES']
L('mints', len(mints), 'bars', sum(len(m['ts']) for m in mints))

TOLL = 0.0114
TOLL2 = 0.025
DROP = -0.30

# ---------------- exit structures ----------------
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
        # deque sliding window max over [e+1, te]
        dqmax = deque()  # indices, decreasing hi
        right = 0        # next index to push
        for e in range(n):
            te = tgl[e]
            if te >= n:
                continue
            if right < e+1: right = e+1
            while right <= te:
                while dqmax and hil[dqmax[-1]] <= hil[right]: dqmax.pop()
                dqmax.append(right); right += 1
            while dqmax and dqmax[0] < e+1: dqmax.popleft()
            wmax = hil[dqmax[0]] if dqmax else -1.0
            px = ol[e]
            if px <= 0: continue
            xpx = ol[te]
            rf = xpx/px - 1.0
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
        hp = False; h3 = False
        xi = te; xpx = ol[te]
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

L('building outcomes...')
for si, (nm, H, tp, sl) in enumerate(EX):
    for m in mints:
        m.setdefault('OUT', {})[si] = build_outcomes(m, H, tp, sl)
    L('  built', nm)

# ---------------- entry conditions ----------------
def entry_masks(m):
    n = len(m['ts']); age = m['age']; r15 = m['r15']; rv = m['relvol']
    ms = {}
    ms['ALL']      = np.ones(n, bool)
    ms['AGE_LT60'] = age < 60
    ms['AGE_60_360'] = (age >= 60) & (age < 360)
    ms['AGE_GE360'] = age >= 360
    ms['R15_UP']   = r15 > 0
    ms['R15_DN']   = r15 < 0
    ms['R15_GT20'] = r15 > 0.20
    ms['R15_LT-20']= r15 < -0.20
    ms['RELVOL_GT2'] = rv > 2.0
    ms['RELVOL_LE1'] = rv <= 1.0
    return ms
ENAMES = ['ALL','AGE_LT60','AGE_60_360','AGE_GE360','R15_UP','R15_DN','R15_GT20','R15_LT-20','RELVOL_GT2','RELVOL_LE1']
for m in mints:
    m['EM'] = entry_masks(m)

# ---------------- regime buckets ----------------
TR = [m for m in mints if m['h'] == 1]
VA = [m for m in mints if m['h'] == 2]
L('train mints', len(TR), 'validate mints', len(VA))

train_reg = np.concatenate([REG[m['gi']] for m in TR])  # (nbars,7)
THR = {}
for k, nm in enumerate(REGNAMES):
    if nm == 'HOUR': continue
    col = train_reg[:, k]
    col = col[~np.isnan(col)]
    THR[nm] = [float(np.percentile(col, q)) for q in (25, 50, 75)]
L('thresholds', json.dumps(THR))

RNAMES = ['REG_ALL']
for k, nm in enumerate(REGNAMES):
    if nm == 'HOUR':
        for b in range(4): RNAMES.append('HOUR_Q%d' % (b+1))
    else:
        for b in range(4): RNAMES.append('%s_Q%d' % (nm, b+1))

def regime_masks(m):
    rv = REG[m['gi']]  # (n,7)
    n = rv.shape[0]
    out = {'REG_ALL': np.ones(n, bool)}
    for k, nm in enumerate(REGNAMES):
        col = rv[:, k]
        if nm == 'HOUR':
            for b in range(4):
                out['HOUR_Q%d' % (b+1)] = (col >= b*6) & (col < (b+1)*6)
        else:
            t = THR[nm]
            out['%s_Q1' % nm] = col <= t[0]
            out['%s_Q2' % nm] = (col > t[0]) & (col <= t[1])
            out['%s_Q3' % nm] = (col > t[1]) & (col <= t[2])
            out['%s_Q4' % nm] = col > t[2]
    return out
for m in mints:
    m['RM'] = regime_masks(m)

# ---------------- scan ----------------
POS = ['full', 'pyramid', 'partial_tp']

def run(group, ename, rname, si):
    """returns dict: per-position (mint-equal mean net, median, n, clusters, res_rate)"""
    per = {p: [] for p in POS}       # list of per-mint mean net returns
    allr = {p: [] for p in POS}      # pooled trade returns (for median only)
    ntr = 0; nres = 0
    for m in group:
        ex, rf, rp, rt = m['OUT'][si]
        mask = m['EM'][ename] & m['RM'][rname]
        S = np.nonzero(mask)[0]
        if len(S) == 0: continue
        n = len(m['ts'])
        exl = ex.tolist(); rfl = rf.tolist(); rpl = rp.tolist(); rtl = rt.tolist()
        cur = -1
        tr = {p: [] for p in POS}
        for i in S.tolist():
            e = i + 1
            if e >= n: break
            if e <= cur: continue
            x = exl[e]
            if x < 0:
                for p in POS: tr[p].append(DROP)
                ntr += 1
                cur = n
                break
            g = {'full': rfl[e], 'pyramid': rpl[e], 'partial_tp': rtl[e]}
            for p in POS:
                tr[p].append((1.0 + g[p]) * (1.0 - TOLL) - 1.0)
            ntr += 1; nres += 1
            cur = x
        if not tr['full']: continue
        for p in POS:
            per[p].append(float(np.mean(tr[p])))
            allr[p].extend(tr[p])
    res = {}
    for p in POS:
        if len(per[p]) == 0:
            res[p] = None; continue
        res[p] = dict(mean=float(np.mean(per[p])), median=float(np.median(allr[p])),
                      n=len(allr[p]), clusters=len(per[p]),
                      res_rate=(nres/ntr if ntr else 0.0), permint=per[p])
    return res

L('sweeping...')
results = {}
cnt = 0
for si in range(len(EX)):
    for ename in ENAMES:
        for rname in RNAMES:
            rt = run(TR, ename, rname, si)
            results[(si, ename, rname)] = rt
            cnt += 3
    L('  swept exit', EX[si][0], 'combos', cnt)
L('TRAIN combos evaluated', cnt)

# controls: entry ALL, regime ALL per (si, pos)
ctrl_tr = {si: results[(si, 'ALL', 'REG_ALL')] for si in range(len(EX))}

rows = []
for (si, ename, rname), rt in results.items():
    for p in POS:
        r = rt.get(p)
        if r is None: continue
        c = ctrl_tr[si][p]
        rows.append(dict(si=si, exitn=EX[si][0], entry=ename, regime=rname, pos=p,
                         mean=r['mean'], median=r['median'], n=r['n'], clusters=r['clusters'],
                         res=r['res_rate'], ctrl=c['mean'], edge=r['mean']-c['mean']))
rows.sort(key=lambda d: -d['mean'])
json.dump(rows[:400], open(OUT+'/train_top.json','w'), indent=0)
L('TRAIN top 25:')
for d in rows[:25]:
    L('   %.4f edge %+.4f n=%d k=%d res=%.2f | %s | %s | %s | %s' % (
        d['mean'], d['edge'], d['n'], d['clusters'], d['res'], d['exitn'], d['entry'], d['regime'], d['pos']))
L('TRAIN control means (ALL/REG_ALL):')
for si in range(len(EX)):
    for p in POS:
        c = ctrl_tr[si][p]
        L('   %-18s %-11s mean %+.4f med %+.4f n=%d k=%d res=%.2f' % (EX[si][0], p, c['mean'], c['median'], c['n'], c['clusters'], c['res_rate']))

# ---------------- select train positives, retest on validate ----------------
cand = [d for d in rows if d['mean'] > 0 and d['edge'] > 0.005 and d['clusters'] >= 20]
L('train positives (mean>0, edge>0.5pp, k>=20):', len(cand))

ctrl_va = {}
for si in range(len(EX)):
    ctrl_va[si] = run(VA, 'ALL', 'REG_ALL', si)

def boot(permint, B=2000, seed=7):
    rng = random.Random(seed)
    k = len(permint)
    if k < 5: return (float('nan'), float('nan'))
    ms = []
    for _ in range(B):
        s = sum(permint[rng.randrange(k)] for _ in range(k)) / k
        ms.append(s)
    ms.sort()
    return (ms[int(0.05*B)], ms[int(0.95*B)])

surv = []
seen = set()
for d in cand:
    key = (d['si'], d['entry'], d['regime'])
    if key not in seen:
        seen.add(key)
        results[('V',)+key] = run(VA, d['entry'], d['regime'], d['si'])
    rv = results[('V',)+key].get(d['pos'])
    if rv is None: continue
    cv = ctrl_va[d['si']][d['pos']]
    lo, hi = boot(rv['permint'])
    rec = dict(d)
    rec.update(v_mean=rv['mean'], v_median=rv['median'], v_n=rv['n'], v_clusters=rv['clusters'],
               v_res=rv['res_rate'], v_ctrl=cv['mean'], v_edge=rv['mean']-cv['mean'],
               v_lo=lo, v_hi=hi)
    surv.append(rec)

surv.sort(key=lambda d: -d['v_mean'])
json.dump(surv, open(OUT+'/validate_all.json','w'), indent=0, default=float)
L('VALIDATE results for %d train-positive combos. Top 40:' % len(surv))
for d in surv[:40]:
    L('   tr %+.4f | va %+.4f (med %+.4f, ci %.3f..%.3f) vedge %+.4f n=%d k=%d res=%.2f | %s|%s|%s|%s' % (
        d['mean'], d['v_mean'], d['v_median'], d['v_lo'], d['v_hi'], d['v_edge'],
        d['v_n'], d['v_clusters'], d['v_res'], d['exitn'], d['entry'], d['regime'], d['pos']))

hard = [d for d in surv if d['v_mean'] > 0 and d['v_edge'] > 0 and d['v_clusters'] >= 20 and d['v_lo'] > 0]
L('SURVIVORS (validate mean>0, beats control, k>=20, boot5%>0):', len(hard))
for d in hard:
    L('   ** %s' % json.dumps({k: v for k, v in d.items()}, default=float))
json.dump(hard, open(OUT+'/survivors.json','w'), indent=1, default=float)

# ---------------- regime response surface (baseline entry ALL) ----------------
L('RESPONSE SURFACE: entry=ALL, pos=full, train mean by regime bucket')
for si in [1, 3, 5]:
    L(' exit %s  (control %+.4f)' % (EX[si][0], ctrl_tr[si]['full']['mean']))
    for rname in RNAMES:
        r = results[(si, 'ALL', rname)]['full']
        if r: L('    %-22s %+.4f  n=%d k=%d' % (rname, r['mean'], r['n'], r['clusters']))
L('DONE')
log.close()
