#!/usr/bin/env python3
"""
INVENT 0822 -- THEME: LOW-TURNOVER (monthly / quarterly) cross-sectional US equity tilts.

Premise under test: the execution-cost wall bites FAST signals. A signal held ~1-3 months
pays the 5bp half-spread roughly h times less often. So the question this sleeve asks is
NOT "can a cost fix rescue a fast signal" (settled: no, the wall is a SIGNIFICANCE wall)
but "is there any SLOW structural tilt whose GROSS Sharpe clears the multiple-testing bar
in the first place -- and if so, is its turnover low enough that cost is immaterial?"

Design 2016-01-04..2021-12-31, held-out 2022-01-03..2026-08-14 (same split as the
newterr_xseq round; the held-out window is NOT looked at until picks are frozen).

Signals are declared LONG=high from a stated mechanism, never fitted. No regime
conditioners anywhere (0/107 survived in round 3 -- that lesson is obeyed by omission).

Usage:  python3 invent0822_slow_xs.py design|holdout|null|selftest
"""
import json, os, sys, math, gc
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from trading_bot.newterr_xseq_sweep import (
    Panel, roll_mean, roll_std, roll_geomean, lag, xs_rank, decile_weights,
    run_book, stats, wmask, F32, FEE, STRESS_FLAT,
)

RES = "/home/anont/meme/research/trading_bot"
CACHE = "/home/anont/meme/research/data/inv0822_cache"
os.makedirs(CACHE, exist_ok=True)

DESIGN = ("2016-01-04", "2021-12-31")
HOLDOUT = ("2022-01-03", "2026-08-14")
HORIZONS = (21, 63)          # ~1 month and ~1 quarter overlapping books
NULL_DRAWS = 150

# ------------------------------------------------------------------ mechanisms
PAY = ("Cash actually paid out is the one hard fundamental in a price-and-dividend panel: "
       "a high payout-to-price is a claim on realised cash flow, and the clientele that "
       "needs that cash is price-insensitive in the wrong direction.")
ILQ = ("Holding inventory that is expensive to exit is a real cost, so illiquid names must "
       "offer a return premium to be held. It is only harvestable by an investor who trades "
       "rarely -- which is exactly what this sleeve is.")
REC = ("Merton (1987) investor recognition: a shrinking investor base raises the required "
       "return of the names it abandons.")
LEV = ("Leverage-constrained investors express views by buying high-beta / high-vol names "
       "rather than levering, so they systematically overpay for risk.")
SHP = ("Investors pay for convexity and charge for concavity, so payoff-shape asymmetry "
       "relative to the market carries a premium independent of its variance.")
SES = ("The close-to-open gap cannot be hedged or exited; bearing it is a distinct risk "
       "from bearing intraday variance, and should be paid for separately.")
LTR = ("Multi-year over-extrapolation of fundamentals corrects on a multi-year clock -- a "
       "slow correction only a slow book can hold.")
ATT = ("Episodic attention (volume arriving in a few jackpot days) is the footprint of a "
       "lottery clientele; the names it visits are left overpriced.")
UNC = ("Uncertainty about a name's own second moment is a risk that variance itself does "
       "not price.")


def build_signals(P):
    """(name, family, mechanism, signal[T,N]); higher == LONG."""
    C, O, H, L, V, DIV = P.C, P.O, P.H, P.L, P.V, P.DIV
    rc, rco, roc, dv, elig = P.rc, P.rco, P.roc, P.dv, P.elig
    S = []
    a = lambda n, f, m, s: S.append((n, f, m, np.asarray(s, F32)))
    NAN = np.float32(np.nan)

    # ---------- slow risk primitives (250d) ----------
    m = np.broadcast_to(P.mkt[:, None], C.shape).astype(F32)
    rcf = np.where(elig, rc, np.nan).astype(F32)
    cov = roll_mean(rcf * m, 250) - roll_mean(rcf, 250) * roll_mean(m, 250)
    var = roll_mean((m * m).astype(F32), 250) - roll_mean(m, 250) ** 2
    beta250 = np.clip(cov / np.maximum(var, 1e-12), -3.0, 5.0).astype(F32)
    resid250 = (rcf - beta250 * m).astype(F32)
    sig250 = roll_std(rcf, 250)
    ivol250 = roll_std(resid250, 250)
    del cov, var
    gc.collect()

    # ---------- dividends ----------
    d = np.where(np.isfinite(DIV), DIV, 0.0).astype(F32)
    ttm = (roll_mean(d, 252, minobs=200) * 252.0).astype(F32)
    ttm_prev = lag(ttm, 252)
    ndiv = (roll_mean((d > 0).astype(F32), 252, minobs=200) * 252.0).astype(F32)
    divy = (ttm / np.maximum(C, 1e-6)).astype(F32)
    divy = np.where(np.isfinite(divy), divy, np.nan).astype(F32)
    payer = (ttm > 0) & (ttm_prev > 0)

    # A1 payout-to-price level
    a("DIVY_TTM", "payout", PAY, divy)
    # A2 payout per unit of risk (cash-quality composite, not a conditioner: a ratio)
    a("DIVY_VOLADJ", "payout", PAY, divy / np.maximum(sig250, 1e-4))
    # A3 payout growth, payers only
    g = np.where(payer, ttm / np.maximum(ttm_prev, 1e-9) - 1.0, np.nan).astype(F32)
    a("DIV_GROWTH", "payout", PAY, np.clip(g, -1.0, 2.0))
    # A4 downside-only: depth of a cut (long the non-cutters)
    a("DIV_CUT_DEPTH", "payout", PAY,
      np.where(payer, -np.maximum(0.0, 1.0 - ttm / np.maximum(ttm_prev, 1e-9)), np.nan))
    # A5 initiation / resumption of a payout
    a("DIV_INIT", "payout", PAY,
      np.where(np.isfinite(ttm) & np.isfinite(ttm_prev),
               ((ttm > 0) & (ttm_prev <= 0)).astype(np.float32), np.nan))
    # A6 payout cadence (how many separate payments back the same yield)
    a("DIV_CADENCE", "payout", PAY, np.where(ttm > 0, ndiv, np.nan))

    # ---------- illiquidity / holding cost ----------
    amih = roll_mean((np.abs(rc) / np.maximum(dv, 1.0) * 1e9).astype(F32), 250)
    lamih = np.log(np.maximum(amih, 1e-9)).astype(F32)
    a("ILLIQ_AMIHUD", "illiq", ILQ, lamih)
    hs250 = roll_mean(P.hs, 250)
    a("SPREAD_LEVEL", "illiq", ILQ, hs250)
    # uncertainty ABOUT the exit cost, not its level
    a("ILLIQ_UNCERT", "illiq", ILQ, roll_std(lamih, 250))
    advg60 = roll_geomean(np.where(np.isfinite(dv), dv, 0.0), 60)
    advg500 = roll_geomean(np.where(np.isfinite(dv), dv, 0.0), 500)
    a("ATTN_DECAY", "illiq", REC,
      -(np.log(np.maximum(advg60, 1.0)) - np.log(np.maximum(advg500, 1.0))))
    # composite of two independent frictions
    a("ILLIQ_x_DIVY", "composite", ILQ,
      xs_rank(lamih, elig) + xs_rank(divy, elig))

    # ---------- risk-shape / leverage constraint ----------
    a("BETA_LOW", "riskshape", LEV, -beta250)
    a("IVOL_LOW", "riskshape", LEV, -ivol250)
    md = np.where(m < 0, m, np.nan).astype(F32)
    mu_ = np.where(m > 0, m, np.nan).astype(F32)
    rd = np.where(m < 0, rcf, np.nan).astype(F32)
    ru = np.where(m > 0, rcf, np.nan).astype(F32)
    bd = ((roll_mean(rd * md, 250, minobs=60) - roll_mean(rd, 250, minobs=60) * roll_mean(md, 250, minobs=60))
          / np.maximum(roll_mean(md * md, 250, minobs=60) - roll_mean(md, 250, minobs=60) ** 2, 1e-12))
    bu = ((roll_mean(ru * mu_, 250, minobs=60) - roll_mean(ru, 250, minobs=60) * roll_mean(mu_, 250, minobs=60))
          / np.maximum(roll_mean(mu_ * mu_, 250, minobs=60) - roll_mean(mu_, 250, minobs=60) ** 2, 1e-12))
    a("DOWNBETA_GAP", "riskshape", SHP, np.clip(bd - bu, -4.0, 4.0))
    del rd, ru, md, mu_
    # tail version: only the |m| > 1.5 sigma days on each side, 500d
    msd = roll_std(P.mkt[:, None].astype(F32), 250)
    msd = np.broadcast_to(msd, C.shape)
    tdn = m < -1.5 * msd
    tup = m > 1.5 * msd
    rtd = np.where(tdn, rcf, np.nan).astype(F32); mtd = np.where(tdn, m, np.nan).astype(F32)
    rtu = np.where(tup, rcf, np.nan).astype(F32); mtu = np.where(tup, m, np.nan).astype(F32)
    btd = ((roll_mean(rtd * mtd, 500, minobs=15) - roll_mean(rtd, 500, minobs=15) * roll_mean(mtd, 500, minobs=15))
           / np.maximum(roll_mean(mtd * mtd, 500, minobs=15) - roll_mean(mtd, 500, minobs=15) ** 2, 1e-12))
    btu = ((roll_mean(rtu * mtu, 500, minobs=15) - roll_mean(rtu, 500, minobs=15) * roll_mean(mtu, 500, minobs=15))
           / np.maximum(roll_mean(mtu * mtu, 500, minobs=15) - roll_mean(mtu, 500, minobs=15) ** 2, 1e-12))
    a("TAILBETA_ASYM", "riskshape", SHP, np.clip(btd - btu, -6.0, 6.0))
    del rtd, mtd, rtu, mtu, btd, btu, tdn, tup
    # coskewness with the market (long the NEGATIVE-coskew names)
    mz = (m - roll_mean(m, 250)) / np.maximum(roll_std(m, 250), 1e-6)
    rz = (rcf - roll_mean(rcf, 250)) / np.maximum(sig250, 1e-6)
    cosk = roll_mean((rz * mz * mz).astype(F32), 250)
    a("COSKEW_NEG", "riskshape", SHP, -np.clip(cosk, -5.0, 5.0))
    del mz, rz, cosk
    # vol-of-vol: uncertainty about own second moment
    v21 = roll_std(rcf, 21)
    a("VOL_UNCERT", "riskshape", UNC, roll_std(v21, 250) / np.maximum(roll_mean(v21, 250), 1e-5))
    del v21

    # ---------- session structure / path ----------
    a("OVN_MINUS_INTRA", "path", SES,
      (roll_mean(np.where(elig, roc, np.nan).astype(F32), 250)
       - roll_mean(np.where(elig, rco, np.nan).astype(F32), 250)) * F32(250.0))
    # long-term reversal on the residual, months -24..-12 (needs 500d of history)
    a("LTREV_RESID", "path", LTR, -lag(roll_mean(resid250, 250, minobs=200), 250) * F32(250.0))
    # episodic-attention concentration: share of dollar volume arriving on spike days
    advg20 = roll_geomean(np.where(np.isfinite(dv), dv, 0.0), 20)
    spike = np.where(dv > 3.0 * lag(advg20, 1), dv, 0.0).astype(F32)
    conc = roll_mean(spike, 250) / np.maximum(roll_mean(dv, 250), 1.0)
    a("ATTN_SPIKE_CONC", "path", ATT, -conc)
    del spike, conc, advg20

    # ---------- one deliberate quality-income composite ----------
    a("DIVY_x_LOWVOL", "composite", PAY,
      xs_rank(divy, elig) + xs_rank(-sig250, elig))

    del m, rcf, beta250, resid250, sig250, ivol250, lamih, amih, hs250
    gc.collect()
    return S


# ------------------------------------------------------------------ sweep
def nw_t(pnl, mask, lags):
    """Newey-West t on the mean. An h-day OVERLAPPING book has h-1 days of built-in
    autocorrelation, so the naive mean/sd*sqrt(n) t is mechanically INFLATED for this
    whole sleeve. Every conclusion below uses the corrected number where it matters."""
    x = pnl[mask]; x = x[np.isfinite(x)]
    n = len(x)
    if n < 250:
        return 0.0
    e = x - x.mean()
    g0 = float(e @ e) / n
    s = g0
    for L in range(1, min(lags, n - 1) + 1):
        gl = float(e[L:] @ e[:-L]) / n
        s += 2.0 * (1.0 - L / (lags + 1.0)) * gl
    if s <= 0:
        return 0.0
    return float(x.mean() / math.sqrt(s / n))


def sweep(P, window, sigs=None):
    mask = wmask(P, window)
    rows = []
    sigs = sigs if sigs is not None else build_signals(P)
    for i, (name, fam, mech, s) in enumerate(sigs):
        w = decile_weights(xs_rank(s, P.elig))
        for h in HORIZONS:
            g, c, t, b = run_book(P, w, h)
            sg = stats(g, mask); sn = stats(g - c, mask)
            flat = {}
            for fc in STRESS_FLAT:
                flat[f"net_sharpe_flat{int(fc*1e4)}bp"] = stats(g - (t * (fc + FEE) + b), mask)["sharpe"]
            gm = float(np.nanmean(g[mask])); tm = float(np.nanmean(t[mask]))
            be = (gm / tm * 1e4) if tm > 0 else 0.0
            cm = float(np.nanmean(c[mask]))
            rows.append(dict(name=name, family=fam, mechanism=mech, h=h,
                             gross_sharpe=sg["sharpe"], gross_t=sg["t"], gross_bps=sg["mean_bps"],
                             gross_t_nw=nw_t(g, mask, h), net_t_nw=nw_t(g - c, mask, h),
                             net_sharpe=sn["sharpe"], net_t=sn["t"], net_bps=sn["mean_bps"],
                             breakeven_cost_bps=be, turnover_per_day=tm,
                             cost_bps_per_day=cm * 1e4,
                             cost_share_of_gross=(cm / gm if gm > 0 else float("nan")),
                             n=sn["n"], **flat))
        del w
        print(f"  [{i+1}/{len(sigs)}] {name}", flush=True)
        gc.collect()
    return rows


# ------------------------------------------------------------------ empirical null
def null_bar(P, draws=NULL_DRAWS, seed=11):
    """Slow random signals with the SAME persistence class as the real ones, pushed
    through the identical ranking/booking pipeline. This is the honest bar: an iid
    t-distribution understates the max because a slow book is autocorrelated.
    Both horizons share one draw's ranking (the expensive step)."""
    rng = np.random.default_rng(seed)
    mask = wmask(P, DESIGN)
    T, N = P.C.shape
    acc = {h: ([], []) for h in HORIZONS}
    for k in range(draws):
        z = rng.standard_normal((T, N)).astype(F32)
        s = roll_mean(z, 250, minobs=100)          # same 250d smoothing as the real signals
        del z
        w = decile_weights(xs_rank(s, P.elig))
        del s
        for h in HORIZONS:
            g, c, t, b = run_book(P, w, h)
            st = stats(g, mask)
            acc[h][0].append(st["t"]); acc[h][1].append(st["sharpe"])
            del g, c, t, b
        del w
        if (k + 1) % 10 == 0:
            print(f"  null {k+1}/{draws}", flush=True)
        gc.collect()
    out = {}
    for h in HORIZONS:
        ts = np.array(acc[h][0]); shs = np.array(acc[h][1])
        out[f"h{h}"] = dict(draws=draws, h=h,
                            t_mean=float(ts.mean()), t_sd=float(ts.std(ddof=1)),
                            abs_t_p50=float(np.percentile(np.abs(ts), 50)),
                            abs_t_p95=float(np.percentile(np.abs(ts), 95)),
                            abs_t_p99=float(np.percentile(np.abs(ts), 99)),
                            abs_t_max=float(np.abs(ts).max()),
                            sharpe_sd=float(shs.std(ddof=1)),
                            abs_sharpe_p95=float(np.percentile(np.abs(shs), 95)))
    return out


def selftest(P):
    rng = np.random.default_rng(3)
    mask = wmask(P, DESIGN)
    fwd = np.full_like(P.roo, np.nan); fwd[:-1] = P.roo[1:]
    fwd = np.where(np.isfinite(fwd), fwd, 0.0).astype(F32)
    # a PERSISTENT planted edge: the signal at t must forecast the mean of roo[t+1..t+21],
    # which is what a 21-day overlapping book actually earns.
    fm = roll_mean(fwd, 21, minobs=10).astype(F32)
    slow = np.full_like(fm, np.nan); slow[:-20] = fm[20:]
    noise = rng.standard_normal(P.C.shape).astype(F32)
    out = {}
    for tag, s in (("planted_slow", (slow * 100 + noise * .5).astype(F32)),
                   ("planted_slow_signflip", (-(slow * 100 + noise * .5)).astype(F32)),
                   ("pure_noise_slow", roll_mean(noise, 250, minobs=100))):
        w = decile_weights(xs_rank(s, P.elig))
        g, c, t, _b = run_book(P, w, 21)
        out[tag] = dict(gross=stats(g, mask), net=stats(g - c, mask),
                        turnover=float(np.nanmean(t[mask])))
    out["mean_half_spread_bps_eligible"] = float(np.nanmean(np.where(P.elig, P.hs, np.nan)) * 1e4)
    out["median_eligible_per_day"] = float(np.median(P.elig.sum(axis=1)[mask]))
    return out


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "design"
    P = Panel()
    if cmd == "selftest":
        out = selftest(P)
        json.dump(out, open(os.path.join(CACHE, "SELFTEST.json"), "w"), indent=1, default=float)
        print(json.dumps(out, indent=1, default=float))
        return
    if cmd == "null":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else NULL_DRAWS
        out = null_bar(P, draws=n)
        print(json.dumps(out, indent=1))
        json.dump(out, open(os.path.join(CACHE, "NULL.json"), "w"), indent=1, default=float)
        return
    win = DESIGN if cmd == "design" else HOLDOUT
    rows = sweep(P, win)
    N = len(rows)
    out = dict(window=win, n_cells=N, horizons=list(HORIZONS),
               expected_max_t_iid=math.sqrt(2 * math.log(max(N, 2))), rows=rows)
    fn = "INVENT_0822_slowturn_XS_DESIGN.json" if cmd == "design" else "INVENT_0822_slowturn_XS_HOLDOUT.json"
    json.dump(out, open(os.path.join(RES, fn), "w"), indent=1, default=float)
    rows.sort(key=lambda r: -r["gross_t"])
    print(f"\n=== {cmd} {win} N_cells={N} sqrt(2lnN)={out['expected_max_t_iid']:.2f}")
    for r in rows:
        print(f"{r['name']:>18s} h{r['h']:>2d} grossSR{r['gross_sharpe']:6.2f} t{r['gross_t']:6.2f} "
              f"tNW{r['gross_t_nw']:6.2f} "
              f"netSR{r['net_sharpe']:6.2f} t{r['net_t']:6.2f} turn{r['turnover_per_day']:7.4f} "
              f"be{r['breakeven_cost_bps']:8.1f}bp costshare{r['cost_share_of_gross']:7.2f}")


if __name__ == "__main__":
    main()
