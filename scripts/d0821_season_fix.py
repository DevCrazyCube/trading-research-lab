#!/usr/bin/env python3
"""D0821: (a) rebuild the X family against the correct control group, (b) add the
ungated controls that ask what the CALENDAR WINDOW actually buys, (c) cluster-robust
inference for the families whose real sample size is years/quarters, not sessions."""
from __future__ import annotations
import json, os, sys
import numpy as np

sys.path.insert(0, "/home/anont/meme/scripts")
from d0821_season_lib import calendar_features, run_weights, stats, COST_BP
from d0821_season_stock import load, xs_weights, _carry, DESIGN, HELD, CACHE


def cluster_t(series, dates, lo, hi, keyfun):
    """t-stat treating each calendar cluster (year / quarter) as ONE observation.
    This is the honest sample size for an annual seasonal."""
    m = np.array([(d >= lo) and (d < hi) for d in dates])
    x, dd = series[m], [d for d in dates if lo <= d < hi]
    agg = {}
    for r, d in zip(x, dd):
        if r != 0.0:
            agg.setdefault(keyfun(d), []).append(r)
    tot = np.array([sum(v) for v in agg.values()])
    if tot.size < 3:
        return float("nan"), int(tot.size), float("nan")
    t = tot.mean() / (tot.std(ddof=1) / np.sqrt(tot.size))
    return float(t), int(tot.size), float((tot > 0).mean())


def main():
    syms, dates, ret, onr, idr, close, elig, exmat, paymat = load()
    m, n = ret.shape
    cf = calendar_features(dates)
    tom, qom, month = cf["tom"], cf["qom"], cf["month"]
    dom = np.array([int(d[8:10]) for d in dates])
    cb = [COST_BP["stock"]] * m
    results = []

    def add(name, desc, fam, W, R=None):
        results.append(run_weights(name, desc, fam, dates, W, ret if R is None else R, cb))
        print("built", name, flush=True)

    # ---- who is a dividend payer at time t?  (>=2 ex-dates in the trailing 400 sessions)
    csx = np.cumsum(exmat.astype(np.int32), axis=1)
    payer = np.zeros((m, n), bool)
    payer[:, 400:] = (csx[:, 400:] - csx[:, :-400]) >= 2

    # a position decided at close of t earns the t->t+1 return, so "closed before the
    # drop" means the nearest offset is 2, not 1.
    ahead = np.zeros((m, n), bool)
    for off in (2, 3, 4):
        ahead[:, :-off] |= exmat[:, off:]
    after = np.zeros((m, n), bool)
    for off in (1, 2, 3, 4, 5):
        after[:, off:] |= exmat[:, :-off]
    paywin = np.zeros((m, n), bool)
    paywin |= paymat
    for off in (1, 2):
        paywin[:, off:] |= paymat[:, :n - off]

    def evt_book(name, desc, flag, sign=1.0):
        """long the flagged names, short the OTHER DIVIDEND PAYERS -- the control group
        that shares the style tilt, so only the ex-date TIMING survives."""
        W = np.zeros((m, n), np.float32)
        hit = flag & elig & payer
        ctl = (~flag) & elig & payer
        for t in range(n):
            a = np.where(hit[:, t])[0]
            b = np.where(ctl[:, t])[0]
            if a.size < 10 or b.size < 30:
                continue
            W[a, t] = sign * 0.5 / a.size
            W[b, t] = -sign * 0.5 / b.size
        add(name, desc, "X", W)

    evt_book("X01b_EXDIV_PRERUN_VS_PAYERS",
             "capture demand ahead of a scheduled ex-date, hedged against OTHER DIVIDEND "
             "PAYERS so the value/low-beta style tilt cancels: long names 1-3 sessions "
             "before their ex-date, short the rest of the payer universe", ahead)
    evt_book("X02b_EXDIV_UNWIND_VS_PAYERS",
             "the capture position unwinding: short names 1-5 sessions after their "
             "ex-date, long the rest of the payer universe", after, sign=-1.0)
    evt_book("X03b_DRIP_PAYDATE_VS_PAYERS",
             "DRIP reinvestment prints on the PAY date: long names on pay..pay+2 versus "
             "the rest of the payer universe (pay dates exist in the feed only from "
             "2020, so the design window carries ~2 years of it)", paywin)

    # ---- the ungated CONTROLS: what does the calendar window buy?
    lc = np.log(np.where(close > 0, close, np.nan))
    def ptd(keyfun):
        key = np.array([keyfun(d) for d in dates]); anchor = np.zeros(n, np.int64); a = 0
        for t in range(n):
            if t > 0 and key[t] != key[t - 1]:
                a = t - 1
            anchor[t] = a
        return lc - lc[:, anchor]
    mtd = ptd(lambda d: d[:7]); qtd = ptd(lambda d: d[:4] + str((int(d[5:7]) - 1) // 3))
    ytd = ptd(lambda d: d[:4])
    r20 = np.full((m, n), np.nan); r20[:, 20:] = lc[:, 20:] - lc[:, :-20]

    add("C01_CTRL_MTDMOM_EVERYDAY",
        "CONTROL, not a candidate: the same MTD-decile long-short book held on EVERY "
        "session. If W03's number is not clearly bigger than this, the month-end window "
        "bought nothing", "C", xs_weights(mtd, elig, np.ones(n, bool)))
    add("C02_CTRL_R20REV_EVERYDAY",
        "CONTROL: 20-session reversal decile book, every session -- the alive mechanism "
        "the seasonal books risk merely re-expressing", "C",
        xs_weights(-r20, elig, np.ones(n, bool)))
    add("C03_CTRL_YTDMOM_MIDYEAR",
        "CONTROL: the L-family book (YTD-return deciles) held through JUNE, a month with "
        "no tax deadline attached to it", "C",
        xs_weights(_carry(ytd, (month == 5) & (dom >= 25), n), elig, month == 6))
    add("C04_CTRL_QTDMOM_MIDQTR",
        "CONTROL: the W-family book (QTD deciles) held over the MIDDLE 4 sessions of each "
        "quarter instead of the last 4", "C",
        xs_weights(qtd, elig, (np.abs(qom) > 20) & (np.abs(qom) < 25)))

    out = {}
    for r in results:
        out[r.name] = dict(desc=r.desc, family=r.family,
                           design_net=stats(r.net, r.dates, *DESIGN),
                           design_gross=stats(r.gross, r.dates, *DESIGN),
                           design_stress=stats(r.net_stress, r.dates, *DESIGN),
                           active_frac=float(np.mean(r.expo > 0)))
        np.save(os.path.join(CACHE, r.name + ".npy"),
                np.vstack([r.gross, r.net, r.net_stress]))
    json.dump({"results": out}, open(os.path.join(CACHE, "stock_fix_design.json"), "w"))
    for k, v in sorted(out.items(), key=lambda x: -abs(x[1]["design_net"]["t"] or 0)):
        s = v["design_net"]
        print(f"{k:30s} act={v['active_frac']:.3f} Sh={s['sharpe']:6.2f} t={s['t']:6.2f} "
              f"meanbp={s['mean_bp']:6.2f} gross_t={v['design_gross']['t']:6.2f} "
              f"stress_t={v['design_stress']['t']:6.2f}")


if __name__ == "__main__":
    main()
