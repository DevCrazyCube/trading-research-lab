# INVENT 0822 · LOW-TURNOVER theme · PICK FREEZE (written BEFORE the held-out window was run)

**Time of freeze:** 2026-08-22, immediately after `invent0822_slow_xs.py design` completed and
before `holdout` was invoked. Design results file:
`research/trading_bot/INVENT_0822_slowturn_XS_DESIGN.json`.

## Design-window verdict (2016-01-04 … 2021-12-31), 42 cells, 21 formulas × {h=21, h=63}

**Best GROSS design t = 1.69** (`COSKEW_NEG` h63) against an iid multiple-testing bar of
`sqrt(2 ln 42) = 2.73` and a (higher) empirical slow-book null bar. **No cell clears.**
The sleeve is declared a NEGATIVE result on the design window before any held-out number exists.

## Picks frozen anyway, so the held-out window is spent on a declared list and not on a scan

Ranked by design GROSS t (the only statistic allowed to choose), plus the two that carry the
theme's central economic claim:

1. `COSKEW_NEG` h63 — design gross SR 0.69, t 1.69
2. `DIV_CUT_DEPTH` h21 — design gross SR 0.51, t 1.24
3. `SPREAD_LEVEL` h63 — design gross SR 0.40, t 0.98 (theme-core: illiquidity premium)
4. `ILLIQ_UNCERT` h63 — design gross SR 0.43, t 1.04 (theme-core: liquidity-risk premium)

**Pre-declared reading rule:** none of these can be promoted, because promotion requires the
GROSS design t to clear the bar FIRST (EXECUTION_COST_WALL lesson) and none does. The held-out
run is therefore reported as *evidence about the theme*, not as a certification step. A positive
held-out number on a sub-bar design cell is not a signal; it is a coin.

## Declared extension, also frozen here

The $20M+ ADV eligibility screen inherited from `newterr_xseq_sweep` structurally excludes the
population where an illiquidity premium could exist. One extension run is therefore declared in
advance: the same illiquidity and payout formulas on a **$2M+ ADV** universe, design and held-out,
counted into N. No other universe will be tried.
