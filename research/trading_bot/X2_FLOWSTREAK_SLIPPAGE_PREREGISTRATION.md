# X2_FLOWSTREAK — Perp Taker-Slippage Pre-Registration (SIZE / KILL)

**Frozen:** 2026-09-01, before any slippage number is computed. Locks the method and the decision rule so
the verdict cannot be reverse-engineered from the measurement. This is the one measurement the repo's own
freeze demands before X2_FLOWSTREAK can be sized: *"size 0 until (a) perp taker slippage is measured from
`bookdepth` and (b) corr(L5, L6) is measured"* (`FORMULA_SWEEP_MASTER.md:274`).

## What is being decided
X2_FLOWSTREAK is the single formula (1 of 598) that survived the pooled multiple-testing correction:
cross-sectional quintile book on 24h Binance USD-M taker-flow one-sidedness, top-50 perps, 24h hold;
virgin 2025-01→2026-08 **net +2.31 @5.5 bp/side, +0.54 @15 bp/side, breakeven 17.9 bp/side**
(`FORMULA_SWEEP_MASTER.md:139,197`). It is logged at risk budget 0.0 pending this measurement
(`BASKET_FORWARD_PREREGISTRATION.md:541`). **The entire question is whether a real rebalance fills inside
the 17.9 bp/side breakeven.** Nothing else about the signal is re-opened.

## Signal + book (frozen, reused — NOT re-derived here)
- Feature: `flowstreak = roll_mean(sign(2·takerBuyQuote − quoteVol) > 0, 24h)` per perp
  (`perpmicro_sweep2.py:166`). Cross-sectional quintile book: long top 20%, short bottom 20%; point-in-time
  top-50 by trailing-7d quote volume; 24h hold; 24h rebalance clock.
- The rebalance events (timestamps, per-name target weights) are taken verbatim from the frozen book
  construction; the slippage layer is added on top and does not touch the signal.

## Data — FREE FIRST, pay only for what free cannot give (this is the owner's spend gate)
1. **Primary (free): Binance USD-M `bookDepth`** — `timestamp,percentage,depth,notional`, ±1%/±2%/±3%/±5%
   levels. Reuse the existing loader `orphanflush_depthq.py::load_bookdepth_band1_perbar` and cache
   `research/data/orphanflush_cache/bookdepth/` (264 perp symbols, already cached **2023→2024-12-31**).
   The held-out window (2025-01→2026-08) is **also free** and will be downloaded from data.binance.vision
   as a **detached background job** (never inside an agent, per the no-crawls rule).
2. **Model-free cross-check (free): `aggTrades`** — measure the realized price impact of actual taker
   market orders of size comparable to the per-name rebalance, on a random subsample of rebalance events.
   Used to validate the ±1%-band model below.
3. **Paid fallback (owner authorization required): Tardis.dev L2 book snapshots** — bought ONLY for the
   minimum window needed, and ONLY if the ±1% band cannot resolve the estimate to a decisive margin of the
   17.9 bp breakeven. No purchase, no API key used, without the owner's explicit go.

## Slippage model (frozen)
Per rebalance, per name: `trade_notional(i,t) = AUM · |leg_weight(i,t)| / (one side)`. The ±1% book notional
`B(i,t) = notional(pct=−1) + notional(pct=+1)` (median over the bar's snapshots, causal) is the depth
available within 100 bp of mid. Under a **uniform-density-within-±1%** book-shape assumption, walking the
book to fill `trade_notional` costs, per side:

    slippage_bp(i,t) ≈ 100 · (trade_notional / B) · 0.5     for trade_notional ≤ B   (linear walk, mean fill)
    slippage_bp(i,t) ≈ 100                                    for trade_notional > B  (exhausts ±1%; treated as ≥100 bp)

plus the taker fee (Binance USD-M taker 4.5 bp; 5.0 bp assumed) and half the observed bid/ask spread. The
uniform-density assumption is the stated model; the `aggTrades` cross-check (data source 2) is what tests
whether it is optimistic or conservative, and the paid L2 (source 3) is what removes the assumption if the
verdict lands within model error of 17.9 bp.

## Output
The **capacity curve**: per-side all-in cost (slippage + fee + half-spread) as a function of book AUM, and
the held-out net mean return re-charged at that per-side cost, computed separately for the 2025 and 2026
sub-windows.

## Decision rule (frozen, evaluated at N = the full held-out rebalance set)
Let `c(AUM)` = median per-side all-in cost at book AUM; the signal's virgin gross is +3.34, breakeven 17.9 bp/side.
- **KILL** if `c(AUM_min) ≥ 17.9 bp/side` at the smallest tradeable book (AUM_min = $100k), **or** the
  held-out net mean is < 0 after cost on **either** the 2025 or 2026 sub-window.
- **SIZE** (recommend promotion off risk-budget 0.0) if at a target `AUM ≥ $250k` the held-out net mean is
  > 0 with t > 2 on **both** sub-windows, **and** `corr(L5, L6) < 0.7` (the second unmet gate, measured
  jointly — a sized leg cannot duplicate L5).
- **SIZE-DOWN** to the largest AUM where the SIZE conditions hold, if they hold at AUM_min but fail at $250k.
- A SIZE verdict on the ±1%-band model authorizes only a **small live-sized paper/forward test**, never
  full sizing, until confirmed against L2 (paid) or realized fills — the model is an estimate, not a fill.

## Honest limitations (recorded up front)
- ±1% bands are 100 bp granularity — 5.5× coarser than the 17.9 bp we must resolve; the estimate leans on
  the uniform-density assumption. This is exactly why the aggTrades cross-check and the paid-L2 fallback
  exist, and why a marginal SIZE is provisional.
- Slippage measured on the design-era cache (2023–2024) is a proxy for liquidity; the held-out download
  (2025–2026) is the rigorous measurement and the one the decision rule is evaluated on.
- This measures cost only. It does not re-validate the signal, and it inherits the "one window, one regime"
  caveat (`FORMULA_SWEEP_MASTER.md:335`).
