# DEEPMINE `etf_structural_rv` — pre-registration

**Written and hashed BEFORE `deepmine_etfstruct.py --stage design` produced a single number.**
Nothing below may be changed once the hash is recorded; anything added afterwards is labelled
POST-HOC in the result document.

## 1. Sub-family

ETF **structural** relative value, deliberately **excluding same-index siblings** (SPY/IVV/VOO,
XLK/VGT, GLD/IAU, EFA/IEFA …), which `rv_sweep.py` already owns. Five structurally different
claims:

| group | claim | why it is a different object |
|---|---|---|
| **N** | ETF vs the sum of its own components | the only free stand-in for iNAV; the arbitrage is a creation/redemption, not a substitution between two funds tracking one index |
| **O** | overlapping-holdings pairs across **different** indices | the two legs are not the same claim, so a 1:1 notional hedge is wrong and a hedge ratio has to be estimated |
| **L** | leveraged / inverse decay, and the levered complex's close rebalance | the deviation is a *mechanical* consequence of the daily reset, not a liquidity imbalance |
| **C** | country ETF vs a NAV whose market has been shut for hours | the mispricing is created by the clock, not by flow |
| **P** | premium/discount as a **signal** on an ETF-only or component-only book | same information, different instruments — the honest robustness axis for N |

## 2. Data

* `research/data/rv_cache/*.npz` — Alpaca SIP 5-minute RTH bars, `adjustment=all`, 2021-01-04
  → 2026-08-15, ~130 symbols. Free tier, already cached; this run adds no new history.
* `research/data/rv_cache/borrow_screen.json` — `/v2/assets` for the traded account: shortable
  / easy-to-borrow, fetched 2026-08-20.
* `research/data/rv_cache/spread_proxy.json` — per-symbol half-spread proxy.
* **Known unavailable, stated up front rather than silently substituted:**
  * **Real iNAV / IIV is not obtainable free.** Alpaca returns zero bars for every pseudo-ticker
    probed (`SPY.IV`, `QQQ.IV`, `EWJ.IV`, `XLKIV`, …). Group N's component sum is a *proxy for*
    iNAV and is called that everywhere; it is not iNAV.
  * **Published index weights are not free**, so N's "component sum" uses equal, ADV-proportional
    or top-3-by-ADV weights, and the cached member list covers only part of each index
    (2 names of XLE, 33 of SPY's 500). The beta-hedged variants exist precisely because the
    replication is partial.
  * **Local-market index history is daily-only (Stooq) and is not tradable by a US retail
    account.** Group C therefore tests the *tradable* formulation — the US-listed country ETF
    alone — and does not pretend to trade Tokyo.
  * **ADR↔ordinary and holdco↔constituent maps are not free here.** Not tested. Absent, not zero.

## 3. Windows — the split is fixed here and not revisited

* **DESIGN: 2021-01-04 → 2024-12-31.** Every scoring, ranking and selection decision uses this
  window and nothing else.
* **HELD OUT: 2025-01-02 → 2026-08-15.** `--stage design` cannot address it. It is read exactly
  once, after §5's shortlist is written to disk, and only for the shortlisted names.

## 4. Costs — charged, not assumed

1. **Both legs' spreads.** Turnover is charged per symbol at that symbol's own half-spread:
   `max(1.0 bp, 2 × (half a cent / price))`, provenance
   `TICK_FLOOR_TIMES_ADVERSITY_NOT_A_QUOTE_MEASUREMENT`. The 1.0 bp floor means no leg is ever
   charged less than `rv_sweep.py`'s flat rung. Flat 1.0 / 2.0 / 2.5 bp rungs are reported as
   sensitivity.
2. **Regulatory**: 0.15 bp per unit of turnover (SEC §31 + FINRA TAF), every rung.
3. **Borrow**: configs that hold overnight pay B22G's measured ETB general-collateral median,
   **0.33 %/yr on short notional, per calendar day**. Intraday-flat configs pay zero borrow and
   that is a claim with a reason: US borrow fees accrue on overnight positions.
4. **Shortability is a constraint, not a price.** Every config reports the share of its short
   notional in names this broker will not lend. Screened 2026-08-20: **SDS, SH, SQQQ, TMV, TNA,
   TZA, USO, VIS are not shortable**; everything else in the universe is shortable and ETB.

## 5. The frozen selection rule

Let `B95` = the 95th percentile of the block-bootstrap max-Sharpe null (stationary block
bootstrap, block = 5 days, 800 resamples, demeaned daily NET pnl, the **same** day indices
across all configs so cross-config correlation is preserved).

**Shortlist** = configs satisfying **all** of:
  1. design `sharpe_net` > `B95`;
  2. `daily_turnover` ≤ 4.0 (gross notional turned per day);
  3. `n_days` ≥ 500;
  4. `unshortable_short_share` ≤ 0.10.
Ranked by design `sharpe_net`, **capped at 6**.

If fewer than three configs qualify, the top three by design `sharpe_net` are carried to the
held-out window anyway and are labelled **BELOW THE NOISE BAR** in the result document. Running
them is not a promotion; it is so the report can state what the held-out numbers actually were
rather than leaving a gap a later reader would fill with hope.

## 6. The verdict rule

A formula is **REAL** only if all of:
  * design `sharpe_net` > `B95`, **and**
  * held-out `sharpe_net` > 0 **net of the same cost model**, **and**
  * held-out `sharpe_net` ≥ 0.5, **and**
  * `unshortable_short_share` ≤ 0.10.

The **sub-family is noise** if no formula is REAL. That outcome is reported as the headline, in
the first line of the result document, with the full distribution beside it.

## 7. What would make this test worthless, declared in advance

* Reading the held-out window before §5's shortlist is on disk.
* Adding a formula after seeing design results and calling it part of N.
* Quoting the flat-1.0 bp rung as the headline because it is kinder than the per-symbol model.
* Reporting a levered-ETF config's Sharpe without its `unshortable_short_share` next to it.
