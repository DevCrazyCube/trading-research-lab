"""POSTURE C2 analyzer — EW-mean basket vs cross-sectional MEDIAN, per cross-section.

Implements the pre-registered gates in c2_prereg.md exactly:
  GATE 1 coverage (>=8 members, >=1000 admissible dates, >=60% member coverage)
  GATE 2 power    MDE = 2.48557 * sd(g_t)/sqrt(T); DEFF = 1+(mbar-1)*0.30
  GATE 3 effect   cluster bootstrap by DATE, 5000 draws, seed 20260903
Kill line theta = 5.0 bp/day.
"""
import json
import os
import sys

import numpy as np

CACHE = "/home/anont/meme/research/data/c2_cache"
SEED = 20260903
NBOOT = 5000
THETA_BP = 5.0          # kill line, bp/day
MIN_MEMBERS = 8
MIN_DATES = 1000
MIN_COVER = 0.60
Z = 1.6448536269514722 + 0.8416212335729143   # z_.95 + z_.80 = 2.48648


def load(name):
    z = np.load(os.path.join(CACHE, name + ".npz"), allow_pickle=True)
    return z["dates"], np.array([str(s) for s in z["syms"]]), z["px"]


def strip_redenominations(px, tol=0.03, min_exp=2):
    """Remove currency redenominations (units changes, not price moves).

    A redenomination is a jump between consecutive observations whose ratio is
    within `tol` of 10**k for integer |k| >= min_exp. Venezuela alone did 1:1000
    (2008), 1:100000 (2018) and 1:1000000 (2021); leaving them in produces a
    +1,000,000x 'return' that is not obtainable by any holder. Genuine
    devaluations (e.g. VEF -99.7% on 2018-02-05, a 1:334 DICOM step) are NOT
    powers of ten and are left untouched.
    Returns (px_clean, n_fixed).
    """
    px = px.copy()
    nfix = 0
    for j in range(px.shape[1]):
        v = px[:, j]
        ok = np.where(~np.isnan(v))[0]
        if len(ok) < 3:
            continue
        for a, b in zip(ok[:-1], ok[1:]):
            ratio = v[b] / v[a]
            if ratio <= 0:
                continue
            k = round(np.log10(ratio))
            if abs(k) >= min_exp and abs(ratio / (10.0 ** k) - 1.0) <= tol:
                px[b:, j] /= (10.0 ** k)
                v = px[:, j]
                nfix += 1
    return px, nfix


def returns_matrix(dates, syms, px, start=None, end=None):
    """Return (dates_kept, syms_kept, R) with R nan where undefined.

    A member's return on kept date t exists only if it has a price on t and on
    the immediately preceding kept date (no forward fill, no stale zeros).
    """
    m = np.ones(len(dates), bool)
    if start is not None:
        m &= dates >= start
    if end is not None:
        m &= dates <= end
    dates, px = dates[m], px[m]

    live = ~np.isnan(px)
    # drop members with too little coverage inside the window
    first = np.array([np.argmax(live[:, j]) if live[:, j].any() else -1
                      for j in range(px.shape[1])])
    last = np.array([len(dates) - 1 - np.argmax(live[::-1, j]) if live[:, j].any()
                     else -1 for j in range(px.shape[1])])
    keep = []
    for j in range(px.shape[1]):
        if first[j] < 0:
            continue
        span = last[j] - first[j] + 1
        if span < 250:
            continue
        if live[first[j]:last[j] + 1, j].mean() < MIN_COVER:
            continue
        keep.append(j)
    if not keep:
        return dates[:0], syms[:0], np.zeros((0, 0))
    px, syms = px[:, keep], syms[keep]
    live = ~np.isnan(px)

    # keep dates where >= MIN_MEMBERS members have a price
    dm = live.sum(1) >= MIN_MEMBERS
    dates, px, live = dates[dm], px[dm], live[dm]
    if len(dates) < 2:
        return dates[:0], syms[:0], np.zeros((0, 0))

    R = np.full((len(dates) - 1, px.shape[1]), np.nan)
    ok = live[1:] & live[:-1]
    R[ok] = (px[1:] / px[:-1] - 1.0)[ok]
    d = dates[1:]

    # keep dates with >= MIN_MEMBERS defined returns
    rm = (~np.isnan(R)).sum(1) >= MIN_MEMBERS
    return d[rm], syms, R[rm]


def ew_med(R):
    ew = np.nanmean(R, axis=1)
    med = np.nanmedian(R, axis=1)
    return ew, med


def boot_ci(g, nboot=NBOOT, seed=SEED):
    rng = np.random.default_rng(seed)
    T = len(g)
    idx = rng.integers(0, T, size=(nboot, T))
    draws = g[idx].mean(axis=1)
    lo, hi = np.percentile(draws, [2.5, 97.5])
    return lo, hi, draws


def horizon_stats(d, R, h):
    """Non-overlapping h-day windows. Returns (gap_per_day_pp, nwin, top1, top5)."""
    T = len(d)
    nw = T // h
    if nw < 2:
        return None
    ew_t, _ = ew_med(R)
    gaps, allmem = [], []
    bask, medm = [], []
    for w in range(nw):
        sl = slice(w * h, (w + 1) * h)
        Rw = R[sl]
        b = np.prod(1.0 + ew_t[sl]) - 1.0
        # member compound over the window: require full coverage in the window
        cov = (~np.isnan(Rw)).mean(axis=0)
        sel = cov >= 0.9
        if sel.sum() < MIN_MEMBERS:
            continue
        Rc = np.where(np.isnan(Rw[:, sel]), 0.0, Rw[:, sel])
        comp = np.prod(1.0 + Rc, axis=0) - 1.0
        gaps.append(b - np.median(comp))
        bask.append(b)
        medm.append(np.median(comp))
        allmem.append(comp)
    if len(gaps) < 2:
        return None
    allmem = np.concatenate(allmem)
    s = np.sort(allmem)[::-1]
    tot = s.sum()
    n1 = max(1, int(round(0.01 * len(s))))
    n5 = max(1, int(round(0.05 * len(s))))
    top1 = s[:n1].sum() / tot if tot != 0 else float("nan")
    top5 = s[:n5].sum() / tot if tot != 0 else float("nan")
    return dict(h=h, nwin=len(gaps), gap_pp_day=100.0 * float(np.mean(gaps)) / h,
                top1=float(top1), top5=float(top5), tot_sign=float(np.sign(tot)),
                n_obs=int(len(s)),
                basket_comp=float(np.prod(1.0 + np.array(bask)) - 1.0),
                med_comp=float(np.prod(1.0 + np.array(medm)) - 1.0))


def analyze(name, label, start=None, end=None, note="", drop=(), redenom=False):
    dates, syms, px = load(name)
    nfix = 0
    if drop:
        keep = np.array([s not in drop for s in syms])
        syms, px = syms[keep], px[:, keep]
    if redenom:
        px, nfix = strip_redenominations(px)
    d, syms, R = returns_matrix(dates, syms, px, start, end)
    out = dict(name=name, label=label, note=note, n_redenom_fixed=nfix,
               dropped=list(drop))
    if len(d) == 0:
        out.update(gate1="FAIL(no data)", n_members=0, n_dates=0)
        return out
    nmem = R.shape[1]
    T = len(d)
    mbar = float((~np.isnan(R)).sum(1).mean())
    nobs = int((~np.isnan(R)).sum())
    out.update(n_members=int(nmem), n_dates=int(T), mbar=mbar, n_obs=nobs,
               first=int(d[0]), last=int(d[-1]))
    if nmem < MIN_MEMBERS or T < MIN_DATES:
        out["gate1"] = "FAIL (members=%d dates=%d)" % (nmem, T)
        return out
    out["gate1"] = "PASS"

    ew, med = ew_med(R)
    g = ew - med

    # GATE 2 power (nuisance sd only; effect not read yet)
    sd = float(np.std(g, ddof=1))
    mde_pp = Z * sd / np.sqrt(T)
    deff = 1.0 + (mbar - 1.0) * 0.30
    out.update(sd_g_pp=100.0 * sd, mde_bp_day=1e4 * mde_pp,
               deff=deff, n_eff=nobs / deff)
    out["gate2"] = "POWERED" if 1e4 * mde_pp <= THETA_BP else "UNDERPOWERED"

    # GATE 3 effect
    delta = float(np.mean(g))
    lo, hi, draws = boot_ci(g)
    out.update(delta_bp_day=1e4 * delta, ci_lo_bp=1e4 * lo, ci_hi_bp=1e4 * hi,
               p_gt0=float((draws <= 0).mean()),
               p_gt_theta=float((draws <= THETA_BP / 1e4).mean()))

    # compounding (the C1 headline form)
    out["basket_compound_pct"] = 100.0 * (float(np.prod(1.0 + ew)) - 1.0)
    out["median_compound_pct"] = 100.0 * (float(np.prod(1.0 + med)) - 1.0)
    out["ew_mean_pp_day"] = 100.0 * float(np.mean(ew))
    out["med_mean_pp_day"] = 100.0 * float(np.mean(med))

    # --- tail-neutralisation: how much of the basket is carried by its right tail?
    # Replace the top q fraction of each day's member returns with that day's median
    # and recompute the daily-rebalanced basket. Denominator-stable (unlike a
    # top-k%-share ratio, whose denominator goes to zero in low-drift panels).
    # DESCRIPTIVE (not pre-registered): cap the pooled member-day return
    # distribution at its 99th / 95th percentile and recompute the daily-rebalanced
    # basket. How much of the basket survives says how much of it lives in the
    # right tail. Denominator-stable; comparable across cross-sections.
    flat = R[~np.isnan(R)]
    for q, key in ((99.0, "wins_p99_pct"), (95.0, "wins_p95_pct")):
        cap = float(np.percentile(flat, q))
        Rw = np.minimum(R, cap)
        eww = np.nanmean(Rw, axis=1)
        out[key] = 100.0 * (float(np.prod(1.0 + eww)) - 1.0)
        out[key.replace("_pct", "_cap_bp")] = 1e4 * cap

    # median of per-member full-window compounds (cross-check, holdable-per-name)
    comps = []
    for j in range(nmem):
        r = R[:, j]
        v = r[~np.isnan(r)]
        if len(v) >= 0.5 * T:
            comps.append(np.prod(1.0 + v) - 1.0)
    out["median_member_compound_pct"] = (100.0 * float(np.median(comps))
                                         if comps else float("nan"))
    out["n_member_compounds"] = len(comps)
    bc = float(np.prod(1.0 + ew)) - 1.0
    out["frac_members_beating_basket"] = (
        float(np.mean(np.array(comps) > bc)) if comps else float("nan"))

    # verdict
    lo_bp, hi_bp = 1e4 * lo, 1e4 * hi
    if lo_bp > THETA_BP:
        v = "TAIL-DOMINATED"
    elif hi_bp < -THETA_BP:
        v = "INVERSE-SKEWED"
    elif lo_bp <= 0 <= hi_bp and 1e4 * mde_pp <= THETA_BP:
        v = "NOT TAIL-DOMINATED"
    elif 1e4 * mde_pp > THETA_BP:
        v = "UNDERPOWERED"
    else:
        v = "AMBIGUOUS(|gap|<theta, CI excludes 0)"
        if lo_bp > 0 and hi_bp <= THETA_BP:
            v = "MILDLY TAIL-TILTED (<theta)"
        if hi_bp < 0 and lo_bp >= -THETA_BP:
            v = "MILDLY INVERSE (<theta)"
    out["verdict"] = v

    out["horizons"] = [h for h in (horizon_stats(d, R, 1),
                                   horizon_stats(d, R, 21),
                                   horizon_stats(d, R, 252)) if h]
    out["syms"] = list(map(str, syms))
    return out


SPECS = [
    ("fx_g10", "G10 FX vs USD (spot, FRED H.10)", 19990104, None,
     "spot only, carry excluded; EUR replaces DEM/FRF/ITL from 1999", (), False),
    ("fx_em", "EM/Asia FX vs USD, incl. VEF (FRED H.10)", 19990104, None,
     "spot only; VEF redenominations stripped, its real -99.99% devaluation kept",
     (), True),
    ("fx_em", "EM/Asia FX vs USD, investable only (FRED H.10)", 19990104, None,
     "VEF dropped: no offshore NDF market, not holdable", ("VEF",), True),
    ("ecb_fx_em", "EM FX vs EUR, survivorship-COMPLETE (ECB)", 19990104, None,
     "includes 8 currencies the ECB stopped publishing (euro-absorbed + RUB 2022)",
     (), True),
    ("ecb_fx_dm", "DM FX vs EUR (ECB)", 19990104, None, "", (), True),
    ("ust_curve", "US Treasury curve, duration-proxy TR (FRED CMT)", 19990104, None,
     "constant maturities cannot die -> survivorship-complete by construction",
     (), False),
    ("commod_fut", "Commodity futures, front continuous (Yahoo)", None, None,
     "24 CME/ICE contracts alive today; roll embedded in the Yahoo series",
     (), False),
    ("commod_etf", "Commodity ETFs/ETNs (Yahoo adj close)", None, None,
     "survivor-only: closed commodity ETNs are absent", (), False),
    ("bond_credit_etf", "Bond + credit ETFs (Yahoo adj close)", None, None,
     "survivor-only", (), False),
    ("sector_etf", "US sector ETFs (SPDR+Vanguard, 5-min->daily close)", None, None,
     "PRICE return only (no dividends); splits adjusted", (), False),
    ("country_idx", "Country equity indices, local ccy (Yahoo)", None, None,
     "price indices, local currency, no dividends", (), False),
    ("country_etf", "Single-country equity ETFs, USD TR (Yahoo)", None, None,
     "survivor-biased where a country fund closed", (), False),
    ("vol_index", "CBOE volatility indices", None, None,
     "NOT investable: indices, not products - descriptive only", (), False),
    ("us_singlename", "US mega-cap single names (control)", None, None,
     "SURVIVOR-ONLY control: names alive today; understates equity skew",
     (), False),
]


def main():
    res = []
    for name, label, s, e, note, drop, rd in SPECS:
        if not os.path.exists(os.path.join(CACHE, name + ".npz")):
            print("skip (no cache): %s" % name)
            continue
        r = analyze(name, label, s, e, note, drop, rd)
        res.append(r)
        print("\n=== %s" % label)
        print("  gate1=%s members=%s dates=%s obs=%s %s..%s"
              % (r.get("gate1"), r.get("n_members"), r.get("n_dates"),
                 r.get("n_obs"), r.get("first"), r.get("last")))
        if r.get("gate1") != "PASS":
            continue
        print("  GATE2 sd(g)=%.4f pp/day  MDE=%.3f bp/day  DEFF=%.2f n_eff=%.0f -> %s"
              % (r["sd_g_pp"], r["mde_bp_day"], r["deff"], r["n_eff"], r["gate2"]))
        print("  GATE3 gap=%.3f bp/day  CI95[%.3f, %.3f]  p(<=0)=%.4f"
              % (r["delta_bp_day"], r["ci_lo_bp"], r["ci_hi_bp"], r["p_gt0"]))
        print("  EW mean %.4f pp/day -> compound %+.1f%% | median %.4f pp/day -> %+.1f%%"
              % (r["ew_mean_pp_day"], r["basket_compound_pct"],
                 r["med_mean_pp_day"], r["median_compound_pct"]))
        print("  median member compound (n=%d): %+.1f%% | %.0f%% of members beat basket"
              % (r["n_member_compounds"], r["median_member_compound_pct"],
                 100.0 * r["frac_members_beating_basket"]))
        print("  right-tail winsorised basket: actual %+.1f%% | cap@p99 (%.0f bp) "
              "%+.1f%% | cap@p95 (%.0f bp) %+.1f%%"
              % (r["basket_compound_pct"], r["wins_p99_cap_bp"], r["wins_p99_pct"],
                 r["wins_p95_cap_bp"], r["wins_p95_pct"]))
        for h in r["horizons"]:
            print("   h=%3dd nwin=%4d gap=%+.3f bp/day top1%%=%.3f top5%%=%.3f "
                  "(sum sign %+d, n=%d)"
                  % (h["h"], h["nwin"], 1e2 * h["gap_pp_day"], h["top1"], h["top5"],
                     int(h["tot_sign"]), h["n_obs"]))
        print("  VERDICT: %s" % r["verdict"])

    out = os.path.join(CACHE, "c2_results.json")
    json.dump(res, open(out, "w"), indent=1, default=float)
    print("\nwrote %s" % out)

    ok = [r for r in res if r.get("gate1") == "PASS"]
    ok.sort(key=lambda r: r["delta_bp_day"])
    print("\n=== SIGNED ORDER: left-tail (median beats basket) -> right-tail ===")
    for r in ok:
        print("  %+9.3f  [%+8.3f,%+8.3f]  MDE %6.3f  %-52s %s"
              % (r["delta_bp_day"], r["ci_lo_bp"], r["ci_hi_bp"], r["mde_bp_day"],
                 r["label"][:52], r["verdict"]))
    # comparability check: every cross-section on the one window they all share
    print("\n=== COMMON WINDOW 2021-01-05..2026-08-14 (all panels overlap) ===")
    common = []
    for name, label, _s, _e, note, drop, rd in SPECS:
        if not os.path.exists(os.path.join(CACHE, name + ".npz")):
            continue
        r = analyze(name, label, 20210105, 20260814, note, drop, rd)
        if r.get("gate1") != "PASS":
            print("  %-52s GATE1 %s" % (label[:52], r.get("gate1")))
            continue
        common.append(r)
    for r in sorted(common, key=lambda x: abs(x["delta_bp_day"])):
        print("  |%7.3f| bp/day CI[%+8.3f,%+8.3f] MDE %6.3f  %-46s %s"
              % (abs(r["delta_bp_day"]), r["ci_lo_bp"], r["ci_hi_bp"],
                 r["mde_bp_day"], r["label"][:46], r["verdict"]))
    json.dump(common, open(os.path.join(CACHE, "c2_results_common.json"), "w"),
              indent=1, default=float)

    ok2 = sorted(ok, key=lambda r: abs(r["delta_bp_day"]))
    print("\n=== RANK: LEAST -> MOST tail-dominated (|gap| = how well median tracks "
          "mean) ===")
    print("  crypto perp benchmark (given, not measured here): |gap| = 57.07 bp/day")
    for i, r in enumerate(ok2, 1):
        print("  %2d. |%6.3f| bp/day  CI[%+7.3f,%+7.3f]  MDE %6.3f  %-50s %s"
              % (i, abs(r["delta_bp_day"]), r["ci_lo_bp"], r["ci_hi_bp"],
                 r["mde_bp_day"], r["label"][:50], r["verdict"]))


if __name__ == "__main__":
    main()
