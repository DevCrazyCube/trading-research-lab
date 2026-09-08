import sqlite3, json, hashlib, math, pickle, os, sys
import numpy as np

OUT = '/home/anont/meme/_r0'
os.makedirs(OUT, exist_ok=True)
log = open(OUT + '/build.log', 'w')
def L(*a):
    log.write(' '.join(str(x) for x in a) + '\n'); log.flush()

def h3(m):
    return int(hashlib.md5(m.encode()).hexdigest(), 16) % 3

# ---------- load bars, ONLY h in (1,2) ----------
con = sqlite3.connect('file:/home/anont/meme/research/midcap/grad_ohlcv.sqlite?mode=ro', uri=True)
mints = []
skipped0 = 0
for mint, nb, bj in con.execute('select mint,n_bars,bars_json from ohlcv where n_bars>0'):
    hh = h3(mint)
    if hh == 0:
        skipped0 += 1
        continue          # NEVER touched further
    b = json.loads(bj)
    b.sort(key=lambda r: r[0])
    # dedupe ts
    seen = set(); bb = []
    for r in b:
        if r[0] in seen: continue
        seen.add(r[0]); bb.append(r)
    if len(bb) < 6: continue
    a = np.array(bb, dtype=np.float64)
    mints.append(dict(mint=mint, h=hh, ts=a[:,0].astype(np.int64), o=a[:,1], hi=a[:,2],
                      lo=a[:,3], c=a[:,4], v=a[:,5]))
con.close()
L('mints loaded', len(mints), 'h0 skipped(untouched)', skipped0)
L('h==1', sum(1 for m in mints if m['h']==1), 'h==2', sum(1 for m in mints if m['h']==2))
L('bars', sum(len(m['ts']) for m in mints))

# ---------- creates (for LAUNCH_1H), only h in (1,2) ----------
creates = []
try:
    c2 = sqlite3.connect('file:/home/anont/meme/research/b11a/window_labels.sqlite?mode=ro', uri=True)
    for mint, bt in c2.execute('select mint,block_time from window_label'):
        if mint is None or bt is None: continue
        if h3(mint) == 0: continue
        creates.append(int(bt))
    c2.close()
except Exception as e:
    L('window_labels err', e)
creates = np.array(sorted(creates), dtype=np.int64)
L('creates(h12)', len(creates), creates[:3] if len(creates) else '', creates[-3:] if len(creates) else '')

# ---------- global bar table for regime ----------
allts = np.concatenate([m['ts'] for m in mints])
allmi = np.concatenate([np.full(len(m['ts']), i, dtype=np.int32) for i, m in enumerate(mints)])
allc  = np.concatenate([m['c'] for m in mints])
allo  = np.concatenate([m['o'] for m in mints])
allv  = np.concatenate([m['v'] for m in mints])
srt = np.argsort(allts, kind='stable')
allts, allmi, allc, allo, allv = allts[srt], allmi[srt], allc[srt], allo[srt], allv[srt]
first_open = np.array([m['o'][0] for m in mints])
L('ts range', int(allts[0]), int(allts[-1]), 'span_days', (allts[-1]-allts[0])/86400.)

# ---------- regime series on 300s grid, 3600s lookback, strictly backward ----------
STEP = 300; WIN = 3600
g0 = (int(allts[0]) // STEP) * STEP
g1 = (int(allts[-1]) // STEP) * STEP + STEP
grid = np.arange(g0, g1 + STEP, STEP, dtype=np.int64)
NG = len(grid)
L('grid pts', NG)

last_close = {}   # mint_idx -> latest close seen (<= T)
REG = np.full((NG, 7), np.nan)   # LAUNCH1H, VOL1H, NACT1H, FRACUP1H, MEDRET1H, FRACABOVEOPEN, HOUR
lo_ptr = 0; hi_ptr = 0
seen_ptr = 0
for gi in range(NG):
    T = grid[gi]
    # advance last_close for all bars with ts <= T
    while seen_ptr < len(allts) and allts[seen_ptr] <= T:
        last_close[int(allmi[seen_ptr])] = allc[seen_ptr]
        seen_ptr += 1
    lo_t = T - WIN
    while hi_ptr < len(allts) and allts[hi_ptr] <= T: hi_ptr += 1
    while lo_ptr < hi_ptr and allts[lo_ptr] <= lo_t: lo_ptr += 1
    sl = slice(lo_ptr, hi_ptr)
    mi = allmi[sl]
    if len(mi) == 0:
        REG[gi,0] = np.searchsorted(creates, T, 'right') - np.searchsorted(creates, lo_t, 'right')
        REG[gi,6] = (T // 3600) % 24
        continue
    vol = float(allv[sl].sum())
    uniq = np.unique(mi)
    # per-mint first open in window and last close in window
    rets = []
    above = 0
    for u in uniq:
        idx = np.nonzero(mi == u)[0]
        fo = allo[sl][idx[0]]; lc = allc[sl][idx[-1]]
        if fo > 0: rets.append(lc/fo - 1.0)
        if first_open[u] > 0 and lc > first_open[u]: above += 1
    rets = np.array(rets) if rets else np.array([0.0])
    REG[gi,0] = np.searchsorted(creates, T, 'right') - np.searchsorted(creates, lo_t, 'right')
    REG[gi,1] = vol
    REG[gi,2] = len(uniq)
    REG[gi,3] = float((rets > 0).mean())
    REG[gi,4] = float(np.median(rets))
    REG[gi,5] = above / len(uniq)
    REG[gi,6] = (T // 3600) % 24

REGNAMES = ['LAUNCH1H','VOL1H','NACT1H','FRACUP1H','MEDRET1H','FRACABOVEOPEN','HOUR']
L('regime built. sample:', REG[NG//2].tolist())

# ---------- per-bar features + regime key ----------
for m in mints:
    ts = m['ts']; c = m['c']; v = m['v']; o = m['o']
    n = len(ts)
    m['age'] = (ts - ts[0]) / 60.0
    # prior 15m return (close vs close at last bar with ts <= t-900); nan if none
    j = np.searchsorted(ts, ts - 900, 'right') - 1
    r15 = np.full(n, np.nan)
    ok = j >= 0
    r15[ok] = c[ok] / c[j[ok]] - 1.0
    m['r15'] = r15
    # prior 60m return
    j2 = np.searchsorted(ts, ts - 3600, 'right') - 1
    r60 = np.full(n, np.nan)
    ok2 = j2 >= 0
    r60[ok2] = c[ok2] / c[j2[ok2]] - 1.0
    m['r60'] = r60
    # trailing rel volume: v_i / median(prev up to 20 bars), need >=5 prior
    rv = np.full(n, np.nan)
    for i in range(5, n):
        w = v[max(0, i-20):i]
        md = np.median(w)
        rv[i] = v[i]/md if md > 0 else np.nan
    m['relvol'] = rv
    # regime index: floor to STEP grid at or before ts (regime window ends at that T <= ts)
    gi = ((ts // STEP) * STEP - g0) // STEP
    gi = np.clip(gi, 0, NG-1)
    m['gi'] = gi.astype(np.int32)

pickle.dump(dict(mints=mints, REG=REG, REGNAMES=REGNAMES, grid=grid, g0=g0, STEP=STEP),
            open(OUT + '/cache.pkl', 'wb'))
L('DONE build')
log.close()
