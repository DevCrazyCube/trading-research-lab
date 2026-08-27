# T3 — end-of-day pressure reversal on the auction rail: the held-out result

## VERDICT: **DEAD** — by the kill condition frozen before any data was fitted.

The rule failed exactly one of the three pre-registered gates, and it failed it by 1.2 percentage
points. It is dead all the same, because the threshold was written down first.

| pre-registered kill condition | held-out value | outcome |
|---|---|---|
| 1. net mean per night ≤ 0 | **+5.35 bp/night**, t = **+2.73** | passes |
| 2. label-permutation p ≥ 0.05 | **p = 0.0001** (10,000 permutations, floor of what they resolve) | passes |
| 3. **DSR < 0.95 at trials = 8** | **DSR = 0.9379** | **FAILS → DEAD** |

**Nominated next candidate: #2, ex-dividend drop-off executed close-to-close in the auctions**, as
the pre-registration named in advance. §7 states the caveat that has to be settled first, and it is
an owner-facing question.

---

## 0. Provenance

| artifact | value |
|---|---|
| pre-registration | `research/trading_bot/T3_PREREGISTRATION.md`, sha256 `401fd377ce1a6e3d60d618a86c36a7834bdafe81c0240e11540b9c038fe4f29f`, frozen 2026-08-16T21:18:39Z |
| frozen configuration | `research/trading_bot/T3_FROZEN_CONFIG.json`, sha256 `ad671e3df8a2a8ec6936aecde6dcceb796a3f3f4d8e1251287716660a2be9e6d` |
| held-out result | `research/trading_bot/T3_HELDOUT_RESULT.json` |
| exploratory diagnostics | `research/trading_bot/T3_DIAGNOSTICS.json` (**not** pre-registered; no verdict follows from it) |
| collection + evaluation code | `scripts/t3_pressure_reversal.py`, `scripts/t3_evaluate.py`, `scripts/t3_diagnostics.py` |

The pre-registration was written and hashed **before any return, signal or portfolio was computed**.
The design phase then ran on 2016–2021 alone and wrote the frozen configuration file; the held-out
command **refuses to run** if that file is absent, so it cannot choose a configuration on the spot.
The held-out period was evaluated once, after the freeze.

Statistics come from the T2 harness (`scripts/trading_bot/stats.py`) — `deflated_sharpe`,
`sharpe_variance_from_trials`, `permutation_test`, `moments`, `annualised_sharpe`, `max_drawdown`,
`cagr` — imported, not reimplemented.

---

## 1. The data actually assembled

| quantity | value |
|---|---|
| asset pool (active **and inactive**, NYSE/NASDAQ/AMEX/ARCA/BATS) | **14,724** symbols with monthly bars |
| point-in-time monthly universe screen (raw close > $5, dollar ADV > $20 M, top 500) | 128 months, **1,648** distinct symbols ever selected |
| official auction prints collected | **3,618,237** symbol-days |
| symbols with a corporate action on record | 1,312 |
| **nights in the panel** | **2,607** (1,468 design + 1,139 held-out) |
| **symbol-nights kept** | **1,242,737** |
| median cross-section per night | 477 names; 47 per decile |

Exclusions applied, identically in both periods: 28,943 symbol-nights for a missing 15:29/15:49/15:59
minute bar, 31,399 for a corporate action landing on the exit date, 421 for a missing opening auction
print, 22 days for an early close, 19 days too thin to form deciles.

**Friction, measured on our own instrument** (SIP quotes, 40 sampled trading days per period):

| period | median half-spread | p25 | p75 | p95 | symbol-days |
|---|---|---|---|---|---|
| design 2016–2021 | **1.13 bp** | 0.70 | 1.90 | 4.81 | 19,835 |
| held-out 2022–2026 | **1.43 bp** | 0.84 | 2.52 | 5.27 | 19,960 |

This is a first-party measurement, not a citation. It is the number charged on 100 % of capital at
entry; the exit leg is charged zero because it is a single-price auction.

**It has an independent corroboration that landed the same day.** The peer seat's B22B run
(`research/B22B_SLIPPAGE_RESULT.json`, 30 pinned days, 429 triggered stock-days) reports a **median
quoted spread of 3 bp** on its ORB most-actives universe. Doubling the half-spread measured here gives
**2.9 bp**. Different universe, different order type, different harness, same number — which is the
standard `FINDINGS.md` §8 asks for, since two indirect signals agreeing is not a measurement but two
direct ones are.

---

## 2. Design phase — 2016-01 → 2021-12, all eight declared trials

Every one of the eight was positive. That is itself a warning sign, and the deflation exists for it.

| window | cut | universe | net bp/night | t | annualised Sharpe |
|---|---|---|---|---|---|
| **10 min** | **10 %** | **top 500** | **+7.52** | **+5.88** | **+2.44** |
| 10 min | 10 % | top 300 | +7.63 | +5.11 | +2.12 |
| 10 min | 20 % | top 500 | +4.78 | +5.68 | +2.35 |
| 10 min | 20 % | top 300 | +4.93 | +5.08 | +2.10 |
| 30 min | 10 % | top 500 | +5.78 | +4.09 | +1.70 |
| 30 min | 10 % | top 300 | +6.23 | +3.73 | +1.54 |
| 30 min | 20 % | top 300 | +3.90 | +3.72 | +1.54 |
| 30 min | 20 % | top 500 | +3.35 | +3.73 | +1.54 |

Frozen by highest design-period net Sharpe: **10-minute signal, decile cut, top-500 universe**.
Cross-trial Sharpe variance across the eight: `5.678e-4` — the honest input to the deflation.

---

## 3. The held-out period — 2022-01-03 → 2026-08-14, run once

1,139 nights. One configuration. No refits.

| series | mean bp/night | t | annualised Sharpe | ann. return | max DD |
|---|---|---|---|---|---|
| **net, at the measured 1.43 bp half-spread** | **+5.35** | **+2.73** | **+1.29** | +13.5 % | −14.0 % |
| gross (zero cost — the B19P diagnostic) | +6.84 | +3.49 | +1.64 | +17.2 % | −13.3 % |
| equal-weight control, same nights | +2.97 | +1.41 | +0.66 | +7.5 % | −21.1 % |
| fade-buy decile **minus** control | +8.81 | +3.91 | +1.84 | +22.2 % | −11.4 % |
| control **minus** fade-sell decile | +4.87 | +2.14 | +1.01 | +12.3 % | −17.4 % |

Both legs contribute; the long (fade-buy) side is the stronger one. Skew −0.10, non-excess kurtosis
**12.3** — a fat-tailed nightly series, which matters below.

**Year by year, net:**

| 2022 | 2023 | 2024 | 2025 | 2026 YTD |
|---|---|---|---|---|
| +5.92 bp, t +1.27 | +5.52 bp, t +2.09 | +7.89 bp, t +2.31 | +5.82 bp, t +1.50 | **−0.62 bp, t −0.08** |

Positive in four of five calendar years and flat in the fifth. No single year carries it, and no
single year is significant on its own.

### The three gates

**Gate 1 — net mean > 0. Passes.** +5.35 bp/night, t = +2.73 over 1,139 non-overlapping nights.

**Gate 2 — label permutation. Passes decisively.** 10,000 permutations that shuffle *which stock gets
which signal label* within each night, holding the nights, the cross-section and the number of names
per side fixed. Observed +6.84 bp; null mean −0.018 bp, null sd 0.49 bp, null 95th percentile
+0.79 bp. **p = 0.0001**, the floor 10,000 permutations can resolve. The last ten minutes carry
information about the overnight return. That is not in doubt.

**Gate 3 — Deflated Sharpe. FAILS. DSR = 0.9379 against the pre-registered 0.95.**

| input | value |
|---|---|
| observed Sharpe (per night) | 0.0810 |
| expected-max Sharpe under the null, 8 trials | 0.0348 |
| z | 1.538 |
| **DSR** | **0.9379** |
| sensitivity at 24 trials | 0.8696 |

Two things push it under. The chance ceiling from eight trials eats 43 % of the observed Sharpe, and
the non-normality correction — kurtosis 12.3 — widens the denominator. Both are exactly what the
instrument is for. `FINDINGS.md` §5 records this programme's own +0.48 % dying at DSR 0.176 against a
chance ceiling of 0.01854; this is the same arithmetic reaching a much closer verdict.

### The T2 wiring check, reported so it is not mistaken for evidence

`stats.permutation_test` on the exposure path returns **p = 1.0** with `degenerate_exposure: true`.
That is correct and expected: this book is fully invested and dollar-neutral every night, so its
exposure is constant and permutes to itself. The instrument that bears on the claim is the
cross-sectional label permutation above — `FINDINGS.md` §5c, *permutation for classifiers*, and the
label assignment is the classifier.

---

## 4. The stress ladder — where the margin actually lives

| rung | mean bp/night | t | annualised Sharpe |
|---|---|---|---|
| zero cost | +6.78 | +3.46 | +1.63 |
| **h = 1.43 bp (measured)** | **+5.35** | **+2.73** | **+1.29** |
| 2h | +3.92 | +2.00 | +0.94 |
| h entry + h exit (the auction rail is **not** free) | +3.92 | +2.00 | +0.94 |
| **4h** | **+1.07** | **+0.55** | **+0.26** |

The entire edge is 6.8 bp per night against an entry friction of 1.4 bp. **Quadruple the spread and
it is gone.** This is the friction floor that has now killed five families in this programme, and the
survivor is standing much closer to it than its Sharpe suggests.

Note that the fourth rung — the one that prices T1's unperformed prerequisite **M0**, *do MOC/MOO
orders actually fill at the official print* — costs the same as 2h and leaves t = 2.00. M0 remains
unmeasured; that assumption is still outstanding.

---

## 5. Two exploratory diagnostics — NOT pre-registered, no verdict follows

Run after the frozen verdict, to explain it. They are labelled here and in
`T3_DIAGNOSTICS.json` because a number that was not frozen is not evidence.

### D1 — is it the bid-ask bounce? **No.**

The frozen rule enters at the 15:59 last *trade* print. The fade-buy leg is by construction the names
that just fell, whose last print sits disproportionately at the bid; marking those to an unbiased
opening auction manufactures microstructure that looks like alpha. D1 replaces the entry price with
the **official closing auction print** — a single-price auction, bounce-free — and leaves the signal
alone.

| | design 2016–2021 | held-out 2022–2026 |
|---|---|---|
| D1, bounce-free entry | +8.15 bp, t +6.38, SR 2.65 | **+6.07 bp, t +3.10, SR 1.46** |

The frozen rule's gross was +6.84 bp; bounce-free it is +6.07 bp. **The signal is real and roughly
0.8 bp of the gross was bounce.** This candidate does not die of a microstructure artifact.

### D2 — can the spread be dodged entirely? **No — that is where it dies.**

NYSE and Nasdaq stop accepting market-on-close orders at **15:50**. A signal measured to 15:59 can
therefore never be executed in the closing auction; the entry must cross the spread. The variant that
*would* be free on both legs uses only what is known before the cutoff — the 15:29 → 15:49 return —
entering MOC and exiting MOO, zero modelled spread on both sides.

| | design 2016–2021 | held-out 2022–2026 |
|---|---|---|
| D2, both legs on the auction rail | +2.26 bp, t +1.63, SR 0.68 | **+2.98 bp, t +1.38, SR 0.65** |

**The edge lives in the last ten minutes and does not survive being committed to nine minutes early.**
The structural cost advantage T1 ranked this candidate first for — the zero-spread rail — is only
available to a signal that is too old to be worth trading.

> **A lookahead I introduced and caught.** D2's first version ranked on the panel's stored 30-minute
> return, which ends at **15:59** — nine minutes of the future in an order that must be submitted by
> 15:50. It reported +6.47 bp, t +3.07 held-out, which would have made D2 look like the answer. The
> pre-cutoff return is recoverable exactly from the two stored windows,
> `(1+r30)/(1+r10) = p49/p29`; corrected, it is +2.98 bp, t +1.38. **The lookahead was worth more than
> half the result.** Recorded because `FINDINGS.md` §8 is right that these are found by checking, not
> by intending.

---

## 6. Deviations from the pre-registration, all of them

1. **Half-spread measurement window narrowed** from `[15:59:00, 16:00:00)` to `[15:59:59, 16:00:00)`.
   Forced: the quotes endpoint is symbol-major, so a truncated page set covers only the
   alphabetically-first symbols, and paging the full minute is ~30,000 quotes per liquid symbol per
   day. The narrower window is inside the registered one, is the instant T1 §5.1 named for the entry
   ("~15:59:5x"), and sits on the **conservative** side because quoted spreads widen into the close.
2. **January 2016 is not tradeable.** The screen for month *m* needs month *m−1*, and Alpaca's SIP
   history begins 2016-01 — there is no December 2015 to screen on. 19 nights are lost at the very
   start of the **design** period. The held-out period is unaffected. (Same species of error as the
   one T1 §2f found in B22B: a calendar assumption, not a data limit.)
3. **ETFs are in the universe.** The frozen rule said "every Alpaca `us_equity` asset", and Alpaca
   classes SPY, QQQ and similar as `us_equity`; they screen in on ADV. The rule was not changed after
   the fact to exclude them. T1 §2e notes ETF closing auctions are a negligible share of volume, so
   this is a live limitation for execution, not for the statistics.
4. **The universe's spread filter** (`median quoted spread < 10 bp`) was replaced by the top-500-ADV
   cut plus a measured, charged half-spread. That substitution was declared in the pre-registration
   itself, not adopted afterwards.

---

## 7. What this means, stated plainly

**The signal is real. The strategy is dead by the rule we froze.** Those are both true and neither
softens the other.

- Out of sample, over 1,139 nights, the last-ten-minute cross-sectional reversal predicts the
  overnight return at permutation p = 0.0001, and it is not a bid-ask-bounce artifact (D1).
- The net risk-adjusted level — Sharpe 1.29, DSR 0.9379 — **does not clear the chance ceiling implied
  by the eight configurations we admitted to trying**. The pre-registered threshold was 0.95. It came
  in at 0.9379.
- The margin is 6.8 bp of gross against 1.4 bp of measured entry friction, and 4× the spread erases
  it. The one execution route that removes the friction entirely (both legs in the auctions) requires
  committing before 15:50, and **the signal is not there yet at 15:50** (D2: t = 1.38).

Calling this "alive because 0.9379 is nearly 0.95" would be the single most expensive thing this
document could do. `FINDINGS.md` §6 records that **every retracted claim in this programme was
flattering**. The rule was written down first precisely so that a near miss would not be argued into
a pass.

**Nominated next candidate, as the pre-registration named in advance: #2 — ex-dividend drop-off,
executed close-to-close in the auctions.** Both of its legs really are auction prints, so its modelled
friction is genuinely zero rather than 1.4 bp, and the data (≈25,000 cash dividends, 2016 → present,
universe-wide, delisted included) is already collected in this run's cache. Its blocking question is
unchanged and is **not mine to decide**: a taxable US retail account receives the dividend as ordinary
income, so the pre-tax edge must exceed the tax differential or the strategy is negative after tax
while looking positive on price data. **That arithmetic must be settled before the backtest is
believed, and it is an owner call.**

### One scope question for the owner, with a recommendation

The pre-registration's kill list is binary and it has fired, so #1 is dead as frozen. There is a
legitimate separate question — *not* a re-scoring of this result — about whether a **new**
pre-registration of the same mechanism is worth one more slice: the failure is on the deflation only,
the signal is independently confirmed, and the honest fix is more evidence rather than more search
(the trial count is what the chance ceiling is built from, so adding configurations makes it worse,
not better). **My recommendation is to proceed to #2 as pre-registered, and to keep #1 on the shelf
as a documented near-miss rather than reopen it** — but that is a scope call, and it is the owner's.

---

## 8. What this document does not claim

- **Nothing here authorises execution.** Paper or real, that gate is the owner's. No order was
  submitted in the course of this test; the only endpoints touched were market-data reads plus the
  read-only `/v2/assets` and `/v2/calendar`.
- **M0 is still unperformed.** Whether an MOC/MOO order actually fills at the official print is
  assumed, not measured. The fourth stress rung prices being wrong about it.
- **Survivorship is reduced, not eliminated.** Alpaca's inactive list is a partial record of what once
  listed; a name absent from it is invisible to this test.
- **Borrow is modelled at 30 bp/yr GC** and the short leg's borrowability is assumed. Alpaca's
  `easy_to_borrow` flag is a live snapshot with no history (T1 §2b), so it cannot be backtested.
- **Queue position, partial fills and size-dependent impact are not modelled.**
