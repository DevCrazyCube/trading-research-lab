#!/usr/bin/env python3
"""POSTURE C1 -- is the US equity cross-section tail-dominated the way crypto is?

Runs the gates in order and PRINTS them in order: coverage first, power (from
dispersion only) second, effect third, economics last. New file; touches nothing
in arena/.
"""
import glob, gzip, json, os, sys
import numpy as np

OUT = "/home/anont/meme/research/postures/c1_equity_skew"
SEED, NBOOT = 20260903, 5000
Z = 1.6448536 + 0.8416212          # z_.95 + z_.80  (alpha .05 one-sided, power .80)
MINN = 30
ICC = 0.3

# ---------------------------------------------------------------- load panel
def load():
    """Two-pass, float32, no high/low: this panel is ~15.7k names x ~2.0k
    sessions and the laptop has ~4GB free."""
    cache = f"{OUT}/panel_cache.npz"
    if os.path.exists(cache):
        z = np.load(cache, allow_pickle=True)
        return (z["syms"], z["dates"], z["close"], z["dv"],
                json.load(open(f"{OUT}/universe_regsho.json")), z["isetf"])
    parts = sorted(glob.glob(f"{OUT}/daily/part_*.json.gz") +
                   glob.glob(f"{OUT}/daily/fix_*.json.gz"))
    # a symbol can appear in more than one part (an index shift during the
    # refetch); keep it once and take the longest series for it.
    best, dset = {}, set()
    for fp in parts:                                    # pass 1: index only
        with gzip.open(fp, "rt") as fh:
            d = json.load(fh)
        for s, bars in d.items():
            prev = best.get(s)
            if prev is None or len(bars) > prev[1]:
                best[s] = (fp, len(bars))
            for b in bars:
                dset.add(b[0])
        del d
    syms = sorted(best)
    dates = np.array(sorted(dset)); dix = {d: i for i, d in enumerate(dates)}
    S, D = len(syms), len(dates)
    close = np.full((S, D), np.nan, dtype=np.float32)
    dv = np.full((S, D), np.nan, dtype=np.float32)
    six = {s: i for i, s in enumerate(syms)}
    for fp in parts:                                    # pass 2: fill
        with gzip.open(fp, "rt") as fh:
            d = json.load(fh)
        for s, bars in d.items():
            if best[s][0] != fp:
                continue                                # duplicate; skip
            i = six[s]
            for b in bars:
                j = dix[b[0]]
                close[i, j] = b[1]; dv[i, j] = b[2] * b[3]
        del d
    etf = json.load(open(f"{OUT}/etf_flag.json"))
    syms = np.array(syms, dtype=object)
    isetf = np.array([bool(etf.get(str(x), False)) for x in syms])
    np.savez_compressed(cache, syms=syms, dates=dates, close=close, dv=dv, isetf=isetf)
    return syms, dates, close, dv, json.load(open(f"{OUT}/universe_regsho.json")), isetf

def boot_ci(g, n=NBOOT, seed=SEED):
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(g), size=(n, len(g)))
    m = g[idx].mean(axis=1)
    return float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))

def main():
    syms, dates, close, dv, uni, isetf = load()
    S, D = close.shape
    ret = np.full((S, D), np.nan)
    ret[:, 1:] = close[:, 1:] / close[:, :-1] - 1.0
    ret[~np.isfinite(ret)] = np.nan
    ret[np.abs(ret) > 5.0] = np.nan                     # >500%/day: bad print guard

    # trailing 21-session average dollar volume, known as of t-1 (no lookahead)
    dvf = np.where(np.isfinite(dv), dv, 0.0)
    csum = np.cumsum(dvf, axis=1)
    adv = np.full((S, D), np.nan)
    adv[:, 22:] = (csum[:, 21:-1] - csum[:, :-22]) / 21.0

    live = np.isfinite(ret)
    scrA = live & (adv >= 1e6)                          # crypto analog: >= $1M/day
    def topN(extra, n=500):
        rank = np.where(np.isfinite(adv) & live & extra, adv, -1.0).astype(np.float32)
        k = min(n, rank.shape[0] - 1)
        thr = np.partition(rank, -k, axis=0)[-k]
        m = (rank >= thr) & (rank > 0)
        del rank
        return m
    scrB = topN(np.ones((1, 1), bool))
    # screen C: top 500 by adv21 among COMMON STOCKS ONLY (ETFs/ETNs removed) --
    # the true name-selection universe; a basket product would otherwise flatter
    # the median by construction.
    scrC = topN((~isetf)[:, None])

    rep = {"generated_utc": __import__("datetime").datetime.now(
        __import__("datetime").UTC).strftime("%Y-%m-%dT%H:%M:%SZ")}

    # ------------------------------------------------------------- GATE 1
    last_bar = np.where(live.any(axis=1),
                        D - 1 - np.argmax(live[:, ::-1], axis=1), -1)
    endcut = np.searchsorted(dates, "2026-06-01")
    dead = int(((last_bar >= 0) & (last_bar < endcut)).sum())
    nA = scrA.sum(axis=0); nB = scrB.sum(axis=0)
    okA = nA >= MINN
    g1 = {
        "universe_symbols_regsho_pointintime": len(uni),
        "symbols_with_price_history": int(live.any(axis=1).sum()),
        "sessions_in_grid": int(D),
        "date_range": [dates[0], dates[-1]],
        "symbols_ceasing_before_2026-06-01": dead,
        "delisted_share_of_panel": round(dead / max(1, int(live.any(axis=1).sum())), 4),
        "screenA_$1M_names_per_day_mean": round(float(nA[okA].mean()), 1),
        "screenA_days_usable": int(okA.sum()),
        "screenB_top500_days_with_ge_400": int((nB >= 400).sum()),
        "n_common_stocks_in_panel": int((~isetf).sum()),
        "n_etf_etn_in_panel": int(isetf.sum()),
        "screenB_share_days_ge_400": round(float((nB >= 400).mean()), 4),
        "PASS_g1a_survivorship>=20pct": bool(dead / max(1, int(live.any(axis=1).sum())) >= 0.20),
        "PASS_g1b_span>=1500": bool(D >= 1500),
        "PASS_g1c_breadth": bool((nB >= 400).mean() >= 0.90),
    }
    rep["GATE1_coverage"] = g1
    print("=== GATE 1 COVERAGE ==="); print(json.dumps(g1, indent=2), flush=True)

    # ------------------------------------------------------------- GATE 2
    def series(mask):
        x = np.where(mask, ret, np.nan)
        with np.errstate(invalid="ignore"):
            ew = np.nanmean(x, axis=0); md = np.nanmedian(x, axis=0)
        bad = mask.sum(axis=0) < MINN
        ew[bad] = np.nan; md[bad] = np.nan
        return ew, md
    ewA, mdA = series(scrA); ewB, mdB = series(scrB); ewC, mdC = series(scrC)
    g2 = {}
    SCREENS = {"screenA_$1M_allNMS": (ewA, mdA, scrA),
               "screenB_top500_allNMS": (ewB, mdB, scrB),
               "screenC_top500_commonstock": (ewC, mdC, scrC)}
    for tag, (ew, md, mask) in SCREENS.items():
        v = np.isfinite(ew) & np.isfinite(md)
        gap = ew[v] - md[v]
        T = int(v.sum()); nbar = float(mask.sum(axis=0)[v].mean())
        sd_nd = float(np.nanstd(np.where(mask, ret, np.nan)[:, v]))
        nobs = int(mask[:, v].sum())
        deff = 1 + (nbar - 1) * ICC
        g2[tag] = {
            "T_date_clusters": T, "avg_names_per_date": round(nbar, 1),
            "n_name_days": nobs,
            "SD_name_day_return_pp": round(sd_nd * 100, 4),
            "SD_daily_gap_pp": round(float(gap.std()) * 100, 4),
            "DEFF_icc0.3": round(deff, 1),
            "n_eff_name_days": int(nobs / deff),
            "MDE_a_name_day_pp_per_day": round(Z * sd_nd / np.sqrt(nobs / deff) * 100, 4),
            "MDE_b_date_cluster_gap_pp_per_day": round(Z * float(gap.std()) / np.sqrt(T) * 100, 4),
        }
        g2[tag]["MDE_governing_pp_per_day"] = round(max(
            g2[tag]["MDE_a_name_day_pp_per_day"], g2[tag]["MDE_b_date_cluster_gap_pp_per_day"]), 4)
    rep["GATE2_power"] = g2
    print("\n=== GATE 2 POWER (dispersion only, effect not yet read) ===")
    print(json.dumps(g2, indent=2), flush=True)

    # ------------------------------------------------------------- GATE 3
    g3 = {}
    for tag, (ew, md, mask) in SCREENS.items():
        v = np.isfinite(ew) & np.isfinite(md)
        e, m = ew[v], md[v]; gap = e - m
        lo_e, hi_e = boot_ci(e); lo_g, hi_g = boot_ci(gap)
        # A mean-median gap is NOT free evidence of tail domination: for a
        # log-normal cross-section with log-dispersion sigma_t the gap is
        # exp(sigma_t^2/2)-1 BY CONSTRUCTION. Validated on synthetic IID data
        # (sigma=2%/day -> gap 1.9bp/day = sigma^2/2). So normalise by it.
        lg = np.log1p(np.where(mask, ret, np.nan))
        with np.errstate(invalid="ignore"):
            sig = np.nanstd(lg, axis=0)
            q1 = np.nanpercentile(lg, 25, axis=0); q3 = np.nanpercentile(lg, 75, axis=0)
        sig_r = (q3 - q1) / 1.349                       # outlier-robust dispersion
        mech = np.expm1(sig[v] ** 2 / 2.0)
        mech_r = np.expm1(sig_r[v] ** 2 / 2.0)
        ratio = float(gap.mean() / mech.mean())
        ratio_r = float(gap.mean() / mech_r.mean())
        d = {
            "days": int(v.sum()),
            "EW_mean_pp_per_day": round(float(e.mean()) * 100, 4),
            "EW_ci95_pp": [round(lo_e * 100, 4), round(hi_e * 100, 4)],
            "MEDIAN_pp_per_day": round(float(m.mean()) * 100, 4),
            "GAP_pp_per_day": round(float(gap.mean()) * 100, 4),
            "GAP_ci95_pp": [round(lo_g * 100, 4), round(hi_g * 100, 4)],
            "xsec_log_dispersion_pct_per_day": round(float(sig[v].mean()) * 100, 3),
            "MECHANICAL_gap_if_lognormal_pp_per_day": round(float(mech.mean()) * 100, 4),
            "EXCESS_SKEW_RATIO_gap_over_mechanical": round(ratio, 3),
            "xsec_log_dispersion_robust_pct_per_day": round(float(sig_r[v].mean()) * 100, 3),
            "MECHANICAL_gap_robust_pp_per_day": round(float(mech_r.mean()) * 100, 4),
            "EXCESS_SKEW_RATIO_robust": round(ratio_r, 3),
            "compound_EW_basket_pct": round((float(np.prod(1 + e)) - 1) * 100, 2),
            "compound_daily_median_pct": round((float(np.prod(1 + m)) - 1) * 100, 4),
        }
        # multi-horizon. step==h -> independent windows; step<h -> overlapping,
        # reported as descriptive only (windows are not independent).
        idx = np.where(v)[0]
        for h, step, lab in ((21, 21, "indep"), (252, 252, "indep"), (252, 21, "overlap")):
            bm, bmd, nw = [], [], 0
            for k in range(0, len(idx) - h, step):
                w = idx[k:k + h]
                elig = mask[:, w[0]]
                if elig.sum() < MINN:
                    continue
                sub = np.where(np.isfinite(ret[:, w]), ret[:, w], 0.0)[elig]
                comp = np.prod(1 + sub, axis=1) - 1
                bm.append(float(np.prod(1 + ew[w]) - 1)); bmd.append(float(np.median(comp)))
                nw += 1
            bm, bmd = np.array(bm), np.array(bmd)
            d[f"h{h}_{lab}"] = {
                "n_windows": nw, "independent": step == h,
                "EW_basket_mean_window_ret_pct": round(float(bm.mean()) * 100, 3),
                "median_NAME_window_ret_mean_pct": round(float(bmd.mean()) * 100, 3),
                "median_NAME_window_ret_median_pct": round(float(np.median(bmd)) * 100, 3),
                "share_windows_median_name_negative": round(float((bmd < 0).mean()), 3),
                "gap_pp_per_day_implied": round(float((bm - bmd).mean()) / h * 100, 4),
            }
        # per-name buy&hold while eligible
        nc = []
        for i in range(S):
            mk = mask[i]
            if mk.sum() < 60:
                continue
            nc.append(float(np.prod(1 + ret[i][mk])) - 1)
        nc = np.array(nc)
        d["per_name_buyhold_while_eligible"] = {
            "n_names": int(nc.size),
            "median_pct": round(float(np.median(nc)) * 100, 2),
            "mean_pct": round(float(nc.mean()) * 100, 2),
            "share_negative": round(float((nc < 0).mean()), 4),
        }
        # SENSITIVITY: free daily data cannot see the delisting return. Shumway
        # (1997) puts the average performance-related delisting return near -30%.
        # Worst case: charge EVERY name that stops printing before the panel end
        # a -30% terminal return, whether it was a bankruptcy or a takeover.
        nc2, ndl = [], 0
        endc = D - 6
        for i in range(S):
            mk = mask[i]
            if mk.sum() < 60:
                continue
            c = float(np.prod(1 + ret[i][mk]))
            lb = int(np.where(live[i])[0][-1]) if live[i].any() else -1
            if 0 <= lb < endc:
                c *= 0.70; ndl += 1
            nc2.append(c - 1)
        nc2 = np.array(nc2)
        d["per_name_buyhold_with_-30pct_delisting_shock"] = {
            "n_names": int(nc2.size), "n_shocked": ndl,
            "median_pct": round(float(np.median(nc2)) * 100, 2),
            "mean_pct": round(float(nc2.mean()) * 100, 2),
            "share_negative": round(float((nc2 < 0).mean()), 4),
        }
        # top-k share of total EW arithmetic return
        n_t = mask.sum(axis=0).astype(float); n_t[n_t == 0] = np.nan
        contrib = np.nansum(np.where(mask, ret, 0.0) / n_t, axis=1)
        tot = float(contrib.sum()); order = np.sort(contrib)[::-1]
        nn = int((mask.any(axis=1)).sum())
        d["top_share_of_total_EW_return"] = {"total_arith_sum": round(tot, 4),
                                             "n_names_ever_eligible": nn}
        for pct in (0.01, 0.05):
            k = max(1, int(round(pct * nn)))
            d["top_share_of_total_EW_return"][f"top_{int(pct*100)}pct"] = {
                "k_names": k, "share": round(float(order[:k].sum() / tot), 4)}
        g3[tag] = d
    rep["GATE3_effect"] = g3
    print("\n=== GATE 3 EFFECT (cluster bootstrap by date, 5000 draws, seed 20260903) ===")
    print(json.dumps(g3, indent=2), flush=True)

    # ------------------------------------------------------------- ECONOMICS
    # Corwin-Schultz was VALIDATED AND REJECTED before use: on synthetic data
    # with a known 2bp spread it returns ~36bp. The cost used is the NBBO spread
    # measured by c1_measure_cost.py off the same SIP feed.
    econ = {}
    cost_bp = None
    if os.path.exists(f"{OUT}/cost_measured.json"):
        cost_bp = json.load(open(f"{OUT}/cost_measured.json"))["round_trip_bp_median"]
    for tag, (_e, _m, mask) in SCREENS.items():
        econ[tag] = {}
        gapv = g3[tag]["GAP_pp_per_day"] * 100          # pp -> bp
        econ[tag]["gap_bp_per_day"] = round(gapv, 2)
        econ[tag]["EW_bp_per_day"] = round(g3[tag]["EW_mean_pp_per_day"] * 100, 2)
        if cost_bp:
            econ[tag]["round_trip_bp_measured_NBBO"] = cost_bp
            econ[tag]["gap_over_roundtrip_per_day"] = round(gapv / cost_bp, 3)
            econ[tag]["EW_over_roundtrip_per_day"] = round(
                econ[tag]["EW_bp_per_day"] / cost_bp, 3)
    rep["ECONOMICS"] = econ
    print("\n=== ECONOMICS (round trip = NBBO spread measured on this panel) ===")
    print(json.dumps(econ, indent=2), flush=True)

    json.dump(rep, open(f"{OUT}/c1_result.json", "w"), indent=2)
    print(f"\nwrote {OUT}/c1_result.json")

if __name__ == "__main__":
    main()
