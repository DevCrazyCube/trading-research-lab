#!/usr/bin/env python3
"""T11 -- evaluation of shortlist candidate #7: cash-merger arbitrage spread.

Frozen rule: research/trading_bot/T11_PREREGISTRATION.md
             sha256 b2aa8c60419a5058437ba26a1df6093d7c85a752f9010a16322edf6ae43e9880

This module refuses to run if that file's hash has changed. Statistics come from the T2 harness
(`scripts/trading_bot/stats.py`) and the cost model from `scripts/trading_bot/costs.py` -- the
T6-corrected PER-SIDE model. Neither is reimplemented here.

The only fitted quantity in the whole rig is the choice of H among the three declared horizons,
made on the design window by the criterion written into section 3 of the pre-registration.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import math
import pathlib
import random
import statistics
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from fractions import Fraction

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.t3_pressure_reversal as t3                                        # noqa: E402
import scripts.t11_merger_arb as t11                                             # noqa: E402
from scripts.trading_bot import costs as C                                       # noqa: E402
from scripts.trading_bot import stats as S                                       # noqa: E402
from scripts.trading_bot.frozen import Refused                                   # noqa: E402

PREREG = ROOT / "research" / "trading_bot" / "T11_PREREGISTRATION.md"
PREREG_SHA = "b2aa8c60419a5058437ba26a1df6093d7c85a752f9010a16322edf6ae43e9880"

DESIGN_START = "2020-01-02"
DESIGN_END, TEST_START, END = t3.DESIGN_END, t3.TEST_START, t3.END

HORIZONS = (5, 21, 63)            # section 3, the entire trial space
TRIALS = 3
SEED = 20260817
MIN_PRICE = 5.0
MIN_DOLLAR_VOL = 1_000_000.0
STOPS_TRADING_WITHIN = 10
DISCOUNT_CAP = 0.20               # section 4, exclusion 8
CASH_LAG_DAYS = 5                 # section 5
RF = "BIL"
MARKET = "SPY"

SEC31_BP = Fraction(278, 1000)                # 0.278 bp of sale notional
TAF_PER_SHARE = Fraction(166, 1_000_000_000)  # $0.000166/share sold

BREAK_LOSSES = (-0.10, -0.20, -0.25, -0.30, -0.40)
PRIMARY_BREAK_LOSS = -0.25
BREAK_RATES = (0.0, 0.02, 0.05, 0.06, 0.08, 0.10, 0.15)
BREAK_GATE_BSTAR = 0.10
LIT_EXCESS_ANNUAL = 0.04          # Mitchell & Pulvino (2001), post-cost


def assert_frozen():
    got = hashlib.sha256(PREREG.read_bytes()).hexdigest()
    if got != PREREG_SHA:
        raise Refused(
            f"pre-registration hash mismatch: expected {PREREG_SHA}, on disk {got}. "
            "The frozen rule changed; this is not the test that was registered."
        )


# ---------------------------------------------------------------------------
# risk-free: BIL total return, dividend-adjusted, first-party
# ---------------------------------------------------------------------------

def adjusted_bars(symbols, name):
    def build():
        out = defaultdict(dict)
        for block in t3.paged("/v2/stocks/bars",
                              {"symbols": ",".join(symbols), "start": t3.START, "end": t3.END,
                               "timeframe": "1Day", "adjustment": "all",
                               "limit": t3.PAGE, "feed": "sip"}, "bars"):
            for sym, rows in block.items():
                for r in rows:
                    out[sym][r["t"][:10]] = r["c"]
        return dict(out)
    return t11.cache_json(name, build)


_RF_DATES: list = []
_RF_CACHE: dict = {}


def rf_factor(rf_close, cal, idx, d0: str, cash_date: str) -> float:
    """Total return of BIL from the close of d0 to the last session on or before cash_date."""
    global _RF_DATES
    if not _RF_DATES:
        _RF_DATES = sorted(rf_close)
    hit = _RF_CACHE.get((d0, cash_date))
    if hit is not None:
        return hit
    import bisect
    k = bisect.bisect_right(_RF_DATES, cash_date)
    if k == 0 or d0 not in rf_close:
        raise Refused(f"BIL has no close for {d0} / {cash_date}")
    value = rf_close[_RF_DATES[k - 1]] / rf_close[d0] - 1.0
    _RF_CACHE[(d0, cash_date)] = value
    return value


# ---------------------------------------------------------------------------
# events
# ---------------------------------------------------------------------------

def build_events(H, bars, auct, cal, idx):
    """Section 4, applied identically in both windows. Returns (kept, funnel counts)."""
    raw = [e for e in t11.cash_merger_events() if t11.is_ticker_shaped(e)]
    f = defaultdict(int)
    kept, capped = [], []
    for e in raw:
        f["events"] += 1
        sym, eff, rate = e["acquiree_symbol"], e["effective_date"], e.get("rate")
        if not rate or rate <= 0:
            continue
        f["rate_positive"] += 1
        b = bars.get(sym) or {}
        if not b:
            continue
        f["has_bars"] += 1
        prior = [d for d in b if d <= eff]
        if not prior:
            continue
        t_last = max(prior)
        if t_last not in idx:
            continue
        j = idx[t_last]
        cut = cal[min(j + STOPS_TRADING_WITHIN, len(cal) - 1)]
        if any(d > cut for d in b):
            continue
        f["stops_trading"] += 1
        k = j - H
        if k < 0:
            continue
        t0 = cal[k]
        bar = b.get(t0)
        if bar is None:
            continue
        f["entry_bar"] += 1
        rec_a = auct.get(f"{sym}|{t0}") or {}
        if "c" not in rec_a:
            continue
        f["entry_auction_close"] += 1
        p0 = rec_a["c"]
        if p0 <= MIN_PRICE:
            continue
        f["price_gt_5"] += 1
        dv = (bar.get("vw") or bar["c"]) * bar["v"]
        if dv <= MIN_DOLLAR_VOL:
            continue
        f["dollar_vol_gt_1m"] += 1
        spread = rate / p0 - 1.0
        rec = {
            "symbol": sym, "effective_date": eff, "t0": t0, "t_last": t_last,
            "rate": rate, "p0": p0, "gross_spread": spread,
            "sessions": j - k,
            "cash_date": (date.fromisoformat(eff) + timedelta(days=CASH_LAG_DAYS)).isoformat(),
            "calendar_days": (date.fromisoformat(eff) + timedelta(days=CASH_LAG_DAYS)
                              - date.fromisoformat(t0)).days,
            "period": "design" if eff <= DESIGN_END else "test",
        }
        if spread > DISCOUNT_CAP:
            capped.append(rec)
            continue
        f["passes_discount_cap"] += 1
        kept.append(rec)
    return kept, capped, dict(f)


# ---------------------------------------------------------------------------
# costs
# ---------------------------------------------------------------------------

def cost_model(h_bp: float) -> C.CostModel:
    # NOT MEASURED_B22B: this number is not B22B's, it is a first-party median SIP quoted
    # half-spread of the merger targets themselves. Neither leg it is charged to has been
    # measured -- the entry is a single-price closing auction (M0's live half is outstanding)
    # and the exit is a cash corporate action that is not a trade at all -- so on both legs it
    # is exactly what the enum says: a deliberately adverse stand-in carried across from a
    # measurement of a different object. Labelling it MEASURED_* would be the mislabel this
    # module exists to prevent.
    prov = C.SlippageProvenance.ADVERSE_PROXY_FOR_AN_UNMEASURED_LEG
    return C.CostModel(
        entry_half_spread=C.CostComponent(
            "entry_half_spread", Fraction(round(h_bp * 1000), 1000), "bp", prov,
            "median SIP quoted half-spread of the merger targets themselves, "
            "[15:59:59,16:00:00) ET on the actual entry days (T11 prereg section 6), charged "
            "to a closing-auction entry that structurally has no spread to cross"),
        entry_extra_slippage=C.CostComponent(
            "entry_extra_slippage", Fraction(0), "bp", C.SlippageProvenance.STRESS_LADDER,
            "declared LOWER BOUND of zero, swept by the stress ladder"),
        exit_half_spread=C.CostComponent(
            "exit_half_spread", Fraction(round(h_bp * 1000), 1000), "bp", prov,
            "the exit is a CASH CORPORATE ACTION, not a trade; a half-spread is "
            "over-conservative here and is charged anyway rather than argued down"),
        exit_extra_slippage=C.CostComponent(
            "exit_extra_slippage", Fraction(0), "bp", C.SlippageProvenance.STRESS_LADDER,
            "declared LOWER BOUND of zero, swept by the stress ladder"),
        commission_per_share=C.CostComponent(
            "commission_per_share", Fraction(0), "micro-dollars/share",
            C.SlippageProvenance.BROKER_SCHEDULE, "Alpaca charges $0/share"),
        borrow_annual=C.measured_borrow_annual("etb_general_collateral"),
    )


def event_costs(rec, model: C.CostModel) -> float:
    """Fraction of entry notional lost to friction over the whole event. Positive is adverse."""
    entry = float(model.entry_spread_and_slippage_fraction())
    exit_ = float(model.exit_spread_and_slippage_fraction())
    # regulatory, charged on the cash-out leg as if it were a sale
    proceeds_ratio = rec["rate"] / rec["p0"]
    sec31 = float(SEC31_BP) * 1e-4 * proceeds_ratio
    taf = float(TAF_PER_SHARE) / rec["p0"]
    return entry + exit_ * proceeds_ratio + sec31 + taf


def net_excess(rec, model, rf_close, cal, idx):
    gross = rec["gross_spread"]
    cost = event_costs(rec, model)
    rf = rf_factor(rf_close, cal, idx, rec["t0"], rec["cash_date"])
    return gross - cost - rf, gross, cost, rf


# ---------------------------------------------------------------------------
# daily portfolio series
# ---------------------------------------------------------------------------

def daily_series(recs, model, bars, auct, rf_close, cal, idx):
    """Equal-weight book of every deal held that session, net of cost and of BIL."""
    entry = float(model.entry_spread_and_slippage_fraction())
    exit_ = float(model.exit_spread_and_slippage_fraction())
    per_day = defaultdict(list)
    for r in recs:
        b = bars.get(r["symbol"]) or {}
        i0, i1 = idx[r["t0"]], idx[r["t_last"]]
        prev = r["p0"]
        prev_day = r["t0"]
        first = True
        for d in cal[i0 + 1:i1 + 1]:
            bar = b.get(d)
            if bar is None:
                continue
            px = (auct.get(f"{r['symbol']}|{d}") or {}).get("c") or bar["c"]
            ret = px / prev - 1.0
            if first:
                ret -= entry
                first = False
            per_day[d].append(ret)
            prev, prev_day = px, d
        # terminal leg: last traded price -> cash, charged the exit side and the regulatory pass
        j = idx[prev_day]
        term_day = cal[min(j + 1, len(cal) - 1)]
        proceeds_ratio = r["rate"] / prev
        term = proceeds_ratio - 1.0 - exit_ * proceeds_ratio \
            - float(SEC31_BP) * 1e-4 * proceeds_ratio - float(TAF_PER_SHARE) / prev
        if first:
            term -= entry
        per_day[term_day].append(term)

    days = sorted(per_day)
    out = []
    for d in days:
        i = idx[d]
        prev_d = cal[i - 1] if i > 0 else None
        rf_d = 0.0
        if prev_d and prev_d in rf_close and d in rf_close:
            rf_d = rf_close[d] / rf_close[prev_d] - 1.0
        out.append({"date": d, "r": statistics.fmean(per_day[d]) - rf_d,
                    "n": len(per_day[d])})
    return out


# ---------------------------------------------------------------------------
# control pool + label permutation (section 8)
# ---------------------------------------------------------------------------

def control_pool(recs, t3_auct, target_syms, rf_close, model, cal, idx):
    by_day = defaultdict(dict)
    for key, rec in t3_auct.items():
        sym, d = key.split("|")
        if "c" in rec:
            by_day[d][sym] = rec["c"]
    entry = float(model.entry_spread_and_slippage_fraction())
    exit_ = float(model.exit_spread_and_slippage_fraction())
    pools = []
    for r in recs:
        a, b = by_day.get(r["t0"], {}), by_day.get(r["t_last"], {})
        rf = rf_factor(rf_close, cal, idx, r["t0"], r["cash_date"])
        cand = []
        for sym, p0 in a.items():
            if sym in target_syms or p0 <= MIN_PRICE:
                continue
            p1 = b.get(sym)
            if not p1:
                continue
            ratio = p1 / p0
            cand.append(ratio - 1.0 - entry - exit_ * ratio
                        - float(SEC31_BP) * 1e-4 * ratio - float(TAF_PER_SHARE) / p0 - rf)
        pools.append(cand)
    return pools


def permutation(values, pools, trials=10_000, seed=SEED):
    obs = statistics.fmean(values)
    usable = [(v, p) for v, p in zip(values, pools) if p]
    if len(usable) < len(values) * 0.8:
        raise Refused(f"only {len(usable)}/{len(values)} events have a control pool; "
                      "a permutation on a subset is a different test")
    rng = random.Random(seed)
    vals = [p for _, p in usable]
    ge = 0
    draws = []
    for _ in range(trials):
        m = statistics.fmean(v[rng.randrange(len(v))] for v in vals)
        draws.append(m)
        if m >= obs:
            ge += 1
    draws.sort()
    return {"observed_mean_excess": obs, "p_right_tail": (ge + 1) / (trials + 1),
            "trials": trials, "seed": seed, "events_with_pool": len(usable),
            "median_pool_size": statistics.median(len(v) for v in vals),
            "null_p50": draws[trials // 2], "null_p95": draws[int(0.95 * (trials - 1))]}


# ---------------------------------------------------------------------------
# measured half-spread on the traded names (section 6)
# ---------------------------------------------------------------------------

def measure_target_half_spread(recs, tag):
    want = defaultdict(set)
    for r in recs:
        want[r["t0"]].add(r["symbol"])
    days = sorted(want)

    def build():
        def work(day):
            off = t3._ny_utc_offset(day)
            start = f"{day}T{15 + off:02d}:59:59Z"
            end = f"{day}T{16 + off:02d}:00:00Z"
            vals = []
            for chunk in t3.chunks(sorted(want[day]), 100):
                per = defaultdict(list)
                try:
                    for block in t3.paged("/v2/stocks/quotes",
                                          {"symbols": ",".join(chunk), "start": start,
                                           "end": end, "limit": t3.PAGE, "feed": "sip"},
                                          "quotes"):
                        for sym, quotes in block.items():
                            for q in quotes:
                                bid, ask = q.get("bp"), q.get("ap")
                                if not bid or not ask or ask <= bid:
                                    continue
                                mid = 0.5 * (bid + ask)
                                v = (ask - bid) / (2 * mid) * 1e4
                                if v < 1000:
                                    per[sym].append(v)
                except Refused:
                    continue
                for sym, xs in per.items():
                    xs.sort()
                    vals.append(xs[len(xs) // 2])
            return vals

        allv = []
        with ThreadPoolExecutor(max_workers=6) as pool:
            for got in pool.map(work, days):
                allv.extend(got)
        return allv

    allv = t11.cache_json(f"half_spread_{tag}", build)
    if not allv:
        raise Refused("no target quotes sampled; refusing to assume a spread")
    allv = sorted(allv)
    return {
        "median_half_spread_bp": allv[len(allv) // 2],
        "p25": allv[len(allv) // 4], "p75": allv[3 * len(allv) // 4],
        "p95": allv[int(0.95 * (len(allv) - 1))],
        "mean": sum(allv) / len(allv), "n_symbol_days": len(allv), "sample_days": len(days),
        "window": "[15:59:59, 16:00:00) ET -- the T3 instrument and its declared deviation",
    }


# ---------------------------------------------------------------------------
# the break analysis (section 7)
# ---------------------------------------------------------------------------

def break_analysis(excess, rf_mean, seed=SEED, draws=10_000):
    mu = statistics.fmean(excess)
    bstar = {}
    for L in BREAK_LOSSES:
        denom = mu + rf_mean - L
        bstar[f"{L:.2f}"] = (mu / denom) if denom > 0 else None
    rng = random.Random(seed)
    n = len(excess)
    grid = {}
    for b in BREAK_RATES:
        for L in (PRIMARY_BREAK_LOSS,):
            means = []
            for _ in range(draws):
                tot = 0.0
                for _ in range(n):
                    if rng.random() < b:
                        tot += L - rf_mean
                    else:
                        tot += excess[rng.randrange(n)]
                means.append(tot / n)
            means.sort()
            grid[f"b={b:.2f}"] = {
                "mean": statistics.fmean(means),
                "p05_VaR": means[int(0.05 * (draws - 1))],
                "CVaR05": statistics.fmean(means[:max(1, int(0.05 * draws))]),
                "p_book_loses": sum(1 for m in means if m < 0) / draws,
            }
    m = S.moments(excess)
    tail = sorted(excess)
    return {
        "break_even_rate_bstar_by_loss": bstar,
        "primary_bstar": bstar[f"{PRIMARY_BREAK_LOSS:.2f}"],
        "gate_bstar_gt": BREAK_GATE_BSTAR,
        "monte_carlo_primary_L": PRIMARY_BREAK_LOSS,
        "monte_carlo": grid,
        "empirical_distribution": {
            "n": m["n"], "mean": m["mean"], "sd": m["sd"], "skew": m["skew"],
            "kurtosis_non_excess": m["kurtosis"],
            "min": tail[0], "p01": tail[int(0.01 * (len(tail) - 1))],
            "p05": tail[int(0.05 * (len(tail) - 1))],
            "median": statistics.median(tail),
            "p95": tail[int(0.95 * (len(tail) - 1))], "max": tail[-1],
            "n_losing": sum(1 for x in excess if x < 0),
            "share_losing": sum(1 for x in excess if x < 0) / len(excess),
        },
    }


# ---------------------------------------------------------------------------
# reporting helpers
# ---------------------------------------------------------------------------

def describe_events(excess, label):
    if len(excess) < 2:
        return {"label": label, "n": len(excess), "mean": None, "t": None,
                "note": "fewer than 2 observations; no moment is defined"}
    m = S.moments(excess)
    n = m["n"]
    se = m["sd"] / math.sqrt(n) if n > 1 else float("nan")
    return {"label": label, "n": n, "mean": m["mean"], "sd": m["sd"],
            "t": (m["mean"] / se) if se else None,
            "ci95": [m["mean"] - 1.96 * se, m["mean"] + 1.96 * se],
            "skew": m["skew"], "kurtosis_non_excess": m["kurtosis"]}


def describe_series(series, label):
    r = [x["r"] for x in series]
    m = S.moments(r)
    eq, v = [1.0], 1.0
    for x in r:
        v *= (1 + x)
        eq.append(v)
    dd = S.max_drawdown(eq)
    se = m["sd"] / math.sqrt(m["n"]) if m["n"] > 1 else float("nan")
    return {"label": label, "sessions": m["n"], "mean_per_session": m["mean"],
            "sd_per_session": m["sd"], "t": (m["mean"] / se) if se else None,
            "sharpe_per_observation": (m["mean"] / m["sd"]) if m["sd"] else None,
            "annualised_sharpe": S.annualised_sharpe(r, 252),
            "annualised_return": (v ** (252 / max(1, m["n"])) - 1) if v > 0 else None,
            "max_drawdown": dd, "skew": m["skew"], "kurtosis_non_excess": m["kurtosis"]}


def main():
    assert_frozen()
    cal = [r["date"] for r in t3.calendar() if r["date"] >= "2016-01-01"]
    idx = {d: i for i, d in enumerate(cal)}

    events_all = [e for e in t11.cash_merger_events() if t11.is_ticker_shaped(e)]
    syms = sorted({e["acquiree_symbol"] for e in events_all})
    bars = t11.daily_bars(syms + [RF, MARKET])
    auct = t11.target_auctions(syms + [RF, MARKET])
    rf_close = adjusted_bars([RF, MARKET], "adjusted_bars")[RF]
    t3_auct = t3.auctions(sorted({s for m in t3.build_universe(500).values() for s in m}))
    target_syms = set(syms)

    out = {"prereg_sha256": PREREG_SHA, "horizons": list(HORIZONS), "trials": TRIALS,
           "seed": SEED}

    # ---- events per horizon, both windows
    by_h = {}
    for H in HORIZONS:
        kept, capped, funnel = build_events(H, bars, auct, cal, idx)
        by_h[H] = {"kept": kept, "capped": capped, "funnel": funnel}
    out["funnel_by_horizon"] = {str(H): by_h[H]["funnel"] for H in HORIZONS}
    out["discount_cap_dropped"] = {
        str(H): {
            "n": len(by_h[H]["capped"]),
            "n_design": sum(1 for r in by_h[H]["capped"] if r["period"] == "design"),
            "n_test": sum(1 for r in by_h[H]["capped"] if r["period"] == "test"),
            "mean_gross_spread_they_would_have_added":
                statistics.fmean([r["gross_spread"] for r in by_h[H]["capped"]])
                if by_h[H]["capped"] else None,
        } for H in HORIZONS}

    # ---- half-spread, measured per period on the traded names
    design_recs_all = [r for H in HORIZONS for r in by_h[H]["kept"] if r["period"] == "design"]
    test_recs_all = [r for H in HORIZONS for r in by_h[H]["kept"] if r["period"] == "test"]
    hs_design = measure_target_half_spread(design_recs_all, "design")
    hs_test = measure_target_half_spread(test_recs_all, "test")
    out["half_spread"] = {"design": hs_design, "test": hs_test}
    model_design = cost_model(hs_design["median_half_spread_bp"])
    model_test = cost_model(hs_test["median_half_spread_bp"])
    out["cost_model_test"] = model_test.to_report()

    # ---- DESIGN WINDOW: select H (the one fitted quantity)
    design = {}
    for H in HORIZONS:
        recs = [r for r in by_h[H]["kept"] if r["period"] == "design"]
        if len(recs) < 2:
            design[str(H)] = {"n": len(recs), "t": None}
            continue
        ex = [net_excess(r, model_design, rf_close, cal, idx)[0] for r in recs]
        d = describe_events(ex, f"design H={H}")
        d["mean_calendar_days"] = statistics.fmean(r["calendar_days"] for r in recs)
        design[str(H)] = d
    out["design"] = design
    scored = [(design[str(H)]["t"], -H, H) for H in HORIZONS
              if design[str(H)].get("t") is not None]
    if not scored:
        raise Refused("no design-window horizon produced a t-statistic; cannot select H")
    PRIMARY_H = max(scored)[2]
    out["primary_H_selected_on_design"] = PRIMARY_H

    # ---- HELD OUT: run once
    test = {}
    per_h_series = {}
    for H in HORIZONS:
        recs = [r for r in by_h[H]["kept"] if r["period"] == "test"]
        ex = [net_excess(r, model_test, rf_close, cal, idx)[0] for r in recs]
        d = describe_events(ex, f"test H={H}")
        d["mean_calendar_days"] = statistics.fmean(r["calendar_days"] for r in recs)
        d["annualised_mean_excess"] = d["mean"] * 365.0 / d["mean_calendar_days"]
        d["mean_gross_spread"] = statistics.fmean(r["gross_spread"] for r in recs)
        series = daily_series(recs, model_test, bars, auct, rf_close, cal, idx)
        per_h_series[H] = series
        d["series"] = describe_series(series, f"test H={H}")
        test[str(H)] = d
    out["test"] = {k: {kk: vv for kk, vv in v.items()} for k, v in test.items()}

    prim_recs = [r for r in by_h[PRIMARY_H]["kept"] if r["period"] == "test"]
    prim_ex = [net_excess(r, model_test, rf_close, cal, idx)[0] for r in prim_recs]
    prim_rf = statistics.fmean(net_excess(r, model_test, rf_close, cal, idx)[3]
                               for r in prim_recs)

    # ---- gate 3: DSR on the held-out daily portfolio net-excess series
    trial_sharpes = [test[str(H)]["series"]["sharpe_per_observation"] for H in HORIZONS]
    sv = S.sharpe_variance_from_trials(trial_sharpes)
    prim_series = [x["r"] for x in per_h_series[PRIMARY_H]]
    out["dsr"] = S.deflated_sharpe(prim_series, trials=TRIALS, sharpe_variance=sv)
    out["dsr_trials_12"] = S.deflated_sharpe(prim_series, trials=12, sharpe_variance=sv)
    out["trial_sharpes"] = dict(zip(map(str, HORIZONS), trial_sharpes))

    # ---- gate 2: event-label permutation against the T3 control pool
    pools = control_pool(prim_recs, t3_auct, target_syms, rf_close, model_test, cal, idx)
    out["permutation"] = permutation(prim_ex, pools)

    # ---- gate 4: the break analysis
    out["break_analysis"] = break_analysis(prim_ex, prim_rf)

    # ---- gate 0: power
    design_recs = [r for r in by_h[PRIMARY_H]["kept"] if r["period"] == "design"]
    design_ex = [net_excess(r, model_design, rf_close, cal, idx)[0] for r in design_recs]
    sigma = statistics.stdev(design_ex) if len(design_ex) > 1 else None
    mean_days = statistics.fmean(r["calendar_days"] for r in prim_recs)
    benchmark = LIT_EXCESS_ANNUAL * mean_days / 365.0
    mde = 2.80 * sigma / math.sqrt(len(prim_ex)) if sigma else None
    out["power"] = {
        "sigma_design": sigma, "n_design": len(design_ex), "n_test": len(prim_ex),
        "mean_calendar_days": mean_days, "benchmark_effect": benchmark, "mde": mde,
        "passes": (mde is not None and mde <= benchmark),
        "n_required": (int(math.ceil((2.80 * sigma / benchmark) ** 2)) if sigma else None),
    }

    # ---- stress ladder + zero-cost diagnostic
    h = hs_test["median_half_spread_bp"]
    ladder = {}
    for mult in (0.0, 0.5, 1.0, 2.0, 4.0):
        m2 = cost_model(h * mult)
        ex2 = [net_excess(r, m2, rf_close, cal, idx)[0] for r in prim_recs]
        ladder[f"{mult}x"] = describe_events(ex2, f"half-spread {mult}x")
    zero = [r["gross_spread"] - rf_factor(rf_close, cal, idx, r["t0"], r["cash_date"])
            for r in prim_recs]
    ladder["frictionless_B19P"] = describe_events(zero, "every cost zero, regulatory included")
    out["stress_ladder"] = ladder

    # ---- SPY paired control, reported
    spy_auc = {k.split("|")[1]: v["c"] for k, v in auct.items()
               if k.startswith(f"{MARKET}|") and "c" in v}
    paired = []
    for r, e in zip(prim_recs, prim_ex):
        a, b = spy_auc.get(r["t0"]), spy_auc.get(r["t_last"])
        if a and b:
            rf = rf_factor(rf_close, cal, idx, r["t0"], r["cash_date"])
            paired.append(e - (b / a - 1.0 - rf))
    out["paired_vs_spy"] = describe_events(paired, "target net excess minus SPY excess")

    # ---- year by year
    yby = defaultdict(list)
    for r, e in zip(prim_recs, prim_ex):
        yby[r["effective_date"][:4]].append(e)
    out["year_by_year"] = {y: describe_events(v, y) for y, v in sorted(yby.items())
                           if len(v) > 1}

    # ---- symmetric-cap robustness
    sym_recs = [r for r in prim_recs if abs(r["gross_spread"]) <= DISCOUNT_CAP]
    out["symmetric_cap_robustness"] = describe_events(
        [net_excess(r, model_test, rf_close, cal, idx)[0] for r in sym_recs],
        "|gross spread| <= 20%")

    # ---- verdict
    g0 = out["power"]["passes"]
    g1 = describe_events(prim_ex, "primary")["mean"] > 0
    g2 = out["permutation"]["p_right_tail"] < 0.05
    g3 = out["dsr"]["dsr"] >= 0.95
    bstar = out["break_analysis"]["primary_bstar"]
    g4 = bstar is not None and bstar > BREAK_GATE_BSTAR
    out["gates"] = {"power": g0, "net_mean_positive": g1, "permutation_p_lt_0.05": g2,
                    "dsr_ge_0.95": g3, "break_bstar_gt_10pct": g4}
    if not g0:
        out["verdict"] = "DEAD-BY-INSUFFICIENT-POWER"
    elif all((g1, g2, g3, g4)):
        out["verdict"] = "SURVIVES-CONDITIONAL-ON-ORACLES"
    else:
        out["verdict"] = "DEAD"
    out["primary"] = describe_events(prim_ex, f"HELD OUT, H={PRIMARY_H}, primary cost rung")
    out["primary"]["mean_calendar_days"] = mean_days
    out["primary"]["annualised"] = out["primary"]["mean"] * 365.0 / mean_days

    path = ROOT / "research" / "trading_bot" / "T11_HELDOUT_RESULT.json"
    path.write_text(json.dumps(out, indent=2, default=float) + "\n")
    print(json.dumps({k: out[k] for k in
                      ("primary_H_selected_on_design", "primary", "gates", "verdict",
                       "power", "permutation", "dsr")}, indent=2, default=float))
    print("wrote", path)


if __name__ == "__main__":
    main()
