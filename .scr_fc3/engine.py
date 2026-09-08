"""Exhaustive grid: creator-identity entry x mint metadata x position x exit.
Harness contract A-G enforced. Only md5(mint)%3 in (1,2) is ever read.
"""
import pickle, hashlib, json, sys, time, collections
from bisect import bisect_left
import numpy as np

CACHE = '/home/anont/meme/.scr_fc3/cache.pkl'
TOLL = 0.0114
CHARGE = 0.50
MIN_CLUSTERS = 15
MIN_TRADES = 40
# --- realism floor, applied identically to every rule AND every control ---
import os as _os
MIN_MCAP = float(_os.environ.get('MIN_MCAP', 2000.0))  # USD mcap at signal bar
MIN_VOL5 = 200.0      # USD traded over the trailing 5 bars
MAXWAIT_MIN = 30      # if no real bar within target+MAXWAIT, the position cannot be exited
RET_CAP = 3.0         # per-trade upside ceiling (you cannot exit a 20x into no book)
import os
STOP_FILL = os.environ.get('STOP_FILL', 'low')   # 'low' = worst-case fill on the trigger bar


def hh(m):
    return int(hashlib.md5(m.encode()).hexdigest(), 16) % 3


_d = pickle.load(open(CACHE, 'rb'))
BARS, FEATS = _d['bars'], _d['feats']
MINTS = sorted(BARS)
HORIZON = max(BARS[m][-1, 0] for m in MINTS)
TRAIN = [m for m in MINTS if hh(m) == 1]
VALID = [m for m in MINTS if hh(m) == 2]

GATES = ['all', 'age_lt60', 'age_60_360', 'age_360_900', 'age_ge900',
         'mc_2k_5k', 'mc_5k_50k', 'mc_50k_250k', 'mc_ge250k',
         'ath_lt20', 'ath_20_60', 'ath_ge60', 'ath_ge90']

GATE_SIG = {}
for m in MINTS:
    a = BARS[m]
    n = len(a)
    ts, cl = a[:, 0], a[:, 4]
    age = (ts - FEATS[m]['t_create']) / 60.0
    mcap = cl * 1e9
    athr = cl / np.maximum.accumulate(cl)
    vol = a[:, 5]
    v5 = np.convolve(vol, np.ones(5))[:n]
    legal = (mcap >= MIN_MCAP) & (v5 >= MIN_VOL5)
    sig = np.arange(n - 1)
    sig = sig[legal[sig]]
    g = {'all': sig,
         'age_lt60': sig[age[sig] < 60],
         'age_60_360': sig[(age[sig] >= 60) & (age[sig] < 360)],
         'age_360_900': sig[(age[sig] >= 360) & (age[sig] < 900)],
         'age_ge900': sig[age[sig] >= 900],
         'mc_2k_5k': sig[mcap[sig] < 5e3],
         'mc_5k_50k': sig[(mcap[sig] >= 5e3) & (mcap[sig] < 5e4)],
         'mc_50k_250k': sig[(mcap[sig] >= 5e4) & (mcap[sig] < 2.5e5)],
         'mc_ge250k': sig[mcap[sig] >= 2.5e5],
         'ath_lt20': sig[athr[sig] < 0.20],
         'ath_20_60': sig[(athr[sig] >= 0.20) & (athr[sig] < 0.60)],
         'ath_ge60': sig[athr[sig] >= 0.60],
         'ath_ge90': sig[athr[sig] >= 0.90]}
    GATE_SIG[m] = g


def build_cfs():
    cf = collections.OrderedDict()
    cf['all'] = lambda f: True
    cf['np0'] = lambda f: f['n_prior'] == 0
    cf['np1p'] = lambda f: f['n_prior'] >= 1
    cf['np2p'] = lambda f: f['n_prior'] >= 2
    cf['np3p'] = lambda f: f['n_prior'] >= 3
    cf['np5p'] = lambda f: f['n_prior'] >= 5
    cf['np10p'] = lambda f: f['n_prior'] >= 10
    cf['np20p'] = lambda f: f['n_prior'] >= 20
    cf['np1_4'] = lambda f: 1 <= f['n_prior'] <= 4
    cf['np5_19'] = lambda f: 5 <= f['n_prior'] <= 19
    cf['np0_l2h'] = lambda f: f['np_2h'] == 0
    cf['np1p_l2h'] = lambda f: f['np_2h'] >= 1
    cf['np3p_l2h'] = lambda f: f['np_2h'] >= 3
    cf['np10p_l2h'] = lambda f: f['np_2h'] >= 10
    cf['np1p_l6h'] = lambda f: f['np_6h'] >= 1
    cf['np5p_l6h'] = lambda f: f['np_6h'] >= 5
    cf['ng0'] = lambda f: f['ng_2h'] == 0
    cf['ng1p'] = lambda f: f['ng_2h'] >= 1
    cf['ng2p'] = lambda f: f['ng_2h'] >= 2
    cf['ng3p'] = lambda f: f['ng_2h'] >= 3
    cf['fg_zero'] = lambda f: f['np_2h'] >= 2 and f['frac_grad'] == 0
    cf['fg_lo'] = lambda f: f['np_2h'] >= 2 and 0 < f['frac_grad'] < 0.10
    cf['fg_hi'] = lambda f: f['np_2h'] >= 2 and f['frac_grad'] >= 0.10
    cf['fg_vhi'] = lambda f: f['np_2h'] >= 2 and f['frac_grad'] >= 0.25
    cf['rec_lt30'] = lambda f: f['recency_min'] < 30
    cf['rec_lt120'] = lambda f: f['recency_min'] < 120
    cf['rec_30_720'] = lambda f: 30 <= f['recency_min'] < 720
    cf['rec_ge120'] = lambda f: 120 <= f['recency_min'] < 1e8
    cf['b60_0'] = lambda f: f['burst_60'] == 0
    cf['b60_1p'] = lambda f: f['burst_60'] >= 1
    cf['b60_3p'] = lambda f: f['burst_60'] >= 3
    cf['b60_10p'] = lambda f: f['burst_60'] >= 10
    cf['b15_1p'] = lambda f: f['burst_15'] >= 1
    cf['b360_5p'] = lambda f: f['burst_360'] >= 5
    cf['pout_pos'] = lambda f: f['n_prior_out'] >= 1 and f['prior_out_med'] > 0
    cf['pout_neg'] = lambda f: f['n_prior_out'] >= 1 and -90 < f['prior_out_med'] <= 0
    cf['db_pos'] = lambda f: f['devbuy'] > 0
    cf['db_zero'] = lambda f: f['devbuy'] == 0
    cf['db_big'] = lambda f: f['devbuy'] >= 1.0
    cf['pdb_pos'] = lambda f: f['n_prior_db'] >= 1 and f['prior_db_med'] > 0
    cf['dlen151'] = lambda f: f['dlen'] == 151
    cf['dlen115'] = lambda f: f['dlen'] == 115
    cf['conch_mm'] = lambda f: f['conchain_match'] == 0
    return cf


CFS = build_cfs()
CF_TRAIN = {k: [m for m in TRAIN if fn(FEATS[m])] for k, fn in CFS.items()}
CF_VALID = {k: [m for m in VALID if fn(FEATS[m])] for k, fn in CFS.items()}

HOLDS = [5, 15, 30, 60, 120, 240]
VARIANTS = ['time', 'tp25', 'tp50', 'tp100', 'sl30', 'sl50',
            'tp50_sl30', 'tp100_sl40', 'tp25_sl15', 'half_tp50', 'trail30', 'trail50']
POSITIONS = ['flat', 'add_dn25', 'add_up25']
VAR_PARAM = {
    'time':       (None, None, None, None),
    'tp25':       (0.25, None, None, None),
    'tp50':       (0.50, None, None, None),
    'tp100':      (1.00, None, None, None),
    'sl30':       (None, 0.30, None, None),
    'sl50':       (None, 0.50, None, None),
    'tp50_sl30':  (0.50, 0.30, None, None),
    'tp100_sl40': (1.00, 0.40, None, None),
    'tp25_sl15':  (0.25, 0.15, None, None),
    'half_tp50':  (None, None, None, 0.50),
    'trail30':    (None, None, 0.30, None),
    'trail50':    (None, None, 0.50, None),
}


def build_hold(H):
    """returns STR[(v,p)][mint] = (sig, bankA, bankW, openR, openW, epx, drop, exitbar)
       and CAND[(mint,gate)] = (positions list, sigvals list)"""
    STR = {(v, p): {} for v in VARIANTS for p in POSITIONS}
    CAND = {}
    for m in MINTS:
        a = BARS[m]
        n = len(a)
        ts, op, hi, lo = a[:, 0], a[:, 1], a[:, 2], a[:, 3]
        sig = np.arange(n - 1)
        j = sig + 1
        tgt = ts[j] + H * 60.0
        ok = tgt <= HORIZON
        if not ok.any():
            continue
        sig = sig[ok]; j = j[ok]; tgt = tgt[ok]
        e = op[j]
        k = np.searchsorted(ts, tgt, 'left')
        too_late = ts[np.minimum(k, n - 1)] > tgt + MAXWAIT_MIN * 60.0
        drop = (k >= n) | too_late
        kk = np.minimum(k, n)
        W = int(max(1, (kk - j).max()))
        cols = np.arange(W)
        raw = j[:, None] + cols[None, :]
        idxm = np.minimum(raw, n - 1)
        mask = raw < kk[:, None]
        hm = np.where(mask, hi[idxm], -np.inf)
        lm = np.where(mask, lo[idxm], np.inf)
        rmax = np.maximum.accumulate(hm, axis=1)
        rmin = np.minimum.accumulate(lm, axis=1)
        lastcol = np.clip((kk - j) - 1, 0, W - 1)
        rows = np.arange(len(j))
        timepx = np.where(drop, np.nan, op[np.minimum(k, n - 1)])
        BIG = W + 10
        # candidate positions per gate (depends only on sig)
        for g in GATES:
            gi = GATE_SIG[m][g]
            if len(gi) == 0:
                CAND[(m, g)] = ([], [])
                continue
            pp = np.searchsorted(sig, gi)
            good = pp < len(sig)
            pp = pp[good]
            if len(pp) == 0:
                CAND[(m, g)] = ([], [])
                continue
            good2 = sig[pp] == gi[good]
            pp = pp[good2]
            CAND[(m, g)] = (pp.tolist(), sig[pp].tolist())

        for v in VARIANTS:
            tp, sl, tr, htp = VAR_PARAM[v]
            ecol = np.full(len(j), BIG, dtype=np.int64)
            epx = timepx.copy()
            if tp is not None:
                lvl = e * (1 + tp)
                c = (rmax < lvl[:, None]).sum(axis=1)
                b = (c < W) & (c < ecol)
                ecol = np.where(b, c, ecol); epx = np.where(b, lvl, epx)
            if sl is not None:
                lvl = e * (1 - sl)
                c = (rmin > lvl[:, None]).sum(axis=1)
                b = (c < W) & (c <= ecol)
                px = lvl if STOP_FILL == 'trigger' else np.minimum(lvl, lm[rows, np.clip(c, 0, W - 1)])
                ecol = np.where(b, c, ecol); epx = np.where(b, px, epx)
            if tr is not None:
                trig = rmax * (1 - tr)
                hitm = mask & (lm <= trig)
                any_hit = hitm.any(axis=1)
                c = np.where(any_hit, hitm.argmax(axis=1), BIG)
                b = any_hit & (c <= ecol)
                cc = np.clip(c, 0, W - 1)
                px = trig[rows, cc] if STOP_FILL == 'trigger' else np.minimum(trig[rows, cc], lm[rows, cc])
                ecol = np.where(b, c, ecol); epx = np.where(b, px, epx)
            dropv = drop & (ecol >= BIG)
            exitbar = np.where(ecol < BIG, j + ecol, np.where(drop, n, k))
            fillcol = np.clip(np.where(ecol < BIG, ecol, lastcol), 0, W - 1)
            for p in POSITIONS:
                if p == 'flat':
                    w1, fill, fp = 1.0, None, None
                else:
                    w1 = 0.5
                    if p == 'add_dn25':
                        fp = e * 0.75
                        fill = rmin[rows, fillcol] <= fp
                    else:
                        fp = e * 1.25
                        fill = rmax[rows, fillcol] >= fp
                bankA = np.zeros(len(j)); bankW = np.zeros(len(j))
                openR = np.zeros(len(j)); openW = np.zeros(len(j))
                legs = [(np.full(len(j), w1), e, np.ones(len(j), dtype=bool))]
                if p != 'flat':
                    legs.append((np.full(len(j), 0.5), fp, fill))
                for (wv, fv, fl) in legs:
                    w = wv * fl
                    if htp is not None:
                        lvl = fv * (1 + htp)
                        c = (rmax < lvl[:, None]).sum(axis=1)
                        hitb = (c < W) & (c <= fillcol) & fl
                        bankA += np.where(hitb, 0.5 * w * (1 + htp), 0.0)
                        bankW += np.where(hitb, 0.5 * w, 0.0)
                        wo = np.where(hitb, 0.5 * w, w)
                    else:
                        wo = w
                    openR += wo / fv
                    openW += wo
                STR[(v, p)][m] = (sig.tolist(), bankA, bankW, openR, openW,
                                  epx, dropv, exitbar.tolist())
    return STR, CAND


def evaluate(struct, cand, mints, gate, toll=TOLL, charge=CHARGE, want_per=False):
    per = []
    ntr = 0
    ndrop = 0
    for m in mints:
        s = struct.get(m)
        if s is None:
            continue
        sig, bankA, bankW, openR, openW, epx, dropv, exitbar = s
        cp, cv = cand.get((m, gate), ([], []))
        if not cp:
            continue
        rets = []
        p = 0
        L = len(cp)
        while p < L:
            i = cp[p]
            if dropv[i]:
                r = bankA[i] * (1 - toll) - bankW[i] - openW[i] * charge
                ndrop += 1
            else:
                r = (bankA[i] + openR[i] * epx[i]) * (1 - toll) - (bankW[i] + openW[i])
                if r > RET_CAP:
                    r = RET_CAP
            rets.append(r)
            nxt = bisect_left(cv, exitbar[i], p)
            if nxt <= p:
                nxt = p + 1
            p = nxt
        if rets:
            ntr += len(rets)
            per.append(sum(rets) / len(rets))
    if not per:
        return None
    arr = np.array(per)
    res = 1.0 - ndrop / ntr if ntr else 0.0
    out = dict(mean=float(arr.mean()), med=float(np.median(arr)), n=ntr,
               cl=len(arr), res=res)
    if want_per:
        out['per'] = arr
    return out


def boot_lo(per, iters=4000, seed=0, q=5.0):
    rng = np.random.default_rng(seed)
    n = len(per)
    idx = rng.integers(0, n, size=(iters, n))
    return float(np.percentile(per[idx].mean(axis=1), q))


if __name__ == '__main__':
    t0 = time.time()
    hits = []
    allrows = []
    base = {}
    combos = 0
    for H in HOLDS:
        STR, CAND = build_hold(H)
        for v in VARIANTS:
            for p in POSITIONS:
                st = STR[(v, p)]
                for g in GATES:
                    b = evaluate(st, CAND, CF_TRAIN['all'], g)
                    bv = evaluate(st, CAND, CF_VALID['all'], g)
                    base[(H, v, p, g)] = (b, bv)
                    for cfn in CFS:
                        combos += 1
                        r = evaluate(st, CAND, CF_TRAIN[cfn], g)
                        if not r or r['cl'] < MIN_CLUSTERS or r['n'] < MIN_TRADES:
                            continue
                        row = dict(H=H, v=v, p=p, g=g, cf=cfn, **r)
                        allrows.append(row)
                        if r['mean'] > 0:
                            hits.append(row)
        print('H=%d combos=%d eligible=%d hits=%d t=%.1f'
              % (H, combos, len(allrows), len(hits), time.time() - t0), flush=True)
    print('TOTAL COMBOS', combos, 'ELIGIBLE', len(allrows), 'TRAIN POSITIVE', len(hits))
    pickle.dump(dict(hits=hits, combos=combos, allrows=allrows, base=base),
                open('/home/anont/meme/.scr_fc3/train_hits.pkl', 'wb'))
    hits.sort(key=lambda r: -r['mean'])
    for r in hits[:40]:
        print('  %+.4f med%+.4f n=%4d k=%3d res=%.3f H=%3d %-10s %-9s %-12s %s'
              % (r['mean'], r['med'], r['n'], r['cl'], r['res'], r['H'], r['v'], r['p'], r['g'], r['cf']))
    print('elapsed', time.time() - t0)
