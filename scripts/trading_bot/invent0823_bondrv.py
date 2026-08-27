#!/usr/bin/env python3
"""INVENT 0823 -- BOND / CREDIT-ETF STRUCTURAL RELATIVE VALUE.

THEME.  Extend the PUBLISHED-TETHER survivor class (T12 CEF discount, ETF-sibling RV) into
fixed income.  A bond ETF has, in principle, the cleanest tether in the market: the issuer
publishes an end-of-day NAV and an intraday iNAV, and the fund is contractually the claim on
that NAV.

DATA REALITY, STATED UP FRONT (this is a result, not a caveat).  Machine-readable daily NAV
HISTORY for US bond ETFs is NOT obtainable on a free feed.  Probed 2026-08-23:
  * iShares  .ajax?fileType=csv&fileName=<T>_NAV&dataType=fund  -> 200 but serves the product
    page HTML (Akamai bot wall), on both ishares.com and blackrock.com hosts, with and without
    browser headers / Referer / siteEntryPassthrough.
  * SSGA nav-history xlsx paths -> 404.
  * Vanguard investor API price-history paths -> 404.
  * Yahoo iNAV proxy tickers (^HYG-IV etc.) -> not served.
  * Nasdaq api/quote/<T>/historical -> PRICE only, no NAV column.
  * FRED ICE BofA index TOTAL RETURN series (BAMLHYH0A0HYM2TRIV, BAMLCC0A0CMTRIV, ...) exist
    and are free but are LICENCE-CAPPED TO A ROLLING 3 YEARS -- too short to split, and a
    rolling cap means the design window is not reproducible.  Recorded, not used as a scored
    tether.  (Same cap already found for the OAS series by newterr_ratescredit.)
So the NAV premium/discount mean-reversion trade -- the direct fixed-income analogue of T12 --
is DATA-BLOCKED on free feeds, exactly like XS_GLSR_Z.  It is not tested here; it is priced.

WHAT IS TESTED INSTEAD -- three tethers that ARE free, daily, long-history and permanent:

  TETHER 1  SIBLING IDENTITY.  Two ETFs whose portfolios are the same economic claim
            (HYG/JNK, LQD/USIG, TLT/VGLT, AGG/BND, TIP/SCHP, MUB/TFI, EMB/PCY, ...).  The
            tether value is not published as a number, but the CLAIM is identical by
            construction, which is the same thing that makes SPY/IVV RV work.
  TETHER 2  THE PUBLISHED TREASURY PAR CURVE.  Treasury/Fed H.15 publishes DGS2/5/10/30 every
            day, public domain, 1990->.  A Treasury bond fund's NAV return is, to first order,
            a known linear function of that published curve.  The residual of the fund's total
            return against the published curve IS a premium/discount, reconstructed from a
            third-party published number.
  TETHER 3  THE PUBLISHED MOODY'S CORPORATE YIELDS.  DAAA / DBAA, public domain, daily.  Same
            construction for IG and HY credit funds.

STRUCTURE.  Everything is ETF-vs-ETF: long the cheap fund, short the identical/curve-matched
fund.  No naked directional leg, no single-stock short.  All legs are US bond ETFs with
>= $20M median dollar volume -- the deepest ETB universe in the market -- so the borrow wall
that killed preferred-RV does not apply here.

GATES, IN ORDER (from the programme's hard lessons):
  G0  rho1 of the daily CHANGE in each spread must be > -0.35.  rho1 near -0.5 is bid-ask
      bounce, which is untradable no matter what the Sharpe says.  Inside a tethered family a
      HIGH gross Sharpe is evidence AGAINST, so this runs BEFORE the Sharpe is looked at.
  G1  LAG-KILL.  w[t] earns close(t-1)->close(t) and sees data only through close(t-L).
      L=1 is the scored base; L=2 is reported next to it.
  G2  GROSS first.  The design gross Sharpe must beat BOTH the analytic bar sqrt(2 ln N)/sqrt(yrs)
      AND the p95 of a SIZE-MATCHED PLACEBO max.  Cost fixes are not attempted for a formula
      that fails on gross.
  G3  HELD-OUT NET > 0, read once, after the design ranking is on disk.
NO regime conditioning anywhere.  Sign is pre-registered: every formula is written so that
mean reversion of the spread is a POSITIVE Sharpe.  A negative Sharpe is a failure, not a flip.

PLACEBO.  The signal matrix is circularly ROTATED by a random offset (>= 63 trading days),
with the return panel and the whole portfolio-construction pipeline untouched.  Rotating the
SIGNAL, not the returns, is the point: the rotate-the-returns null is broken for
cross-sectional books because it injects a directional leg.  Rotation preserves the signal's
own autocorrelation, hence the turnover, hence the cost -- so the placebo is size-matched in
the way that matters.  The SAME offset is used for every formula inside a draw, so their
cross-correlation survives and the max is not inflated.  400 draws.

COSTS.  Both legs pay.  Headline half-spread per symbol = max(1.0 bp, 2 x (half a cent /
price)) -- a tick-floor-times-adversity PROXY, not a quote measurement, said out loud.  Plus
0.15 bp per unit of turnover for SEC 31 + FINRA TAF.  Plus borrow at B22G's measured ETB
general-collateral median 0.33 %/yr on short notional per calendar day.  A tick-floor LOWER
BOUND (half of a one-cent spread, no adversity, no floor) is reported alongside as the
arithmetic floor no execution can beat.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[2]
CACHE = ROOT / "research" / "data" / "ratescredit_cache"
OUT = ROOT / "research" / "trading_bot"
KEY = "INVENT_0823_bondrv"

DESIGN = ("2010-01-04", "2019-12-31")
HELDOUT = ("2020-01-02", "2026-08-20")

REG_BP = 0.15          # SEC 31 + FINRA TAF per unit turnover
BORROW_ANN = 0.0033    # B22G measured ETB GC median
MIN_ADV_USD = 20e6
RHO1_FLOOR = -0.35
N_PLACEBO = 400
ANN = 252.0


# ----------------------------------------------------------------------------- data

def load() -> dict:
    px = json.loads((CACHE / "etf_daily.json").read_text())
    fred = json.loads((CACHE / "fred_daily.json").read_text())

    # union calendar from SPY (a full NYSE calendar)
    def to_date(ts):
        return dt.datetime.fromtimestamp(ts, dt.UTC).strftime("%Y-%m-%d")

    cal = sorted({to_date(t) for t in px["SPY"]["t"]})
    idx = {d: i for i, d in enumerate(cal)}
    n = len(cal)

    syms, A, C, V = [], [], [], []
    for s, v in px.items():
        a = np.full(n, np.nan)
        c = np.full(n, np.nan)
        w = np.full(n, np.nan)
        for t, ac, cl, vol in zip(v["t"], v["adjclose"], v["close"], v["volume"]):
            d = to_date(t)
            i = idx.get(d)
            if i is None or ac is None:
                continue
            a[i] = ac
            c[i] = cl if cl is not None else np.nan
            w[i] = vol if vol is not None else np.nan
        syms.append(s)
        A.append(a)
        C.append(c)
        V.append(w)
    A = np.array(A)
    C = np.array(C)
    V = np.array(V)

    # FRED aligned to the equity calendar, forward-filled (a rate published today is
    # available today; a missing day is a holiday in one market and not the other)
    F = {}
    for sid, series in fred.items():
        arr = np.full(n, np.nan)
        for d, val in series.items():
            i = idx.get(d)
            if i is not None:
                arr[i] = val
        # forward fill
        last = np.nan
        for i in range(n):
            if np.isnan(arr[i]):
                arr[i] = last
            else:
                last = arr[i]
        F[sid] = arr

    return {"cal": np.array(cal), "syms": syms, "adj": A, "close": C, "vol": V, "fred": F,
            "si": {s: i for i, s in enumerate(syms)}}


def log_ret(adj: np.ndarray) -> np.ndarray:
    r = np.full_like(adj, np.nan)
    r[:, 1:] = np.log(adj[:, 1:] / adj[:, :-1])
    return r


# ----------------------------------------------------------------------------- helpers

def roll_z(x: np.ndarray, w: int) -> np.ndarray:
    """Rolling z of a 1-D or 2-D (sym x time) series, causal, using data through t."""
    x = np.atleast_2d(x)
    out = np.full(x.shape, np.nan)
    for i in range(x.shape[0]):
        v = x[i]
        cs = np.nancumsum(np.nan_to_num(v))
        cs2 = np.nancumsum(np.nan_to_num(v) ** 2)
        cnt = np.cumsum(~np.isnan(v))
        for t in range(w, x.shape[1]):
            k = cnt[t] - cnt[t - w]
            if k < w * 0.8:
                continue
            m = (cs[t] - cs[t - w]) / k
            s2 = (cs2[t] - cs2[t - w]) / k - m * m
            if s2 <= 1e-18:
                continue
            out[i, t] = (v[t] - m) / np.sqrt(s2)
    return out


def ewma_z(x: np.ndarray, hl: int) -> np.ndarray:
    x = np.atleast_2d(x)
    lam = 0.5 ** (1.0 / hl)
    out = np.full(x.shape, np.nan)
    for i in range(x.shape[0]):
        m = v = np.nan
        for t in range(x.shape[1]):
            if np.isnan(x[i, t]):
                out[i, t] = np.nan
                continue
            if np.isnan(m):
                m, v = x[i, t], 0.0
            else:
                d = x[i, t] - m
                m = m + (1 - lam) * d
                v = lam * (v + (1 - lam) * d * d)
            if v > 1e-18:
                out[i, t] = (x[i, t] - m) / np.sqrt(v)
    return out


def band(z: np.ndarray, hi: float, lo: float) -> np.ndarray:
    """Hysteresis band: enter at |z|>hi with position -sign(z), exit at |z|<lo."""
    out = np.zeros(z.shape)
    for i in range(z.shape[0]):
        pos = 0.0
        for t in range(z.shape[1]):
            zz = z[i, t]
            if np.isnan(zz):
                out[i, t] = pos
                continue
            if pos == 0.0:
                if abs(zz) > hi:
                    pos = -np.sign(zz)
            elif abs(zz) < lo:
                pos = 0.0
            out[i, t] = pos
    return out


def rho1_dspread(sp: np.ndarray, m: np.ndarray) -> float:
    d = np.diff(sp[m])
    d = d[np.isfinite(d)]
    if len(d) < 100:
        return np.nan
    return float(np.corrcoef(d[:-1], d[1:])[0, 1])


# ----------------------------------------------------------------------------- universe

PAIRS = [
    # (long-name, a, b, family)  a/b are the SAME economic claim
    ("hy_hyg_jnk",   "HYG", "JNK",  "HY"),
    ("hy_hyg_ushy",  "HYG", "USHY", "HY"),
    ("hy_jnk_hylb",  "JNK", "HYLB", "HY"),
    ("hy_sjnk_shyg", "SJNK", "SHYG", "HY"),
    ("ig_lqd_usig",  "LQD", "USIG", "IG"),
    ("ig_igib_vcit", "IGIB", "VCIT", "IG"),
    ("ig_igsb_vcsh", "IGSB", "VCSH", "IG"),
    ("ig_spib_igib", "SPIB", "IGIB", "IG"),
    ("tsy_tlt_vglt", "TLT", "VGLT", "TSY"),
    ("tsy_tlt_sptl", "TLT", "SPTL", "TSY"),
    ("tsy_ief_vgit", "IEF", "VGIT", "TSY"),
    ("tsy_shy_vgsh", "SHY", "VGSH", "TSY"),
    ("tsy_shy_scho", "SHY", "SCHO", "TSY"),
    ("agg_agg_bnd",  "AGG", "BND",  "AGG"),
    ("tip_tip_schp", "TIP", "SCHP", "TIP"),
    ("muni_mub_tfi", "MUB", "TFI",  "MUNI"),
    ("em_emb_pcy",   "EMB", "PCY",  "EM"),
    ("lo_bkln_srln", "BKLN", "SRLN", "LOAN"),
    ("pf_pff_pgx",   "PFF", "PGX",  "PFD"),
]

TSY_SET = ["SHY", "SCHO", "VGSH", "IEI", "SCHR", "VGIT", "IEF", "TLH", "TLT", "VGLT",
           "SPTL", "GOVT", "EDV", "ZROZ"]
IG_SET = ["VCSH", "IGSB", "SPIB", "IGIB", "VCIT", "USIG", "LQD", "VCLT"]
# TIPS + duration-matched nominals in ONE cross-section: with the breakeven among the
# factors the book is neutral to the curve AND to the published breakeven, so what is left
# is the deviation of the ETF-implied real/nominal pricing from the PUBLISHED one.
TIPS_SET = ["VTIP", "STIP", "SCHP", "TIP", "LTPZ", "SHY", "IEI", "IEF", "TLT"]
CURVE = ["DGS2", "DGS5", "DGS10", "DGS30"]
CREDIT = ["DAAA", "DBAA"]
BREAKEVEN = ["T5YIE", "T10YIE"]


# ----------------------------------------------------------------------------- weights

def pair_parts(D, a, b, sigfn, entry, hedge_w=0, hold=1):
    """Return (unitW, pos, spread, z) for one sibling pair.

    unitW is the leg structure normalised to gross notional 1 at pos=+1 (long a, short beta*b);
    pos is the scalar position in [-1,1].  Long a / short b when a is cheap relative to b.
    """
    ia, ib = D["si"][a], D["si"][b]
    ra, rb = D["lr"][ia], D["lr"][ib]
    valid = np.isfinite(ra) & np.isfinite(rb)
    dsp = np.where(valid, ra - rb, np.nan)
    sp = np.nancumsum(np.nan_to_num(dsp))
    sp[~np.cumsum(valid).astype(bool)] = np.nan

    if hedge_w > 0:  # rolling OLS beta of ra on rb, causal
        beta = np.full(len(ra), np.nan)
        for t in range(hedge_w, len(ra)):
            x = rb[t - hedge_w:t]
            y = ra[t - hedge_w:t]
            m = np.isfinite(x) & np.isfinite(y)
            if m.sum() < hedge_w * 0.8 or np.nanvar(x[m]) < 1e-18:
                continue
            beta[t] = np.cov(y[m], x[m])[0, 1] / np.var(x[m])
        beta = np.clip(beta, 0.2, 5.0)
        dsp2 = np.where(valid & np.isfinite(beta), ra - beta * rb, np.nan)
        sp = np.nancumsum(np.nan_to_num(dsp2))
        sp[~np.cumsum(valid).astype(bool)] = np.nan
    else:
        beta = np.ones(len(ra))

    z = sigfn(sp)[0]
    if entry == "cont":
        pos = np.clip(-z, -3, 3) / 3.0
    else:
        hi, lo = entry
        pos = band(np.atleast_2d(z), hi, lo)[0]
    pos = np.nan_to_num(pos)
    if hold > 1:  # smooth over `hold` days = 1/hold refresh
        k = np.ones(hold) / hold
        pos = np.convolve(pos, k)[:len(pos)]

    unitW = np.zeros((D["adj"].shape[0], D["adj"].shape[1]))
    bb = np.nan_to_num(beta, nan=1.0)
    gross = 1.0 + bb
    unitW[ia] = 1.0 / gross
    unitW[ib] = -bb / gross
    unitW[:, ~valid] = 0.0
    pos = np.where(valid, pos, 0.0)
    return unitW, pos, sp, z


def pair_weights(D, a, b, sigfn, entry, hedge_w=0, hold=1):
    unitW, pos, sp, z = pair_parts(D, a, b, sigfn, entry, hedge_w, hold)
    return unitW * pos[None, :], sp, z


def xs_pair_weights(D, pairs, sigfn, entry, hedge_w=0, hold=1, rank=False):
    """Equal-risk book across many sibling pairs; gross notional normalised to 1 each day."""
    parts = []
    for nm, a, b, fam in pairs:
        if a not in D["si"] or b not in D["si"]:
            continue
        parts.append(pair_parts(D, a, b, sigfn, entry, hedge_w, hold))
    if not parts:
        return None, None
    Z = np.array([p[3] for p in parts])
    POS = np.array([p[1] for p in parts])
    if rank:
        # cross-sectional rank of z each day -> [-1,1], reversed (cheapest gets the long)
        R = np.zeros(Z.shape)
        for t in range(Z.shape[1]):
            col = Z[:, t]
            m = np.isfinite(col) & (np.abs(POS[:, t]) >= 0)
            live_t = m & np.array([np.abs(p[0][:, t]).sum() > 0 for p in parts])
            if live_t.sum() < 3:
                continue
            order = np.argsort(np.argsort(col[live_t])).astype(float)
            R[live_t, t] = -(2 * order / (live_t.sum() - 1) - 1)
        POS = R
    W = np.zeros(parts[0][0].shape)
    for i, p in enumerate(parts):
        W += p[0] * POS[i][None, :]
    # constant capital: each AVAILABLE pair gets 1/n_available, so sitting out stays flat
    navail = np.sum([np.abs(p[0]).sum(axis=0) > 0 for p in parts], axis=0).astype(float)
    W = np.divide(W, np.where(navail > 0, navail, 1.0)[None, :])
    return W, Z


def resid_curve(D, syms, factors, fitw=250):
    """Residual of each fund's daily TR return against the PUBLISHED factor changes.
    Causal rolling OLS; residual at t uses betas fit on [t-fitw, t)."""
    T = D["adj"].shape[1]
    X = np.array([np.concatenate([[np.nan], np.diff(D["fred"][f])]) for f in factors])
    out, betas, keep = [], [], []
    for s in syms:
        if s not in D["si"]:
            continue
        y = D["lr"][D["si"][s]]
        res = np.full(T, np.nan)
        bt = np.full((len(factors), T), np.nan)
        for t in range(fitw, T):
            xs = X[:, t - fitw:t].T
            ys = y[t - fitw:t]
            m = np.isfinite(ys) & np.isfinite(xs).all(axis=1)
            if m.sum() < fitw * 0.7:
                continue
            Xm = np.column_stack([np.ones(m.sum()), xs[m]])
            try:
                b, *_ = np.linalg.lstsq(Xm, ys[m], rcond=None)
            except np.linalg.LinAlgError:
                continue
            if not np.isfinite(y[t]) or not np.isfinite(X[:, t]).all():
                continue
            res[t] = y[t] - (b[0] + X[:, t] @ b[1:])
            bt[:, t] = b[1:]
        out.append(res)
        betas.append(bt)
        keep.append(s)
    return np.array(out), np.array(betas), keep


def tether_weights(D, syms, factors, sigfn, entry, fitw=250):
    """Cross-sectional book on cumulative published-tether residuals, factor-neutralised."""
    R, B, keep = D["resid_cache"][(tuple(syms), tuple(factors), fitw)]
    CUM = np.nancumsum(np.nan_to_num(R), axis=1)
    CUM[np.isnan(R)] = np.nan
    Z = sigfn(CUM)
    # demean cross-sectionally so the book has no common-mode tilt
    Zc = Z - np.nanmean(Z, axis=0, keepdims=True)
    if entry == "cont":
        raw = np.nan_to_num(np.clip(-Zc, -3, 3) / 3.0)
    else:
        raw = band(np.nan_to_num(Zc), *entry)
    T = D["adj"].shape[1]
    W = np.zeros((D["adj"].shape[0], T))
    for t in range(T):
        w = raw[:, t].copy()
        bt = B[:, :, t]
        ok = np.isfinite(bt).all(axis=1) & np.isfinite(w)
        if ok.sum() < len(factors) + 2:
            continue
        w = np.where(ok, w, 0.0)
        # project the raw weights onto the orthogonal complement of the published-factor
        # loadings AND the constant -> the book is curve/credit neutral and dollar neutral
        Xb = np.column_stack([np.ones(ok.sum()), bt[ok]])
        try:
            proj = Xb @ np.linalg.lstsq(Xb, w[ok], rcond=None)[0]
        except np.linalg.LinAlgError:
            continue
        wn = w[ok] - proj
        g = np.abs(wn).sum()
        if g < 1e-12:
            continue
        wn = wn / g
        for k, s in enumerate(np.array(keep)[ok]):
            W[D["si"][s], t] = wn[k]
    return W, Z


def synth_weights(D, etf, legs, sigfn, entry):
    """ETF vs a published-composition synthetic basket of liquid ETFs."""
    if etf not in D["si"] or any(l not in D["si"] for l, _ in legs):
        return None, None
    r_e = D["lr"][D["si"][etf]]
    r_s = np.zeros_like(r_e)
    ok = np.isfinite(r_e)
    for l, w in legs:
        rl = D["lr"][D["si"][l]]
        ok &= np.isfinite(rl)
        r_s = r_s + w * np.nan_to_num(rl)
    dsp = np.where(ok, r_e - r_s, np.nan)
    sp = np.nancumsum(np.nan_to_num(dsp))
    sp[~np.cumsum(ok).astype(bool)] = np.nan
    z = sigfn(sp)[0]
    if entry == "cont":
        pos = np.clip(-z, -3, 3) / 3.0
    else:
        pos = band(np.atleast_2d(z), *entry)[0]
    pos = np.nan_to_num(pos)
    W = np.zeros(D["adj"].shape)
    gross = 1.0 + sum(abs(w) for _, w in legs)
    W[D["si"][etf]] = pos / gross
    for l, w in legs:
        W[D["si"][l]] -= pos * w / gross
    W[:, ~ok] = 0.0
    return W, sp


# ----------------------------------------------------------------------------- pnl

def evaluate(D, W, lag: int, mask: np.ndarray, lb=False, ret=None):
    """W[:,t] is the target book formed from data through close(t).

    ret=None (default): P[:,t]=W[:,t-lag] earns close(t-1)->close(t).  lag=1 therefore means
    the book is FILLED AT close(t-1), the same print the signal was computed from.
    ret="oo": the return series is open-to-open, so lag=2 means signal at close(t-2), fill at
    open(t-1), and the P&L earned is open(t-1)->open(t) -- signal price and fill price are
    DIFFERENT PRINTS, which is the whole point of the variant.
    """
    T = W.shape[1]
    P = np.zeros_like(W)
    P[:, lag:] = W[:, :T - lag]
    R = np.nan_to_num(D["lr_oo"] if ret == "oo" else D["lr"])
    gross_pnl = (P * R).sum(axis=0)
    turn = np.abs(np.diff(P, axis=1, prepend=0.0)).sum(axis=0)
    hs = D["hs_lb"] if lb else D["hs"]
    cost = (np.abs(np.diff(P, axis=1, prepend=0.0)) * hs[:, None]).sum(axis=0) / 1e4
    cost = cost + turn * REG_BP / 1e4
    shortn = np.clip(-P, 0, None).sum(axis=0)
    borrow = shortn * BORROW_ANN / 365.0 * D["caldays"]
    net = gross_pnl - cost - borrow
    g, n, t = gross_pnl[mask], net[mask], turn[mask]
    return {
        "gross_sharpe": sharpe(g), "net_sharpe": sharpe(n),
        "gross_bpd": float(np.nanmean(g) * 1e4), "cost_bpd": float(np.nanmean(cost[mask]) * 1e4),
        "borrow_bpd": float(np.nanmean(borrow[mask]) * 1e4),
        "net_bpd": float(np.nanmean(n) * 1e4), "turn": float(np.nanmean(t)),
        "days": int(mask.sum()), "daily_net": n, "daily_gross": g,
    }


def sharpe(x: np.ndarray) -> float:
    x = x[np.isfinite(x)]
    if len(x) < 60 or np.std(x) < 1e-14:
        return float("nan")
    return float(np.mean(x) / np.std(x) * np.sqrt(ANN))


# ----------------------------------------------------------------------------- formulas

def build_formulas(D):
    F = {}
    z21 = lambda x: roll_z(x, 21)
    z63 = lambda x: roll_z(x, 63)
    z126 = lambda x: roll_z(x, 126)
    z252 = lambda x: roll_z(x, 252)
    ew21 = lambda x: ewma_z(x, 21)

    live = [p for p in PAIRS if p[1] in D["si"] and p[2] in D["si"]
            and D["adv"][D["si"][p[1]]] > MIN_ADV_USD and D["adv"][D["si"][p[2]]] > MIN_ADV_USD]
    # rho1-CLEAN subset: pairs whose DESIGN-window d(spread) autocorrelation clears the
    # bounce floor.  Selected on the design window only, and used unchanged out of sample.
    clean = [p for p in live if D["pair_rho1"].get(p[0], -1) > RHO1_FLOOR]

    # --- A: single sibling pairs, continuous z63 (10 formulas, one per asset class) ---
    for nm, a, b, fam in live[:12]:
        F[f"A_{nm}_z63c"] = ("pair", dict(a=a, b=b, sig=z63, entry="cont"), f"sibling {a}/{b} z63 continuous")

    # --- B: pooled cross-sectional books over all sibling pairs ---
    F["B_xs_z63c"] = ("xs", dict(sig=z63, entry="cont"), "all sibling pairs, z63 continuous")
    F["B_xs_z21c"] = ("xs", dict(sig=z21, entry="cont"), "all sibling pairs, z21 continuous")
    F["B_xs_z126c"] = ("xs", dict(sig=z126, entry="cont"), "all sibling pairs, z126 continuous")
    F["B_xs_z252c"] = ("xs", dict(sig=z252, entry="cont"), "all sibling pairs, z252 continuous")
    F["B_xs_ew21c"] = ("xs", dict(sig=ew21, entry="cont"), "all sibling pairs, EWMA z hl=21")
    F["B_xs_z63_band15"] = ("xs", dict(sig=z63, entry=(1.5, 0.5)), "all sibling pairs, z63 band 1.5/0.5")
    F["B_xs_z63_band20"] = ("xs", dict(sig=z63, entry=(2.0, 0.5)), "all sibling pairs, z63 band 2.0/0.5")
    F["B_xs_z63_beta"] = ("xs", dict(sig=z63, entry="cont", hedge_w=126), "all sibling pairs, z63, rolling-beta hedge")
    F["B_xs_z63_hold5"] = ("xs", dict(sig=z63, entry="cont", hold=5), "all sibling pairs, z63, 5-day averaged book")
    F["B_xs_z63_rank"] = ("xs", dict(sig=z63, entry="cont", rank=True), "all sibling pairs, cross-sectional rank of z63")

    # --- B-clean: same books restricted to pairs that pass the rho1 bounce gate on design ---
    F["BC_xs_z63c"] = ("xsc", dict(sig=z63, entry="cont"), "rho1-CLEAN sibling pairs, z63 continuous")
    F["BC_xs_z21c"] = ("xsc", dict(sig=z21, entry="cont"), "rho1-CLEAN sibling pairs, z21 continuous")
    F["BC_xs_z126c"] = ("xsc", dict(sig=z126, entry="cont"), "rho1-CLEAN sibling pairs, z126 continuous")
    F["BC_xs_ew21c"] = ("xsc", dict(sig=ew21, entry="cont"), "rho1-CLEAN sibling pairs, EWMA z hl=21")
    F["BC_xs_band15"] = ("xsc", dict(sig=z63, entry=(1.5, 0.5)), "rho1-CLEAN sibling pairs, z63 band 1.5/0.5")
    F["BC_xs_hold5"] = ("xsc", dict(sig=z63, entry="cont", hold=5), "rho1-CLEAN sibling pairs, z63, 5-day averaged book")

    # --- C: PUBLISHED TREASURY CURVE tether ---
    F["C_tsy_z63c"] = ("teth", dict(syms=TSY_SET, fac=CURVE, sig=z63, entry="cont"), "Treasury ETFs vs published H.15 par curve, cum-resid z63")
    F["C_tsy_z21c"] = ("teth", dict(syms=TSY_SET, fac=CURVE, sig=z21, entry="cont"), "Treasury vs published curve, z21")
    F["C_tsy_z126c"] = ("teth", dict(syms=TSY_SET, fac=CURVE, sig=z126, entry="cont"), "Treasury vs published curve, z126")
    F["C_tsy_band15"] = ("teth", dict(syms=TSY_SET, fac=CURVE, sig=z63, entry=(1.5, 0.5)), "Treasury vs published curve, z63 band")
    F["C_tsy_fit500"] = ("teth", dict(syms=TSY_SET, fac=CURVE, sig=z63, entry="cont", fitw=500), "Treasury vs published curve, 500d loading fit")

    # --- D: PUBLISHED MOODY'S CORPORATE YIELD tether ---
    F["D_ig_z63c"] = ("teth", dict(syms=IG_SET, fac=CURVE + CREDIT, sig=z63, entry="cont"), "IG credit ETFs vs published curve + Moody's DAAA/DBAA, z63")
    F["D_ig_z21c"] = ("teth", dict(syms=IG_SET, fac=CURVE + CREDIT, sig=z21, entry="cont"), "IG vs published credit tether, z21")
    F["D_ig_band15"] = ("teth", dict(syms=IG_SET, fac=CURVE + CREDIT, sig=z63, entry=(1.5, 0.5)), "IG vs published credit tether, z63 band")

    # --- T: PUBLISHED TIPS-BREAKEVEN tether (FRED publishes T5YIE/T10YIE daily) ---
    F["T_be_z63c"] = ("teth", dict(syms=TIPS_SET, fac=CURVE + BREAKEVEN, sig=z63, entry="cont"),
                      "TIPS vs nominals, residual to published curve + FRED breakeven, z63")
    F["T_be_z21c"] = ("teth", dict(syms=TIPS_SET, fac=CURVE + BREAKEVEN, sig=z21, entry="cont"),
                      "TIPS vs nominals, published breakeven tether, z21")
    F["T_be_z126c"] = ("teth", dict(syms=TIPS_SET, fac=CURVE + BREAKEVEN, sig=z126, entry="cont"),
                       "TIPS vs nominals, published breakeven tether, z126")
    F["T_be_band15"] = ("teth", dict(syms=TIPS_SET, fac=CURVE + BREAKEVEN, sig=z63, entry=(1.5, 0.5)),
                        "TIPS vs nominals, published breakeven tether, z63 band 1.5/0.5")

    # --- E: ETF vs published-composition synthetic basket ---
    F["E_agg_synth"] = ("syn", dict(etf="AGG", legs=[("IEF", 0.42), ("MBB", 0.28), ("LQD", 0.25), ("SHY", 0.05)], sig=z63, entry="cont"),
                        "AGG vs published-composition basket (IEF/MBB/LQD/SHY)")
    F["E_bnd_synth"] = ("syn", dict(etf="BND", legs=[("IEF", 0.42), ("MBB", 0.28), ("LQD", 0.25), ("SHY", 0.05)], sig=z63, entry="cont"),
                        "BND vs published-composition basket")
    F["E_ushy_split"] = ("syn", dict(etf="USHY", legs=[("HYG", 0.5), ("JNK", 0.5)], sig=z63, entry="cont"),
                         "USHY vs 50/50 HYG+JNK (sum-of-siblings tether)")
    F["E_govt_ladder"] = ("syn", dict(etf="GOVT", legs=[("SHY", 0.35), ("IEI", 0.25), ("IEF", 0.25), ("TLT", 0.15)], sig=z63, entry="cont"),
                          "GOVT vs published-maturity-ladder basket")
    return F, live, clean


def make_weights(D, kind, kw, live, clean=None):
    if kind == "xsc":
        kind, live = "xs", clean
    if kind == "pair":
        W, sp, _ = pair_weights(D, kw["a"], kw["b"], kw["sig"], kw["entry"],
                                kw.get("hedge_w", 0), kw.get("hold", 1))
        return W, sp
    if kind == "xs":
        W, Z = xs_pair_weights(D, live, kw["sig"], kw["entry"], kw.get("hedge_w", 0),
                               kw.get("hold", 1), kw.get("rank", False))
        # spread panel = the per-pair cumulative log-TR difference
        SP = np.array([np.nancumsum(np.nan_to_num(D["lr"][D["si"][a]] - D["lr"][D["si"][b]]))
                       for _, a, b, _ in live])
        return W, SP
    if kind == "teth":
        W, Z = tether_weights(D, kw["syms"], kw["fac"], kw["sig"], kw["entry"], kw.get("fitw", 250))
        R, B, keep = D["resid_cache"][(tuple(kw["syms"]), tuple(kw["fac"]), kw.get("fitw", 250))]
        # spread = cumulative published-tether residual, so d(spread) = the residual itself
        SP = np.nancumsum(np.nan_to_num(R), axis=1)
        SP[np.isnan(R)] = np.nan
        return W, SP
    if kind == "syn":
        W, sp = synth_weights(D, kw["etf"], kw["legs"], kw["sig"], kw["entry"])
        return W, sp
    raise ValueError(kind)


# ----------------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["design", "holdout"], required=True)
    a = ap.parse_args()

    D = load()
    D["lr"] = log_ret(D["adj"])
    px = np.nanmedian(D["close"], axis=1)
    # median dollar volume over the last 750 VALID sessions -- nan_to_num over the full
    # history would count pre-inception days as zero volume and zero out the median
    dv = D["close"] * D["vol"]
    adv = np.zeros(dv.shape[0])
    for i in range(dv.shape[0]):
        v = dv[i][np.isfinite(dv[i])]
        adv[i] = np.median(v[-750:]) if len(v) >= 250 else 0.0
    D["adv"] = adv
    D["hs"] = np.maximum(1.0, 2 * 0.005 / np.where(px > 0, px, 1e9) * 1e4)
    D["hs_lb"] = 0.005 / np.where(px > 0, px, 1e9) * 1e4
    days = np.array([dt.date.fromisoformat(d).toordinal() for d in D["cal"]])
    D["caldays"] = np.concatenate([[1], np.diff(days)]).astype(float)

    lo, hi = DESIGN if a.stage == "design" else HELDOUT
    mask = (D["cal"] >= lo) & (D["cal"] <= hi)
    dmask = (D["cal"] >= DESIGN[0]) & (D["cal"] <= DESIGN[1])
    yrs = mask.sum() / ANN

    # open-to-open TOTAL RETURN: adjusted open = open * (adjclose/close) applies that day's
    # own dividend/split factor to the open print
    op = CACHE / "etf_open.json"
    D["lr_oo"] = np.full(D["lr"].shape, np.nan)
    if op.exists():
        raw = json.loads(op.read_text())
        idx = {d: i for i, d in enumerate(D["cal"])}
        AO = np.full(D["adj"].shape, np.nan)
        for s, v in raw.items():
            if s not in D["si"]:
                continue
            i = D["si"][s]
            for t, o, c in zip(v["t"], v["open"], v["close"]):
                d = dt.datetime.fromtimestamp(t, dt.UTC).strftime("%Y-%m-%d")
                j = idx.get(d)
                if j is None or o is None or not c:
                    continue
                if np.isfinite(D["adj"][i, j]) and np.isfinite(D["close"][i, j]) and D["close"][i, j]:
                    AO[i, j] = o * D["adj"][i, j] / D["close"][i, j]
        D["lr_oo"][:, 1:] = np.log(AO[:, 1:] / AO[:, :-1])
        n_oo = int(np.isfinite(D["lr_oo"][:, mask]).any(axis=1).sum())
        print(f"open-to-open panel: {n_oo} symbols", flush=True)
    else:
        print("open-to-open panel: MISSING (run invent0823_bondrv_ohlc.py)", flush=True)

    # design-window rho1 per sibling pair -- computed BEFORE any Sharpe is looked at
    D["pair_rho1"] = {}
    for nm, aa, bb, fam in PAIRS:
        if aa in D["si"] and bb in D["si"]:
            sp = np.nancumsum(np.nan_to_num(D["lr"][D["si"][aa]] - D["lr"][D["si"][bb]]))
            D["pair_rho1"][nm] = rho1_dspread(sp, dmask)

    F, live, clean = build_formulas(D)
    print(f"universe: {len(live)} sibling pairs pass ADV>=${MIN_ADV_USD/1e6:.0f}M; "
          f"{len(clean)} also pass rho1>{RHO1_FLOOR}", flush=True)
    print("  pair rho1 (design):", {k: round(v, 3) for k, v in D["pair_rho1"].items()
                                    if np.isfinite(v)}, flush=True)

    # cache tether residuals once (expensive)
    D["resid_cache"] = {}
    for k, (kind, kw, desc) in F.items():
        if kind == "teth":
            key = (tuple(kw["syms"]), tuple(kw["fac"]), kw.get("fitw", 250))
            if key not in D["resid_cache"]:
                print(f"  fitting published-tether residuals {key[1]} fitw={key[2]} ...", flush=True)
                D["resid_cache"][key] = resid_curve(D, list(key[0]), list(key[1]), key[2])

    # ---- build every book once
    books, res, daily_gross, daily_gross_oo = {}, {}, {}, {}
    for k, (kind, kw, desc) in F.items():
        W, sp = make_weights(D, kind, kw, live, clean)
        if W is None:
            continue
        books[k] = W
        r1, r1w = np.nan, np.nan
        if sp is not None:
            S = np.atleast_2d(sp)
            rs = np.array([rho1_dspread(S[i], dmask) for i in range(S.shape[0])])
            rs = rs[np.isfinite(rs)]
            if len(rs):
                r1, r1w = float(np.median(rs)), float(np.min(rs))
        e1 = evaluate(D, W, 1, mask)
        e2 = evaluate(D, W, 2, mask)
        elb = evaluate(D, W, 1, mask, lb=True)
        eoo = evaluate(D, W, 2, mask, ret="oo")     # signal close(t), fill open(t+1)
        res[k] = dict(desc=desc, kind=kind, rho1=r1, rho1_worst=r1w,
                      gross=e1["gross_sharpe"], net=e1["net_sharpe"],
                      net_lag2=e2["net_sharpe"], gross_lag2=e2["gross_sharpe"],
                      net_tickfloor=elb["net_sharpe"],
                      gross_oo=eoo["gross_sharpe"], net_oo=eoo["net_sharpe"],
                      gross_bpd_oo=eoo["gross_bpd"], cost_bpd_oo=eoo["cost_bpd"],
                      net_bpd_oo=eoo["net_bpd"], turn_oo=eoo["turn"],
                      net_oo_tickfloor=evaluate(D, W, 2, mask, lb=True, ret="oo")["net_sharpe"],
                      gross_bpd=e1["gross_bpd"], cost_bpd=e1["cost_bpd"],
                      borrow_bpd=e1["borrow_bpd"], net_bpd=e1["net_bpd"],
                      turn=e1["turn"], days=e1["days"])
        daily_gross[k] = e1["daily_gross"]
        daily_gross_oo[k] = eoo["daily_gross"]
        print(f"  {k:22s} rho1={r1: .3f} gross={res[k]['gross']: .2f} net={res[k]['net']: .2f} "
              f"grL2={res[k]['gross_lag2']: .2f} grOO={res[k]['gross_oo']: .2f} "
              f"netOO={res[k]['net_oo']: .2f} turn={res[k]['turn']:.3f}", flush=True)

    N = len(res)
    analytic = float(np.sqrt(2 * np.log(N)) / np.sqrt(yrs))

    # ---- SIZE-MATCHED PLACEBO: rotate the SIGNAL, keep returns + construction
    print(f"\nplacebo: {N_PLACEBO} signal-rotation draws over N={N} formulas ...", flush=True)
    T = D["adj"].shape[1]
    rng = np.random.default_rng(20260823)
    maxes, maxes_oo = [], []
    for it in range(N_PLACEBO):
        off = int(rng.integers(63, T - 63))
        m, moo = [], []
        for k, W in books.items():
            Wr = np.roll(W, off, axis=1)
            m.append(evaluate(D, Wr, 1, mask)["gross_sharpe"])
            moo.append(evaluate(D, Wr, 2, mask, ret="oo")["gross_sharpe"])
        maxes.append(np.nanmax(m))
        maxes_oo.append(np.nanmax(moo))
        if (it + 1) % 100 == 0:
            print(f"    draw {it+1}: p95 cc={np.nanpercentile(maxes, 95):.2f} "
                  f"oo={np.nanpercentile(maxes_oo, 95):.2f}", flush=True)
    placebo = dict(mean=float(np.nanmean(maxes)), p95=float(np.nanpercentile(maxes, 95)),
                   p99=float(np.nanpercentile(maxes, 99)), draws=N_PLACEBO)
    placebo_oo = dict(mean=float(np.nanmean(maxes_oo)), p95=float(np.nanpercentile(maxes_oo, 95)),
                      p99=float(np.nanpercentile(maxes_oo, 99)), draws=N_PLACEBO)

    # ---- stationary block bootstrap of the DEMEANED daily gross PnL, same day indices
    # across all formulas so their cross-correlation survives.  Daily RV PnL is fat-tailed
    # and autocorrelated; the analytic bar assumes neither.
    blk = 5

    def block_boot(dg):
        G = np.array([dg[k] for k in books])
        G = G - np.nanmean(G, axis=1, keepdims=True)
        nd = G.shape[1]
        bmax = []
        for _ in range(N_PLACEBO):
            idx = []
            while len(idx) < nd:
                s = int(rng.integers(0, nd))
                idx.extend(((s + np.arange(blk)) % nd).tolist())
            Gb = G[:, np.array(idx[:nd])]
            sh = np.nanmean(Gb, axis=1) / np.nanstd(Gb, axis=1) * np.sqrt(ANN)
            bmax.append(np.nanmax(np.abs(sh)))
        bmax = np.array(bmax)
        return dict(mean=float(np.mean(bmax)), p95=float(np.percentile(bmax, 95)),
                    p99=float(np.percentile(bmax, 99)), draws=N_PLACEBO, block=blk)

    boot = block_boot(daily_gross)
    boot_oo = block_boot(daily_gross_oo)

    bar = max(analytic, placebo["p95"], boot["p95"])
    bar_oo = max(analytic, placebo_oo["p95"], boot_oo["p95"])
    for k in res:
        res[k]["beats_analytic"] = bool(res[k]["gross"] > analytic)
        res[k]["beats_placebo"] = bool(res[k]["gross"] > placebo["p95"])
        res[k]["beats_bootstrap"] = bool(res[k]["gross"] > boot["p95"])
        res[k]["passes_rho1"] = bool(np.isfinite(res[k]["rho1"]) and res[k]["rho1"] > RHO1_FLOOR)
        res[k]["passes_lagkill"] = bool(np.isfinite(res[k]["gross_lag2"])
                                        and res[k]["gross_lag2"] > bar)
        # SCORED VERDICT.  The L=1 close-to-close book is filled at the very print its signal
        # was computed from, so it is not the executable structure; the open-to-open book is.
        res[k]["REAL"] = bool(res[k]["passes_rho1"]
                              and np.isfinite(res[k]["gross_oo"]) and res[k]["gross_oo"] > bar_oo
                              and res[k]["net_oo"] > 0)

    out = dict(stage=a.stage, window=[lo, hi], years=yrs, n_formulas=N,
               analytic_bar=analytic,
               placebo_cc=placebo, bootstrap_cc=boot, bar_cc=bar,
               placebo_oo=placebo_oo, bootstrap_oo=boot_oo, bar_oo=bar_oo,
               rho1_floor=RHO1_FLOOR, results=res,
               pairs=[p[0] for p in live], clean_pairs=[p[0] for p in clean],
               pair_rho1_design={k: v for k, v in D["pair_rho1"].items() if np.isfinite(v)})
    p = OUT / f"{KEY}_{a.stage.upper()}.json"
    p.write_text(json.dumps(out, indent=1, default=float))
    print(f"\nN={N} yrs={yrs:.1f}  analytic={analytic:.2f}")
    print(f"  close-to-close: placebo p95={placebo['p95']:.2f} bootstrap p95={boot['p95']:.2f} BAR={bar:.2f}")
    print(f"  open-to-open  : placebo p95={placebo_oo['p95']:.2f} bootstrap p95={boot_oo['p95']:.2f} BAR={bar_oo:.2f}")
    surv = [k for k in res if res[k]["REAL"]]
    print(f"SURVIVORS (rho1 + OO gross>bar + OO net>0): {surv or 'NONE'}")
    print(f"wrote {p}")


if __name__ == "__main__":
    main()
