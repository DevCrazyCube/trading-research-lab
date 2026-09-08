#!/usr/bin/env python3
"""INVENT-R3 -- the joint null and the calendar-gate value test.

(1) Correlation-aware joint null.  Every formula's per-event gross return series is
    re-signed with a sign drawn ONCE PER TRADING DAY and shared by every formula that has
    an event on that day, so contemporaneous cross-formula correlation survives the
    resampling.  The statistic is max |t| over the whole family per replicate.

(2) Gate value.  For the close-location fade -- the only family whose event-gated means
    exceed the always-on control -- ask directly whether the gate is worth anything:
    regress the per-event gross return of the ALL-DAYS control on a month-end / quarter-end
    / witching dummy.
"""
import json
import math

import numpy as np

import inv3_run as R
import inv3_run2 as R2

CACHE = R.CACHE
NREP = 20000
RNG = np.random.default_rng(20260821)


def per_event_series(D):
    """rebuild (event_day, gross_bp) for every formula, design window only."""
    coh = R.announcer_cohorts(D)
    peers = R2.peer_sets(D)
    PLAIN = {"2.02", "9.01"}
    io = R.items_of
    builders = {}

    def fb(fn, sign):
        return R.flag_book(D, coh, fn, sign)

    def sb(fn, sign):
        return R.score_book(D, coh, fn, sign)

    builders["A01_ITEM_EXTRA_5"] = (fb(lambda e: len(io(e) - PLAIN - {"7.01"}) > 0, -1), 5)
    builders["A02_ITEM_502_OFFICER_5"] = (fb(lambda e: "5.02" in io(e), -1), 5)
    builders["A04_ITEM_801_OTHER_5"] = (fb(lambda e: "8.01" in io(e), +1), 5)
    builders["A05_ITEM_701_REGFD_5"] = (fb(lambda e: "7.01" in io(e), +1), 5)
    builders["A06_ITEM_COUNT_XS_5"] = (sb(lambda e: float(len(io(e))), -1), 5)
    builders["A07_ITEM_EXTRA_21"] = (fb(lambda e: len(io(e) - PLAIN - {"7.01"}) > 0, -1), 21)
    builders["A08_TIMEMIG_LATE_5"] = (fb(lambda e: (None if e["med_hour"] is None
                                                    else e["hour"] - e["med_hour"] >= 2.0), -1), 5)
    builders["A09_TIMEMIG_EARLY_5"] = (fb(lambda e: (None if e["med_hour"] is None
                                                     else e["hour"] - e["med_hour"] <= -2.0), +1), 5)
    builders["A10_TIMEMIG_XS_5"] = (sb(lambda e: (None if e["med_hour"] is None
                                                  else e["hour"] - e["med_hour"]), -1), 5)
    builders["A11_LAGDELTA_XS_5"] = (sb(lambda e: (None if e["lag_delta"] is None
                                                   else float(e["lag_delta"])), -1), 5)
    builders["A12_LAGDELTA_XS_21"] = (sb(lambda e: (None if e["lag_delta"] is None
                                                    else float(e["lag_delta"])), -1), 21)
    builders["A13_AMC_VS_BMO_5"] = (fb(lambda e: e["hour"] >= 16.0, -1), 5)

    clv = lambda t, u: D.clv[u, t]  # noqa: E731
    builders["C01_WITCH_CLV_FADE"] = (R.xs_book(D, D.is_witch, clv, -1), 1)
    builders["C02_MONTHEND_CLV_FADE"] = (R.xs_book(D, D.month_last, clv, -1), 1)
    builders["C03_QEND_CLV_FADE"] = (R.xs_book(D, D.quarter_end, clv, -1), 1)
    builders["C04_CLV_FADE_ALLDAYS_CTRL"] = (R.xs_book(D, np.ones(D.nD, bool), clv, -1), 1)
    builders["C06_OPEXWEEK_RET_FADE"] = (
        R.xs_book(D, D.is_opex, lambda t, u: D.rcc[u, t - 4:t + 1].sum(axis=1), -1), 5)
    dayret = lambda t, u: D.rcc[u, t]  # noqa: E731
    builders["D01_FOMCDAY_XS_FADE"] = (R.xs_book(D, D.is_fomc, dayret, -1), 1)
    builders["D02_FOMCEVE_LOWBETA"] = (R.xs_book(D, D.fomc_eve, R2_lowbeta(D), +1), 1)
    builders["D03_NFPDAY_XS_FADE"] = (R.xs_book(D, D.is_nfp, dayret, -1), 1)
    ctrl = ~(D.is_fomc | D.is_nfp | D.is_witch | D.month_last)
    builders["D04_XS_FADE_QUIETDAYS_CTRL"] = (R.xs_book(D, ctrl, dayret, -1), 1)
    builders["B01_PEER_SYMPATHY_FADE_1"] = (R2.peer_sympathy(D, peers, coh, 1, -1), 1)
    builders["B02_PEER_SYMPATHY_FADE_3"] = (R2.peer_sympathy(D, peers, coh, 3, -1), 3)
    builders["B03_BUYBACK_WINDOW"] = (R2.buyback_window(D, coh), 1)
    builders["E01_CROWDED_CAL_XS_FADE"] = (R2.attention_fade(D, coh, True, -1), 1)
    builders["E02_QUIET_CAL_XS_FADE_CTRL"] = (R2.attention_fade(D, coh, False, -1), 1)
    builders["E03_EARN_GAP_OC_FADE"] = (R2.reaction_gap_fade(D, coh, -1), 0)

    import inv3_run3 as R3
    _, last_print, next_pred = R3.event_masks(D)
    rebal = D.month_last | D.is_witch | D.quarter_end
    macro = D.is_fomc | D.is_nfp
    builders["F01_REBAL_CLV_FADE_POOLED"] = (R.xs_book(D, rebal, clv, -1), 1)
    builders["F04_MACRO_POOLED_XS_FADE"] = (R.xs_book(D, macro, dayret, -1), 1)
    builders["F08_REV5_PRE_EARN"] = (R3.gated_rev_book(
        D, lambda t, u: u[(next_pred[u, t] >= 1) & (next_pred[u, t] <= 5)], minn=25), 5)
    builders["F09_REV5_POST_EARN"] = (R3.gated_rev_book(
        D, lambda t, u: u[((t - last_print[u, t]) >= 1) & ((t - last_print[u, t]) <= 10)],
        minn=25), 5)
    builders["F10_REV5_NOEVENT_CTRL"] = (R3.gated_rev_book(
        D, lambda t, u: u[((t - last_print[u, t]) > 20) & (next_pred[u, t] > 20)],
        minn=25), 5)

    di = D.didx[max(d for d in D.days if d <= R.DESIGN_END)]
    with np.errstate(invalid="ignore"):
        roc = D.c / D.o - 1.0
    roc[~np.isfinite(roc) | (np.abs(roc) > 0.9)] = np.nan

    series = {}
    for name, (tr, h) in builders.items():
        F = roc if h == 0 else D.fwd(h)
        days, vals = [], []
        for t0, iL, iS in tr:
            if t0 > di:
                continue
            col = 0 if h == 0 else t0
            rl = F[iL, t0] if h == 0 else F[iL, t0]
            rs = F[iS, t0] if h == 0 else F[iS, t0]
            rl, rs = rl[np.isfinite(rl)], rs[np.isfinite(rs)]
            if len(rl) < 3 or len(rs) < 3:
                continue
            days.append(t0)
            vals.append((0.5 * rl.mean() - 0.5 * rs.mean()) * 1e4)
        if len(vals) >= 12:
            series[name] = (np.array(days), np.array(vals), max(h - 1, 1))
    return series, builders


def R2_lowbeta(D):
    def f(t, univ):
        w = slice(t - 120, t)
        r = np.nan_to_num(D.rcc[univ, w], nan=0.0)
        mm = np.nan_to_num(D.mkt[w], nan=0.0)
        cov = (r * mm).mean(axis=1) - r.mean(axis=1) * mm.mean()
        var = mm.var()
        return -(cov / var) if var > 0 else np.full(len(univ), np.nan)
    return f


def main():
    D = R.Data()
    series, _ = per_event_series(D)
    names = sorted(series)
    print(f"{len(names)} formulas in the joint null", flush=True)

    obs = {}
    for nm in names:
        d, v, lag = series[nm]
        obs[nm] = abs(R.nw_t(v, lag))
    for nm in sorted(obs, key=lambda k: -obs[k])[:6]:
        print("  observed |t| %-28s %.2f" % (nm, obs[nm]))

    maxday = D.nD
    maxes = np.empty(NREP)
    packs = [(series[nm][0], series[nm][1] - series[nm][1].mean(), series[nm][2])
             for nm in names]
    for rep in range(NREP):
        s = RNG.choice([-1.0, 1.0], size=maxday)
        m = 0.0
        for d, v, lag in packs:
            x = v * s[d]
            t = abs(R.nw_t(x, lag))
            if t > m:
                m = t
        maxes[rep] = m
        if rep % 4000 == 0:
            print(f"  rep {rep}", flush=True)

    N = len(names)
    out = dict(
        n_formulas_in_null=N,
        analytic_expected_max_sqrt_2lnN=math.sqrt(2 * math.log(N)),
        analytic_sign_agnostic_2N=math.sqrt(2 * math.log(2 * N)),
        empirical_expected_max=float(maxes.mean()),
        empirical_p50=float(np.percentile(maxes, 50)),
        empirical_p95=float(np.percentile(maxes, 95)),
        empirical_p99=float(np.percentile(maxes, 99)),
        observed_max=float(max(obs.values())),
        observed_max_name=max(obs, key=lambda k: obs[k]),
        observed_max_excluding_controls=float(max(v for k, v in obs.items()
                                                  if "CTRL" not in k)),
        observed_max_excluding_controls_name=max((k for k in obs if "CTRL" not in k),
                                                 key=lambda k: obs[k]),
        p_value_of_observed_max=float((maxes >= max(obs.values())).mean()),
        observed=obs,
    )

    # ---- gate value: does the calendar gate add anything to the all-days fade? ----
    d, v, _ = series["C04_CLV_FADE_ALLDAYS_CTRL"]
    for gname, flag in (("month_last", D.month_last), ("quarter_end", D.quarter_end),
                        ("witch", D.is_witch), ("opex", D.is_opex), ("fomc", D.is_fomc)):
        g = flag[d].astype(float)
        if g.sum() < 8:
            continue
        a, b = v[g == 0], v[g == 1]
        se = math.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
        out.setdefault("gate_value", {})[gname] = dict(
            n_gated=int(len(b)), mean_gated_bp=float(b.mean()),
            n_ungated=int(len(a)), mean_ungated_bp=float(a.mean()),
            diff_bp=float(b.mean() - a.mean()), t_diff=float((b.mean() - a.mean()) / se))
    with open(f"{CACHE}/null.json", "w") as fh:
        json.dump(out, fh, indent=1)
    print(json.dumps({k: v for k, v in out.items() if k != "observed"}, indent=1))


if __name__ == "__main__":
    main()
