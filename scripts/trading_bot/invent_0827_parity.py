"""INVENT_2026-08-27 parity-implied carry on the free DoltHub panel. Implements INVENT_2026-08-27_parity_PREREG.md.
Research only. No network. Held-out F1 is only read if design F1 clears both bars."""
import json, gzip, glob, math, bisect, statistics as st
import numpy as np
rng = np.random.default_rng(20260827)
ROOT = 'research'
DESIGN_END = '2023-06-30'
# --- data
fred = json.load(open(f'{ROOT}/data/ratescredit_cache/fred_daily.json'))
def rate(d):
    for ser in ('DGS1MO', 'DGS3MO'):
        ks = sorted(fred[ser]); i = bisect.bisect_right(ks, d) - 1
        while i >= 0:
            v = fred[ser][ks[i]]
            if v is not None and not (isinstance(v, float) and math.isnan(v)): return v / 100.0
            i -= 1
    return 0.0
bars = json.load(gzip.open(f'{ROOT}/data/t15_cache/daily_bars.json.gz'))
bdates = {s: [x[0] for x in v] for s, v in bars.items()}
bclose = {s: [x[1] for x in v] for s, v in bars.items()}
def fwd(s, d, a, b):
    """return close[t+b]/close[t+a]-1 where t is the bar index of snapshot date d (exact match required)."""
    ds = bdates.get(s)
    if not ds: return None
    i = bisect.bisect_left(ds, d)
    if i >= len(ds) or ds[i] != d or i + b >= len(ds): return None
    return bclose[s][i + b] / bclose[s][i + a] - 1
def dte(d, e):
    from datetime import date
    y, m, dd = map(int, d.split('-')); y2, m2, d2 = map(int, e.split('-'))
    return (date(y2, m2, d2) - date(y, m, dd)).days
# --- per snapshot extraction
files = sorted(glob.glob(f'{ROOT}/data/doltopts_cache/*.json'))
obs = []  # dict(date, sym, c, nf, oc, T)
hist = {}  # sym -> list of c (backward)
for f in files:
    d = f.split('/')[-1][:-5]
    if d < '2020-01-01': continue
    js = json.load(open(f)); r = rate(d)
    row = {}
    for s, rows in js['options'].items():
        sk = js['stocks'].get(s)
        if not sk: continue
        S = float(sk['close']); O = float(sk['open'])
        if S <= 0 or O <= 0: continue
        byexp = {}
        for q in rows:
            byexp.setdefault(q['expiration'], {}).setdefault(float(q['strike']), {})[q['call_put']] = (float(q['bid']), float(q['ask']))
        cands = [(dte(d, e), e) for e in byexp if 20 <= dte(d, e) <= 65]
        if not cands: continue
        T_days, e = max(cands); T = T_days / 365.0
        Fs, hws = [], []
        for K, cp in byexp[e].items():
            if 'Call' not in cp or 'Put' not in cp or abs(K / S - 1) > 0.075: continue
            (cb, ca), (pb, pa) = cp['Call'], cp['Put']
            if cb <= 0 or pb <= 0 or ca < cb or pa < pb: continue
            Fs.append(((ca + cb) / 2 - (pa + pb) / 2) * math.exp(r * T) + K)
            hws.append(0.5 * ((ca - cb) + (pa - pb)))
        if len(Fs) < 3: continue
        F = st.median(Fs); c = r - math.log(F / S) / T
        nf = (sum(hws) / len(hws)) / (S * T)
        h = hist.setdefault(s, [])
        c_res = c - st.median(h[-26:]) if len(h) >= 8 else None
        h.append(c)
        if c_res is None: continue
        row[s] = dict(c=c, c_res=c_res, nf=nf, oc=S / O - 1, T=T)
    if len(row) >= 30: obs.append((d, row))
print('snapshots with >=30 names & warm history:', len(obs), obs[0][0], obs[-1][0])
# --- books
def book(d, row, a, b):
    syms = sorted(row, key=lambda s: row[s]['c_res']); n = len(syms) // 3
    lo, hi = syms[:n], syms[-n:]
    rl = [fwd(s, d, a, b) for s in lo]; rh = [fwd(s, d, a, b) for s in hi]
    rl = [x for x in rl if x is not None]; rh = [x for x in rh if x is not None]
    if len(rl) < n * 0.8 or len(rh) < n * 0.8: return None, None
    return np.mean(rl) - np.mean(rh), (lo, hi)
def tstat(x): x = np.asarray(x); return x.mean() / (x.std(ddof=1) / math.sqrt(len(x))), x.mean(), len(x)
def placebo(d_rows, a, b, ndraw=1000):
    """size-matched random tercile draws: mean L/S per draw across the same dates."""
    per_date = []
    for d, row in d_rows:
        syms = [s for s in row if fwd(s, d, a, b) is not None]; n = len(syms) // 3
        if n < 5: continue
        rets = np.array([fwd(s, d, a, b) for s in syms]); per_date.append((rets, n))
    draws = np.zeros(ndraw)
    for k in range(ndraw):
        acc = []
        for rets, n in per_date:
            p = rng.permutation(len(rets)); acc.append(rets[p[:n]].mean() - rets[p[-n:]].mean())
        draws[k] = np.mean(acc)
    return float(np.percentile(draws, 99)), float(np.mean(draws)), float(np.std(draws))
def run_window(rows, label, read_returns=True):
    out = {'label': label, 'n_snapshots': len(rows), 'first': rows[0][0], 'last': rows[-1][0]}
    # F3 asynchrony + D measurability (diagnostics, always)
    cr = np.array([v['c_res'] for _, r in rows for v in r.values()]); oc = np.array([v['oc'] for _, r in rows for v in r.values()])
    X = np.vstack([np.ones_like(oc), oc]).T; beta, res, *_ = np.linalg.lstsq(X, cr, rcond=None)
    resid = cr - X @ beta; s2 = resid @ resid / (len(cr) - 2); se = math.sqrt(s2 / ((oc - oc.mean()) ** 2).sum())
    r2 = 1 - resid @ resid / ((cr - cr.mean()) ** 2).sum()
    out['F3_async'] = dict(slope=float(beta[1]), t=float(beta[1] / se), r2=float(r2), n=int(len(cr)))
    iqr = [float(np.subtract(*np.percentile([v['c_res'] for v in r.values()], [75, 25]))) for _, r in rows]
    nfm = [float(np.median([v['nf'] for v in r.values()])) for _, r in rows]
    out['D_borrow'] = dict(median_xs_IQR_cres=float(np.median(iqr)), median_noise_floor=float(np.median(nfm)),
                           ratio=float(np.median(iqr) / np.median(nfm)), measurable=bool(np.median(iqr) > 2 * np.median(nfm)),
                           median_c_level=float(np.median([v['c'] for _, r in rows for v in r.values()])))
    if not read_returns: return out
    for name, (a, b) in {'F1_exec_t1_t6': (1, 6), 'F2_sameprint_t0_t5': (0, 5)}.items():
        pnl = [book(d, r, a, b)[0] for d, r in rows]; pnl = [x for x in pnl if x is not None]
        t, m, n = tstat(pnl); p99, pm, ps = placebo(rows, a, b)
        out[name] = dict(t_weekly=float(t), mean_weekly=float(m), n_weeks=n, sharpe_ann=float(t / math.sqrt(n) * math.sqrt(52)),
                         placebo_p99=p99, placebo_mean=pm, placebo_sd=ps, clears_t=bool(t >= 2.5), clears_placebo=bool(m > p99),
                         net_mean_weekly_after_6p6bp=float(m - 0.00066))
    return out
design = [(d, r) for d, r in obs if d <= DESIGN_END]; held = [(d, r) for d, r in obs if d > DESIGN_END]
res = {'prereg_sha256': open(f'{ROOT}/trading_bot/INVENT_2026-08-27_parity_PREREG.sha256').read().split()[0]}
res['design'] = run_window(design, 'design 2020-01..2023-06')
f1 = res['design']['F1_exec_t1_t6']; gate = f1['clears_t'] and f1['clears_placebo']
res['design_F1_clears_both_bars'] = gate
res['heldout'] = run_window(held, 'held-out 2023-07..', read_returns=gate)
if not gate: res['heldout']['note'] = 'F1/F2 returns NOT read: design gate failed (prereg §4). Diagnostics only.'
json.dump(res, open(f'{ROOT}/trading_bot/INVENT_2026-08-27_parity.json', 'w'), indent=1)
print(json.dumps(res, indent=1))
