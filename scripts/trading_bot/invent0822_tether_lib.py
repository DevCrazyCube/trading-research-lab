#!/usr/bin/env python3
"""INVENT 0822 -- theme: CRYPTO SPOT with a STRUCTURAL TETHER.

Library: panel loading, tether-spread construction, OU/ADF/Hurst/rho1 diagnostics,
book P&L accounting. Pure numpy (no scipy/pandas in this env).

Tether classes built here (each is a spread whose fair value is pinned by a REAL
economic mechanism, not by a fitted statistic):
  A  stablecoin vs USDT        fair = 1.0        anchor = issuer redemption at $1
  B  wrapped/staked vs under.  fair = parity or  anchor = burn/unwrap (WBTC->BTC),
                               accrual index            withdrawal (WBETH/BETH->ETH)
  C  triangular cross-quote    fair = 0          anchor = same-venue no-arbitrage
  D  cross-venue same asset    fair = 0          anchor = cross-venue arbitrage
"""
from __future__ import annotations
import os, sys, json
import numpy as np

ROOT = "/home/anont/meme"
CACHE = os.path.join(ROOT, "research/data/xspot_cache")
sys.path.insert(0, os.path.join(ROOT, "research/trading_bot/ou_mean_reversion"))
import oulib  # noqa: E402


# --------------------------------------------------------------------- panels
class Panels:
    def __init__(self):
        bn = np.load(os.path.join(CACHE, "spot_daily.npz"), allow_pickle=True)
        xq = np.load(os.path.join(CACHE, "spotxq_daily.npz"), allow_pickle=True)
        cb = np.load(os.path.join(CACHE, "coinbase_daily.npz"), allow_pickle=True)
        self.days = bn["days"].astype(np.int64)
        assert np.array_equal(self.days, xq["days"].astype(np.int64))
        self.T = self.days.size
        self.bn_syms = {str(s): i for i, s in enumerate(bn["syms"])}
        self.xq_syms = {str(s): i for i, s in enumerate(xq["syms"])}
        self.bn_o, self.bn_c, self.bn_qv = bn["o"], bn["c"], bn["qv"]
        self.xq_o, self.xq_c, self.xq_qv = xq["o"], xq["c"], xq["qv"]
        # coinbase grid -> common grid
        cbd = cb["days"].astype(np.int64)
        pos = {int(d): i for i, d in enumerate(cbd)}
        self.cb_idx = np.array([pos.get(int(d), -1) for d in self.days])
        self.cb_syms = {str(s): i for i, s in enumerate(cb["syms"])}
        self.cb_c_raw, self.cb_qv_raw = cb["c"], cb["qv"]

    def _get(self, syms, arr, sym):
        i = syms.get(sym)
        if i is None:
            return None
        v = np.asarray(arr[i], dtype=np.float64).copy()
        v[~np.isfinite(v)] = np.nan
        v[v <= 0] = np.nan
        return v

    def bn(self, sym, f="c"):
        return self._get(self.bn_syms, {"c": self.bn_c, "o": self.bn_o, "qv": self.bn_qv}[f], sym)

    def xq(self, sym, f="c"):
        return self._get(self.xq_syms, {"c": self.xq_c, "o": self.xq_o, "qv": self.xq_qv}[f], sym)

    def cb(self, sym, f="c"):
        i = self.cb_syms.get(sym)
        if i is None:
            return None
        src = self.cb_c_raw if f == "c" else self.cb_qv_raw
        raw = np.asarray(src[i], dtype=np.float64)
        out = np.full(self.T, np.nan)
        ok = self.cb_idx >= 0
        out[ok] = raw[self.cb_idx[ok]]
        out[~np.isfinite(out)] = np.nan
        out[out <= 0] = np.nan
        return out

    def dates(self):
        import datetime
        return np.array([int(datetime.datetime.fromtimestamp(int(d) / 1000, datetime.UTC)
                             .strftime("%Y%m%d")) for d in self.days])


# ------------------------------------------------------------------ diagnostics
def rho1_dspread(s):
    """lag-1 autocorrelation of the spread's daily CHANGE.  -0.5 == pure
    measurement/bid-ask bounce (untradable).  Gate: must be > ~-0.35."""
    s = np.asarray(s, float)
    m = np.isfinite(s)
    # use the longest finite run-set: diff only over consecutive finite pairs
    d = np.full(s.size - 1, np.nan)
    ok = m[:-1] & m[1:]
    d[ok] = s[1:][ok] - s[:-1][ok]
    x = d[:-1]; y = d[1:]
    g = np.isfinite(x) & np.isfinite(y)
    if g.sum() < 50:
        return float("nan"), int(g.sum())
    x = x[g]; y = y[g]
    r = np.corrcoef(x, y)[0, 1]
    return float(r), int(g.sum())


def diag_spread(s, name):
    s = np.asarray(s, float)
    f = s[np.isfinite(s)]
    out = {"name": name, "n": int(f.size)}
    if f.size < 120:
        out["note"] = "too short"
        return out
    ou = oulib.fit_ou(f)
    ad = oulib.adf(f)
    h = oulib.hurst_rs(f)
    r1, nr = rho1_dspread(s)
    out.update(half_life=round(ou["half_life"], 2), theta=round(ou["theta"], 5),
               sigma_eq_bp=round(ou["sigma_eq"] * 1e4, 1), phi=round(ou["phi"], 4),
               hurst=round(float(h if np.isscalar(h) else h[0]), 3) if h is not None else None,
               adf_t=round(ad["tstat"], 2), adf=oulib.adf_verdict(ad["tstat"]),
               rho1_dspread=round(r1, 3), rho1_n=nr,
               mean_bp=round(float(np.mean(f)) * 1e4, 1),
               sd_bp=round(float(np.std(f)) * 1e4, 1),
               p01_bp=round(float(np.percentile(f, 1)) * 1e4, 1),
               p99_bp=round(float(np.percentile(f, 99)) * 1e4, 1))
    out["rho1_gate"] = bool(np.isfinite(r1) and r1 > -0.35)
    return out


# ---------------------------------------------------------------- book P&L
def normalize_eq(w):
    """Equal-weight the fired instruments so the book carries <=1 unit gross/day."""
    w = np.nan_to_num(np.asarray(w, float))
    nact = np.maximum(np.sum(np.abs(w) > 0, axis=1), 1)
    return w / nact[:, None]


def book_pnl(ww, legret, legs, fee_bp):
    """ww     (T,K) FINAL weight per instrument for the day-t holding period
       legret (T,K) the spread's log return realised over that holding period
       legs   (K,)  number of exchange legs crossed per unit weight change
    Returns dict of gross/net daily portfolio pnl in bp and turnover in legs."""
    ww = np.nan_to_num(np.asarray(ww, float))
    legret = np.asarray(legret, float)
    T, K = ww.shape
    act = np.isfinite(legret) & (np.abs(ww) > 0)
    r = np.where(np.isfinite(legret), legret, 0.0)
    gross = np.sum(ww * r, axis=1)
    dw = np.abs(np.diff(np.vstack([np.zeros((1, K)), ww]), axis=0))
    turn = np.sum(dw * np.asarray(legs, float)[None, :], axis=1)
    net = gross - turn * fee_bp * 1e-4
    return dict(gross=gross * 1e4, net=net * 1e4, turn=turn, active=act.any(axis=1))


def stats(pnl_bp, mask, ann=365.0):
    x = np.asarray(pnl_bp, float)[mask]
    x = x[np.isfinite(x)]
    n = x.size
    if n < 30 or x.std() == 0:
        return dict(n=n, mean_bp=float("nan"), sharpe=float("nan"), t=float("nan"))
    mu = x.mean(); sd = x.std(ddof=1)
    return dict(n=int(n), mean_bp=round(float(mu), 4), sd_bp=round(float(sd), 4),
                sharpe=round(float(mu / sd * np.sqrt(ann)), 3),
                t=round(float(mu / sd * np.sqrt(n)), 3))


def block_signflip_maxsharpe_masks(pnls, masks, nrep=2000, block=10, seed=7, ann=365.0):
    """Sign-flip block bootstrap of max |Sharpe| over a family of correlated daily
    P&L series that live on DIFFERENT windows.  One global block-sign vector per
    replicate (so cross-formula correlation survives), each series scored on its
    own design mask (so each formula keeps its true sample size)."""
    rng = np.random.default_rng(seed)
    T = len(np.asarray(pnls[0]))
    nb = int(np.ceil(T / block))
    P = [np.nan_to_num(np.asarray(p, float)) for p in pnls]
    out = np.empty(nrep)
    for r in range(nrep):
        sg = np.repeat(rng.choice([-1.0, 1.0], size=nb), block)[:T]
        best = 0.0
        for p, m in zip(P, masks):
            x = (p * sg)[m]
            if x.size < 30:
                continue
            sd = x.std(ddof=1)
            if sd <= 0:
                continue
            sh = abs(x.mean() / sd * np.sqrt(ann))
            if sh > best:
                best = sh
        out[r] = best
    return dict(mean=round(float(out.mean()), 3), p95=round(float(np.percentile(out, 95)), 3),
                p99=round(float(np.percentile(out, 99)), 3))


def tail_stats(pnl_bp, mask):
    x = np.asarray(pnl_bp, float)[mask]
    x = x[np.isfinite(x)]
    if x.size < 30:
        return {}
    eq = np.cumsum(x)
    dd = eq - np.maximum.accumulate(eq)
    sd = x.std(ddof=1)
    sk = float(np.mean(((x - x.mean()) / sd) ** 3)) if sd > 0 else float("nan")
    w5 = np.convolve(x, np.ones(5), "valid") if x.size >= 5 else np.array([np.nan])
    return dict(skew=round(sk, 2), worst_day_bp=round(float(x.min()), 1),
                best_day_bp=round(float(x.max()), 1),
                worst_5d_bp=round(float(np.nanmin(w5)), 1),
                maxdd_bp=round(float(dd.min()), 1),
                total_bp=round(float(eq[-1]), 1),
                pct_days_neg=round(float(np.mean(x < 0)), 3))


def block_signflip_maxsharpe(pnls, mask, nrep=2000, block=10, seed=7, ann=365.0):
    """Sign-flip block bootstrap of the MAX |Sharpe| over a family of correlated
    daily-P&L series, re-scored jointly in every replicate."""
    rng = np.random.default_rng(seed)
    M = np.vstack([np.nan_to_num(np.asarray(p, float))[mask] for p in pnls])
    F, n = M.shape
    nb = int(np.ceil(n / block))
    out = np.empty(nrep)
    for r in range(nrep):
        sg = rng.choice([-1.0, 1.0], size=nb)
        sg = np.repeat(sg, block)[:n]
        X = M * sg[None, :]
        mu = X.mean(axis=1); sd = X.std(axis=1, ddof=1)
        sh = np.where(sd > 0, mu / np.maximum(sd, 1e-12) * np.sqrt(ann), 0.0)
        out[r] = np.max(np.abs(sh))
    return dict(mean=round(float(out.mean()), 3), p95=round(float(np.percentile(out, 95)), 3),
                p99=round(float(np.percentile(out, 99)), 3))
