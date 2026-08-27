# T23 — FUNDING CARRY VALIDATION: is T21's +2.20 pp/yr real out of sample?

## VERDICT: **DEAD BY INSUFFICIENT POWER.** The free panel cannot answer the question, and the held-out window was NOT spent.

**The +2.20 pp/yr is neither confirmed nor refuted. It is UNRESOLVABLE on this data**, by a factor
of **2.07×** using the most favourable dispersion number that exists anywhere (T21's own 3.08 %),
and by **6.93×** using the dispersion actually measured on the panel. Certifying a +2.20 pp/yr
edge over T-bills on a book with this volatility needs **15.4 to 172 years**. `data.binance.vision`
publishes **6.6**.

> **The one sentence that explains the whole thing.** T21's "Sharpe 3.14, t = +4.26" is the Sharpe
> of the **gross return**. The quantity actually on trial is the **excess over T-bills**, whose
> implied Sharpe is `2.20 / 3.08 = 0.714` — and `T10`'s resolution arithmetic `(2.80/S)²` turns
> that into **15.4 years, not "under a year."** Every subsequent number in this document follows
> from that single substitution, and it was written into the frozen power gate *before* the census
> ran.

**Three things were nonetheless established, and they are not small:**

1. **All four leakages are fixed in code**, and the survivorship fix is **materially large**:
   **31.2 % of the distinct names the rule selects no longer trade**, and **22.7 % of all
   name-month selections involve a name that is dead today**. T21's universe, built from live
   `exchangeInfo`, could not have selected any of them.
2. **The liquidity screen — the component T21 credits the entire edge to — does not have a stable
   sign.** On the 34 design-window months T21 never saw, applying it **reduced** return and Sharpe
   at every `topN` tested. On T21's own 22 months it reversed a −70.67 %/yr loss into a +9.67 %/yr
   gain. §5.
3. **The panel is now cached, hashed and reproducible** — 63,801 raw archives, 2,721,204 funding
   prints, 420 MB on disk — and the BTC leg reconciles **exactly** against this repository's
   pre-existing independently-pulled series. T21 pulled 1.07 M prints and discarded them; that is
   not repeated.

---

## 1. Chain of custody — what was frozen, when, and against what

| # | event | what existed at that moment | hash |
|---|---|---|---|
| 1 | `T23_POWER_GATE.md` frozen: windows, charges, benchmark, required-edge bar, the one **binding** gate and its consequence | **no T23 number of any kind** | `a9ce4fc0680e5972e76bb593b97f1b73cc5e8fe7ce28304614b0d20fca47e1e7` |
| 2 | panel collected from `data.binance.vision`, rule written, DESIGN window smoke-tested | design-window numbers only — **burnable by construction** | panel `PANEL_SHA256.json` = `cc797246c3729d3f…` |
| 3 | **power census** run; it re-hashed the gate and asserted the match | `T23_POWER_CENSUS.json`; `"matches": true` | — |
| 4 | `T23_PREREGISTRATION.md` frozen: the rule, the 12 declared trials, the five held-out gates | **`T23_HELDOUT_RESULT.json` did not exist** | `030ec5a0f226ff5c435928a4d4c0e7187b8e6fe324db3496824c2f9886cd64f3` |
| 5 | `t23_run.py heldout` invoked | **refused, exit 2**, and `T23_HELDOUT_RESULT.json` **still does not exist** | — |

Step 5 is the protocol working rather than being described:

```
$ python3 scripts/trading_bot/t23_run.py heldout
REFUSING to spend the held-out window: census verdict is POWER-BLOCKED.
T23_POWER_GATE.md G1 says the window is NOT spent when the census fails.
```

Everything that could have been chosen to flatter a result — the two windows, the 36.8 bp round
trip, the −2.00 % delisting tail, the ÷1.2 capital multiplier, the **by-year** T-bill benchmark,
the **+1.00 pp venue-failure bar** and the MDE threshold G1 is judged against — was fixed at step 1,
before a single funding print had been read into the estimator.

---

## 2. The panel: survivorship-complete, cached, and reconciled

| quantity | value |
|---|---|
| source | `data.binance.vision` bucket listing, 43 pages, `data/futures/um/monthly/fundingRate/` |
| symbol folders (the **universe index**) | **920**, delisted names included |
| USDT perps used | **833** — of which **675 alive today, 158 (19.0 %) dead** |
| symbol-months enumerated | **21,447** |
| raw archives cached | **63,801** (funding + 1d klines + 1d premium index), 540 absent, **420 MB** |
| funding prints | **2,721,204** |
| daily perp bars / daily premium bars | 634,608 / 620,625 |
| calendar span | **2020-01 → 2026-07**, 79 months |
| coverage (census G0) | fundingRate **1.0000**, klines **0.9945**, premium **0.9803** |

`BUSD`- and `USDC`-quoted contracts are excluded as same-underlying duplicates of the USDT perp;
including them would double-count the cross-section.

### 2a. Independent reconciliation of the ingestion

The repository already held `research/data/btc_perp_funding_binance_2019_2026.csv`, pulled
months earlier from the **live REST API** by a different piece of code. Against it:

| check | result |
|---|---|
| T23 `BTCUSDT` prints | 7,212 |
| overlapping with the legacy series | **7,212 — every one** |
| **max absolute difference in rate** | **0.0** |
| legacy-only prints | 374, all either **2019-09 → 2019-12** (before the monthly dumps begin) or **2026-08** (current month, not yet dumped) |

The dump-based ingestion is byte-equivalent to an independent API pull. The panel's start date of
2020-01 is a property of Binance's archive, not of this code.

---

## 3. The census: why the answer is "unresolvable" and not "yes" or "no"

Judged against the frozen gate. Verdict **POWER-BLOCKED**.

| gate | quantity | threshold | measured | |
|---|---|---|---|---|
| **G0** data census | fundingRate symbol-month coverage | ≥ 0.98 | **1.0000** | pass |
| **G0b** survivorship proof | held-out-window symbols delisted since | ≥ 20 | **146** of 821 | pass |
| **G1** portfolio power **(BINDING)** | MDE of annualised excess, z = 2.80 | ≤ **2.20 pp** | **15.25 pp** | **FAIL, 6.93×** |
| **G2** bar separation (diagnostic) | same | ≤ 1.20 pp | 15.25 pp | fail, 12.7× |
| **G3** month count | design / held-out usable months | ≥ 30 / ≥ 36 | **34 / 43** | pass |
| **G4** cost resolution | held-out symbol-months with a volume bar | ≥ 0.95 | **0.9943** | pass |

**Every data gate passes. The panel is fine. The estimator is too noisy for the claim.**

### 3a. And the verdict does not depend on the convenient choice

The gate required the **larger** of two dispersion inputs, so the census also reports the smaller:

| dispersion input | MDE on the 43 held-out months (3.583 y) | MDE on the **whole** 77-month panel spent in one shot (6.417 y) | years to certify **+2.20 pp** | years to separate +2.20 from the **+1.00 pp bar** |
|---|---|---|---|---|
| **10.31 pp** — measured on the design window, the gate's input | **15.25 pp** (6.93× miss) | 11.39 pp (5.18× miss) | **172.1** | 578.5 |
| **3.08 pp** — T21's own reported figure, the most favourable number in existence | **4.56 pp** (2.07× miss) | 3.40 pp (1.55× miss) | **15.4** | 51.6 |

> **Even the entire free panel, spent in one shot with no design allowance at all, at the most
> optimistic dispersion anybody has published for this strategy, misses by 1.55×.** There is no
> arrangement of these 6.4 years that resolves +2.20 pp/yr.

**Turned round, the same arithmetic states what this panel *can* see:** a funding-carry edge of
**≥ 11.4 pp/yr** over T-bills. Anything smaller is invisible to it. T21's claim is **2.20**.

### 3b. The basis leg is not what broke the power — and that was declared in advance

T21 measured **realised funding only**; a short perp against a long spot is also short the premium,
and this implementation charges `−Δpremium` from `premiumIndexKlines`. Pre-declared diagnostic, so
that a G1 failure could not be dismissed as an artefact of the extra leg:

| estimator | design-window annualised sd | MDE on held-out |
|---|---|---|
| with the basis mark-to-market (the rule) | 10.308 pp | 15.25 pp |
| **funding-only — T21's own object** | **10.324 pp** | **15.27 pp** |

The premium leg contributed **+0.15 pp/yr of return and essentially nothing to the variance**. The
power failure is a property of the strategy, not of the correction.

---

## 4. The four leakages: all fixed, and one of them is enormous

| # | leakage | found by | status |
|---|---|---|---|
| **L1** | liquidity screen used **today's** 24h volume on a two-year-old history | T21's author (§3d) | **FIXED.** `screen_month()` takes the median daily quote volume over the 30 days ending on the last day of the month *before* the holding month; `median_quote_volume()` bisects at an `as_of` and no later bar is reachable |
| **L2** | threshold / horizon / `topN` chosen after an earlier pass failed; no trial count, no DSR | T21's author (§3d) | **FIXED.** 12 trials declared in the pre-registration; the primary cell is **inherited from T21, not searched**; DSR at 12 trials is gate H3 |
| **L3** | universe from live `exchangeInfo` — survivors only | verifier | **FIXED.** Universe = the 920 dump folders. `LUNAUSDT`, `FTTUSDT`, `SRMUSDT` present and selectable |
| **L4** | all 22 months in-sample | verifier | **FIXED.** Design 2020-01→2022-12, held-out 2023-01→2026-07, frozen before the census — and the held-out half is still unspent |

### 4a. How big L1/L3 actually were

Across the 12 declared trials on the design window:

| quantity | value |
|---|---|
| distinct names the rule selected | **138** |
| of which **no longer trading today** | **43 — 31.2 %** |
| name-month selections involving a now-dead name | **806 of 3,555 — 22.7 %** |
| names in the top-3 book that later died outright | `LUNAUSDT` (Oct **and** Nov 2021), `SRMUSDT` (Jan 2022), `ATAUSDT`, `ANTUSDT`, `ALPHAUSDT`, `FOOTBALLUSDT`, … |

**`LUNAUSDT` is a top-3 holding in October and November 2021 and the contract is dead by May
2022.** A universe built from today's `exchangeInfo` cannot select it, cannot hold it, and cannot
be charged for it. Nearly a quarter of this strategy's history is invisible to the way T21 built
its universe.

---

## 5. What the design window says — labelled IN-SAMPLE, and it is the most useful thing here

The design window (2020-03 → 2022-12, 34 usable months) is burnable by construction and T21 never
saw it. **These are not validation numbers.** They are what the fixed rule does in the richest
funding regime the panel contains, and they carry two findings that survive the power block.

### 5a. The primary cell, `liq20m_top3`, decomposed

| step | %/yr |
|---|---|
| funding received | **+24.91** |
| less basis mark-to-market (`−Δpremium`) | +0.15 |
| = gross | **+25.06** |
| less friction (80 % turnover/month × 36.8 bp) | −3.55 |
| less delisting funding-cap tail | **−0.00** |
| ÷ 1.2 for capital committed twice | → **+17.92 on capital** |
| less **by-year** T-bill (design window: **0.72 %/yr**) | −0.72 |
| **excess over by-year T-bills** | **+17.21** |
| annualised sd / Sharpe / t | 10.31 / **1.67** / +2.81 |
| worst month / max drawdown / negative months | −2.46 % / −5.33 % / 9 of 34 |

### 5b. The controls, and the first finding that survives

| book | excess pp/yr | sd | **Sharpe** |
|---|---|---|---|
| `liq20m_top3` — the cross-sectional rule | **+17.21** | 10.31 | **1.67** |
| all screened names, equal weight | +12.25 | 7.86 | 1.56 |
| all **unscreened** names, equal weight | +12.90 | 8.17 | 1.58 |
| **BTC only** | **+12.64** | **5.11** | **2.47** |

> **Carrying BTC and nothing else had a HIGHER Sharpe than the cross-sectional book, at half the
> volatility and a −0.69 % maximum drawdown against −5.33 %.** The cross-sectional machinery bought
> +4.6 pp of return by taking +5.2 pp of volatility. In the window where the mechanism paid best,
> the clever version was the worse risk-adjusted trade.

### 5c. The second finding, and it is the one that should worry anybody quoting +2.20 pp

Post-census control on the design window, one consistent implementation, screen on vs off:

| book | excess pp/yr | Sharpe | worst month |
|---|---|---|---|
| top 1, **unscreened** | **+29.17** | **2.74** | −1.37 % |
| top 1, \$20 M screen | +16.69 | 1.24 | −8.26 % |
| top 3, **unscreened** | **+22.44** | **2.34** | −0.72 % |
| top 3, \$20 M screen | +17.21 | 1.67 | −2.46 % |
| top 5, **unscreened** | **+21.50** | **2.28** | −0.30 % |
| top 5, \$20 M screen | +16.08 | 1.57 | −3.58 % |

**On these 34 months the liquidity screen HURT at every `topN` — in return, in Sharpe, and in worst
month.** T21 §3c/§3d reports the exact opposite on its own 22 months: unscreened top-1 at
**−70.67 %/yr gross**, screened top-3 at **+9.67 %/yr gross**, and describes the screen as
"reversing the sign".

**Stated with its caveats, because the caveats matter.** The two windows are different regimes;
T21's screen used today's 24h volume at a \$20 M cut while this one uses a point-in-time 30-day
median; T21's figures are gross and survivor-only while these carry costs, the basis and the
delisting tail. **This is not an arithmetic refutation of T21.** What it is, is direct evidence
that **the screen's contribution is not sign-stable across the panel** — which is what a
search-max artefact looks like, and it is the specific component T21 attributes the entire edge to.

**And there is a mechanism for the instability, which matters more than the sign.** The universe
grew from **11 symbols in 2020-01 to 727 in 2026-07**. In 2020–2022 there was barely an illiquid
tail to screen out — the unscreened top-1 book's own picks had a median trailing volume of
\$11.6 M. By 2024–2026 the tail is hundreds of names deep and screening it away is worth a great
deal. **The early years therefore cannot inform the late years about this rule**, which is an
independent, structural reason a design→held-out split on this panel is weak *even if the power
had been there.*

### 5d. What the screen demonstrably does buy

The delisting funding-cap tail, charged at the measured −2.00 % of notional:

| book | delisting-months held | tail charge |
|---|---|---|
| `liq20m_top3` | **0** | 0.000 pp/yr |
| all screened, equal weight | 6 | 0.07 pp/yr |
| all unscreened, equal weight | 10 | 0.07 pp/yr |

The screen buys away the delisting tail. In this window that is worth **0.07 pp/yr**. It is not
worth 2.20.

---

### 5e. A new contamination of the held-out window, disclosed rather than left for the next reader to trip over

**T22 ran in parallel with this task and published `LEVERAGED_FUNDING_CARRY.md` while this
document was being written.** It measures, on **2023–2026** — inside T23's held-out window — a
**BTC-only** Binance cash-and-carry book at **+0.66 pp/yr over T-bills at L = 1** and **+0.71 pp
at its best leverage**, and finds the mechanism DEAD at every useful leverage for reasons of its
own (the spot leg is unlevered, and perp funding minus the market price of USD financing is
**−0.81 pp/yr since 2024-01, t = −4.15**).

**Three things follow and all three should be recorded.**

1. **It does not spend T23's held-out window.** T22's object is BTC-only carry — a *control* here,
   not the frozen primary — and no score for `liq20m_top3` on 2023-01→2026-07 exists in this
   repository.
2. **It is nonetheless a burn on the held-out window's BTC control**, in exactly the sense T21's
   search was a burn, and a future tester of the frozen rule must know it before quoting the BTC
   control as clean.
3. **It corroborates the direction without resolving the question.** T22's held-out-period BTC
   number, **+0.66 pp/yr**, sits *below* this document's frozen **+1.00 pp/yr venue-tail bar** —
   consistent with `FINDINGS.md` §5d's original −0.46 pp close, and consistent with a world in
   which T21's +2.20 pp does not survive. **It is not evidence that it does not.** The census's
   whole point is that a 3.6-year read at this dispersion cannot separate +0.66 from +2.20 from 0.

---

## 6. Capacity, reported whatever the verdict

| measure | value | what it means |
|---|---|---|
| median trailing daily **volume** of the design picks | **\$60.2 M** | the screen does select genuinely traded names |
| book size at 10 % of one day's volume across 3 names | **\$18.1 M** | the *volume* ceiling, and it is not the binding one |
| T21's measured instantaneous **top-20 depth**, thinner leg, median held name | **\$52,862** | **the binding one** |

**Daily volume is not depth.** A \$100 k book across three names is \$33 k per name, which is
**63 %** of the measured top-20 depth on the thinner leg — so the 5.2 bp median spread charged in
the cost model is a **floor, not the cost, at our own account size**. Nothing in this document
relaxes T21 §3f's conclusion that a \$100 k account is already too large for the top-3 form.

---

## 7. What would change the answer, stated so nobody re-runs this

The binding constraint is **dispersion, not years.** To certify +2.20 pp/yr on the 6.4 years that
exist, the annualised sd of the excess series would have to be **≤ 1.99 pp**. The quietest book
measured anywhere in this exercise is BTC-only at **5.11 pp**. So:

- **More free history will not fix it.** Binance's archive begins 2020-01 and that is the whole of it.
- **A quieter estimator might.** Anything that removes the common funding factor — a
  long-rich/short-cheap *cross-sectional spread* rather than an absolute book — could cut the
  dispersion several-fold. That is a different strategy and needs its own pre-registration.
- **A paid, longer, multi-venue panel** would help linearly in √years and is therefore worth ~1.55×
  at best against the 3.08 pp figure: **~15 years of clean panel** is the requirement.
- **The held-out window is preserved.** `T23_PREREGISTRATION.md` pins the rule, the 12 trials and
  the five held-out gates at sha256 `030ec5a0…`, and `t23_run.py heldout` refuses while the census
  says POWER-BLOCKED. Whoever earns the power gets a real test, not another search.

**What is NOT recommended.** Quoting +2.20 pp/yr as a measured edge. It is a search-max on 22
months with four leakages, its central component has an unstable sign, and the panel that could
have adjudicated it cannot.

---

## 8. Guardrails, and how each was honoured

| guardrail | how |
|---|---|
| point-in-time everything; the screen uses only trailing data | `median_quote_volume(sym, as_of)` bisects a sorted array at `as_of` = last day of the month **before** the holding month. No call site can pass a later date. The live `exchangeInfo` endpoint is read **once**, to *count* dead names for census gate G0b, and never for selection |
| survivorship-complete universe incl. delisted names | universe = the **920** `fundingRate` folders in the dump index; **158 of the 833 USDT perps are dead today** and all remain selectable in their own lifetimes |
| delisting funding-cap tail charged | **−2.00 %** of notional, the measured worst 8h print, charged on any name whose funding history terminates inside the holding month. Frozen in the gate before any number |
| required-edge bar stated before the number | **+1.00 pp/yr over by-year T-bills**, the venue-failure tail, in `T23_POWER_GATE.md` §4, hashed before the census |
| trials declared; freeze before fitting | **12**, in the pre-registration; the primary cell inherited from T21 rather than searched |
| cache data + reproducible code | 420 MB of raw archives on disk, sha256 manifest, three flat panels hashed in `PANEL_SHA256.json`, four scripts hashed in the pre-registration. **T21's discard-the-prints violation is not repeated** |
| no secrets, no orders, no custody, no purchase, no git commit | none of the above occurred. Every endpoint used is public and keyless |

---

## 9. Artifacts

| path | what |
|---|---|
| `research/trading_bot/T23_POWER_GATE.md` | the gate, frozen first — `a9ce4fc0…` |
| `research/trading_bot/T23_POWER_CENSUS.json` | the census, judged against it, `"matches": true` |
| `research/trading_bot/T23_PREREGISTRATION.md` | the rule, 12 trials, five held-out gates — `030ec5a0…` |
| `research/trading_bot/T23_DESIGN_RESULT.json` | design-window results, all 12 trials + 3 controls |
| `research/trading_bot/T23_HELDOUT_RESULT.json` | **deliberately absent** |
| `scripts/trading_bot/t23_collect.py` | enumerate / download / panel / verify |
| `scripts/trading_bot/t23_carry.py` | **the rule** |
| `scripts/trading_bot/t23_census.py` | the census |
| `scripts/trading_bot/t23_run.py` | design / held-out driver, refuses on a failed census |
| `research/data/t23_cache/` | 920 symbols, 63,801 archives, 3 flat panels, all hashed |

---

*T23, 2026-08-19. Scope: the EDGE only. Executability, leverage and venue are T22's. Binance.com
perpetuals do not serve US persons and Alpaca's crypto is spot-only and non-marginable, so neither
leg of this trade is expressible at our broker; every custodial expression re-imports the FTX tail
that prices it, and choosing a custody model is an owner call. No order was placed, no account
exists, and nothing here authorises real-money execution.*
