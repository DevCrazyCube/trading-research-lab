import json, hashlib, numpy as np
from collections import defaultdict

SNAP = '/home/anont/meme/research/midcap/fresh_snapshots.jsonl'


def hh(m):
    return int(hashlib.md5(m.encode()).hexdigest(), 16) % 3


def build():
    rows = defaultdict(dict)
    cyc = set()
    for line in open(SNAP):
        try:
            d = json.loads(line)
        except Exception:
            continue
        if 'mint' not in d:
            continue
        if hh(d['mint']) == 0:
            continue                       # RESERVED HOLDOUT - never touched
        rows[d['mint']][d['ts_ms']] = d
        cyc.add(d['ts_ms'])
    cy = sorted(cyc)
    ci = {t: i for i, t in enumerate(cy)}
    NC = len(cy)
    mints = sorted(rows.keys())
    M = len(mints)
    mcap = np.full((M, NC), np.nan)
    present = np.zeros((M, NC), dtype=bool)
    age_h = np.full((M, NC), np.nan)
    mar = np.full((M, NC), np.nan)
    tath = np.full((M, NC), np.nan)
    stale = np.full((M, NC), np.nan)
    cmp_ = np.zeros((M, NC), dtype=bool)
    X = np.zeros(M, dtype=bool); TG = np.zeros(M, dtype=bool); WEB = np.zeros(M, dtype=bool)
    h = np.zeros(M, dtype=np.int8)
    creator = []
    for i, m in enumerate(mints):
        dd = rows[m]
        h[i] = hh(m)
        r0 = dd[min(dd)]
        X[i] = bool(r0['has_x']); TG[i] = bool(r0['has_tg']); WEB[i] = bool(r0['has_web'])
        creator.append(r0.get('creator'))
        for t, r in dd.items():
            j = ci[t]
            present[i, j] = True
            mcap[i, j] = r['mcap']
            age_h[i, j] = (r['ts_ms'] - r['created_ms']) / 3.6e6 if r.get('created_ms') else np.nan
            a = r.get('ath')
            mar[i, j] = (r['mcap'] / a) if a else np.nan
            at = r.get('ath_ts')
            tath[i, j] = (r['ts_ms'] - at) / 60000.0 if at else np.nan
            lt = r.get('last_trade_ms')
            stale[i, j] = (r['ts_ms'] - lt) / 1000.0 if lt else np.nan
            cmp_[i, j] = bool(r['complete'])
    return dict(mints=mints, cy=np.array(cy), present=present, mcap=mcap, age_h=age_h,
                mar=mar, tath=tath, stale=stale, cmp=cmp_, X=X, TG=TG, WEB=WEB, h=h,
                creator=creator, M=M, NC=NC)


def exits(P, Hc, entry_slack=2, exit_slack=3):
    """signal at cycle j -> entry at first present cycle in (j, j+entry_slack]
       -> exit at first present cycle in [e+Hc, e+Hc+exit_slack].
       returns gross (M,NC), resolved, blockuntil (cycle index), eligible"""
    M, NC = P['M'], P['NC']
    pres = P['present']; mc = P['mcap']
    gross = np.full((M, NC), np.nan)
    res = np.zeros((M, NC), dtype=bool)
    filled = np.zeros((M, NC), dtype=bool)
    block = np.zeros((M, NC), dtype=np.int32)
    elig = np.zeros((M, NC), dtype=bool)
    for i in range(M):
        pr = pres[i]
        idx = np.flatnonzero(pr)
        if len(idx) < 2:
            continue
        last = idx[-1]
        for j in idx:
            if j >= NC - 1:
                continue
            elig[i, j] = True
            e = -1
            for k in range(j + 1, min(j + 1 + entry_slack, NC)):
                if pr[k]:
                    e = k; break
            if e < 0:
                block[i, j] = NC
                continue                      # unfilled -> dropout
            filled[i, j] = True
            q = -1
            for k in range(e + Hc, min(e + Hc + exit_slack + 1, NC)):
                if pr[k]:
                    q = k; break
            if q < 0:
                block[i, j] = NC
                continue                      # unresolved -> dropout
            gross[i, j] = mc[i, q] / mc[i, e] - 1.0
            res[i, j] = True
            block[i, j] = q
    return gross, res, filled, block, elig


def netarr(gross, res, toll, drop):
    return np.where(res, gross - toll, drop - toll)


def cellstat(mask, net, res, block, elig, ref=None):
    """greedy non-overlap per mint (row); mint-equal weights"""
    M, NC = mask.shape
    pm = []; ks = []; ntr = 0; nres = 0; excs = []
    for i in range(M):
        js = np.flatnonzero(mask[i])
        if len(js) == 0:
            continue
        nf = -1; s = 0.0; c = 0
        for j in js:
            if j < nf:
                continue
            s += net[i, j]; c += 1; ntr += 1
            if res[i, j]:
                nres += 1
            nf = block[i, j]
        if c:
            pm.append(s / c); ks.append(i)
            if ref is not None and not np.isnan(ref[i]):
                excs.append(s / c - ref[i])
    if not pm:
        return None
    pm = np.array(pm); excs = np.array(excs) if excs else np.array([])
    return dict(pm=pm, mints=np.array(ks), exc=excs,
                mean=float(pm.mean()), med=float(np.median(pm)),
                exc_mean=float(excs.mean()) if len(excs) else float('nan'),
                n=ntr, k=len(pm), res=nres / ntr if ntr else 0.0)


def refmeans(base, net):
    """per-mint mean net return over all eligible signal cycles = random-entry control"""
    M = base.shape[0]
    ref = np.full(M, np.nan)
    for i in range(M):
        js = np.flatnonzero(base[i])
        if len(js):
            ref[i] = net[i, js].mean()
    return ref
