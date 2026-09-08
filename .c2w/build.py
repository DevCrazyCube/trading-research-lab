"""Stage 1: build (mint,bar) feature matrix + 15m trade outcomes under the harness contract.
ONLY mints with md5(mint)%3 in (1,2). h==1 -> TRAIN, h==2 -> VALIDATE.
"""
import sqlite3, json, hashlib, collections, math
import numpy as np

OUT = open('/home/anont/meme/.c2w/build.txt', 'w')
def p(*a): print(*a, file=OUT); OUT.flush()

GOH = '/home/anont/meme/research/midcap/grad_ohlcv.sqlite'
WL  = '/home/anont/meme/research/b11a/window_labels.sqlite'

def hh(m): return int(hashlib.md5(m.encode()).hexdigest(), 16) % 3

# ---------- window_labels metadata ----------
wc = sqlite3.connect('file:%s?mode=ro' % WL, uri=True)
creator_creates = collections.Counter()
meta = {}
for mint, creator, block_time, cslot in wc.execute(
        "select mint, creator, block_time, create_slot from window_label"):
    creator_creates[creator] += 1          # exogenous prior, no outcome column touched
    if hh(mint) != 0:
        meta[mint] = (creator, block_time, cslot)
wc.close()

# ---------- ohlcv ----------
gc = sqlite3.connect('file:%s?mode=ro' % GOH, uri=True)
rows = gc.execute("select mint, n_bars, first_ts, last_ts, bars_json, fetched_at, status "
                  "from ohlcv where status='ok' and n_bars>0").fetchall()
rows = [r for r in rows if hh(r[0]) != 0]
p("mints h12 with bars:", len(rows))

fa = np.array([r[5] for r in rows], float)
lt = np.array([r[3] for r in rows], float)
p("fetched_at - last_ts (s) quantiles:", np.percentile(fa - lt, [0, 5, 25, 50, 75, 95, 100]).round(0).tolist())
p("n_bars==1000 count:", sum(1 for r in rows if r[1] >= 1000))

HOLD   = 900          # 15 minutes
GRACE  = 1800         # exit must land within +30 min of the 15m mark
TAIL_TRUNC_TOL = 900  # series ending within 15 min of fetch = collection truncation, not death
WARM_S = 1200         # 20 min of history required
WARM_N = 8

FEATNAMES = [
 'r1','r5','r15','r60','r_since_first','dd_from_ath','runup_from_low','rvol15','bar_range',
 'body_pos','gap_prev','active_frac15','vol_z','vol_share15','cumvol60','vwap_dev15',
 'age_min','price_level','ath_age_min','ttft_min','hour_utc','creator_creates',
 'accel_5_15','up_frac15','mdd15','vol_accel','dd60','ath_frac_life'
]
NF = len(FEATNAMES)

Xs=[]; mint_id=[]; hs=[]; ent_ts=[]; ret_g=[]; okv=[]; xts=[]
mints_used=[]
nsig_total=0; ndrop_trunc=0

for mi, (mint, n_bars, first_ts, last_ts, bj, fetched_at, status) in enumerate(rows):
    if mint not in meta:
        continue
    creator, block_time, cslot = meta[mint]
    b = sorted(json.loads(bj), key=lambda x: x[0])
    n = len(b)
    if n < WARM_N + 4:
        continue
    ts = np.array([x[0] for x in b], float)
    o  = np.array([x[1] for x in b], float)
    hi = np.array([x[2] for x in b], float)
    lo = np.array([x[3] for x in b], float)
    cl = np.array([x[4] for x in b], float)
    vo = np.array([x[5] for x in b], float)
    if np.any(cl <= 0) or np.any(o <= 0):
        good = (cl > 0) & (o > 0) & (hi > 0) & (lo > 0)
        ts, o, hi, lo, cl, vo = ts[good], o[good], hi[good], lo[good], cl[good], vo[good]
        n = len(ts)
        if n < WARM_N + 4: continue

    truncated_by_collection = (fetched_at - last_ts) <= TAIL_TRUNC_TOL

    # running extremes (causal)
    runmax = np.maximum.accumulate(hi)
    runmin = np.minimum.accumulate(lo)
    argmax = np.zeros(n, int)
    cm = -1e300; am = 0
    for i in range(n):
        if hi[i] > cm: cm = hi[i]; am = i
        argmax[i] = am
    ath_ts = ts[argmax]

    def back(K):
        j = np.searchsorted(ts, ts - K, side='right') - 1
        return np.clip(j, 0, n-1)
    b1, b5, b15, b60 = back(60), back(300), back(900), back(3600)

    r1  = cl/cl[b1]  - 1.0
    r5  = cl/cl[b5]  - 1.0
    r15 = cl/cl[b15] - 1.0
    r60 = cl/cl[b60] - 1.0
    rsf = cl/o[0]    - 1.0
    dd  = cl/runmax  - 1.0
    ru  = cl/runmin  - 1.0
    rng = (hi-lo)/cl
    bp  = np.where(hi>lo, (cl-lo)/np.maximum(hi-lo,1e-300), 0.5)
    gapp = np.empty(n); gapp[0]=60.0; gapp[1:] = ts[1:]-ts[:-1]

    lr = np.zeros(n); lr[1:] = np.log(cl[1:]/cl[:-1])
    rvol = np.zeros(n); actf = np.zeros(n); volz = np.zeros(n)
    vsh = np.zeros(n); cv60 = np.zeros(n); vwd = np.zeros(n)
    upf = np.zeros(n); mdd = np.zeros(n); vacc = np.zeros(n); dd60 = np.zeros(n)
    lo15 = np.searchsorted(ts, ts-900, side='left')
    lo60 = np.searchsorted(ts, ts-3600, side='left')
    cvol = np.concatenate([[0.0], np.cumsum(vo)])
    cpv  = np.concatenate([[0.0], np.cumsum(vo*cl)])
    for i in range(n):
        a = lo15[i]
        w = lr[a+1:i+1]
        rvol[i] = w.std() if len(w) > 1 else 0.0
        actf[i] = (i-a+1)/15.0
        sv = cvol[i+1]-cvol[a]
        vsh[i] = vo[i]/sv if sv > 0 else 0.0
        med = np.median(vo[a:i+1]) if i >= a else vo[i]
        volz[i] = math.log((vo[i]+1e-9)/(med+1e-9))
        a6 = lo60[i]
        sv6 = cvol[i+1]-cvol[a6]
        cv60[i] = math.log1p(sv6)
        sv2 = cvol[i+1]-cvol[a]
        vwap = (cpv[i+1]-cpv[a])/sv2 if sv2 > 1e-300 else cl[i]
        vwd[i] = cl[i]/vwap - 1.0 if vwap > 0 else 0.0
        upf[i] = float((w > 0).mean()) if len(w) else 0.5
        seg = cl[a:i+1]
        rm = np.maximum.accumulate(seg)
        mdd[i] = float((seg/rm - 1.0).min()) if len(seg) else 0.0
        vacc[i] = math.log((sv2 + 1e-9) / (sv6/4.0 + 1e-9))
        dd60[i] = cl[i]/hi[a6:i+1].max() - 1.0

    age_min = (ts - block_time)/60.0
    plev = np.log10(cl)
    athage = (ts - ath_ts)/60.0
    bsf = np.arange(n, dtype=float)
    ttft = np.full(n, (first_ts - block_time)/60.0)
    hour = ((ts//3600) % 24)
    ccr  = np.full(n, math.log1p(creator_creates.get(creator, 0)))
    accel = r5 - r15
    life = np.maximum(ts - ts[0], 1.0)
    athfrac = (ath_ts - ts[0]) / life          # where in the life so far the ATH sits

    F = np.column_stack([r1,r5,r15,r60,rsf,dd,ru,rvol,rng,bp,gapp,actf,volz,vsh,cv60,vwd,
                         age_min,plev,athage,ttft,hour,ccr,
                         accel,upf,mdd,vacc,dd60,athfrac])

    # ---- trades: signal at i, enter at OPEN of next real bar i+1, exit 15m later ----
    warm = (ts - ts[0] >= WARM_S) & (bsf >= WARM_N)
    kept=[]
    for i in range(n-1):
        if not warm[i]:
            continue
        e_ts = ts[i+1]; e_px = o[i+1]
        target = e_ts + HOLD
        j = int(np.searchsorted(ts, target, side='left'))
        resolved = (j < n) and (ts[j] <= target + GRACE)
        if not resolved:
            # drop the signal only if the series was cut by the collector, not by death
            if truncated_by_collection and (target + GRACE) > last_ts:
                ndrop_trunc += 1
                continue
            g = np.nan
            x_ts = target + GRACE
        else:
            g = o[j]/e_px - 1.0
            x_ts = ts[j]
        kept.append((i, e_ts, g, 1.0 if resolved else 0.0, x_ts))
        nsig_total += 1
    if not kept:
        continue
    ii = np.array([k[0] for k in kept])
    Xs.append(F[ii])
    mint_id.append(np.full(len(kept), len(mints_used)))
    ent_ts.append(np.array([k[1] for k in kept], float))
    ret_g.append(np.array([k[2] for k in kept], float))
    okv.append(np.array([k[3] for k in kept], float))
    xts.append(np.array([k[4] for k in kept], float))
    hs.append(np.full(len(kept), hh(mint)))
    mints_used.append(mint)

X = np.vstack(Xs)
mint_id = np.concatenate(mint_id)
ent_ts  = np.concatenate(ent_ts)
ret_g   = np.concatenate(ret_g)
okv     = np.concatenate(okv)
hs      = np.concatenate(hs)
exit_ts = np.concatenate(xts)

order = np.lexsort((ent_ts, mint_id))
X, mint_id, ent_ts, ret_g, okv, hs, exit_ts = (a[order] for a in (X, mint_id, ent_ts, ret_g, okv, hs, exit_ts))

p("mints used:", len(mints_used), " signal bars:", len(X))
p("  train h1 mints:", len(set(mint_id[hs==1].tolist())), " bars:", int((hs==1).sum()))
p("  valid h2 mints:", len(set(mint_id[hs==2].tolist())), " bars:", int((hs==2).sum()))
p("raw resolution rate:", round(float(okv.mean()), 4))
p("signals dropped as collector-truncated:", ndrop_trunc)
for k, nm in enumerate(FEATNAMES):
    q = np.nanpercentile(X[:, k], [1, 20, 40, 60, 80, 99])
    p("  feat %-14s p1/p20/p40/p60/p80/p99 = %s" % (nm, np.round(q, 4).tolist()))

np.savez_compressed('/home/anont/meme/.c2w/mat.npz', X=X, mint_id=mint_id, ent_ts=ent_ts,
                    ret_g=ret_g, ok=okv, hs=hs, exit_ts=exit_ts,
                    featnames=np.array(FEATNAMES))
p("saved.")
OUT.close()
