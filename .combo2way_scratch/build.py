"""Build feature matrix + 15m outcome table for combo-2way search.
HOLDOUT RULE: only mints with md5(mint)%3 in (1,2). h==0 never read/counted.
"""
import sqlite3, json, hashlib, math, os, sys
import numpy as np

ROOT = '/home/anont/meme'
OUT = os.path.join(ROOT, '.combo2way_scratch')

def h3(m):
    return int(hashlib.md5(m.encode()).hexdigest(), 16) % 3

# ---------- 1. bars ----------
con = sqlite3.connect('file:%s/research/midcap/grad_ohlcv.sqlite?mode=ro' % ROOT, uri=True)
rows = con.execute("select mint,bars_json from ohlcv where n_bars>0").fetchall()
bars = {}
for m, bj in rows:
    hv = h3(m)
    if hv == 0:
        continue                      # NEVER touched
    b = sorted(json.loads(bj), key=lambda z: z[0])
    if len(b) >= 8:
        bars[m] = (hv, b)
print('mints kept', len(bars), 'bars', sum(len(v[1]) for v in bars.values()))

MY = set(bars)

# ---------- 2. metadata from fresh_snapshots ----------
meta = {}
fp = os.path.join(ROOT, 'research/midcap/fresh_snapshots.jsonl')
nline = 0
with open(fp) as f:
    for line in f:
        nline += 1
        if '"mint"' not in line:
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        m = d.get('mint')
        if m not in MY:               # h==0 rows discarded unread
            continue
        e = meta.setdefault(m, {'replies': 0, 'mcap': [], 'rsol': [], 'vsol': [],
                                'created_ms': None, 'sym': '', 'name': '',
                                'has_x': 0, 'has_tg': 0, 'has_web': 0, 'first_ts': None,
                                'ath': 0.0})
        try:
            e['replies'] = max(e['replies'], int(d.get('replies') or 0))
        except Exception:
            pass
        for k in ('mcap', 'rsol', 'vsol'):
            v = d.get(k)
            if isinstance(v, (int, float)) and v > 0:
                e[k].append(float(v))
        if d.get('created_ms'):
            e['created_ms'] = d['created_ms']
        if d.get('sym'):
            e['sym'] = d['sym']
        if d.get('name'):
            e['name'] = d['name']
        for k in ('has_x', 'has_tg', 'has_web'):
            if d.get(k):
                e[k] = 1
        try:
            e['ath'] = max(e['ath'], float(d.get('ath') or 0))
        except Exception:
            pass
        t = d.get('ts_ms')
        if t and (e['first_ts'] is None or t < e['first_ts']):
            e['first_ts'] = t
print('snapshot lines', nline, 'meta mints', len(meta))

# ---------- 3. features ----------
FEATS = ['ret1', 'ret5', 'ret15', 'ret30', 'dd_max', 'up_min', 'tot_ret', 'rvol15',
         'barrange', 'bodypos', 'volratio', 'logvol5', 'density15', 'age_min',
         'cumvol', 'hour', 'accel', 'vwapdev',
         'm_gradspeed', 'm_replies', 'm_socials', 'm_mcap', 'm_rsol', 'm_namelen', 'm_symlen']
NF = len(FEATS)

TOL_EXIT = 3600      # exit bar must be within 60 min of the 15m target, else dropout
HOLD = 900

rec_mint = []
rec_h = []
rec_pos = []
rec_feat = []
rec_gross = []       # nan when unresolved
rec_exitpos = []     # -1 when unresolved

mint_ids = []
for mi, (m, (hv, b)) in enumerate(sorted(bars.items())):
    mint_ids.append(m)
    n = len(b)
    ts = np.array([x[0] for x in b], dtype=np.int64)
    op = np.array([x[1] for x in b], dtype=np.float64)
    hi = np.array([x[2] for x in b], dtype=np.float64)
    lo = np.array([x[3] for x in b], dtype=np.float64)
    cl = np.array([x[4] for x in b], dtype=np.float64)
    vo = np.array([x[5] for x in b], dtype=np.float64)
    if np.any(cl <= 0) or np.any(op <= 0):
        good = (cl > 0) & (op > 0) & (hi > 0) & (lo > 0)
        if good.sum() < 8:
            continue
        ts, op, hi, lo, cl, vo = ts[good], op[good], hi[good], lo[good], cl[good], vo[good]
        n = len(ts)
    runmax = np.maximum.accumulate(hi)
    runmin = np.minimum.accumulate(lo)
    cumv = np.cumsum(vo)
    lr = np.zeros(n)
    lr[1:] = np.log(cl[1:] / cl[:-1])
    pv = cl * vo

    md = meta.get(m)
    if md:
        mcap = float(np.median(md['mcap'])) if md['mcap'] else np.nan
        rsol = float(np.median(md['rsol'])) if md['rsol'] else np.nan
        cms = md['created_ms']
        gradspeed = math.log1p(max(0.0, (ts[0] - cms / 1000.0) / 60.0)) if cms else np.nan
        replies = float(md['replies'])
        socials = float(md['has_x'] + md['has_tg'] + md['has_web'])
        namelen = float(len(md['name']))
        symlen = float(len(md['sym']))
    else:
        mcap = rsol = gradspeed = replies = socials = namelen = symlen = np.nan
    mfeat = [gradspeed, replies, socials,
             math.log1p(mcap) if mcap == mcap else np.nan,
             rsol, namelen, symlen]

    # index lookbacks (wall clock)
    i5 = np.searchsorted(ts, ts - 300, side='right') - 1
    i15 = np.searchsorted(ts, ts - 900, side='right') - 1
    i30 = np.searchsorted(ts, ts - 1800, side='right') - 1
    j5 = np.searchsorted(ts, ts - 300, side='left')     # first bar within 5m window
    j15 = np.searchsorted(ts, ts - 900, side='left')
    j30 = np.searchsorted(ts, ts - 1800, side='left')

    # exit resolution for entry at bar k (open of k)
    tgt = ts + HOLD
    ex = np.searchsorted(ts, tgt, side='left')
    ok_ex = (ex < n)
    exi = np.where(ok_ex, np.minimum(ex, n - 1), 0)
    within = ok_ex & ((ts[exi] - tgt) <= TOL_EXIT)

    for i in range(3, n - 1):
        if ts[i] - ts[0] < 300:
            continue
        if i5[i] < 0 or i15[i] < 0:
            continue
        k = i + 1                      # entry bar = next real bar
        f = [0.0] * NF
        f[0] = cl[i] / cl[i - 1] - 1.0
        f[1] = cl[i] / cl[i5[i]] - 1.0
        f[2] = cl[i] / cl[i15[i]] - 1.0
        f[3] = cl[i] / cl[i30[i]] - 1.0 if i30[i] >= 0 else np.nan
        f[4] = cl[i] / runmax[i] - 1.0
        f[5] = cl[i] / runmin[i] - 1.0
        f[6] = cl[i] / op[0] - 1.0
        seg = lr[max(1, j15[i]):i + 1]
        f[7] = float(seg.std()) if len(seg) >= 3 else np.nan
        f[8] = (hi[i] - lo[i]) / cl[i]
        f[9] = (cl[i] - lo[i]) / (hi[i] - lo[i]) if hi[i] > lo[i] else 0.5
        v5 = float(vo[j5[i]:i + 1].sum())
        v30 = float(vo[j30[i]:i + 1].sum())
        nb30 = (i + 1 - j30[i])
        f[10] = v5 / (v30 / max(1.0, nb30 / 5.0)) if v30 > 0 else np.nan
        f[11] = math.log1p(v5)
        f[12] = float(i + 1 - j15[i])
        f[13] = (ts[i] - ts[0]) / 60.0
        f[14] = math.log1p(cumv[i])
        f[15] = float((ts[i] // 3600) % 24)
        f[16] = f[1] - (f[2] - f[1]) / 2.0
        pvs = float(pv[j30[i]:i + 1].sum()); vvs = float(vo[j30[i]:i + 1].sum())
        f[17] = cl[i] / (pvs / vvs) - 1.0 if vvs > 0 else np.nan
        f[18:25] = mfeat

        if within[k]:
            g = op[exi[k]] / op[k] - 1.0
            xp = int(exi[k])
        else:
            g = np.nan
            xp = -1
        rec_mint.append(mi); rec_h.append(hv); rec_pos.append(k)
        rec_feat.append(f); rec_gross.append(g); rec_exitpos.append(xp)

F = np.array(rec_feat, dtype=np.float64)
np.savez_compressed(os.path.join(OUT, 'matrix.npz'),
                    F=F,
                    mint=np.array(rec_mint, dtype=np.int32),
                    hv=np.array(rec_h, dtype=np.int8),
                    pos=np.array(rec_pos, dtype=np.int32),
                    gross=np.array(rec_gross, dtype=np.float64),
                    exitpos=np.array(rec_exitpos, dtype=np.int32),
                    feats=np.array(FEATS))
with open(os.path.join(OUT, 'mints.json'), 'w') as fh:
    json.dump(mint_ids, fh)
print('rows', F.shape, 'mints used', len(set(rec_mint)))
print('resolution rate', float(np.mean(~np.isnan(rec_gross))))
gm = np.array(rec_gross)
print('unconditional gross mean (trade-pooled)', float(np.nanmean(gm)))
for f_i, name in enumerate(FEATS):
    col = F[:, f_i]
    ok = np.isfinite(col)
    print('%-12s valid=%.3f q=%s' % (name, ok.mean(),
          np.round(np.nanpercentile(col[ok], [1, 25, 50, 75, 99]), 4).tolist() if ok.sum() > 10 else 'NA'))
