# Pre-registration — intraday equity/ETF relative-value & mean-reversion sweep

Written **before** any design-window result existed. Timestamped by the commit that adds it;
the design JSON did not exist on disk when this was written.

## Data

- Alpaca SIP 5-minute bars, `adjustment=all`, RTH only (09:30–16:00 ET), 2021-01-04 → 2026-08-15.
- 132-symbol universe: same-claim ETF sibling clusters, sector SPDR/Vanguard twins, style and
  regional ETFs, levered/inverse funds, and 30+ mega-cap single names for the basket and
  lead-lag families. Cache: `research/data/rv_cache/`, one `.npz` per symbol.
- **Survivorship:** Alpaca serves symbols that exist today. Every ETF in the universe is alive
  in 2026, so the ETF side is survivorship-biased by construction. This cannot be fixed from
  this feed and is not claimed away.
- **Price levels from this cache are not point-in-time** (retroactive split/dividend
  adjustment). No config filters on a price level; all of them use returns or log ratios.

## Windows

| | |
|---|---|
| DESIGN | 2021-01-04 → 2024-12-31 (~1,005 sessions) |
| HELD OUT | 2025-01-02 → 2026-08-15 (~405 sessions) |

The held-out window is not read during the sweep. `rv_sweep.py --stage heldout` refuses to run
without an explicit `--only` shortlist, so it cannot be used to browse.

## Execution and costs

- Signal from closes through bar *t−1*; fill at the **VWAP of bar t**; return
  `vwap[t+1]/vwap[t] − 1`. A full 5-minute bar separates the last observed price from the fill.
- Every config is forced flat at the closing bar of each session.
- Cost rungs: **0.5 / 1.0 / 2.0 / 2.5 bp per side**, charged on `|Δw|`. Headline = 1.0 bp.
  Provenance `ADVERSE_PROXY_FOR_AN_UNMEASURED_LEG`; the repo's measured liquid-name close
  half-spread is 1.13 bp (T3, 19,835 symbol-days) and 2.5 bp is `retail_taker_costs()`'s own
  default.
- Plus **0.15 bp per unit of turnover** for SEC 31 / FINRA TAF, on every rung.
- Borrow = 0, justified: intraday-only, flat overnight, so no borrow accrual.

## The noise bar

`N` configs are scored. The bar is the **95th percentile of the max design Sharpe under H0**,
from a stationary block bootstrap (block = 5 days, 500 resamples) of each config's *demeaned*
daily net PnL, drawing the **same day indices for every config** so the sweep's internal
correlation structure is preserved. `sqrt(2 ln N)/sqrt(years)` is reported alongside as a
sanity check but the bootstrap is the operative bar.

## Selection rule — FROZEN

1. Rank configs by design net Sharpe at the **1.0 bp/side** headline rung.
2. A config is a **candidate** iff its design net Sharpe **exceeds the bootstrap p95**.
3. At most the **top 3** candidates go to the held-out window.
4. **If nothing clears p95, the theme is reported as NOISE.** The top 3 are still run
   out-of-sample, but explicitly as a documented negative control, and no design winner is
   promoted as an edge on the strength of its design number.
5. No config is re-specified, no parameter is re-tuned, and no window is moved after the
   design results are read.

## What would make this theme interesting

A same-claim pair trade crosses **four half-spreads** per round trip (two legs, in and out), so
at the headline rung it must capture ~4.6 bp to break even. `rv_census.py` measures, before any
strategy is scored, how far these spreads actually travel from their own trailing mean and
whether the displacement persists for even one bar. If the p95 displacement sits below the
round-trip cost and the one-bar autocorrelation is near zero, the theme is dead on mechanism
and the sweep is expected to confirm it rather than discover it.
