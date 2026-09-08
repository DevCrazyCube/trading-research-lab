#!/usr/bin/env python3
"""D0821 seasonality-with-mechanism: the cross-sectional stock families (W, L, X).

SPLIT PINNED BEFORE SCORING:
    design   = 2016-01-04 .. 2021-12-31
    held-out = 2022-01-01 .. 2026-08-13
"""
from __future__ import annotations
import gzip, json, os, sys, datetime as dt
import numpy as np

sys.path.insert(0, "/home/anont/meme/scripts")
from d0821_season_lib import calendar_features, run_weights, stats, COST_BP

PANEL = "/home/anont/meme/research/data/inv3_cache/panel.npz"
CORPACT = "/home/anont/meme/research/data/t3_cache/corporate_actions.json.gz"
CACHE = "/home/anont/meme/research/data/d0821_cache"
DESIGN = ("2016-01-04", "2022-01-01")
HELD = ("2022-01-01", "2099-01-01")
TOPN = 1000        # liquidity screen: top-N by 60d dollar volume
MINPX = 5.0
DECILE = 0.10


def build():
    z = np.load(PANEL, allow_pickle=True)
    syms = np.array(z["syms"]); dates = list(z["dates"])
    c = z["c"].astype(np.float64); o = z["o"].astype(np.float64); v = z["v"].astype(np.float64)
    m, n = c.shape
    ret = np.full((m, n), np.nan)
    ret[:, 1:] = c[:, 1:] / c[:, :-1] - 1.0
    # overnight and intraday legs (raw prices: fine, both are same-instrument ratios)
    onr = np.full((m, n), np.nan); onr[:, 1:] = o[:, 1:] / c[:, :-1] - 1.0
    idr = c / o - 1.0

    # --- corporate actions: mask returns spanning a split/adjustment
    ca = json.load(gzip.open(CORPACT))
    didx = {d: i for i, d in enumerate(dates)}
    sidx = {s: i for i, s in enumerate(syms)}
    exmat = np.zeros((m, n), bool)        # cluster-FIRST date == ex-date
    camat = np.zeros((m, n), bool)        # any corporate-action date
    paymat = np.zeros((m, n), bool)       # cluster-THIRD date == pay date (2020+ only)
    for s, ds in ca.items():
        i = sidx.get(s)
        if i is None:
            continue
        ds = sorted(ds)
        cluster = []
        clusters = []
        for d in ds:
            if cluster and (dt.date.fromisoformat(d) - dt.date.fromisoformat(cluster[-1])).days > 12:
                clusters.append(cluster); cluster = []
            cluster.append(d)
        if cluster:
            clusters.append(cluster)
        for cl in clusters:
            j = didx.get(cl[0])
            if j is not None:
                exmat[i, j] = True
            if len(cl) >= 3:
                j3 = didx.get(cl[2])
                if j3 is not None:
                    paymat[i, j3] = True
            for d in cl:
                j = didx.get(d)
                if j is not None:
                    camat[i, j] = True
    # a raw-price return spanning a SPLIT is garbage; kill any |ret|>25% on a CA day
    bad = camat & (np.abs(np.nan_to_num(ret)) > 0.25)
    bad[:, 1:] |= bad[:, :-1]
    ret[bad] = np.nan

    # --- liquidity screen
    dv = c * v
    dv = np.nan_to_num(dv)
    k = np.zeros_like(dv)
    cs = np.cumsum(dv, axis=1)
    k[:, 60:] = (cs[:, 60:] - cs[:, :-60]) / 60.0
    elig = (k > 0) & (c > MINPX) & np.isfinite(ret)
    rank = np.argsort(np.argsort(-k, axis=0), axis=0)
    elig &= rank < TOPN
    np.savez_compressed(os.path.join(CACHE, "stock_panel.npz"),
                        syms=syms, dates=np.array(dates), ret=ret.astype(np.float32),
                        onr=onr.astype(np.float32), idr=idr.astype(np.float32),
                        close=c.astype(np.float32), elig=elig,
                        exmat=exmat, paymat=paymat)
    return syms, dates, ret, onr, idr, c, elig, exmat, paymat


def load():
    """The panel's prices are RAW -- unadjusted for dividends -- so the close-to-close
    return realised ON an ex-date carries a mechanical drop of the dividend amount.
    A long-short book sorted on anything correlated with yield (and YTD losers ARE
    higher-yield) would then earn a spurious spread of the yield difference. It is
    exactly the sort of unmeasured sign error this programme keeps dying on, so the
    ex-date return is replaced by that session's cross-sectional median eligible
    return -- the total-return holder's approximate experience (price drop offset by
    the cash received), with no cross-sectional information in it."""
    p = os.path.join(CACHE, "stock_panel.npz")
    if not os.path.exists(p):
        syms, dates, ret, onr, idr, c, elig, exmat, paymat = build()
    else:
        z = np.load(p, allow_pickle=True)
        syms, dates = z["syms"], list(z["dates"])
        ret = z["ret"].astype(np.float64); onr = z["onr"].astype(np.float64)
        idr = z["idr"].astype(np.float64); c = z["close"].astype(np.float64)
        elig, exmat, paymat = z["elig"], z["exmat"], z["paymat"]
    med = np.nanmedian(np.where(elig, ret, np.nan), axis=0)
    med = np.nan_to_num(med)
    rows, cols = np.where(exmat)
    ret[rows, cols] = med[cols]
    onr[rows, cols] = np.nan          # the drop lands in the opening print
    return syms, dates, ret, onr, idr, c, elig, exmat, paymat


def xs_weights(score, elig, hold, dec=DECILE):
    """Dollar-neutral decile long-short from `score`, only on sessions where hold[t]."""
    m, n = score.shape
    W = np.zeros((m, n), dtype=np.float32)
    for t in np.where(hold)[0]:
        e = elig[:, t] & np.isfinite(score[:, t])
        idx = np.where(e)[0]
        if idx.size < 50:
            continue
        s = score[idx, t]
        order = np.argsort(s)
        k = max(5, int(round(dec * idx.size)))
        lo = idx[order[:k]]; hi = idx[order[-k:]]
        W[hi, t] = 0.5 / k
        W[lo, t] = -0.5 / k
    return W


def main():
    syms, dates, ret, onr, idr, close, elig, exmat, paymat = load()
    m, n = ret.shape
    cf = calendar_features(dates)
    tom, qom, month = cf["tom"], cf["qom"], cf["month"]
    dom = np.array([int(d[8:10]) for d in dates])
    year = cf["year"]
    cb = [COST_BP["stock"]] * m
    results = []

    def add(name, desc, fam, W, R=None):
        R = ret if R is None else R
        results.append(run_weights(name, desc, fam, dates, W, R, cb))
        print("built", name, flush=True)

    # ---------- scores -------------------------------------------------------
    lc = np.log(np.where(close > 0, close, np.nan))
    # period-to-date return since the start of the current quarter / year
    def ptd(keyfun):
        key = np.array([keyfun(d) for d in dates])
        anchor = np.zeros(n, dtype=np.int64)
        a = 0
        for t in range(n):
            if t > 0 and key[t] != key[t - 1]:
                a = t - 1
            anchor[t] = a
        return lc - lc[:, anchor]

    qtd = ptd(lambda d: d[:4] + str((int(d[5:7]) - 1) // 3))
    ytd = ptd(lambda d: d[:4])
    mtd = ptd(lambda d: d[:7])
    # trailing 250-session mean log price -> depth of embedded unrealised loss
    csl = np.cumsum(np.nan_to_num(lc), axis=1)
    okl = np.cumsum(np.isfinite(lc), axis=1)
    emb = np.full((m, n), np.nan)
    emb[:, 250:] = lc[:, 250:] - (csl[:, 250:] - csl[:, :-250]) / np.maximum(
        okl[:, 250:] - okl[:, :-250], 1)

    # =============================== FAMILY W ===============================
    # Quarter-end window dressing: a fund that must publish its holdings is paid to
    # be seen owning the quarter's winners.  The flow is winners-up / losers-down in
    # the final sessions and it has no information in it, so it must give back.
    add("W01_WD_QTR_MARKUP",
        "window dressing into the reporting date: long top-decile QTD return / short "
        "bottom decile, held over the last 4 sessions of the quarter", "W",
        xs_weights(qtd, elig, (qom >= -4) & (qom <= -1)))
    add("W02_WD_QTR_GIVEBACK",
        "the mark-up has no information: short the same top-decile QTD winners / long "
        "the losers over the first 3 sessions of the new quarter", "W",
        xs_weights(-_carry(qtd, qom == -1, n), elig, (qom >= 0) & (qom <= 2)))
    add("W03_WD_MONTH_MARKUP",
        "monthly-reporting version: long top-decile MTD / short bottom decile over the "
        "last 4 sessions of every month", "W",
        xs_weights(mtd, elig, (tom >= -4) & (tom <= -1)))
    add("W04_WD_MONTH_GIVEBACK",
        "monthly give-back: short the month's decile winners / long its losers over the "
        "first 3 sessions of the new month", "W",
        xs_weights(-_carry(mtd, tom == -1, n), elig, (tom >= 0) & (tom <= 2)))
    add("W05_WD_LASTSESSION",
        "leaning for the tape: long top-decile QTD / short bottom decile held over the "
        "final session of the quarter only", "W",
        xs_weights(qtd, elig, qom == -1))
    # the sharp mechanical test: a mark-up printed in the close must reverse in the
    # very next OPENING auction, before any information can arrive.
    Wov = xs_weights(-qtd, elig, qom == -1)
    add("W06_WD_CLOSE_TO_OPEN",
        "the mechanical signature: a close-print mark-up must unwind in the next OPENING "
        "auction. Short the quarter's decile winners / long its losers from the "
        "quarter-end close to the next open", "W", Wov, R=_shift_on(onr))
    Wov2 = xs_weights(-mtd, elig, tom == -1)
    add("W07_WD_MONTHEND_CLOSE_TO_OPEN",
        "same overnight signature at every month end", "W", Wov2, R=_shift_on(onr))

    # =============================== FAMILY L ===============================
    # Tax-loss harvesting.  A taxable holder with an embedded loss has a dated,
    # rule-bound incentive to realise it before 31 Dec, and the wash-sale rule then
    # FORBIDS the repurchase for 31 calendar days.
    ytd_dec = _carry(ytd, (month == 11) & (dom >= 25), n)     # score frozen ~1 Dec
    ytd_oct = _carry(ytd, (month == 9) & (dom >= 25), n)      # score frozen ~1 Oct
    ytd_mid = _carry(ytd, (month == 12) & (dom >= 12) & (dom <= 16), n)
    is_dec = (month == 12) & (dom <= 24)
    is_jan = (month == 1)
    is_wash = (month == 1) & (dom >= 12) & (dom <= 23)
    is_jan_early = (month == 1) & (dom <= 8)
    is_oct = (month == 10)
    is_nov_early = (month == 11) & (dom <= 10)

    add("L01_TLS_DEC_PRESSURE",
        "harvesting pressure: short the bottom-decile YTD losers / long the top decile "
        "through 1-24 December", "L", xs_weights(ytd_dec, elig, is_dec))
    add("L02_TLS_JAN_BOUNCE",
        "post-harvest bounce: long the prior year's decile losers / short its winners "
        "through January", "L", xs_weights(-ytd_dec, elig, is_jan))
    add("L03_TLS_WASHSALE_31D",
        "the rule-dated repurchase: the wash-sale clock on mid-December selling expires "
        "12-23 January. Long losers / short winners in exactly that window", "L",
        xs_weights(-ytd_mid, elig, is_wash))
    add("L04_TLS_JAN_FIRSTWEEK",
        "the naive-January control against L03: same book held only 2-8 January, before "
        "any wash-sale clock can have expired", "L",
        xs_weights(-ytd_dec, elig, is_jan_early))
    add("L05_TLS_OCT_FUNDYEAR",
        "US mutual funds close their tax year on 31 October: short the decile losers / "
        "long the winners through October", "L",
        xs_weights(ytd_oct, elig, is_oct))
    add("L06_TLS_NOV_BOUNCE",
        "the fund-year bounce: long October's decile losers / short its winners over "
        "1-10 November", "L",
        xs_weights(-_carry(ytd, (month == 10) & (dom >= 28), n), elig, is_nov_early))
    add("L07_TLS_EMBEDDED_LOSS",
        "score the AMOUNT of unrealised loss, not the YTD return: depth below the "
        "trailing 250-session mean log price, short the deepest through 1-24 December",
        "L", xs_weights(_carry(emb, (month == 11) & (dom >= 25), n), elig, is_dec))
    add("L08_TLS_EMBEDDED_JAN",
        "January bounce scored on embedded loss instead of YTD return", "L",
        xs_weights(-_carry(emb, (month == 11) & (dom >= 25), n), elig, is_jan))
    lowpx = close < 15.0
    add("L09_TLS_RETAIL_COHORT",
        "harvesting is a TAXABLE-holder flow: L01 restricted to the retail-heavy "
        "sub-$15 price cohort", "L",
        xs_weights(ytd_dec, elig & lowpx, is_dec))

    # =============================== FAMILY X ===============================
    # Single-name dividend plumbing: capture demand before a scheduled ex-date, and
    # DRIP reinvestment on the pay date.
    ahead = np.zeros((m, n), np.float64)
    for off in (1, 2, 3):
        ahead[:, :-off] += exmat[:, off:]
    after = np.zeros((m, n), np.float64)
    for off in (1, 2, 3, 4, 5):
        after[:, off:] += exmat[:, :-off]
    paywin = np.zeros((m, n), np.float64)
    for off in (0, 1, 2):
        paywin[:, off:] += paymat[:, :n - off] if off else paymat

    def evt_book(name, desc, flag, sign=1.0):
        W = np.zeros((m, n), np.float32)
        f = (flag > 0) & elig
        cnt = f.sum(0)
        for t in np.where(cnt >= 10)[0]:
            idx = np.where(f[:, t])[0]
            W[idx, t] = sign * 1.0 / idx.size
            # market hedge: short the eligible universe equally
            u = np.where(elig[:, t])[0]
            W[u, t] -= sign * 1.0 / u.size
        add(name, desc, "X", W)

    evt_book("X01_EXDIV_CAPTURE_PRERUN",
             "dividend-capture demand ahead of a scheduled ex-date: long names whose ex "
             "date is 1-3 sessions away, short the eligible universe (position closed "
             "before the ex drop)", ahead)
    evt_book("X02_EXDIV_CAPTURE_UNWIND",
             "the capture trade unwinds: short names 1-5 sessions AFTER their ex-date, "
             "long the universe", after, sign=-1.0)
    evt_book("X03_DRIP_PAYDATE",
             "DRIP reinvestment prints on the PAY date: long names on pay..pay+2, short "
             "the universe (pay dates only exist in this feed from 2020, so this book is "
             "almost entirely out of the design window and is reported as underpowered)",
             paywin)

    out = {}
    for r in results:
        out[r.name] = dict(desc=r.desc, family=r.family,
                           design_net=stats(r.net, r.dates, *DESIGN),
                           design_gross=stats(r.gross, r.dates, *DESIGN),
                           design_stress=stats(r.net_stress, r.dates, *DESIGN),
                           active_frac=float(np.mean(r.expo > 0)))
        np.save(os.path.join(CACHE, r.name + ".npy"),
                np.vstack([r.gross, r.net, r.net_stress]))
    json.dump({"dates": dates, "results": out, "design": DESIGN, "held": HELD},
              open(os.path.join(CACHE, "stock_design.json"), "w"))
    for k, v in sorted(out.items(), key=lambda x: -abs(x[1]["design_net"]["t"] or 0)):
        s = v["design_net"]
        print(f"{k:30s} fam={v['family']} act={v['active_frac']:.3f} "
              f"Sh={s['sharpe']:6.2f} t={s['t']:6.2f} meanbp={s['mean_bp']:6.2f} "
              f"gross_t={v['design_gross']['t']:6.2f} stress_t={v['design_stress']['t']:6.2f}")


def _carry(x, flag, n):
    """freeze x on the sessions where flag is True and carry it forward."""
    out = np.full_like(x, np.nan)
    cur = np.full(x.shape[0], np.nan)
    for t in range(n):
        if flag[t]:
            cur = x[:, t]
        out[:, t] = cur
    return out


def _shift_on(onr):
    """returns matrix whose column t+1 is the OVERNIGHT return close(t)->open(t+1)."""
    return onr


if __name__ == "__main__":
    os.makedirs(CACHE, exist_ok=True)
    main()
