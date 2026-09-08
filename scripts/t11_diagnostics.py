#!/usr/bin/env python3
"""T11 -- post-verdict diagnostics. NOT a second test.

The verdict is `t11_evaluate.py`'s and it is already on disk. Everything here interrogates the
SAME frozen configuration and the SAME held-out events for *why*, using quantities the
pre-registration already declared (the symmetric |spread| <= 20% robustness variant of section 4
exclusion 8, and the break-even break rate b* of section 7). No gate is re-run, no parameter is
re-chosen, and no number here can change the verdict.

What it answers:
  1. WHAT is in the left tail -- event by event, named.
  2. Is that tail an economic tail, or a feed-classification artifact? (counts against
     `stock_and_cash_mergers`, and against warrant/unit/right ticker shapes)
  3. Applied to the CLEANEST possible version of the trade -- the pre-declared symmetric-cap
     variant, which is the single most favourable object this dataset can produce -- does the
     pre-registered break gate pass?
"""

from __future__ import annotations

import gzip
import json
import pathlib
import statistics
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.t3_pressure_reversal as t3                                        # noqa: E402
import scripts.t11_evaluate as E                                                 # noqa: E402
import scripts.t11_merger_arb as t11                                             # noqa: E402

RESULT = ROOT / "research" / "trading_bot" / "T11_HELDOUT_RESULT.json"
T7_CACHE = ROOT / "research" / "data" / "t7_cache" / "corporate_actions_all.json.gz"


def main():
    E.assert_frozen()
    held = json.loads(RESULT.read_text())
    H = held["primary_H_selected_on_design"]
    h_bp = held["half_spread"]["test"]["median_half_spread_bp"]
    model = E.cost_model(h_bp)

    cal = [r["date"] for r in t3.calendar() if r["date"] >= "2016-01-01"]
    idx = {d: i for i, d in enumerate(cal)}
    events = [e for e in t11.cash_merger_events() if t11.is_ticker_shaped(e)]
    syms = sorted({e["acquiree_symbol"] for e in events})
    bars = t11.daily_bars(syms + [E.RF, E.MARKET])
    auct = t11.target_auctions(syms + [E.RF, E.MARKET])
    rf_close = E.adjusted_bars([E.RF, E.MARKET], "adjusted_bars")[E.RF]

    kept, _capped, _f = E.build_events(H, bars, auct, cal, idx)
    test = [r for r in kept if r["period"] == "test"]
    rows = []
    for r in test:
        x, g, c, rr = E.net_excess(r, model, rf_close, cal, idx)
        rows.append({"symbol": r["symbol"], "effective_date": r["effective_date"],
                     "t0": r["t0"], "t_last": r["t_last"], "p0": r["p0"], "rate": r["rate"],
                     "gross_spread": g, "cost": c, "rf": rr, "net_excess": x,
                     "calendar_days": r["calendar_days"],
                     "sessions_t_last_to_effective":
                         idx[r["effective_date"]] - idx[r["t_last"]]
                         if r["effective_date"] in idx else None})
    rows.sort(key=lambda z: z["net_excess"])

    # --- 2. is the tail economic, or a feed artifact?
    ca = json.load(gzip.open(T7_CACHE, "rt"))
    mixed = {}
    for r in ca["stock_and_cash_mergers"]:
        mixed.setdefault(r.get("acquiree_symbol"), []).append(r.get("effective_date"))

    def _near(a, b, tol=3):
        """Same event, allowing the two feeds to disagree by a settlement day or three."""
        if not a or not b or a not in idx or b not in idx:
            return a == b
        return abs(idx[a] - idx[b]) <= tol

    def is_mixed(sym, eff):
        return any(_near(eff, d) for d in mixed.get(sym, ()))

    def is_warrantish(sym):
        return len(sym) == 5 and sym.endswith(("W", "U", "R"))

    tail = [z for z in rows if z["gross_spread"] < -0.20]
    contamination = {
        "held_out_events": len(rows),
        "events_with_gross_spread_below_minus_20pct": len(tail),
        "their_mean_net_excess": statistics.fmean(z["net_excess"] for z in tail) if tail else None,
        "their_share_of_the_book": len(tail) / len(rows),
        "of_those_also_recorded_as_stock_and_cash_merger_within_3_sessions":
            sum(1 for z in tail if is_mixed(z["symbol"], z["effective_date"])),
        "of_those_with_warrant_unit_right_ticker_shape":
            sum(1 for z in tail if is_warrantish(z["symbol"])),
        "of_those_whose_last_bar_is_more_than_10_sessions_before_the_effective_date":
            sum(1 for z in tail if (z["sessions_t_last_to_effective"] or 0) > 10),
        "tail_symbols": [z["symbol"] for z in tail],
        "universe_wide_cash_mergers_also_in_stock_and_cash_within_3_sessions": sum(
            1 for e in events if is_mixed(e["acquiree_symbol"], e["effective_date"])),
        "universe_wide_warrant_unit_right_shaped_acquirees": sum(
            1 for e in events if is_warrantish(e["acquiree_symbol"])),
        "held_out_events_whose_last_bar_is_more_than_10_sessions_before_effective": sum(
            1 for z in rows if (z["sessions_t_last_to_effective"] or 0) > 10),
        "note": (
            "Three named defects, all inside the pre-registered event set. (a) A record in "
            "`cash_mergers` whose (symbol, effective_date) also appears in "
            "`stock_and_cash_mergers` carries only the CASH leg of a mixed-consideration deal; "
            "dividing that cash leg by the pre-close price manufactures a catastrophic loss the "
            "actual shareholder never took, because they also received stock. (b) Warrant, unit "
            "and rights tickers are admitted by a bare ^[A-Z]{1,5}$ shape test and are cashed "
            "out at a cent. (c) Section 4's exclusion 3 forbids bars AFTER the effective date "
            "but says nothing about a name that stopped trading long BEFORE it, so a halted or "
            "sanctioned ADR can enter with a multi-year holding period. Each is a definitional "
            "error in this pre-registration, not a finding about merger arbitrage; each is "
            "reported rather than repaired, because repairing it after the verdict is exactly "
            "the move a freeze exists to forbid."
        ),
    }

    # --- 3. the pre-declared symmetric-cap variant, and the break gate applied to it
    clean = [z for z in rows if abs(z["gross_spread"]) <= E.DISCOUNT_CAP]
    mu = statistics.fmean(z["net_excess"] for z in clean)
    rfm = statistics.fmean(z["rf"] for z in clean)
    days = statistics.fmean(z["calendar_days"] for z in clean)
    bstar = {f"{L:.2f}": (mu / (mu + rfm - L)) for L in E.BREAK_LOSSES}
    clean_block = {
        "n": len(clean),
        "mean_net_excess_per_event": mu,
        "t": mu / (statistics.stdev(z["net_excess"] for z in clean) / len(clean) ** 0.5),
        "mean_calendar_days": days,
        "annualised_excess_over_tbills": mu * 365.0 / days,
        "mean_risk_free_over_window": rfm,
        "break_even_break_rate_bstar_by_loss": bstar,
        "primary_bstar_L_minus_25pct": bstar[f"{E.PRIMARY_BREAK_LOSS:.2f}"],
        "gate_requires_bstar_above": E.BREAK_GATE_BSTAR,
        "gate_passes": bstar[f"{E.PRIMARY_BREAK_LOSS:.2f}"] > E.BREAK_GATE_BSTAR,
        "literature_break_rate_band": [0.05, 0.10],
        "note": (
            "This is the MOST FAVOURABLE object this dataset can produce: both oracles of "
            "prereg section 1b, plus a cap that conditions on the eventual cash rate and so "
            "keeps only deals whose price was already near the terminal consideration. It is "
            "not tradable and is reported as an upper bound, not an estimate."
        ),
    }

    out = {
        "prereg_sha256": E.PREREG_SHA,
        "primary_H": H,
        "worst_15_events": rows[:15],
        "best_10_events": rows[-10:],
        "tail_contamination": contamination,
        "symmetric_cap_variant": clean_block,
        "frictionless_diagnostic_from_heldout": held["stress_ladder"]["frictionless_B19P"],
    }
    path = ROOT / "research" / "trading_bot" / "T11_DIAGNOSTICS.json"
    path.write_text(json.dumps(out, indent=2, default=float) + "\n")
    print(json.dumps({"tail_contamination": contamination,
                      "symmetric_cap_variant": clean_block}, indent=2, default=float))
    print("wrote", path)


if __name__ == "__main__":
    main()
