#!/usr/bin/env python3
"""Ties the pieces together: walk-forward a strategy against its benchmark and report.

The out-of-sample statistics are computed on the CONCATENATED test folds, not as an average
of per-fold statistics. Averaging per-fold Sharpes weights a 40-bar fold the same as a
400-bar one and is systematically wrong in whichever direction the small folds happen to
point. Per-fold numbers are still reported, as diagnostics.

`trials` is a REQUIRED argument all the way down. It is the number of configurations that
were ever tried in reaching the thing being reported, and it is the input the deflated Sharpe
charges for. Passing 1 when the truth is 40 is not a rounding error; it is the entire failure
mode DSR exists to catch, and this programme's own +0.48% died precisely there.
"""

from __future__ import annotations

from .costs import CostModel
from .engine import build_strategy, run_backtest, validate_series
from .frozen import Refused, pin_report
from .stats import (annualised_sharpe, cagr, deflated_sharpe, evaluate, max_drawdown,
                    paired_excess, summarise)
from .strategies import BuyAndHold
from .walkforward import assert_no_leakage, walk_forward_folds


def _dsr_refusal_help(trials: int) -> dict:
    """Name the two distinct reasons a deflated Sharpe can refuse. Both are correct behaviour."""
    return {
        "why_a_refusal_here_is_correct": (
            "Two distinct causes, and the message above says which. (1) A ZERO-VARIANCE excess "
            "series means the strategy IS the benchmark on these bars -- FINDINGS 5c's "
            "'wrong object', where returning a probability would invent a difference that does "
            "not exist. (2) A declared trial count above 1 with no cross-trial Sharpe variance "
            "cannot form the chance ceiling, and defaulting it to zero would silently hand back "
            "an UNDEFLATED number under a deflated name."
        ),
        "how_to_supply_it": (
            f"trials={trials} was declared. Pass sharpe_variance= the sample variance of the "
            "per-observation Sharpes across the configurations actually tried "
            "(stats.sharpe_variance_from_trials), or declare trials=1 if only one was ever run."
        ),
    }


def walk_forward_run(
    series,
    strategy_factory,
    cost_model: CostModel,
    *,
    periods_per_year: int,
    n_folds: int = 5,
    purge_bars: int = 0,
    embargo_bars: int = 0,
    execution_lag_bars: int = 1,
    trials: int = 1,
    sharpe_variance: float | None = None,
    permutation_trials: int = 10_000,
    audit_probes: int = 6,
    seed: int = 20260816,
    benchmark_factory=BuyAndHold,
    anchored: bool = True,
) -> dict:
    """Run `strategy_factory` and `benchmark_factory` over the same walk-forward folds."""
    series = validate_series(series)
    warmup = build_strategy(strategy_factory, series).warmup_bars
    bench_warmup = build_strategy(benchmark_factory, series).warmup_bars
    if bench_warmup > warmup:
        raise Refused(
            f"the benchmark needs {bench_warmup} warm-up bars against the strategy's {warmup}. "
            "The pairing would then compare different bar ranges, which cancels nothing."
        )

    folds = walk_forward_folds(
        len(series), n_folds=n_folds, warmup_bars=warmup,
        purge_bars=purge_bars, embargo_bars=embargo_bars, anchored=anchored,
    )
    leakage = assert_no_leakage(folds)

    fold_reports, oos_strategy, oos_benchmark, oos_market, oos_positions = [], [], [], [], []
    first_ts = last_ts = None

    for fold in folds:
        bars = fold.test_slice(series)
        result = run_backtest(
            bars, strategy_factory, cost_model,
            execution_lag_bars=execution_lag_bars, audit_probes=audit_probes,
            audit_seed=seed + fold.index,
        )
        bench = run_backtest(
            bars, benchmark_factory, cost_model,
            execution_lag_bars=execution_lag_bars, audit_probes=audit_probes,
            audit_seed=seed + fold.index,
            # The benchmark is forced onto the STRATEGY's warm-up so both cover exactly the
            # same bars. Letting buy-and-hold start 99 bars earlier than an SMA(100) would
            # pair two different date ranges, and a paired difference over different ranges
            # cancels nothing -- it silently adds the benchmark's extra period as "excess".
            warmup_bars=warmup,
        )
        if result.n_segments != bench.n_segments:
            raise Refused(
                f"fold {fold.index}: strategy and benchmark produced different segment counts"
            )

        oos_strategy.extend(result.returns)
        oos_benchmark.extend(bench.returns)
        oos_market.extend(result.market_returns)
        oos_positions.extend(result.positions[:len(result.market_returns)])
        if first_ts is None:
            first_ts = result.bar_timestamps_ns[0]
        last_ts = result.bar_timestamps_ns[-1]

        fold_reports.append({
            **fold.to_report(),
            "strategy": summarise(result, periods_per_year),
            "benchmark": summarise(bench, periods_per_year),
            "lookahead_audit": result.lookahead_audit["verdict"],
        })

    if not oos_strategy:
        raise Refused("no out-of-sample segments were produced")

    excess = paired_excess(oos_strategy, oos_benchmark)

    def _curve(returns):
        equity, curve = 1.0, [1.0]
        for r in returns:
            equity *= 1.0 + float(r)
            curve.append(equity)
        return curve

    strategy_curve, benchmark_curve = _curve(oos_strategy), _curve(oos_benchmark)
    pooled = {
        "n_out_of_sample_segments": len(oos_strategy),
        "strategy_annualised_sharpe": annualised_sharpe(oos_strategy, periods_per_year),
        "benchmark_annualised_sharpe": annualised_sharpe(oos_benchmark, periods_per_year),
        # CAGR over the CALENDAR span the concatenated test folds actually cover. The folds
        # are contiguous and non-overlapping (asserted above), which is what makes stitching
        # them into one curve legitimate.
        "strategy_cagr": cagr(strategy_curve, first_ts, last_ts),
        "benchmark_cagr": cagr(benchmark_curve, first_ts, last_ts),
        "strategy_max_drawdown": max_drawdown(strategy_curve)["max_drawdown"],
        "benchmark_max_drawdown": max_drawdown(benchmark_curve)["max_drawdown"],
        "strategy_final_equity": strategy_curve[-1],
        "benchmark_final_equity": benchmark_curve[-1],
        "calendar_span_ns": last_ts - first_ts,
    }
    # Two SEPARATE try blocks. An earlier version wrapped both in one, so a refusal from the
    # deflation discarded a paired Sharpe that had already been computed correctly -- and the
    # canned explanation attached to it named the wrong cause. A refusal must say which fact
    # could not be established, not the most convenient one.
    try:
        pooled["paired_excess_annualised_sharpe"] = annualised_sharpe(excess, periods_per_year)
    except Refused as exc:
        pooled["paired_excess_annualised_sharpe"] = {
            "refused": str(exc),
            "meaning": "the excess series is constant: the strategy IS the benchmark here.",
        }
    try:
        pooled["paired_excess_dsr"] = deflated_sharpe(
            excess, trials=trials, sharpe_variance=sharpe_variance,
        )
    except Refused as exc:
        pooled["paired_excess_dsr"] = {"refused": str(exc), **_dsr_refusal_help(trials)}

    from .stats import permutation_test
    pooled["permutation"] = permutation_test(
        oos_positions, oos_market, trials=permutation_trials, seed=seed, statistic="mean",
    )

    return {
        "provenance": pin_report(),
        "cost_model": cost_model.to_report(),
        "strategy": build_strategy(strategy_factory, series).describe(),
        "benchmark": build_strategy(benchmark_factory, series).describe(),
        "execution_lag_bars": execution_lag_bars,
        "periods_per_year": periods_per_year,
        "trials_declared": trials,
        "walk_forward": {
            "n_folds": len(folds),
            "anchored": anchored,
            "leakage_check": leakage,
            "folds": fold_reports,
        },
        "pooled_out_of_sample": pooled,
        "decision_instrument": "pooled_out_of_sample.paired_excess_dsr",
        "reading_note": (
            "Pooled out-of-sample statistics are computed on the CONCATENATED test folds. "
            "Per-fold numbers are diagnostics; averaging them would weight a short fold like "
            "a long one. The decision instrument is the PAIRED excess DSR, per FINDINGS 5c."
        ),
    }


def single_run(
    series,
    strategy_factory,
    cost_model: CostModel,
    *,
    periods_per_year: int,
    trials: int = 1,
    sharpe_variance: float | None = None,
    execution_lag_bars: int = 1,
    permutation_trials: int = 10_000,
    audit_probes: int = 6,
    seed: int = 20260816,
    benchmark_factory=BuyAndHold,
) -> dict:
    """One in-sample pass with the full significance report. NOT out-of-sample evidence.

    Kept separate from `walk_forward_run` and named so nothing produced by it can be quoted
    as out-of-sample by accident.
    """
    series = validate_series(series)
    warmup = build_strategy(strategy_factory, series).warmup_bars
    result = run_backtest(
        series, strategy_factory, cost_model,
        execution_lag_bars=execution_lag_bars, audit_probes=audit_probes, audit_seed=seed,
    )
    bench = run_backtest(
        series, benchmark_factory, cost_model,
        execution_lag_bars=execution_lag_bars, audit_probes=audit_probes, audit_seed=seed,
        warmup_bars=warmup,          # same bars on both legs, or the pairing cancels nothing
    )
    report = evaluate(
        result, bench, periods_per_year=periods_per_year, trials=trials,
        sharpe_variance=sharpe_variance, permutation_trials=permutation_trials, seed=seed,
    )
    report["provenance"] = pin_report()
    report["sample"] = "IN-SAMPLE, single pass. Not out-of-sample evidence."
    report["cost_model"] = cost_model.to_report()
    return report


__all__ = ["walk_forward_run", "single_run"]
