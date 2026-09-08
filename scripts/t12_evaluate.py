#!/usr/bin/env python3
"""T12 -- the verdict for shortlist candidate #5: closed-end-fund discount mean reversion.

Frozen rule: research/trading_bot/T12_PREREGISTRATION.md
             sha256 d88663008a813064816f53cb8ac19c051d057a115560ebc9f41114186037bd3e

This script REFUSES to run unless that hash is on disk unchanged. Everything it can vary is one
of the six trials the pre-registration declares; nothing else is reachable.

Statistics come from the T2 harness (`scripts/trading_bot/stats.py`) and costs from the
T6-corrected `scripts/trading_bot/costs.py`. Neither is reimplemented here.
"""

from __future__ import annotations

import hashlib
import json
import math
import pathlib
import random
import statistics
import sys
from collections import defaultdict
from fractions import Fraction

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.t3_pressure_reversal as t3                                        # noqa: E402
import scripts.t12_cef_discount as t12                                           # noqa: E402
from scripts.trading_bot import costs as C                                       # noqa: E402
from scripts.trading_bot import stats as S                                       # noqa: E402
from scripts.trading_bot.frozen import Refused                                   # noqa: E402

OUT = ROOT / "research" / "trading_bot"
PREREG = OUT / "T12_PREREGISTRATION.md"
PREREG_SHA = "d88663008a813064816f53cb8ac19c051d057a115560ebc9f41114186037bd3e"

SPLIT = "2024-03-01"          # prereg section 2b
MIN_PRICE = 5.0               # prereg section 4 exclusion 3
DECILE = 0.10
TRIALS = [                    # prereg section 4 -- EXACTLY these six
    {"id": 1, "family": "S1", "L": 26, "H": 1},
    {"id": 2, "family": "S1", "L": 26, "H": 4},
    {"id": 3, "family": "S1", "L": 52, "H": 1},
    {"id": 4, "family": "S1", "L": 52, "H": 4, "primary": True},
    {"id": 5, "family": "S2", "L": None, "H": 1},
    {"id": 6, "family": "S2", "L": None, "H": 4},
]
WEEKS_PER_YEAR = 52
SEED = 20260817
PONTIFF_ANNUAL = 0.06         # prereg section 3b -- the declared benchmark effect

SEC31_BP = Fraction(278, 1000)              # 0.278 bp of SALE notional
TAF_MICROS_PER_SHARE = 166                  # $0.000166 per share sold


def assert_frozen():
    got = hashlib.sha256(PREREG.read_bytes()).hexdigest()
    if got != PREREG_SHA:
        raise Refused(
            f"pre-registration hash mismatch: {got} != {PREREG_SHA}. The frozen rule has "
            "changed since the freeze; refusing to produce a verdict against a moved target."
        )


# ---------------------------------------------------------------------------
# 1. the panel
# ---------------------------------------------------------------------------

def build_panel():
    """(grid dates, {date: {ticker: row}}, adjusted-bar closes) -- no return computed yet."""
    uni = t12.universe()
    tickers = sorted({r["Ticker"] for r in uni if r.get("Ticker")})
    hist = t12.all_histories(tickers, "5Y")

    by_date = defaultdict(dict)
    for tkr, rows in hist.items():
        for r in rows or []:
            if r["price"] and r["nav"] and r["discount"] is not None:
                by_date[r["date"]][tkr] = r

    # DATA HYGIENE, declared in the result as a post-freeze deviation and reported by count.
    # Six of the 249 raw dates carry 1-28 funds: five are US market holidays on which a
    # handful of sponsors published anyway (2025-04-18, 2025-07-04, 2026-04-03, 2026-06-19,
    # 2026-07-03) and one is the truncated final date (2026-08-14). This is EDGE_SHORTLIST
    # section 2f's own lesson -- a pinned sample must come from the trading calendar, not from
    # weekdays. The rule is structural (half the live universe must be quoted), it cannot be
    # tuned, and the dates it removes are listed.
    dropped = sorted(d for d in by_date if len(by_date[d]) < len(tickers) / 2)
    grid = sorted(d for d in by_date if d not in set(dropped))

    bars = adjusted_bars(tickers, grid[0], grid[-1])
    return grid, dict(by_date), bars, tickers, dropped


def adjusted_bars(tickers, start, end):
    """SIP daily bars, adjustment=all (split AND dividend adjusted).

    CEFConnect's price field is a raw close. CEFs distribute 7-8 %/yr, often monthly, and the
    widest-discount funds are disproportionately the highest distributors -- so a raw-price
    return series systematically understates the LONG leg. That is the CONSERVATIVE direction,
    which is why both are computed and both are reported; the adjusted series is primary
    because ignoring an 8 %/yr distribution is a known error rather than a choice.
    """
    def build():
        out = defaultdict(dict)
        for chunk in t3.chunks(tickers, 40):
            for block in t3.paged("/v2/stocks/bars",
                                  {"symbols": ",".join(chunk), "start": start, "end": end,
                                   "timeframe": "1Day", "adjustment": "all",
                                   "limit": t3.PAGE, "feed": "sip"}, "bars"):
                for sym, rows in block.items():
                    for r in rows:
                        out[sym][r["t"][:10]] = r["c"]
        return dict(out)
    return t12.cache_json("adjusted_bars", build)


# ---------------------------------------------------------------------------
# 2. signal, book, and the weekly gross series
# ---------------------------------------------------------------------------

def signal_at(panel, grid, k, cfg, tickers):
    """{ticker: signal} at grid index k. STRICTLY TRAILING (prereg section 4)."""
    date = grid[k]
    today = panel[date]
    out = {}
    for tkr, row in today.items():
        if row["price"] is None or row["price"] <= MIN_PRICE:
            continue
        d = row["discount"]
        if cfg["family"] == "S2":
            out[tkr] = d
            continue
        L = cfg["L"]
        if k < L:
            continue
        hist = [panel[grid[j]][tkr]["discount"] for j in range(k - L, k)
                if tkr in panel[grid[j]]]
        if len(hist) < L * 0.8:
            continue
        mu = statistics.fmean(hist)
        sd = statistics.pstdev(hist)
        if sd <= 0:
            continue
        out[tkr] = (d - mu) / sd
    return out


def deciles(sig):
    """Long the widest discount (most negative signal), short the narrowest."""
    if len(sig) < 20:
        return [], []
    order = sorted(sig, key=lambda t: sig[t])
    n = max(1, int(round(len(order) * DECILE)))
    return order[:n], order[-n:]


def weekly_returns(prices, grid):
    """{ticker: {k: r}} -- return from grid[k] to grid[k+1]. The FIRST arithmetic in this file."""
    out = defaultdict(dict)
    for tkr, series in prices.items():
        for k in range(len(grid) - 1):
            a, b = series.get(grid[k]), series.get(grid[k + 1])
            if a and b and a > 0:
                out[tkr][k] = b / a - 1.0
    return out


def run_config(cfg, panel, grid, rets, cost_model, *, k_lo, k_hi):
    """The book, its weekly gross/net series, turnover, and the tranche record.

    Rebalance at grid index k; the signal uses data up to and including k; the position is held
    over the weekly returns starting at k+1 (prereg section 9 -- act on the FOLLOWING week's
    price, never the same day's).
    """
    H = cfg["H"]
    start = max(k_lo, cfg["L"] or 0)
    held = {}
    weekly, tranches = [], []
    entry_sp = cost_model.entry_spread_and_slippage_fraction()
    exit_sp = cost_model.exit_spread_and_slippage_fraction()
    borrow = cost_model.borrow_annual.value

    k = start
    while k + 1 + H <= k_hi:
        sig = signal_at(panel, grid, k, cfg, None)
        lo, hi = deciles(sig)
        if not lo or not hi:
            k += H
            continue
        target = {}
        for t in lo:
            target[t] = Fraction(1, 2) / len(lo)
        for t in hi:
            target[t] = -Fraction(1, 2) / len(hi)

        # ---- friction on the rebalance, PER SIDE (T6) ----
        names = set(target) | set(held)
        cost = Fraction(0)
        sale_notional = Fraction(0)
        traded_total = Fraction(0)
        for t in names:
            prev, tgt = held.get(t, Fraction(0)), target.get(t, Fraction(0))
            e, x = C.split_turnover(prev, tgt)
            if e == 0 and x == 0:
                continue
            traded_total += e + x
            cost += e * entry_sp + x * exit_sp
            # a SALE is: closing a long, or opening a short
            if prev > 0:
                sale_notional += min(prev, prev - min(prev, max(tgt, Fraction(0))))
            if tgt < 0:
                sale_notional += (-tgt) - min(-tgt, max(-prev, Fraction(0)))
        cost += sale_notional * SEC31_BP * C.BP
        # FINRA TAF, per share sold: shares = notional/price, so charge = TAF/price * notional
        px = statistics.fmean([panel[grid[k]][t]["price"] for t in names
                               if t in panel[grid[k]]] or [10.0])
        cost += sale_notional * Fraction(TAF_MICROS_PER_SHARE) / Fraction(int(px * 1e6))

        held = target
        # ---- the holding period ----
        for j in range(k + 1, k + 1 + H):
            gross = 0.0
            for t, w in held.items():
                r = rets.get(t, {}).get(j)
                if r is None:
                    continue
                gross += float(w) * r
            days = _days(grid[j], grid[j + 1]) if j + 1 < len(grid) else 7
            carry = float(borrow) * (Fraction(1, 2)) * days / 365
            c = float(cost) if j == k + 1 else 0.0
            weekly.append({"k": j, "date": grid[j], "gross": gross,
                           "cost": c + carry, "net": gross - c - carry})
        tranches.append({"k": k, "date": grid[k], "n_long": len(lo), "n_short": len(hi),
                         "turnover": float(traded_total), "cost_bp": float(cost) * 1e4})
        k += H
    return weekly, tranches


def _days(a, b):
    import datetime as dt
    return (dt.date.fromisoformat(b) - dt.date.fromisoformat(a)).days


# ---------------------------------------------------------------------------
# 3. cost models
# ---------------------------------------------------------------------------

def cef_cost_model(half_spread_bp, extra_bp=0):
    fric = json.loads((OUT / "T12_FRICTION_CENSUS.json").read_text())
    m = fric["measured_quoted_half_spread"]
    src = (
        f"T12 first-party measurement: median quoted half-spread {m['median_half_spread_bp']:.3f} "
        f"bp over {m['n_symbol_days']} CEF symbol-days, SIP quotes in {m['window']} "
        f"(p75 {m['p75']:.2f}, p90 {m['p90']:.2f}, p95 {m['p95']:.2f}, max {m['max']:.1f} bp). "
        "NOT the auction rail: costs.measured_auction_leg refuses for CEFs and EDGE_SHORTLIST "
        "section 2e measured CEF closing auctions clearing $0.0-0.3 M, so every leg of this "
        "candidate crosses a continuous spread."
    )
    comp = lambda n, v, p, s: C.CostComponent(n, Fraction(str(v)), "bp of notional", p, s)  # noqa
    return C.CostModel(
        entry_half_spread=comp("entry_half_spread", half_spread_bp,
                               C.SlippageProvenance.MEASURED_B22B if False else
                               C.SlippageProvenance.PUBLISHED_ACADEMIC_MEASUREMENT, src),
        exit_half_spread=comp("exit_half_spread", half_spread_bp,
                              C.SlippageProvenance.PUBLISHED_ACADEMIC_MEASUREMENT,
                              src + " Charged to the EXIT leg in its own component (T6)."),
        entry_extra_slippage=comp("entry_extra_slippage", extra_bp,
                                  C.SlippageProvenance.STRESS_LADDER,
                                  "NOT MEASURED for CEFs. Zero is a stated LOWER BOUND."),
        exit_extra_slippage=comp("exit_extra_slippage", extra_bp,
                                 C.SlippageProvenance.STRESS_LADDER,
                                 "NOT MEASURED for CEFs. Zero is a stated LOWER BOUND."),
        commission_per_share=C.CostComponent(
            "commission_per_share", Fraction(0), "micro-dollars per share",
            C.SlippageProvenance.BROKER_SCHEDULE, "Alpaca, $0/share."),
        borrow_annual=C.measured_borrow_annual("etb_general_collateral"),
    )


def zero_model():
    z = C.zero_cost_model()
    return z


# ---------------------------------------------------------------------------
# 4. summary helpers
# ---------------------------------------------------------------------------

def summarise(weekly, key="net"):
    xs = [w[key] for w in weekly]
    if len(xs) < 3:
        raise Refused(f"{len(xs)} observations cannot be summarised")
    m = S.moments(xs)
    eq, v = [1.0], 1.0
    for x in xs:
        v *= (1 + x)
        eq.append(v)
    return {
        "n": len(xs), "mean_bp": m["mean"] * 1e4, "sd_bp": m["sd"] * 1e4,
        "t": m["mean"] / m["sd"] * math.sqrt(len(xs)) if m["sd"] else 0.0,
        "sharpe_per_obs": m["mean"] / m["sd"] if m["sd"] else 0.0,
        "ann_sharpe": S.annualised_sharpe(xs, WEEKS_PER_YEAR),
        "ann_return": v ** (WEEKS_PER_YEAR / len(xs)) - 1,
        "max_drawdown": S.max_drawdown(eq)["max_drawdown"],
        "skew": m["skew"], "kurtosis_non_excess": m["kurtosis"],
    }


def decile_label_permutation(cfg, panel, grid, rets, k_lo, k_hi, n=10_000, seed=SEED):
    """Redraw WHICH funds are called wide/narrow, holding dates, counts and holding period.

    FINDINGS 5c as extended by T10_RESULT.md section 5: on a sorted return series this answers
    'is this partition special?', not 'is the mean positive?'. The dispersion ratio is returned
    beside the p-value and the result must print it.
    """
    H = cfg["H"]
    start = max(k_lo, cfg["L"] or 0)
    plan = []
    k = start
    while k + 1 + H <= k_hi:
        sig = signal_at(panel, grid, k, cfg, None)
        lo, hi = deciles(sig)
        if lo and hi:
            pool = sorted(sig)
            # per-week per-fund returns over the tranche
            mat = [[rets.get(t, {}).get(j) for t in pool] for j in range(k + 1, k + 1 + H)]
            plan.append((pool, mat, lo, hi))
        k += H
    if not plan:
        raise Refused("no tranches to permute")

    def series(pick):
        out = []
        for (pool, mat, lo, hi) in plan:
            idx = {t: i for i, t in enumerate(pool)}
            L, Sh = pick(pool, lo, hi)
            li = [idx[t] for t in L]
            si = [idx[t] for t in Sh]
            for row in mat:
                a = [row[i] for i in li if row[i] is not None]
                b = [row[i] for i in si if row[i] is not None]
                out.append(0.5 * (statistics.fmean(a) if a else 0.0)
                           - 0.5 * (statistics.fmean(b) if b else 0.0))
        return out

    real = series(lambda pool, lo, hi: (lo, hi))
    observed = statistics.fmean(real)
    rng = random.Random(seed)

    def shuffled(pool, lo, hi):
        s = rng.sample(pool, len(lo) + len(hi))
        return s[:len(lo)], s[len(lo):]

    ge, disp = 0, []
    for _ in range(n):
        x = series(shuffled)
        if statistics.fmean(x) >= observed:
            ge += 1
        disp.append(statistics.pstdev(x))
    return {
        "observed_mean_bp": observed * 1e4,
        "p_right_tail": (ge + 1) / (n + 1),
        "trials": n, "seed": seed,
        "real_dispersion_bp": statistics.pstdev(real) * 1e4,
        "null_median_dispersion_bp": statistics.median(disp) * 1e4,
        "dispersion_ratio": statistics.pstdev(real) / statistics.median(disp),
        "note": (
            "Decile-label permutation. Report the dispersion ratio beside the p-value: far from "
            "1 means the p-value is about WHICH partition, not about the mean (T10 section 5)."
        ),
    }


# ---------------------------------------------------------------------------
# 5. main
# ---------------------------------------------------------------------------

def main():
    assert_frozen()
    grid, panel, bars, tickers, dropped = build_panel()
    k_split = next(i for i, d in enumerate(grid) if d >= SPLIT)
    print(f"grid {len(grid)} weekly dates {grid[0]} .. {grid[-1]}; "
          f"design [0,{k_split}) held-out [{k_split},{len(grid)})")
    print(f"dropped non-grid dates: {dropped}")

    rets_adj = weekly_returns(bars, grid)
    raw_px = defaultdict(dict)
    for d, row in panel.items():
        for t, r in row.items():
            raw_px[t][d] = r["price"]
    rets_raw = weekly_returns(raw_px, grid)
    nav_px = defaultdict(dict)
    for d, row in panel.items():
        for t, r in row.items():
            nav_px[t][d] = r["nav"]
    rets_nav = weekly_returns(nav_px, grid)

    base = cef_cost_model(json.loads((OUT / "T12_FRICTION_CENSUS.json").read_text())
                          ["measured_quoted_half_spread"]["median_half_spread_bp"])
    h = float(base.entry_half_spread.value)

    doc = {
        "preregistration_sha256": PREREG_SHA,
        "grid": {"n_weekly_dates": len(grid), "first": grid[0], "last": grid[-1],
                 "design_n": k_split, "heldout_n": len(grid) - k_split,
                 "dropped_dates": dropped,
                 "dropped_reason": "fewer than half the live universe quoted (US market "
                                   "holidays + the truncated final date)"},
        "cost_model": base.to_report(),
        "design": {}, "heldout": {},
    }

    # ---- design window: all six trials ----
    design_sharpes = []
    for cfg in TRIALS:
        w, tr = run_config(cfg, panel, grid, rets_adj, base, k_lo=0, k_hi=k_split)
        s = summarise(w)
        design_sharpes.append(s["sharpe_per_obs"])
        doc["design"][f"trial{cfg['id']}"] = {
            "cfg": cfg, "net": s, "gross": summarise(w, "gross"),
            "n_tranches": len(tr),
            "mean_turnover_per_rebalance": statistics.fmean([x["turnover"] for x in tr]),
            "mean_cost_bp_per_rebalance": statistics.fmean([x["cost_bp"] for x in tr]),
            "mean_n_per_leg": statistics.fmean([x["n_long"] for x in tr]),
        }
        print(f"  design trial{cfg['id']} {cfg['family']} L={cfg['L']} H={cfg['H']}: "
              f"net {s['mean_bp']:+.2f} bp/wk t {s['t']:+.2f} annSR {s['ann_sharpe']:+.3f}")

    V = S.sharpe_variance_from_trials(design_sharpes)
    primary = next(c for c in TRIALS if c.get("primary"))

    # ---- THE HISTORY GATE (prereg section 3) ----
    pw, _ = run_config(primary, panel, grid, rets_adj, base, k_lo=0, k_hi=k_split)
    sigma_ann = summarise(pw)["sd_bp"] / 1e4 * math.sqrt(WEEKS_PER_YEAR)
    n_heldout = len(grid) - k_split - 1

    def min_detectable(n, trials, var):
        sr0 = S.expected_max_sharpe(trials, var) if trials > 1 else 0.0
        z = S.norm_ppf(0.95)
        lo, hi = 0.0, 5.0
        for _ in range(300):
            mid = (lo + hi) / 2
            if (mid - sr0) * math.sqrt(n - 1) / math.sqrt(1 + mid * mid / 2) < z:
                lo = mid
            else:
                hi = mid
        return hi

    mds = min_detectable(n_heldout, len(TRIALS), V)
    mds_ann = mds * math.sqrt(WEEKS_PER_YEAR)
    bench_sharpe = PONTIFF_ANNUAL / sigma_ann
    # years of weekly history that would make mds_ann == bench_sharpe
    need_n = 2
    while min_detectable(need_n, len(TRIALS), V) * math.sqrt(WEEKS_PER_YEAR) > bench_sharpe:
        need_n += 1
        if need_n > 200_000:
            break
    doc["history_gate"] = {
        "heldout_weekly_observations": n_heldout,
        "trials": len(TRIALS),
        "sharpe_variance_across_design_trials": V,
        "sd_of_design_trial_sharpes": math.sqrt(V),
        "sigma_annualised_design_window": sigma_ann,
        "min_detectable_annualised_sharpe": mds_ann,
        "min_detectable_annualised_sharpe_at_trials_1": (
            min_detectable(n_heldout, 1, 0.0) * math.sqrt(WEEKS_PER_YEAR)),
        "benchmark": {
            "annual_return": PONTIFF_ANNUAL,
            "source": "Pontiff (1995) JFE 37 -- the largest clean figure in this literature, "
                      "declared in T12_PREREGISTRATION.md section 3b before measurement",
            "implied_annualised_sharpe": bench_sharpe,
        },
        "passes": mds_ann <= bench_sharpe,
        "heldout_weekly_observations_required": need_n,
        "years_of_weekly_history_required": need_n / WEEKS_PER_YEAR,
        "years_available_heldout": n_heldout / WEEKS_PER_YEAR,
    }
    print("\nHISTORY GATE: min detectable annualised Sharpe "
          f"{mds_ann:.3f} vs benchmark {bench_sharpe:.3f} -> "
          f"{'PASS' if mds_ann <= bench_sharpe else 'FAIL'}")

    # ---- held out, run once ----
    for cfg in TRIALS:
        w, tr = run_config(cfg, panel, grid, rets_adj, base, k_lo=k_split, k_hi=len(grid) - 1)
        row = {"cfg": cfg, "net": summarise(w), "gross": summarise(w, "gross"),
               "n_tranches": len(tr),
               "mean_turnover_per_rebalance": statistics.fmean([x["turnover"] for x in tr]),
               "mean_cost_bp_per_rebalance": statistics.fmean([x["cost_bp"] for x in tr])}
        doc["heldout"][f"trial{cfg['id']}"] = row
        print(f"  heldout trial{cfg['id']} {cfg['family']} L={cfg['L']} H={cfg['H']}: "
              f"net {row['net']['mean_bp']:+.2f} bp/wk t {row['net']['t']:+.2f} "
              f"annSR {row['net']['ann_sharpe']:+.3f}")

    pw_h, pt_h = run_config(primary, panel, grid, rets_adj, base,
                            k_lo=k_split, k_hi=len(grid) - 1)
    net = [x["net"] for x in pw_h]
    doc["primary_heldout"] = {
        "cfg": primary,
        "net": summarise(pw_h), "gross": summarise(pw_h, "gross"),
        "dsr_trials6": S.deflated_sharpe(net, trials=len(TRIALS), sharpe_variance=V),
        "dsr_trials1": S.deflated_sharpe(net, trials=1),
        "dsr_trials12": S.deflated_sharpe(net, trials=12, sharpe_variance=V),
    }
    print("\nprimary held out: net "
          f"{doc['primary_heldout']['net']['mean_bp']:+.3f} bp/wk, "
          f"t {doc['primary_heldout']['net']['t']:+.3f}, "
          f"annSR {doc['primary_heldout']['net']['ann_sharpe']:+.3f}, "
          f"DSR {doc['primary_heldout']['dsr_trials6']['dsr']:.4f}")

    # ---- permutation ----
    doc["primary_heldout"]["permutation"] = decile_label_permutation(
        primary, panel, grid, rets_adj, k_split, len(grid) - 1)
    print(f"permutation p {doc['primary_heldout']['permutation']['p_right_tail']:.4f}, "
          f"dispersion ratio "
          f"{doc['primary_heldout']['permutation']['dispersion_ratio']:.3f}")

    # ---- stress ladders + zero cost ----
    ladder = []
    for mult, label in [(0.0, "0"), (0.5, "0.5h"), (1.0, "h (primary)"), (2.0, "2h")]:
        m = cef_cost_model(h * mult)
        w, _ = run_config(primary, panel, grid, rets_adj, m, k_lo=k_split, k_hi=len(grid) - 1)
        ladder.append({"half_spread_bp": h * mult, "label": label, "net": summarise(w)})
    for bp in (5, 10, 25, 50):
        m = cef_cost_model(h, bp)
        w, _ = run_config(primary, panel, grid, rets_adj, m, k_lo=k_split, k_hi=len(grid) - 1)
        ladder.append({"half_spread_bp": h, "extra_slippage_bp": bp,
                       "label": f"h + {bp}bp impact", "net": summarise(w)})
    wz, _ = run_config(primary, panel, grid, rets_adj, zero_model(),
                       k_lo=k_split, k_hi=len(grid) - 1)
    doc["stress_ladder"] = ladder
    doc["frictionless_diagnostic"] = {
        "net": summarise(wz), "note": "B19P diagnostic. Not a tradeable assumption."}
    print("\nstress ladder (held out, primary):")
    for r in ladder:
        print(f"  {r['label']:>16}: {r['net']['mean_bp']:+.3f} bp/wk  "
              f"annSR {r['net']['ann_sharpe']:+.3f}")
    print(f"  {'ZERO COST':>16}: {doc['frictionless_diagnostic']['net']['mean_bp']:+.3f} bp/wk  "
          f"annSR {doc['frictionless_diagnostic']['net']['ann_sharpe']:+.3f}")

    # ---- price-source and NAV diagnostics ----
    wr, _ = run_config(primary, panel, grid, rets_raw, base, k_lo=k_split, k_hi=len(grid) - 1)
    wn, _ = run_config(primary, panel, grid, rets_nav, base, k_lo=k_split, k_hi=len(grid) - 1)
    doc["diagnostics"] = {
        "raw_cefconnect_price_series": summarise(wr),
        "nav_return_series": summarise(wn, "gross"),
        "note": (
            "raw_cefconnect_price ignores distributions (CEFs pay 7-8 %/yr, and the "
            "widest-discount funds distribute most), so it is the CONSERVATIVE leg; the primary "
            "uses Alpaca adjustment=all. nav_return_series is the NAV leg of the long-short "
            "book -- it is NOT tradeable and is reported only to decompose whether P&L came "
            "from the discount narrowing or from the assets."
        ),
    }

    # ---- year by year ----
    yby = defaultdict(list)
    for x in pw_h:
        yby[x["date"][:4]].append(x["net"])
    doc["heldout_year_by_year"] = {
        y: {"n": len(v), "mean_bp": statistics.fmean(v) * 1e4,
            "total_pct": (math.prod(1 + r for r in v) - 1) * 100}
        for y, v in sorted(yby.items())}

    # ---- verdict ----
    p = doc["primary_heldout"]
    gate = doc["history_gate"]["passes"]
    fails = []
    if not gate:
        fails.append("history gate (section 3)")
    if p["net"]["mean_bp"] <= 0:
        fails.append("net mean <= 0")
    if p["permutation"]["p_right_tail"] >= 0.05:
        fails.append(f"permutation p = {p['permutation']['p_right_tail']:.4f} >= 0.05")
    if p["dsr_trials6"]["dsr"] < 0.95:
        fails.append(f"DSR = {p['dsr_trials6']['dsr']:.4f} < 0.95")
    doc["verdict"] = {
        "verdict": ("DEAD-BY-INSUFFICIENT-HISTORY" if not gate
                    else "DEAD" if fails else "SURVIVES"),
        "failed_gates": fails,
    }
    print(f"\nVERDICT: {doc['verdict']['verdict']}  fails={fails}")

    path = OUT / "T12_HELDOUT_RESULT.json"
    path.write_text(json.dumps(doc, indent=2, default=str) + "\n")
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
