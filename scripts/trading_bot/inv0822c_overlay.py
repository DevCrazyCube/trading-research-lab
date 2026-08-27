#!/usr/bin/env python3
"""INVENT_0822C -- PORTFOLIO-LEVEL OVERLAYS across the sized basket legs.

Question: does any ZERO-PARAMETER / structural overlay on the COMBINED book beat plain
equal-risk (1/N scaled to design vol) out of sample -- WITHOUT fitting weights?

Base book (BASE_EQRISK): w_i = 1/N on leg return scaled by 1/sd_design(leg).  No fit.
Every overlay below is either parameter-free or carries only a declared lookback; all are
strictly lagged (values through t-1 only).  Nothing is a single-leg regime gate.

Statistic: dSharpe = SR(overlay) - SR(BASE) on the SAME calendar.
Null: 2000 draws of an IID within-leg permutation (destroys vol clustering + correlation
timing, keeps each leg's marginal); record max_over_overlays dSharpe per draw.
"""
from __future__ import annotations
import json, math, pathlib, random, sys
import numpy as np

ROOT = pathlib.Path("/home/anont/meme")
CACHE = ROOT / "research/data/inv0822c_cache"
OUT = ROOT / "research/trading_bot"
RNG = np.random.default_rng(20260822)

LEGS = json.load(open(CACHE / "legs_daily.json"))["legs"]
COND = json.load(open(ROOT / "research/data/invent_r3/cond.json"))

PANELS = {
    "P1_LONG4": {"legs": ["T3", "T7D1", "ORB", "DUALCLASS"], "ppy": 252,
                 "design_end": "2022-12-30", "hold_start": "2023-01-03"},
    "P2_FULL5": {"legs": ["T3", "T7D1", "ORB", "DUALCLASS", "ETFRV"], "ppy": 252,
                 "design_end": "2024-03-29", "hold_start": "2024-04-01"},
    "P3_BASKET6W": {"legs": ["T3", "T7D1", "ORB", "DUALCLASS", "ETFRV", "CEF"], "ppy": 52,
                    "design_end": "2024-03-29", "hold_start": "2024-04-01", "weekly": True},
}


# ------------------------------------------------------------------ helpers
def sharpe(x, ppy):
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    if len(x) < 10 or x.std(ddof=1) == 0:
        return float("nan")
    return float(x.mean() / x.std(ddof=1) * math.sqrt(ppy))


def tstat(x):
    x = np.asarray(x, float); x = x[np.isfinite(x)]
    if len(x) < 10 or x.std(ddof=1) == 0:
        return float("nan")
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x))))


def week_key(d):
    import datetime as dt
    y, m, dd = (int(v) for v in d.split("-"))
    x = dt.date(y, m, dd)
    x = x + dt.timedelta(days=(4 - x.weekday()))     # Friday of that ISO week
    return x.isoformat()


def trail_sd(a, n):
    """sd of a[i-n:i] -- strictly lagged.  O(T) via cumsum."""
    a = np.asarray(a, float)
    T = len(a)
    out = np.full(T, np.nan)
    if T <= n:
        return out
    c1 = np.concatenate([[0.0], np.cumsum(a)])
    c2 = np.concatenate([[0.0], np.cumsum(a * a)])
    i = np.arange(n, T)
    s1 = c1[i] - c1[i - n]
    s2 = c2[i] - c2[i - n]
    var = (s2 - s1 * s1 / n) / (n - 1)
    out[i] = np.sqrt(np.maximum(var, 0.0))
    return out


def expand_sd(a, minobs=31):
    """sd of a[:i] -- strictly lagged, expanding.  O(T)."""
    a = np.asarray(a, float)
    T = len(a)
    c1 = np.concatenate([[0.0], np.cumsum(a)])
    c2 = np.concatenate([[0.0], np.cumsum(a * a)])
    k = np.arange(T)
    out = np.full(T, np.nan)
    ok = k >= minobs
    kk = k[ok].astype(float)
    s1 = c1[k[ok]]
    s2 = c2[k[ok]]
    var = (s2 - s1 * s1 / kk) / (kk - 1)
    out[ok] = np.sqrt(np.maximum(var, 0.0))
    return out


import heapq


def expanding_median(a, minobs):
    """median of the finite values seen strictly BEFORE i.  Two-heap, O(T log T)."""
    a = np.asarray(a, float)
    T = len(a)
    out = np.full(T, np.nan)
    lo, hi = [], []          # lo: max-heap (negated), hi: min-heap
    n = 0
    for i in range(T):
        if n >= minobs:
            out[i] = -lo[0] if len(lo) > len(hi) else (-lo[0] + hi[0]) / 2.0
        v = a[i]
        if not np.isfinite(v):
            continue
        if lo and v <= -lo[0]:
            heapq.heappush(lo, -v)
        else:
            heapq.heappush(hi, v)
        if len(lo) > len(hi) + 1:
            heapq.heappush(hi, -heapq.heappop(lo))
        elif len(hi) > len(lo):
            heapq.heappush(lo, -heapq.heappop(hi))
        n += 1
    return out


def roll_cov(X, n):
    """rolling covariance matrices over X[:, j-n:j] for every j.  Returns (T,N,N)."""
    N, T = X.shape
    P = np.einsum("it,jt->ijt", X, X)
    c = np.concatenate([np.zeros((N, N, 1)), np.cumsum(P, axis=2)], axis=2)
    c1 = np.concatenate([np.zeros((N, 1)), np.cumsum(X, axis=1)], axis=1)
    out = np.full((T, N, N), np.nan)
    j = np.arange(n, T)
    S2 = c[:, :, j] - c[:, :, j - n]
    S1 = c1[:, j] - c1[:, j - n]
    cov = (S2 - np.einsum("ik,jk->ijk", S1, S1) / n) / (n - 1)
    out[j] = np.moveaxis(cov, 2, 0)
    return out


# ------------------------------------------------------------------ panel
def build_panel(cfg):
    names = cfg["legs"]
    weekly = cfg.get("weekly", False)
    per = {}
    for nm in names:
        L = LEGS[nm]
        if weekly:
            agg = {}
            for d, v in zip(L["dates"], L["net"]):
                k = week_key(d) if not L.get("weekly") else d
                agg[k] = agg.get(k, 0.0) + v
            per[nm] = agg
        else:
            if L.get("weekly"):
                raise ValueError("weekly leg in a daily panel")
            per[nm] = dict(zip(L["dates"], L["net"]))
    # calendar: union of the two densest legs' dates, restricted to the common span
    lo = max(min(per[nm]) for nm in names)
    hi = min(max(per[nm]) for nm in names)
    allk = sorted({k for nm in names for k in per[nm] if lo <= k <= hi})
    R = np.zeros((len(names), len(allk)))
    LIVE = np.zeros((len(names), len(allk)), bool)
    for i, nm in enumerate(names):
        for j, k in enumerate(allk):
            if k in per[nm]:
                R[i, j] = per[nm][k]
                LIVE[i, j] = True
    return names, np.array(allk), R, LIVE


# ------------------------------------------------------------------ books
def base_book(R, dates, design_end):
    """equal-risk: each leg / its DESIGN sd, then 1/N.  Zero fitted parameters."""
    dm = dates <= design_end
    sd = np.array([max(R[i, dm].std(ddof=1), 1e-12) for i in range(R.shape[0])])
    S = R / sd[:, None]
    W = np.full(R.shape, 1.0 / R.shape[0])
    return S, W, sd


def apply_w(S, W):
    return (S * W).sum(axis=0)


# ---------------------------------------------------------------- overlays
def spy_exposure(dates):
    """the FROZEN T13 vol overlay (L=60, target 10% ann, wmax 1.0) on SPY, lagged."""
    spyd = sorted(COND["spy"])
    spyv = np.array([COND["spy"][d] for d in spyd])
    spyr = np.diff(np.log(spyv))
    ssd = trail_sd(spyr, 60) * math.sqrt(252)
    rd = spyd[1:]
    ex = np.ones(len(dates))
    j = 0
    last = np.nan
    for i, d in enumerate(dates):
        while j < len(rd) and rd[j] < d:
            if np.isfinite(ssd[j]):
                last = ssd[j]
            j += 1
        if np.isfinite(last) and last > 0:
            ex[i] = min(1.0, 0.10 / last)
    return ex


def overlays(S, W0, LIVE, dates, ppy, names, ctx):
    """{overlay_name: book_series}.  All strictly lagged, zero-parameter or structural."""
    N, T = S.shape
    base = apply_w(S, W0)
    out = {}

    def norm_w(W):
        t = np.abs(W).sum(axis=0)
        t[t == 0] = 1.0
        return W / t

    # ---- (A) BOOK-LEVEL VOL TARGETING (target = expanding median of its own trailing vol)
    for lb in (20, 60, 120):
        sd = trail_sd(base, lb)
        tgt = expanding_median(sd, 60)
        sc = np.where(np.isfinite(sd) & np.isfinite(tgt) & (sd > 0), tgt / np.where(sd > 0, sd, 1), 1.0)
        out[f"OV_VT{lb}"] = np.clip(sc, 0.25, 4.0) * base
        if lb == 60:
            out["OV_VT60_INV"] = np.clip(1.0 / np.clip(sc, 0.25, 4.0), 0.25, 4.0) * base

    lam = 1 - 1 / 20.0
    ew = np.full(T, np.nan)
    v = None
    for i in range(T):
        ew[i] = math.sqrt(v) if v is not None else np.nan
        v = base[i] ** 2 if v is None else lam * v + (1 - lam) * base[i] ** 2
    tgt = expanding_median(ew, 60)
    sc = np.where(np.isfinite(ew) & np.isfinite(tgt) & (ew > 0), tgt / np.where(ew > 0, ew, 1), 1.0)
    out["OV_VT_EWMA20"] = np.clip(sc, 0.25, 4.0) * base

    # ---- (B) THE FROZEN T13 SPY-VOL OVERLAY, applied to the whole book
    out["OV_T13_SPYVOL"] = ctx["spy_ex"] * base

    # ---- (C) DRAWDOWN DE-LEVER / LEVER-UP (zero parameter)
    eq = np.cumsum(base)
    peak = np.maximum.accumulate(np.concatenate([[0.0], eq]))[:-1]
    dd = np.where(peak > 0, np.clip((peak - eq) / np.maximum(peak, 1e-12), 0, 1), 0.0)
    ddl = np.concatenate([[0.0], dd[:-1]])
    out["OV_DD_DELEVER"] = (1.0 - np.clip(ddl, 0, 0.75)) * base
    out["OV_DD_LEVERUP"] = (1.0 + np.clip(ddl, 0, 0.75)) * base

    # ---- (D) STRUCTURAL RISK PARITY on TRAILING leg vol (vs the fixed design-vol base)
    for lb in (60, 120):
        SD = np.vstack([trail_sd(S[i], lb) for i in range(N)])
        W = np.where(np.isfinite(SD) & (SD > 1e-12), 1.0 / np.maximum(SD, 1e-12), np.nan)
        W = np.where(np.isfinite(W), W, 1.0)
        out[f"OV_RP{lb}"] = apply_w(S, norm_w(W))
        if lb == 60:
            Wc = np.minimum(norm_w(W), 0.40)
            out["OV_RP60_CAP40"] = apply_w(S, norm_w(Wc))
            out["OV_SQRTVOL60"] = apply_w(S, norm_w(np.sqrt(W)))
            out["OV_RP60_INV"] = apply_w(S, norm_w(np.where(np.isfinite(SD), SD, 1.0)))

    SDx = np.vstack([expand_sd(S[i]) for i in range(N)])
    W = np.where(np.isfinite(SDx) & (SDx > 1e-12), 1.0 / np.maximum(SDx, 1e-12), 1.0)
    out["OV_RP_EXPAND"] = apply_w(S, norm_w(W))

    # ---- (E) CORRELATION TIMING
    for lb in (60, 120):
        C = roll_cov(S, lb)                       # (T,N,N)
        w = W0.T                                  # (T,N)
        pv = np.einsum("ti,tij,tj->t", w, C, w)
        iv = np.einsum("ti,tii->t", w ** 2, C)
        dr = np.where((pv > 0) & (iv > 0), np.sqrt(np.divide(iv, pv, out=np.ones_like(pv), where=pv > 0)), np.nan)
        med = expanding_median(dr, 60)
        sc = np.where(np.isfinite(dr) & np.isfinite(med) & (med > 0), dr / np.where(med > 0, med, 1), 1.0)
        out[f"OV_DIVSCALE{lb}"] = np.clip(sc, 0.25, 4.0) * base
        if lb == 120:
            out["OV_DIVSCALE120_INV"] = np.clip(1.0 / np.clip(sc, 0.25, 4.0), 0.25, 4.0) * base
            d = np.sqrt(np.abs(np.einsum("tii->ti", C)))
            d = np.where(d > 1e-12, d, np.nan)
            R = C / (d[:, :, None] * d[:, None, :])
            R = np.where(np.isfinite(R), R, 0.0)
            mc = (np.abs(R).sum(axis=2) - 1.0) / max(N - 1, 1)      # (T,N)
            Wi = np.where(np.isfinite(mc), 1.0 / (1.0 + mc), 1.0 / N).T
            Wi[:, :lb] = 1.0 / N
            out["OV_INVCORR120"] = apply_w(S, norm_w(Wi))
            # drop the single most-correlated leg each day (structural, zero-param)
            Wd = np.full((N, T), 1.0 / max(N - 1, 1))
            worst = np.nanargmax(np.where(np.isfinite(mc), mc, -9), axis=1)
            Wd[worst, np.arange(T)] = 0.0
            Wd[:, :lb] = 1.0 / N
            out["OV_DROP_MOSTCORR120"] = apply_w(S, norm_w(Wd))

    # ---- (F) WALK-FORWARD FITTED CONTROLS (declared as controls; fitting is expected to lose)
    MU = np.vstack([np.concatenate([[np.nan], np.cumsum(S[i])[:-1] / np.maximum(np.arange(1, T), 1)])
                    for i in range(N)])
    W = np.where(np.isfinite(MU) & (MU > 0), MU, 0.0)
    W[:, :60] = 1.0 / N
    bad = np.abs(W).sum(axis=0) == 0
    W[:, bad] = 1.0 / N
    out["OV_FIT_SHARPEWEIGHT_EXPAND"] = apply_w(S, norm_w(W))
    mu_b = np.concatenate([[np.nan], np.cumsum(base)[:-1] / np.maximum(np.arange(1, T), 1)])
    sd_b = expand_sd(base)
    kel = np.where(np.isfinite(mu_b) & np.isfinite(sd_b) & (sd_b > 0), mu_b / (sd_b ** 2), np.nan)
    med = expanding_median(kel, 60)
    sc = np.where(np.isfinite(kel) & np.isfinite(med) & (med > 0), kel / np.where(med > 0, med, 1), 1.0)
    out["OV_FIT_KELLY_EXPAND"] = np.clip(sc, 0.0, 4.0) * base

    return out, base


# --------------------------------------------------------------- blackouts
def quarter_edge(dates):
    """last 4 and first 1 session of each calendar quarter (ETF ex-distribution window)."""
    q = np.array([(d[:4], (int(d[5:7]) - 1) // 3) for d in dates], dtype=object)
    key = np.array([f"{a}Q{b}" for a, b in q])
    flag = np.zeros(len(dates), bool)
    for k in set(key):
        idx = np.where(key == k)[0]
        for i in idx[-4:]:
            flag[i] = True
        flag[idx[0]] = True
    return flag


def month_end_week(dates):
    flag = np.zeros(len(dates), bool)
    mk = np.array([d[:7] for d in dates])
    for k in set(mk):
        idx = np.where(mk == k)[0]
        flag[idx[-1]] = True
    return flag


def triple_witch(dates):
    import datetime as dt
    flag = np.zeros(len(dates), bool)
    for i, d in enumerate(dates):
        y, m, dd = (int(v) for v in d.split("-"))
        if m not in (3, 6, 9, 12):
            continue
        x = dt.date(y, m, dd)
        if x.weekday() == 4 and 15 <= dd <= 21:
            flag[i] = True
    return flag


def year_edge(dates):
    flag = np.zeros(len(dates), bool)
    yk = np.array([d[:4] for d in dates])
    for k in set(yk):
        idx = np.where(yk == k)[0]
        for i in idx[-3:]:
            flag[i] = True
        for i in idx[:2]:
            flag[i] = True
    return flag


# ------------------------------------------------------------------- run
def run_panel(pname, cfg, nperm=2000):
    names, dates, R, LIVE = build_panel(cfg)
    ppy = cfg["ppy"]
    S, W0, sd = base_book(R, dates, cfg["design_end"])
    ctx = {"spy_ex": spy_exposure(dates)}
    books, base = overlays(S, W0, LIVE, dates, ppy, names, ctx)

    # equal-dollar (no vol scaling at all) -- the other zero-parameter default
    books["OV_EQDOLLAR"] = R.mean(axis=0)

    # always-full: renormalise over LIVE legs so idle legs do not de-lever the book
    Wl = LIVE.astype(float)
    s = Wl.sum(axis=0); s[s == 0] = 1.0
    books["OV_ALWAYSFULL"] = apply_w(S, Wl / s)

    # structural blackouts
    qe = quarter_edge(dates); me = month_end_week(dates)
    tw = triple_witch(dates); ye = year_edge(dates)
    if "ETFRV" in names:
        i = names.index("ETFRV")
        W = W0.copy(); W[i, qe] = 0.0
        books["OV_ETFRV_EXDIST_OFF"] = apply_w(S, W)
    if "CEF" in names:
        i = names.index("CEF")
        W = W0.copy(); W[i, me] = 0.0
        books["OV_CEF_MONTHEND_OFF"] = apply_w(S, W)
    books["OV_TRIPLEWITCH_OFF"] = np.where(tw, 0.0, base)
    books["OV_YEAREND_OFF"] = np.where(ye, 0.0, base)
    books["OV_MONTHEND_OFF"] = np.where(me, 0.0, base)

    dm = dates <= cfg["design_end"]; hm = dates >= cfg["hold_start"]
    res = []
    sr_b = {"design": sharpe(base[dm], ppy), "holdout": sharpe(base[hm], ppy),
            "full": sharpe(base, ppy)}
    for nm, b in books.items():
        res.append({
            "overlay": nm,
            "design_sr": sharpe(b[dm], ppy), "holdout_sr": sharpe(b[hm], ppy),
            "full_sr": sharpe(b, ppy),
            "d_design": sharpe(b[dm], ppy) - sr_b["design"],
            "d_holdout": sharpe(b[hm], ppy) - sr_b["holdout"],
            "d_full": sharpe(b, ppy) - sr_b["full"],
            "t_full": tstat(b),
            "turnover_proxy": float(np.mean(np.abs(np.diff(b - base)))) if len(b) > 2 else None,
        })

    # ---------------- size-matched placebo: IID within-leg permutation
    K = len(books)
    maxd_h, maxd_f = [], []
    for _ in range(nperm):
        Rp = np.empty_like(R)
        for i in range(R.shape[0]):
            Rp[i] = RNG.permutation(R[i])
        Sp, Wp, _ = base_book(Rp, dates, cfg["design_end"])
        bk, bs = overlays(Sp, Wp, LIVE, dates, ppy, names, ctx)
        bk["OV_EQDOLLAR"] = Rp.mean(axis=0)
        bk["OV_ALWAYSFULL"] = apply_w(Sp, Wl / s)
        if "ETFRV" in names:
            i = names.index("ETFRV"); W = Wp.copy(); W[i, qe] = 0.0
            bk["OV_ETFRV_EXDIST_OFF"] = apply_w(Sp, W)
        if "CEF" in names:
            i = names.index("CEF"); W = Wp.copy(); W[i, me] = 0.0
            bk["OV_CEF_MONTHEND_OFF"] = apply_w(Sp, W)
        bk["OV_TRIPLEWITCH_OFF"] = np.where(tw, 0.0, bs)
        bk["OV_YEAREND_OFF"] = np.where(ye, 0.0, bs)
        bk["OV_MONTHEND_OFF"] = np.where(me, 0.0, bs)
        sb_h = sharpe(bs[hm], ppy); sb_f = sharpe(bs, ppy)
        dh = [sharpe(v[hm], ppy) - sb_h for v in bk.values()]
        df = [sharpe(v, ppy) - sb_f for v in bk.values()]
        maxd_h.append(np.nanmax(dh)); maxd_f.append(np.nanmax(df))
    maxd_h = np.array(maxd_h); maxd_f = np.array(maxd_f)

    return {
        "panel": pname, "legs": names, "n_obs": int(len(dates)),
        "span": [str(dates[0]), str(dates[-1])], "ppy": ppy,
        "design_end": cfg["design_end"], "hold_start": cfg["hold_start"],
        "n_design": int(dm.sum()), "n_holdout": int(hm.sum()),
        "base": sr_b, "n_overlays": K,
        "results": sorted(res, key=lambda r: -(r["d_holdout"] if np.isfinite(r["d_holdout"]) else -9)),
        "placebo_null": {
            "n_draws": nperm,
            "max_dSharpe_holdout_mean": float(np.nanmean(maxd_h)),
            "max_dSharpe_holdout_p95": float(np.nanpercentile(maxd_h, 95)),
            "max_dSharpe_full_mean": float(np.nanmean(maxd_f)),
            "max_dSharpe_full_p95": float(np.nanpercentile(maxd_f, 95)),
        },
    }


def main():
    nperm = int(sys.argv[1]) if len(sys.argv) > 1 else 400
    payload = {"theme": "portfolio_level_overlay_across_sized_basket_legs",
               "panels": {}}
    for pn, cfg in PANELS.items():
        print("panel", pn, file=sys.stderr)
        payload["panels"][pn] = run_panel(pn, cfg, nperm)
        r = payload["panels"][pn]
        print(f"  {pn}: n={r['n_obs']} base design {r['base']['design']:.2f} "
              f"holdout {r['base']['holdout']:.2f} | K={r['n_overlays']} "
              f"placebo p95 dSR_hold={r['placebo_null']['max_dSharpe_holdout_p95']:.3f}",
              file=sys.stderr)
        for x in r["results"][:6]:
            print("    %-24s dDesign %+6.3f  dHold %+6.3f  dFull %+6.3f"
                  % (x["overlay"], x["d_design"], x["d_holdout"], x["d_full"]), file=sys.stderr)
    ntot = sum(p["n_overlays"] for p in payload["panels"].values())
    payload["n_formulas_tested"] = ntot
    payload["expected_max_sigma_analytic"] = math.sqrt(2 * math.log(max(ntot, 2)))
    (CACHE / "overlay_raw.json").write_text(json.dumps(payload, indent=1))
    print("N =", ntot, "sqrt(2lnN) =", payload["expected_max_sigma_analytic"], file=sys.stderr)


if __name__ == "__main__":
    main()
