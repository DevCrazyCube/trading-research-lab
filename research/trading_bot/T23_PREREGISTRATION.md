# T23 — PRE-REGISTRATION: is T21's +2.20 pp/yr cross-sectional funding carry REAL out of sample?

**Status: FROZEN 2026-08-19, and the chain of custody is stated exactly rather than flattered.**

| # | event | what existed at that moment |
|---|---|---|
| 1 | `T23_POWER_GATE.md` frozen at sha256 `a9ce4fc0680e5972e76bb593b97f1b73cc5e8fe7ce28304614b0d20fca47e1e7` — windows, charges, benchmark, required-edge bar, and the one binding gate | **no T23 number of any kind** |
| 2 | `t23_carry.py` / `t23_run.py` / `t23_census.py` written; the DESIGN window run as a smoke test | design-window numbers only, which the protocol makes **burnable by construction** |
| 3 | power census run, judged against the gate, hash asserted and matched | `T23_POWER_CENSUS.json` |
| 4 | **this document hashed** | **`T23_HELDOUT_RESULT.json` did not exist — and, the census having returned POWER-BLOCKED, it still does not** |

**The load-bearing freeze is step 1, not step 4.** Everything that could have been chosen to
flatter a result — the two windows, the 36.8 bp round trip, the −2.00 % delisting tail, the ÷1.2
capital multiplier, the by-year T-bill benchmark, the +1.00 pp venue-tail bar, and the MDE
threshold `G1` is judged against — was fixed and hashed before a single funding print had been
read into the estimator. Nothing here may loosen anything there.

**Why this document exists even though the census blocked the test.** The held-out window was
**not spent**. This pre-registration is what makes it still spendable: it pins the rule, the trial
count and the five held-out gates at a hash, so that a future test — with a lower-variance
estimator, or more years, or a paid panel — is a *test* and not another search. `t23_run.py
heldout` refuses to run while the census verdict on disk is not `POWERED`.

---

## 1. The question, in one sentence

`NONDIRECTIONAL_INCOME_SHORTLIST.md` (T21) §3d–§3e reports **+2.20 pp/yr over T-bills** for a
liquidity-screened, cross-sectionally-ranked perpetual funding carry, and states in the same
section that the number carries **two leakages of its own author's finding, both running toward
the result.** A verifier found two more. **This document tests the same rule with all four
leakages closed, on a survivorship-complete panel, with the held-out window declared first.**

## 2. The four leakages, and the fix for each

| # | leakage | found by | fix, and where it lives in code |
|---|---|---|---|
| **L1** | the \$20 M/day liquidity screen used **today's** 24-hour volume applied to two-year-old history | T21's author, §3d | `t23_carry.screen_month()` reads the median daily quote volume over the **30 days ending on the last day of the month before the holding month**, from the historical dumps. `Panel.median_quote_volume()` takes an `as_of` and bisects; no bar after it is reachable |
| **L2** | threshold, horizon and `topN` were chosen after seeing §3c fail — a search-max with no declared trial count and no DSR | T21's author, §3d | the grid in §5 is declared here, **12 trials**, and the **primary configuration is inherited from T21 rather than searched**. DSR is computed at 12 trials with the cross-trial Sharpe variance measured on the DESIGN window |
| **L3** | the universe came from live `exchangeInfo` — survivors only; 127 perps are currently `SETTLING` and their trailing funding is median **−23.6 %/yr** | verifier | the universe is the **920 `fundingRate` symbol folders enumerated from `data.binance.vision`**, delisted names included (`LUNAUSDT`, `FTTUSDT`, `SRMUSDT` all present). A symbol enters and leaves the panel on its own data. The live endpoint is read exactly once, to COUNT how many held-out names are dead today (census gate G0b), and never for selection |
| **L4** | all 22 months were in-sample | verifier | design 2020-01 → 2022-12, held-out 2023-01 → 2026-07, frozen in the power gate before the census |

**And one omission neither party flagged.** T21 measured **realised funding only**. A short perp
against a long spot is short the premium, and the premium's change over the holding month is real
P&L. `t23_carry.month_return()` charges `−(premium_end − premium_start)` from
`premiumIndexKlines`. This is a fifth correction and it is not necessarily adverse.

## 3. What is frozen, and at what hash

| artifact | role | sha256 |
|---|---|---|
| `scripts/trading_bot/t23_carry.py` | **the rule.** Universe, point-in-time screen, ranking, holding, funding, basis, delisting tail, costs, capital multiplier, benchmark | `9ec1835a139ca5c54fb549ee9b5af6e7fa6de64d0637c480f3d6aecc2e96d453` |
| `scripts/trading_bot/t23_run.py` | the driver: the 12 declared trials, the two permutation nulls, DSR, the held-out gates | `b1206678703e30efeb1c3397849756bd2bee7a0c73f7640a24a82b4180246dbc` |
| `scripts/trading_bot/t23_census.py` | the power census, judged against the frozen gate | `cb8bdac79e1228bd6b9a9c1a52a9e7124d0f78683d0e7fdf1fe88d71e134b191` |
| `scripts/trading_bot/t23_collect.py` | data collection only; contains no decision | `735aa191215309df2e3ab6d0ae2b0936eb263917b76c6ff869338c57f7d5610d` |
| `research/trading_bot/T23_POWER_GATE.md` | windows, charges, benchmark, required-edge bar | `a9ce4fc0680e5972e76bb593b97f1b73cc5e8fe7ce28304614b0d20fca47e1e7` |
| `research/data/t23_cache/universe.json` | the survivorship-complete universe index | `4a17093778da8e53e4de9c4258dfae0df71ce41c91e03f08bc07cbcf7115904b` |
| `research/data/t23_cache/panel/PANEL_SHA256.json` | the three flat panels the rule reads | `cc797246c3729d3fcfe6ef4e2b551b02cd941bfefc581eb9fae7b1e299c93702` |

## 4. The rule under test

1. **Universe (point in time, survivorship-complete).** Every symbol with a `fundingRate` folder
   on `data.binance.vision` whose ticker ends `USDT`. `BUSD`- and `USDC`-quoted contracts are
   excluded as same-underlying duplicates of the USDT perp; including them would double-count the
   cross-section. A symbol is present in month *m* iff its own funding history covers month *m*.
2. **Listing age.** ≥ **60 days** of funding history before the holding month begins, and ≥ **20**
   funding prints inside the ranking month.
3. **Liquidity screen (point in time).** Median daily **quote volume** over the **30 calendar days
   ending on the last day of the month before the holding month** ≥ the threshold, with ≥ **20**
   daily bars present in that window. Never today's volume.
4. **Ranking.** Descending realised funding over the **previous calendar month** — T21's own
   signal, unchanged.
5. **Hold** the top *N* equal-weight for the whole holding month; rebalance monthly.
6. **Per-name P&L for the month** = `Σ funding` (the carrier receives positive funding)
   `− Δ premium` (short the premium; a rise is a loss) `−` the delisting tail if the name's
   funding history terminates in that month.
7. **Book P&L** = equal-weight mean, minus `turnover × 36.8 bp`, then **÷ 1.2** for capital
   committed twice, then minus the **by-year** monthly T-bill accrual.

### 4a. Charges (restated from the frozen gate so this document stands alone)

| charge | value |
|---|---|
| round trip per rotated notional | **36.8 bp** (30 bp published VIP-0 fees + 5.2 bp spot + 1.7 bp perp measured half-spreads) |
| delisting funding-cap tail | **−2.00 %** of that name's notional, once, if the name dies in the holding month |
| capital multiplier | **÷ 1.2** |
| benchmark | **by-year** 3-month T-bill, `FRED_DTB3` via `research/data/t13_cache/cash.csv`, read at the last quote **before** the holding month starts |
| venue-failure tail | **1.00 pp/yr**, applied as the required-edge **bar** (gate H2) |

## 5. The DECLARED trial count: 12

`top_n ∈ {3, 5, 10, 20}` × `threshold ∈ {$5 M, $20 M, $50 M}/day` = **12 trials**.

**The primary configuration is `liq20m_top3`** — `$20 M`, `top 3`, one-month horizon. It is
**inherited from T21 §3d, not chosen here.** That is what makes this a validation rather than a
second search: the headline number is fixed before the panel is looked at, and the other 11 cells
exist only to price the search that produced it.

**Three controls, declared as controls and ineligible to become the headline:** BTC-only;
equal-weight all screened names; equal-weight all unscreened names. They isolate whether any edge
comes from the screen, the ranking, or blind exposure.

## 6. The held-out gates. All five must pass, or the verdict is DEAD.

| gate | quantity | threshold |
|---|---|---|
| **H1** | net annualised excess over by-year T-bills | **> 0** |
| **H2** | the same, against the venue-failure tail bar | **> +1.00 pp/yr** — **THE DECISION GATE**; below it the mechanism is dead regardless of significance |
| **H3** | **DSR** at **12** declared trials, cross-trial Sharpe variance from the design window | **≥ 0.95** |
| **H4** | permutation p against the **joint null** — *N* names drawn at random each month from the point-in-time universe with **no** liquidity screen, same costs, same tail charge, 10,000 draws, seed 20260819 | **≤ 0.05** |
| **H5** | capacity: book size at which one name's notional reaches 10 % of that name's median daily volume, at `top_n` names | **≥ \$100,000** (the account) |

### 6a. H4b, a diagnostic whose interpretation is declared BEFORE the number

`H4b` is the same permutation drawn from the **screened** universe — it asks whether the funding
**ranking** adds anything beyond the screen. It is not binding. **Declared in advance: if H4b
fails while H4 passes, then the edge lives in the LIQUIDITY SCREEN and not in the funding
ranking**, which is precisely what T21 suspected in §3d, and the result document must say so in
those words.

## 7. What this pre-registration forbids

- Editing `t23_carry.py` after the held-out run.
- Running the held-out window if the census verdict is not `POWERED` — `t23_run.py heldout`
  refuses on the census file and exits non-zero.
- Reporting any held-out cell other than `liq20m_top3` as the headline.
- Reporting the 43-month held-out result without the contamination label: **T21 searched
  2024-10 → 2026-07, which is 22 of those 43 months.** The 21-month `2023-01 → 2024-09`
  sub-window is the only fully unburned part and is reported separately, with its own statement
  that 21 months resolves nothing on its own.
- Presenting a pass on H1/H3/H4 as a live-trading recommendation. Executability, leverage and
  venue are **T22's** job, and every custodial expression of this trade re-imports the FTX tail
  that prices it. **No order, no custody action, no venue account.**

---

*Frozen 2026-08-19.*
