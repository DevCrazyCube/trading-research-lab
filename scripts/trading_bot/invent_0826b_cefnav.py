#!/usr/bin/env python3
"""INVENT_2026-08-26B: CEF NAV-innovation underreaction. Stages: design | reveal.
Research only. Reads pre-existing t12_cache only. Writes to research/trading_bot/."""
import gzip, json, sys, hashlib, os
import numpy as np
ROOT = '/home/anont/meme'
CACHE = f'{ROOT}/data' if False else f'{ROOT}/research/data/t12_cache'
OUT = f'{ROOT}/research/trading_bot'
TAG = 'INVENT_2026-08-26B_cefnav'
HS = {'median': 11.525163273146124, 'p75': 18.382352941176897, 'p90': 27.247956403269615}
BORROW_BP_YR = 200.0; SEC_BP = 0.278
N_PLACEBO = 300; SEED = 20260826
rng = np.random.default_rng(SEED)

def load(f): return json.load(gzip.open(f'{CACHE}/{f}.json.gz'))

def build_daily():
    h1 = load('history_1Y'); ab = load('adjusted_bars'); assets = load('alpaca_assets')
    syms = sorted(set(h1) & set(ab))
    dates = sorted({d for s in syms for d in ab[s] if d >= '2025-08-18'})
    T, N = len(dates), len(syms); di = {d: i for i, d in enumerate(dates)}
    P = np.full((T, N), np.nan); V = np.full((T, N), np.nan); A = np.full((T, N), np.nan)
    for j, s in enumerate(syms):
        for d, a in ab[s].items():
            if d in di: A[di[d], j] = a
        for r in h1[s]:
            if r['date'] in di and r['price'] and r['nav']:
                P[di[r['date']], j] = r['price']; V[di[r['date']], j] = r['nav']
    etb = np.array([bool(assets.get(s, {}).get('easy_to_borrow', False)) for s in syms])
    return dates, syms, P, V, A, etb

def build_weekly():
    h5 = load('history_5Y'); ab = load('adjusted_bars'); assets = load('alpaca_assets')
    syms = sorted(set(h5) & set(ab))
    abdates = sorted({d for s in syms for d in ab[s]})
    fr = sorted({r['date'] for s in syms for r in h5[s]}); fr = [f for f in fr if f <= abdates[-1]]
    # for each Friday grid date, its adjusted-bar index (last ab date <= friday)
    import bisect
    fidx = [bisect.bisect_right(abdates, f) - 1 for f in fr]
    T, N = len(fr), len(syms); di = {d: i for i, d in enumerate(fr)}
    P = np.full((T, N), np.nan); V = np.full((T, N), np.nan)
    Aall = np.full((len(abdates), N), np.nan); adi = {d: i for i, d in enumerate(abdates)}
    for j, s in enumerate(syms):
        for d, a in ab[s].items(): Aall[adi[d], j] = a
        for r in h5[s]:
            if r['date'] in di and r['price'] and r['nav']:
                P[di[r['date']], j] = r['price']; V[di[r['date']], j] = r['nav']
    etb = np.array([bool(assets.get(s, {}).get('easy_to_borrow', False)) for s in syms])
    return fr, np.array(fidx), abdates, syms, P, V, Aall, etb

def lrets(X):
    R = np.full_like(X, np.nan); R[1:] = np.log(X[1:] / X[:-1]); return R

def series(P, V, A):
    r_p = lrets(A); r_raw = lrets(P); y = r_p - r_raw
    r_nav = lrets(V) + y
    return r_p, r_raw, y, r_nav

def ksum(R, k):
    S = np.full_like(R, np.nan)
    for t in range(k, R.shape[0]):
        blk = R[t - k + 1:t + 1]
        S[t] = np.where(np.isnan(blk).any(0), np.nan, np.nansum(blk, 0))
    return S

def tercile_weights(sig, elig, etb):
    """sig: (T,N). Long top tercile, short bottom tercile among elig; short only etb. Returns W (T,N), formed at t."""
    T, N = sig.shape; W = np.zeros((T, N))
    for t in range(T):
        m = elig[t] & ~np.isnan(sig[t]); idx = np.where(m)[0]
        if len(idx) < 30: continue
        order = idx[np.argsort(sig[t, idx], kind='stable')]; q = len(idx) // 3
        lo = order[:q]; hi = order[-q:]
        lo = lo[etb[lo]]
        if len(lo) == 0 or len(hi) == 0: continue
        W[t, hi] = 1.0 / len(hi); W[t, lo] = -1.0 / len(lo)
    return W

def run_book(W, r_p, lag, h, cost_bp):
    """Effective weight on session s = mean of W formed at s-lag-h..s-lag-1. P&L on s uses r_p[s]."""
    T, N = W.shape; Weff = np.zeros((T, N))
    for s in range(T):
        lo, hi = s - lag - h, s - lag - 1
        if lo < 0: continue
        Weff[s] = W[lo:hi + 1].mean(0)
    rp = np.nan_to_num(r_p, nan=0.0)
    gross = (Weff * rp).sum(1)
    dW = np.abs(np.diff(Weff, axis=0, prepend=np.zeros((1, N)))).sum(1)
    sells = np.clip(-np.diff(Weff, axis=0, prepend=np.zeros((1, N))), 0, None).sum(1)
    short_not = np.clip(-Weff, 0, None).sum(1)
    active = (np.abs(Weff).sum(1) > 0)
    return dict(gross=gross, turnover=dW, sells=sells, short_not=short_not, active=active, Weff=Weff)

def stats(bk, sl, per_yr=252, hs_bp=HS['median']):
    g = bk['gross'][sl]; a = bk['active'][sl]; g = g[a]
    if len(g) < 10 or g.std() == 0: return None
    to = bk['turnover'][sl][a]; se = bk['sells'][sl][a]; sn = bk['short_not'][sl][a]
    def net_for(hs):
        return g - to * hs * 1e-4 - se * SEC_BP * 1e-4 - sn * BORROW_BP_YR * 1e-4 / per_yr
    n = len(g); out = dict(n=n, gross_bp=1e4 * g.mean(), gross_t=g.mean() / g.std() * np.sqrt(n),
                           gross_sharpe=g.mean() / g.std() * np.sqrt(per_yr),
                           turnover=to.mean(), rho1=float(np.corrcoef(g[:-1], g[1:])[0, 1]))
    for k, hs in HS.items():
        nt = net_for(hs); out[f'net_bp_{k}'] = 1e4 * nt.mean(); out[f'net_t_{k}'] = nt.mean() / nt.std() * np.sqrt(n)
    return out

def placebo_t(sig, elig, etb, r_p, lag, h, sl, per_yr, n_draw):
    ts = []
    for _ in range(n_draw):
        ps = sig.copy()
        for t in range(sig.shape[0]):
            m = np.where(elig[t] & ~np.isnan(sig[t]))[0]
            if len(m): ps[t, m] = sig[t, rng.permutation(m)]
        W = tercile_weights(ps, elig, etb); bk = run_book(W, r_p, lag, h, 0)
        st = stats(bk, sl, per_yr); ts.append(st['gross_t'] if st else 0.0)
    return np.array(ts)

def concentration(bk, sl, syms):
    We = bk['Weff'][sl]; c = (We * 0).sum(0)
    return None

def formulas_daily():
    return [(f'D_{kind}_k{k}', kind, k) for kind in ('NAV', 'PRC', 'TOT') for k in (1, 5, 10)]

def daily_signals(kind, k, r_raw, r_nav):
    if kind == 'NAV': return ksum(r_nav, k)
    if kind == 'PRC': return -ksum(r_raw, k)
    return -(ksum(r_raw, k) - ksum(r_nav, k))

def main(stage):
    res = {'stage': stage, 'prereg_sha256': hashlib.sha256(open(f'{OUT}/{TAG}_PREREG.md', 'rb').read()).hexdigest(), 'daily': {}, 'weekly': {}}
    # ---------------- daily panel ----------------
    dates, syms, P, V, A, etb = build_daily()
    r_p, r_raw, y, r_nav = series(P, V, A)
    navchg = np.nanmean(np.diff(V, axis=0) != 0, axis=0)
    fresh = navchg >= 0.7
    elig = (P > 5) & ~np.isnan(V) & ~np.isnan(A) & fresh[None, :]
    T = len(dates); split = int(0.6 * T)
    res['daily']['panel'] = dict(sessions=T, funds=len(syms), fresh_funds=int(fresh.sum()), design=[dates[0], dates[split - 1]], heldout=[dates[split], dates[-1]],
                                 rho1_pooled_dprem=float(np.nanmean([np.corrcoef(x[:-1], x[1:])[0, 1] for x in np.nan_to_num((r_raw - r_nav)[1:, fresh]).T if x.std() > 0])),
                                 rho1_pooled_rraw=float(np.nanmean([np.corrcoef(x[:-1], x[1:])[0, 1] for x in np.nan_to_num(r_raw[1:, fresh]).T if x.std() > 0])),
                                 rho1_pooled_rnav=float(np.nanmean([np.corrcoef(x[:-1], x[1:])[0, 1] for x in np.nan_to_num(r_nav[1:, fresh]).T if x.std() > 0])))
    shortlist = json.load(open(f'{OUT}/{TAG}_SHORTLIST.json'))['shortlist'] if stage == 'reveal' else None
    des = slice(0, split); ho = slice(split, T)
    for fid, kind, k in formulas_daily():
        sig = daily_signals(kind, k, r_raw, r_nav)
        W = tercile_weights(sig, elig, etb)
        row = {}
        for lag in (1, 0):
            bk = run_book(W, r_p, lag, 5, 0)
            row[f'design_lag{lag}'] = stats(bk, des, 252)
            if stage == 'reveal' and fid in shortlist:
                st = stats(bk, ho, 252)
                # per-half signs and concentration
                g = bk['gross'][ho]; hh = len(g) // 2
                st['half_signs'] = [float(np.sign(g[:hh].mean())), float(np.sign(g[hh:].mean()))]
                contrib = (bk['Weff'][ho] * np.nan_to_num(r_p[ho])).sum(0)
                tot = contrib.sum(); st['top5_share'] = float(np.sort(contrib)[-5:].sum() / tot) if tot != 0 else None
                row[f'heldout_lag{lag}'] = st
            else:
                row[f'heldout_lag{lag}'] = 'SEALED'
        if stage == 'design':
            pt = placebo_t(sig, elig, etb, r_p, 1, 5, des, 252, N_PLACEBO)
            row['placebo_design'] = dict(p95=float(np.percentile(pt, 95)), pct_of_real=float((pt < row['design_lag1']['gross_t']).mean() * 100), sd=float(pt.std()))
        res['daily'][fid] = row
        print(fid, json.dumps({k2: (round(v, 3) if isinstance(v, float) else v) for k2, v in (row['design_lag1'] or {}).items()}), 'lag0 t', round(row['design_lag0']['gross_t'], 2), row.get('placebo_design', ''), flush=True)
    # ---------------- weekly panel ----------------
    fr, fidx, abdates, wsyms, WP, WV, Aall, wetb = build_weekly()
    r_pA = lrets(Aall)
    Tw = len(fr); split_w = int(0.6 * Tw)
    # weekly raw / nav returns on the Friday grid; adjusted weekly return between the ab indices
    Af = Aall[fidx]
    w_raw = lrets(WP); w_adj = lrets(Af); w_y = w_adj - w_raw; w_nav = lrets(WV) + w_y
    welig = (WP > 5) & ~np.isnan(WV) & ~np.isnan(Af)
    res['weekly']['panel'] = dict(weeks=Tw, funds=len(wsyms), design=[fr[0], fr[split_w - 1]], heldout=[fr[split_w], fr[-1]])
    def weekly_book(sig, lag):
        W = tercile_weights(sig, welig, wetb)
        # entry at ab index fidx[t]+lag, exit at fidx[t+1]+lag
        g = np.full(Tw, np.nan); to = np.zeros(Tw); se = np.zeros(Tw); sn = np.zeros(Tw); act = np.zeros(Tw, bool); Wprev = np.zeros(W.shape[1])
        for t in range(Tw - 1):
            i0, i1 = fidx[t] + lag, fidx[t + 1] + lag
            if i1 >= Aall.shape[0] or np.abs(W[t]).sum() == 0: continue
            ret = np.log(Aall[i1] / Aall[i0]); ret = np.nan_to_num(ret)
            g[t] = (W[t] * ret).sum(); to[t] = np.abs(W[t] - Wprev).sum(); se[t] = np.clip(Wprev - W[t], 0, None).sum(); sn[t] = np.clip(-W[t], 0, None).sum() * 5
            act[t] = True; Wprev = W[t]
        return dict(gross=np.nan_to_num(g), turnover=to, sells=se, short_not=sn, active=act, Weff=W)
    wdes = slice(0, split_w); who = slice(split_w, Tw)
    wform = [('W_NAV_1w', w_nav), ('W_PRC_1w', -w_raw), ('W_TOT_1w', -(w_raw - w_nav))]
    for fid, sig in wform:
        row = {}
        for lag in (1, 0):
            bk = weekly_book(sig, lag)
            row[f'design_lag{lag}'] = stats(bk, wdes, 52)
            if stage == 'reveal' and fid in shortlist:
                st = stats(bk, who, 52); g = bk['gross'][who]; yrs = np.array([f[:4] for f in fr[who]])
                st['year_signs'] = {yv: float(np.sign(g[yrs == yv].mean())) for yv in sorted(set(yrs))}
                st['year_bp'] = {yv: float(1e4 * g[yrs == yv].mean()) for yv in sorted(set(yrs))}
                lvl = weekly_book(-(WP / WV), lag)['gross']   # T12-style level tilt: long deepest discount tercile
                st['corr_to_level_tilt_heldout'] = float(np.corrcoef(g, lvl[who])[0, 1])
                st['corr_to_level_tilt_design'] = float(np.corrcoef(bk['gross'][wdes], lvl[wdes])[0, 1])
                contrib = np.zeros(W_.shape[1]) if False else None
                row[f'heldout_lag{lag}'] = st
            else:
                row[f'heldout_lag{lag}'] = 'SEALED'
        if stage == 'design':
            ts = []
            for _ in range(N_PLACEBO):
                ps = sig.copy()
                for t in range(Tw):
                    m = np.where(welig[t] & ~np.isnan(sig[t]))[0]
                    if len(m): ps[t, m] = sig[t, rng.permutation(m)]
                st = stats(weekly_book(ps, 1), wdes, 52); ts.append(st['gross_t'] if st else 0.0)
            ts = np.array(ts); row['placebo_design'] = dict(p95=float(np.percentile(ts, 95)), pct_of_real=float((ts < row['design_lag1']['gross_t']).mean() * 100), sd=float(ts.std()))
        res['weekly'][fid] = row
        print(fid, json.dumps({k2: (round(v, 3) if isinstance(v, float) else v) for k2, v in (row['design_lag1'] or {}).items()}), 'lag0 t', round(row['design_lag0']['gross_t'], 2), row.get('placebo_design', ''), flush=True)
    fn = f'{OUT}/{TAG}_{"DESIGN" if stage == "design" else "REVEAL"}.json'
    json.dump(res, open(fn, 'w'), indent=1, default=lambda o: float(o) if isinstance(o, (np.floating, np.integer)) else str(o))
    print('wrote', fn)

if __name__ == '__main__':
    main(sys.argv[1])
