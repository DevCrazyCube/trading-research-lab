#!/usr/bin/env python3
"""
NEWTERR xs_equity sweep: short-horizon cross-sectional US equity factors.

One vectorized engine, ~40 structurally different formulas x 3 horizons.
Pre-registration: research/trading_bot/NEWTERR_xs_equity_PREREGISTRATION.md

Usage:
  python3 newterr_xseq_sweep.py selftest  # planted-edge / sign-flip / null harness check
  python3 newterr_xseq_sweep.py design    # design window only, writes DESIGN.json
  python3 newterr_xseq_sweep.py holdout   # reads frozen picks, runs held-out window
"""
import json, os, sys, math, gc
import numpy as np

DATA = "/home/anont/meme/research/data"
CACHE = os.path.join(DATA, "newterr_xseq_cache")
RES = "/home/anont/meme/research/trading_bot"

DESIGN = ("2016-01-04", "2021-12-31")
HOLDOUT = ("2022-01-03", "2026-08-14")

MIN_PX = 5.0
MIN_ADV = 20e6
DECILE = 0.10
BORROW_ANNUAL = 0.005
FEE = 0.5e-4
TARGET_MEAN_HS = 5e-4     # 5 bp one-way effective half-spread, universe mean
STRESS_FLAT = (5e-4, 10e-4)
HORIZONS = (1, 3, 5)

F32 = np.float32


# ---------------------------------------------------------------- primitives
def roll_mean(x, w, minobs=None):
    m = np.isfinite(x)
    xf = np.where(m, x, 0.0).astype(np.float64)
    cs = np.cumsum(xf, axis=0)
    cn = np.cumsum(m, axis=0, dtype=np.float64)
    s = cs.copy(); n = cn.copy()
    s[w:] = cs[w:] - cs[:-w]; n[w:] = cn[w:] - cn[:-w]
    mo = minobs if minobs is not None else max(3, w // 2)
    out = np.where(n >= mo, s / np.maximum(n, 1.0), np.nan)
    return out.astype(F32)


def roll_std(x, w):
    m1 = roll_mean(x, w).astype(np.float64)
    m2 = roll_mean((x.astype(np.float64)) ** 2, w).astype(np.float64)
    return np.sqrt(np.maximum(m2 - m1 * m1, 0.0)).astype(F32)


def roll_geomean(x, w):
    return np.exp(roll_mean(np.log(np.maximum(x, 1.0)), w))


def roll_max(x, w):
    """trailing max over w rows inclusive, sparse-table doubling. NaN-aware (fmax)."""
    k = int(math.floor(math.log2(w)))
    M = x.copy()
    for j in range(k):
        sh = 1 << j
        t = np.full_like(M, np.nan)
        t[sh:] = M[:-sh]
        M = np.fmax(M, t)
    rest = w - (1 << k)
    if rest > 0:
        t = np.full_like(M, np.nan)
        t[rest:] = M[:-rest]
        M = np.fmax(M, t)
    M[: w - 1] = np.nan
    return M.astype(F32)


def lag(x, k):
    out = np.full_like(x, np.nan)
    if k > 0:
        out[k:] = x[:-k]
        return out
    return x.copy()


def xs_rank(sig, elig):
    """cross-sectional rank -> uniform [0,1] within eligible set; NaN elsewhere."""
    T, N = sig.shape
    ok = elig & np.isfinite(sig)
    s = np.where(ok, sig.astype(np.float64), np.float64(1e18))
    order = np.argsort(s, axis=1, kind="stable")
    ranks = np.empty(order.shape, np.int32)
    rows = np.arange(T)[:, None]
    ranks[rows, order] = np.arange(N, dtype=np.int32)[None, :]
    del order, s
    cnt = ok.sum(axis=1)
    denom = np.maximum(cnt - 1, 1)[:, None].astype(F32)
    r = (ranks.astype(F32) / denom)
    del ranks
    return np.where(ok, r, np.nan).astype(F32)


def decile_weights(rank, cnt_min=40):
    ok = np.isfinite(rank)
    cnt = ok.sum(axis=1)
    hi = ok & (rank >= 1.0 - DECILE)
    lo = ok & (rank <= DECILE)
    nl = hi.sum(axis=1).astype(np.float64)
    ns = lo.sum(axis=1).astype(np.float64)
    good = (cnt >= cnt_min) & (nl >= 4) & (ns >= 4)
    wl = np.where(nl > 0, 0.5 / np.maximum(nl, 1), 0.0)[:, None].astype(F32)
    ws = np.where(ns > 0, 0.5 / np.maximum(ns, 1), 0.0)[:, None].astype(F32)
    w = np.where(hi, wl, F32(0.0)) - np.where(lo, ws, F32(0.0))
    w[~good] = 0.0
    return w.astype(F32)


# ---------------------------------------------------------------- panel
class Panel:
    def __init__(self):
        z = np.load(os.path.join(CACHE, "panel.npz"), allow_pickle=False)
        dates = z["dates"].astype(str); syms = z["syms"].astype(str)
        O = z["O"]; H = z["H"]; L = z["L"]; C = z["C"]; V = z["V"]; DIV = z["DIV"]
        z.close(); del z

        dv = (C * V).astype(F32)
        adv = roll_geomean(np.where(np.isfinite(dv), dv, 0.0), 20)
        nval = roll_mean(np.isfinite(C).astype(F32), 260, minobs=1)
        prelim = np.isfinite(C) & (C >= MIN_PX) & (adv >= MIN_ADV) & (nval >= 200.0 / 260.0)
        keep = prelim.sum(axis=0) >= 60
        print(f"  column subset: {keep.sum()} / {len(syms)}", flush=True)
        syms = syms[keep]
        O = O[:, keep]; H = H[:, keep]; L = L[:, keep]
        C = C[:, keep]; V = V[:, keep]; DIV = DIV[:, keep]
        dv = dv[:, keep]; adv = adv[:, keep]
        prelim = prelim[:, keep]
        gc.collect()

        self.dates, self.syms = dates, syms
        self.O, self.H, self.L, self.C, self.V, self.DIV = O, H, L, C, V, DIV
        self.dv, self.adv = dv, adv
        self.T, self.N = C.shape

        Cp = lag(C, 1)
        rc = ((C + DIV) / Cp - 1.0).astype(F32)
        rco = (C / O - 1.0).astype(F32)
        roc = ((O + DIV) / Cp - 1.0).astype(F32)
        for a in (rc, rco, roc):
            a[~np.isfinite(a)] = np.nan
        rc[np.abs(rc) > 1.5] = np.nan
        rco[np.abs(rco) > 1.0] = np.nan
        roc[np.abs(roc) > 1.0] = np.nan
        self.rc, self.rco, self.roc, self.Cp = rc, rco, roc, Cp

        Onx = np.full_like(O, np.nan); Onx[:-1] = O[1:]
        Dnx = np.full_like(DIV, np.nan); Dnx[:-1] = DIV[1:]
        roo = ((Onx + Dnx) / O - 1.0).astype(F32)
        roo[~np.isfinite(roo)] = np.nan
        roo[np.abs(roo) > 1.0] = np.nan
        self.roo = roo
        del Onx, Dnx

        self.elig = (prelim & np.isfinite(rc) & np.isfinite(O) & np.isfinite(roo))

        # market factor + beta/residual
        rr = np.where(self.elig, np.nan_to_num(rc), 0.0)
        cnt = self.elig.sum(axis=1)
        mkt = np.where(cnt > 0, rr.sum(axis=1) / np.maximum(cnt, 1), 0.0).astype(F32)
        del rr
        self.mkt = mkt
        m = np.broadcast_to(mkt[:, None], C.shape)
        rcf = np.where(self.elig, rc, np.nan).astype(F32)
        cov = roll_mean(rcf * m, 60) - roll_mean(rcf, 60) * roll_mean(m, 60)
        var = roll_mean((m * m).astype(F32), 60) - roll_mean(m, 60) ** 2
        self.beta = np.clip(cov / np.maximum(var, 1e-12), -3.0, 5.0).astype(F32)
        del cov, var
        self.resid = (rcf - self.beta * m).astype(F32)
        self.sig20 = roll_std(rcf, 20)
        self.isig20 = roll_std(self.resid, 20)
        self.atr20 = roll_mean(((H - L) / np.maximum(Cp, 1e-6)).astype(F32), 20)
        del rcf
        gc.collect()

        self.hs = self._cs_halfspread()
        gc.collect()

    def _cs_halfspread(self):
        H, L, C = self.H, self.L, self.C
        Hp, Lp = lag(H, 1), lag(L, 1)
        h2 = np.fmax(H, Hp); l2 = np.fmin(L, Lp)
        with np.errstate(invalid="ignore", divide="ignore"):
            b = (np.log(H / L) ** 2 + np.log(Hp / Lp) ** 2).astype(np.float64)
            g = (np.log(h2 / l2) ** 2).astype(np.float64)
            k = 3.0 - 2.0 * math.sqrt(2.0)
            a = (math.sqrt(2.0) * np.sqrt(b) - np.sqrt(b)) / k - np.sqrt(g / k)
            s = 2.0 * (np.exp(a) - 1.0) / (1.0 + np.exp(a))
        del b, g, a, Hp, Lp, h2, l2
        s = np.where(np.isfinite(s), s, np.nan)
        s = np.clip(s, 0.0, 0.02).astype(F32)
        half = roll_mean(s, 20) / 2.0
        del s
        # Corwin-Schultz is known to overstate the level badly (universe mean came
        # out at 26bp for a $20M+ ADV universe, which is not credible). We keep its
        # CROSS-SECTIONAL SHAPE and anchor the LEVEL so the eligible-universe mean
        # equals TARGET_MEAN_HS, a realistic effective half-spread for this
        # liquidity tier. Level is then stress-tested separately.
        mu = float(np.nanmean(np.where(self.elig, half, np.nan)))
        scale = TARGET_MEAN_HS / mu if (np.isfinite(mu) and mu > 0) else 1.0
        floor = np.maximum(0.5e-4, 0.0025 / np.maximum(C, 1e-6)).astype(F32)
        floor = np.where(np.isfinite(floor), floor, 0.5e-4).astype(F32)
        out = np.where(np.isfinite(half), half * scale, floor).astype(F32)
        out = np.clip(out, floor, 0.004).astype(F32)
        out[~np.isfinite(out)] = F32(0.004)
        self.cs_raw_mean_bps = mu * 1e4
        self.hs_scale = scale
        return out


# ---------------------------------------------------------------- mechanisms
LIQ = ("Non-informational demand shocks (index/flow/retail impatience) push price "
       "away from value; whoever absorbs the shock is paid when it reverts.")
LEV = ("Leverage-constrained investors express views by buying high-beta/high-vol "
       "names instead of levering, so they systematically overpay for risk.")
ILQ = ("Holding hard-to-exit inventory is a real cost, so illiquid names must offer "
       "a return premium to be held at all.")
LOT = ("Retail lottery preference bids up names with a recent jackpot payoff or "
       "right-skewed payoff shape, leaving them overpriced.")
UND = ("Information diffuses slowly across a fragmented investor base, leaving a "
       "short window in which a move is not yet fully priced.")
MMI = ("FINRA-reported short volume is dominated by market makers shorting to fill "
       "retail buy orders; a short-volume spike marks MM inventory that must be "
       "unwound, and the pressure that created it reverts.")
COND = ("Same liquidity-provision mechanism as REV1, restricted to the sub-universe "
        "where the friction that creates it should be largest.")


def build_signals(P):
    """(name, family, mechanism, signal). Higher signal == LONG. Signs are
    declared from the mechanism, never fitted."""
    C, O, H, L = P.C, P.O, P.H, P.L
    rc, rco, roc, dv, elig = P.rc, P.rco, P.roc, P.dv, P.elig
    S = []
    a = lambda n, f, m, s: S.append((n, f, m, s.astype(F32)))
    cum = lambda k: (C / lag(C, k) - 1.0).astype(F32)

    amih = roll_mean((np.abs(rc) / np.maximum(dv, 1.0) * 1e9).astype(F32), 20)
    lamih = np.log(np.maximum(amih, 1e-9)).astype(F32)
    advg = roll_geomean(np.where(np.isfinite(dv), dv, 0.0), 20)
    vshock = (np.log(np.maximum(dv, 1.0)) - np.log(np.maximum(advg, 1.0))).astype(F32)

    # ---- reversal ----
    a("REV1", "reversal", LIQ, -rc)
    a("REV2", "reversal", LIQ, -cum(2))
    a("REV5", "reversal", LIQ, -cum(5))
    a("REV10", "reversal", LIQ, -cum(10))
    a("REV1_RESID", "reversal", LIQ, -P.resid)
    a("REV5_RESID", "reversal", LIQ, -roll_mean(P.resid, 5) * 5.0)
    a("REV1_STD", "reversal", LIQ, -rc / np.maximum(P.sig20, 1e-4))
    a("REV5_STD", "reversal", LIQ, -cum(5) / np.maximum(P.sig20 * math.sqrt(5), 1e-4))
    a("REV_INTRA", "reversal", LIQ, -rco)
    a("REV_ON", "reversal", LIQ, -roc)
    a("REV1_LAG1", "reversal", LIQ, -lag(rc, 1))
    a("CLOSE_LOC", "reversal", LIQ, -(C - L) / np.maximum(H - L, 1e-6))
    a("RANGE_SHOCK_REV", "reversal", LIQ,
      -np.sign(np.nan_to_num(rc)) * ((H - L) / np.maximum(P.Cp, 1e-6)) / np.maximum(P.atr20, 1e-4)
      * np.where(np.isfinite(rc), 1.0, np.nan))
    a("REV1_x_ILLIQ", "reversal", LIQ, -rc * xs_rank(lamih, elig))
    a("REV1_x_VOLSHOCK", "reversal", LIQ, -rc * np.maximum(vshock, 0.0))
    a("REV1_x_SIG", "reversal", LIQ, -rc * xs_rank(P.sig20, elig))
    a("REV_ON_INTRA_SPREAD", "reversal", LIQ, (rco - roc))

    # ---- illiquidity ----
    a("AMIHUD", "illiq", ILQ, lamih)
    a("SIZE_ILLIQ", "illiq", ILQ, -np.log(np.maximum(advg, 1.0)))
    a("ZERORET", "illiq", ILQ, roll_mean((np.abs(rc) < 1e-6).astype(F32), 20)
      * np.where(np.isfinite(rc), 1.0, np.nan))
    a("DV_SHOCK_REV", "illiq", LIQ, -vshock)
    a("DV_TREND_REV", "illiq", LIQ, -(roll_mean(np.log(np.maximum(dv, 1.0)).astype(F32), 5)
                                      - np.log(np.maximum(advg, 1.0))).astype(F32))

    # ---- vol / beta / lottery ----
    a("LOWVOL", "vol", LEV, -P.sig20)
    a("LOWIVOL", "vol", LEV, -P.isig20)
    a("LOWBETA", "vol", LEV, -P.beta)
    a("LOW_VOV", "vol", LEV, -roll_std(P.sig20, 60))
    a("LOWMAX", "vol", LOT, -roll_max(rc, 20))
    m1 = roll_mean(rc, 20); s20 = np.maximum(P.sig20, 1e-6)
    m3 = roll_mean((rc.astype(np.float64) ** 3).astype(F32), 20)
    sk = ((m3 - 3.0 * m1 * s20 ** 2 - m1 ** 3) / (s20 ** 3)).astype(F32)
    a("LOWSKEW", "vol", LOT, -sk)
    a("LOWRANGE", "vol", LEV, -P.atr20)

    # ---- momentum ----
    a("MOM20_SKIP1", "mom", UND, (lag(C, 1) / lag(C, 21) - 1.0).astype(F32))
    a("MOM5_SKIP1", "mom", UND, (lag(C, 1) / lag(C, 6) - 1.0).astype(F32))
    a("MOM20_RESID", "mom", UND, roll_mean(lag(P.resid, 1), 20) * 20.0)
    a("HI52", "mom", UND, (C / np.maximum(roll_max(C, 252), 1e-6)).astype(F32))
    a("MOM_INTRA5", "mom", UND, roll_mean(rco, 5) * 5.0)

    cond = [
        ("REV1_HIVOL_UNIV", -rc, P.sig20, "hi"),
        ("REV1_HIILLIQ_UNIV", -rc, lamih, "hi"),
        ("REV1_VOLSHOCK_UNIV", -rc, vshock, "hi"),
        ("REV1_QUIET_UNIV", -rc, vshock, "lo"),
        ("REV1_LOWPX_UNIV", -rc, -C, "hi"),
    ]
    return S, cond


def regsho_signals(P):
    p = os.path.join(CACHE, "regsho.npz")
    if not os.path.exists(p):
        print("  (no regsho cache)", flush=True)
        return []
    z = np.load(p)
    SV = z["SV"]; TV = z["TV"]; z.close()
    # panel.npz column subset must be reapplied: regsho was built on full syms
    full = np.load(os.path.join(CACHE, "panel.npz"), allow_pickle=False)
    allsyms = full["syms"].astype(str); full.close()
    pos = {s: i for i, s in enumerate(allsyms)}
    idx = np.array([pos[s] for s in P.syms])
    SV = SV[:, idx]; TV = TV[:, idx]
    with np.errstate(invalid="ignore", divide="ignore"):
        svr = np.where(TV > 0, SV / TV, np.nan).astype(F32)
    del SV, TV
    svr[(svr <= 0) | (svr >= 1)] = np.nan
    svr20 = roll_mean(svr, 20)
    svr5 = roll_mean(svr, 5)
    out = [
        ("SVR_LEVEL", "regsho", MMI, (-svr20).astype(F32)),
        ("SVR_SHOCK", "regsho", MMI, (-(svr - svr20)).astype(F32)),
        ("SVR_TREND", "regsho", MMI, (-(svr5 - svr20)).astype(F32)),
        ("SVR_x_REV", "regsho", MMI,
         (-P.rc * np.maximum(svr - svr20, 0.0) * 20.0).astype(F32)),
        ("SVR_DISP", "regsho", MMI, (-roll_std(svr, 20)).astype(F32)),
    ]
    return out


# ---------------------------------------------------------------- backtest
def run_book(P, w_raw, h, extra_lag=0, flat_cost=None):
    T, N = w_raw.shape
    book = np.zeros((T, N), F32)
    for k in range(h):
        s = 1 + extra_lag + k
        book[s:] += w_raw[: T - s]
    book /= F32(h)
    prev = np.zeros((T, N), F32); prev[1:] = book[:-1]
    dw = np.abs(book - prev)
    r = np.where(np.isfinite(P.roo), P.roo, F32(0.0))
    gross = (book.astype(np.float64) * r).sum(axis=1)
    cvec = (P.hs + FEE) if flat_cost is None else F32(flat_cost + FEE)
    cost = (dw.astype(np.float64) * np.nan_to_num(cvec, nan=0.004)).sum(axis=1)
    borrow = np.abs(np.minimum(book, 0)).sum(axis=1).astype(np.float64) * (BORROW_ANNUAL / 252.0)
    turn = dw.sum(axis=1).astype(np.float64)
    del book, prev, dw
    return gross, cost + borrow, turn, borrow


def stats(pnl, mask):
    x = pnl[mask]; x = x[np.isfinite(x)]
    n = len(x)
    if n < 250:
        return dict(n=int(n), sharpe=0.0, t=0.0, mean_bps=0.0)
    mu = float(x.mean()); sd = float(x.std(ddof=1))
    if sd <= 0:
        return dict(n=int(n), sharpe=0.0, t=0.0, mean_bps=0.0)
    return dict(n=int(n), sharpe=mu / sd * math.sqrt(252), t=mu / sd * math.sqrt(n),
                mean_bps=mu * 1e4)


def wmask(P, w):
    return (P.dates >= w[0]) & (P.dates <= w[1])


def weights_for(P, spec):
    kind = spec[0]
    if kind == "plain":
        _, name, sig = spec
        return decile_weights(xs_rank(sig, P.elig))
    _, name, sig, cvar, side = spec
    crk = xs_rank(cvar, P.elig)
    sub = P.elig & np.isfinite(crk) & ((crk >= 2.0 / 3.0) if side == "hi" else (crk <= 1.0 / 3.0))
    return decile_weights(xs_rank(sig, sub), cnt_min=20)


_SPEC_CACHE = {}


def all_specs(P):
    if id(P) in _SPEC_CACHE:
        return _SPEC_CACHE[id(P)]
    S, cond = build_signals(P)
    S = S + regsho_signals(P)
    specs = []
    for (n, f, m, s) in S:
        specs.append((n, f, m, ("plain", n, s)))
    for (n, s, cv, side) in cond:
        specs.append((n, "reversal_cond", COND, ("cond", n, s, cv, side)))
    _SPEC_CACHE[id(P)] = specs
    return specs


def sweep(P, window, extra_lag=0):
    mask = wmask(P, window)
    rows = []
    specs = all_specs(P)
    for i, (name, fam, mech, spec) in enumerate(specs):
        w = weights_for(P, spec)
        for h in HORIZONS:
            g, c, t, b = run_book(P, w, h, extra_lag=extra_lag)
            sg = stats(g, mask); sn = stats(g - c, mask)
            flat = {}
            for fc in STRESS_FLAT:
                flat[f"net_sharpe_flat{int(fc*1e4)}bp"] = stats(
                    g - (t * (fc + FEE) + b), mask)["sharpe"]
            # break-even one-way cost in bp: gross mean / mean turnover
            gm = float(np.nanmean(g[mask])); tm = float(np.nanmean(t[mask]))
            be = (gm / tm * 1e4) if tm > 0 else 0.0
            rows.append(dict(name=name, family=fam, mechanism=mech, h=h,
                             gross_sharpe=sg["sharpe"], net_sharpe=sn["sharpe"],
                             net_t=sn["t"], net_bps=sn["mean_bps"], gross_bps=sg["mean_bps"],
                             gross_t=sg["t"], breakeven_cost_bps=be,
                             turnover=tm, n=sn["n"], **flat))
        del w
        if i % 10 == 0:
            print(f"  spec {i}/{len(specs)} {name}", flush=True)
        gc.collect()
    return rows


def lag_kill_one(P, name, h, window):
    mask = wmask(P, window)
    for (nm, fam, mech, spec) in all_specs(P):
        if nm != name:
            continue
        w = weights_for(P, spec)
        out = {}
        for el in (0, 1, 2):
            g, c, _t, _b = run_book(P, w, h, extra_lag=el)
            out[f"lag{el}"] = dict(net=stats(g - c, mask), gross=stats(g, mask))
        return out
    return None


# ---------------------------------------------------------------- selftest
def selftest(P):
    rng = np.random.default_rng(7)
    mask = wmask(P, DESIGN)
    # the book formed on sig[t] earns roo[t+1]; plant THAT return, not roo[t]
    fwd = np.full_like(P.roo, np.nan); fwd[:-1] = P.roo[1:]
    fwd = np.where(np.isfinite(fwd), fwd, 0.0).astype(F32)
    noise = rng.standard_normal(P.C.shape).astype(F32)
    planted = (fwd * 100.0 + noise * 0.5).astype(F32)
    out = {}
    for tag, sig in (("planted", planted), ("planted_signflip", -planted), ("pure_noise", noise)):
        w = decile_weights(xs_rank(sig, P.elig))
        g, c, t, _b = run_book(P, w, 1)
        out[tag] = dict(gross=stats(g, mask), net=stats(g - c, mask),
                        turnover=float(np.nanmean(t[mask])))
    # cost sanity
    # a signal that predicts roo[t] (NOT roo[t+1]) must NOT look like alpha:
    stale = np.where(np.isfinite(P.roo), P.roo, 0.0).astype(F32)
    w = decile_weights(xs_rank(stale, P.elig))
    g, c, _t, _b = run_book(P, w, 1)
    out["lookahead_control_roo_t"] = dict(gross=stats(g, mask))
    out["mean_half_spread_bps_eligible"] = float(
        np.nanmean(np.where(P.elig, P.hs, np.nan)) * 1e4)
    out["corwin_schultz_raw_mean_bps"] = float(P.cs_raw_mean_bps)
    out["hs_anchor_scale"] = float(P.hs_scale)
    out["median_eligible_per_day"] = float(np.median(P.elig.sum(axis=1)[mask]))
    return out


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "design"
    print("loading panel...", flush=True)
    P = Panel()
    print(f"panel {P.T}x{P.N}; median eligible/day {np.median(P.elig.sum(axis=1)):.0f}",
          flush=True)

    if mode == "selftest":
        st = selftest(P)
        json.dump(st, open(os.path.join(RES, "NEWTERR_xs_equity_SELFTEST.json"), "w"),
                  indent=2, default=float)
        print(json.dumps(st, indent=2, default=float))
        return

    if mode == "design":
        rows = sweep(P, DESIGN)
        Nf = len(rows)
        bar = math.sqrt(2 * math.log(Nf))
        rows.sort(key=lambda r: -r["net_t"])
        lk = {}
        for r in rows[:10]:
            lk[f"{r['name']}_h{r['h']}"] = lag_kill_one(P, r["name"], r["h"], DESIGN)
        picks = []
        for r in rows:
            if r["net_t"] < bar:
                continue
            k = f"{r['name']}_h{r['h']}"
            info = lk.get(k) or lag_kill_one(P, r["name"], r["h"], DESIGN)
            lk[k] = info
            a, b = info["lag0"]["gross"]["sharpe"], info["lag1"]["gross"]["sharpe"]
            picks.append(dict(r, lag_kill=info, lag_survived=bool(b > 0 and b > 0.5 * a)))
        gsurv = sorted([r for r in rows if r["gross_t"] >= bar], key=lambda r: -r["gross_t"])
        for r in gsurv[:12]:
            k = f"{r['name']}_h{r['h']}"
            if k not in lk:
                lk[k] = lag_kill_one(P, r["name"], r["h"], DESIGN)
        out = dict(window=DESIGN, n_formulas_tested=Nf, null_bar_t=bar,
                   design_days=rows[0]["n"] if rows else 0,
                   cost_model=dict(target_mean_half_spread_bps=TARGET_MEAN_HS * 1e4,
                                   fee_bps=FEE * 1e4, borrow_annual=BORROW_ANNUAL),
                   rows=rows, lag_kill=lk, frozen_picks=picks,
                   gross_survivors=[dict(r, lag_kill=lk.get(f"{r['name']}_h{r['h']}"))
                                    for r in gsurv])
        json.dump(out, open(os.path.join(RES, "NEWTERR_xs_equity_DESIGN.json"), "w"),
                  indent=2, default=float)
        print(f"\nN={Nf} null_bar_t={bar:.2f} "
              f"(design yrs={rows[0]['n']/252:.1f} -> SR bar {bar/math.sqrt(rows[0]['n']/252):.2f})")
        for r in rows[:25]:
            print(f"  {r['name']:22s} h={r['h']} gS={r['gross_sharpe']:6.2f} nS={r['net_sharpe']:6.2f} "
                  f"t={r['net_t']:6.2f} turn={r['turnover']:.2f} "
                  f"gbps={r['gross_bps']:6.2f} nbps={r['net_bps']:6.2f} "
                  f"be={r['breakeven_cost_bps']:5.2f}bp f10={r['net_sharpe_flat10bp']:6.2f}")
        print("\nworst 5:")
        for r in rows[-5:]:
            print(f"  {r['name']:22s} h={r['h']} nS={r['net_sharpe']:6.2f} t={r['net_t']:6.2f}")
        print("\ntop 12 by GROSS t (pre-cost, diagnostic only):")
        for r in sorted(rows, key=lambda r: -r["gross_t"])[:12]:
            info = lk.get(f"{r['name']}_h{r['h']}")
            lg = (f" lag0gS={info['lag0']['gross']['sharpe']:.2f}"
                  f" lag1gS={info['lag1']['gross']['sharpe']:.2f}"
                  f" lag2gS={info['lag2']['gross']['sharpe']:.2f}") if info else ""
            print(f"  {r['name']:22s} h={r['h']} gS={r['gross_sharpe']:6.2f} gt={r['gross_t']:6.2f}"
                  f" be={r['breakeven_cost_bps']:5.2f}bp{lg}")
        print(f"\nfrozen picks ({len(picks)}): "
              f"{[p['name']+'_h'+str(p['h']) for p in picks]}")
        return

    if mode == "holdout":
        dz = json.load(open(os.path.join(RES, "NEWTERR_xs_equity_DESIGN.json")))
        rows = sweep(P, HOLDOUT)
        by = {f"{r['name']}_h{r['h']}": r for r in rows}
        res = []
        for p in dz["frozen_picks"]:
            k = f"{p['name']}_h{p['h']}"
            res.append(dict(name=p["name"], h=p["h"],
                            design_net_sharpe=p["net_sharpe"], design_net_t=p["net_t"],
                            heldout=by.get(k),
                            heldout_lag_kill=lag_kill_one(P, p["name"], p["h"], HOLDOUT)))
        json.dump(dict(window=HOLDOUT, picks=res, all_rows=rows),
                  open(os.path.join(RES, "NEWTERR_xs_equity_HOLDOUT.json"), "w"),
                  indent=2, default=float)
        for r in res:
            ho = r["heldout"] or {}
            print(f"  {r['name']:22s} h={r['h']} design_nS={r['design_net_sharpe']:6.2f} "
                  f"-> heldout_nS={ho.get('net_sharpe',0):6.2f} t={ho.get('net_t',0):6.2f} "
                  f"nbps={ho.get('net_bps',0):6.2f}")
        return


if __name__ == "__main__":
    main()
