import sqlite3, os, json, hashlib, collections, statistics

def hh(m):
    return int(hashlib.md5(m.encode()).hexdigest(), 16) % 3

# --- window_label, restricted to h in (1,2) ONLY ---
w = sqlite3.connect('file:/home/anont/meme/research/b11a/window_labels.sqlite?mode=ro', uri=True)
rows = w.execute('select bonding_curve,mint,creator,create_slot,block_time,complete,status from window_label').fetchall()
w.close()
print('total window_label rows', len(rows))
keep = [r for r in rows if hh(r[1]) in (1, 2)]
print('h12 rows', len(keep))
del rows
creators = collections.Counter(r[2] for r in keep)
print('distinct creators (h12)', len(creators))
dist = collections.Counter(min(v, 20) for v in creators.values())
print('creates-per-creator dist (capped 20):', sorted(dist.items()))
print('graduated h12', sum(1 for r in keep if r[5] == 1))
bts = [r[4] for r in keep if r[4]]
print('block_time range', min(bts), max(bts))

# --- ohlcv ---
c = sqlite3.connect('file:/home/anont/meme/research/midcap/grad_ohlcv.sqlite?mode=ro', uri=True)
orows = c.execute("select mint,pool,n_bars,first_ts,last_ts,status from ohlcv").fetchall()
c.close()
oh12 = [r for r in orows if hh(r[0]) in (1, 2) and r[5] == 'ok' and r[2] and r[2] > 0]
print('ohlcv rows', len(orows), 'h12 ok', len(oh12))
print('bars in h12', sum(r[2] for r in oh12))
print('h1', sum(1 for r in oh12 if hh(r[0]) == 1), 'h2', sum(1 for r in oh12 if hh(r[0]) == 2))
print('global last_ts', max(r[4] for r in oh12), 'global first_ts', min(r[3] for r in oh12))

wl_by_mint = {r[1]: r for r in keep}
matched = [r for r in oh12 if r[0] in wl_by_mint]
print('ohlcv h12 matched to window_label:', len(matched))

# creator prior-count for matched mints (h12-only priors)
by_creator = collections.defaultdict(list)
for r in keep:
    if r[4]:
        by_creator[r[2]].append(r)
for v in by_creator.values():
    v.sort(key=lambda r: r[4])

npriors = []
for r in matched:
    wl = wl_by_mint[r[0]]
    t0 = wl[4]
    pri = [x for x in by_creator[wl[2]] if x[4] < t0]
    npriors.append(len(pri))
print('n_prior dist for tradeable mints:', sorted(collections.Counter(min(n, 10) for n in npriors).items()))

# --- fresh snapshots coverage ---
seen = collections.Counter()
meta = {}
n = 0
with open('/home/anont/meme/research/midcap/fresh_snapshots.jsonl') as f:
    for line in f:
        n += 1
        try:
            d = json.loads(line)
        except Exception:
            continue
        m = d.get('mint')
        if not m or hh(m) not in (1, 2):
            continue
        seen[m] += 1
        meta.setdefault(m, d)
print('snapshot lines', n, 'distinct h12 mints in snapshots', len(seen))
tset = set(r[0] for r in matched)
print('tradeable mints with >=1 snapshot:', len(tset & set(seen)))
k = list(meta.values())[0]
print('snapshot keys', sorted(k.keys()))
