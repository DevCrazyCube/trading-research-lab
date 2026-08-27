# INVENT_0822B — futures/FX mechanical-roll & seasonal: FROZEN SHORTLIST

**Written 2026-08-22, BEFORE the held-out window (2019-01-01..2026-08-21) was scored by
`inv0822b_sweep.py holdout`.** Design window 2007-01-01..2018-12-31 only.

## Search size
- N = **42** formulas, sign-agnostic → 84 effective one-sided tries.
- Analytic bar: sqrt(2 ln 2N) = **t 2.977** (Sharpe 0.86 over 12.0y).
- **Measured, size-matched null** (circular-shift bootstrap, 2000 draws, weights fixed,
  turnover and cost line preserved exactly, correlation between formulas preserved):
  **E[max] = +0.608**, p95 = +0.849, p99 = +0.975, max = +1.138.
  For a calendar formula this is the right placebo: it destroys the alignment between the
  weights and the day-of-month and changes nothing else.

## Design result
Only family **Q** (month-end bond-index duration extension) produced anything.
Families **P** (FX month-end hedge rebalancing), **R** (commodity-index roll window weighted
by published index weight) and **S** (physical/regulatory seasonals) are flat: best P = +0.14,
best R = +0.55, best S = +0.56, all below E[max] = +0.61.

| pick | design net SR | vs measured null |
|---|---|---|
| `Q12_BONDME_AGG` — long AGG, last 2 bdays | **+1.082** | > p99 (0.975) |
| `Q03_BONDME_TLT_3D` — long TLT, last 3 bdays | +0.971 | ≈ p99 |
| `Q01_BONDME_TLT_2D` — long TLT, last 2 bdays (**a-priori mechanism formula**) | +0.947 | > p95 |
| `Q08_BONDME_IEF` — long IEF, last 2 bdays | +0.913 | > p95 |
| `Q04_BONDME_DURSPREAD` — long TLT / short SHY, last 2 bdays | +0.718 | < p95 |

**PRIMARY PICK: `Q01_BONDME_TLT_2D`.** Chosen on MECHANISM, not on the maximum: the last two
business days is the window the index-extension story specifies a priori. Q12/Q03 score higher
and are carried as secondary.

## Controls that must FAIL (they are in N)
- `Q10_BONDME_PLACEBO` (bd 12-13 of month, TLT): design +0.350.
- `Q15_BONDME_SPY_CTRL` (SPY, last 2 bdays — no bond-index mechanism).
- `Q14_BONDME_SHY` (1-3y, last 2 bdays — the duration floor): design net +0.413.
- `Q05/Q06` calendar-month conditioners: +0.478 / +0.389, i.e. conditioning HURTS (lesson 1 holds).

## Gates already passed on the design window (recorded before the held-out look)
| gate | result |
|---|---|
| gross-first (lesson 2) | gross +1.032 → net +0.947; cost is **8%** of gross; break-even **≈17 bp/side** vs a ~1 bp TLT half-spread. Cost does not bind. |
| ρ1(Δ) bounce gate (lesson 3) | TLT −0.041, IEF −0.043, AGG −0.112, TLT/SHY spread −0.037. All far above −0.35. Not a bounce artifact. |
| size-matched placebo (lesson 4) | circular-shift E[max] +0.608; **plus** a calendar placebo: over all 18 candidate 2-day windows in the month, on the untouched **45-year pre-sample 1962-2006** of ^TNX, the a-priori window bd_end 1-2 ranks **1 of 18**. |
| instant-vs-interval (lesson 5) | it is an INTERVAL: bd_end 1-2 +0.947, bd_end 1 alone +0.747, delayed bd_start 2-3 +0.644. It survives one session of delay. |
| free-feed durability (lesson 6) | TLT / IEF / AGG / ^TNX / ZN futures. Nothing exotic, nothing discontinuable. |
| bond-beta / drift | unconditional TLT drift explains **13%** of the month-end day return; a drift-neutral version (long month-end, short a matched notional of every other day) scores **+0.936**, i.e. unchanged. |
| orthogonal instrument, pre-sample | raw CBOE constant-maturity yields, no ETF and no fees: month-end 2-day yield fall vs rest of month — ^TNX **1962-2006 t +2.98**, 2007-2018 t +3.32, ^FVX and ^TYX the same; ^IRX (13-wk bill) **t +1.04, i.e. the duration floor is flat.** |

## Pass criteria for the held-out window (stated before it is read)
`Q01` is **REAL** only if all hold:
1. held-out **net** Sharpe > 0 and t > 1.5;
2. the placebo `Q10` and the control `Q15` do not out-score it;
3. the ^TNX held-out yield test keeps the same sign.
Anything less is logged as a characterised object, not a promotion.

## Standing honesty flag
The turn-of-month effect in Treasuries is a **PUBLISHED** phenomenon (Ogden 1987; the
Bloomberg/Lehman index month-end extension literature). This round did not discover it; it
re-derived it from the mechanism and put it through this programme's bar. It must be reported
as a *replication that cleared the bar*, never as an invention.
