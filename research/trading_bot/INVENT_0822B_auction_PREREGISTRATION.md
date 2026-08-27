# INVENT_0822B — AUCTION IMBALANCE AS A SIGNAL SOURCE — PRE-REGISTRATION

**Written before any design-window statistic was computed.** Date: 2026-08-22.

## Theme
The closing/opening single-price call auction is a *free, ~zero-spread rail* (M0: official
closing print on 99.96 % of top-500-ADV symbol-days, median $37 M). Free SIP history does not
publish the exchange **imbalance feed**, but it publishes the **prints**. The revealed
imbalance is therefore reconstructed as the *dislocation of the official print from the last
free continuous reference*:

```
d_t   = ln( C_t  / P59_t )      close-auction dislocation  (revealed close imbalance)
q_t   = ln( O_t  / C_{t-1} )    open-auction gap
e_t   = ln( P59_t / P49_t )     drift over the imbalance-PUBLICATION window (15:50 feeds)
f_t   = ln( P49_t / P29_t )     drift BEFORE imbalance publication
x_t   = ln( C_t  / O_t )        print-to-print day return
u_t   = ln( O_t  / P59_{t-1} )  total off-hours move
```

C/O = official auction prints, P29/P49/P59 = raw SIP 1-minute closes at 15:29/15:49/15:59 ET.

## Legality constraint (declared up front, and it is binding)
The MOC/LOC cut-off is **15:50 ET**. Therefore:
* Any signal containing `P59_t` or `C_t` **cannot** be used to enter at `C_t`. It may only be
  used to enter at the **next opening auction** `O_{t+1}`.
* Signals usable for an entry at `C_t` are restricted to information complete by 15:49:
  `f_t`, `ln(P49_t/C_{t-1})`, and anything dated `t-1` or earlier.

Two disjoint formula blocks follow from this, and only these cells are eligible:

| block | entry | exit | outcomes |
|---|---|---|---|
| **S** (MOO entry, signal dated t) | `O_{t+1}` | `C_{t+1}` or `O_{t+2}` | `DAY_{t+1}`, `OO_{t+1}` |
| **M** (MOC entry, 15:50-legal signal) | `C_t` | `O_{t+1}` or `C_{t+1}` | `ON_t`, `CC_t` |

**Consequence, noted before running:** by construction **no eligible cell shares a price
between its predictor and its outcome**, so the bid-ask-bounce manufacture of gross
significance is structurally impossible here. The ρ1(Δ·) diagnostic is still computed and
reported for every dislocation series.

## Formula grid (N pre-declared)
Block S predictors (18): `d`, `e`, `f`, `e−f`, `d − mean5(d)`, `d − mean20(d)`, `d/std60(d)`,
`d49 = ln(C/P49)`, `q`, `u`, `q − d_{t-1}`, `x`, `d + d_{t-1}`, `sign(d)√|d|`, `d − d_{t-1}`,
`e + d`, `mean5(d)`, `print-vs-continuous daily divergence`.
× 2 outcomes = **36**.

Block M predictors (9): `f`, `d_{t-1}`, `q`, `q − d_{t-1}`, `u`, `mean5(d)_{t-1}`, `x_{t-1}`,
`ln(P49_t/C_{t-1})`, `d_{t-1} + q`. × 2 outcomes = **18**.

**N = 54.** Analytic bar √(2 ln 54) = **2.807**; two-sided (each formula is scored with its own
sign, so 108 effective) √(2 ln 108) = **3.061**.

## Portfolio construction (fixed, no variants)
Cross-sectional z of the predictor within each day, winsorised at ±3, demeaned (dollar-neutral),
scaled to Σ|w| = 2. Return = Σ w_i r_i. Daily series. No regime conditioning of any kind.

## Universe (point-in-time, no screen invented)
Symbol-days that have a 15:59 minute bar in the cached T3 collection — that collection *is* the
point-in-time top-500-ADV screen, and is exactly the M0-measured liquid tier. Additional
disclosed filters: price ≥ $3; drop symbol-days flagged by the corporate-action cache (t−1, t,
t+1); drop |overnight gap| > 20 % or |print-to-print day| > 25 % as a raw-price split guard;
require ≥ 50 usable names on the day.

## Costs
Gross = 0 bp (the bar must be cleared on gross first). Net charged on the **M0-measured auction
rail**: half-spread 0, plus the M0 `auction_non_fill_provision` for the tier, plus a flat
commission rung. Reported at c ∈ {0.0, 0.5, 1.0} bp per side per unit notional; turnover is the
actual Σ|Δw| for holds that persist and 2Σ|w| for flat-between legs.

## Windows
**Design 2016-01-04 → 2021-12-31.** **Held-out 2022-01-01 → 2026-08-14, untouched until the
design-window selection below is fixed.**

## Selection rule (fixed now)
Rank design cells by |gross t|. Carry to held-out **only** cells whose design gross |t| exceeds
BOTH (a) the analytic two-sided bar 3.061 and (b) the size-matched placebo 95th percentile of
max|t|. If no cell clears both, the theme is reported as **NOISE** and the held-out window is
still evaluated for the top-3 by design |t| purely to document the failure — those numbers
carry no promotion claim.

## Null measurement (size-matched placebo)
300 draws. Each draw applies one random circular **time shift** (30 ≤ k ≤ D−30 days) to the
signal matrix of every formula, preserving the cross-sectional structure, the per-symbol
autocorrelation and the return panel exactly, and destroying only the signal↔return alignment.
All 54 formulas are re-scored on each draw; the draw's statistic is max|t|. Reported: median and
95th percentile of that max, against the analytic 3.061.

## Promotion
Real only if: design gross |t| beats BOTH nulls **AND** held-out net (on the auction rail) is
positive and same-signed **AND** the ρ1 diagnostic does not indicate bounce. Anything else is an
honest zero.
