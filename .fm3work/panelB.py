import sqlite3, json, hashlib, numpy as np
from collections import defaultdict

ROOT = '/home/anont/meme'


def hh(m):
    return int(hashlib.md5(m.encode()).hexdigest(), 16) % 3


def build():
    c = sqlite3.connect('file:%s/research/midcap/grad_ohlcv.sqlite?mode=ro' % ROOT, uri=True)
    w = sqlite3.connect('file:%s/research/b11a/window_labels.sqlite?mode=ro' % ROOT, uri=True)
    wl = {}
    creates = defaultdict(list)
    for m, cr, bt, co in w.execute('select mint,creator,block_time,complete from window_label'):
        wl[m] = (cr, bt, co)
        if cr is not None and bt is not None:
            creates[cr].append((bt, co))
    for cr in creates:
        creates[cr].sort()

    mints = []
    TS = []; O = []; HI = []; LO = []; CL = []; VO = []; MID = []
    rows = c.execute('select mint,bars_json,n_bars from ohlcv where n_bars>0').fetchall()
    for mint, bj, nb in rows:
        if hh(mint) == 0:
            continue                      # RESERVED HOLDOUT - never touched
        if mint not in wl:
            continue
        bars = json.loads(bj)
        bars.sort(key=lambda b: b[0])
        if len(bars) < 2:
            continue
        cr, bt, co = wl[mint]
        pc = 0; pg = 0
        for obt, oco in creates.get(cr, []):
            if obt < bt:
                pc += 1
                pg += (1 if oco else 0)
            else:
                break
        mid = len(mints)
        mints.append(dict(mint=mint, h=hh(mint), creator=cr, block_time=bt,
                          prior_creates=pc, prior_grads=pg, n=len(bars)))
        for b in bars:
            TS.append(b[0]); O.append(b[1]); HI.append(b[2]); LO.append(b[3])
            CL.append(b[4]); VO.append(b[5]); MID.append(mid)
    return dict(ts=np.array(TS, dtype=np.int64), o=np.array(O), hi=np.array(HI),
                lo=np.array(LO), cl=np.array(CL), vo=np.array(VO),
                mid=np.array(MID, dtype=np.int32), mints=mints)


def features(d):
    ts = d['ts']; hi = d['hi']; cl = d['cl']; mid = d['mid']; mints = d['mints']
    n = len(ts)
    age_h = np.zeros(n); dd = np.zeros(n); m_since_ath = np.zeros(n); gap = np.zeros(n)
    since_first = np.zeros(n); prior_c = np.zeros(n); prior_g = np.zeros(n)
    bnds = []
    i = 0
    while i < n:
        j = i
        while j < n and mid[j] == mid[i]:
            j += 1
        bnds.append((i, j)); i = j
    for (a, b) in bnds:
        mm = mints[mid[a]]
        bt = mm['block_time']
        age_h[a:b] = (ts[a:b] - bt) / 3600.0
        since_first[a:b] = (ts[a:b] - ts[a]) / 60.0
        prior_c[a:b] = mm['prior_creates']; prior_g[a:b] = mm['prior_grads']
        runmax = np.maximum.accumulate(hi[a:b])
        dd[a:b] = cl[a:b] / runmax
        L = b - a
        argm = np.zeros(L, dtype=np.int64); best = -1e30; bi = 0
        for k in range(L):
            if hi[a + k] >= best:
                best = hi[a + k]; bi = k
            argm[k] = bi
        m_since_ath[a:b] = (ts[a:b] - ts[a + argm]) / 60.0
        g = np.empty(L); g[0] = 1.0
        if L > 1:
            g[1:] = (ts[a + 1:b] - ts[a:b - 1]) / 60.0
        gap[a:b] = g
    mcap_k = cl * 1e9 / 1000.0
    return dict(age_h=age_h, dd=dd, m_since_ath=m_since_ath, gap=gap,
                since_first=since_first, prior_c=prior_c, prior_g=prior_g,
                mcap_k=mcap_k, vo=d['vo'], bnds=bnds)


def exits(d, H, slack_s):
    ts = d['ts']; o = d['o']
    n = len(ts)
    gross = np.full(n, np.nan); res = np.zeros(n, dtype=bool)
    block = np.zeros(n, dtype=np.int64); entry_ok = np.zeros(n, dtype=bool)
    for (a, b) in d['_bnds']:
        tsm = ts[a:b]
        for p in range(a, b - 1):
            e = p + 1
            tgt = ts[e] + H * 60
            q = a + int(np.searchsorted(tsm, tgt, side='left'))
            entry_ok[p] = True
            if q < b and ts[q] <= tgt + slack_s:
                gross[p] = o[q] / o[e] - 1.0
                res[p] = True
                block[p] = q
            else:
                res[p] = False
                block[p] = b
    return gross, res, block, entry_ok


def simulate(mask, gross, res, block, mid, nmints, toll, drop):
    idx = np.flatnonzero(mask)
    sums = np.zeros(nmints); cnts = np.zeros(nmints, dtype=np.int64)
    nf = -1; ntr = 0; nres = 0
    for p in idx:
        if p < nf:
            continue
        m = mid[p]
        if res[p]:
            r = gross[p] - toll; nres += 1
        else:
            r = drop - toll
        sums[m] += r; cnts[m] += 1; ntr += 1
        nf = block[p]
    act = cnts > 0
    if act.sum() == 0:
        return None
    pm = sums[act] / cnts[act]
    return dict(mint_mean=float(pm.mean()), mint_median=float(np.median(pm)),
                n=int(ntr), k=int(act.sum()),
                res_rate=float(nres / ntr) if ntr else 0.0, per_mint=pm)
