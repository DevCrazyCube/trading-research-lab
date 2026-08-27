# T25 — POWER GATE: what a free two-venue perp panel must be able to SEE before it is allowed to answer

**Candidate on trial:** `NONDIRECTIONAL_INCOME_SHORTLIST.md` (T21) **rank 3 — cross-venue perpetual
funding differential**, Hyperliquid vs Binance USD-M, same coin, no spot leg. This is the
highest-ranked mechanism in that survey that is **not already killed**: rank 1 and rank 2 died in
`FUNDING_CARRY_VALIDATION.md` (T23, dead by insufficient power), rank 6 died in
`CME_BASIS_PROBE.md` (T24, dead by insufficient power), rank 4 is the equity variance-risk premium
whose harvestable form died in T21 §4b on this programme's own N1 null, and rank 5 (stablecoin
depeg) is excluded by the task's own dead list.

**Status: written and hashed BEFORE the census ran and before any T25 profit-and-loss or dispersion
number existed.** At the moment this file's hash was taken,
`research/trading_bot/T25_POWER_CENSUS.json` and `research/trading_bot/T25_RESULT.md` did not
exist, and no Hyperliquid funding history had been downloaded.

This document follows `T23_POWER_GATE.md` deliberately, including its rule: *state the threshold and
the consequence in the same sentence, and name the ONE binding gate.*

---

## 0. The mechanism, and why it is not a re-run of a killed one

A perpetual swap's funding rate is set by each venue **from its own book**. The same coin therefore
funds differently on two venues. Long the cheap-funding venue's perp and short the rich one's and
**the delta is exactly zero — there is no spot leg, no borrow, no basis convergence** — and you
collect the difference.

**How this differs from the three carry deaths.** T23/`FINDINGS.md` §5d killed the harvest of the
funding **level** (long spot / short perp, one venue). T24 killed the same level on the CME rail.
This candidate harvests a **difference between two venues' levels**, and its risk is not the
level's risk: what you are paid for is **bearing the failure of TWO venues simultaneously**, plus
the correlation of their margin calls. The payment source is the same instrument; the estimand,
the risk and the accessibility are not. That is why T21 ranked it separately, and it is the only
live mechanism in T21 §5 with `D ≥ 4`.

---

## 1. What was probed BEFORE this gate was written (structural inputs only, no P&L)

| probe, 2026-08-19 | result |
|---|---|
| Hyperliquid `POST /info` `meta` | **232 perps**, of which **55 carry `isDelisted: true`** — the venue's own metadata retains dead names |
| Hyperliquid `fundingHistory` | free, keyless, **HOURLY**, paginated 500 rows/call. Earliest print for BTC/ETH/SOL/DOGE/ATOM is all **2023-05-12 00:00 UTC** |
| Binance USD-M survivorship-complete panel (already on disk, built and hashed by T23) | `research/data/t23_cache/panel/funding.csv`, **920 symbols, 2,721,205 prints, 2020-01-01 → 2026-07-31** |
| coins on **both** venues (incl. `k`/`1000` prefix mapping) | **214**, of which **41** are HL-delisted today |
| **Hyperliquid top-of-book half-spread**, live, 65 screened names | **median 0.85 bp** (p75 1.35, p90 1.95) |
| **Hyperliquid impact-price half-spread** (size-aware, ≈\$20 k notional), same names | median **6.05 bp** (p75 11.28, p90 14.71) |
| **Hyperliquid top-20 depth, thinner side**, same names | **median \$33,309** (p25 \$20,988) |

**The joint span of the two venues is therefore 2023-05-12 → 2026-07-31 = 1,176 days = 3.220
years, and that is the entire life of the younger venue.** No paid or free source extends it,
because Hyperliquid did not exist before it.

---

## 2. The estimator whose power is being censused

An **equal-weight top-N book of cross-venue funding-differential positions**, one per coin (long the
cheap-funding venue's perp, short the rich one's, matched notional), selected on **trailing realised
differential**, rebalanced **monthly**, from a **point-in-time liquidity-screened** universe, net of
the §5 charges, minus the **by-year** 3-month T-bill.

- **Observation unit: one calendar month.** Non-overlapping, therefore independent, per the
  `T15_RESULT.md` estimator rule. `n_months`, never `n_funding_prints`.
- `sd_annual = sd(monthly excess return) × √12`.
- `MDE_annual = z × sd_annual / √(years_in_window)`, **z = 2.80** (1.96 + 0.84; two-sided 5 %,
  80 % power) — the constant T9, T10, T15, T23 and T24 all used.

### 2a. The dispersion input, chosen so it cannot be selected conveniently

`sd_annual` is measured for **every declared `topN` ∈ {3, 5, 10, 20}**. The gate uses the
**SMALLEST** of them — i.e. the configuration most favourable to the candidate. Choosing the
largest would guarantee the death this gate exists to test for honestly.

### 2b. The download universe, declared with its limitation

API cost bounds the pull. The census downloads Hyperliquid funding history for:

> every overlap coin that (a) had a Binance USD-M perp quoting on ≥ 80 of the 92 days
> **2023-05-12 → 2023-08-11** — the first quarter of the joint span — **or** (b) is flagged
> `isDelisted` by Hyperliquid today.

Limb (b) exists so the panel is not survivors-only. **The limitation this leaves, stated here and
not in a footnote: coins first listed on Hyperliquid after 2023-08 are absent**, and new listings
are where the largest funding dislocations live. The census therefore **understates both the
available edge and its dispersion**, and the honest reading of a pass is "at least this powered",
of a fail "no better than this". Names in limb (a) are selected on volume in a window that
precedes 2023-08-12, so no post-screen information is used.

*Within* that download universe, the **monthly** universe is strictly point-in-time: a coin is
eligible in month `t` only if both venues published funding for it in month `t−1` and its Binance
trailing-30-day quote volume through the last day of month `t−1` was ≥ **\$20 M/day** (T21 §3d's
own threshold, applied point-in-time — the fix for T21's Leakage 1, exactly as T23 applied it).

---

## 3. The windows, frozen here

| window | span | months | years | burn status |
|---|---|---|---|---|
| **DESIGN** | 2024-10-01 → 2026-07-31 | 22 | 1.833 | **deliberately assigned the burned months.** T21 §3c/§3d searched exactly 2024-10 → 2026-07 on the Binance leg |
| **HELD-OUT** | 2023-06-01 → 2024-09-30 | 16 | 1.333 | **unburned.** No document in this programme has looked at Hyperliquid funding in this window |
| **FULL** | 2023-06-01 → 2026-07-31 | 38 | 3.167 | the charitable ceiling — *"if we spent the entire joint history of both venues"* |

The split is deliberately **backwards** in time so that the contaminated months become the design
window and the virgin months become the test. 2023-05 is dropped because Hyperliquid's history
starts mid-month.

No parameter, threshold, horizon or `topN` in any pre-registration following this census may be
chosen by looking at any month before 2024-10-01.

---

## 4. The effect the window must resolve, computed BEFORE any funding data was fitted

T21 §6.3 publishes the only claim that exists for this mechanism — a one-interval cross-sectional
snapshot of `|differential|` over 206 dual-listed assets:

| | median | p75 | p90 |
|---|---|---|---|
| `|HL − Binance| funding`, annualised | **2.06 pp/yr** | **11.41 pp/yr** | **32.37 pp/yr** |

Applying the §5 charges to each, **assuming persistence = 1.0** (i.e. the selected differential is
collected in full for the whole month — the most generous assumption available, and deliberately
generous because erring toward the candidate is the honest direction):

| gross | less friction 1.591 pp/yr | ÷ 2 (capital posted at BOTH venues) | less T-bill 3.843 pp | **= E** |
|---|---|---|---|---|
| p50 2.06 | 0.469 | 0.235 | −3.843 | **−3.61 pp/yr** |
| **p75 11.41** | 9.819 | 4.910 | −3.843 | **+1.07 pp/yr** ← **E_claim, primary** |
| p90 32.37 | 30.779 | 15.390 | −3.843 | **+11.55 pp/yr** ← `E_max`, the most generous reading that exists |

> **Recorded here because it is already decided by arithmetic and not by statistics: at the
> MEDIAN cross-venue differential this trade returns −3.61 pp/yr against T-bills before a single
> test is run.** Only the upper tail of the differential distribution is even a candidate.

---

## 5. The charges, frozen before the number exists

| charge | value | provenance |
|---|---|---|
| Binance USD-M perp taker fee | **5.0 bp/side** | `CITED_FEE_SCHEDULE`, VIP-0 (0.05 %) |
| Hyperliquid perp taker fee | **4.5 bp/side** | `CITED_FEE_SCHEDULE` (0.045 %) |
| Binance perp half-spread | **1.7 bp** | T21 §3e, first-party order-book measurement |
| Hyperliquid perp half-spread | **0.85 bp** | first-party, §1 of this document, 65 names, 2026-08-19 |
| **round trip, one full rotation** (open 2 legs + close 2 legs) | **24.1 bp** of rotated notional | = 2×(5.0+4.5) + 2×(1.7+0.85) |
| declared turnover | **55 % of the book per month** | T21 §3e's measured turnover for the analogous monthly top-N book |
| **friction drag** | **1.591 pp/yr** | 0.55 × 24.1 bp × 12 |
| capital multiplier | net ÷ **2.0** | collateral must be posted at **both** venues and neither cross-margins the other |
| benchmark | **by-year** 3-month T-bill, `research/data/t13_cache/cash.csv` (FRED DTB3) | `FINDINGS.md` Seq 670: this single choice moves the verdict |
| venue-failure tail | **+1.00 pp/yr**, applied as the §6 bar, not as a return charge | T23 §4's charge, **reused unchanged and therefore charitable**: it prices ONE custodial venue, and this trade needs two |

**Funding is the only P&L source modelled, plus mark divergence.** The book also carries the change
in the two venues' mark spread between entry and exit, because a long perp on A against a short perp
on B is long the (A − B) mark difference and its change is real P&L.

---

## 6. The required-edge bar, stated before the number exists

> **Net annualised return, after all charges in §5, minus the BY-YEAR 3-month T-bill, must exceed
> +1.00 pp/yr.**

**If the net edge does not clear +1.00 pp/yr, the mechanism is DEAD regardless of significance.**
The bar is T23's, unchanged, and is charitable here: T23 charged 1 pp for one custodial venue's
failure; this trade posts collateral at a custodial exchange **and** a smart-contract venue for
whose failure mode no base rate exists (T21 §6.1: *"changes its name from custody risk to
smart-contract and bridge risk"*).

---

## 7. The gates, each with its consequence in the same row

| gate | quantity | threshold | **consequence of FAILURE** |
|---|---|---|---|
| **G0** data census | share of eligible coin-months in the FULL window with Hyperliquid funding present | ≥ **0.95** | **the test is not run** |
| **G0b** survivorship proof | HL-delisted-today coins in the download universe that still return funding history | ≥ **5** | **the test is not run.** A panel with no dead names is a survivorship panel |
| **G1** portfolio power on the window that would be SPENT **(BINDING)** | `MDE_annual` on **HELD-OUT** (1.333 yr), z = 2.80, §2a dispersion | ≤ **E_claim = 1.07 pp/yr** | **POWER-BLOCKED. The held-out window is NOT spent**; verdict DEAD-BY-INSUFFICIENT-POWER |
| **G1b** the charitable ceiling **(BINDING)** | `MDE_annual` on **FULL** (3.167 yr) | ≤ **E_claim = 1.07 pp/yr** | if this also fails, **no split of this data can ever work** and the verdict is DEAD-BY-INSUFFICIENT-POWER **permanently on free data**, not merely today |
| **G1max** most-generous reading (reported, **not** blocking) | `MDE_annual` on **FULL** | ≤ **E_max = 11.55 pp/yr** | reported as a failure in the result; if even this fails the verdict is unambiguous |
| **G2** bar separation (diagnostic, **NOT** blocking) | `MDE_annual` on **FULL** | ≤ **E_claim − 1.00 = 0.07 pp/yr** | reported as a failure; does not by itself stop the test |
| **G3** month count | months in each window with ≥ 20 eligible screened names | design ≥ 18 **and** held-out ≥ 12 | **the test is not run** |
| **G4** capacity, reported whatever the verdict | implied book size at which one name's notional reaches 10 % of measured Hyperliquid top-20 depth | reported, not thresholded | — |

**G1 is the single binding gate; G1b is its permanent form.** G1max and G2 are explicitly
diagnostics and are written as such here so that no later document has to adjudicate between
readings — the failure `T17_POWER_GATE.md` had to footnote.

---

## 8. What this document forbids

- Re-reading it after the census and re-interpreting a threshold.
- Running the held-out window, or writing any pre-registration, if G1 fails.
- Choosing `sd_annual` as anything other than the smallest across the declared `topN` grid.
- Reporting the design-window differential as evidence of anything.
- Treating the download-universe limitation in §2b as a footnote rather than a stated bound.

---

*Frozen 2026-08-19. The census that judges against this file records this file's sha256 and asserts
it matches. No order was placed, no account created, no custody action taken, nothing purchased.*
