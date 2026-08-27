# T23 — POWER GATE: what the free Binance panel must be able to SEE before it is allowed to answer

**Status: written and hashed BEFORE the census ran and before any T23 profit-and-loss number
existed.** At the moment the hash of this file was taken,
`research/trading_bot/T23_POWER_CENSUS.json`, `research/trading_bot/T23_DESIGN_RESULT.json` and
`research/trading_bot/T23_HELDOUT_RESULT.json` did not exist.

This document exists because two candidates in this programme (`T9`, `T15`) died **by insufficient
power, before their held-out window was spent**, and one (`T17`) spent its window under a gate
whose consequences were not stated crisply enough, which forced a two-reading footnote. The
lesson from both is the same: *state the threshold and the consequence in the same sentence, and
name the ONE binding gate.*

---

## 0. The claim on trial

`research/trading_bot/NONDIRECTIONAL_INCOME_SHORTLIST.md` §3e reports, for a liquidity-screened
cross-sectional perp funding carry:

| quantity | T21's value | role here |
|---|---|---|
| net return on capital | **+6.05 %/yr** | — |
| less trailing-12m 3-month T-bill | −3.84 pp | — |
| **edge over risk-free** | **+2.20 pp/yr** | **the effect this window must be able to resolve** |
| annualised sd of the top-3 book | **3.08 %** | the optimistic dispersion input |
| annualised sd of the top-20 book | 1.68 % | the most favourable dispersion in the family |
| in-sample window | 22 months, 2024-10 → 2026-07 | **burned**; see §2 |
| in-sample Sharpe / t | 3.14 / +4.26 | *gross*; the excess-over-T-bills Sharpe implied is 2.20/3.08 = **0.714** |

**The number that matters for power is not 3.14.** A Sharpe of 3.14 is computed on the gross
return. The quantity under test is the **excess over by-year T-bills**, whose implied Sharpe is
`2.20 / 3.08 = 0.714`. `T10`'s resolution arithmetic — `(2.80/S)²` years to certify Sharpe `S` —
therefore asks for **15.4 years**, not the "under a year" that 3.14 would suggest. This document
is written so that arithmetic is confronted before the window is spent rather than after.

---

## 1. The estimator whose power is being censused

A **monthly-rebalanced, equal-weight top-N book** of cash-and-carry positions (long the spot
index leg, short the perp), selected by trailing realised funding from a **point-in-time
liquidity-screened** universe, net of the frozen cost and tail model, minus the **by-year**
3-month T-bill.

- **Observation unit: one calendar month.** Non-overlapping, therefore independent, per the
  `T15_RESULT.md` rule. `n_months`, never `n_funding_prints`.
- `sd_annual = sd(monthly excess return) × √12`.
- `MDE_annual = z × sd_annual / √(years_in_window)`, with **z = 2.80** (= 1.96 + 0.84; two-sided
  5 %, 80 % power) — the same constant `T9`, `T10` and `T15` used.

### 1a. The dispersion input, chosen so it cannot be selected conveniently

Two candidate values for `sd_annual` exist: the one **measured on the design window** for the
primary configuration, and T21's **reported 3.08 %** from the burned window. The gate uses the
**LARGER of the two**. Both are printed in the census. Choosing the smaller would be exactly the
"silently select the more convenient claim" that `AGENTS.md` forbids, and the larger is the
hostile direction.

---

## 2. The windows, frozen here

The public monthly dumps at `data.binance.vision` begin **2020-01** for `fundingRate` and run to
**2026-07** (the current month is not yet published). 79 calendar months.

| window | span | months | years | burn status |
|---|---|---|---|---|
| **DESIGN** | 2020-01-01 → 2022-12-31 | 36 | 3.000 | free to burn; T21 never saw it |
| **HELD-OUT** | 2023-01-01 → 2026-07-31 | 43 | 3.583 | **PARTIALLY BURNED** — see below |

**The held-out window is not virgin, and pretending otherwise would be the same dishonesty this
task exists to correct.** T21's §3c/§3d searched **2024-10 → 2026-07 (22 months)**, which is 22
of these 43 held-out months. What is *known* from that search is: the liq-top-3 book returned
+9.67 %/yr gross, the monotone decline in `topN`, and that 2026-07 was the single bad month. So:

- **The 21 held-out months 2023-01 → 2024-09 are fully unburned** and are reported separately as
  `HELDOUT_CLEAN`.
- The full 43-month held-out result is reported as `HELDOUT_FULL` and is **labelled contaminated
  by T21's parameter search** wherever it appears.
- The **binding** power gate is computed on `HELDOUT_FULL` (43 months); the clean sub-window is
  reported as a diagnostic, because 21 months resolves nothing and saying so is the point.

No parameter, threshold, horizon or `topN` in the pre-registration that follows this census may be
chosen by looking at any month on or after 2023-01-01.

---

## 3. The gates, each with its consequence in the same row

| gate | quantity | threshold | **consequence of FAILURE** |
|---|---|---|---|
| **G0** data census | share of the 21,447 enumerated `fundingRate` symbol-months present on disk | ≥ **0.98** | **the test is not run.** A panel with holes is a survivorship panel again |
| **G0b** survivorship proof | number of held-out-window symbols that are **absent from today's live `exchangeInfo`** (i.e. delisted since) | ≥ **20** | **the test is not run.** If the panel contains no dead names the survivorship fix is not live and the whole exercise is void |
| **G1** portfolio power **(BINDING)** | `MDE_annual` on `HELDOUT_FULL`, at z = 2.80, using the §1a dispersion | ≤ **2.20 pp/yr** | **POWER-BLOCKED. The held-out window is NOT spent** and the verdict is DEAD-BY-INSUFFICIENT-POWER |
| **G2** bar separation (diagnostic, **NOT blocking**) | `MDE_annual` on `HELDOUT_FULL` | ≤ **1.20 pp/yr** | reported as a failure in the result document; does not by itself stop the test |
| **G3** month count | months in each window with ≥ `N` screened names available | design ≥ 30 **and** held-out ≥ 36 | **the test is not run** |
| **G4** cost resolution | symbol-months in the held-out window carrying a usable quote-volume bar | ≥ **0.95** of held-out symbol-months | **the test is not run** |

**G1 is the single binding gate.** G2 is explicitly a diagnostic and is written here as one so
that no later document has to adjudicate between two readings.

### 3a. Why G2 exists even though it does not block

The required-edge bar (§4) is **+1.00 pp/yr**, not zero. To claim T21's +2.20 pp *clears* that
bar, the window must resolve the 1.20 pp gap between them. If G2 fails while G1 passes, the
honest statement is "the window can see the effect but cannot see whether it clears the bar",
and the result document must say exactly that.

---

## 4. The required-edge bar, stated before the number exists

A pass on the statistical gates is **not** a pass on the decision. The frozen bar:

> **Net annualised return, after all charges in §5, minus the BY-YEAR 3-month T-bill, must exceed
> +1.00 pp/yr.**

The +1.00 pp is the **venue-failure tail charge**: T21 §3f counts six total-loss events for
venues holding customer crypto in twelve years (Mt Gox 2014, QuadrigaCX 2019, Celsius, Voyager,
BlockFi, FTX 2022), and even generously assuming fifty venues ever mattered that is ~1 %/yr per
venue with **loss given failure = 100 % of deployed capital**. The same charge appears in
`FINDINGS.md` §5d as the +1.47 pp bar that killed BTC-only carry.

**If the net edge does not clear +1.00 pp/yr, the mechanism is DEAD regardless of significance.**

---

## 5. The charges, frozen before the number exists

| charge | value | provenance |
|---|---|---|
| round-trip friction per rotation | **36.8 bp** of the notional rotated = 30 bp published Binance VIP-0 taker fees on the two legs + 5.2 bp spot half-spread + 1.7 bp perp half-spread | `CITED_FEE_SCHEDULE` + T21 §3e first-party order-book measurement |
| **delisting funding-cap tail** | **−2.00 % of position notional**, charged once, on any position held in a symbol whose funding history ends inside or at the end of the holding month | T21 §3f: the worst single 8-hour funding print measured in the condemned pool |
| capital multiplier | net return **÷ 1.2** — capital is committed twice, spot notional plus perp margin | T21 §3e |
| benchmark | **by-year** 3-month T-bill, `research/data/t13_cache/cash.csv` (`FRED_DTB3`), compounded over each holding month | `FINDINGS.md` Seq 670: this single choice moves the verdict |
| venue-failure tail | **1.00 pp/yr**, applied as the §4 bar rather than as a return charge | T21 §3f |

**Basis mark-to-market is charged, not ignored.** T21 measured realised funding only. The book
here also carries `−(premium_exit − premium_entry)` from the `premiumIndexKlines` series, because
a short perp against a long spot is short the premium and its change is a real P&L.

---

## 6. Capacity gate, declared first

The rule is **dead at any book size where the required per-name notional exceeds the measured
depth.** T21 measured \$52,862 of top-20 depth on the thinner leg at the median held name, and a
\$100 k book across three names needs \$33 k per name = **63 %** of that. The census reports, for
the held-out window, the **median trailing dollar volume of the names actually selected** and the
implied book size at which one name's notional reaches **10 %** of one day's volume. That number
is reported whatever the statistical verdict.

---

## 7. What this document forbids

- Re-reading it after the census and re-interpreting a threshold.
- Running the held-out window if G1 fails.
- Choosing `sd_annual` as the smaller of the two candidates in §1a.
- Reporting `HELDOUT_FULL` without the contamination label from §2.

---

*Frozen 2026-08-19. The census that judges against this file records this file's sha256 and
asserts it matches.*
