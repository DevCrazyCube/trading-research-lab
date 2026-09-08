#!/usr/bin/env python3
"""
INVENT_0824_perpoi: build a DAILY feature panel from the Binance USD-M
futures METRICS feed (5-minute open interest + positioning ratios) plus
daily klines.

Key data point that makes this round different from SWEEP round 1/2 and
INVENT_R3: those all worked on a 1-HOUR panel.  The metrics feed is
5-MINUTE, and it carries sum_open_interest (contracts) AND
sum_open_interest_value (USD), so
        price_5m = sum_open_interest_value / sum_open_interest
is a free 5-minute mark that is *exactly synchronous* with the OI print.
Every intraday OI/price co-movement statistic below is computed on that
synchronous pair, at 5m, which no previous round could see.

Output: research/data/oi0824_cache/sym/<SYM>.npz  (one row per UTC day)
"""
import os, sys, zipfile, io, csv
import numpy as np
from multiprocessing import Pool

BASE = '/home/anont/meme/research/data/orphanflush_cache'
OUT = '/home/anont/meme/research/data/oi0824_cache'
os.makedirs(OUT + '/sym', exist_ok=True)

FIELDS = [
    'day',        # 0 days since epoch
    'nb',         # 1 number of 5m bars
    'oiv_last',   # 2 last sum_open_interest_value of the day
    'oiv_mean',   # 3
    'oi_last',    # 4 contracts
    'oi_max',     # 5
    'oi_min',     # 6
    'churn',      # 7 sum |dlogOI|
    'net',        # 8 sum dlogOI  (== log(oi_last/oi_first))
    'maxdrop',    # 9 most negative single-bar dlogOI
    'maxbuild',   # 10 most positive single-bar dlogOI
    'liq_long',   # 11 -sum(dlogOI | dlogOI<0 & dlogP<0)  long-liquidation proxy
    'liq_short',  # 12 -sum(dlogOI | dlogOI<0 & dlogP>0)  short-squeeze proxy
    'add_up',     # 13  sum(dlogOI | dlogOI>0 & dlogP>0)  new longs
    'add_dn',     # 14  sum(dlogOI | dlogOI>0 & dlogP<0)  new shorts
    'cov_po',     # 15 sum dlogP*dlogOI
    'var_o',      # 16 sum dlogOI^2
    'var_p',      # 17 sum dlogP^2
    'oi_asia',    # 18 dlogOI over 00-08 UTC
    'oi_eu',      # 19 dlogOI over 08-16 UTC
    'oi_us',      # 20 dlogOI over 16-24 UTC
    'glsr',       # 21 count_long_short_ratio, last
    'glsr_m',     # 22 mean
    'tt_c',       # 23 count_toptrader_long_short_ratio, last
    'tt_s',       # 24 sum_toptrader_long_short_ratio, last
    'taker',      # 25 mean sum_taker_long_short_vol_ratio
    'oiwap',      # 26 OI-BUILD weighted avg price: sum(dOI+ * P)/sum(dOI+)
    'p_last',     # 27 metrics-implied last price
]
NF = len(FIELDS)


def do_symbol(sym):
    d = os.path.join(BASE, 'raw/metrics', sym)
    try:
        files = sorted(f for f in os.listdir(d) if f.endswith('.zip'))
    except OSError:
        return sym, 0
    rows = []
    for fn in files:
        try:
            z = zipfile.ZipFile(os.path.join(d, fn))
            nm = z.namelist()[0]
            raw = z.read(nm).decode('utf-8', 'ignore')
        except Exception:
            continue
        lines = raw.splitlines()
        if len(lines) < 30:
            continue
        ts = []
        oi = []
        oiv = []
        gl = []
        ttc = []
        tts = []
        tk = []
        for ln in lines[1:]:
            p = ln.split(',')
            if len(p) < 8:
                continue
            try:
                hh = int(p[0][11:13]); mm = int(p[0][14:16])
                a = float(p[2]); b = float(p[3])
                if a <= 0 or b <= 0:
                    continue
                def f(x):
                    try:
                        return float(x)
                    except Exception:
                        return np.nan
                ts.append(hh * 60 + mm)
                oi.append(a); oiv.append(b)
                ttc.append(f(p[4])); tts.append(f(p[5]))
                gl.append(f(p[6])); tk.append(f(p[7]))
            except ValueError:
                continue
        n = len(ts)
        if n < 100:
            continue
        ts = np.asarray(ts, np.int32)
        oi = np.asarray(oi, np.float64)
        oiv = np.asarray(oiv, np.float64)
        P = oiv / oi
        lo = np.log(oi); lp = np.log(P)
        dO = np.diff(lo); dP = np.diff(lp)
        # guard against contract-size redenominations / bad prints
        ok = (np.abs(dO) < 0.5) & (np.abs(dP) < 0.5)
        dO = dO[ok]; dP = dP[ok]
        if dO.size < 50:
            continue
        neg = dO < 0; pos = dO > 0
        up = dP > 0; dn = dP < 0
        # session OI change (nearest bar to boundary)
        def at(minute):
            i = int(np.argmin(np.abs(ts - minute)))
            return lo[i] if abs(ts[i] - minute) <= 20 else np.nan
        a0, a8, a16, a24 = at(0), at(480), at(960), at(1435)
        # OI-build weighted price
        w = np.where(pos, dO, 0.0)
        Pm = P[1:][ok]
        sw = w.sum()
        oiwap = float((w * Pm).sum() / sw) if sw > 1e-12 else np.nan
        day = int(np.datetime64(fn.split('metrics-')[1][:10]).astype('datetime64[D]').astype(int))
        r = np.full(NF, np.nan)
        r[0] = day
        r[1] = dO.size
        r[2] = oiv[-1]; r[3] = oiv.mean()
        r[4] = oi[-1]; r[5] = oi.max(); r[6] = oi.min()
        r[7] = np.abs(dO).sum(); r[8] = dO.sum()
        r[9] = dO.min(); r[10] = dO.max()
        r[11] = -dO[neg & dn].sum(); r[12] = -dO[neg & up].sum()
        r[13] = dO[pos & up].sum(); r[14] = dO[pos & dn].sum()
        r[15] = float((dP * dO).sum()); r[16] = float((dO * dO).sum()); r[17] = float((dP * dP).sum())
        r[18] = a8 - a0; r[19] = a16 - a8; r[20] = a24 - a16
        def lastfin(v):
            v = np.asarray(v, np.float64)
            if v.size == 0:
                return np.nan, np.nan
            fin = v[np.isfinite(v)]
            if fin.size == 0:
                return np.nan, np.nan
            return fin[-1], fin.mean()
        r[21], r[22] = lastfin(gl)
        r[23], _ = lastfin(ttc)
        r[24], _ = lastfin(tts)
        _, r[25] = lastfin(tk)
        r[26] = oiwap
        r[27] = P[-1]
        rows.append(r)
    if not rows:
        return sym, 0
    A = np.asarray(rows, np.float64)
    A = A[np.argsort(A[:, 0])]
    np.savez_compressed(os.path.join(OUT, 'sym', sym + '.npz'), a=A.astype(np.float32),
                        fields=np.array(FIELDS))
    return sym, A.shape[0]


if __name__ == '__main__':
    syms = sorted(os.listdir(os.path.join(BASE, 'raw/metrics')))
    todo = [s for s in syms if not os.path.exists(os.path.join(OUT, 'sym', s + '.npz'))]
    print('symbols', len(syms), 'todo', len(todo), flush=True)
    with Pool(10) as p:
        for i, (s, n) in enumerate(p.imap_unordered(do_symbol, todo, chunksize=2)):
            if i % 20 == 0:
                print(i, s, n, flush=True)
    print('DONE', flush=True)
