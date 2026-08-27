#!/usr/bin/env python3
"""INVENT_0822C -- CEF structure BEYOND the discount level.

Reuses the DEEPMINE_CEFNAV panel/book/cost machinery verbatim (same universe, same costs,
same split, same stress ladder) and adds three things that sweep did not have:

  1. point-in-time DOLLAR distribution per share -> a distribution CUT / RAISE detector
  2. point-in-time NAV erosion (distribution-coverage proxy)
  3. SEC EDGAR corporate-action events (SC 13D activist, SC TO-I tender, N-2/424B rights,
     SC 13G as the sweep's own inert placebo)

plus risk-normalised / category-MAD-standardised discounts and category-relative NAV momentum.

Stage `design` seals every held-out field. Stage `reveal` unseals.
"""
from __future__ import annotations

import gzip
import json
import math
import pathlib
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from deepmine_cefnav import (  # noqa: E402
    CACHE, DECILE, OUT, SPLIT, WEEKS_PER_YEAR, book_from_score, build_panel,
    net_series, summarise, _demean_by, _lag_diff, _roll_mean, _roll_std, _roll_sum, _xs_resid,
)

EDGAR = pathlib.Path("/home/anont/meme/research/data/cef0822c_cache/edgar_submissions.json.gz")
RNG = np.random.default_rng(20260822)
N_PLACEBO = 300


# ---------------------------------------------------------------------------
# new primitives
# ---------------------------------------------------------------------------

def _roll_median_cs(X, keys):
    """cross-sectional (D - group median) / group MAD, per date."""
    out = np.full(X.shape, np.nan)
    for g in np.unique(keys):
        m = keys == g
        sub = X[:, m]
        med = np.nanmedian(sub, axis=1, keepdims=True)
        mad = np.nanmedian(np.abs(sub - med), axis=1, keepdims=True)
        mad = np.where(mad > 1e-6, mad, np.nan)
        out[:, m] = (sub - med) / mad
    return out


def edgar_flags(pnl):
    """Return dict of TxN boolean 'event happened within the last W weeks' matrices."""
    grid = pnl["grid"]
    tickers = pnl["tickers"]
    T, N = len(grid), len(tickers)
    ti = {t: i for i, t in enumerate(tickers)}
    if not EDGAR.exists():
        return None, {"available": False}
    with gzip.open(EDGAR, "rt") as fh:
        blob = json.load(fh)
    data = blob["data"]

    def cls(form):
        f = form.upper()
        if f.startswith("SC 13D"):
            return "ACTIVIST"
        if f.startswith("SC 13G"):
            return "PLACEBO13G"
        if f.startswith("SC TO") or f.startswith("SC 13E") or f.startswith("SC 14D"):
            return "TENDER"
        if f.startswith("N-23C"):
            return "REPURCH"
        if f.startswith("N-2") or f.startswith("424B"):
            return "RIGHTS"
        return None

    ev = defaultdict(lambda: defaultdict(list))   # kind -> ticker -> [dates]
    counts = defaultdict(int)
    for tk, rec in data.items():
        if tk not in ti:
            continue
        for row in rec["filings"]:
            k = cls(row[0])
            if k is None:
                continue
            d = row[1]
            if d < grid[0] or d > grid[-1]:
                continue
            ev[k][tk].append(d)
            counts[k] += 1

    out = {}
    for kind in ("ACTIVIST", "PLACEBO13G", "TENDER", "REPURCH", "RIGHTS"):
        for W in (13, 26):
            M = np.zeros((T, N), dtype=bool)
            for tk, dates in ev[kind].items():
                i = ti[tk]
                for d in dates:
                    k0 = int(np.searchsorted(grid, d, side="left"))
                    for k in range(k0, min(T, k0 + W)):
                        M[k, i] = True
            out[f"{kind}_{W}"] = M
    meta = {"available": True, "fetched": blob.get("fetched_utc"),
            "n_tickers_with_cik": blob.get("n_tickers"),
            "missing_tickers": len(blob.get("missing", [])),
            "event_counts_in_window": dict(counts),
            "funds_with_event": {k: len(v) for k, v in ev.items()},
            "fund_weeks_flagged_26w": {k: int(out[f"{k}_26"].sum())
                                       for k in ("ACTIVIST", "PLACEBO13G", "TENDER", "REPURCH", "RIGHTS")}}
    return out, meta


def catalogue(pnl, flags):
    D, P, V, R, Y, RVT = pnl["D"], pnl["P"], pnl["V"], pnl["R"], pnl["Y"], pnl["RVT"]
    cat, grp = pnl["cat"], pnl["grp"]
    statics = pnl["statics"]
    tickers = pnl["tickers"]
    T, N = D.shape

    # --- 2a. PIT distribution RUN-RATE from reconstructed per-payment amounts -----------
    # LOOK-AHEAD GUARD. Y[k] = R[k] - RP[k] is the distribution realised over week k -> k+1,
    # i.e. CONTEMPORANEOUS with the return the book at k earns. Every distribution primitive
    # below is built from Y SHIFTED ONE WEEK, so index k uses weeks <= k-1 only.
    #
    # A 13-week SUM of the reconstructed distribution is dominated by ex-date TIMING noise
    # (a monthly payer whose payment crosses a window boundary swings the sum by ~33%); the
    # measured median |quarter-over-quarter change| was 6.8%, far above the real rate of
    # distribution changes. So the run-rate is instead the MEDIAN OF THE LAST 3 RECONSTRUCTED
    # PAYMENTS, compared with the median of the 3 before those -- a per-payment comparison
    # that is immune to ex-date timing. Measured median |change| falls to 2.45%.
    dps_raw = np.where(np.isfinite(Y) & np.isfinite(P), np.nan_to_num(Y) * P, np.nan)
    dps = np.vstack([np.full((1, N), np.nan), dps_raw[:-1]])
    Pl = np.vstack([np.full((1, N), np.nan), P[:-1]])
    pay = dps > 0.001 * Pl                     # >10 bp of price counts as a real payment
    cur = np.full((T, N), np.nan)
    prv = np.full((T, N), np.nan)
    K = 3
    for i in range(N):
        idx = [k for k in range(T) if pay[k, i]]
        amt = [dps[k, i] for k in idx]
        ptr = 0
        for k in range(T):
            while ptr < len(idx) and idx[ptr] <= k:
                ptr += 1
            if ptr >= K:
                cur[k, i] = np.median(amt[ptr - K:ptr])
            if ptr >= 2 * K:
                prv[k, i] = np.median(amt[ptr - 2 * K:ptr - K])
    with np.errstate(invalid="ignore", divide="ignore"):
        ddps = np.where(prv > 1e-4, cur / prv - 1.0, np.nan)
    ddps = np.where(np.abs(ddps) > 3.0, np.nan, ddps)

    freq = np.array([(statics.get(t, {}).get("DistributionFrequency") or "") for t in tickers])
    regular = np.tile((freq == "Monthly") | (freq == "Quarterly"), (T, 1))

    CUT = regular & (ddps < -0.05)
    RAISE = regular & (ddps > 0.05)
    CUT10 = regular & (ddps < -0.10)
    RAISE10 = regular & (ddps > 0.10)
    chg26 = np.zeros((T, N), dtype=bool)
    unstable = regular & (np.abs(ddps) > 0.02)
    for L in range(0, 26):
        sh = np.zeros((T, N), dtype=bool)
        sh[L:] = unstable[:T - L] if L else unstable
        chg26 |= sh
    STABLE = regular & (~chg26) & np.isfinite(ddps)

    ddps_s = np.where(regular, ddps, np.nan)

    # --- 2b. PIT NAV erosion (coverage proxy) ------------------------------------------
    RV_raw = np.full((T, N), np.nan)
    RV_raw[:-1] = V[1:] / V[:-1] - 1.0
    # same look-ahead guard: RV[k] is the NAV move over the traded week k -> k+1
    RV = np.vstack([np.full((1, N), np.nan), RV_raw[:-1]])
    ero52 = _roll_sum(RV, 52)                       # 52w NAV PRICE return, strictly trailing
    ero_x = _demean_by(ero52, cat)                  # market direction removed
    med_e = np.nanmedian(ero_x, axis=1, keepdims=True)
    COVERED = ero_x >= med_e                        # NAV holding up = distribution earned
    ERODING = ero_x < med_e

    # --- 2c. risk-normalised / MAD-standardised discount --------------------------------
    navvol = _roll_std(RV, 52)
    dvol = np.where(navvol > 1e-5, D / (navvol * 100.0), np.nan)
    dmad_cat = _roll_median_cs(D, cat)
    dmad_grp = _roll_median_cs(D, grp)
    levr = np.array([(statics.get(t, {}).get("LeverageRatioPercentage") or 0.0)
                     for t in tickers], dtype=float)
    lev_ok = levr > 0
    dlev = np.where(np.tile(lev_ok, (T, 1)), D / np.tile(np.maximum(levr, 1.0), (T, 1)), np.nan)

    # --- idiosyncratic (category-relative) NAV total-return momentum ---------------------
    lv = np.log1p(np.nan_to_num(RVT, nan=0.0)) * np.isfinite(RVT)
    lv_x = _demean_by(lv, cat)
    lvp = np.vstack([np.full((1, N), np.nan), lv_x[:-1]])
    inav4 = _roll_sum(lvp, 4)
    inav13 = _roll_sum(lvp, 13)

    mdp = np.tile(np.array([bool(statics.get(t, {}).get("IsManagedDistribution"))
                            for t in tickers]), (T, 1))

    F = []

    def add(key, desc, score, **kw):
        F.append(dict(key=key, desc=desc, score=score, kw=kw))

    add("REF_T12_LEVEL", "INCUMBENT L5: discount LEVEL decile tilt", -D, H=4, reference=True)
    add("REF_T12_LEVEL_H1", "control: incumbent signal at 1-week hold", -D, H=1, reference=True)

    # ---- E: distribution-policy events ----
    add("E01_ddps_fade_H4",
        "fade the PIT quarterly distribution RUN-RATE change (cut -> long, raise -> short)",
        -ddps_s, H=4)
    add("E02_ddps_resid_level_H4",
        "distribution run-rate change ORTHOGONALISED cross-sectionally to the discount level",
        -_xs_resid(ddps_s, D), H=4)
    add("E03_cut_vs_raise_H4",
        "event book: long the recent-CUT cohort, short the recent-RAISE cohort (equal weight)",
        np.where(CUT, 1.0, np.where(RAISE, -1.0, np.nan)), H=4, frac=0.5, min_names=8)
    add("E04_level_in_stable_H4",
        "discount level tilt restricted to funds with a STABLE distribution (no +-5% run-rate "
        "change in 26w)", -D, H=4, mask=STABLE)
    add("E05_level_in_cut_H4",
        "discount level tilt restricted to funds that recently CUT", -D, H=4,
        mask=chg26 & (ddps_s < 0), min_names=8)
    add("E06_ddps_in_muni_eq_H4",
        "distribution run-rate change fade, MUNI+EQUITY only", -ddps_s, H=4,
        mask=np.tile((grp == "MUNI") | (grp == "EQUITY"), (T, 1)))
    add("E08_cut10_vs_raise10_H4",
        "event book at a +-10% run-rate threshold instead of +-5% (the threshold is reported, "
        "not tuned: both are run)",
        np.where(CUT10, 1.0, np.where(RAISE10, -1.0, np.nan)), H=4, frac=0.5, min_names=8)
    add("E07_ddps_in_taxfi_H4",
        "distribution run-rate change fade, TAXABLE-CREDIT only", -ddps_s, H=4,
        mask=np.tile(grp == "TAXFI", (T, 1)))

    # ---- N: NAV erosion / distribution coverage ----
    add("N01_lowerosion_H4", "long funds whose 52w category-relative NAV EROSION is smallest "
        "(distribution is earned, not returned capital)", ero_x, H=4)
    add("N02_level_in_covered_H4", "discount level tilt inside the WELL-COVERED half",
        -D, H=4, mask=COVERED)
    add("N03_level_in_eroding_H4", "discount level tilt inside the ERODING half (mirror)",
        -D, H=4, mask=ERODING)
    add("N04_level_resid_erosion_H4",
        "discount level orthogonalised to NAV erosion", -_xs_resid(D, ero_x), H=4)
    add("N05_erosion_resid_level_H4",
        "NAV erosion orthogonalised to the discount level (the residual L5 cannot span)",
        _xs_resid(ero_x, D), H=4)

    # ---- R: risk-normalised / dispersion-standardised discount ----
    add("R01_disc_per_navvol_H4",
        "discount divided by the fund's own trailing 52w NAV volatility", -dvol, H=4)
    add("R02_disc_cat_mad_H4",
        "discount standardised within Morningstar CATEGORY by the category MAD (not merely "
        "demeaned) -- cross-sectional dispersion normalisation", -dmad_cat, H=4)
    add("R03_disc_grp_mad_H4", "discount standardised within broad group by group MAD",
        -dmad_grp, H=4)
    add("R04_disc_per_leverage_H4",
        "discount divided by the fund's leverage ratio (levered funds structurally price "
        "differently)", -dlev, H=4, min_names=15)

    # ---- I: category-relative NAV lead-lag ----
    add("I01_idio_navmom4_H4",
        "long 4w category-RELATIVE NAV total-return momentum (price under-reacts to "
        "idiosyncratic NAV news; the raw version S03 was already dead)", inav4, H=4)
    add("I02_idio_navmom13_H4", "long 13w category-relative NAV total-return momentum",
        inav13, H=4)
    add("I03_idio_navmom4_fade_H4", "FADE 4w category-relative NAV momentum (mirror)",
        -inav4, H=4)

    # ---- G: structural statics ----
    add("G01_level_in_mdp_H4",
        "discount level tilt inside MANAGED-DISTRIBUTION funds only", -D, H=4, mask=mdp)
    add("G02_level_in_nonmdp_H4", "discount level tilt inside NON-managed-distribution funds",
        -D, H=4, mask=~mdp)

    # ---- A: EDGAR corporate-action events ----
    if flags:
        act = flags["ACTIVIST_26"]
        pl = flags["PLACEBO13G_26"]
        ten = flags["TENDER_26"]
        rgt = flags["RIGHTS_13"]
        add("A01_activist_long_H4",
            "long the SC 13D ACTIVIST cohort vs the rest of the universe",
            np.where(act, 1.0, 0.0) + 1e-6 * np.where(np.isfinite(D), 0.0, np.nan), H=4,
            frac=0.10)
        add("A02_level_in_activist_H4",
            "discount level tilt restricted to the SC 13D activist cohort", -D, H=4,
            mask=act, min_names=8)
        add("A03_level_ex_activist_H4",
            "discount level tilt EXCLUDING the activist cohort", -D, H=4, mask=~act)
        add("A04_placebo13g_long_H4",
            "PLACEBO: long the SC 13G (passive) cohort -- must be inert if A01 is a story",
            np.where(pl, 1.0, 0.0) + 1e-6 * np.where(np.isfinite(D), 0.0, np.nan), H=4,
            frac=0.10)
        add("A05_tender_long_H4", "long the issuer-TENDER cohort (SC TO / 13E / 14D)",
            np.where(ten, 1.0, 0.0) + 1e-6 * np.where(np.isfinite(D), 0.0, np.nan), H=4,
            frac=0.10)
        add("A06_rights_fade_H4",
            "WEAK LABEL: short the recent N-2 / 424B (rights-offering / shelf) cohort, then "
            "long the rest -- dilution widens the discount and then reverts",
            np.where(rgt, -1.0, 0.0) + 1e-6 * np.where(np.isfinite(D), 0.0, np.nan), H=4,
            frac=0.10)
        add("A08_repurch_long_H4",
            "long the N-23C share-repurchase / preferred-redemption notice cohort",
            np.where(flags["REPURCH_26"], 1.0, 0.0)
            + 1e-6 * np.where(np.isfinite(D), 0.0, np.nan), H=4, frac=0.10)
        add("A09_level_in_repurch_H4",
            "discount level tilt inside the N-23C repurchase-notice cohort", -D, H=4,
            mask=flags["REPURCH_26"], min_names=8)
        add("A07_activist_x_widedisc_H4",
            "activist cohort AND wide discount: level tilt inside activist names, 13w window",
            -D, H=4, mask=flags["ACTIVIST_13"], min_names=8)

    # ---- B: FULLY EXECUTABLE, SIGN-SYMMETRIC construction -----------------------------
    # book_from_score screens only the SHORT leg to easy-to-borrow, so an unrestricted long
    # leg is compared with a restricted short leg and a sign flip is NOT a mirror. That
    # asymmetry can masquerade as a huge one-sided effect. Restricting the WHOLE universe to
    # ETB names makes the book executable on both legs and makes the sign flip an exact
    # mirror, so the two-sided search becomes honest. Run for the incumbent and for every
    # structure that looked strong on the asymmetric construction.
    etbm = np.tile(pnl["etb"], (T, 1))

    def both(mask):
        return etbm if mask is None else (mask & etbm)

    add("B00_L5_level_etbboth_H4", "CONTROL: the incumbent L5 level tilt with BOTH legs "
        "restricted to easy-to-borrow (fully executable, sign-symmetric)", -D, H=4, mask=etbm)
    add("B01_idio_navmom4_etbboth_H4",
        "long 4w category-relative NAV momentum, BOTH legs ETB", inav4, H=4, mask=etbm)
    add("B02_idio_navmom4_fade_etbboth_H4",
        "FADE 4w category-relative NAV momentum, BOTH legs ETB (exact mirror of B01)",
        -inav4, H=4, mask=etbm)
    add("B03_disc_grp_mad_etbboth_H4", "group-MAD-standardised discount, BOTH legs ETB",
        -dmad_grp, H=4, mask=etbm)
    add("B04_ddps_fade_etbboth_H4", "fade the distribution run-rate change, BOTH legs ETB",
        -ddps_s, H=4, mask=both(regular))
    add("B05_ddps_mom_etbboth_H4", "FOLLOW the distribution run-rate change, BOTH legs ETB "
        "(exact mirror of B04)", ddps_s, H=4, mask=both(regular))
    add("B06_lowerosion_etbboth_H4", "long low NAV erosion, BOTH legs ETB", ero_x, H=4,
        mask=etbm)
    add("B07_higherosion_etbboth_H4", "long high NAV erosion, BOTH legs ETB (mirror of B06)",
        -ero_x, H=4, mask=etbm)
    if flags:
        add("B08_activist_long_etbboth_H4", "long the SC 13D activist cohort, BOTH legs ETB",
            np.where(flags["ACTIVIST_26"], 1.0, 0.0)
            + 1e-6 * np.where(np.isfinite(D), 0.0, np.nan), H=4, frac=0.10, mask=etbm)
        add("B09_placebo13g_etbboth_H4", "PLACEBO: long the SC 13G cohort, BOTH legs ETB",
            np.where(flags["PLACEBO13G_26"], 1.0, 0.0)
            + 1e-6 * np.where(np.isfinite(D), 0.0, np.nan), H=4, frac=0.10, mask=etbm)

    # ---- honest two-sidedness ------------------------------------------------------
    # The book is NOT symmetric under a sign flip: only the SHORT leg is ETB-screened, so
    # negating a score produces a genuinely different, and possibly non-executable, book.
    # A two-sided search therefore has to RUN both signs, not assert the mirror by symmetry.
    # For scores derived from the discount LEVEL the sign is fixed a priori by the incumbent's
    # established direction (wide discount -> long) and is not searched. For the NEW primitives
    # -- distribution run-rate change, NAV erosion, category-relative NAV momentum, EDGAR event
    # cohorts -- the sign is genuinely free, so both are run and BOTH count towards N.
    SIGN_FREE = ("E01", "E02", "E03", "E06", "E07", "E08", "N01", "N05",
                 "I01", "I02", "I03", "A01", "A04", "A05", "A06", "A08")
    mirrors = []
    for f in F:
        if f["kw"].get("reference"):
            continue
        if not f["key"].split("_")[0] in SIGN_FREE:
            continue
        mirrors.append(dict(key=f["key"].rsplit("_H", 1)[0] + "_NEG_H4",
                            desc="MIRROR (sign flipped, re-run not asserted): " + f["desc"],
                            score=-f["score"], kw=dict(f["kw"])))
    F.extend(mirrors)

    extra = []
    for f in F:
        if f["kw"].get("reference"):
            continue
        kw = dict(f["kw"])
        kw["H"] = 1
        extra.append(dict(key=f["key"].rsplit("_H", 1)[0] + "_H1",
                          desc=f["desc"] + " [hold 1w]", score=f["score"], kw=kw))
    F.extend(extra)
    return F


# ---------------------------------------------------------------------------
# bounce gate
# ---------------------------------------------------------------------------

def rho1_discount(pnl):
    D = pnl["D"]
    dD = np.diff(D, axis=0)
    vals = []
    for i in range(dD.shape[1]):
        x = dD[:, i]
        x = x[np.isfinite(x)]
        if len(x) < 60:
            continue
        s = np.std(x)
        if s <= 0:
            continue
        vals.append(float(np.corrcoef(x[:-1], x[1:])[0, 1]))
    return dict(n_funds=len(vals), rho1_median=float(np.median(vals)),
                rho1_mean=float(np.mean(vals)),
                rho1_p10=float(np.percentile(vals, 10)),
                rho1_p90=float(np.percentile(vals, 90)))


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------

def main(stage="design"):
    pnl = build_panel()
    grid = pnl["grid"]
    T = len(grid)
    split_k = next(k for k, d in enumerate(grid) if d >= SPLIT)
    k_end = T - 1
    reveal = stage == "reveal"

    flags, emeta = edgar_flags(pnl)
    F = catalogue(pnl, flags)
    refs = [f for f in F if f["kw"].get("reference")]

    def build(f, H=None):
        kw = dict(f["kw"])
        kw.pop("reference", None)
        H = kw.pop("H") if H is None else (kw.pop("H"), H)[1]
        W, counts = book_from_score(f["score"], pnl, H=H, **kw)
        return W, counts

    def evaluate(W, counts):
        live = np.flatnonzero(np.abs(W).sum(axis=1) > 1e-9)
        if live.size == 0:
            return None
        k0 = int(live[0])
        des = net_series(W, pnl, k0, split_k)
        hld = net_series(W, pnl, max(k0, split_k), k_end)

        def ladder(a, b):
            return dict(
                lag1_trading_day=summarise(net_series(W, pnl, a, b, rkey="R_LAG1")[:, 1]),
                spread_p90_27p25=summarise(net_series(W, pnl, a, b,
                                                      half_spread_bp=27.25)[:, 1]),
                lag1_and_p90=summarise(net_series(W, pnl, a, b, rkey="R_LAG1",
                                                  half_spread_bp=27.25)[:, 1]),
            )
        nl = [c[0] for c in counts if c[0]]
        ns = [c[1] for c in counts if c[1]]
        return dict(k0=k0, design=des, held=hld,
                    stress=ladder(k0, split_k),
                    hstress=ladder(max(k0, split_k), k_end),
                    dlag=net_series(W, pnl, k0, split_k, rkey="R_LAG1",
                                    half_spread_bp=27.25)[:, 1],
                    hlag=net_series(W, pnl, max(k0, split_k), k_end, rkey="R_LAG1",
                                    half_spread_bp=27.25)[:, 1],
                    n_long_med=float(np.median(nl)) if nl else 0,
                    n_short_med=float(np.median(ns)) if ns else 0,
                    turnover_med=float(np.median(des[:, 2])) if len(des) else None)

    ref_r = evaluate(*build(refs[0]))
    ref1_r = evaluate(*build(refs[1]))
    ref_d, ref_h = ref_r["design"][:, 1], ref_r["held"][:, 1]
    ref1_d, ref1_h = ref1_r["design"][:, 1], ref1_r["held"][:, 1]
    ref_dl, ref_hl = ref_r["dlag"], ref_r["hlag"]
    ref1_dl, ref1_hl = ref1_r["dlag"], ref1_r["hlag"]

    def reg2(y, f1, f2):
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

    def reg1(y, x):
        n = min(len(y), len(x))
        if n < 12:
            return None
        y, x = y[-n:], x[-n:]
        if np.std(x) <= 0:
            return None
        b = np.cov(x, y, bias=True)[0, 1] / np.var(x)
        a = y.mean() - b * x.mean()
        resid = y - (a + b * x)
        se = np.std(resid, ddof=2) / math.sqrt(n)
        return dict(beta=float(b), alpha_bp=float(a) * 1e4,
                    alpha_t=float(a / se) if se > 0 else 0.0,
                    corr=float(np.corrcoef(x, y)[0, 1]))

    rows = []
    for f in F:
        if f["kw"].get("reference"):
            continue
        try:
            r = evaluate(*build(f))
        except Exception as e:                       # noqa: BLE001
            print("skip", f["key"], e)
            continue
        if r is None or len(r["design"]) < 20 or len(r["held"]) < 20:
            continue
        dn = r["design"][:, 1]
        half = len(dn) // 2
        rows.append(dict(
            key=f["key"], desc=f["desc"], hold_weeks=f["kw"].get("H"),
            n_long_med=r["n_long_med"], n_short_med=r["n_short_med"],
            turnover_med=r["turnover_med"],
            design=summarise(dn), design_gross=summarise(r["design"][:, 0]),
            design_stress=dict(r["stress"],
                               first_half=summarise(dn[:half]),
                               second_half=summarise(dn[half:])),
            design_vs_incumbent=reg1(dn, ref_d),
            design_alpha_2factor=reg2(dn, ref_d, ref1_d),
            design_alpha_2factor_stressed=reg2(r["dlag"], ref_dl, ref1_dl),
            held_out=summarise(r["held"][:, 1]) if reveal else "SEALED",
            held_out_stress=r["hstress"] if reveal else "SEALED",
            held_vs_incumbent=reg1(r["held"][:, 1], ref_h) if reveal else "SEALED",
            held_alpha_2factor=reg2(r["held"][:, 1], ref_h, ref1_h) if reveal else "SEALED",
            held_alpha_2factor_stressed=(reg2(r["hlag"], ref_hl, ref1_hl)
                                         if reveal else "SEALED"),
        ))

    Nf = len(rows)
    bar_analytic = math.sqrt(2 * math.log(max(2 * Nf, 2)))

    # ---- size-matched placebo: fund-identity permutation, held fixed through time ----
    placebo_keys = ["E01_ddps_fade_H4", "N01_lowerosion_H4", "R02_disc_cat_mad_H4",
                    "I01_idio_navmom4_H4", "E01_ddps_fade_H1", "R02_disc_cat_mad_H1"]
    fmap = {f["key"]: f for f in F}
    pl_t, pl_at, pl_gt = [], [], []
    per_key = {}
    for pk in placebo_keys:
        f = fmap.get(pk)
        if f is None:
            continue
        ts, ats, gts = [], [], []
        for _ in range(N_PLACEBO // len(placebo_keys) * 2):
            perm = RNG.permutation(f["score"].shape[1])
            g = dict(f)
            g["score"] = f["score"][:, perm]
            kw = dict(f["kw"])
            if isinstance(kw.get("mask"), np.ndarray) and kw["mask"].ndim == 2:
                kw = dict(kw, mask=kw["mask"][:, perm])
            g["kw"] = kw
            try:
                rr = evaluate(*build(g))
            except Exception:                        # noqa: BLE001
                continue
            if rr is None or len(rr["design"]) < 20:
                continue
            s = summarise(rr["design"][:, 1])
            sg = summarise(rr["design"][:, 0])
            if sg:
                gts.append(sg["t"])
            if s:
                ts.append(s["t"])
                a = reg2(rr["design"][:, 1], ref_d, ref1_d)
                if a:
                    ats.append(a["alpha_t"])
        if ts:
            per_key[pk] = dict(n=len(ts), sd_t=float(np.std(ts, ddof=1)),
                               mean_t=float(np.mean(ts)),
                               p95_abs_t=float(np.percentile(np.abs(ts), 95)),
                               sd_alpha_t=float(np.std(ats, ddof=1)) if len(ats) > 2 else None)
        pl_t += ts
        pl_at += ats
        pl_gt += gts
    sd_t = float(np.std(pl_t, ddof=1)) if len(pl_t) > 5 else 1.0
    sd_gt = float(np.std(pl_gt, ddof=1)) if len(pl_gt) > 5 else 1.0
    sd_at = float(np.std(pl_at, ddof=1)) if len(pl_at) > 5 else 1.0
    bar_placebo = sd_t * bar_analytic
    bar_gross = sd_gt * bar_analytic
    bar_alpha = sd_at * bar_analytic

    doc = dict(
        theme="CEF structure beyond the discount level: distribution-policy events, NAV-erosion "
              "coverage, EDGAR corporate actions, dispersion-normalised discount",
        stage=stage,
        incumbent=dict(slot="L5", id="T12CEF",
                       design=summarise(ref_d), design_stress=ref_r["stress"],
                       held_out=summarise(ref_h) if reveal else "SEALED",
                       held_out_stress=ref_r["hstress"] if reveal else "SEALED"),
        data=dict(cached="research/data/t12_cache (CEFConnect weekly + Alpaca adjusted daily)",
                  edgar=emeta, grid_weeks=T, first=grid[0], last=grid[-1],
                  funds=len(pnl["tickers"])),
        window=dict(design=f"{grid[0]} .. {grid[split_k-1]}",
                    held_out=f"{grid[split_k]} .. {grid[-1]}", split=SPLIT),
        bounce_gate=dict(
            rho1_of_weekly_discount_change=rho1_discount(pnl),
            rule="need rho1 > ~-0.35; below that the spread family is closing-print bounce"),
        n_formulas=Nf,
        noise_bar=dict(analytic_sqrt_2ln2N=bar_analytic,
                       placebo_sd_of_t=sd_t,
                       placebo_sd_of_alpha_t=sd_at,
                       size_matched_expected_max_t=bar_placebo,
                       placebo_sd_of_gross_t=sd_gt,
                       size_matched_expected_max_GROSS_t=bar_gross,
                       size_matched_expected_max_alpha_t=bar_alpha,
                       placebo_method="fund-identity permutation of the score matrix, fixed "
                                      "through time; preserves persistence, book size, "
                                      "turnover and every screen",
                       placebo_per_structure=per_key,
                       n_placebo_draws=len(pl_t)),
        results=sorted(rows, key=lambda r: -abs(r["design"]["t"])),
    )
    name = "INVENT_0822C_cefdeep.json" if reveal else "INVENT_0822C_cefdeep_DESIGN.json"
    (OUT / name).write_text(json.dumps(doc, indent=1, default=float) + "\n")

    print(f"stage={stage}  N={Nf}  analytic_bar={bar_analytic:.3f}  "
          f"placebo_sd_t={sd_t:.3f} -> size-matched bar {bar_placebo:.3f}  "
          f"(alpha bar {bar_alpha:.3f})")
    print("rho1(dDiscount) median = %.3f" % doc["bounce_gate"]
          ["rho1_of_weekly_discount_change"]["rho1_median"])
    hdr = (f"{'key':34s} {'nD':>4s} {'dSh':>6s} {'dt':>6s} {'turn':>5s} {'nL':>4s} {'nS':>4s} "
           f"{'corr':>6s} {'da2T':>6s} {'dStrs':>6s} {'ds2T':>6s}")
    print(hdr + ("| {:>6s} {:>6s} {:>6s} {:>6s}".format("hSh", "ha2T", "hStrs", "hs2T")
                 if reveal else ""))
    for r in doc["results"]:
        d, dv = r["design"], r["design_vs_incumbent"]
        st = r["design_stress"]
        line = (f"{r['key']:34s} {d['n']:4d} {d['ann_sharpe']:6.2f} {d['t']:6.2f} "
                f"{(r['turnover_med'] or 0):5.2f} {r['n_long_med']:4.0f} {r['n_short_med']:4.0f} "
                f"{(dv or {}).get('corr', 0):6.2f} "
                f"{(r['design_alpha_2factor'] or {}).get('alpha_t', 0):6.2f} "
                f"{(st['lag1_and_p90'] or {}).get('ann_sharpe', 0):6.2f} "
                f"{(r['design_alpha_2factor_stressed'] or {}).get('alpha_t', 0):6.2f}")
        if reveal:
            h = r["held_out"]
            line += (f"| {h['ann_sharpe']:6.2f} "
                     f"{(r['held_alpha_2factor'] or {}).get('alpha_t', 0):6.2f} "
                     f"{(r['held_out_stress']['lag1_and_p90'] or {}).get('ann_sharpe', 0):6.2f} "
                     f"{(r['held_alpha_2factor_stressed'] or {}).get('alpha_t', 0):6.2f}")
        print(line)
    print("\n=== ranked by |GROSS design t| (the correct pooled screen; a large NEGATIVE net t "
          "on a sign-free formula is friction, not signal) ===")
    print(f"{'key':34s} {'gSh':>6s} {'gt':>6s} {'nSh':>6s} {'strsSh':>7s} {'ds2T':>6s}")
    for r in sorted(doc["results"], key=lambda r: -abs(r["design_gross"]["t"]))[:20]:
        print(f"{r['key']:34s} {r['design_gross']['ann_sharpe']:6.2f} "
              f"{r['design_gross']['t']:6.2f} {r['design']['ann_sharpe']:6.2f} "
              f"{(r['design_stress']['lag1_and_p90'] or {}).get('ann_sharpe',0):7.2f} "
              f"{(r['design_alpha_2factor_stressed'] or {}).get('alpha_t',0):6.2f}")
    inc = doc["incumbent"]
    print(f"\nINCUMBENT L5 design Sh {inc['design']['ann_sharpe']:.2f} t {inc['design']['t']:.2f}"
          f"  stressed {inc['design_stress']['lag1_and_p90']['ann_sharpe']:.2f}"
          + (f"  | held {inc['held_out']['ann_sharpe']:.2f}"
             f" stressed {inc['held_out_stress']['lag1_and_p90']['ann_sharpe']:.2f}"
             if reveal else ""))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "design")
