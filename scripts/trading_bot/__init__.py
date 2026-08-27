#!/usr/bin/env python3
"""T2 -- the leakage-free backtest and paper-execution harness.

This is the rig every edge candidate must pass through before anyone believes it. It is
deliberately built BEFORE any equity candidate exists, so that no part of it was shaped by a
result someone wanted.

    from scripts.trading_bot import (
        load_bars, retail_taker_costs, walk_forward_run, BuyAndHold, bars_per_year,
    )

    bars, manifest = load_bars("SPY", "2016-01-01", "2026-08-01", "1Day")
    report = walk_forward_run(
        bars, BuyAndHold, retail_taker_costs(),
        periods_per_year=bars_per_year("1Day"), n_folds=5, trials=1,
    )

See README.md in this directory for the three layers that make it leakage-free, and for the
list of things it deliberately refuses to do.
"""

from .costs import (CostComponent, CostModel, SlippageProvenance, b22b_measured_costs,
                    measured_borrow_annual, measured_extra_slippage, retail_taker_costs,
                    stress_ladder, zarattini_paper_costs, zero_cost_model)
from .data import (bars_per_year, load_bars, load_env_credentials,
                   assert_levels_are_point_in_time)
from .engine import (Bar, BacktestResult, PointInTimeView, Strategy, lookahead_audit,
                     run_backtest, validate_series)
from .frozen import PINNED_SHA256, PinBroken, Refused, pin_report
from .paper import Order, OrderType, PaperBroker, Side, orders_for_target
from .runner import single_run, walk_forward_run
from .stats import (annualised_sharpe, cagr, deflated_sharpe, evaluate, expected_max_sharpe,
                    max_drawdown, moments, paired_excess, permutation_test,
                    sharpe_variance_from_trials, summarise)
from .strategies import (AlwaysFlat, AlwaysShort, BuyAndHold, CheatingOracle, Oscillator,
                         TrailingSmaCross)
from .walkforward import Fold, assert_no_leakage, walk_forward_folds

__all__ = [
    "Refused", "PinBroken", "PINNED_SHA256", "pin_report",
    "SlippageProvenance", "CostComponent", "CostModel",
    "retail_taker_costs", "zarattini_paper_costs", "zero_cost_model", "stress_ladder",
    "b22b_measured_costs", "measured_extra_slippage", "measured_borrow_annual",
    "Bar", "validate_series", "PointInTimeView", "Strategy", "BacktestResult",
    "run_backtest", "lookahead_audit",
    "load_bars", "load_env_credentials", "bars_per_year", "assert_levels_are_point_in_time",
    "moments", "annualised_sharpe", "max_drawdown", "cagr", "expected_max_sharpe",
    "sharpe_variance_from_trials", "deflated_sharpe", "permutation_test", "paired_excess",
    "summarise", "evaluate",
    "Fold", "walk_forward_folds", "assert_no_leakage",
    "walk_forward_run", "single_run",
    "BuyAndHold", "AlwaysFlat", "AlwaysShort", "Oscillator", "TrailingSmaCross",
    "CheatingOracle",
    "Side", "OrderType", "Order", "orders_for_target", "PaperBroker",
]
