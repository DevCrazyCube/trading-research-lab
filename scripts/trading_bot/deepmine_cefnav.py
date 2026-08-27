#!/usr/bin/env python3
"""DEEPMINE_CEFNAV -- wide search inside the CEF NAV-discount family.

Sub-family: closed-end-fund / fund NAV-discount relative value.
Incumbent already in the basket (slot L5, "T12CEF"): cross-sectional DISCOUNT LEVEL decile
tilt, ETB-short-screened, price>$5, 4-week hold weekly-overlapping, dollar-neutral.

This module asks a different question from t12_evaluate.py: NOT "does the discount level tilt
work" (answered: yes, held out at ann Sharpe 2.35) but "is there anything in this family that
is NOT that". Every candidate is therefore scored twice:

  * raw held-out Sharpe (does it stand alone), and
  * ALPHA to the incumbent (regress candidate net weekly returns on incumbent net weekly
    returns; the intercept is the part the basket does not already own).

DESIGN WINDOW ONLY for selection. The held-out block is computed in the same pass but is
written to a separate section of the JSON and is NEVER used to pick anything -- the ranking,
the "best", and the basket-ready list are all decided on design-window numbers plus the
a-priori noise bar, exactly as the pre-registration in the .md says.

Data: 100 % cached / free.
  research/data/t12_cache/history_5Y.json.gz   weekly price/NAV/discount, 353 funds, 249 dates
  research/data/t12_cache/adjusted_bars.json.gz  Alpaca SIP daily closes, adjustment=all
  research/data/t12_cache/universe.json.gz     CEFConnect statics (category, sponsor, term...)
  research/data/t12_cache/alpaca_assets.json.gz  live ETB / shortable flags
  research/data/t12_cache/cef_half_spread.json.gz measured 11.53 bp median CEF half-spread
No network access is performed.
"""

from __future__ import annotations

import gzip
import json
import math
import pathlib
import sys
from collections import defaultdict

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[2]
CACHE = ROOT / "research" / "data" / "t12_cache"
OUT = ROOT / "research" / "trading_bot"

# ---------------------------------------------------------------------------
# frozen conventions (T6/T8/M0): costs are charged, never assumed away
# ---------------------------------------------------------------------------
HALF_SPREAD_BP = 11.53          # T12 first-party SIP measurement, median CEF symbol-day
SEC31_BP = 0.278                # of SALE notional
BORROW_ANNUAL_BP = 200.0        # REALISED short rate, not the 33 bp ETB floor (L5 guard)
MIN_PRICE = 5.0
DECILE = 0.10
WEEKS_PER_YEAR = 52.0
SPLIT = "2024-03-01"            # T12's frozen split; design < SPLIT, held out >= SPLIT


def _load(name):
    with gzip.open(CACHE / f"{name}.json.gz", "rt") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# 1. panel
# ---------------------------------------------------------------------------

def build_panel():
    uni = _load("universe")
    hist = _load("history_5Y")
    bars = _load("adjusted_bars")
    flags = _load("alpaca_assets")

    tickers_all = sorted({r["Ticker"] for r in uni if r.get("Ticker")})
    by_date = defaultdict(dict)
    for tkr, rows in hist.items():
        for r in rows or []:
            if r["price"] and r["nav"] and r["discount"] is not None:
                by_date[r["date"]][tkr] = r

    # same structural hygiene rule as T12: half the live universe must be quoted
    dropped = sorted(d for d in by_date if len(by_date[d]) < len(tickers_all) / 2)
    grid = sorted(d for d in by_date if d not in set(dropped))

    tickers = [t for t in tickers_all if any(t in by_date[d] for d in grid)]
    ti = {t: i for i, t in enumerate(tickers)}
    T, N = len(grid), len(tickers)

    D = np.full((T, N), np.nan)      # discount, % , negative = discount
    P = np.full((T, N), np.nan)      # raw close (CEFConnect)
    V = np.full((T, N), np.nan)      # NAV
    A = np.full((T, N), np.nan)      # adjusted close (Alpaca, adjustment=all)
    for k, d in enumerate(grid):
        row = by_date[d]
        for t, r in row.items():
            i = ti[t]
            D[k, i] = r["discount"]
            P[k, i] = r["price"]
            V[k, i] = r["nav"]
    for t, series in bars.items():
        i = ti.get(t)
        if i is None:
            continue
        for k, d in enumerate(grid):
            v = series.get(d)
            if v:
                A[k, i] = v

    # weekly TOTAL return, grid[k] -> grid[k+1]
    R = np.full((T, N), np.nan)
    R[:-1] = A[1:] / A[:-1] - 1.0
    # IMPLEMENTATION LAG: CEFConnect publishes NAV for date d after that close (the snapshot's
    # NAVPublished trails LastUpdated by one session), so a discount observed on grid[k] is
    # actionable no earlier than the NEXT trading session's close. Rebuild the weekly return
    # on a grid shifted one trading day forward, from the DAILY adjusted bars.
    all_days = sorted({d for s in bars.values() for d in s})
    day_ix = {d: j for j, d in enumerate(all_days)}
    nxt = []
    for d in grid:
        j = day_ix.get(d)
        if j is None:
            j = np.searchsorted(all_days, d)
            j = int(j) - 1 if j >= len(all_days) else int(j)
        nxt.append(all_days[min(j + 1, len(all_days) - 1)])
    AL = np.full((T, N), np.nan)
    for t, series in bars.items():
        i = ti.get(t)
        if i is None:
            continue
        for k, d in enumerate(nxt):
            v = series.get(d)
            if v:
                AL[k, i] = v
    R_LAG1 = np.full((T, N), np.nan)
    R_LAG1[:-1] = AL[1:] / AL[:-1] - 1.0

    # weekly PRICE return on the raw close
    RP = np.full((T, N), np.nan)
    RP[:-1] = P[1:] / P[:-1] - 1.0
    # point-in-time weekly DISTRIBUTION yield = total return - price return
    Y = R - RP
    Y[~np.isfinite(Y)] = np.nan
    Y = np.where((Y < -0.002) | (Y > 0.06), np.nan, Y)   # split / stale-print guard
    Y = np.where(Y < 0, 0.0, Y)
    # NAV total return = NAV price return + the same distribution
    RV = np.full((T, N), np.nan)
    RV[:-1] = V[1:] / V[:-1] - 1.0
    RVT = RV + np.nan_to_num(Y)

    statics = {r["Ticker"]: r for r in uni}
    etb = np.array([bool(flags.get(t) and flags[t].get("easy_to_borrow")) for t in tickers])
    cat = np.array([statics.get(t, {}).get("CategoryName") or "?" for t in tickers])
    spon = np.array([statics.get(t, {}).get("SponsorName") or "?" for t in tickers])
    term = np.array([bool(statics.get(t, {}).get("Term")) for t in tickers])
    lev = np.array([bool(statics.get(t, {}).get("IsLeveraged")) for t in tickers])

    def group(c):
        if "Municipal" in c or "Taxable Muni" in c:
            return "MUNI"
        if c in ("Morningstar US CEF High Yield", "Morningstar US CEF Senior Loans",
                 "Morningstar US CEF Investment Grade", "Morningstar US CEF Preferreds",
                 "Morningstar US CEF Multi-Sector", "Morningstar US CEF Global Income",
                 "Morningstar US CEF Convertibles", "Morningstar US CEF Limited Duration",
                 "Morningstar US CEF Emerging Market Income"):
            return "TAXFI"
        if "Allocation" in c:
            return "HYBRID"
        return "EQUITY"

    grp = np.array([group(c) for c in cat])

    # today's dollar-ADV: a LOOK-AHEAD screen, used only as a declared robustness stress
    dadv = np.array([(statics.get(t, {}).get("AvgDailyVolume") or 0)
                     * (statics.get(t, {}).get("Price") or 0) for t in tickers])
    liquid = dadv > 1e6

    return dict(grid=grid, tickers=tickers, D=D, P=P, V=V, A=A, R=R, R_LAG1=R_LAG1,
                RP=RP, Y=Y, RVT=RVT, etb=etb, cat=cat, spon=spon, term=term, lev=lev,
                grp=grp, liquid=liquid, dropped=dropped, statics=statics)


# ---------------------------------------------------------------------------
# 2. signal primitives (all STRICTLY trailing: index k uses rows <= k)
# ---------------------------------------------------------------------------

def _roll_mean(X, L):
    T, N = X.shape
    out = np.full((T, N), np.nan)
    for k in range(L, T):
        w = X[k - L + 1:k + 1]
        cnt = np.sum(np.isfinite(w), axis=0)
        s = np.nansum(w, axis=0)
        out[k] = np.where(cnt >= L * 0.8, s / np.maximum(cnt, 1), np.nan)
    return out


def _roll_std(X, L):
    T, N = X.shape
    out = np.full((T, N), np.nan)
    for k in range(L, T):
        w = X[k - L + 1:k + 1]
        cnt = np.sum(np.isfinite(w), axis=0)
        m = np.nansum(w, axis=0) / np.maximum(cnt, 1)
        v = np.nansum((w - m) ** 2, axis=0) / np.maximum(cnt, 1)
        out[k] = np.where(cnt >= L * 0.8, np.sqrt(v), np.nan)
    return out


def _roll_pct_rank(X, L):
    """percentile position of X[k] inside its own trailing-L window, in [0,1]."""
    T, N = X.shape
    out = np.full((T, N), np.nan)
    for k in range(L, T):
        w = X[k - L + 1:k + 1]
        cur = X[k]
        cnt = np.sum(np.isfinite(w), axis=0)
        below = np.sum(np.isfinite(w) & (w < cur), axis=0)
        out[k] = np.where(cnt >= L * 0.8, below / np.maximum(cnt, 1), np.nan)
    return out


def _roll_sum(X, L):
    T, N = X.shape
    out = np.full((T, N), np.nan)
    Xf = np.nan_to_num(X)
    ok = np.isfinite(X).astype(float)
    for k in range(L, T):
        cnt = ok[k - L + 1:k + 1].sum(axis=0)
        out[k] = np.where(cnt >= L * 0.8, Xf[k - L + 1:k + 1].sum(axis=0), np.nan)
    return out


def _lag_diff(X, L):
    T, N = X.shape
    out = np.full((T, N), np.nan)
    out[L:] = X[L:] - X[:-L]
    return out


def _demean_by(X, keys):
    """subtract the cross-sectional MEDIAN of X within each key group, per date."""
    out = np.full(X.shape, np.nan)
    uk = np.unique(keys)
    for g in uk:
        m = keys == g
        sub = X[:, m]
        med = np.nanmedian(sub, axis=1, keepdims=True)
        out[:, m] = sub - med
    return out


def _xs_resid(Yv, Xv):
    """per-date cross-sectional OLS residual of Yv on [1, Xv]."""
    T = Yv.shape[0]
    out = np.full(Yv.shape, np.nan)
    for k in range(T):
        y, x = Yv[k], Xv[k]
        m = np.isfinite(y) & np.isfinite(x)
        if m.sum() < 30:
            continue
        xm, ym = x[m], y[m]
        vx = np.var(xm)
        if vx <= 0:
            continue
        b = np.cov(xm, ym, bias=True)[0, 1] / vx
        a = ym.mean() - b * xm.mean()
        out[k, m] = ym - (a + b * xm)
    return out


# ---------------------------------------------------------------------------
# 3. book construction + net returns
# ---------------------------------------------------------------------------

def book_from_score(S, pnl, *, H, mask=None, within=None, frac=DECILE,
                    weight="equal", min_names=20):
    """Return (W, n_long, n_short) with W[k] the ACTIVE book held over week k -> k+1.

    Long the HIGH score, short the LOW score. Short leg is restricted to ETB names.
    `within` (an array of group labels) makes the book group-neutral: the quantile cut and the
    dollar-neutrality are enforced INSIDE each group.
    Overlapping tranches: the held book at k is the mean of the last H tranche targets.
    """
    T, N = S.shape
    etb = pnl["etb"]
    price_ok = pnl["P"] > MIN_PRICE
    tranche = np.zeros((T, N))
    counts = []

    groups = [np.ones(N, dtype=bool)] if within is None else \
             [within == g for g in np.unique(within)]

    for k in range(T):
        base = np.isfinite(S[k]) & price_ok[k]
        if mask is not None:
            base &= mask[k] if mask.ndim == 2 else mask
        tgt = np.zeros(N)
        nl = ns = 0
        for gm in groups:
            m = base & gm
            idx = np.flatnonzero(m)
            if idx.size < min_names:
                continue
            order = idx[np.argsort(S[k, idx])]
            n = max(1, int(round(order.size * frac)))
            lo = order[-n:]                       # highest score -> LONG
            sh = order[:n]
            sh = sh[etb[sh]]                      # short leg must be borrowable
            if sh.size == 0:
                continue
            if weight == "equal":
                wl = np.ones(lo.size)
                ws = np.ones(sh.size)
            else:                                  # signal-proportional
                zl = S[k, lo] - S[k, order].mean()
                zs = S[k, order].mean() - S[k, sh]
                wl = np.maximum(zl, 1e-9)
                ws = np.maximum(zs, 1e-9)
            gw = 1.0 / len(groups)
            tgt[lo] += 0.5 * gw * wl / wl.sum()
            tgt[sh] -= 0.5 * gw * ws / ws.sum()
            nl += lo.size
            ns += sh.size
        counts.append((nl, ns))
        tranche[k] = tgt

    W = np.zeros((T, N))
    for k in range(T):
        lo = max(0, k - H + 1)
        act = tranche[lo:k + 1]
        live = np.any(np.abs(act) > 0, axis=1)
        if live.sum() == 0:
            continue
        W[k] = act[live].mean(axis=0)
    return W, counts


def net_series(W, pnl, k_lo, k_hi, *, rkey="R", half_spread_bp=HALF_SPREAD_BP):
    """Weekly NET return over [k_lo, k_hi) with all frictions charged."""
    R = np.nan_to_num(pnl[rkey])
    have = np.isfinite(pnl[rkey])
    hs = half_spread_bp * 1e-4
    sec = SEC31_BP * 1e-4
    out = []
    for k in range(k_lo, k_hi):
        w = W[k]
        prev = W[k - 1] if k > 0 else np.zeros_like(w)
        if np.abs(w).sum() < 1e-9:
            continue
        gross = float(np.sum(w * R[k] * have[k]))
        turn = float(np.abs(w - prev).sum())
        cost = turn * hs + 0.5 * turn * sec
        short_notional = float(np.abs(np.minimum(w, 0)).sum())
        days = 7.0
        borrow = short_notional * (BORROW_ANNUAL_BP * 1e-4) * days / 365.0
        out.append((gross, gross - cost - borrow, turn))
    return np.array(out) if out else np.zeros((0, 3))


def summarise(x):
    n = len(x)
    if n < 8:
        return None
    m = float(np.mean(x))
    s = float(np.std(x, ddof=1))
    t = m / s * math.sqrt(n) if s > 0 else 0.0
    return dict(n=n, mean_bp=m * 1e4, sd_bp=s * 1e4, t=t,
                ann_sharpe=(m / s * math.sqrt(WEEKS_PER_YEAR)) if s > 0 else 0.0)


# ---------------------------------------------------------------------------
# 4. the formula catalogue
# ---------------------------------------------------------------------------

def catalogue(pnl):
    D, P, V, R, Y, RVT = pnl["D"], pnl["P"], pnl["V"], pnl["R"], pnl["Y"], pnl["RVT"]
    cat, spon, grp, term, lev = pnl["cat"], pnl["spon"], pnl["grp"], pnl["term"], pnl["lev"]
    T, N = D.shape

    z52 = (D - _roll_mean(D, 52)) / np.where(_roll_std(D, 52) > 0, _roll_std(D, 52), np.nan)
    z26 = (D - _roll_mean(D, 26)) / np.where(_roll_std(D, 26) > 0, _roll_std(D, 26), np.nan)
    z13 = (D - _roll_mean(D, 13)) / np.where(_roll_std(D, 13) > 0, _roll_std(D, 13), np.nan)
    pr52 = _roll_pct_rank(D, 52)
    dist52 = D - _roll_mean(D, 52)
    yld52 = _roll_sum(Y, 52)

    dd1, dd4, dd13, dd26 = (_lag_diff(D, k) for k in (1, 4, 13, 26))
    accel = dd4 - np.roll(dd4, 4, axis=0)
    accel[:8] = np.nan

    # price-vs-NAV cumulative total-return spread (return space, not pct-point space)
    lp = np.log1p(np.nan_to_num(R, nan=0.0)) * np.isfinite(R)
    lv = np.log1p(np.nan_to_num(RVT, nan=0.0)) * np.isfinite(RVT)
    spread = lp - lv
    cum4 = _roll_sum(np.vstack([np.full((1, N), np.nan), spread[:-1]]), 4)
    cum13 = _roll_sum(np.vstack([np.full((1, N), np.nan), spread[:-1]]), 13)
    navmom4 = _roll_sum(np.vstack([np.full((1, N), np.nan), lv[:-1]]), 4)
    navmom13 = _roll_sum(np.vstack([np.full((1, N), np.nan), lv[:-1]]), 13)

    med_y = np.nanmedian(yld52, axis=1, keepdims=True)
    hi_y = yld52 >= med_y
    lo_y = yld52 < med_y

    F = []      # (key, description, score, kwargs)

    def add(key, desc, score, **kw):
        F.append(dict(key=key, desc=desc, score=score, kw=kw))

    # ---- reference: the incumbent, so collinearity is measurable ----
    add("REF_T12_LEVEL", "INCUMBENT L5: cross-sectional discount LEVEL decile tilt",
        -D, H=4, reference=True)
    # second control: the SAME incumbent signal at the other horizon. Without it, any H=1
    # candidate can show "alpha to L5" that is nothing but the horizon difference.
    add("REF_T12_LEVEL_H1", "control: the incumbent signal at a 1-week hold",
        -D, H=1, reference=True)

    # ---- B. sector / sponsor neutralisation of the level ----
    add("C01_cat_demean_H4", "discount level demeaned by Morningstar CATEGORY median",
        -_demean_by(D, cat), H=4)
    add("C02_cat_within_H4", "book formed WITHIN each category (category-neutral book)",
        -D, H=4, within=cat)
    add("C03_grp_demean_H4", "discount level demeaned by broad group (muni/taxfi/eq/hybrid)",
        -_demean_by(D, grp), H=4)
    add("C04_grp_within_H4", "book formed WITHIN each broad group",
        -D, H=4, within=grp)
    add("C05_sponsor_demean_H4", "discount level demeaned by SPONSOR median",
        -_demean_by(D, spon), H=4)

    # ---- D. own-history normalisation ----
    add("Z01_pctrank52_H4", "percentile rank of discount in its own trailing 52w history",
        -pr52, H=4)
    add("Z02_dist52_H4", "discount minus own trailing-52w MEAN (unstandardised)",
        -dist52, H=4)
    add("Z03_z13_H4", "z-score of discount, trailing 13w", -z13, H=4)
    add("Z04_z52_resid_level_H4",
        "z52 ORTHOGONALISED to the cross-sectional level (built to not be the incumbent)",
        -_xs_resid(z52, D), H=4)
    add("Z05_z26_resid_level_H4", "z26 orthogonalised to the cross-sectional level",
        -_xs_resid(z26, D), H=4)

    # ---- E. discount momentum vs reversion ----
    add("M01_dd1_fade_H1", "fade 1-week discount CHANGE (widened -> long)", -dd1, H=1)
    add("M02_dd4_fade_H4", "fade 4-week discount change", -dd4, H=4)
    add("M03_dd13_fade_H4", "fade 13-week discount change", -dd13, H=4)
    add("M04_dd26_fade_H4", "fade 26-week discount change", -dd26, H=4)
    add("M05_accel_fade_H4", "fade discount ACCELERATION (dd4 minus dd4 lagged 4)",
        -accel, H=4)

    # ---- F. price-vs-NAV return spread ----
    add("S01_cum4_fade_H4", "fade 4w cumulative (price TR - NAV TR) log spread", -cum4, H=4)
    add("S02_cum13_fade_H4", "fade 13w cumulative price-minus-NAV spread", -cum13, H=4)
    add("S03_navmom4_H4", "long 4w NAV total-return momentum (price under-reaction)",
        navmom4, H=4)
    add("S04_navmom13_H4", "long 13w NAV total-return momentum", navmom13, H=4)

    # ---- G. distribution-yield conditioning (PIT yield from adjusted-vs-raw) ----
    add("Y01_yield_tilt_H4", "long high trailing-52w PIT distribution yield, no discount",
        yld52, H=4)
    add("Y02_level_resid_yield_H4",
        "discount level orthogonalised to trailing distribution yield",
        -_xs_resid(D, yld52), H=4)
    add("Y03_level_in_hiyield_H4", "discount level tilt, HIGH-yield half only",
        -D, H=4, mask=hi_y)
    add("Y04_level_in_loyield_H4", "discount level tilt, LOW-yield half only",
        -D, H=4, mask=lo_y)

    # DISENTANGLER: the low-yield half is 44% muni / 33% equity / 16% taxable-credit, so a
    # static sector screen could produce the same book without any yield in it. These two
    # separate "low PIT yield" from "not a credit fund".
    add("Y05_muni_eq_static_H4", "level tilt inside MUNI+EQUITY only (static sector twin of "
        "the low-yield half, contains NO yield information)",
        -D, H=4, mask=np.tile((grp == "MUNI") | (grp == "EQUITY"), (T, 1)))
    add("Y06_loyield_within_taxfi_H4",
        "level tilt in the LOW-yield half of the TAXABLE-CREDIT group only (yield conditioner "
        "with the sector split held fixed)",
        -D, H=4, mask=lo_y & np.tile(grp == "TAXFI", (T, 1)), min_names=10)

    # ---- H. structural screens ----
    tmask = np.tile(term, (T, 1))
    lmask = np.tile(lev, (T, 1))
    add("X01_term_only_H4", "discount level tilt inside TERM funds only (mandated wind-up)",
        -D, H=4, mask=tmask, min_names=10)
    add("X02_levered_H4", "discount level tilt, LEVERAGED funds only", -D, H=4, mask=lmask)
    add("X03_muni_H4", "discount level tilt, MUNI funds only", -D, H=4,
        mask=np.tile(grp == "MUNI", (T, 1)))
    add("X04_equity_H4", "discount level tilt, EQUITY funds only", -D, H=4,
        mask=np.tile(grp == "EQUITY", (T, 1)))
    add("X05_taxfi_H4", "discount level tilt, TAXABLE-FI funds only", -D, H=4,
        mask=np.tile(grp == "TAXFI", (T, 1)))

    # ---- I. construction variants on a NEUTRALISED level ----
    add("W01_cat_demean_prop_H4", "category-demeaned level, SIGNAL-PROPORTIONAL weights",
        -_demean_by(D, cat), H=4, weight="prop")
    add("W02_cat_demean_quintile_H4", "category-demeaned level, QUINTILE cut",
        -_demean_by(D, cat), H=4, frac=0.20)
    thr = np.where(np.abs(np.nan_to_num(z52, nan=0.0)) > 1.5, 1.0, 0.0) > 0
    add("W03_z52_threshold_H4", "level tilt only among names with |z52| > 1.5",
        -D, H=4, mask=thr)

    # every structure is also run at the other horizon
    extra = []
    for f in F:
        if f["kw"].get("reference"):
            continue
        H = f["kw"].get("H", 4)
        alt = 1 if H == 4 else 4
        kw = dict(f["kw"])
        kw["H"] = alt
        extra.append(dict(key=f["key"].rsplit("_H", 1)[0] + f"_H{alt}",
                          desc=f["desc"] + f" [hold {alt}w]", score=f["score"], kw=kw))
    F.extend(extra)
    return F


# ---------------------------------------------------------------------------
# 5. run
# ---------------------------------------------------------------------------

def main(stage="design"):
    pnl = build_panel()
    grid = pnl["grid"]
    T = len(grid)
    split_k = next(k for k, d in enumerate(grid) if d >= SPLIT)
    # last usable rebalance index: needs grid[k+1] for the return
    k_end = T - 1

    F = catalogue(pnl)
    refs = [f for f in F if f["kw"].get("reference")]
    ref = refs[0]
    ref_h1 = refs[1]

    def run(f, liquid_only=False):
        kw = dict(f["kw"])
        kw.pop("reference", None)
        H = kw.pop("H")
        if liquid_only:
            lm = np.tile(pnl["liquid"], (T, 1))
            kw["mask"] = lm if kw.get("mask") is None else (kw["mask"] & lm)
        W, counts = book_from_score(f["score"], pnl, H=H, **kw)
        # warm-up: first index where the book is non-empty
        live = np.flatnonzero(np.abs(W).sum(axis=1) > 1e-9)
        if live.size == 0:
            return None
        k0 = int(live[0])
        des = net_series(W, pnl, max(k0, 0), split_k)
        hld = net_series(W, pnl, max(k0, split_k), k_end)
        nl = [c[0] for c in counts if c[0]]
        ns = [c[1] for c in counts if c[1]]
        def ladder(a, b):
            return dict(
                lag1_trading_day=summarise(
                    net_series(W, pnl, a, b, rkey="R_LAG1")[:, 1]),
                spread_p75_18p38=summarise(
                    net_series(W, pnl, a, b, half_spread_bp=18.38)[:, 1]),
                spread_p90_27p25=summarise(
                    net_series(W, pnl, a, b, half_spread_bp=27.25)[:, 1]),
                lag1_and_p90=summarise(
                    net_series(W, pnl, a, b, rkey="R_LAG1", half_spread_bp=27.25)[:, 1]),
            )
        lo_d = max(k0, 0)
        stress = ladder(lo_d, split_k)
        hstress = ladder(max(k0, split_k), k_end)
        hlag = net_series(W, pnl, max(k0, split_k), k_end,
                          rkey="R_LAG1", half_spread_bp=27.25)[:, 1]
        return dict(W=W, design=des, held=hld, k0=k0, stress=stress,
                    hstress=hstress, hlag=hlag,
                    n_long_med=float(np.median(nl)) if nl else 0,
                    n_short_med=float(np.median(ns)) if ns else 0,
                    turnover_med=float(np.median(des[:, 2])) if len(des) else None)

    ref_run = run(ref)
    ref_stress = ref_run["stress"]
    ref_des_net = ref_run["design"][:, 1]
    ref_hld_net = ref_run["held"][:, 1]
    r1 = run(ref_h1)
    ref1_des_net, ref1_hld_net = r1["design"][:, 1], r1["held"][:, 1]
    ref_hlag, ref1_hlag = ref_run["hlag"], r1["hlag"]
    reveal = stage == "reveal"

    def reg2(y, f1, f2):
        """alpha of y on [1, f1, f2] -- the incumbent at BOTH horizons."""
        n = min(len(y), len(f1), len(f2))
        if n < 20:
            return None
        y, X = y[-n:], np.column_stack([np.ones(n), f1[-n:], f2[-n:]])
        b, *_ = np.linalg.lstsq(X, y, rcond=None)
        resid = y - X @ b
        s2 = resid @ resid / (n - 3)
        cov = s2 * np.linalg.pinv(X.T @ X)
        se = math.sqrt(max(cov[0, 0], 0.0))
        sd = float(np.std(resid, ddof=1))
        return dict(alpha_bp=float(b[0]) * 1e4,
                    alpha_t=float(b[0] / se) if se > 0 else 0.0,
                    beta_h4=float(b[1]), beta_h1=float(b[2]),
                    alpha_ann_sharpe=float(b[0] / sd * math.sqrt(52)) if sd > 0 else 0.0)

    rows = []
    for f in F:
        if f["kw"].get("reference"):
            continue
        r = run(f)
        if r is None or len(r["design"]) < 20 or len(r["held"]) < 20:
            continue
        d_sum = summarise(r["design"][:, 1])
        d_gross = summarise(r["design"][:, 0])
        h_sum = summarise(r["held"][:, 1])
        dn = r["design"][:, 1]
        half = len(dn) // 2
        r["stress"]["design_first_half"] = summarise(dn[:half])
        r["stress"]["design_second_half"] = summarise(dn[half:])
        rl = run(f, liquid_only=True)
        r["stress"]["liquid_dadv_gt_1m"] = (summarise(rl["design"][:, 1])
                                            if rl is not None else None)
        # collinearity + alpha vs the incumbent
        def align(a, b):
            n = min(len(a), len(b))
            return a[-n:], b[-n:]
        ad, bd = align(r["design"][:, 1], ref_des_net)
        ah, bh = align(r["held"][:, 1], ref_hld_net)

        def reg(y, x):
            if np.std(x) <= 0 or len(y) < 10:
                return None
            b = np.cov(x, y, bias=True)[0, 1] / np.var(x)
            a = y.mean() - b * x.mean()
            resid = y - (a + b * x)
            se = np.std(resid, ddof=2) / math.sqrt(len(y))
            return dict(beta=float(b), alpha_bp=float(a) * 1e4,
                        alpha_t=float(a / se) if se > 0 else 0.0,
                        corr=float(np.corrcoef(x, y)[0, 1]),
                        alpha_ann_sharpe=float(a / np.std(resid, ddof=1) * math.sqrt(52))
                        if np.std(resid, ddof=1) > 0 else 0.0)

        rows.append(dict(
            key=f["key"], desc=f["desc"], hold_weeks=f["kw"].get("H"),
            n_long_med=r["n_long_med"], n_short_med=r["n_short_med"],
            turnover_med=r["turnover_med"],
            design=d_sum, design_gross=d_gross, design_stress=r["stress"],
            held_out=h_sum if reveal else "SEALED",
            held_out_stress=r["hstress"] if reveal else "SEALED",
            design_vs_incumbent=reg(ad, bd),
            design_alpha_2factor=reg2(r["design"][:, 1], ref_des_net, ref1_des_net),
            held_vs_incumbent=reg(ah, bh) if reveal else "SEALED",
            held_alpha_2factor=(reg2(r["held"][:, 1], ref_hld_net, ref1_hld_net)
                                if reveal else "SEALED"),
            held_alpha_2factor_stressed=(reg2(r["hlag"], ref_hlag, ref1_hlag)
                                         if reveal else "SEALED"),
        ))

    N = len(rows)
    # two-sided search: each score could have been signed either way
    bar_t = math.sqrt(2 * math.log(max(2 * N, 2)))
    doc = dict(
        family="closed-end-fund / fund NAV-discount relative value",
        incumbent=dict(
            slot="L5", id="T12CEF",
            rule="cross-sectional discount LEVEL decile tilt, ETB-short-screened, price>$5, "
                 "4-week hold, weekly overlapping tranches, dollar-neutral",
            design=summarise(ref_des_net), design_stress=ref_stress,
            held_out=summarise(ref_hld_net) if reveal else "SEALED",
        ),
        data=dict(
            source="100% cached: t12_cache (CEFConnect 5Y weekly + Alpaca adjusted daily bars)",
            grid_weeks=T, first=grid[0], last=grid[-1],
            funds=len(pnl["tickers"]), dropped_dates=pnl["dropped"],
            etb_names=int(pnl["etb"].sum()),
            no_bdcs="CEFConnect DailyPricing carries 0 BDCs (26 Morningstar CEF categories, "
                    "all closed-end funds). BDC NAV is quarterly and no free wired source "
                    "exists in this repo, so the BDC branch of the brief is NOT testable here.",
        ),
        window=dict(design=f"{grid[0]} .. {grid[split_k-1]}",
                    held_out=f"{grid[split_k]} .. {grid[-1]}",
                    split=SPLIT,
                    holdout_is_not_virgin_at_family_level=(
                        "The incumbent L5 was already measured in this block at ann Sharpe "
                        "2.35. A new formula that merely correlates with it will inherit that "
                        "number. The decisive held-out statistic is therefore the ALPHA to the "
                        "incumbent, not the raw Sharpe -- both are reported."),
        ),
        costs=dict(half_spread_bp=HALF_SPREAD_BP, sec31_bp_on_sold=SEC31_BP,
                   borrow_annual_bp_on_short=BORROW_ANNUAL_BP,
                   note="both legs charged the measured CEF half-spread on realised turnover; "
                        "borrow charged at the REALISED 200 bp short rate on the short half, "
                        "not the 33 bp ETB floor; short leg screened to Alpaca easy_to_borrow"),
        n_formulas=N,
        noise_bar=dict(expected_max_t_under_null=bar_t,
                       basis="sqrt(2 ln 2N), two-sided over N scored formulas"),
        results=sorted(rows, key=lambda r: -r["design"]["t"]),
    )
    doc["stage"] = stage
    name = "DEEPMINE_CEFNAV.json" if reveal else "DEEPMINE_CEFNAV_DESIGN.json"
    (OUT / name).write_text(json.dumps(doc, indent=1, default=float) + "\n")
    print(f"stage={stage} N={N} bar_t={bar_t:.3f}")
    hdr = (f"{'key':30s} {'nD':>4s} {'dSh':>6s} {'dt':>6s} {'turn':>5s} "
           f"{'corr':>6s} {'daT':>6s} {'lag1':>6s} {'p90':>6s} {'l+p90':>6s} {'liq':>6s} ")
    print(hdr + ("| {:>6s} {:>6s} {:>6s} {:>6s} {:>6s}".format("hSh","haT","ha2T","hStrs","hs2T") if reveal else ""))
    for r in doc["results"]:
        d, dv, st = r["design"], r["design_vs_incumbent"], r["design_stress"]
        g = lambda k: (st.get(k) or {}).get("ann_sharpe", float("nan"))   # noqa: E731
        line = (f"{r['key']:30s} {d['n']:4d} "
                f"{d['ann_sharpe']:6.2f} {d['t']:6.2f} {(r['turnover_med'] or 0):5.2f} "
                f"{(dv or {}).get('corr', 0):6.2f} {(dv or {}).get('alpha_t', 0):6.2f} "
                f"{g('lag1_trading_day'):6.2f} {g('spread_p90_27p25'):6.2f} "
                f"{g('lag1_and_p90'):6.2f} {g('liquid_dadv_gt_1m'):6.2f} ")
        if reveal:
            h, hv = r["held_out"], r["held_vs_incumbent"]
            hs2 = (r["held_out_stress"].get("lag1_and_p90") or {}).get("ann_sharpe", 0)
            line += (f"| {h['ann_sharpe']:6.2f} {(hv or {}).get('alpha_t', 0):6.2f} "
                     f"{(r['held_alpha_2factor'] or {}).get('alpha_t', 0):6.2f} "
                     f"{hs2:6.2f} "
                     f"{(r['held_alpha_2factor_stressed'] or {}).get('alpha_t', 0):6.2f}")
        print(line)
    inc = doc["incumbent"]
    st = inc["design_stress"]
    print(f"\n{'INCUMBENT_L5_level_H4':30s} {inc['design']['n']:4d} "
          f"{inc['design']['ann_sharpe']:6.2f} {inc['design']['t']:6.2f} "
          f"{'':5s} {1.00:6.2f} {'':6s} "
          f"{st['lag1_trading_day']['ann_sharpe']:6.2f} "
          f"{st['spread_p90_27p25']['ann_sharpe']:6.2f} "
          f"{st['lag1_and_p90']['ann_sharpe']:6.2f} "
          f"{(st.get('liquid_dadv_gt_1m') or {}).get('ann_sharpe', float('nan')):6.2f}")
    msg = f"\nINCUMBENT design Sh {inc['design']['ann_sharpe']:.2f} (n={inc['design']['n']})"
    if reveal:
        msg += f", held {inc['held_out']['ann_sharpe']:.2f} (n={inc['held_out']['n']})"
    print(msg)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "design")
