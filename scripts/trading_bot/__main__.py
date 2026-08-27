#!/usr/bin/env python3
"""CLI: run the smoke test, or walk-forward a named smoke strategy on cached/fetched bars.

    python -m scripts.trading_bot selftest
    python -m scripts.trading_bot run --symbol SPY --start 2016-01-01 --end 2026-08-01
    python -m scripts.trading_bot run --symbol SPY ... --offline    # cache only, no network

`--offline` is the mode the test suite uses; the suite blocks outbound sockets for the whole
session (tests/_netguard.py), so anything that reaches the network there fails loudly.
"""

from __future__ import annotations

import argparse
import json
import sys

from .costs import retail_taker_costs, stress_ladder, zarattini_paper_costs, zero_cost_model
from .data import bars_per_year, load_bars
from .frozen import Refused, pin_report
from .runner import walk_forward_run
from .strategies import AlwaysShort, BuyAndHold, Oscillator, TrailingSmaCross

STRATEGIES = {
    "buy_and_hold": BuyAndHold,
    "always_short": AlwaysShort,
    "oscillator": Oscillator,
    "sma_cross": lambda: TrailingSmaCross(100),
}

COST_MODELS = {
    "retail_taker": retail_taker_costs,
    "zarattini_paper": zarattini_paper_costs,
    "zero_diagnostic": zero_cost_model,
}


def _selftest() -> int:
    """Synthetic-data wiring check. No network, no credentials, no cached data required."""
    from .engine import Bar, run_backtest
    from .stats import evaluate

    price, bars = 100_000_000, []
    for i in range(600):
        drift = 1 + ((i * 37) % 11) - 5           # deterministic zig-zag, no RNG
        nxt = price + drift * 20_000
        bars.append(Bar(
            symbol="SYNTH", ts_ns=(1_700_000_000 + i * 86_400) * 1_000_000_000,
            open_micros=price, high_micros=max(price, nxt) + 10_000,
            low_micros=min(price, nxt) - 10_000, close_micros=nxt, volume_shares=1_000_000,
        ))
        price = nxt

    cost = retail_taker_costs()
    bh = run_backtest(bars, BuyAndHold, cost)
    osc = run_backtest(bars, Oscillator, cost)
    report = evaluate(osc, bh, periods_per_year=252, trials=1, permutation_trials=2000)

    out = {
        "provenance": pin_report(),
        "bars": len(bars),
        "buy_and_hold": {
            "segments": bh.n_segments,
            "final_equity": bh.equity_curve()[-1],
            "total_turnover": float(bh.total_turnover()),
            "lookahead_audit": bh.lookahead_audit["verdict"],
        },
        "oscillator": {
            "segments": osc.n_segments,
            "total_turnover": float(osc.total_turnover()),
            "lookahead_audit": osc.lookahead_audit["verdict"],
        },
        "evaluate_keys": sorted(report.keys()),
        "paired_excess_dsr": report["paired_excess_dsr"],
        "permutation_p_right": report["permutation"]["p_right_tail"],
        "cost_ladder_rungs": [str(bp) for bp, _ in stress_ladder(cost)],
    }
    json.dump(out, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="scripts.trading_bot", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("selftest", help="synthetic-data wiring check; no network, no credentials")

    run = sub.add_parser("run", help="walk-forward a smoke strategy on real bars")
    run.add_argument("--symbol", required=True)
    run.add_argument("--start", required=True)
    run.add_argument("--end", required=True)
    run.add_argument("--timeframe", default="1Day")
    run.add_argument("--strategy", default="buy_and_hold", choices=sorted(STRATEGIES))
    run.add_argument("--costs", default="retail_taker", choices=sorted(COST_MODELS))
    run.add_argument("--folds", type=int, default=5)
    run.add_argument("--purge-bars", type=int, default=0)
    run.add_argument("--embargo-bars", type=int, default=0)
    run.add_argument("--trials", type=int, required=True,
                     help="how many configurations were EVER tried to reach this one. "
                          "The deflated Sharpe charges for the search; understating it "
                          "silently undoes the deflation.")
    run.add_argument("--sharpe-variance", type=float, default=None,
                     help="sample variance of the per-observation Sharpes across the trials. "
                          "REQUIRED whenever --trials > 1: it is what builds the chance "
                          "ceiling, and without it the deflation refuses rather than "
                          "silently reporting an undeflated number.")
    run.add_argument("--permutations", type=int, default=10_000)
    run.add_argument("--offline", action="store_true", help="cache only; never touch the network")
    run.add_argument("--out", help="write the report JSON here instead of stdout")

    args = parser.parse_args(argv)

    if args.command == "selftest":
        return _selftest()

    bars, manifest = load_bars(
        args.symbol, args.start, args.end, args.timeframe,
        allow_network=not args.offline,
    )
    report = walk_forward_run(
        bars, STRATEGIES[args.strategy], COST_MODELS[args.costs](),
        periods_per_year=bars_per_year(args.timeframe),
        n_folds=args.folds, purge_bars=args.purge_bars, embargo_bars=args.embargo_bars,
        trials=args.trials, sharpe_variance=args.sharpe_variance,
        permutation_trials=args.permutations,
    )
    report["data_manifest"] = manifest

    text = json.dumps(report, indent=2, default=str)
    if args.out:
        with open(args.out, "w") as handle:
            handle.write(text + "\n")
        print(f"wrote {args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Refused as exc:
        sys.stderr.write(f"REFUSED: {exc}\n")
        sys.exit(2)
