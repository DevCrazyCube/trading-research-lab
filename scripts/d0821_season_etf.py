#!/usr/bin/env python3
"""D0821 seasonality-with-mechanism: the ETF-level families (P, T, D, R).

SPLIT PINNED BEFORE SCORING:
    design  = first available session .. 2013-12-31
    held-out= 2014-01-01 .. 2026-08-21   (untouched until every design number is fixed)
"""
from __future__ import annotations
import json, os, sys
import numpy as np

sys.path.insert(0, "/home/anont/meme/scripts")
from d0821_season_lib import (EtfBook, calendar_features, trailing_vol, run_weights,
                              stats, block_bootstrap_p, etf_cost_bp, STRESS_MULT)

DESIGN = ("1900-01-01", "2014-01-01")
HELD = ("2014-01-01", "2099-01-01")

SYMS = ["SPY", "RSP", "MDY", "OEF", "IWM", "QQQ", "DIA", "IEF", "TLT", "SHY",
        "AGG", "LQD", "HYG", "TIP", "EFA", "EEM", "GLD", "XLP", "XLU", "XLK", "VNQ"]

VOL_FLOOR = 0.001
CAP = 4.0
K = 0.01  # per-leg daily vol target


def main():
    bk = EtfBook(SYMS, start="2003-05-01")   # RSP inception bounds the joint panel
    n = len(bk.dates)
    cf = calendar_features(bk.dates)
    tom, qom, mid, month = cf["tom"], cf["qom"], cf["mid"], cf["month"]
    vol = trailing_vol(bk.ret, 60, VOL_FLOOR)
    RET = bk.ret           # total return
    PRET = bk.pret         # price-only return
    I = bk.i

    results = []

    def spread(name, desc, fam, a, b, sig, hold_mask, use_price=False):
        """long a / short b, vol-scaled, scaled by scalar signal sig on hold_mask."""
        ia, ib = I[a], I[b]
        wa = np.clip(K / vol[ia], 0, CAP)
        wb = np.clip(K / vol[ib], 0, CAP)
        s = np.where(hold_mask, sig, 0.0)
        s = np.nan_to_num(s, nan=0.0)
        W = np.vstack([s * wa, -s * wb])
        R = np.vstack([(PRET if use_price else RET)[ia], (PRET if use_price else RET)[ib]])
        res = run_weights(name, desc, fam, bk.dates, W, R,
                          [etf_cost_bp(a), etf_cost_bp(b)])
        results.append(res)
        return res

    # ---- month-to-date / quarter-to-date relative performance of two legs
    def td_div(a, b, boundary):
        """cumulative (r_a - r_b) since the start of the current month/quarter,
        through the close of t. boundary: 'm' or 'q'."""
        d = np.nan_to_num(RET[I[a]] - RET[I[b]], nan=0.0)
        key = cf["ym"] if boundary == "m" else np.array(
            [x[:4] + "Q" + str((int(x[5:7]) - 1) // 3) for x in bk.dates])
        out = np.zeros(n)
        acc = 0.0
        for t in range(n):
            if t == 0 or key[t] != key[t - 1]:
                acc = 0.0
            acc += d[t]
            out[t] = acc
        return out

    def zc(x, win=750):
        """causal z of a series against its own trailing scale (no look-ahead)."""
        out = np.zeros_like(x)
        for t in range(n):
            lo = max(0, t - win)
            s = np.std(x[lo:t + 1]) if t > 60 else np.nan
            out[t] = x[t] / s if (s and np.isfinite(s) and s > 0) else 0.0
        return np.clip(np.nan_to_num(out), -2.5, 2.5) / 2.5

    # =============================== FAMILY P ===============================
    # Balanced-fund / target-date / pension rebalancing.  A plan document that says
    # 60/40 OBLIGES the manager to sell whatever outperformed inside the period,
    # in the last sessions of it.  Signal = MINUS the intra-period divergence.
    div_m = td_div("SPY", "IEF", "m")
    div_q = td_div("SPY", "IEF", "q")
    sgn_m = -np.sign(div_m)
    mag_m = -zc(div_m)

    spread("P01_PENSION_MEQ_SIGN",
           "sell-the-outperformer 60/40 rebalance: -sign(MTD SPY-IEF), SPY vs IEF, "
           "held over the last 4 sessions of the month", "P",
           "SPY", "IEF", sgn_m, (tom >= -4) & (tom <= -1))
    spread("P02_PENSION_MEQ_MAG",
           "same as P01 but sized by the magnitude of the MTD divergence "
           "(a bigger drift obliges a bigger rebalance trade)", "P",
           "SPY", "IEF", mag_m, (tom >= -4) & (tom <= -1))
    spread("P03_PENSION_QTR",
           "quarter-end version: -sign(QTD SPY-IEF) over the last 4 sessions of the "
           "quarter, when quarterly-mandate rebalancers join the monthly ones", "P",
           "SPY", "IEF", -np.sign(div_q), (qom >= -4) & (qom <= -1))
    spread("P04_PENSION_UNWIND",
           "the price-impact give-back: +sign(prior-month SPY-IEF divergence) held "
           "over the first 3 sessions of the new month", "P",
           "SPY", "IEF", np.sign(_carry_last(div_m, cf, n)), (tom >= 0) & (tom <= 2))
    spread("P05_PENSION_LASTDAY",
           "the single session the rebalance actually prints: -sign(MTD SPY-IEF) held "
           "over the final session of the month only", "P",
           "SPY", "IEF", sgn_m, (tom == -1))
    div_g = td_div("SPY", "EFA", "m")
    spread("P06_PENSION_GLOBAL",
           "regional-weight rebalance inside global balanced mandates: "
           "-sign(MTD SPY-EFA), last 4 sessions of the month", "P",
           "SPY", "EFA", -np.sign(div_g), (tom >= -4) & (tom <= -1))
    div_c = td_div("HYG", "IEF", "m")
    spread("P07_PENSION_CREDIT",
           "credit-sleeve rebalance: -sign(MTD HYG-IEF), last 4 sessions of the month",
           "P", "HYG", "IEF", -np.sign(div_c), (tom >= -4) & (tom <= -1))

    # =============================== FAMILY T ===============================
    # Payroll-deferral contribution inflow.  The marginal 401(k) dollar is invested
    # CAP-WEIGHTED, so the mechanical prediction is a cap-weight TILT in the window
    # the money lands, not a market-direction effect.
    one = np.ones(n)
    tomw = (tom >= -2) & (tom <= 2)
    spread("T01_TOM_CAPWEIGHT",
           "cap-weight tilt of turn-of-month contribution flow: long SPY / short RSP "
           "(equal-weight sibling) over the -2..+2 session TOM window", "T",
           "SPY", "RSP", one, tomw)
    spread("T02_TOM_MEGACAP",
           "sharper cap tilt: long OEF (S&P100) / short SPY over the TOM window", "T",
           "OEF", "SPY", one, tomw)
    spread("T03_TOM_SIZE",
           "the marginal contribution dollar is S&P-heavy: long SPY / short IWM over "
           "the TOM window", "T", "SPY", "IWM", one, tomw)
    spread("T04_MIDMONTH_CAPWEIGHT",
           "the SECOND payroll date: same SPY-vs-RSP cap tilt around the first session "
           "on/after the 15th (-2..+2). If the mechanism is payroll, this must fire too",
           "T", "SPY", "RSP", one, (mid >= -2) & (mid <= 2))
    spread("T05_TOM_EQBOND",
           "contribution money is ~70/30 equity-tilted: long SPY / short IEF over the "
           "TOM window", "T", "SPY", "IEF", one, tomw)
    spread("T06_TOM_SETTLE12",
           "settlement timing: the cap tilt only on the two sessions the T+1/T+2 money "
           "actually buys (first and second session of the new month)", "T",
           "SPY", "RSP", one, (tom >= 0) & (tom <= 1))

    # =============================== FAMILY D ===============================
    # ETF distribution ex-dates recovered exactly from adjclose-vs-close.
    ex = bk.distyield > 5e-4
    div_syms = [s for s in SYMS if ex[I[s]].sum() >= 12 and s != "SPY"]

    def evt_basket(name, desc, off_lo, off_hi, use_price=True):
        """Long each ETF over [ex+off_lo, ex+off_hi] sessions, short SPY vol-matched;
        equal-weight across concurrently live events."""
        m = len(SYMS)
        W = np.zeros((m + 1, n))
        for s in div_syms:
            k = I[s]
            for t0 in np.where(ex[k])[0]:
                a, b = t0 + off_lo, t0 + off_hi
                for t in range(max(0, a), min(n, b + 1)):
                    W[k, t] += np.clip(K / vol[k, t], 0, CAP)
        # normalise by number of live legs, hedge with SPY at matched vol units
        live = np.sum(W[:m] != 0, axis=0)
        W[:m] /= np.maximum(live, 1)
        W[m] = -np.sum(W[:m] * vol[:m], axis=0) / np.maximum(vol[I["SPY"]], VOL_FLOOR)
        Rm = (PRET if use_price else RET)
        R = np.vstack([Rm, Rm[I["SPY"]][None, :]])
        cb = [etf_cost_bp(s) for s in SYMS] + [etf_cost_bp("SPY")]
        results.append(run_weights(name, desc, "D", bk.dates, W, R, cb))

    evt_basket("D01_ETF_EXDIST_RECOVERY",
               "DRIP reinvestment lands a few sessions after the ETF's ex-distribution "
               "date: long the ex-ing ETF vs SPY from the ex close to ex+5, price return",
               0, 4)
    evt_basket("D02_ETF_EXDIST_PRERUN",
               "dividend-capture demand into a known ex-date: long the ETF vs SPY over "
               "ex-5..ex-2 (position closed before the drop), price return", -5, -2)
    evt_basket("D03_ETF_EXDIST_CROSS",
               "hold across the ex-date and collect: total return over ex-1 -> ex, "
               "long the ETF vs SPY", -1, -1, use_price=False)

    bondb = ["AGG", "LQD", "HYG", "TLT", "IEF", "TIP"]
    som = np.zeros(n, bool)
    cnt = 0
    for t in range(n):
        if t == 0 or cf["ym"][t] != cf["ym"][t - 1]:
            cnt = 0
        cnt += 1
        som[t] = 4 <= cnt <= 8
    Wb = np.zeros((len(bondb) + 1, n))
    for j, s in enumerate(bondb):
        Wb[j] = np.where(som, np.clip(K / vol[I[s]], 0, CAP) / len(bondb), 0.0)
    Wb[-1] = -np.sum(Wb[:-1] * np.array([vol[I[s]] for s in bondb]), axis=0) / \
        np.maximum(vol[I["SHY"]], VOL_FLOOR)
    Rb = np.vstack([RET[[I[s] for s in bondb]], RET[I["SHY"]][None, :]])
    results.append(run_weights(
        "D04_BONDETF_COUPON_DRIP",
        "monthly-pay bond ETFs go ex on the first business day and PAY around the 7th; "
        "reinvested coupon buys the fund back. Long the monthly-pay basket vs SHY on "
        "sessions 4-8 of the month", "D", bk.dates, Wb, Rb,
        [etf_cost_bp(s) for s in bondb] + [etf_cost_bp("SHY")]))

    # =============================== FAMILY R ===============================
    # Bond index rulebooks (Bloomberg US Agg / ICE) rebalance on the LAST business day
    # of the month: new issuance enters, the index's duration mechanically EXTENDS, and
    # every index-tracking fund must buy duration into that close.
    ext = (tom >= -3) & (tom <= -1)
    spread("R01_TSY_INDEX_EXTENSION",
           "month-end index duration extension: long TLT / short IEF over the last 3 "
           "sessions of the month", "R", "TLT", "IEF", one, ext)
    spread("R02_TSY_EXT_UNWIND",
           "the extension's give-back: short TLT / long IEF over the first 2 sessions "
           "of the new month", "R", "TLT", "IEF", -one, (tom >= 0) & (tom <= 1))
    refund = np.where(np.isin(month, [2, 5, 8, 11]), 1.0, 0.4)
    spread("R03_TSY_EXT_REFUNDING",
           "the extension is larger in quarterly-refunding settlement months: R01 sized "
           "1.0 in Feb/May/Aug/Nov and 0.4 elsewhere", "R", "TLT", "IEF", refund, ext)
    spread("R04_CORP_INDEX_EXTENSION",
           "same rulebook, credit sleeve: long LQD / short SHY over the last 3 sessions "
           "of the month", "R", "LQD", "SHY", one, ext)
    spread("R05_TSY_EXT_TLT_SHY",
           "full-curve version of R01: long TLT / short SHY over the last 3 sessions of "
           "the month", "R", "TLT", "SHY", one, ext)

    out = {}
    for r in results:
        d = stats(r.net, r.dates, *DESIGN)
        dg = stats(r.gross, r.dates, *DESIGN)
        ds = stats(r.net_stress, r.dates, *DESIGN)
        out[r.name] = dict(desc=r.desc, family=r.family,
                           design_net=d, design_gross=dg, design_stress=ds,
                           mean_gross_expo=float(np.mean(r.expo[r.expo > 0])) if np.any(r.expo > 0) else 0.0,
                           active_frac=float(np.mean(r.expo > 0)))
        np.save(f"/home/anont/meme/research/data/d0821_cache/{r.name}.npy",
                np.vstack([r.gross, r.net, r.net_stress]))
    json.dump({"dates": bk.dates, "results": out, "design": DESIGN, "held": HELD},
              open("/home/anont/meme/research/data/d0821_cache/etf_design.json", "w"))
    for k, v in sorted(out.items(), key=lambda x: -abs(x[1]["design_net"]["t"] if np.isfinite(x[1]["design_net"]["t"]) else 0)):
        s = v["design_net"]
        print(f"{k:28s} fam={v['family']} n={s['n']:5d} act={v['active_frac']:.2f} "
              f"Sh={s['sharpe']:6.2f} t={s['t']:6.2f} meanbp={s['mean_bp']:6.2f} "
              f"gross_t={v['design_gross']['t']:6.2f} stress_t={v['design_stress']['t']:6.2f}")


def _carry_last(x, cf, n):
    """value of x at the LAST session of the previous month, carried forward."""
    out = np.zeros(n)
    last = 0.0
    for t in range(n):
        if t > 0 and cf["ym"][t] != cf["ym"][t - 1]:
            last = x[t - 1]
        out[t] = last
    return out


if __name__ == "__main__":
    os.makedirs("/home/anont/meme/research/data/d0821_cache", exist_ok=True)
    main()
