#!/usr/bin/env python3
"""T9 -- evaluation of shortlist candidate #4: spin-off forced-selling drift.

Frozen rule: research/trading_bot/T9_PREREGISTRATION.md
             sha256 cd36949cce70cce4fabe1a268b549a0e99a6518e1be3f2e41a3f4fcf16715510

This module refuses to run if that file's hash has changed. Statistics come from the T2 harness
(`scripts/trading_bot/stats.py`) and the cost model from `scripts/trading_bot/costs.py` -- the
T6-corrected PER-SIDE model. Neither is reimplemented here.

There is no fitted parameter anywhere in this file. The three holding periods are the three
declared in section 3 of the pre-registration and nothing selects among them.
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
from fractions import Fraction

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.t3_pressure_reversal as t3                                        # noqa: E402
import scripts.t9_spinoff_drift as t9                                            # noqa: E402
from scripts.trading_bot import costs as C                                       # noqa: E402
from scripts.trading_bot import stats as S                                       # noqa: E402
from scripts.trading_bot.frozen import Refused                                   # noqa: E402

PREREG = ROOT / "research" / "trading_bot" / "T9_PREREGISTRATION.md"
PREREG_SHA = "cd36949cce70cce4fabe1a268b549a0e99a6518e1be3f2e41a3f4fcf16715510"

DESIGN_END, TEST_START, END = t3.DESIGN_END, t3.TEST_START, t3.END
HEDGE = "SPY"

HORIZONS = (21, 60, 126)          # section 3, the entire trial space
PRIMARY_H = 60
TRIALS = 3
SEED = 20260817
MIN_PRICE = 5.0
MIN_DOLLAR_VOL = 1_000_000.0
MAX_ENTRY_SEARCH = 5
CONTROL_K = 5

SEC31_BP = Fraction(278, 1000)               # 0.278 bp of sale notional
TAF_PER_SHARE = Fraction(166, 1_000_000_000)  # $0.000166/share sold
BORROW = C.measured_borrow_annual("etb_general_collateral")


def assert_frozen():
    got = hashlib.sha256(PREREG.read_bytes()).hexdigest()
    if got != PREREG_SHA:
        raise Refused(
            f"pre-registration hash mismatch: expected {PREREG_SHA}, on disk {got}. "
            "The frozen rule changed; this run has no standing."
        )


# ---------------------------------------------------------------------------
# panel
# ---------------------------------------------------------------------------

def build_events(bars, auct, cal, idx):
    """One record per surviving spin-off event, section 4 exclusions applied once, here."""
    raw = [e for e in t9.spinoff_events() if t9.is_tradeable_stub(e)]
    # exclusion 6/7: new == source is a restatement; only the earliest ex_date per stub
    seen = {}
    dropped = defaultdict(int)
    for e in sorted(raw, key=lambda x: x["ex_date"]):
        if e["new_symbol"] == e.get("source_symbol"):
            dropped["new_equals_source"] += 1
            continue
        if e["new_symbol"] in seen:
            dropped["duplicate_stub_later_ex_date"] += 1
            continue
        seen[e["new_symbol"]] = e

    out = []
    for e in seen.values():
        sym, ex = e["new_symbol"], e["ex_date"]
        b = bars.get(sym, {})
        i = idx.get(ex)
        if i is None:
            dropped["ex_date_not_a_trading_day"] += 1
            continue
        t0 = None
        for d in cal[i:i + MAX_ENTRY_SEARCH]:
            if d in b and auct.get(f"{sym}|{d}", {}).get("c"):
                t0 = d
                break
        if t0 is None:
            dropped["no_entry_price_within_5_sessions"] += 1
            continue
        p0 = auct[f"{sym}|{t0}"]["c"]
        bar0 = b[t0]
        if p0 <= MIN_PRICE:
            dropped["entry_price_le_5"] += 1
            continue
        if (bar0.get("vw") or bar0["c"]) * bar0["v"] <= MIN_DOLLAR_VOL:
            dropped["entry_dollar_volume_le_1m"] += 1
            continue
        out.append({"stub": sym, "parent": e.get("source_symbol"), "ex_date": ex, "t0": t0,
                    "p0": p0, "period": "design" if ex <= DESIGN_END else "test"})
    return out, dict(dropped)


def price_path(sym, t0, t1, cal, idx, bars, auct):
    """[(date, price)] from the entry auction print to the exit price, section 5.

    Intermediate marks are raw daily closes; the two endpoints are official auction prints, so
    the compounded path equals the event's own total return by construction. A missing session
    is forward-filled (a zero-return day), never dropped -- dropping it would shorten the holding
    period silently.
    """
    i0, i1 = idx[t0], idx[t1]
    b = bars.get(sym, {})
    path = [(t0, auct[f"{sym}|{t0}"]["c"])]
    last = path[0][1]
    for d in cal[i0 + 1:i1]:
        if d in b:
            last = b[d]["c"]
        path.append((d, last))
    end = auct.get(f"{sym}|{t1}", {}).get("c") or (b.get(t1) or {}).get("c")
    if end is None:                      # terminal price rule: last print available
        avail = [d for d in cal[i0:i1] if d in b]
        if not avail:
            return None, None
        d = avail[-1]
        end = auct.get(f"{sym}|{d}", {}).get("c") or b[d]["c"]
        path = [p for p in path if p[0] <= d]
        path.append((d, end))
        return path, d
    path.append((t1, end))
    return path, t1


def run_horizon(events, H, cal, idx, bars, auct, half_spread_bp, spy_half_spread_bp):
    """Per-event records and the daily portfolio series, at holding period H. No fitting."""
    recs, dropped = [], defaultdict(int)
    for e in events:
        i0 = idx[e["t0"]]
        if i0 + H >= len(cal):
            dropped["window_extends_past_data_end"] += 1
            continue
        t1_nominal = cal[i0 + H]
        if not auct.get(f"{HEDGE}|{e['t0']}", {}).get("c") or \
           not auct.get(f"{HEDGE}|{t1_nominal}", {}).get("c"):
            dropped["spy_auction_missing"] += 1
            continue
        path, t1 = price_path(e["stub"], e["t0"], t1_nominal, cal, idx, bars, auct)
        if path is None or t1 == e["t0"]:
            dropped["no_usable_price_path"] += 1
            continue
        spy_path, _ = price_path(HEDGE, e["t0"], t1, cal, idx, bars, auct)
        if spy_path is None:
            dropped["no_spy_path"] += 1
            continue
        p0, p1 = path[0][1], path[-1][1]
        s0, s1 = spy_path[0][1], spy_path[-1][1]
        r_stub, r_spy = (p1 - p0) / p0, (s1 - s0) / s0
        gross = 0.5 * r_stub - 0.5 * r_spy
        cal_days = (
            __import__("datetime").date.fromisoformat(t1)
            - __import__("datetime").date.fromisoformat(e["t0"])).days
        recs.append({**e, "t1": t1, "p1": p1, "spy0": s0, "spy1": s1,
                     "r_stub": r_stub, "r_spy": r_spy, "gross": gross,
                     "calendar_days": cal_days, "path": path, "spy_path": spy_path,
                     "truncated": t1 != t1_nominal})
    return recs, dict(dropped)


def event_cost(rec, h_bp, spy_h_bp):
    """Total round-trip friction of one unit position, as a fraction of its own equity.

    PER SIDE throughout (the T6 correction): each of the four legs is charged its own
    half-spread, the two SALE legs carry the regulatory pass-through, and the SPY short carries
    borrow on calendar days.
    """
    w = 0.5
    h, sh = h_bp * 1e-4, spy_h_bp * 1e-4
    spread = w * h + w * h + w * sh + w * sh          # stub in/out, SPY in/out
    stub_sale_notional = w * (1.0 + rec["r_stub"])
    spy_sale_notional = w                              # the short SALE happens at entry
    sec31 = float(SEC31_BP) * 1e-4 * (stub_sale_notional + spy_sale_notional)
    taf = float(TAF_PER_SHARE) * (stub_sale_notional / rec["p1"] + spy_sale_notional / rec["spy0"])
    borrow = float(BORROW.value) * w * rec["calendar_days"] / 365.0
    return {"spread": spread, "sec31": sec31, "taf": taf, "borrow": borrow,
            "total": spread + sec31 + taf + borrow}


def daily_series(recs, h_bp, spy_h_bp, cal, idx):
    """Equal-weight book of unit positions; one observation per session it holds something."""
    active = defaultdict(list)
    for k, r in enumerate(recs):
        for d, _ in r["path"][1:]:
            active[d].append(k)
    entry_day, exit_day = defaultdict(list), defaultdict(list)
    for k, r in enumerate(recs):
        entry_day[r["t0"]].append(k)
        exit_day[r["t1"]].append(k)

    px = [{d: p for d, p in r["path"]} for r in recs]
    spx = [{d: p for d, p in r["spy_path"]} for r in recs]
    prev_of = {}
    for r in recs:
        for a, b in zip(r["path"], r["path"][1:]):
            prev_of[(id(r), b[0])] = a[0]

    days = sorted(active)
    out = []
    for d in days:
        ks = active[d]
        contrib = []
        for k in ks:
            r = recs[k]
            pd_ = prev_of[(id(r), d)]
            rs = (px[k][d] - px[k][pd_]) / px[k][pd_]
            rm = (spx[k][d] - spx[k][pd_]) / spx[k][pd_]
            contrib.append(0.5 * rs - 0.5 * rm)
        gross = sum(contrib) / len(contrib)
        i = idx[d]
        prev_cal = cal[i - 1]
        cd = (__import__("datetime").date.fromisoformat(d)
              - __import__("datetime").date.fromisoformat(prev_cal)).days
        borrow = float(BORROW.value) * 0.5 * cd / 365.0
        h, sh = h_bp * 1e-4, spy_h_bp * 1e-4
        cost = borrow
        for k in entry_day.get(d, []):
            if k in ks:
                cost += (0.5 * h + 0.5 * sh) / len(ks)
        for k in exit_day.get(d, []):
            if k in ks:
                r = recs[k]
                sale = 0.5 * (1 + r["r_stub"])
                reg = float(SEC31_BP) * 1e-4 * (sale + 0.5) + float(TAF_PER_SHARE) * (
                    sale / r["p1"] + 0.5 / r["spy0"])
                cost += (0.5 * h + 0.5 * sh + reg) / len(ks)
        out.append({"date": d, "gross": gross, "net": gross - cost, "n": len(ks)})
    return out


# ---------------------------------------------------------------------------
# controls and permutation
# ---------------------------------------------------------------------------

def control_pool(recs, t3_auct, stub_symbols, seed=SEED):
    """For each event: the market-adjusted GROSS excess of every eligible non-stub name.

    Eligible = has an official closing print on BOTH the event's t0 and t1, price > $5 on t0,
    and is not a spin-off stub. The pool is the T3 top-500-ADV union, so the $1 M dollar-volume
    floor of section 4 is satisfied by construction of that screen (it is a $20 M ADV screen).
    """
    by_day = defaultdict(dict)
    for key, rec in t3_auct.items():
        sym, d = key.split("|")
        if "c" in rec:
            by_day[d][sym] = rec["c"]
    pools = []
    for r in recs:
        a, b = by_day.get(r["t0"], {}), by_day.get(r["t1"], {})
        cand = []
        for sym, p0 in a.items():
            if sym in stub_symbols or sym == HEDGE or p0 <= MIN_PRICE:
                continue
            p1 = b.get(sym)
            if not p1:
                continue
            cand.append((sym, 0.5 * ((p1 - p0) / p0) - 0.5 * r["r_spy"]))
        pools.append(cand)
    return pools


def permutation(recs, pools, trials=10_000, seed=SEED):
    """Right-tail p on the mean per-event excess, replacing each stub by a control name."""
    obs = statistics.fmean(r["gross"] for r in recs)
    usable = [(r, p) for r, p in zip(recs, pools) if p]
    if len(usable) < len(recs) * 0.8:
        raise Refused(f"only {len(usable)}/{len(recs)} events have a control pool; "
                      "a permutation on a subset is a different test")
    rng = random.Random(seed)
    ge = 0
    vals = [[x[1] for x in p] for _, p in usable]
    for _ in range(trials):
        m = statistics.fmean(v[rng.randrange(len(v))] for v in vals)
        if m >= obs:
            ge += 1
    return {"observed_mean_excess": obs, "p_right_tail": (ge + 1) / (trials + 1),
            "trials": trials, "seed": seed, "events_with_pool": len(usable),
            "median_pool_size": statistics.median(len(v) for v in vals)}


# ---------------------------------------------------------------------------
# measured half-spread on the traded names (section 6)
# ---------------------------------------------------------------------------

def measure_stub_half_spread(recs):
    want = defaultdict(set)
    for r in recs:
        want[r["t0"]].add(r["stub"])
        want[r["t1"]].add(r["stub"])
    spy_days = sorted(want)

    def work(day):
        off = t3._ny_utc_offset(day)
        start = f"{day}T{15 + off:02d}:59:59Z"
        end = f"{day}T{16 + off:02d}:00:00Z"
        syms = sorted(want[day] | {HEDGE})
        stub_vals, spy_vals = [], []
        for chunk in t3.chunks(syms, 100):
            per = defaultdict(list)
            for block in t3.paged("/v2/stocks/quotes",
                                  {"symbols": ",".join(chunk), "start": start, "end": end,
                                   "limit": t3.PAGE, "feed": "sip"}, "quotes"):
                for sym, quotes in block.items():
                    for q in quotes:
                        bid, ask = q.get("bp"), q.get("ap")
                        if not bid or not ask or ask <= bid:
                            continue
                        mid = 0.5 * (bid + ask)
                        v = (ask - bid) / (2 * mid) * 1e4
                        if v < 1000:
                            per[sym].append(v)
            for sym, vals in per.items():
                vals.sort()
                (spy_vals if sym == HEDGE else stub_vals).append(vals[len(vals) // 2])
        return stub_vals, spy_vals

    stub_all, spy_all = [], []
    with ThreadPoolExecutor(max_workers=6) as pool:
        for a, b in pool.map(work, spy_days):
            stub_all.extend(a)
            spy_all.extend(b)
    if not stub_all:
        raise Refused("no stub quotes sampled; refusing to assume a spread")
    stub_all.sort()
    spy_all.sort()
    return {
        "stub_median_half_spread_bp": stub_all[len(stub_all) // 2],
        "stub_p25": stub_all[len(stub_all) // 4],
        "stub_p75": stub_all[3 * len(stub_all) // 4],
        "stub_p95": stub_all[int(0.95 * (len(stub_all) - 1))],
        "stub_mean": sum(stub_all) / len(stub_all),
        "stub_n_symbol_days": len(stub_all),
        "spy_median_half_spread_bp": (spy_all[len(spy_all) // 2] if spy_all else None),
        "spy_n_symbol_days": len(spy_all),
        "window": "[15:59:59, 16:00:00) ET -- the T3 instrument and its declared deviation",
    }


# ---------------------------------------------------------------------------
# reporting
# ---------------------------------------------------------------------------

def describe(net_events, series, label):
    n = len(net_events)
    out = {"n_events": n}
    if n >= 2:
        m = statistics.fmean(net_events)
        sd = statistics.stdev(net_events)
        out.update({"net_mean_per_event": m, "net_sd_per_event": sd,
                    "t_stat": m / (sd / math.sqrt(n)) if sd else None,
                    "ci95_low": m - 1.96 * sd / math.sqrt(n),
                    "ci95_high": m + 1.96 * sd / math.sqrt(n)})
    if series and len(series) >= 2:
        nets = [d["net"] for d in series]
        eq, v = [1.0], 1.0
        for r in nets:
            v *= (1 + r)
            eq.append(v)
        out.update({
            "n_sessions": len(nets),
            "net_daily_mean": statistics.fmean(nets),
            "net_annualised_sharpe": S.annualised_sharpe(nets, 252),
            "net_sharpe_per_observation": S.sharpe_per_observation(nets),
            "net_total_return": v - 1.0,
            "max_drawdown": S.max_drawdown(eq)["max_drawdown"],
            "mean_names_held": statistics.fmean(d["n"] for d in series),
            "t_stat_daily": (statistics.fmean(nets) /
                             (statistics.stdev(nets) / math.sqrt(len(nets)))
                             if statistics.stdev(nets) else None),
        })
    return {label: out}


def main():
    assert_frozen()
    cal = [r["date"] for r in t3.calendar() if r["date"] >= "2016-01-01"]
    idx = {d: i for i, d in enumerate(cal)}
    events_all = [e for e in t9.spinoff_events() if t9.is_tradeable_stub(e)]
    stub_symbols = {e["new_symbol"] for e in events_all}
    parents = {e["source_symbol"] for e in events_all if e.get("source_symbol")}
    bars = t9.daily_bars(sorted(stub_symbols | parents | {HEDGE}))
    auct = t9.stub_auctions(sorted(stub_symbols | {HEDGE}))

    events, drop_pre = build_events(bars, auct, cal, idx)
    print(f"events after section-4 exclusions: {len(events)}  dropped: {drop_pre}", flush=True)

    # ---- friction, measured on the traded names, primary horizon's dates
    prim_recs, drop_h = run_horizon(events, PRIMARY_H, cal, idx, bars, auct, 0.0, 0.0)
    hs = measure_stub_half_spread(prim_recs)
    h = hs["stub_median_half_spread_bp"]
    sh = hs["spy_median_half_spread_bp"] or 0.13
    print(f"measured stub half-spread: {h:.2f} bp (n={hs['stub_n_symbol_days']}), "
          f"SPY {sh:.3f} bp", flush=True)

    report = {
        "prereg_sha256": PREREG_SHA,
        "generated_utc": __import__("datetime").datetime.utcnow().isoformat() + "Z",
        "events_after_exclusions": len(events),
        "exclusion_counts": drop_pre,
        "friction_measured": hs,
        "cost_model": {
            "per_side": True,
            "entry_half_spread_bp": h, "exit_half_spread_bp": h,
            "spy_half_spread_bp": sh,
            "entry_extra_slippage_bp": 0.0, "exit_extra_slippage_bp": 0.0,
            "sec31_bp_of_sale_notional": float(SEC31_BP),
            "taf_per_share_usd": float(TAF_PER_SHARE),
            "borrow_annual": float(BORROW.value), "borrow_source": BORROW.source,
            "commission": 0.0,
        },
        "horizons": {},
    }

    trial_sharpes_test = []
    for H in HORIZONS:
        recs, dh = run_horizon(events, H, cal, idx, bars, auct, h, sh)
        block = {"dropped": dh, "n_events": len(recs)}
        for period in ("design", "test", "all"):
            sub = [r for r in recs if period == "all" or r["period"] == period]
            if not sub:
                continue
            nets = [r["gross"] - event_cost(r, h, sh)["total"] for r in sub]
            grosses = [r["gross"] for r in sub]
            ser = daily_series(sub, h, sh, cal, idx)
            block.update(describe(nets, ser, period))
            block[period]["gross_mean_per_event"] = statistics.fmean(grosses)
            block[period]["mean_cost_per_event"] = statistics.fmean(
                event_cost(r, h, sh)["total"] for r in sub)
            block[period]["cost_breakdown_mean"] = {
                k: statistics.fmean(event_cost(r, h, sh)[k] for r in sub)
                for k in ("spread", "sec31", "taf", "borrow")}
            block[period]["n_truncated_by_terminal_price_rule"] = sum(
                1 for r in sub if r["truncated"])
            if period == "test":
                trial_sharpes_test.append(S.sharpe_per_observation([d["net"] for d in ser]))
                block["test_series"] = ser
                block["test_recs"] = [
                    {k: r[k] for k in ("stub", "parent", "ex_date", "t0", "t1",
                                       "r_stub", "r_spy", "gross", "calendar_days",
                                       "truncated")} for r in recs if r["period"] == "test"]
        report["horizons"][str(H)] = block

    # ---- POWER GATE (section 7), design-window sigma at the primary horizon
    prim = report["horizons"][str(PRIMARY_H)]
    sigma_design = prim.get("design", {}).get("net_sd_per_event")
    n_test = prim.get("test", {}).get("n_events", 0)
    sigma_used, sigma_basis = sigma_design, "design window 2016-2021 only (section 7 step 1)"
    if not sigma_design or prim["design"]["n_events"] < 3:
        raise Refused("design window has too few events to estimate sigma; the power gate "
                      "cannot be evaluated and the pre-registration requires it")
    mde = 2.80 * sigma_used / math.sqrt(n_test) if n_test else None
    benchmark = 0.024 * (PRIMARY_H / 252.0) / (60 / 252.0)   # +10%/yr over 60 sessions = 2.4%
    n_required = (2.80 * sigma_used / benchmark) ** 2
    per_year = n_test / ((__import__("datetime").date.fromisoformat(END)
                          - __import__("datetime").date.fromisoformat(TEST_START)).days / 365.25)
    report["power_gate"] = {
        "sigma_per_event_design": sigma_used,
        "sigma_basis": sigma_basis,
        "n_design_events": prim["design"]["n_events"],
        "n_test_events": n_test,
        "mde_80pct_power": mde,
        "benchmark_effect_cusatis_10pct_per_year_over_H": benchmark,
        "passes": bool(mde is not None and mde <= benchmark),
        "n_required_for_benchmark": n_required,
        "events_per_year_observed": per_year,
        "years_of_prospective_collection_required": n_required / per_year if per_year else None,
    }

    # ---- DSR on the held-out daily portfolio series, trials = 3 (section 8)
    test_ser = [d["net"] for d in prim["test_series"]]
    sv = S.sharpe_variance_from_trials(trial_sharpes_test)
    report["dsr"] = {
        "trials_3": S.deflated_sharpe(test_ser, trials=TRIALS, sharpe_variance=sv),
        "trials_12": S.deflated_sharpe(test_ser, trials=12, sharpe_variance=sv),
        "trial_sharpes_per_observation": trial_sharpes_test,
        "sharpe_variance": sv,
    }

    # ---- event-label permutation on the held-out cross-section
    t3_auct = t3.auctions(sorted({s for syms in t3.build_universe(500).values() for s in syms}))
    test_recs = [r for r in run_horizon(events, PRIMARY_H, cal, idx, bars, auct, h, sh)[0]
                 if r["period"] == "test"]
    pools = control_pool(test_recs, t3_auct, stub_symbols)
    report["permutation"] = permutation(test_recs, pools)
    report["control_basket"] = {
        "mean_control_excess_per_event": statistics.fmean(
            statistics.fmean(x[1] for x in random.Random(SEED).sample(p, min(CONTROL_K, len(p))))
            for p in pools if p),
        "k_per_event": CONTROL_K, "seed": SEED,
    }

    # ---- stress ladder + zero-cost diagnostic (section 6)
    ladder = {}
    for name, mult in (("0", 0.0), ("0.5h", 0.5), ("h", 1.0), ("2h", 2.0), ("4h", 4.0)):
        nets = [r["gross"] - event_cost(r, h * mult, sh * mult)["total"] for r in test_recs]
        ladder[name] = {"net_mean_per_event": statistics.fmean(nets),
                        "t_stat": statistics.fmean(nets) /
                        (statistics.stdev(nets) / math.sqrt(len(nets)))}
    ladder["frictionless_B19P"] = {
        "net_mean_per_event": statistics.fmean(r["gross"] for r in test_recs),
        "t_stat": statistics.fmean(r["gross"] for r in test_recs) /
        (statistics.stdev([r["gross"] for r in test_recs]) / math.sqrt(len(test_recs)))}
    report["stress_ladder_heldout"] = ladder

    by_year = defaultdict(list)
    for r in test_recs:
        by_year[r["t0"][:4]].append(r["gross"] - event_cost(r, h, sh)["total"])
    report["heldout_by_year"] = {y: {"n": len(v), "net_mean_per_event": statistics.fmean(v)}
                                 for y, v in sorted(by_year.items())}

    # ---- verdict
    pg = report["power_gate"]
    prim_test = prim["test"]
    gates = {
        "power_gate_passes": pg["passes"],
        "net_mean_positive": prim_test["net_mean_per_event"] > 0,
        "permutation_p_lt_0p05": report["permutation"]["p_right_tail"] < 0.05,
        "dsr_ge_0p95": report["dsr"]["trials_3"]["dsr"] >= 0.95,
    }
    report["gates"] = gates
    report["verdict"] = ("SURVIVES" if all(gates.values())
                         else ("DEAD-BY-INSUFFICIENT-POWER" if not pg["passes"] else "DEAD"))

    out = ROOT / "research" / "trading_bot" / "T9_HELDOUT_RESULT.json"
    slim = json.loads(json.dumps(report))
    for H in slim["horizons"]:
        slim["horizons"][H].pop("test_series", None)
    out.write_text(json.dumps(slim, indent=1))
    (ROOT / "research" / "trading_bot" / "T9_DIAGNOSTICS.json").write_text(json.dumps({
        "heldout_daily_series_primary": prim["test_series"],
        "heldout_events_primary": prim.get("test_recs", []),
    }, indent=1))
    print(json.dumps({k: v for k, v in slim.items()
                      if k in ("verdict", "gates", "power_gate", "dsr", "permutation",
                               "stress_ladder_heldout", "heldout_by_year", "friction_measured",
                               "events_after_exclusions", "exclusion_counts",
                               "control_basket")}, indent=1))
    for H in HORIZONS:
        b = slim["horizons"][str(H)]
        print(f"H={H}: design {b.get('design', {}).get('n_events')} events, "
              f"test {b.get('test', {}).get('n_events')} events, "
              f"test net mean {b.get('test', {}).get('net_mean_per_event')}, "
              f"t {b.get('test', {}).get('t_stat')}")


if __name__ == "__main__":
    main()
