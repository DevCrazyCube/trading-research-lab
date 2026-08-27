#!/usr/bin/env python3
"""
INVENT D0821 -- theme: CROSS-SECTIONAL equity factor signals, fresh structures.

Builds on the validated NEWTERR xs_equity engine (same panel, same universe,
same open-to-open fills, same cost model, same self-test harness) but with
STRUCTURALLY NEW signals that the 132-cell NEWTERR sweep did not contain:

  * statistical-SECTOR neutralisation (data-driven correlation clusters, PIT)
  * MULTI-FACTOR cross-sectional residual (beta+size+vol+cluster dummies)
  * PAIRWISE peer-basket divergence (top-K correlated peers, PIT, hedged + z)
  * BETA-shape features (down-minus-up beta, beta instability, idio share)
  * fresh LIQUIDITY-PROVISION forms (size-neutral Amihud, Amihud change,
    spread level, Amivest/sqrt-dollar-volume impact)

NOT included, by instruction: any regime gate / conditioner / sub-universe
restriction (round-3 meta-result: gating is noise and harmful, 0/107).

Usage:
  python3 invent_d0821_xsfactor.py selftest
  python3 invent_d0821_xsfactor.py design
  python3 invent_d0821_xsfactor.py holdout
"""
import json, os, sys, math, gc
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from newterr_xseq_sweep import (  # noqa: E402
    Panel, xs_rank, decile_weights, run_book, stats, wmask,
    roll_mean, roll_std, roll_geomean, lag,
    DESIGN, HOLDOUT, HORIZONS, F32, FEE, STRESS_FLAT, DECILE,
)

RES = "/home/anont/meme/research/trading_bot"
TAG = "INVENT_D0821_xsfactor"

LOOKBACK = 250      # trailing days used to fit clusters / peers / hedge betas
STEP = 63           # refresh cadence (quarterly), strictly point-in-time
NCLUST = 15         # statistical "sectors"
NPC = 10            # PCs used as clustering features
PEERK = 10          # peers per name


# ------------------------------------------------------------------ mechanisms
LIQ = ("Non-informational demand shocks push a name away from its peers; whoever "
       "absorbs the shock is paid when the relative dislocation reverts.")
UND = ("Sector/peer-relative information diffuses slowly across a fragmented "
       "investor base, leaving a window in which a relative move is not yet priced.")
SECP = ("Sector-level flow (ETF creates, rotation) moves a whole cluster together; "
        "the cluster-level push is non-informational and reverts.")
HEDG = ("A name whose factor exposure is unstable or whose risk is unhedgeable "
        "cannot be warehoused cheaply, so it must be paid a premium to be held.")
CRSH = ("Assets that fall harder than they rise in market drawdowns are poor "
        "hedges and must trade at a discount, i.e. earn a premium.")
LEV = ("Leverage-constrained investors express views by buying high-vol names "
       "instead of levering, so they systematically overpay for risk.")
LOT = ("A jump in idiosyncratic volatility attracts lottery-seeking buyers, "
       "leaving the name temporarily overpriced.")
ILQ = ("Holding hard-to-exit inventory is a real cost, so illiquid names must "
       "offer a return premium to be held at all.")
ILQC = ("A deterioration in liquidity raises the inventory cost of holding a name; "
        "the required compensation is repriced with a lag.")


# ------------------------------------------------------------------ PIT groups
class Groups:
    """Point-in-time statistical sectors and correlated-peer sets.

    At each refresh date index t0 we use ONLY returns in [t0-LOOKBACK, t0-1]:
      * SVD of the standardised residual-return matrix -> NPC loadings per name
      * k-means (loadings, whitened) -> NCLUST cluster labels
      * top-PEERK correlation peers per name, from the same window
      * OLS hedge beta of each name on its own peer basket
    Labels/peers apply to days [t0, t0+STEP).
    """

    def __init__(self, P):
        T, N = P.C.shape
        self.T, self.N = T, N
        rc = P.rc
        elig = P.elig

        starts = list(range(LOOKBACK + 5, T, STEP))
        self.starts = starts
        nper = len(starts)
        self.lab = np.full((nper, N), -1, np.int16)
        self.peers = np.full((nper, N, PEERK), -1, np.int32)
        self.hbeta = np.full((nper, N), np.nan, F32)
        self.pcorr = np.full((nper, N), np.nan, F32)
        self.day_period = np.full(T, -1, np.int32)
        for p, t0 in enumerate(starts):
            t1 = min(t0 + STEP, T)
            self.day_period[t0:t1] = p

        rng = np.random.default_rng(11)
        for p, t0 in enumerate(starts):
            lo = t0 - LOOKBACK
            R = rc[lo:t0]                      # (L, N)
            E = elig[lo:t0]
            ok = (np.isfinite(R) & E).sum(axis=0) >= int(0.8 * LOOKBACK)
            idx = np.flatnonzero(ok)
            if len(idx) < 100:
                continue
            X = np.where(np.isfinite(R[:, idx]), R[:, idx], 0.0).astype(np.float64)
            X -= X.mean(axis=0, keepdims=True)
            sd = X.std(axis=0, ddof=1)
            sd[sd <= 0] = 1.0
            X /= sd                            # (L, n) standardised
            # --- PCA loadings via SVD on the (L x n) matrix
            k = min(NPC, min(X.shape) - 1)
            # economical: eigendecomp of the LxL gram (L=250 << n)
            G = X @ X.T / max(len(idx) - 1, 1)
            w, V = np.linalg.eigh(G)
            order = np.argsort(w)[::-1][:k]
            F = V[:, order]                    # (L, k) factor time series
            load = (X.T @ F) / max(len(X) - 1, 1)   # (n, k) loadings
            ls = load.std(axis=0)
            ls[ls <= 0] = 1.0
            Z = load / ls
            self.lab[p, idx] = _kmeans(Z, NCLUST, rng)
            # --- correlation peers (corr of standardised returns)
            Cm = (X.T @ X) / max(len(X) - 1, 1)     # (n, n) correlation
            np.fill_diagonal(Cm, -9.0)
            pk = min(PEERK, len(idx) - 1)
            top = np.argpartition(-Cm, pk - 1, axis=1)[:, :pk]     # (n, pk)
            rows = np.arange(len(idx))[:, None]
            cvals = Cm[rows, top]
            srt = np.argsort(-cvals, axis=1)
            top = top[rows, srt]
            self.peers[p, idx, :pk] = idx[top]
            self.pcorr[p, idx] = cvals[rows, srt].mean(axis=1).astype(F32)
            # --- hedge beta on the equal-weight peer basket (raw return space)
            Rr = np.where(np.isfinite(R[:, idx]), R[:, idx], np.nan)
            PB = np.nanmean(Rr[:, top], axis=2)      # (L, n) peer basket return
            a = Rr - np.nanmean(Rr, axis=0, keepdims=True)
            b = PB - np.nanmean(PB, axis=0, keepdims=True)
            m = np.isfinite(a) & np.isfinite(b)
            a = np.where(m, a, 0.0); b = np.where(m, b, 0.0)
            num = (a * b).sum(axis=0)
            den = (b * b).sum(axis=0)
            hb = np.where(den > 0, num / np.maximum(den, 1e-12), 1.0)
            self.hbeta[p, idx] = np.clip(hb, -1.0, 3.0).astype(F32)
            del X, G, V, F, load, Z, Cm, Rr, PB, a, b, m
            gc.collect()
        print(f"  groups: {nper} periods, "
              f"median labelled/period {np.median((self.lab >= 0).sum(axis=1)):.0f}",
              flush=True)

    # ---- daily expansions
    def cluster_return(self, P):
        """clu[t,i] = equal-weight return of i's cluster on day t (excl. nothing)."""
        T, N = self.T, self.N
        out = np.full((T, N), np.nan, F32)
        rc = P.rc
        for p, t0 in enumerate(self.starts):
            t1 = min(t0 + STEP, T)
            L = self.lab[p]
            has = L >= 0
            if not has.any():
                continue
            M = np.zeros((N, NCLUST), F32)
            M[np.flatnonzero(has), L[has]] = 1.0
            R = rc[t0:t1]
            v = np.isfinite(R).astype(F32)
            S = np.nan_to_num(R) * v
            cs = S @ M
            cn = v @ M
            cm = np.where(cn >= 3, cs / np.maximum(cn, 1.0), np.nan)
            blk = np.full((t1 - t0, N), np.nan, F32)
            blk[:, has] = cm[:, L[has]]
            out[t0:t1] = blk
        return out

    def peer_return(self, P):
        """pr[t,i] = equal-weight return of i's top-K correlated peers on day t."""
        T, N = self.T, self.N
        out = np.full((T, N), np.nan, F32)
        rc = P.rc
        for p, t0 in enumerate(self.starts):
            t1 = min(t0 + STEP, T)
            pk = self.peers[p]
            has = (pk[:, 0] >= 0)
            if not has.any():
                continue
            idx = np.flatnonzero(has)
            sub = pk[idx]                     # (n, K)
            sub = np.where(sub >= 0, sub, 0)
            R = rc[t0:t1]
            g = R[:, sub]                     # (days, n, K)
            with np.errstate(invalid="ignore"):
                pm = np.nanmean(g, axis=2)
            out[t0:t1, idx] = pm.astype(F32)
            del g, pm
        return out

    def daily(self, arr):
        """expand a per-period (nper, N) array to (T, N)."""
        T, N = self.T, self.N
        out = np.full((T, N), np.nan, F32)
        for p, t0 in enumerate(self.starts):
            t1 = min(t0 + STEP, T)
            out[t0:t1] = arr[p][None, :]
        return out


def _kmeans(Z, K, rng, iters=25):
    n = len(Z)
    K = min(K, max(2, n // 20))
    c = Z[rng.choice(n, K, replace=False)].copy()
    lab = np.zeros(n, np.int16)
    for _ in range(iters):
        d = ((Z[:, None, :] - c[None, :, :]) ** 2).sum(axis=2)
        nl = np.argmin(d, axis=1).astype(np.int16)
        if (nl == lab).all():
            break
        lab = nl
        for k in range(K):
            m = lab == k
            if m.any():
                c[k] = Z[m].mean(axis=0)
            else:
                c[k] = Z[rng.integers(n)]
    return lab


# ------------------------------------------------------------------ helpers
def xs_z(x, elig):
    """cross-sectional z of the RANK (robust, outlier-proof), NaN outside elig."""
    r = xs_rank(x, elig)
    return ((r - 0.5) * math.sqrt(12.0)).astype(F32)


def xs_resid(y, X, elig):
    """Daily cross-sectional OLS residual of y on columns of X (list of (T,N))."""
    T, N = y.shape
    cols = [np.ones((T, N), F32)] + list(X)
    k = len(cols)
    ok = elig & np.isfinite(y)
    for c in cols:
        ok &= np.isfinite(c)
    Y = np.where(ok, y, 0.0).astype(np.float64)
    Cs = [np.where(ok, c, 0.0).astype(np.float64) for c in cols]
    out = np.full((T, N), np.nan, F32)
    XtX = np.empty((T, k, k))
    XtY = np.empty((T, k))
    for i in range(k):
        XtY[:, i] = (Cs[i] * Y).sum(axis=1)
        for j in range(i, k):
            v = (Cs[i] * Cs[j]).sum(axis=1)
            XtX[:, i, j] = v
            XtX[:, j, i] = v
    eye = np.eye(k)[None, :, :] * 1e-8
    try:
        beta = np.linalg.solve(XtX + eye, XtY[:, :, None])[:, :, 0]
    except np.linalg.LinAlgError:
        beta = np.zeros((T, k))
    fit = np.zeros((T, N))
    for i in range(k):
        fit += beta[:, i][:, None] * Cs[i]
    res = np.where(ok, Y - fit, np.nan)
    out[:] = res.astype(F32)
    del Y, Cs, fit, res
    gc.collect()
    return out


def cumret(C, k):
    return (C / lag(C, k) - 1.0).astype(F32)


def run_book2(P, w_raw, h, extra_lag=0):
    """Identical to newterr_xseq_sweep.run_book but ALSO returns a per-day
    'active' flag (book has non-zero gross notional). Signals that need a
    250d group-fitting warm-up would otherwise be silently penalised by
    leading all-zero P&L days inside the design window."""
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
    cvec = (P.hs + FEE)
    cost = (dw.astype(np.float64) * np.nan_to_num(cvec, nan=0.004)).sum(axis=1)
    borrow = np.abs(np.minimum(book, 0)).sum(axis=1).astype(np.float64) * (0.005 / 252.0)
    turn = dw.sum(axis=1).astype(np.float64)
    act = np.abs(book).sum(axis=1) > 1e-6
    del book, prev, dw
    return gross, cost + borrow, turn, borrow, act


# ------------------------------------------------------------------ signals
def build_signals(P, G):
    """(name, family, mechanism, signal). Higher signal == LONG.
    Every sign is declared from the mechanism before the run."""
    C, elig, rc, dv = P.C, P.elig, P.rc, P.dv
    S = []
    a = lambda n, f, m, s: S.append((n, f, m, np.asarray(s, F32)))

    print("  expanding clusters/peers...", flush=True)
    clu = G.cluster_return(P)          # cluster daily return per member
    pr = G.peer_return(P)              # peer-basket daily return per name
    hb = G.daily(G.hbeta)
    pc = G.daily(G.pcorr)
    gc.collect()

    dsec = (rc - clu).astype(F32)      # sector-relative daily return
    dpee = (rc - pr).astype(F32)       # peer-relative daily return
    dhed = (rc - hb * pr).astype(F32)  # beta-hedged peer-relative daily return

    sd_sec20 = roll_std(dsec, 20)
    sd_pee20 = roll_std(dpee, 20)

    # ---- 1. statistical-sector neutralisation --------------------------------
    a("SEC_REV1", "sector", LIQ, -dsec)
    a("SEC_REV5", "sector", LIQ, -roll_mean(dsec, 5) * 5.0)
    a("SEC_REV1_Z", "sector", LIQ, -dsec / np.maximum(sd_sec20, 1e-4))
    a("SEC_REV5_Z", "sector", LIQ,
      -(roll_mean(dsec, 5) * 5.0) / np.maximum(sd_sec20 * math.sqrt(5), 1e-4))
    a("SEC_MOM20", "sector", UND, roll_mean(lag(dsec, 1), 20) * 20.0)
    a("CLU_REV1", "sector", SECP, -clu)
    a("CLU_MOM20", "sector", UND, roll_mean(lag(clu, 1), 20) * 20.0)

    # ---- 2. multi-factor cross-sectional residual ----------------------------
    print("  multi-factor XS residual...", flush=True)
    advg = roll_geomean(np.where(np.isfinite(dv), dv, 0.0), 20)
    size = np.log(np.maximum(advg, 1.0)).astype(F32)
    Xf = [xs_z(P.beta, elig), xs_z(size, elig), xs_z(P.sig20, elig),
          xs_z(pc, elig), xs_z(hb, elig)]
    mres = xs_resid(rc, Xf, elig)
    del Xf
    gc.collect()
    sd_m20 = roll_std(mres, 20)
    a("FR_REV1", "mfresid", LIQ, -mres)
    a("FR_REV5", "mfresid", LIQ, -roll_mean(mres, 5) * 5.0)
    a("FR_REV1_Z", "mfresid", LIQ, -mres / np.maximum(sd_m20, 1e-4))
    a("FR_MOM20", "mfresid", UND, roll_mean(lag(mres, 1), 20) * 20.0)

    # ---- 3. pairwise peer-basket divergence ----------------------------------
    a("PEER_DIV1", "peer", LIQ, -dpee)
    a("PEER_DIV5", "peer", LIQ, -roll_mean(dpee, 5) * 5.0)
    a("PEER_DIV5_Z", "peer", LIQ,
      -(roll_mean(dpee, 5) * 5.0) / np.maximum(sd_pee20 * math.sqrt(5), 1e-4))
    a("PEER_DIV20_Z", "peer", LIQ,
      -(roll_mean(dpee, 20) * 20.0) / np.maximum(sd_pee20 * math.sqrt(20), 1e-4))
    a("PEER_HEDGE_DIV5", "peer", LIQ, -roll_mean(dhed, 5) * 5.0)
    a("PEER_CORR_LOW", "peer", HEDG, -pc)

    # ---- 4. beta shape / risk-warehousing ------------------------------------
    print("  beta shape...", flush=True)
    m = np.broadcast_to(P.mkt[:, None], C.shape).astype(F32)
    rcf = np.where(elig, rc, np.nan).astype(F32)
    dn = m < 0
    rd = np.where(dn, rcf, np.nan).astype(F32)
    md = np.where(dn, m, np.nan).astype(F32)
    ru = np.where(~dn, rcf, np.nan).astype(F32)
    mu = np.where(~dn, m, np.nan).astype(F32)
    W = 250

    def cbeta(r_, m_):
        # only ~half the days in the window are up (or down) days, so the
        # default minobs = W//2 would NaN out every cell. 40 conditional
        # observations inside 250 sessions is the floor we require.
        mo = 40
        cov = (roll_mean(r_ * m_, W, minobs=mo)
               - roll_mean(r_, W, minobs=mo) * roll_mean(m_, W, minobs=mo))
        var = roll_mean(m_ * m_, W, minobs=mo) - roll_mean(m_, W, minobs=mo) ** 2
        return np.clip(cov / np.maximum(var, 1e-12), -3.0, 5.0).astype(F32)

    bdn = cbeta(rd, md)
    bup = cbeta(ru, mu)
    del rd, md, ru, mu, dn
    gc.collect()
    a("BETA_DOWN_UP", "betashape", CRSH, (bdn - bup).astype(F32))
    a("BETA_INSTAB", "betashape", HEDG, roll_std(P.beta, 120))
    del bdn, bup
    gc.collect()
    # idiosyncratic SHARE of variance (scale-free, unlike LOWIVOL's level)
    tot = np.maximum(roll_std(rcf, 60), 1e-6)
    idio_share = (roll_std(mres, 60) / tot).astype(F32)
    a("IDIO_SHARE", "betashape", HEDG, idio_share)
    del m, rcf
    gc.collect()

    # ---- 5. idiosyncratic-vol, fresh forms -----------------------------------
    ivol_mf20 = roll_std(mres, 20)
    ivol_mf120 = roll_std(mres, 120)
    a("IVOL_MF_LOW", "ivol", LEV, -ivol_mf20)
    a("IVOL_CHG_LOW", "ivol", LOT,
      -(ivol_mf20 / np.maximum(ivol_mf120, 1e-6) - 1.0).astype(F32))
    a("IVOL_SEC_LOW", "ivol", LEV, -sd_sec20)

    # ---- 6. liquidity provision, fresh forms ---------------------------------
    print("  liquidity forms...", flush=True)
    amih = roll_mean((np.abs(rc) / np.maximum(dv, 1.0) * 1e9).astype(F32), 20)
    lamih = np.log(np.maximum(amih, 1e-9)).astype(F32)
    lamih120 = np.log(np.maximum(
        roll_mean((np.abs(rc) / np.maximum(dv, 1.0) * 1e9).astype(F32), 120), 1e-9)).astype(F32)
    a("AMIHUD_SIZENEUT", "liq", ILQ, xs_resid(lamih, [xs_z(size, elig)], elig))
    a("AMIHUD_CHG", "liq", ILQC, (lamih - lamih120).astype(F32))
    a("SPREAD_LEVEL", "liq", ILQ, np.where(elig, P.hs, np.nan).astype(F32))
    amv = roll_mean((np.abs(rc) / np.sqrt(np.maximum(dv, 1.0)) * 1e4).astype(F32), 20)
    a("SQRT_IMPACT", "liq", ILQ, np.log(np.maximum(amv, 1e-9)).astype(F32))
    a("ILLIQ_VOLNEUT", "liq", ILQ,
      xs_resid(lamih, [xs_z(size, elig), xs_z(P.sig20, elig)], elig))

    del clu, pr, dsec, dpee, dhed, mres, sd_sec20, sd_pee20, sd_m20
    gc.collect()
    return S


# ------------------------------------------------------------------ sweep
def sweep(P, S, window, extra_lag=0):
    mask = wmask(P, window)
    rows = []
    for i, (name, fam, mech, sig) in enumerate(S):
        w = decile_weights(xs_rank(sig, P.elig))
        for h in HORIZONS:
            g, c, t, b, act = run_book2(P, w, h, extra_lag=extra_lag)
            m2 = mask & act
            sg = stats(g, m2)
            sn = stats(g - c, m2)
            flat = {}
            for fc in STRESS_FLAT:
                flat[f"net_sharpe_flat{int(fc*1e4)}bp"] = stats(
                    g - (t * (fc + FEE) + b), m2)["sharpe"]
            gm = float(np.nanmean(g[m2])); tm = float(np.nanmean(t[m2]))
            be = (gm / tm * 1e4) if tm > 0 else 0.0
            rows.append(dict(name=name, family=fam, mechanism=mech, h=h,
                             gross_sharpe=sg["sharpe"], net_sharpe=sn["sharpe"],
                             net_t=sn["t"], net_bps=sn["mean_bps"],
                             gross_bps=sg["mean_bps"], gross_t=sg["t"],
                             breakeven_cost_bps=be, turnover=tm, n=sn["n"], **flat))
        del w
        print(f"  spec {i+1}/{len(S)} {name}", flush=True)
        gc.collect()
    return rows


def lag_kill_one(P, S, name, h, window):
    mask = wmask(P, window)
    for (nm, fam, mech, sig) in S:
        if nm != name:
            continue
        w = decile_weights(xs_rank(sig, P.elig))
        out = {}
        for el in (0, 1, 2):
            g, c, _t, _b, act = run_book2(P, w, h, extra_lag=el)
            m2 = mask & act
            out[f"lag{el}"] = dict(net=stats(g - c, m2), gross=stats(g, m2))
        return out
    return None


def selftest(P, S, G):
    rng = np.random.default_rng(7)
    mask = wmask(P, DESIGN)
    fwd = np.full_like(P.roo, np.nan); fwd[:-1] = P.roo[1:]
    fwd = np.where(np.isfinite(fwd), fwd, 0.0).astype(F32)
    noise = rng.standard_normal(P.C.shape).astype(F32)
    out = {}
    for tag, sig in (("planted", (fwd * 100.0 + noise * 0.5).astype(F32)),
                     ("planted_signflip", -(fwd * 100.0 + noise * 0.5).astype(F32)),
                     ("pure_noise", noise)):
        w = decile_weights(xs_rank(sig, P.elig))
        g, c, t, _b = run_book(P, w, 1)
        out[tag] = dict(gross=stats(g, mask), net=stats(g - c, mask),
                        turnover=float(np.nanmean(t[mask])))
    stale = np.where(np.isfinite(P.roo), P.roo, 0.0).astype(F32)
    w = decile_weights(xs_rank(stale, P.elig))
    g, c, _t, _b = run_book(P, w, 1)
    out["lookahead_control_roo_t"] = dict(gross=stats(g, mask))
    # group sanity
    out["n_signals"] = len(S)
    out["median_eligible_per_day"] = float(np.median(P.elig.sum(axis=1)[mask]))
    out["mean_half_spread_bps_eligible"] = float(
        np.nanmean(np.where(P.elig, P.hs, np.nan)) * 1e4)
    lab = G.lab
    out["cluster_periods"] = int(len(G.starts))
    out["median_labelled_per_period"] = float(np.median((lab >= 0).sum(axis=1)))
    # cluster stability: fraction of pairs co-clustered in consecutive periods
    sameness = []
    for p in range(1, len(G.starts)):
        a, b = lab[p - 1], lab[p]
        m = (a >= 0) & (b >= 0)
        if m.sum() < 50:
            continue
        aa, bb = a[m], b[m]
        s = np.random.default_rng(p).choice(len(aa), size=min(400, len(aa)), replace=False)
        aa, bb = aa[s], bb[s]
        ca = aa[:, None] == aa[None, :]
        cb = bb[:, None] == bb[None, :]
        sameness.append(float((ca == cb).mean()))
    out["cluster_pair_agreement_consecutive"] = float(np.mean(sameness)) if sameness else None
    # per-signal coverage
    cov = {}
    for (nm, _f, _m, sig) in S:
        cov[nm] = float(np.mean(np.isfinite(sig[mask]) & P.elig[mask]))
    out["signal_coverage"] = cov
    return out


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "design"
    print("loading panel...", flush=True)
    P = Panel()
    print(f"panel {P.T}x{P.N}", flush=True)
    print("building PIT groups...", flush=True)
    G = Groups(P)
    S = build_signals(P, G)
    print(f"{len(S)} signals x {len(HORIZONS)} horizons "
          f"= {len(S)*len(HORIZONS)} cells", flush=True)

    if mode == "selftest":
        st = selftest(P, S, G)
        json.dump(st, open(os.path.join(RES, f"{TAG}_SELFTEST.json"), "w"),
                  indent=2, default=float)
        print(json.dumps({k: v for k, v in st.items() if k != "signal_coverage"},
                         indent=2, default=float))
        print("coverage:", json.dumps(st["signal_coverage"], indent=1, default=float))
        return

    if mode == "design":
        rows = sweep(P, S, DESIGN)
        Nf = len(rows)
        bar = math.sqrt(2 * math.log(Nf))
        rows.sort(key=lambda r: -r["net_t"])
        lk = {}
        for r in rows[:8]:
            lk[f"{r['name']}_h{r['h']}"] = lag_kill_one(P, S, r["name"], r["h"], DESIGN)
        picks = []
        for r in rows:
            if r["net_t"] < bar:
                continue
            k = f"{r['name']}_h{r['h']}"
            info = lk.get(k) or lag_kill_one(P, S, r["name"], r["h"], DESIGN)
            lk[k] = info
            a_, b_ = info["lag0"]["gross"]["sharpe"], info["lag1"]["gross"]["sharpe"]
            picks.append(dict(r, lag_kill=info, lag_survived=bool(b_ > 0 and b_ > 0.5 * a_)))
        # information-only: top 5 by design net t, carried to holdout regardless
        info_only = [dict(name=r["name"], h=r["h"], net_t=r["net_t"],
                          net_sharpe=r["net_sharpe"]) for r in rows[:5]]
        gsurv = sorted([r for r in rows if r["gross_t"] >= bar], key=lambda r: -r["gross_t"])
        out = dict(window=DESIGN, n_formulas_tested=Nf, n_signals=len(S),
                   null_bar_t=bar, design_days=rows[0]["n"] if rows else 0,
                   rows=rows, lag_kill=lk, frozen_picks=picks,
                   info_only_top5=info_only,
                   gross_survivors=[dict(r) for r in gsurv])
        json.dump(out, open(os.path.join(RES, f"{TAG}_DESIGN.json"), "w"),
                  indent=2, default=float)
        yrs = rows[0]["n"] / 252 if rows else 1
        print(f"\nN={Nf} null_bar_t={bar:.2f} (design yrs={yrs:.1f} "
              f"-> SR bar {bar/math.sqrt(yrs):.2f})")
        for r in rows[:20]:
            print(f"  {r['name']:18s} h={r['h']} gS={r['gross_sharpe']:6.2f} "
                  f"nS={r['net_sharpe']:6.2f} t={r['net_t']:6.2f} "
                  f"turn={r['turnover']:.2f} gbps={r['gross_bps']:6.2f} "
                  f"be={r['breakeven_cost_bps']:5.2f}bp f10={r['net_sharpe_flat10bp']:6.2f}")
        print("\nworst 5:")
        for r in rows[-5:]:
            print(f"  {r['name']:18s} h={r['h']} nS={r['net_sharpe']:6.2f} t={r['net_t']:6.2f}")
        print("\ntop 8 by GROSS t:")
        for r in sorted(rows, key=lambda r: -r["gross_t"])[:8]:
            info = lk.get(f"{r['name']}_h{r['h']}")
            lg = ""
            if info:
                lg = (f" lag0gS={info['lag0']['gross']['sharpe']:.2f}"
                      f" lag1gS={info['lag1']['gross']['sharpe']:.2f}"
                      f" lag2gS={info['lag2']['gross']['sharpe']:.2f}")
            print(f"  {r['name']:18s} h={r['h']} gS={r['gross_sharpe']:6.2f} "
                  f"gt={r['gross_t']:6.2f} be={r['breakeven_cost_bps']:5.2f}bp{lg}")
        print(f"\nfrozen picks ({len(picks)}): "
              f"{[p['name']+'_h'+str(p['h']) for p in picks]}")
        return

    if mode == "holdout":
        dz = json.load(open(os.path.join(RES, f"{TAG}_DESIGN.json")))
        rows = sweep(P, S, HOLDOUT)
        by = {f"{r['name']}_h{r['h']}": r for r in rows}
        res = []
        carry = list(dz["frozen_picks"]) + [p for p in dz["info_only_top5"]
                                            if not any(q["name"] == p["name"] and q["h"] == p["h"]
                                                       for q in dz["frozen_picks"])]
        for p in carry:
            k = f"{p['name']}_h{p['h']}"
            res.append(dict(name=p["name"], h=p["h"],
                            design_net_sharpe=p["net_sharpe"], design_net_t=p["net_t"],
                            cleared_design_bar=bool(p["net_t"] >= dz["null_bar_t"]),
                            heldout=by.get(k),
                            heldout_lag_kill=lag_kill_one(P, S, p["name"], p["h"], HOLDOUT)))
        json.dump(dict(window=HOLDOUT, picks=res, all_rows=rows,
                       design_bar=dz["null_bar_t"]),
                  open(os.path.join(RES, f"{TAG}_HOLDOUT.json"), "w"),
                  indent=2, default=float)
        for r in res:
            ho = r["heldout"] or {}
            print(f"  {r['name']:18s} h={r['h']} design_nS={r['design_net_sharpe']:6.2f} "
                  f"-> heldout_nS={ho.get('net_sharpe',0):6.2f} "
                  f"t={ho.get('net_t',0):6.2f} nbps={ho.get('net_bps',0):6.2f}")
        return


if __name__ == "__main__":
    main()
