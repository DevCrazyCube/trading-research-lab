#!/usr/bin/env python3
"""POSTURE A - OWN THE BASKET.  New file; touches nothing in arena/.
Measures the honest EW-liquid-basket baseline on the survivorship-complete Binance USD-M panel.
Pre-registration: scripts/trading_bot/postures/PREREG_POSTURE_A.md (frozen before any effect).
"""
import csv, math, os, sys, time
import numpy as np

ROOT = "/home/anont/meme"
PANEL = os.path.join(ROOT, "research/data/t23_cache/panel")
SEED = 20260903
NBOOT = 5000
RT_BP = 24.1          # round-trip bp, repo-measured for two perp legs
LEG_BP = RT_BP / 2.0  # one leg
QV_MIN = 1_000_000.0
DAY = 86400000

def load_panel():
    syms, days = {}, {}
    rows = []
    with open(os.path.join(PANEL, "perp_daily.csv")) as f:
        r = csv.reader(f); next(r)
        for s, d, c, qv, tr in r:
            d = int(d)
            si = syms.setdefault(s, len(syms))
            di = days.setdefault(d, len(days))
            rows.append((di, si, float(c), float(qv)))
    ns, nd = len(syms), len(days)
    order = np.argsort(np.array(sorted(days, key=lambda k: days[k])))  # unused
    dayvals = np.array(sorted(days.keys()))
    remap = {days[d]: i for i, d in enumerate(dayvals)}
    close = np.full((nd, ns), np.nan); qvm = np.full((nd, ns), np.nan)
    for di, si, c, qv in rows:
        i = remap[di]
        close[i, si] = c; qvm[i, si] = qv
    inv = {v: k for k, v in syms.items()}
    symnames = [inv[i] for i in range(ns)]
    return dayvals, symnames, close, qvm

def load_funding(dayvals, symnames):
    sidx = {s: i for i, s in enumerate(symnames)}
    didx = {d: i for i, d in enumerate(dayvals)}
    F = np.zeros((len(dayvals), len(symnames))); H = np.zeros_like(F, dtype=bool)
    n = 0
    with open(os.path.join(PANEL, "funding.csv")) as f:
        r = csv.reader(f); next(r)
        for s, tms, ih, rate in r:
            si = sidx.get(s)
            if si is None: continue
            d = (int(tms) // DAY) * DAY
            di = didx.get(d)
            if di is None: continue
            F[di, si] += float(rate); H[di, si] = True; n += 1
    return F, H, n

def dstr(ms): return time.strftime('%Y-%m-%d', time.gmtime(ms/1000))

def metrics(r, ann=365.0):
    r = np.asarray(r, float)
    n = len(r)
    eq = np.cumprod(1.0 + r)
    total = eq[-1] - 1.0
    yrs = n / ann
    cagr = eq[-1] ** (1.0 / yrs) - 1.0 if eq[-1] > 0 else -1.0
    mu = r.mean(); sd = r.std(ddof=1)
    vol = sd * math.sqrt(ann)
    sharpe = mu / sd * math.sqrt(ann) if sd > 0 else float('nan')
    peak = np.maximum.accumulate(eq); dd = eq / peak - 1.0
    mdd = dd.min()
    # worst 60-day compounded window
    w = 60
    if n > w:
        lg = np.log1p(np.clip(r, -0.999999, None))
        cs = np.concatenate([[0.0], np.cumsum(lg)])
        win = cs[w:] - cs[:-w]
        w60 = math.expm1(win.min())
        i60 = int(np.argmin(win))
    else:
        w60, i60 = float('nan'), -1
    return dict(n=n, mean_daily=mu, sd_daily=sd, total=total, cagr=cagr, vol=vol,
                sharpe=sharpe, mdd=mdd, w60=w60, i60=i60, eq=eq)

def boot_ci(r, seed=SEED, nboot=NBOOT):
    """Cluster bootstrap by DATE. Basket series = one obs per date -> resample dates."""
    rng = np.random.default_rng(seed)
    r = np.asarray(r, float); n = len(r)
    idx = rng.integers(0, n, size=(nboot, n))
    samp = r[idx]
    mus = samp.mean(axis=1)
    sds = samp.std(axis=1, ddof=1)
    shr = np.where(sds > 0, mus / sds * math.sqrt(365.0), np.nan)
    q = lambda a, p: float(np.percentile(a, p))
    return dict(mu_lo=q(mus, 2.5), mu_hi=q(mus, 97.5), mu_lo1=q(mus, 5.0),
                sh_lo=q(shr, 2.5), sh_hi=q(shr, 97.5), sh_lo1=q(shr, 5.0),
                p_le0=float((mus <= 0).mean()))

# ---------------- portfolio engine ----------------
def run_basket(close, qvm, F, H, elig_mask, rebal_every=1, charge_cost=True,
               charge_funding=True, top_n=None, trail=None):
    """Weights set at close of day t over eligible set; return earned over day t+1.
    Delisted name (no close next day) -> settled at last price (r=0) and force-exited to cash.
    Returns dict with gross/net series and turnover."""
    nd, ns = close.shape
    have = ~np.isnan(close)
    w = np.zeros(ns)
    cash = 1.0  # fraction not invested (only from forced exits between rebalances)
    gross = np.zeros(nd - 1); net = np.zeros(nd - 1); to = np.zeros(nd - 1)
    fund = np.zeros(nd - 1); nheld = np.zeros(nd - 1, dtype=int)
    forced = 0
    invested = False
    for t in range(nd - 1):
        # --- rebalance decision at close of day t (info through day t only)
        if t % rebal_every == 0:
            e = elig_mask[t]
            k = int(e.sum())
            if k > 0:
                wt = np.zeros(ns); wt[e] = 1.0 / k
            else:
                wt = np.zeros(ns)
            turn = 0.5 * np.abs(wt - w).sum()
            w = wt
            invested = k > 0
        else:
            turn = 0.0
        to[t] = turn
        nheld[t] = int((w > 0).sum())
        # --- returns over day t+1
        c0 = close[t]; c1 = close[t + 1]
        alive = have[t + 1] & have[t]
        r = np.zeros(ns)
        np.divide(c1, c0, out=r, where=alive)
        r = np.where(alive, r - 1.0, 0.0)
        g = float((w * r).sum())
        # funding paid by longs on day t+1 (rate>0 = long pays)
        fpay = float((w * F[t + 1]).sum()) if charge_funding else 0.0
        fund[t] = fpay
        cost = turn * (RT_BP / 1e4) if charge_cost else 0.0
        gross[t] = g
        net[t] = g - fpay - cost
        # --- drift weights
        neww = w * (1.0 + r)
        s = neww.sum()
        if s > 0:
            neww = neww / (1.0 + g) if (1.0 + g) > 0 else neww
        # forced exit of names that stop trading after t+1
        dead = (w > 0) & (~have[t + 1])
        if dead.any():
            forced += int(dead.sum())
        # names with no close on t+1 are gone; their (settled) value stays as cash -> weight 0
        gone = (~have[t + 1]) & (neww > 0)
        neww[gone] = 0.0
        w = neww
    return dict(gross=gross, net=net, turn=to, fund=fund, nheld=nheld, forced=forced)

def fmt(m, label, extra=""):
    return (f"{label:<34s} n={m['n']:5d} CAGR={m['cagr']*100:8.2f}%  vol={m['vol']*100:6.1f}%  "
            f"Sharpe={m['sharpe']:6.3f}  maxDD={m['mdd']*100:7.1f}%  worst60d={m['w60']*100:7.1f}%  "
            f"mean/day={m['mean_daily']*1e4:7.2f}bp {extra}")

def main():
    t0 = time.time()
    dayvals, symnames, close, qvm = load_panel()
    nd, ns = close.shape
    F, H, nfund = load_funding(dayvals, symnames)
    have = ~np.isnan(close)
    print("="*118)
    print("POSTURE A - OWN THE BASKET | panel %s .. %s | days=%d symbols=%d rows=%d"
          % (dstr(dayvals[0]), dstr(dayvals[-1]), nd, ns, int(have.sum())))
    print("="*118)

    # eligibility: qv on day t >= $1M and price present on day t (weights set at close t)
    elig = have & (np.nan_to_num(qvm, nan=0.0) >= QV_MIN)

    # ---------- GATE 1 COVERAGE ----------
    print("\n--- GATE 1 COVERAGE (minimums declared in PREREG before counting) ---")
    per_day = elig.sum(axis=1)
    g1a = int((per_day >= 20).sum())
    g1b = int((elig.any(axis=0)).sum())
    heldmask = elig[:-1]  # symbol-days actually held under daily rebal
    fund_cov = float(H[1:][heldmask].mean()) if heldmask.sum() else 0.0
    last_day = np.array([np.max(np.where(have[:, i])[0]) if have[:, i].any() else -1 for i in range(ns)])
    delisted = int((last_day < nd - 1).sum())
    print(f"G1a days with >=20 liquid names : {g1a:5d}  (min 1000)   {'PASS' if g1a>=1000 else 'FAIL'}")
    print(f"G1b distinct symbols ever liquid: {g1b:5d}  (min  300)   {'PASS' if g1b>=300 else 'FAIL'}")
    print(f"G1c funding coverage of held sym-days: {fund_cov*100:5.1f}% (min 80%)  {'PASS' if fund_cov>=0.80 else 'FAIL'}  (funding rows used={nfund})")
    print(f"G1d survivorship: symbols whose last panel day < panel end = {delisted} of {ns} "
          f"({delisted/ns*100:.1f}%)  {'PASS' if delisted>50 else 'FAIL'}")
    if not (g1a>=1000 and g1b>=300 and fund_cov>=0.80 and delisted>50):
        print("\nGATE 1 FAILED -> STOP."); return
    print("GATE 1 PASS.")

    # replicate the brief's headline (contemporaneous screen, symbol-day level)
    r_all = np.full((nd-1, ns), np.nan)
    a = have[:-1] & have[1:]
    r_all[a] = close[1:][a] / close[:-1][a] - 1.0
    sel = elig[:-1] & a
    day_mean = np.array([r_all[t][sel[t]].mean() if sel[t].sum() else np.nan for t in range(nd-1)])
    day_med  = np.array([np.median(r_all[t][sel[t]]) if sel[t].sum() else np.nan for t in range(nd-1)])
    ok = ~np.isnan(day_mean)
    m_all, md_all = day_mean[ok].mean(), day_med[ok].mean()
    print(f"\n[replication of the brief] symbol-day EW-mean {m_all*1e4:.2f} bp/day vs cross-sectional "
          f"MEDIAN {md_all*1e4:.2f} bp/day  gap={(m_all-md_all)*100:.4f} pp/day  "
          f"(n_days={int(ok.sum())}, n_symday={int(sel.sum())})")
    print(f"  mean-name compounding  : {(np.cumprod(1+day_mean[ok])[-1]-1)*100:+.1f}%")
    print(f"  median-name compounding: {(np.cumprod(1+day_med[ok])[-1]-1)*100:+.1f}%  "
          f"<- NOT holdable; control rule forbids using it as benchmark")

    # ---------- GATE 2 POWER (before any effect is read) ----------
    print("\n--- GATE 2 POWER (declared before reading the effect) ---")
    z = 1.6448536269514722 + 0.8416212335729143
    sd_pilot = np.nanstd(day_mean[ok], ddof=1)
    n_days_eff = int(ok.sum())
    mde = z * sd_pilot / math.sqrt(n_days_eff)
    m_per_day = float(sel.sum()) / n_days_eff
    deff_sym = 1.0 + (m_per_day - 1.0) * 0.3
    print(f"basket series: 1 obs/date -> date-clustered DEFF = 1.000 (ICC 0.3 cannot bite)")
    print(f"sd(daily basket ret) = {sd_pilot*100:.3f}%/day, n_days = {n_days_eff}")
    print(f"MDE(mean daily basket return) = {mde*1e4:.2f} bp/day  @ alpha .05 1-sided, power .80")
    print(f"  -> annualised MDE = {mde*365*100:.1f}%/yr ; kill line: point estimate below MDE = NOT ESTABLISHED")
    print(f"symbol-day panel (where ICC bites): mean {m_per_day:.1f} names/day -> DEFF={deff_sym:.1f}, "
          f"n_eff = {sel.sum()/deff_sym:.0f} of {int(sel.sum())} symbol-days")

    # ---------- baskets ----------
    print("\n--- BASKETS (all long-only, gross = price only; net = price - funding - turnover cost) ---")
    res = {}
    res['ew_d'] = run_basket(close, qvm, F, H, elig, rebal_every=1)
    # BTC alone
    btc = symnames.index('BTCUSDT')
    bm = np.zeros((nd, ns), bool); bm[:, btc] = have[:, btc]
    res['btc'] = run_basket(close, qvm, F, H, bm, rebal_every=1)
    # top-20 by trailing 30d mean quote volume, lagged (uses info through day t)
    qv0 = np.nan_to_num(qvm, nan=0.0)
    csum = np.cumsum(np.vstack([np.zeros(ns), qv0]), axis=0)
    trail30 = (csum[30:] - csum[:-30]) / 30.0   # trail30[t-29] uses days t-29..t
    T30 = np.zeros_like(qv0); T30[29:] = trail30
    top = np.zeros((nd, ns), bool)
    for t in range(nd):
        v = np.where(elig[t], T30[t], -1.0)
        if (v > 0).sum() == 0: continue
        k = min(20, int((v > 0).sum()))
        idx = np.argpartition(-v, k-1)[:k]
        top[t, idx] = True
    res['top20'] = run_basket(close, qvm, F, H, top, rebal_every=1)

    lab = {'ew_d': 'EW liquid basket (daily reb)', 'btc': 'BTCUSDT alone', 'top20': 'Top-20 by trailing qv'}
    M = {}
    for k in ['ew_d', 'btc', 'top20']:
        M[k+'_g'] = metrics(res[k]['gross']); M[k+'_n'] = metrics(res[k]['net'])
        print(fmt(M[k+'_g'], lab[k]+" GROSS"))
        print(fmt(M[k+'_n'], lab[k]+" NET  ",
                  f"| turn/day={res[k]['turn'].mean()*100:5.2f}% funding={res[k]['fund'].mean()*1e4:5.2f}bp/day names={res[k]['nheld'].mean():.0f}"))
    print(f"\nforced delist exits inside EW basket: {res['ew_d']['forced']}")
    print(f"EW basket cost decomposition (bp/day): gross {M['ew_d_g']['mean_daily']*1e4:+.2f} "
          f"- funding {res['ew_d']['fund'].mean()*1e4:.2f} - turnover cost {res['ew_d']['turn'].mean()*RT_BP:.2f} "
          f"= net {M['ew_d_n']['mean_daily']*1e4:+.2f}")

    # ---------- rebalance frequency ----------
    print("\n--- REBALANCE FREQUENCY (EW liquid basket) ---")
    freqs = [(1,'daily'), (7,'weekly'), (28,'monthly')]
    freqres = {}
    for k, nm in freqs:
        rr = run_basket(close, qvm, F, H, elig, rebal_every=k)
        mg, mn = metrics(rr['gross']), metrics(rr['net'])
        freqres[nm] = (rr, mn)
        print(f"{nm:<8s} turn/day={rr['turn'].mean()*100:6.3f}%  cost={rr['turn'].mean()*RT_BP:5.2f}bp/day  "
              f"GROSS Sharpe={mg['sharpe']:6.3f} CAGR={mg['cagr']*100:7.2f}%  ||  "
              f"NET Sharpe={mn['sharpe']:6.3f} CAGR={mn['cagr']*100:7.2f}% maxDD={mn['mdd']*100:6.1f}%")

    # zero-cost / zero-funding counterfactual
    rr0 = run_basket(close, qvm, F, H, elig, rebal_every=1, charge_cost=False, charge_funding=False)
    m0 = metrics(rr0['net'])
    print(fmt(m0, "EW daily, ZERO cost+funding"))

    # ---------- GATE 3 EFFECT ----------
    print("\n--- GATE 3 EFFECT (cluster bootstrap by DATE, 5000 draws, seed 20260903) ---")
    for k in ['ew_d', 'btc', 'top20']:
        ci = boot_ci(res[k]['net'])
        m = M[k+'_n']
        print(f"{lab[k]:<30s} NET mean/day={m['mean_daily']*1e4:+7.2f}bp  95%CI=[{ci['mu_lo']*1e4:+7.2f},{ci['mu_hi']*1e4:+7.2f}]bp  "
              f"Sharpe={m['sharpe']:.3f} CI=[{ci['sh_lo']:.3f},{ci['sh_hi']:.3f}]  P(mu<=0)={ci['p_le0']:.3f}  "
              f"{'PASS' if ci['mu_lo']>0 else 'FAIL(CI-lo<=0)'}")
        print(f"    vs MDE {mde*1e4:.2f}bp/day -> {'ADEQUATELY POWERED' if abs(m['mean_daily'])>=mde else 'UNDERPOWERED: NOT ESTABLISHED'}")

    # ---------- OVERLAY (pre-registered, lookback 100) ----------
    print("\n--- OVERLAY: flat below own 100d SMA (pre-registered, single spec) ---")
    def overlay(net_series, lb):
        eq = np.cumprod(1.0 + net_series)
        pos = np.ones(len(net_series))
        for t in range(len(net_series)):
            if t < lb:
                pos[t] = 1.0
            else:
                sma = eq[t-lb:t].mean()
                pos[t] = 1.0 if eq[t-1] >= sma else 0.0
        out = net_series * pos
        sw = np.abs(np.diff(np.concatenate([[1.0], pos])))
        out = out - sw * (LEG_BP / 1e4)
        return out, pos
    base = res['ew_d']['net']
    ov, pos = overlay(base, 100)
    mo = metrics(ov); mb = M['ew_d_n']
    print(fmt(mb, "EW daily NET (no overlay)"))
    print(fmt(mo, "EW daily NET + 100d SMA filter", f"| in-market {pos.mean()*100:.1f}% switches={int(np.abs(np.diff(pos)).sum())}"))
    verdict = ("IMPROVES" if (mo['sharpe'] > mb['sharpe'] and mo['mdd'] > mb['mdd']) else "FAILS")
    print(f"pre-registered overlay verdict: {verdict}  (dSharpe={mo['sharpe']-mb['sharpe']:+.3f}, "
          f"dMaxDD={(mo['mdd']-mb['mdd'])*100:+.1f}pp, dCAGR={(mo['cagr']-mb['cagr'])*100:+.2f}pp)")
    print("  DIAGNOSTIC ONLY lookback sweep (may not be used to select):")
    wins = 0
    for lb in [20,30,50,60,80,100,120,150,180,200]:
        o, p = overlay(base, lb); mm = metrics(o)
        w = mm['sharpe'] > mb['sharpe']
        wins += w
        print(f"    lb={lb:3d}  Sharpe={mm['sharpe']:6.3f} ({mm['sharpe']-mb['sharpe']:+.3f})  "
              f"CAGR={mm['cagr']*100:7.2f}% ({(mm['cagr']-mb['cagr'])*100:+6.2f}pp)  maxDD={mm['mdd']*100:6.1f}% "
              f"({(mm['mdd']-mb['mdd'])*100:+5.1f}pp)  {'sharpe-up' if w else 'sharpe-down'}")
    print(f"    lookbacks improving Sharpe: {wins}/10")

    # ---------- PRODUCT LINE ----------
    print("\n--- PRODUCT LINE (declared in PREREG: net Sharpe >= 0.50 AND maxDD <= 50%) ---")
    for k, nm in [('ew_d','EW liquid daily'), ('btc','BTCUSDT'), ('top20','Top-20 cap proxy')]:
        m = M[k+'_n']
        ok_s = m['sharpe'] >= 0.50; ok_d = m['mdd'] >= -0.50
        print(f"{nm:<20s} Sharpe={m['sharpe']:6.3f} {'ok' if ok_s else 'FAIL'} | maxDD={m['mdd']*100:7.1f}% "
              f"{'ok' if ok_d else 'FAIL'} -> {'PRODUCT' if (ok_s and ok_d) else 'NOT A PRODUCT'}")
    mo_ok = mo['sharpe'] >= 0.50 and mo['mdd'] >= -0.50
    print(f"{'EW + SMA overlay':<20s} Sharpe={mo['sharpe']:6.3f} | maxDD={mo['mdd']*100:7.1f}% -> "
          f"{'PRODUCT' if mo_ok else 'NOT A PRODUCT'}")
    print(f"\nedge/cost ratio (EW daily): gross {M['ew_d_g']['mean_daily']*1e4:.2f} bp/day vs all-in daily drag "
          f"{(res['ew_d']['fund'].mean()*1e4 + res['ew_d']['turn'].mean()*RT_BP):.2f} bp/day -> "
          f"{M['ew_d_g']['mean_daily']*1e4 / max(1e-9,(res['ew_d']['fund'].mean()*1e4 + res['ew_d']['turn'].mean()*RT_BP)):.2f}x")
    # worst 60d window dates
    for k in ['ew_d','btc','top20']:
        m = M[k+'_n']
        i = m['i60']
        print(f"worst 60d {lab[k]:<30s} {m['w60']*100:7.1f}%  ending {dstr(dayvals[min(nd-1,i+61)])}")
    print("\nelapsed %.1fs" % (time.time()-t0))

if __name__ == "__main__":
    main()
