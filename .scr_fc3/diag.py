import pickle, numpy as np, hashlib, sqlite3, json, collections

def hh(m):
    return int(hashlib.md5(m.encode()).hexdigest(), 16) % 3

d = pickle.load(open('/home/anont/meme/.scr_fc3/cache.pkl', 'rb'))
bars, feats = d['bars'], d['feats']

c = sqlite3.connect('file:/home/anont/meme/research/midcap/grad_ohlcv.sqlite?mode=ro', uri=True)
fa = {m: (f, lt) for m, f, lt in c.execute("select mint,fetched_at,last_ts from ohlcv where status='ok'") if hh(m) in (1, 2)}
c.close()
fs = sorted(v[0] for v in fa.values())
ls = sorted(v[1] for v in fa.values())
print('fetched_at p5/p50/p95', fs[len(fs)//20], fs[len(fs)//2], fs[19*len(fs)//20])
print('last_ts   p5/p50/p95', ls[len(ls)//20], ls[len(ls)//2], ls[19*len(ls)//20])
gap = sorted((fa[m][0] - fa[m][1]) / 60 for m in fa)
print('fetched-last (min) p10/p50/p90', gap[len(gap)//10], gap[len(gap)//2], gap[9*len(gap)//10])

trn = [m for m in bars if hh(m) == 1]
mc, ag, ar, vo, gp = [], [], [], [], []
for m in trn:
    a = bars[m]
    p = a[:, 4]
    rm = np.maximum.accumulate(p)
    mc.append(p * 1e9)
    ag.append((a[:, 0] - feats[m]['t_create']) / 60.0)
    ar.append(p / rm)
    v5 = np.convolve(a[:, 5], np.ones(5), 'full')[:len(a)]
    vo.append(v5)
    gp.append(np.diff(a[:, 0]) / 60.0)
mc = np.concatenate(mc); ag = np.concatenate(ag); ar = np.concatenate(ar); vo = np.concatenate(vo); gp = np.concatenate(gp)
for nm, arr in (('mcap_sol', mc), ('age_min', ag), ('ath_ratio', ar), ('vol5', vo), ('bargap_min', gp)):
    q = np.percentile(arr, [5, 10, 25, 50, 75, 90, 95])
    print(nm, ' '.join('%.4g' % x for x in q))
print('n train bars', len(mc))
nb = sorted(len(bars[m]) for m in bars)
print('bars per mint p10/p50/p90', nb[len(nb)//10], nb[len(nb)//2], nb[9*len(nb)//10])
