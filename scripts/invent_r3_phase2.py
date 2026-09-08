#!/usr/bin/env python3
"""INVENT R3 phase 2 -- forms of conditioning the binary median gate cannot express.

  TILT     : continuous size proportional to the DESIGN-standardised conditioner
  INTERACT : two-way regime gates (VIX x trend, term x rate, ...)
  SIDE     : condition the LONG and SHORT halves of T3 separately on trend
             (mechanism: an overnight reversal's long half also collects market drift)
  SENTGATE : gate equity legs on the CEF-universe MEDIAN DISCOUNT (Lee-Shleifer-Thaler
             retail-sentiment proxy) -- a conditioner from one alive edge applied to another
  SWITCH   : ensemble weights that switch on the VIX regime
"""
from __future__ import annotations
import json, math, pathlib, datetime, gzip, os, sys
import numpy as np

ROOT = pathlib.Path("/home/anont/meme"); sys.path.insert(0, str(ROOT))
from scripts.invent_r3_conditioning import (   # noqa: E402
    load, load_legs, build_conditioners, daytype, align, gate_test, ann_sharpe,
    report, trail_mean, _trail_sd, to_weekly, DESIGN_END, HOLD_START, D, OUT)

os.environ.setdefault("ALPACA_API_KEY_ID", "x")
os.environ.setdefault("ALPACA_API_SECRET_KEY", "y")


def zscore_design(v, dates, design_end):
    d = np.array(dates)
    m = (d <= design_end) & np.isfinite(v)
    if m.sum() < 100:
        return None
    mu, sd = v[m].mean(), v[m].std(ddof=1)
    if sd == 0:
        return None
    return np.clip((v - mu) / sd, -2.5, 2.5)


def tilt_test(r, dates, cval, design_end, hold_start, ppy):
    """size = 1 + s*z, s in {+1,-1} chosen on DESIGN, clipped to [0,2]. Same gross budget
    on average, so the comparison against the raw leg is like-for-like."""
    z = zscore_design(cval, dates, design_end)
    if z is None:
        return None
    d = np.array(dates)
    fin = np.isfinite(z)
    dm, hm = (d <= design_end) & fin, (d >= hold_start) & fin
    if dm.sum() < 100 or hm.sum() < 50:
        return None
    best = None
    for s in (+1.0, -1.0):
        w = np.clip(1.0 + s * 0.5 * z, 0.0, 2.0)
        w = w / w[dm].mean()                      # unit average gross on design
        sr = ann_sharpe((w * r)[dm], ppy)
        if best is None or sr > best[0]:
            best = (sr, s, w)
    sr_d, s, w = best
    raw_d, raw_h = ann_sharpe(r[dm], ppy), ann_sharpe(r[hm], ppy)
    # the OVERLAY series: what the tilt adds on top of the flat book
    ov_d, ov_h = ((w - 1.0) * r)[dm], ((w - 1.0) * r)[hm]
    return {"sign": s,
            "design": {"sharpe_book": sr_d, "sharpe_raw": raw_d, "d_sharpe": sr_d - raw_d,
                       "overlay_t": float(ov_d.mean() / ov_d.std(ddof=1) * math.sqrt(len(ov_d)))
                       if ov_d.std() > 0 else 0.0},
            "holdout": {"sharpe_book": ann_sharpe((w * r)[hm], ppy), "sharpe_raw": raw_h,
                        "d_sharpe": ann_sharpe((w * r)[hm], ppy) - raw_h,
                        "overlay_t": float(ov_h.mean() / ov_h.std(ddof=1) * math.sqrt(len(ov_h)))
                        if ov_h.std() > 0 else 0.0}}


def cef_sentiment():
    """median discount of the live CEF universe, per CEFConnect grid date. Cached, no network."""
    import scripts.t12_evaluate as t12e
    grid, panel, bars, tickers, dropped = t12e.build_panel()
    dates, med, disp = [], [], []
    for g in grid:
        vals = [row["discount"] for row in panel[g].values() if row["discount"] is not None]
        if len(vals) < 50:
            continue
        dates.append(g)
        med.append(float(np.median(vals)))
        disp.append(float(np.percentile(vals, 75) - np.percentile(vals, 25)))
    return dates, np.array(med), np.array(disp)


def main():
    legs = load_legs()
    trials = 0
    out = {"tilts": [], "interactions": [], "side": [], "sentgate": [], "switch": []}

    # ---------------- TILT -------------------------------------------------
    for legname in ("T3", "T7D1"):
        leg = legs[legname]
        dates, r, ppy = leg["dates"], leg["net"], leg["ppy"]
        C = build_conditioners(dates)
        for cname in ("VIX_LEVEL", "VIX_TERM", "RV20", "VRP", "SPY_TREND200",
                      "VIX_DCHG", "VVIX_RATIO", "RATE_CHG", "SPY_MOM20", "RV5_OVER_RV20"):
            res = tilt_test(r, dates, C[cname], DESIGN_END, HOLD_START, ppy)
            trials += 2
            if res:
                out["tilts"].append({"leg": legname, "cond": cname, **res})

    # ---------------- INTERACTION -----------------------------------------
    pairs = [("VIX_LEVEL", "SPY_TREND200"), ("VIX_TERM", "SPY_TREND200"),
             ("VIX_LEVEL", "RATE_CHG"), ("RV20", "VOLUME_REL"),
             ("VIX_TERM", "VIX_DCHG"), ("VRP", "SPY_MOM20")]
    for legname in ("T3", "T7D1"):
        leg = legs[legname]
        dates, r, ppy = leg["dates"], leg["net"], leg["ppy"]
        C = build_conditioners(dates)
        d = np.array(dates)
        dm = d <= DESIGN_END
        for a, b in pairs:
            va, vb = C[a], C[b]
            fin = np.isfinite(va) & np.isfinite(vb)
            if (dm & fin).sum() < 200:
                continue
            ta, tb = np.median(va[dm & fin]), np.median(vb[dm & fin])
            quad = ((va > ta).astype(int) * 2 + (vb > tb).astype(int)).astype(float)
            quad[~fin] = np.nan
            # pick the single best DESIGN quadrant, stand down in the other three
            means = {}
            for q in range(4):
                m = dm & fin & (quad == q)
                if m.sum() > 40:
                    means[q] = r[m].mean()
            if len(means) < 4:
                continue
            qbest = max(means, key=means.get)
            on = fin & (quad == qbest)
            trials += 4
            hm = d >= HOLD_START
            rec = {"leg": legname, "pair": [a, b], "quadrant": int(qbest)}
            for lbl, msk in (("design", dm), ("holdout", hm)):
                aa, bb = r[msk & on], r[msk & fin & ~on]
                if len(aa) < 10 or len(bb) < 10:
                    rec[lbl] = None
                    continue
                se = math.sqrt(aa.var(ddof=1) / len(aa) + bb.var(ddof=1) / len(bb))
                book = np.where(on[msk], r[msk], 0.0)
                rec[lbl] = {"t_diff": float((aa.mean() - bb.mean()) / se) if se else 0.0,
                            "sharpe_book": ann_sharpe(book, ppy),
                            "sharpe_raw": ann_sharpe(r[msk], ppy),
                            "d_sharpe": ann_sharpe(book, ppy) - ann_sharpe(r[msk], ppy),
                            "n_on": int(len(aa))}
            if rec.get("design") and rec.get("holdout"):
                out["interactions"].append(rec)

    # ---------------- SIDE (T3 long half vs short half, conditioned) -------
    t3 = legs["T3"]
    dates, ppy = t3["dates"], 252
    d = np.array(dates)
    dm, hm = d <= DESIGN_END, d >= HOLD_START
    L, S = t3["long"], t3["short"]
    cost = (1.43 + 0.31) / 1e4
    C = build_conditioners(dates)
    for cname in ("SPY_TREND200", "SPY_MOM20", "VIX_LEVEL", "VIX_TERM"):
        v = C[cname]
        fin = np.isfinite(v)
        thr = np.median(v[dm & fin])
        hi = (v > thr) & fin
        for label, wl_hi, ws_hi, wl_lo, ws_lo in (
                ("SIDE_LONGONLY_HI", 1.0, 0.0, 0.5, 0.5),
                ("SIDE_SHORTONLY_HI", 0.0, 1.0, 0.5, 0.5),
                ("SIDE_TILT", 0.75, 0.25, 0.25, 0.75)):
            wl = np.where(hi, wl_hi, wl_lo)
            ws = np.where(hi, ws_hi, ws_lo)
            book = wl * L - ws * S - cost
            trials += 1
            base = 0.5 * L - 0.5 * S - cost
            rec = {"cond": cname, "variant": label}
            for lbl, msk in (("design", dm & fin), ("holdout", hm & fin)):
                rec[lbl] = {"sharpe_book": ann_sharpe(book[msk], ppy),
                            "sharpe_raw": ann_sharpe(base[msk], ppy),
                            "d_sharpe": ann_sharpe(book[msk], ppy) - ann_sharpe(base[msk], ppy),
                            "mean_bp": float(book[msk].mean() * 1e4)}
            out["side"].append(rec)

    # ---------------- SENTGATE (CEF discount sentiment -> equity legs) -----
    cd, cmed, cdisp = cef_sentiment()
    sent_ma = trail_mean(cmed, 13)
    for legname in ("T3", "T7D1", "CEF"):
        leg = legs[legname]
        ld, r, p = leg["dates"], leg["net"], leg["ppy"]
        for cname, arr in (("CEF_MED_DISCOUNT", cmed), ("CEF_DISC_VS_13W", cmed - sent_ma),
                           ("CEF_DISPERSION", cdisp)):
            v = align(ld, cd, arr, lag=1)
            # CEF data starts 2021-08 -> its own thinner design window
            res = gate_test(r, ld, v, DESIGN_END, HOLD_START, p)
            trials += 2
            if res and res["design"] and res["holdout"]:
                out["sentgate"].append({"leg": legname, "cond": cname, **res})

    # ---------------- SWITCH (regime-dependent ensemble weights) -----------
    wk = {}
    for name, leg in legs.items():
        if leg["ppy"] == 52:
            w = {}
            for dd, x in zip(leg["dates"], leg["net"]):
                dt = datetime.date.fromisoformat(dd)
                w[(dt - datetime.timedelta(days=dt.weekday())).isoformat()] = float(x)
            wk[name] = w
        else:
            wk[name] = to_weekly(leg["dates"], leg["net"])
    cef_start = min(wk["CEF"])
    keys = sorted(k for k in set().union(*[set(v) for v in wk.values()]) if k >= cef_start)
    kd = np.array(keys)
    dmw, hmw = kd <= DESIGN_END, kd >= HOLD_START
    V = {n: np.array([wk[n].get(k, 0.0) for k in keys]) for n in wk}
    sd = {n: (V[n][dmw].std(ddof=1) or 1.0) for n in V}
    Z = {n: V[n] / sd[n] for n in V}
    Cw = build_conditioners(keys)
    eq = (Z["T3"] + Z["T7D1"] + Z["CEF"]) / 3.0
    # report at a common 1%/wk design vol so bp are comparable
    scale = 0.01 / (eq[dmw].std(ddof=1) or 1.0)
    for cname in ("VIX_LEVEL", "VIX_TERM", "SPY_TREND200", "RV20"):
        v = Cw[cname]
        fin = np.isfinite(v)
        if (dmw & fin).sum() < 30:
            continue
        thr = np.median(v[dmw & fin])
        hi = (v > thr) & fin
        # design-fit per-leg weights inside each regime (Sharpe-proportional, clipped >=0)
        wts = {}
        for reg, msk in (("hi", dmw & hi), ("lo", dmw & fin & ~hi)):
            s = {n: max(0.0, ann_sharpe(Z[n][msk], 52)) for n in ("T3", "T7D1", "CEF")}
            tot = sum(s.values()) or 1.0
            wts[reg] = {n: s[n] / tot for n in s}
        book = np.zeros(len(keys))
        for n in ("T3", "T7D1", "CEF"):
            book += np.where(hi, wts["hi"][n], wts["lo"][n]) * Z[n]
        trials += 2
        out["switch"].append({
            "cond": cname, "weights": wts,
            "design": {"sharpe": ann_sharpe(book[dmw & fin], 52),
                       "sharpe_eq": ann_sharpe(eq[dmw & fin], 52)},
            "holdout": {"sharpe": ann_sharpe(book[hmw & fin], 52),
                        "sharpe_eq": ann_sharpe(eq[hmw & fin], 52),
                        "mean_bp_at_1pct_wk": float(book[hmw & fin].mean() * scale * 1e4)}})

    out["n_trials_phase2"] = trials
    (OUT / "INVENT_R3_condition_combine_phase2.json").write_text(json.dumps(out, indent=1))

    print("trials phase2:", trials)
    print("\n=== TILT (overlay t = does the tilt add on top of the flat book) ===")
    for x in sorted(out["tilts"], key=lambda z: -abs(z["design"]["overlay_t"]))[:10]:
        print(f"{x['leg']:5s} {x['cond']:15s} s={x['sign']:+.0f} design ov_t={x['design']['overlay_t']:+.2f} "
              f"dSR={x['design']['d_sharpe']:+.2f} | HOLD ov_t={x['holdout']['overlay_t']:+.2f} "
              f"dSR={x['holdout']['d_sharpe']:+.2f} (book {x['holdout']['sharpe_book']:+.2f} raw {x['holdout']['sharpe_raw']:+.2f})")
    print("\n=== INTERACTION (best design quadrant) ===")
    for x in sorted(out["interactions"], key=lambda z: -z["design"]["t_diff"])[:8]:
        print(f"{x['leg']:5s} {x['pair'][0]:14s}x{x['pair'][1]:14s} q{x['quadrant']} "
              f"design t={x['design']['t_diff']:+.2f} dSR={x['design']['d_sharpe']:+.2f} | "
              f"HOLD t={x['holdout']['t_diff']:+.2f} dSR={x['holdout']['d_sharpe']:+.2f}")
    print("\n=== SIDE (T3 long/short halves conditioned) ===")
    for x in out["side"]:
        print(f"{x['cond']:14s} {x['variant']:20s} design SR {x['design']['sharpe_book']:+.2f} "
              f"(raw {x['design']['sharpe_raw']:+.2f}) | HOLD SR {x['holdout']['sharpe_book']:+.2f} "
              f"(raw {x['holdout']['sharpe_raw']:+.2f}, d {x['holdout']['d_sharpe']:+.2f})")
    print("\n=== SENTGATE (CEF discount sentiment) ===")
    for x in out["sentgate"]:
        print(f"{x['leg']:5s} {x['cond']:20s} design t={x['design']['t_diff']:+.2f} "
              f"dSR={x['design']['d_sharpe']:+.2f} | HOLD t={x['holdout']['t_diff']:+.2f} "
              f"dSR={x['holdout']['d_sharpe']:+.2f}")
    print("\n=== SWITCH (regime-dependent ensemble weights) ===")
    for x in out["switch"]:
        print(f"{x['cond']:14s} design SR {x['design']['sharpe']:+.2f} (eq {x['design']['sharpe_eq']:+.2f}) "
              f"| HOLD SR {x['holdout']['sharpe']:+.2f} (eq {x['holdout']['sharpe_eq']:+.2f})")


if __name__ == "__main__":
    main()
