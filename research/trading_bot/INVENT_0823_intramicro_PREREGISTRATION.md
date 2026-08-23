# Pre-registration — INTRADAY MICROSTRUCTURE BEYOND THE AUCTION (0823)

Written **before** any design-window number for this theme existed on disk. Committed ahead of
`INVENT_0823_intramicro_design.json`.

## 0. Why this is not the intraday-RV sweep again

`SWEEP_intraday_rv` (98 formulas, 2026-08-20) already killed the *relative-value / mean-reversion*
half of intraday: pair-z, ETF-vs-basket, PCA residual, high-frequency XS reversal. Its verdict was
specific and it constrains this round: **the gross edge there was real (+6.9 design, +5.4 held-out)
but the turnover was 20–130 units/day, so the break-even was 0.01–0.3 bp/turnover against a 1.15 bp
charge.** The signal was the bid-ask bounce.

This round therefore refuses the entire high-turnover branch. **Every formula here trades at most
3 units of turnover per day** (one entry, one exit, occasionally a second entry), holds for hours,
and is *directional-in-the-cross-section* rather than a spread convergence. At turnover 2.0/day the
1.0 bp rung charges 2.3 bp/day; a dollar-neutral mega-cap book has ~40–60 bp/day of return sd, so
the cost drag is ~0.6–0.9 Sharpe — a hurdle, not a 37× wall. That is the only region of intraday
left where an answer other than "friction" is possible.

Formulas deliberately NOT re-tested because the prior sweep or the corrected basket state already
settled them: any pair/sibling ETF convergence (ETFRV is a 15:45 shared-price artefact), any
sub-hour holding period, any config with turnover > 3/day, plain overnight-gap reversal
(`D1_gap_rev_mega`), ex-dividend (T7 is a data bug), auction-imbalance (died on ρ1).

## 1. Data

**Panel A — `research/data/rv_cache/*.npz` (Alpaca SIP 5-minute bars, `adjustment=all`, RTH).**
2021-01-04 → 2026-08-14, 1410 sessions, 78 slots/session, 132 symbols. Rebuilt by
`scripts/trading_bot/im0823_panel.py` into a `(D, 78, S)` cube carrying **open, high, low, close,
vwap, dollar-volume and trade-count** — the last three fields are what make the order-flow
sub-family possible and were not used by the prior sweep.

Universes drawn from Panel A:
- `MEGA` — the 35 single names (AAPL, MSFT, NVDA, AMZN, GOOGL, GOOG, META, TSLA, AVGO, BRK.B, JPM,
  XOM, UNH, JNJ, V, PG, HD, MA, COST, WMT, BAC, CVX, LLY, ABBV, MRK, PEP, KO, ORCL, CRM, AMD, INTC,
  NFLX, ADBE, CSCO).
- `LIQETF` — 40 unlevered, non-same-claim ETFs (broad, sector, style, region, bond, commodity).
  Levered/inverse funds (SSO/SDS/UPRO/SPXU/TQQQ/SQQQ/TNA/TZA/TMF/TMV/QLD/SH/PSQ) are excluded, and
  only one fund per same-claim cluster is kept, so no config can accidentally re-discover the
  sibling-pair artefact.

**Panel B — `research/data/auc0822_cache/panel.npz`.** Point-in-time top-500-ADV universe (1611
symbols ever, median 497/day), 2016-01-04 → 2026-08-14, with RAW 15:29 / 15:49 / 15:59 minute
prices plus the official open and close and a trailing $ADV. Used **only** by the late-day
sub-family G, which needs breadth more than it needs bar granularity. All Panel-B returns are
strictly *within one session* (open → 15:29 → 15:49 → close), so raw unadjusted prices are safe;
no overnight return is ever computed on Panel B.

**Survivorship / point-in-time.** Panel A is survivorship-biased by construction (Alpaca serves
today's symbols) and its prices are retroactively adjusted, so no config filters on a price level.
Panel B *is* point-in-time in membership (a symbol is in the universe on a day iff it printed a
15:59 bar that day) and is the honest breadth check on Panel A's survivor set.

## 2. Windows — frozen

| | |
|---|---|
| DESIGN | 2021-01-04 → 2024-12-31 (1005 sessions, both panels) |
| HELD OUT | 2025-01-02 → 2026-08-14 (405 sessions, both panels) |
| PRE-SAMPLE (Panel B only, reported after freeze, never used for selection) | 2016-01-04 → 2020-12-31 |

The held-out window is not read until the shortlist is written to disk and committed. The
Panel-B pre-sample is declared here so that reporting it later is not a post-hoc window search;
it may not promote or demote anything.

## 3. Execution convention — the anti-bounce design

Bounce (ρ1 of Δspread) is what killed auction-imbalance and manufactured the ETFRV leg. On a
5-minute bar cube the equivalent discipline is a **realistic later fill plus a one-bar-gap
re-entry test**:

- A formula observes bars `0..s` only (their opens, highs, lows, closes, volumes, trade counts).
- **PRIMARY fill: the VWAP of bar `s+1`.** The last observed price is the close of bar `s`; the
  fill is the volume-weighted average of the *next* five minutes, i.e. a different set of prints
  ~2.5 minutes later on average. Signal and fill never share a print.
- **GAP TEST (mandatory gate): the VWAP of bar `s+2`** — one additional full bar of delay, fill
  ~7.5 minutes after the last observed close. A signal that is really the bid-ask bounce, a stale
  print, or a one-bar continuation of the signal bar loses most of its edge here.
- **EXIT: the VWAP of bar 77** (the 15:55–16:00 bar) for every hold-to-close config. The exit is
  unconditional, so it carries no signal and cannot manufacture edge.
- Panel B: signal from the open→15:29 leg, **primary fill at the 15:49 print (20 minutes later)**,
  **gap test at the 15:59 print**, exit in the **closing auction** at `pc`.
- Every config is flat at every session close. Borrow = 0, and that is exact, not an assumption.

**Gap gate, frozen now:** a config is only eligible to be a candidate if its design net Sharpe
under the GAP fill is **≥ 0.5 ×** its net Sharpe under the PRIMARY fill *and* is positive. A
config whose edge lives in the first bar after the signal is reported as a bounce artefact and
is disqualified regardless of how large its primary number is. **A high primary Sharpe with a
collapsed gap Sharpe is evidence against the formula, not for it.**

## 4. Weights and cost

- Every config produces a raw score per symbol per day. Scores are cross-sectionally **demeaned**
  (dollar-neutral) and then **L1-normalised so that Σ|w| = 1** (gross exposure 1.0). Turnover is
  therefore 2.0/day for a single-entry config and 3.0/day for the two-entry config.
- Cost rungs **0.5 / 1.0 / 2.0 / 2.5 bp per side** on `|Δw|`, headline **1.0 bp**, plus
  **0.15 bp per unit of turnover** for SEC 31 + FINRA TAF. Panel B's closing-auction exit leg is
  charged **0 bp of spread** (M0 measured the official print on 99.96% of top-500 symbol-days)
  but still pays the 0.15 bp fee.
- Cost provenance: `ADVERSE_PROXY_FOR_AN_UNMEASURED_LEG`. The repo's measured liquid-name close
  half-spread is 1.13 bp (T3, 19,835 symbol-days); Dyhrberg et al. (JFE 168, 2025) put the liquid
  retail taker at 2.5 bp before price improvement. 1.0 bp headline is optimistic-but-defensible
  for mega-caps at midday and the 2.5 bp rung is the pessimistic bound.

## 5. The formulas — 28, frozen

Sign-flipped pairs are counted as two formulas each (they consume two draws of the multiple-
testing budget and are counted that way; the bootstrap null handles their anti-correlation
correctly because it resamples the same day indices for every config).

**A. Opening drive (5)** — does the first 15–30 minutes of *intraday* tape predict the rest of the
session, cross-sectionally?
`A1_OD30_CONT` (first-30min return, s=5, long high) · `A2_OD30_FADE` (−A1) ·
`A3_OD15_CONT` (s=2) · `A4_OD30_CONT_RESID` (first-30 return residualised on a 60-day rolling beta
to the universe-mean first-30 return) · `A5_DRIVE_EX_GAP` (first-30 return **minus** the overnight
gap — the part of the drive that is not the gap; deliberately orthogonal to `D1_gap_rev_mega`).

**B. Order-flow / trade-size microstructure (5)** — new fields, not price-reversion.
`B1_OFI_MORN_CONT` (Σ close-location-value × dollar-volume over bars 0..17, normalised by Σdvol;
s=17) · `B2_OFI_MORN_FADE` (−B1) · `B3_TRDSIZE_TILT` (average trade size dvol/n over bars 0..17
as a z-score against the same symbol's own trailing 20-day same-window median, multiplied by the
morning return — "institutional participation amplifies the move") · `B4_VOLFRONT_DRIVE`
(front-loading of the day's volume vs the symbol's own 20-day norm, × morning return) ·
`B5_NTRADE_ACCEL` (trade-count intensity of bars 12..17 vs bars 0..11, × morning return).

**C. VWAP deviation with a later fill (4)**
`C1_VWAPDEV_MID_REV` (s=41, score = −(close/running-VWAP − 1)) · `C2_VWAPDEV_MID_CONT` (−C1) ·
`C3_VWAPDEV_1030_REV` (s=11) · `C4_VWAPDEV_TWOLEG` (half weight at s=11, half at s=41; turnover 3).

**D. First-hour range breakout (4)**
`D1_ORB_BREAK_XS` (OR = high/low of bars 0..11; at s=23 score = (close−OR mid)/OR range, zeroed
inside the range) · `D2_ORB_FADE_XS` (−D1) · `D3_ORB30_BREAK` (OR from bars 0..5, decision s=11) ·
`D4_ORB_EXTENSION` (distance *beyond* the OR edge in OR-range units, 0 inside; s=23).

**E. Volume-profile value area (4)**
`E1_VA_REJECT` (20-bin dollar-volume profile over bars 0..23; 70% value area around the POC;
short above VAH, long below VAL, flat inside; s=23) · `E2_VA_ACCEPT` (−E1) · `E3_POC_MAGNET`
(score = (POC − close)/day range, s=23) · `E4_PDPOC_MAGNET` (previous session's POC as the magnet,
decision at s=5).

**F. Late-day drift, Panel A (3)**
`F1_LD_CONT` (s=69 ≈ 15:15, score = open→close_s return, entry bar 71, exit bar 77) ·
`F2_LD_REV` (−F1) · `F3_LD_VWAPDEV_REV` (s=69, score = −(close/day-VWAP − 1)).

**G. Late-day drift, Panel B breadth (3)**
`G1_LD500_CONT` (score = open→15:29 return over the point-in-time top-500; fill 15:49; exit at the
closing auction) · `G2_LD500_REV` (−G1) · `G3_LD500_CONT_TOP150` (G1 restricted to that day's 150
highest-$ADV names).

## 6. Null hypotheses — both are computed before anything is called real

1. **Size-matched placebo / best-of-N bar.** Stationary block bootstrap (block = 5 sessions, 2000
   resamples) of each config's *demeaned* daily net PnL on the design window, drawing the **same
   day indices for every config** so the sweep's internal correlation survives. The bar is the
   **95th percentile of the best-of-28 design Sharpe under H0**. `sqrt(2 ln N)/sqrt(years)` is
   reported beside it as a sanity check only; the analytic number is known to understate by ~2× on
   overlapping books and is not the operative bar.
2. **ADV-slot signal permutation** (the cross-sectional null; rotate-the-returns is broken and is
   not used). For each config reaching the top of the design ranking, symbols are bucketed into
   ADV deciles *within each day*, the score vector is permuted **within** each bucket, and the
   whole backtest is re-run. 500 permutations. This destroys the symbol↔score mapping while
   preserving the day, the ADV/liquidity profile and the score distribution. Reported as a
   one-sided p-value.

## 7. Selection rule — FROZEN

A config is a **candidate** iff **all four** hold on the design window:

1. design net Sharpe at the 1.0 bp rung **> bootstrap best-of-28 p95**;
2. **gap gate** of §3 passes (gap net Sharpe ≥ 0.5 × primary net Sharpe, and positive);
3. ADV-slot permutation p **< 0.05**;
4. design **gross** Sharpe also clears the gross best-of-28 p95 (gross first, per the standing rule).

At most the **top 3** candidates are run on the held-out window. **If nothing clears, the theme is
reported as NOISE**; the top 3 by design net Sharpe are still run out of sample, labelled
explicitly as a documented negative control, and none of them may be promoted.

A candidate is **REAL** only if: design bars cleared (all four), **and** held-out **net** Sharpe is
positive at the 1.0 bp rung, **and** the held-out gap-fill number is also positive.

No config is re-specified, no parameter re-tuned, no window moved, and no formula added after the
first design number is read. If a formula turns out to be numerically identical to another, that
is disclosed and the effective N is corrected downward rather than the duplicate being deleted.
