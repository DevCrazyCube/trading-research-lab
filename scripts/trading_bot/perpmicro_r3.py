#!/usr/bin/env python3
"""ROUND 3 of the crypto-perp funding / OI / liquidation-structure invention sweep.

WHAT IS NEW vs rounds 1-2 (106 formulas already burned; see perpmicro_sweep{,2}.py):

  round 1 tested the LEVEL and the FIRST DIFFERENCE of funding, OI and the L/S ratios.
  round 2 tested PATH statistics of those same series (persistence, flip rate, streaks)
  and conjunctions (products) of the round-1 primitives.

  Round 3 deliberately goes after objects neither round could express:
    * SECOND-ORDER properties of the carry series -- its mean-reversion SPEED (rolling AR1),
      its BETA to the market carry, its idiosyncratic residual, the SHAPE of the trailing
      carry curve (slope and curvature of 3/9/27-period means). None of these is a level or
      a difference; a symbol can have identical funding level and opposite AR1.
    * A real LIQUIDATION-HEATMAP construct: an OI-weighted average entry price (OIWAP) built
      by accumulating price weighted by POSITIVE OI creation with a 7d decay, split by the
      side of the aggressor flow that created it, and the distance from spot to the 25x
      liquidation band implied by that cost basis. Round 1's "XS_LIQPROX" was drawdown +
      realised vol; it never reconstructed a cost basis.
    * RELATIVE leverage flow: the symbol's SHARE of universe open interest and its drift.
      Round 2 did volume share; nobody did OI share (where leverage is rotating TO).
    * FLOW-QUADRANT decomposition: volume split by (OI rising/falling) x (aggressor buying/
      selling) to separate short-covering from long-liquidation from fresh leverage.
    * A signal designed to be ORTHOGONAL to the basket's existing XS_GLSR_Z leg: retail
      crowding cross-sectionally RESIDUALISED on OI growth.

HONESTY MECHANICS (inherited from perpmicro_sweep.py, unchanged):
  entry/exit at the OPEN of a bar the signal cannot see; H overlapping tranches; funding
  accrued at the settlement bar; 5.5 bp/side; sign oriented on DESIGN and FROZEN out of
  sample; sign-flip block bootstrap for the multiple-testing bar.

WINDOWS
  class A (price/flow/funding only, panel runs to 2026-08-16)
      DESIGN  2022-11-01 -> 2024-10-01
      HOLDOUT 2024-10-01 -> 2026-08-16     (22.5 months, untouched by ROUND-3 fitting)
  class B (needs the OI / long-short metrics feed)
      DESIGN  2023-01-01 -> 2024-06-01
      HOLD_B1 2024-06-01 -> 2025-01-01     (dense cross-section)
      HOLD_B2 2025-01-01 -> 2026-08-16     (THIN: only ~20 names have the metrics feed there;
                                            reported separately and never used for selection)
"""
from __future__ import annotations

import argparse
import gc
import json
import math
import pathlib

import numpy as np

import perpmicro_sweep as ps
from perpmicro_sweep import (roll_sum, roll_mean, roll_std, roll_max, roll_min, lag, dlog,
                             zs, xz, xrank, to_daily, sharpe, noise_bar, window_mask,
                             run_window, _corr)

ROOT = pathlib.Path(__file__).resolve().parents[2]
EXT = ROOT / "research" / "data" / "perpmicro_cache" / "panel1h_ext_trim.npz"
META = ROOT / "research" / "data" / "perpmicro_cache" / "panel1h_r3meta.npz"
OUT = ROOT / "research" / "trading_bot"

DESIGN_A = ("2022-11-01", "2024-10-01")
HOLD_A = ("2024-10-01", "2026-08-16")
DESIGN_B = ("2023-01-01", "2024-06-01")
HOLD_B1 = ("2024-06-01", "2025-01-01")
HOLD_B2 = ("2025-01-01", "2026-08-16")

EPS = 1e-12


# ------------------------------------------------------------------ extra helpers
def roll_cov(a, b, w):
    return roll_mean(a * b, w) - roll_mean(a, w) * roll_mean(b, w)


def roll_ar1(a, w, k=1):
    """rolling AR(k) slope of a on its own k-lag, over w bars."""
    al = lag(a, k)
    v = roll_mean(al * al, w) - roll_mean(al, w) ** 2
    c = roll_cov(a, al, w)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(v > EPS, c / v, np.nan).astype(np.float32)


def xs_resid(a, b, mask):
    """cross-sectional OLS residual of a on b, per column, within mask."""
    A = np.where(mask & np.isfinite(a) & np.isfinite(b), a, np.nan)
    B = np.where(mask & np.isfinite(a) & np.isfinite(b), b, np.nan)
    n = np.isfinite(A).sum(0)
    ma = np.nanmean(A, axis=0); mb = np.nanmean(B, axis=0)
    ca = A - ma; cb = B - mb
    cov = np.nansum(ca * cb, axis=0)
    var = np.nansum(cb * cb, axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        beta = np.where(var > EPS, cov / var, 0.0)
    r = ca - beta[None, :] * cb
    r = np.where(n[None, :] >= ps.MIN_NAMES, r, np.nan)
    return r.astype(np.float32)


def ewma_ratio(num_w, price, lam):
    """OI-weighted average price: num_t = lam*num_{t-1} + w_t*p_t ; den likewise."""
    S, NH = num_w.shape
    w = np.nan_to_num(num_w, nan=0.0, posinf=0.0, neginf=0.0).astype(np.float64)
    p = np.nan_to_num(price, nan=0.0, posinf=0.0, neginf=0.0).astype(np.float64)
    num = np.zeros(S); den = np.zeros(S)
    out = np.full((S, NH), np.nan, np.float32)
    for j in range(NH):
        num *= lam; den *= lam
        num += w[:, j] * p[:, j]
        den += w[:, j]
        good = den > 0
        out[good, j] = (num[good] / den[good]).astype(np.float32)
    return out


# ------------------------------------------------------------------ feature build
class P:
    pass


def build(cls, top_n, min_names):
    ps.TOP_N = top_n
    ps.MIN_NAMES = min_names
    pan = np.load(EXT, allow_pickle=True)
    p = P()
    p.sym = np.array([str(s) for s in pan["symbols"]])
    p.t = pan["t"].astype(np.int64)
    g = {k: pan[k].astype(np.float32) for k in
         ["o", "h", "l", "c", "qv", "ntr", "tbq", "fund", "fund_age_h", "fund_next_h"]}
    if cls == "B":
        mp = np.load(META, allow_pickle=True)
        assert [str(s) for s in mp["symbols"]] == list(p.sym)
        assert int(mp["t"][0]) == int(p.t[0]) and len(mp["t"]) == len(p.t)
        for k in ["oi", "oiv", "ttc", "tts", "glsr", "tlsr"]:
            g[k] = mp[k].astype(np.float32)
        del mp
    del pan
    p.g = g
    S, NH = g["c"].shape
    p.S, p.NH = S, NH

    o = g["o"]
    nxt = np.full_like(o, np.nan); nxt[:, :-1] = o[:, 1:]
    with np.errstate(invalid="ignore", divide="ignore"):
        p.ret = np.clip(np.where((o > 0) & (nxt > 0), nxt / o - 1.0, 0.0), -0.5, 0.5).astype(np.float32)

    qv7 = roll_sum(g["qv"], 168)
    liq_ok = np.isfinite(qv7) & np.isfinite(o) & (o > 0) & (g["qv"] > 0)
    if cls == "B":
        liq_ok &= np.isfinite(g["oi"]) & (g["oi"] > 0)
    v = np.where(liq_ok, qv7, -np.inf)
    ordr = np.argsort(-v, axis=0, kind="stable")
    rk = np.empty_like(ordr, dtype=np.int32)
    np.put_along_axis(rk, ordr, np.broadcast_to(np.arange(S, dtype=np.int32)[:, None],
                                                ordr.shape), axis=0)
    p.univ = liq_ok & (rk < top_n)
    U = p.univ

    p.lc = np.log(np.where(g["c"] > 0, g["c"], np.nan)).astype(np.float32)
    p.r1 = (p.lc - lag(p.lc, 1)).astype(np.float32)
    p.r24 = (p.lc - lag(p.lc, 24)).astype(np.float32)
    p.r168 = (p.lc - lag(p.lc, 168)).astype(np.float32)
    p.rv24 = roll_std(p.r1, 24)
    p.rv168 = roll_std(p.r1, 168)

    with np.errstate(invalid="ignore", divide="ignore"):
        p.ti1 = np.where(g["qv"] > 0, (2 * g["tbq"] - g["qv"]) / g["qv"], np.nan).astype(np.float32)
    tb24 = roll_sum(g["tbq"], 24); qq24 = roll_sum(g["qv"], 24)
    with np.errstate(invalid="ignore", divide="ignore"):
        p.ti24 = np.where(qq24 > 0, (2 * tb24 - qq24) / qq24, np.nan).astype(np.float32)

    # ---- funding (step function: the settled rate held for the next 8 hours)
    p.f = g["fund"]
    p.settle = (np.isfinite(g["fund_age_h"]) & (g["fund_age_h"] < 1.0))
    p.fpaid = np.where(p.settle & np.isfinite(p.f), p.f, 0.0).astype(np.float32)
    return p


# ------------------------------------------------------------------ CLASS A catalogue
def catalogue_A(p):
    U = p.univ
    F = []
    A = F.append
    f = p.f

    fm3 = roll_mean(f, 24)          # 3 funding periods
    fm9 = roll_mean(f, 72)          # 9
    fm27 = roll_mean(f, 216)        # 27
    fm21 = roll_mean(f, 168)        # 21 (7 days)
    fsd = roll_std(f, 720)

    with np.errstate(invalid="ignore", divide="ignore"):
        slope = np.where(fsd > EPS, (fm3 - fm21) / fsd, np.nan).astype(np.float32)
        curve = np.where(fsd > EPS, (fm3 - 2 * fm9 + fm27) / fsd, np.nan).astype(np.float32)
    A(("R3A_FUND_TERM", slope, 8, "quintile",
       "TERM STRUCTURE of own carry: (3-period mean funding - 21-period mean funding) / 30d "
       "funding sd. Front-vs-deferred slope of the coin's own carry curve, scale-free."))
    A(("R3A_FUND_CONVEX", curve, 8, "quintile",
       "CURVATURE of the carry curve: (3p - 2*9p + 27p mean funding)/sd. Humped vs bowed carry."))

    ar1 = roll_ar1(f, 720, k=8)     # lag = one funding period
    A(("R3A_FUND_AR1", ar1, 24, "quintile",
       "rolling AR(1) coefficient of the funding series at a 1-period lag over 30d: the SPEED "
       "at which this coin's carry mean-reverts. Second-order; independent of the level."))
    A(("R3A_FUND_DECAY", (xz(f, U) * (1.0 - np.clip(ar1, -1, 1))).astype(np.float32), 24, "quintile",
       "carry level x (1 - AR1): expensive carry that historically DECAYS fast, vs expensive "
       "carry that sticks. Round 1/2 only ever sorted on the level or the path."))

    nlive = np.maximum(U.sum(0), 1)
    mf = (np.where(U & np.isfinite(f), f, 0.0).sum(0) / nlive).astype(np.float32)
    MF = np.broadcast_to(mf[None, :], f.shape).astype(np.float32)
    vmf = roll_mean(MF * MF, 720) - roll_mean(MF, 720) ** 2
    with np.errstate(invalid="ignore", divide="ignore"):
        fbeta = np.where(vmf > EPS, roll_cov(f, MF, 720) / vmf, np.nan).astype(np.float32)
    A(("R3A_FUND_BETA", fbeta, 24, "quintile",
       "30d rolling BETA of the coin's funding to the universe-mean funding: how levered this "
       "coin's carry is to the market-wide carry cycle (a loading, not a level)."))
    falpha = roll_mean((f - fbeta * MF).astype(np.float32), 168)
    A(("R3A_FUND_ALPHA", falpha, 8, "quintile",
       "7d mean IDIOSYNCRATIC funding: funding minus beta x market funding. Differs from a "
       "cross-sectional demean because it removes each coin's own carry beta first."))

    A(("R3A_NETCARRY_MOM", (p.r168 - roll_sum(p.fpaid, 168)).astype(np.float32), 24, "quintile",
       "7d price return MINUS 7d funding actually paid: the total return a levered long really "
       "earned. Momentum and carry are netted inside one number, not z-summed."))

    with np.errstate(invalid="ignore", divide="ignore"):
        cir = np.where(fsd > EPS, roll_sum(p.fpaid, 720) / (fsd * math.sqrt(90)), np.nan)
    A(("R3A_CARRY_IR", cir.astype(np.float32), 24, "quintile",
       "30d cumulative funding divided by the sd of the funding prints: an information ratio "
       "of the carry (stability-adjusted), not a vol-adjusted level."))

    tar1 = roll_ar1(p.ti1, 168, k=1)
    A(("R3A_TAKER_AR1", tar1, 24, "quintile",
       "7d rolling AR(1) SLOPE of the hourly taker imbalance: magnitude-weighted order-flow "
       "persistence (round 2's FLOWPERSIST used sign agreement, which discards magnitude)."))

    A(("R3A_FLOW_VS_FUND", (xz(p.ti24, U) - xz(f, U)).astype(np.float32), 24, "quintile",
       "aggressor flow buying while carry is still cheap: flow LEADING the funding reprice."))

    dfund = (f - lag(f, 24)).astype(np.float32)
    dti = (p.ti24 - lag(p.ti24, 24)).astype(np.float32)
    A(("R3A_FUND_LEAD_FLOW", (xz(dfund, U) - xz(dti, U)).astype(np.float32), 24, "quintile",
       "24h carry repricing NOT confirmed by a matching move in aggressor flow (carry moved, "
       "flow did not) -- a lead/lag divergence, not a level or a product."))

    hod = ((p.t // 3_600_000) % 24).astype(np.int32)
    dow = (((p.t // 86_400_000) + 4) % 7).astype(np.int32)   # 1970-01-01 = Thursday
    wknd = ((dow == 5) | (dow == 6))
    Wk = np.broadcast_to(wknd[None, :], f.shape)
    sw = np.where(p.settle & Wk, f, 0.0).astype(np.float32)
    nw = np.where(p.settle & Wk, 1.0, 0.0).astype(np.float32)
    sd_ = np.where(p.settle & ~Wk, f, 0.0).astype(np.float32)
    nd_ = np.where(p.settle & ~Wk, 1.0, 0.0).astype(np.float32)
    with np.errstate(invalid="ignore", divide="ignore"):
        wc = (roll_sum(sw, 672) / np.maximum(roll_sum(nw, 672), 1)
              - roll_sum(sd_, 672) / np.maximum(roll_sum(nd_, 672), 1))
    A(("R3A_WEEKEND_CARRY", wc.astype(np.float32), 24, "quintile",
       "28d mean WEEKEND funding minus 28d mean WEEKDAY funding, per coin: a cross-sectional "
       "sort on who pays a weekend carry premium (round 2 only timed the market on weekends)."))
    del hod
    return F


# ------------------------------------------------------------------ CLASS B catalogue
def catalogue_B(p):
    U = p.univ
    g = p.g
    F = []
    A = F.append

    def L(a):
        return np.log(np.where(a > 0, a, np.nan)).astype(np.float32)

    oi = g["oi"]; oiv = g["oiv"]
    doiu24 = dlog(oi, 24)

    # ---------- relative leverage flow
    tot = np.where(U & np.isfinite(oiv), oiv, 0.0).sum(0)
    with np.errstate(invalid="ignore", divide="ignore"):
        share = np.where(tot > 0, oiv / tot[None, :], np.nan).astype(np.float32)
    A(("R3B_OISHARE_CHG", dlog(share, 168), 24, "quintile",
       "7d log change in the coin's SHARE of total universe open-interest VALUE: where levered "
       "money is rotating TO, net of the market-wide leverage cycle."))
    with np.errstate(invalid="ignore", divide="ignore"):
        sticky = np.where(roll_max(oi, 168) > 0, roll_min(oi, 24) / roll_max(oi, 168), np.nan)
    A(("R3B_OI_STICKY", sticky.astype(np.float32), 24, "quintile",
       "min(OI,24h)/max(OI,7d): what fraction of the leverage built this week SURVIVED. Low = "
       "flighty, repeatedly-flushed leverage; high = sticky positioning."))

    # ---------- liquidation heatmap: OI-weighted cost basis
    doi = (oi - lag(oi, 1)).astype(np.float32)
    dpos = np.clip(doi, 0, None)
    lam = math.exp(-1.0 / (24 * 7))
    px = g["c"]
    oiwap = ewma_ratio(dpos, px, lam)
    vol_d = np.maximum(p.rv24 * math.sqrt(24), 1e-4)
    with np.errstate(invalid="ignore", divide="ignore"):
        gap = np.where(oiwap > 0, (np.log(np.where(px > 0, px, np.nan)) - np.log(oiwap)) / vol_d,
                       np.nan).astype(np.float32)
    A(("R3B_OIWAP_GAP", gap, 24, "quintile",
       "spot vs the OI-WEIGHTED AVERAGE ENTRY PRICE (price accumulated weighted by POSITIVE OI "
       "creation, 7d decay), in daily sigmas: is the aggregate open position in profit or "
       "underwater? A reconstructed cost basis, not a drawdown proxy."))
    lb = math.log(1.0 - 1.0 / 25.0)
    with np.errstate(invalid="ignore", divide="ignore"):
        dist25 = np.where(oiwap > 0,
                          (np.log(np.where(px > 0, px, np.nan)) - (np.log(oiwap) + lb)) / vol_d,
                          np.nan).astype(np.float32)
    A(("R3B_LIQ_DIST_25X", dist25, 24, "quintile",
       "daily sigmas from spot DOWN to the 25x long-liquidation band implied by the OI-weighted "
       "cost basis: proximity to the densest long-liq cluster."))

    tin = np.nan_to_num(p.ti1, nan=0.0)
    oiwl = ewma_ratio(np.where(tin > 0, dpos, 0.0).astype(np.float32), px, lam)
    oiws = ewma_ratio(np.where(tin < 0, dpos, 0.0).astype(np.float32), px, lam)
    lu = math.log(1.0 + 1.0 / 25.0)
    with np.errstate(invalid="ignore", divide="ignore"):
        lpx = np.log(np.where(px > 0, px, np.nan))
        dl = np.where(oiwl > 0, (lpx - (np.log(oiwl) + lb)) / vol_d, np.nan)
        dsh = np.where(oiws > 0, ((np.log(oiws) + lu) - lpx) / vol_d, np.nan)
    A(("R3B_LIQ_ASYM", (dl - dsh).astype(np.float32), 24, "quintile",
       "SIDED liquidation-heatmap asymmetry: distance to the 25x LONG liq band (cost basis built "
       "on aggressor BUYING) minus distance to the 25x SHORT liq band (basis built on aggressor "
       "SELLING). Which side is closer to being flushed."))

    # ---------- flow-quadrant decomposition
    qv = g["qv"]
    q7 = np.maximum(roll_sum(qv, 168), EPS)
    cover = roll_sum(np.where((doi < 0) & (tin > 0), qv, 0.0).astype(np.float32), 168)
    longliq = roll_sum(np.where((doi < 0) & (tin < 0), qv, 0.0).astype(np.float32), 168)
    A(("R3B_COVER_SHARE", ((cover - longliq) / q7).astype(np.float32), 24, "quintile",
       "share of 7d volume that was SHORT COVERING (OI falling on aggressor buying) minus the "
       "share that was LONG LIQUIDATION (OI falling on aggressor selling). A quadrant split of "
       "volume by (dOI sign) x (aggressor sign) -- neither round could express this."))
    oi7 = np.maximum(roll_mean(oi, 168), EPS)
    nl = roll_sum(np.where(tin > 0, dpos, 0.0).astype(np.float32), 168)
    nsh = roll_sum(np.where(tin < 0, dpos, 0.0).astype(np.float32), 168)
    A(("R3B_NEWLONG_SHARE", ((nl - nsh) / oi7).astype(np.float32), 24, "quintile",
       "7d OI created on aggressor BUYING minus OI created on aggressor SELLING, scaled by mean "
       "OI: signed fresh-leverage build (fresh longs vs fresh shorts)."))
    dneg = np.clip(-doi, 0, None)
    fd = roll_sum(np.where(p.r1 < 0, dneg, 0.0).astype(np.float32), 168)
    fu = roll_sum(np.where(p.r1 > 0, dneg, 0.0).astype(np.float32), 168)
    A(("R3B_FLUSH_ASYM", ((fd - fu) / oi7).astype(np.float32), 24, "quintile",
       "7d OI DESTROYED in down-hours minus OI destroyed in up-hours, scaled by mean OI: which "
       "side of the book keeps getting repeatedly flushed."))

    # ---------- positioning structure
    A(("R3B_TT_CONC", (L(g["tts"]) - L(g["ttc"])).astype(np.float32), 24, "quintile",
       "top-trader POSITION L/S ratio minus top-trader ACCOUNT-COUNT L/S ratio: conviction "
       "concentration INSIDE the smart-money cohort (round 1 compared top traders to the "
       "global crowd, never to their own account count in log space at 24h)."))
    A(("R3B_FUNDxOISHARE", (xz(p.f, U) + xz(dlog(share, 168), U)).astype(np.float32), 24, "quintile",
       "expensive carry AND rising share of total leverage: fragility = the crowd concentrating "
       "into the coin that already costs the most to hold."))

    lgz = zs(L(g["glsr"]), 168)
    A(("R3B_GLSR_RESID_OI", xs_resid(lgz, xz(doiu24, U), U), 24, "quintile",
       "the basket's XS_GLSR_Z leg RESIDUALISED cross-sectionally on 24h OI growth: retail "
       "crowding that is NOT just a proxy for the overall leverage build. Designed to be the "
       "orthogonal part of an edge already in the basket."))

    # reference leg (NOT counted in the multiple-testing N; it is the incumbent)
    A(("REF_XS_GLSR_Z", lgz, 24, "quintile",
       "INCUMBENT basket leg XS_GLSR_Z, re-run here only as a correlation benchmark."))
    return F


# ------------------------------------------------------------------ run
def to_F(cat):
    return [(n, x, H, sc, None, d) for (n, x, H, sc, d) in cat]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cls", choices=["A", "B"], required=True)
    ap.add_argument("--top-n", type=int, default=60)
    ap.add_argument("--min-names", type=int, default=20)
    ap.add_argument("--thin", action="store_true",
                    help="class B only: also run the thin 2025-01+ virgin window")
    args = ap.parse_args()

    p = build(args.cls, args.top_n, args.min_names)
    cat = catalogue_A(p) if args.cls == "A" else catalogue_B(p)
    F = to_F(cat)
    gc.collect()

    wins = ([("design", DESIGN_A), ("holdout", HOLD_A)] if args.cls == "A"
            else [("design", DESIGN_B), ("hold_b1", HOLD_B1)])
    out = {"class": args.cls, "top_n": args.top_n, "min_names": args.min_names,
           "cost_bp_per_side": ps.COST_SIDE_BP, "windows": {}}
    signs = None
    pnl_store = {}
    for tag, (a, b) in wins:
        m = window_mask(p.t, a, b)
        res, mat = run_window(F, p, m, signs=signs)
        if tag == "design":
            signs = {r["name"]: r["sign"] for r in res}
            nb = noise_bar(mat[: len(F)])
            out["noise_bar_design"] = nb
        # store daily net pnl for correlation work
        for r, row in zip(res, mat):
            pnl_store.setdefault(tag, {})[r["name"]] = (r["sign"] * row).tolist()
        out["windows"][tag] = {"range": [a, b], "results": res}
        print(f"--- {tag} {a}..{b}")
        for r in sorted(res, key=lambda z: -(z["sharpe_net"] if np.isfinite(z["sharpe_net"]) else -9)):
            print(f"  {r['name']:22s} net {r['sharpe_net']:+6.2f} gross {r['sharpe_gross']:+6.2f} "
                  f"be {r['breakeven_cost_bp_per_side']:6.1f}bp tpd {r['turnover_per_day']:.2f}")
        gc.collect()

    if args.cls == "B" and args.thin:
        del p, F, cat
        gc.collect()
        p2 = build("B", 40, 8)
        cat2 = catalogue_B(p2)
        F2 = to_F(cat2)
        m = window_mask(p2.t, *HOLD_B2)
        res, mat = run_window(F2, p2, m, signs=signs)
        for r, row in zip(res, mat):
            pnl_store.setdefault("hold_b2_thin", {})[r["name"]] = (r["sign"] * row).tolist()
        out["windows"]["hold_b2_thin"] = {"range": list(HOLD_B2), "results": res,
                                          "note": "thin cross-section (~20 names, A-B tickers "
                                                  "only: the metrics cache download is "
                                                  "alphabetical and stops at B after 2024-12). "
                                                  "Directional evidence only."}
        print("--- hold_b2_thin")
        for r in sorted(res, key=lambda z: -(z["sharpe_net"] if np.isfinite(z["sharpe_net"]) else -9)):
            print(f"  {r['name']:22s} net {r['sharpe_net']:+6.2f} gross {r['sharpe_gross']:+6.2f}")

    (OUT / f"INVENT_R3_perpstructure_{args.cls}.json").write_text(json.dumps(out, indent=1))
    np.savez_compressed(OUT / f"INVENT_R3_perpstructure_{args.cls}_pnl.npz",
                        **{f"{k}|{n}": np.asarray(v) for k, d in pnl_store.items()
                           for n, v in d.items()})
    print("wrote", OUT / f"INVENT_R3_perpstructure_{args.cls}.json")


if __name__ == "__main__":
    main()
