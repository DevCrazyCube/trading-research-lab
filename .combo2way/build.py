import sqlite3, json, hashlib, math, os
import numpy as np

R = '/home/anont/meme/research'
OUT = '/home/anont/meme/.combo2way'
H = lambda m: int(hashlib.md5(m.encode()).hexdigest(), 16) % 3
W = 5   # rolling window (short, to keep the universe wide -- contract G)

# ---- window_labels metadata, h in (1,2) ONLY (holdout never read) ----
w = sqlite3.connect('file:%s/b11a/window_labels.sqlite?mode=ro' % R, uri=True)
rows = []
for mint, creator, cs, bt, comp in w.execute(
        'select mint,creator,create_slot,block_time,complete from window_label'):
    if mint is None or H(mint) == 0:
        continue
    rows.append((mint, creator, cs or 0, bt or 0, comp or 0))
rows.sort(key=lambda r: r[2])
seen = {}
meta = {}
for mint, creator, cs, bt, comp in rows:
    pc, pg = seen.get(creator, (0, 0))
    meta[mint] = dict(creator=creator, create_slot=cs, block_time=bt,
                      complete=comp, cr_prior=pc, cr_grad=pg)
    seen[creator] = (pc + 1, pg + (1 if comp else 0))
print('meta mints (h12):', len(meta))

# ---- ohlcv ----
c = sqlite3.connect('file:%s/midcap/grad_ohlcv.sqlite?mode=ro' % R, uri=True)
M = []
n_h12_any = 0
for mint, nb, ft, lt, bj, st in c.execute(
        "select mint,n_bars,first_ts,last_ts,bars_json,status from ohlcv where n_bars>0"):
    if H(mint) == 0:
        continue
    n_h12_any += 1
    try:
        b = json.loads(bj)
    except Exception:
        continue
    if not b:
        continue
    a = np.array(sorted(b, key=lambda x: x[0]), dtype=float)
    _, keep = np.unique(a[:, 0], return_index=True)
    a = a[np.sort(keep)]
    if len(a) < W + 2:
        continue
    M.append((mint, a))
print('h12 mints with any bars:', n_h12_any)
print('h12 mints usable (>=%d bars):' % (W + 2), len(M))

FEAT = ['ret1', 'ret3', 'ret5', 'ret15', 'dd', 'runup', 'rng', 'vol5',
        'volratio', 'logvol5', 'dens15', 'logpx', 'upfrac', 'vwapdev',
        'agemin', 'gapprev', 'hour', 'cr_prior', 'cr_grad', 'c2first']
cols = {f: [] for f in FEAT}
ts_l, open_l, close_l, mid_l, valid_l = [], [], [], [], []
mint_names = []

for mid, (mint, a) in enumerate(M):
    mint_names.append(mint)
    ts, o, hi, lo, cl, v = a[:, 0], a[:, 1], a[:, 2], a[:, 3], a[:, 4], a[:, 5]
    n = len(a)
    r1 = np.full(n, np.nan)
    r1[1:] = cl[1:] / np.maximum(cl[:-1], 1e-30) - 1

    def lag(x, k):
        y = np.empty(n)
        y[:k] = np.nan
        y[k:] = x[:-k]
        return y

    ret3 = cl / lag(cl, 3) - 1
    ret5 = cl / lag(cl, 5) - 1
    ret15 = cl / lag(cl, 15) - 1
    runmax = np.maximum.accumulate(hi)
    runmin = np.minimum.accumulate(lo)
    dd = cl / np.maximum(runmax, 1e-30) - 1
    runup = cl / np.maximum(runmin, 1e-30) - 1
    rng = (hi - lo) / np.maximum(cl, 1e-30)

    vol5 = np.full(n, np.nan); upf = np.full(n, np.nan)
    volr = np.full(n, np.nan); lv5 = np.full(n, np.nan); vwd = np.full(n, np.nan)
    for i in range(W, n):
        seg = r1[i - W + 1:i + 1]
        vol5[i] = np.nanstd(seg)
        upf[i] = float((seg > 0).mean())
        vs = v[i - W + 1:i + 1]
        mv = vs.mean()
        volr[i] = v[i] / mv if mv > 0 else np.nan
        lv5[i] = math.log10(1 + max(0.0, vs.sum()))
        tp = (hi[i - W + 1:i + 1] + lo[i - W + 1:i + 1] + cl[i - W + 1:i + 1]) / 3.0
        sw = vs.sum()
        vwd[i] = (cl[i] / ((tp * vs).sum() / sw) - 1) if sw > 0 else np.nan

    lo_idx = np.searchsorted(ts, ts - 900.0, side='left')
    dens = (np.arange(n) - lo_idx + 1).astype(float)
    gap = np.full(n, np.nan)
    gap[1:] = np.log10(1 + (ts[1:] - ts[:-1]) / 60.0)
    agemin = np.log10(1 + (ts - ts[0]) / 60.0)
    logpx = np.log10(np.maximum(cl, 1e-30))
    hour = ((ts // 3600) % 24).astype(float)

    md = meta.get(mint)
    cp = float(md['cr_prior']) if md else np.nan
    cg = float(md['cr_grad']) if md else np.nan
    bt = md['block_time'] if md else 0
    c2f = math.log10(1 + max(0.0, (ts[0] - bt) / 60.0)) if (md and bt > 0) else np.nan

    vals = dict(ret1=r1, ret3=ret3, ret5=ret5, ret15=ret15, dd=dd, runup=runup,
                rng=rng, vol5=vol5, volratio=volr, logvol5=lv5, dens15=dens,
                logpx=logpx, upfrac=upf, vwapdev=vwd, agemin=agemin,
                gapprev=gap, hour=hour,
                cr_prior=np.full(n, cp), cr_grad=np.full(n, cg),
                c2first=np.full(n, c2f))
    for f in FEAT:
        cols[f].append(vals[f])
    ts_l.append(ts); open_l.append(o); close_l.append(cl)
    mid_l.append(np.full(n, mid))
    ok = np.ones(n, bool)
    ok[:W + 1] = False        # warmup only; NOT a total-bar-count filter
    ok[-1:] = False           # need bar i+1 to exist as the entry bar
    valid_l.append(ok)

TS = np.concatenate(ts_l); OP = np.concatenate(open_l); CL = np.concatenate(close_l)
MID = np.concatenate(mid_l).astype(np.int32)
VALID = np.concatenate(valid_l)
X = np.column_stack([np.concatenate(cols[f]) for f in FEAT])
N = len(TS)

starts = np.zeros(len(M), int); ends = np.zeros(len(M), int)
p = 0
for mid, (mint, a) in enumerate(M):
    starts[mid] = p
    p += len(a)
    ends[mid] = p

EXIT = np.full(N, -1, np.int32)
for mid in range(len(M)):
    s, e = starts[mid], ends[mid]
    t = TS[s:e]
    j = np.searchsorted(t, t + 900.0, side='right') - 1 + s
    idx = np.arange(s, e)
    EXIT[s:e] = np.where(j > idx, j, -1)

hh = np.array([H(m) for m in mint_names])
np.savez_compressed(os.path.join(OUT, 'ds.npz'),
                    TS=TS, OP=OP, CL=CL, MID=MID, VALID=VALID, X=X, EXIT=EXIT,
                    starts=starts, ends=ends, hh=hh,
                    FEAT=np.array(FEAT), mints=np.array(mint_names))
sig = np.arange(N)[VALID]
print('N bars', N, 'mints', len(M), 'valid signal bars', len(sig))
print('train mints h1', int((hh == 1).sum()), 'validate mints h2', int((hh == 2).sum()))
print('exit resolution over all valid entries:', round(float((EXIT[sig + 1] >= 0).mean()), 4))
for k, f in enumerate(FEAT):
    col = X[sig, k]
    fin = np.isfinite(col)
    if fin.any():
        print('%-9s finite=%.3f q10=%.4g q50=%.4g q90=%.4g' % (
            f, fin.mean(), np.percentile(col[fin], 10),
            np.percentile(col[fin], 50), np.percentile(col[fin], 90)))
