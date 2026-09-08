#!/usr/bin/env python3
"""INVENT-R3 -- event-calendar sweep.  Design window first, holdout frozen until the end.

Rail (one rail for everything, no per-formula rail shopping):
  * enter at the CLOSE of the signal day t, exit at the CLOSE of day t+h
  * every book is dollar-neutral, gross 1.0 at entry (0.5 long / 0.5 short), equal weight
  * per-event return is therefore a gross-1.0 return; a round trip costs 2 x cost_bp
  * short leg pays borrow at 30 bp/yr on 0.5 notional

Statistics: per-event returns, Newey-West(h-1) t-stat, plus the annualised Sharpe of the
daily book that runs h overlapping 1/h tranches.
"""
import json
import math
import os
import sys
from collections import defaultdict

import numpy as np

ROOT = "/home/anont/meme"
CACHE = f"{ROOT}/research/data/inv3_cache"
DESIGN_END = "2021-12-31"
HOLDOUT_START = "2022-01-03"
BORROW_ANNUAL_BP = 30.0
COST_LO, COST_HI = 3.0, 6.0     # bp per side of gross traded

FOMC = set("""
2016-01-27 2016-03-16 2016-04-27 2016-06-15 2016-07-27 2016-09-21 2016-11-02 2016-12-14
2017-02-01 2017-03-15 2017-05-03 2017-06-14 2017-07-26 2017-09-20 2017-11-01 2017-12-13
2018-01-31 2018-03-21 2018-05-02 2018-06-13 2018-08-01 2018-09-26 2018-11-08 2018-12-19
2019-01-30 2019-03-20 2019-05-01 2019-06-19 2019-07-31 2019-09-18 2019-10-30 2019-12-11
2020-01-29 2020-03-15 2020-04-29 2020-06-10 2020-07-29 2020-09-16 2020-11-05 2020-12-16
2021-01-27 2021-03-17 2021-04-28 2021-06-16 2021-07-28 2021-09-22 2021-11-03 2021-12-15
2022-01-26 2022-03-16 2022-05-04 2022-06-15 2022-07-27 2022-09-21 2022-11-02 2022-12-14
2023-02-01 2023-03-22 2023-05-03 2023-06-14 2023-07-26 2023-09-20 2023-11-01 2023-12-13
2024-01-31 2024-03-20 2024-05-01 2024-06-12 2024-07-31 2024-09-18 2024-11-07 2024-12-18
2025-01-29 2025-03-19 2025-05-07 2025-06-18 2025-07-30 2025-09-17 2025-10-29 2025-12-10
2026-01-28 2026-03-18 2026-04-29 2026-06-17 2026-07-29
""".split())


# ===========================================================================
# data
# ===========================================================================
class Data:
    def __init__(self):
        z = np.load(f"{CACHE}/rets.npz", allow_pickle=False)
        self.days = [str(d) for d in z["days"]]
        self.syms = [str(s) for s in z["syms"]]
        self.rcc = z["rcc"]
        self.o, self.h, self.l, self.c = z["o"], z["h"], z["l"], z["c"]
        self.dv = z["dv"]
        self.nS, self.nD = self.rcc.shape
        self.didx = {d: i for i, d in enumerate(self.days)}
        self.events = json.load(open(f"{CACHE}/events.json"))

        # 21-day trailing mean dollar volume, strictly through day t
        dv0 = np.nan_to_num(self.dv, nan=0.0)
        cs = np.cumsum(dv0, axis=1)
        adv = np.full_like(dv0, np.nan)
        adv[:, 21:] = (cs[:, 21:] - cs[:, :-21]) / 21.0
        self.adv = adv
        self.tradable = (adv >= 5e6) & (self.c >= 5.0) & np.isfinite(self.rcc)

        # rank of adv within each day (0 = most liquid)
        self.advrank = np.full((self.nS, self.nD), 10**6, dtype=np.int32)
        for t in range(21, self.nD):
            ok = np.where(self.tradable[:, t])[0]
            if len(ok) == 0:
                continue
            order = ok[np.argsort(-adv[ok, t])]
            self.advrank[order, t] = np.arange(len(order))

        # cross-sectional mean return per day over the liquid universe (the "market")
        m = np.where(self.tradable, self.rcc, np.nan)
        self.mkt = np.nanmean(m, axis=0)

        # close location within the day's range
        rng = self.h - self.l
        with np.errstate(invalid="ignore", divide="ignore"):
            self.clv = (self.c - 0.5 * (self.h + self.l)) / rng
        self.clv[~np.isfinite(self.clv)] = np.nan

        # calendar flags
        self.is_fomc = np.array([d in FOMC for d in self.days])
        self.fomc_eve = np.zeros(self.nD, bool)
        self.fomc_eve[:-1] = self.is_fomc[1:]
        self.month = np.array([d[5:7] for d in self.days])
        self.year = np.array([d[:4] for d in self.days])
        ym = np.array([d[:7] for d in self.days])
        self.month_last = np.zeros(self.nD, bool)
        self.month_last[:-1] = ym[:-1] != ym[1:]
        self.month_last[-1] = True
        self.quarter_end = self.month_last & np.isin(self.month, ["03", "06", "09", "12"])
        # third Friday of Mar/Jun/Sep/Dec = triple witching; monthly third Friday = OPEX
        import datetime as _dt
        self.is_opex = np.zeros(self.nD, bool)
        self.is_witch = np.zeros(self.nD, bool)
        self.is_nfp = np.zeros(self.nD, bool)
        self.is_recon = np.zeros(self.nD, bool)
        by_month = defaultdict(list)
        for i, d in enumerate(self.days):
            by_month[d[:7]].append(i)
        for mkey, idxs in by_month.items():
            fridays = [i for i in idxs
                       if _dt.date.fromisoformat(self.days[i]).weekday() == 4]
            if len(fridays) >= 3:
                self.is_opex[fridays[2]] = True
                if mkey[5:7] in ("03", "06", "09", "12"):
                    self.is_witch[fridays[2]] = True
            if fridays:
                self.is_nfp[fridays[0]] = True          # first Friday of the month
                if mkey[5:7] == "06":
                    self.is_recon[fridays[-1]] = True   # last Friday of June
        # h-day forward sums
        self._fwd = {}

    def fwd(self, h):
        if h not in self._fwd:
            r = np.nan_to_num(self.rcc, nan=0.0)
            miss = ~np.isfinite(self.rcc)
            cs = np.concatenate([np.zeros((self.nS, 1)), np.cumsum(r, axis=1)], axis=1)
            cm = np.concatenate([np.zeros((self.nS, 1)),
                                 np.cumsum(miss.astype(np.float32), axis=1)], axis=1)
            F = np.full((self.nS, self.nD), np.nan, dtype=np.float32)
            end = self.nD - h
            F[:, :end] = cs[:, 1 + h:1 + h + end] - cs[:, 1:1 + end]
            nmiss = cm[:, 1 + h:1 + h + end] - cm[:, 1:1 + end]
            F[:, :end][nmiss > 0] = np.nan
            self._fwd[h] = F
        return self._fwd[h]


# ===========================================================================
# evaluation
# ===========================================================================
def nw_t(x, lag):
    x = np.asarray(x, float)
    n = len(x)
    if n < 8:
        return 0.0
    m = x.mean()
    d = x - m
    g0 = float(d @ d) / n
    var = g0
    for k in range(1, min(lag, n - 1) + 1):
        gk = float(d[k:] @ d[:-k]) / n
        var += 2.0 * (1.0 - k / (lag + 1.0)) * gk
    if var <= 0:
        return 0.0
    return m / math.sqrt(var / n)


def evaluate(D, tranches, h, name, note):
    """tranches: list of (t0, idx_long, idx_short). Returns per-window stats."""
    F = D.fwd(h)
    rows = []
    for t0, iL, iS in tranches:
        rl = F[iL, t0] if len(iL) else np.array([])
        rs = F[iS, t0] if len(iS) else np.array([])
        rl = rl[np.isfinite(rl)]
        rs = rs[np.isfinite(rs)]
        if len(rl) < 3 or len(rs) < 3:
            continue
        rows.append((t0, 0.5 * rl.mean() - 0.5 * rs.mean()))
    if len(rows) < 12:
        return None
    t0s = np.array([r[0] for r in rows])
    ret = np.array([r[1] for r in rows]) * 1e4          # bp, gross-1.0 book
    borrow = 0.5 * BORROW_ANNUAL_BP * h / 252.0
    out = {}
    for tag, dates, mask in (("design", None, t0s <= D.didx[max(d for d in D.days
                                                               if d <= DESIGN_END)]),
                             ("holdout", None, t0s >= D.didx[min(d for d in D.days
                                                                 if d >= HOLDOUT_START)])):
        r = ret[mask]
        if len(r) < 12:
            out[tag] = None
            continue
        span_days = (t0s[mask].max() - t0s[mask].min()) + h
        years = max(span_days / 252.0, 0.5)
        res = dict(n=int(len(r)), mean_bp=float(r.mean()), sd_bp=float(r.std(ddof=1)),
                   hit=float((r > 0).mean()),
                   t_gross=float(nw_t(r, max(h - 1, 1))),
                   breakeven_bp_per_side=float(r.mean() / 2.0))
        for cost, key in ((COST_LO, "lo"), (COST_HI, "hi")):
            net = r - 2.0 * cost - borrow
            res[f"mean_bp_net_{key}"] = float(net.mean())
            res[f"t_net_{key}"] = float(nw_t(net, max(h - 1, 1)))
            # annualised Sharpe of the capital-committed book
            per_year = len(r) / years
            res[f"sharpe_net_{key}"] = float(net.mean() / r.std(ddof=1)
                                             * math.sqrt(per_year)) if r.std(ddof=1) > 0 else 0.0
        res["events_per_year"] = float(len(r) / years)
        res["years"] = float(years)
        out[tag] = res
    out["name"] = name
    out["note"] = note
    out["h"] = h
    return out


# ===========================================================================
# book builders
# ===========================================================================
def announcer_cohorts(D):
    """entry day -> list of events, restricted to tradable names."""
    coh = defaultdict(list)
    for e in D.events:
        j, t = e["col"], e["entry"]
        if t >= D.nD - 25 or t < 25:
            continue
        if not D.tradable[j, t] or D.advrank[j, t] >= 2000:
            continue
        coh[t].append(e)
    return coh


def flag_book(D, coh, flagfn, sign, minn=8):
    """long the flagged announcers, short the same-day unflagged announcers."""
    tr = []
    for t, evs in coh.items():
        if len(evs) < minn:
            continue
        fl, un = [], []
        for e in evs:
            f = flagfn(e)
            if f is None:
                continue
            (fl if f else un).append(e["col"])
        if len(fl) < 3 or len(un) < 3:
            continue
        iL, iS = np.array(sorted(set(fl))), np.array(sorted(set(un)))
        if sign < 0:
            iL, iS = iS, iL
        tr.append((t, iL, iS))
    return tr


def score_book(D, coh, scorefn, sign, frac=0.30, minn=10):
    """cross-sectional sort inside the same-day announcer cohort."""
    tr = []
    for t, evs in coh.items():
        pairs = [(scorefn(e), e["col"]) for e in evs]
        pairs = [(s, j) for s, j in pairs if s is not None and np.isfinite(s)]
        if len(pairs) < minn:
            continue
        pairs.sort()
        k = max(3, int(len(pairs) * frac))
        lowi = np.array([j for _, j in pairs[:k]])
        highi = np.array([j for _, j in pairs[-k:]])
        iL, iS = (highi, lowi) if sign > 0 else (lowi, highi)
        tr.append((t, iL, iS))
    return tr


def xs_book(D, dayflags, scorefn, sign, topn=1000, frac=0.10, minn=50):
    """cross-sectional decile book on the liquid universe, only on flagged days."""
    tr = []
    for t in np.where(dayflags)[0]:
        if t < 260 or t >= D.nD - 30:
            continue
        univ = np.where(D.tradable[:, t] & (D.advrank[:, t] < topn))[0]
        if len(univ) < minn:
            continue
        s = scorefn(t, univ)
        ok = np.isfinite(s)
        univ, s = univ[ok], s[ok]
        if len(univ) < minn:
            continue
        order = np.argsort(s)
        k = max(5, int(len(univ) * frac))
        lowi, highi = univ[order[:k]], univ[order[-k:]]
        iL, iS = (highi, lowi) if sign > 0 else (lowi, highi)
        tr.append((t, iL, iS))
    return tr


def items_of(e):
    return set(x.strip() for x in e["items"].split(",") if x.strip())


# ===========================================================================
def main():
    D = Data()
    coh = announcer_cohorts(D)
    print(f"cohort days {len(coh)}  events in cohorts "
          f"{sum(len(v) for v in coh.values())}", flush=True)
    results = []

    def add(res):
        if res is not None:
            results.append(res)
            d, ho = res["design"], res.get("holdout")
            print("%-26s h=%-3d design n=%4d mean=%7.1fbp t=%5.2f  | holdout t=%5.2f"
                  % (res["name"], res["h"], d["n"], d["mean_bp"], d["t_net_lo"],
                     ho["t_net_lo"] if ho else float("nan")), flush=True)

    PLAIN = {"2.02", "9.01"}

    # ---- A: 8-K metadata conditioners -------------------------------------
    add(evaluate(D, flag_book(D, coh, lambda e: len(items_of(e) - PLAIN - {"7.01"}) > 0, -1),
                 5, "A01_ITEM_EXTRA_5",
                 "short announcers whose 8-K carries an item beyond 2.02/9.01/7.01, "
                 "long the same-day plain announcers"))
    add(evaluate(D, flag_book(D, coh, lambda e: "5.02" in items_of(e), -1),
                 5, "A02_ITEM_502_OFFICER_5",
                 "short announcers whose earnings 8-K also carries item 5.02 "
                 "(officer departure/appointment)"))
    add(evaluate(D, flag_book(D, coh, lambda e: "2.05" in items_of(e), -1),
                 5, "A03_ITEM_205_RESTRUCT_5",
                 "short announcers whose 8-K also carries item 2.05 (exit/disposal costs)"))
    add(evaluate(D, flag_book(D, coh, lambda e: "8.01" in items_of(e), +1),
                 5, "A04_ITEM_801_OTHER_5",
                 "long announcers whose 8-K also carries item 8.01 (other events: "
                 "buyback, guidance, dividend)"))
    add(evaluate(D, flag_book(D, coh, lambda e: "7.01" in items_of(e), +1),
                 5, "A05_ITEM_701_REGFD_5",
                 "long announcers who furnish item 7.01 (Reg FD deck) with the release"))
    add(evaluate(D, score_book(D, coh, lambda e: float(len(items_of(e))), -1),
                 5, "A06_ITEM_COUNT_XS_5",
                 "tercile sort on the NUMBER of 8-K items; short the busiest filings"))
    add(evaluate(D, flag_book(D, coh, lambda e: len(items_of(e) - PLAIN - {"7.01"}) > 0, -1),
                 21, "A07_ITEM_EXTRA_21",
                 "A01 held 21 sessions instead of 5"))
    add(evaluate(D, flag_book(D, coh, lambda e: (None if e["med_hour"] is None
                                                 else e["hour"] - e["med_hour"] >= 2.0), -1),
                 5, "A08_TIMEMIG_LATE_5",
                 "short announcers releasing >=2h LATER in the day than their own "
                 "trailing-4-quarter median filing hour"))
    add(evaluate(D, flag_book(D, coh, lambda e: (None if e["med_hour"] is None
                                                 else e["hour"] - e["med_hour"] <= -2.0), +1),
                 5, "A09_TIMEMIG_EARLY_5",
                 "long announcers releasing >=2h EARLIER than their own median filing hour"))
    add(evaluate(D, score_book(D, coh, lambda e: (None if e["med_hour"] is None
                                                  else e["hour"] - e["med_hour"]), -1),
                 5, "A10_TIMEMIG_XS_5",
                 "continuous tercile sort on filing-hour delta vs own history; short the "
                 "late-shifters"))
    add(evaluate(D, score_book(D, coh, lambda e: (None if e["lag_delta"] is None
                                                  else float(e["lag_delta"])), -1),
                 5, "A11_LAGDELTA_XS_5",
                 "tercile sort on reporting-lag delta vs the same quarter a year earlier; "
                 "short the ones reporting later than last year"))
    add(evaluate(D, score_book(D, coh, lambda e: (None if e["lag_delta"] is None
                                                  else float(e["lag_delta"])), -1),
                 21, "A12_LAGDELTA_XS_21", "A11 held 21 sessions"))
    add(evaluate(D, flag_book(D, coh, lambda e: e["hour"] >= 16.0, -1),
                 5, "A13_AMC_VS_BMO_5",
                 "short after-the-close announcers, long before-the-open announcers "
                 "(structural release-time split, not migration)"))

    with open(f"{CACHE}/partial_A.json", "w") as fh:
        json.dump(results, fh, indent=1)

    # ---- C: rebalance / witching close-auction distortion -----------------
    def clv_score(t, univ):
        return D.clv[univ, t]

    add(evaluate(D, xs_book(D, D.is_witch, clv_score, -1), 1, "C01_WITCH_CLV_FADE",
                 "on triple-witching day, fade the close-location-in-range decile "
                 "(index MOC distortion unwind), hold 1 session"))
    add(evaluate(D, xs_book(D, D.month_last, clv_score, -1), 1, "C02_MONTHEND_CLV_FADE",
                 "same fade on the last session of each month"))
    add(evaluate(D, xs_book(D, D.quarter_end, clv_score, -1), 1, "C03_QEND_CLV_FADE",
                 "same fade on quarter-end sessions only"))
    allday = np.ones(D.nD, bool)
    add(evaluate(D, xs_book(D, allday, clv_score, -1), 1, "C04_CLV_FADE_ALLDAYS_CTRL",
                 "CONTROL: the same close-location fade on EVERY session -- what the "
                 "calendar gate has to beat"))

    def clv_small(t, univ):
        s = D.clv[univ, t].copy()
        s[D.advrank[univ, t] < 400] = np.nan      # small caps only
        return s
    add(evaluate(D, xs_book(D, D.is_recon, clv_small, -1, topn=1500, minn=40), 1,
                 "C05_RUSSELL_RECON_CLV_FADE",
                 "last Friday of June (Russell reconstitution effective close): fade the "
                 "close-location decile in the smaller half of the liquid universe"))

    def opexweek_ret(t, univ):
        return D.rcc[univ, t - 4:t + 1].sum(axis=1)
    add(evaluate(D, xs_book(D, D.is_opex, opexweek_ret, -1), 5, "C06_OPEXWEEK_RET_FADE",
                 "on monthly OPEX Friday, fade the 5-session return run into expiry "
                 "(pin-release), hold 5 sessions"))

    # ---- D: macro windows -------------------------------------------------
    def day_ret(t, univ):
        return D.rcc[univ, t]

    add(evaluate(D, xs_book(D, D.is_fomc, day_ret, -1), 1, "D01_FOMCDAY_XS_FADE",
                 "on an FOMC statement session, fade the day's cross-sectional return "
                 "decile, hold 1 session"))
    beta = None

    def lowbeta(t, univ):
        w = slice(t - 120, t)
        r = D.rcc[univ, w]
        m = D.mkt[w]
        r = np.nan_to_num(r, nan=0.0)
        mm = np.nan_to_num(m, nan=0.0)
        cov = (r * mm).mean(axis=1) - r.mean(axis=1) * mm.mean()
        var = mm.var()
        return -(cov / var) if var > 0 else np.full(len(univ), np.nan)
    add(evaluate(D, xs_book(D, D.fomc_eve, lowbeta, +1), 1, "D02_FOMCEVE_LOWBETA",
                 "the session before an FOMC decision, long the low-beta decile and short "
                 "the high-beta decile, unwound at the decision close"))
    add(evaluate(D, xs_book(D, D.is_nfp, day_ret, -1), 1, "D03_NFPDAY_XS_FADE",
                 "on payroll Friday, fade the day's cross-sectional return decile"))
    ctrl = ~(D.is_fomc | D.is_nfp | D.is_witch | D.month_last)
    add(evaluate(D, xs_book(D, ctrl, day_ret, -1), 1, "D04_XS_FADE_QUIETDAYS_CTRL",
                 "CONTROL: the same one-day cross-sectional return fade on sessions with "
                 "NO scheduled event -- the always-on benchmark"))

    with open(f"{CACHE}/partial_ACD.json", "w") as fh:
        json.dump(results, fh, indent=1)
    print("wrote partial_ACD.json", flush=True)
    return results


if __name__ == "__main__":
    main()
