"""Build the feature/bar cache for the creator-identity slice.
STRICT: only mints with md5(mint)%3 in (1,2) are ever read.
"""
import sqlite3, os, json, hashlib, collections, pickle, time
import numpy as np

OUT = '/home/anont/meme/.scr_fc3/cache.pkl'


def hh(m):
    return int(hashlib.md5(m.encode()).hexdigest(), 16) % 3


t0 = time.time()

# ---------- window_label (h12 only) ----------
w = sqlite3.connect('file:/home/anont/meme/research/b11a/window_labels.sqlite?mode=ro', uri=True)
wl = []
for r in w.execute('select bonding_curve,mint,creator,create_slot,block_time,complete,creator_onchain,data_len,status from window_label'):
    if hh(r[1]) in (1, 2) and r[4]:
        wl.append(dict(curve=r[0], mint=r[1], creator=r[2], slot=r[3], bt=r[4],
                       complete=r[5], conchain=r[6], dlen=r[7], status=r[8]))
w.close()
wl_by_mint = {r['mint']: r for r in wl}
by_creator = collections.defaultdict(list)
for r in wl:
    by_creator[r['creator']].append(r)
for v in by_creator.values():
    v.sort(key=lambda r: r['bt'])
print('h12 window_label rows', len(wl), 'creators', len(by_creator))

# ---------- ohlcv (h12 only) ----------
c = sqlite3.connect('file:/home/anont/meme/research/midcap/grad_ohlcv.sqlite?mode=ro', uri=True)
bars = {}
for mint, bj, n in c.execute("select mint,bars_json,n_bars from ohlcv where status='ok'"):
    if hh(mint) not in (1, 2):
        continue
    if not bj:
        continue
    b = json.loads(bj)
    if not b:
        continue
    b.sort(key=lambda x: x[0])
    a = np.array(b, dtype=float)
    # drop bars with non-positive prices
    ok = (a[:, 1] > 0) & (a[:, 2] > 0) & (a[:, 3] > 0) & (a[:, 4] > 0)
    a = a[ok]
    if len(a) < 3:
        continue
    bars[mint] = a
c.close()
print('mints with usable bars', len(bars), 'bars', sum(len(v) for v in bars.values()))

GLOBAL_LAST = max(v[-1, 0] for v in bars.values())
print('global last ts', GLOBAL_LAST)

# ---------- prior-coin outcome lookup: first-hour return of each h12 graduated coin ----------
first_hour_ret = {}
for m, a in bars.items():
    t_end = a[0, 0] + 3600
    j = int(np.searchsorted(a[:, 0], t_end))
    if j < len(a):
        first_hour_ret[m] = a[j, 1] / a[0, 1] - 1.0

# ---------- dev-buy features from b11a bodies (coverage is thin; computed anyway) ----------
devbuy = {}
try:
    b = sqlite3.connect('file:/home/anont/meme/research/b11a/b11a_bodies.sqlite?mode=ro', uri=True)
    curves = {r['curve']: r for r in wl}
    obs = collections.defaultdict(list)
    for r in b.execute('select slot,transaction_index,outer_index,inner_index,bonding_curve,virtual_quote_before,virtual_quote_after from reserve_observation'):
        bc = r[4]
        if bc in curves and len(obs[bc]) < 12:
            obs[bc].append(r)
    TRADER_IDX = {'buy': 6, 'sell': 6, 'buy_exact_sol_in': 6,
                  'buy_v2': 13, 'sell_v2': 13, 'buy_exact_sol_in_v2': 13,
                  'buy_exact_quote_in_v2': 13, 'sell_exact_token_in_v2': 13}
    for bc, rs in obs.items():
        rs.sort(key=lambda r: (r[0], r[1], r[2], r[3]))
        creator = curves[bc]['creator']
        tot = 0.0
        found = False
        for r in rs:
            ins = b.execute('select idl_name,accounts_json from instruction where slot=? and transaction_index=? and outer_index=? and inner_index=?',
                            (r[0], r[1], r[2], r[3])).fetchone()
            if not ins or not ins[1]:
                continue
            idx = TRADER_IDX.get(ins[0])
            if idx is None:
                continue
            acc = json.loads(ins[1])
            if idx >= len(acc):
                continue
            if r[5] is None or r[6] is None:
                continue
            dq = (r[6] - r[5]) / 1e9
            if acc[idx] == creator and dq > 0:
                tot += dq
                found = True
        devbuy[curves[bc]['mint']] = tot if found else 0.0
    b.close()
except Exception as e:
    print('devbuy failed', e)
print('devbuy coverage', len(devbuy), 'nonzero', sum(1 for v in devbuy.values() if v > 0))

# ---------- creator features, strictly as-of ----------
HOUR = 3600
feats = {}
for m, a in bars.items():
    wr = wl_by_mint.get(m)
    if not wr:
        continue
    t_create = wr['bt']
    pri = [x for x in by_creator[wr['creator']] if x['bt'] < t_create]
    f = {}
    f['t_create'] = t_create
    f['creator'] = wr['creator']
    f['dlen'] = wr['dlen'] if wr['dlen'] is not None else -1
    f['conchain_match'] = 1 if (wr['conchain'] == wr['creator']) else 0
    f['n_prior'] = len(pri)
    # lagged variants: priors created at least LAG before t_create (graduation-lookahead guard)
    for lag_name, lag in (('0', 0), ('2h', 2 * HOUR), ('6h', 6 * HOUR)):
        p2 = [x for x in pri if x['bt'] <= t_create - lag]
        f['np_' + lag_name] = len(p2)
        f['ng_' + lag_name] = sum(1 for x in p2 if x['complete'] == 1)
    f['n_prior_grad'] = f['ng_2h']          # default: 2h-lagged graduation count
    f['n_prior_lag'] = f['np_2h']
    f['frac_grad'] = (f['ng_2h'] / f['np_2h']) if f['np_2h'] > 0 else -1.0
    f['recency_min'] = ((t_create - pri[-1]['bt']) / 60.0) if pri else 1e9
    f['burst_60'] = sum(1 for x in pri if x['bt'] >= t_create - HOUR)
    f['burst_15'] = sum(1 for x in pri if x['bt'] >= t_create - 900)
    f['burst_360'] = sum(1 for x in pri if x['bt'] >= t_create - 6 * HOUR)
    # prior graduated coins' realised first-hour outcome (h12 only, lagged 2h)
    outs = [first_hour_ret[x['mint']] for x in pri
            if x['bt'] <= t_create - 2 * HOUR and x['mint'] in first_hour_ret]
    f['n_prior_out'] = len(outs)
    f['prior_out_med'] = float(np.median(outs)) if outs else -99.0
    # dev-buy on this mint and creator's prior dev-buy median
    f['devbuy'] = devbuy.get(m, -1.0)
    pdb = [devbuy[x['mint']] for x in pri if x['mint'] in devbuy]
    f['n_prior_db'] = len(pdb)
    f['prior_db_med'] = float(np.median(pdb)) if pdb else -1.0
    feats[m] = f

print('mints with features', len(feats))
mints = sorted(feats)
print('elapsed', time.time() - t0)

with open(OUT, 'wb') as fh:
    pickle.dump(dict(bars={m: bars[m] for m in mints}, feats=feats,
                     global_last=GLOBAL_LAST), fh, protocol=4)
print('wrote', OUT, os.path.getsize(OUT))

# ---------- diagnostics ----------
import statistics as st
h1 = [m for m in mints if hh(m) == 1]
h2 = [m for m in mints if hh(m) == 2]
print('train(h1)', len(h1), 'validate(h2)', len(h2))
lag = [ (bars[m][0,0] - feats[m]['t_create'])/60 for m in mints]
lag.sort()
print('first_bar - create (min): p10 %.1f med %.1f p90 %.1f' % (lag[len(lag)//10], lag[len(lag)//2], lag[9*len(lag)//10]))
for k in ('n_prior', 'np_2h', 'ng_2h', 'burst_60', 'n_prior_out', 'n_prior_db'):
    vals = [feats[m][k] for m in mints]
    print(k, 'nonzero', sum(1 for v in vals if v > 0), 'med', st.median(vals), 'max', max(vals))
vals = [feats[m]['frac_grad'] for m in mints if feats[m]['np_2h'] >= 2]
print('frac_grad n>=2:', len(vals), 'med', st.median(vals) if vals else None,
      'frac with >0:', sum(1 for v in vals if v > 0))
print('dlen dist', collections.Counter(feats[m]['dlen'] for m in mints).most_common(6))
print('conchain_match', collections.Counter(feats[m]['conchain_match'] for m in mints))
