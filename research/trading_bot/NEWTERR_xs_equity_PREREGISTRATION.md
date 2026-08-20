# NEWTERR — Short-horizon cross-sectional US equity factors: PRE-REGISTRATION

Written **before any design-window result exists**. Territory key: `xs_equity`.

## Territory

Short-horizon (1–10 day) cross-sectional equity factors on the survivorship-mitigated
Alpaca daily panel (`research/data/t17_cache/daily`, 14,794 symbols incl. delisted,
2016-01-04 → 2026-08-14), split/dividend-adjusted with the t7 corporate-actions cache,
plus the T16 FINRA Reg SHO daily short-volume panel (2018-08 → 2026-08, 19.3M rows)
and the FINRA bimonthly short-interest panel (2017-12 → 2026-07, 3.9M rows).

Explicitly **not** re-mining: overnight-equity event studies (T3/T7), ETF same-index RV,
cross-asset lead-lag, futures term structure, generic calendar, perp funding/OI/flow,
CEF/dual-class/ADR RV.

## Windows (frozen now)

- **Design**: 2016-01-04 → 2021-12-31
- **Held out** (not to be touched until design picks are frozen to disk):
  2022-01-03 → 2026-08-14

## Universe (point-in-time, from data through close of day *t*)

- split-adjusted close ≥ $5
- 20-day median dollar volume ≥ $20M  (this doubles as the easy-to-borrow screen)
- ≥ 200 valid closes in the trailing 260 sessions
- delisted symbols retained for as long as they have bars (survivorship mitigated,
  not cured: a symbol Alpaca dropped from its asset list entirely is invisible)

## Portfolio construction (identical for every formula)

1. Signal computed from data through **close of day t**.
2. Cross-sectional rank within the day's eligible set; long the top decile, short the
   bottom decile, equal-weighted, dollar-neutral, gross notional 1.0.
3. **Entry at the open of t+1, exit at the open of t+1+h.** No same-bar fills, no
   close-to-close fills.
4. Horizons h ∈ {1, 3, 5}. Overlapping cohorts are averaged, so the daily book is
   `mean(w[t-1] … w[t-h])` and the daily P&L series is honest and non-overlapping.

## Costs charged (both legs, every rebalance)

- one-way per-name cost = `clip(Corwin–Schultz 20d half-spread, max(1bp, 0.25¢/price), 100bp) + 0.5bp` fees
- charged on `Σ_i |book[t,i] − book[t−1,i]|`
- short borrow 50 bp/yr on gross short notional (ETB assumed via the $20M ADV screen)

## Sign convention

Every formula's sign is **declared in advance from its mechanism** (see the formula
table in the result file). A formula whose design-window t-stat is negative under its
declared sign is DEAD — a sign flip is not a rescue.

## Gates

- **G0 mechanism**: one-sentence causal WHY per formula, stated before the run.
- **Lag-kill**: re-run every design survivor with one extra day of lag
  (entry at the open of t+2). A survivor that loses most of its edge is a
  staleness/publish-lag artefact and is KILLED.
- **Statistical bar**: N = (#formulas × #horizons) tested. Pooled expected max
  |t| under the null ≈ `sqrt(2 ln N)`. A formula is real only if its design t
  clearly beats that AND its **held-out** net Sharpe is positive after the cost
  model above.

## Anti-peeking commitment

The design run writes `NEWTERR_xs_equity_DESIGN.json` including the frozen pick list.
Only then is the held-out run executed. Held-out numbers are reported as-is,
including negative ones.
