# INVENT D0821 — cross-sectional equity factors, fresh structures

**28 new signals × 3 horizons = 84 cells. Zero survivors. Honest zero — and not a
near-miss: the design maximum did not reach the *mean* of its own null-max distribution.**

Date: 2026-08-21. Theme key `xsfactor`. Pre-registration (written before any design
number): `INVENT_D0821_xsfactor_PREREG.md`. Machine-readable: `INVENT_D0821_xsfactor.json`.
Script: `scripts/trading_bot/invent_d0821_xsfactor.py`.

---

## 1. The bar, and what the search actually produced

| | t-units | Sharpe units (5.6 y design) |
|---|---|---|
| within-theme, N = 84 | **2.98** | **1.26** |
| pooled with the 132 `NEWTERR xs_equity` cells that searched the same theme on the same panel, N = 216 | **3.28** | **1.39** |
| **best design cell, net** (`BETA_INSTAB` h=1) | **+0.78** | +0.33 |
| **best design cell, gross** (`FR_REV1` h=1) | **+2.32** | +1.04 |

`E[max|t|] ≈ √(2 ln N)`. The pooled 3.28 is the bar that applies: both searches are
answering one question — *does anything in the short-horizon US equity cross-section
work* — and they are being read together.

**The best NET result in the theme is t = +0.78.** That is not "below the bar"; it is
below the bar for N = 2. Nothing here needed a multiple-testing correction to be killed.
Even pre-cost, the largest gross t (2.32) sits under the within-theme bar.

Frozen picks: **0**. 24 of 84 design cells had a positive net t at all; 10 of 84 in the
held-out window.

## 2. What was tested, and why it is not the dead ledger

The theme brief named residual reversal, idiosyncratic-vol ranking, beta dispersion,
sector-relative momentum/reversal, correlation-breakdown baskets and Amihud tilts.
**Six of those, in their textbook form, were already dead on this exact panel** —
`REV1_RESID`, `LOWIVOL`, `LOWBETA`, `MOM20_RESID`, `AMIHUD`, `SIZE_ILLIQ` are in the
NEWTERR ledger with max net t = +0.89 across 132 cells. Re-running them would have been
theatre. So each named angle was rebuilt in a form the prior sweep did not contain:

| named angle | prior (dead) form | what was built instead |
|---|---|---|
| residual reversal | market-beta residual | **cross-sectional OLS residual** on beta, size, vol, peer-correlation and peer-hedge-beta, plus **statistical-sector** demeaning |
| sector-relative | *not tested — no sector labels exist in the panel* | **data-driven sectors**: PIT quarterly SVD → 10 PC loadings → k-means into 15 clusters |
| correlation breakdown | not tested | **top-10 correlated-peer baskets**, PIT, raw / z-scored / hedge-beta forms |
| idio-vol ranking | market-model σ level | multi-factor σ, sector-relative σ, σ **change**, and the scale-free **idio share of variance** |
| beta dispersion | β level | **down-minus-up beta** and **beta instability** (σ of rolling β) |
| Amihud | raw log-Amihud | **size-neutral** and **size-and-vol-neutral** Amihud, Amihud **change**, spread level, √-impact form |

No gates, no conditioners, no sub-universe restrictions — round 3's 0/107 result was
taken as settled.

The group machinery is point-in-time and is not noise: 39 quarterly refits, median 1533
names labelled, and **91.2 % pair-level cluster agreement between consecutive quarters**.
The clusters are stable objects; they simply do not pay.

## 3. Family by family

| family | cells | best net t | best gross t | best gross SR | median turnover | best break-even |
|---|---|---|---|---|---|---|
| beta-shape | 9 | **+0.78** | +0.96 | 0.40 | 0.06 | 51.2 bp |
| liquidity | 15 | +0.76 | +1.27 | 0.52 | 0.13 | 29.0 bp |
| peer-divergence | 18 | +0.56 | +1.99 | 0.90 | 0.40 | 9.2 bp |
| sector-relative | 21 | +0.25 | +2.07 | 0.93 | 0.44 | 8.1 bp |
| multi-factor residual | 12 | +0.11 | **+2.32** | **1.04** | 0.41 | 6.8 bp |
| idio-vol | 9 | −0.19 | +1.11 | 0.51 | 0.12 | 5.1 bp |

Read the last two columns together. **The families with signal have no room, and the
families with room have no signal.** Everything that generates gross alpha turns over
40–170 % of gross notional a day and breaks even at 5–9 bp; everything that is cheap to
hold (turnover 3–13 %) has a gross t under 1.3.

## 4. The one real finding: neutralisation buys Sharpe by cutting variance, not by
   earning more per unit of turnover

This is the part worth carrying forward. Factor-neutralising short-horizon reversal
**does** improve the gross Sharpe — and simultaneously makes the economics *worse*.

| h=1 form | gross SR | gross bp/day | turnover | **break-even one-way cost** |
|---|---|---|---|---|
| `REV1` raw (prior sweep) | +0.78 | 4.41 | 1.64 | **2.68 bp** |
| `REV1_RESID` market-beta (prior sweep) | +0.69 | 2.74 | 1.61 | 1.70 bp |
| `SEC_REV1` statistical-sector demeaned | +0.77 | 3.20 | 1.66 | 1.93 bp |
| **`FR_REV1` full multi-factor residual** | **+1.04** | 3.71 | 1.66 | 2.23 bp |
| `FR_REV1_Z` risk-normalised | +0.97 | 2.54 | 1.76 | 1.44 bp |
| `PEER_DIV1` peer-basket relative | +0.38 | 1.25 | 1.65 | 0.76 bp |

`FR_REV1` has the best gross Sharpe in the entire study (1.04, +33 % over raw `REV1`) and
a **lower** break-even cost than the raw signal it improves on. Neutralisation removed
factor variance from the denominator; it removed return from the numerator too. Against
a 5.0 bp modelled effective half spread plus 0.5 bp fees — an ~11 bp round trip on a
$20M+ ADV universe — every row above is under water by a factor of two to seven.

**Generalised, across both windows: every short-horizon cross-sectional reversal variant
tested breaks even between 0.46 and 6.6 bp per side, while 66/84 design cells and 61/84
held-out cells have positive gross t.** The gross alpha is systematically present and
systematically smaller than the spread. This is a *cost* wall at h=5 and *both* a cost
and a decay wall at h=1.

## 5. The held-out window: opened for one declared diagnostic, not for a rescue

Nothing cleared the design bar, so nothing was promotable and the held-out window could
not change the verdict. It was opened for exactly one pre-declared question (addendum in
the pre-registration, written before the run): **is the sub-spread gross alpha a
design-window artefact, or a structural fact?** Three readouts were declared in advance;
the full 84-cell held-out sweep is on disk but its maximum is deliberately not quoted as
a result.

**Readout 1–2 — `FR_REV1` gross persistence (design → held-out, 4.6 y):**

| | gross SR | gross t | gross bp/day | break-even | net SR |
|---|---|---|---|---|---|
| h=1 | +1.04 → **+0.20** | +2.32 → +0.42 | 3.71 → 0.76 | 2.23 → 0.46 bp | −2.63 |
| h=3 | +0.98 → +0.34 | +2.19 → +0.73 | 2.42 → 0.86 | 4.34 → 1.55 bp | −1.16 |
| h=5 | +0.89 → **+0.86** | +1.99 → +1.85 | 1.80 → 1.71 | 5.36 → 5.13 bp | −0.29 |

The answer is split and it matters. **At h=1 the gross alpha itself collapsed** (SR 1.04 →
0.20) — so the 1-day factor-neutral reversal was never a cost-blocked edge, it was a
decayed one. **At h=5 the gross alpha fully persisted** (0.89 → 0.86, break-even 5.36 →
5.13 bp) and is still net-negative, because its break-even sits *at* the modelled half
spread. That is a genuine cost wall, measured on virgin data, and it is the tightest
statement this programme has on the question: at the horizon where the signal survives,
the edge is worth about 5 bp a side and the spread is about 5 bp a side.

**Readout 3 — the five design-best cells, net, as-is:**

| | design net SR | held-out net SR | held-out net t |
|---|---|---|---|
| `BETA_INSTAB` h=1 | +0.33 | +0.28 | +0.60 |
| `BETA_INSTAB` h=3 | +0.33 | +0.30 | +0.65 |
| `BETA_INSTAB` h=5 | +0.32 | **+0.31** | +0.67 |
| `SPREAD_LEVEL` h=5 | +0.31 | −0.28 | −0.59 |
| `SPREAD_LEVEL` h=3 | +0.29 | −0.33 | −0.71 |

`BETA_INSTAB` (long names whose 60-day beta is least stable, on the hedging-difficulty
premium) is the only thing in the theme that is sign-stable across both windows, at
3–4 % daily turnover and a 43–51 bp break-even, with the lag-kill flat (gross SR +0.40 /
+0.40 / +0.38 at lag 0/1/2 — a slow characteristic tilt, not a staleness artefact).
**It is still not a finding.** t = +0.78 design, +0.67 held-out; a 0.3 Sharpe sleeve is
indistinguishable from zero on 10 years, and proposing it would be exactly the mistake
round 3 named. It is recorded here so the next round does not rediscover it and mistake
consistency for significance.

`SPREAD_LEVEL` flipped sign out of sample — the one design-window cell that behaved like
a classic search maximum.

## 6. Verdict

**The theme is noise.** Combined with the 132-cell `NEWTERR xs_equity` sweep, **216 cells
of short-horizon US equity cross-section have now been tested on this panel with zero
survivors** — and the ceiling is now understood rather than merely observed: the gross
alpha is real, small, and priced inside the spread of a $20M+ ADV universe. No basket
change is proposed. No leg is proposed. The ALIVE legs (T3, ETF-sibling RV, dual-class RV,
T7 ex-open, T12 CEF) are untouched by this work.

**Two things for the next round:**

1. **Do not re-mine the daily equity cross-section on free data.** The binding constraint
   is not signal discovery, it is the ~11 bp round trip. A 5-day factor-neutral reversal
   that persisted perfectly out of sample still lost, by about 1× its own edge.
2. **The self-test caught a real bug before the design run** — conditional up/down-day
   betas silently produced 0.000 coverage because a 250-day window contains only ~125
   qualifying days and the rolling primitive requires half the window. Any conditional
   rolling statistic added to this engine needs an explicit `minobs`. Coverage per signal
   is now part of the self-test output; keep it there.

## 7. Files

- `scripts/trading_bot/invent_d0821_xsfactor.py` — self-test / design / held-out
- `research/trading_bot/INVENT_D0821_xsfactor_PREREG.md` — pre-registration + held-out addendum
- `research/trading_bot/INVENT_D0821_xsfactor_SELFTEST.json` — harness validation, per-signal coverage
- `research/trading_bot/INVENT_D0821_xsfactor_DESIGN.json` — 84 design cells, lag-kill, zero picks
- `research/trading_bot/INVENT_D0821_xsfactor_HOLDOUT.json` — declared readouts + full sweep
- `research/trading_bot/INVENT_D0821_xsfactor.json` — machine-readable summary
